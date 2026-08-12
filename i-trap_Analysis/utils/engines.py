import pandas as pd
import numpy as np
from collections import defaultdict
from utils.data_processor import BORDER_PROVINCES, haversine_km


def get_2d_hideout_estimates(df_plate):
    """
    ประเมินพิกัดแหล่งกบดานและจุดพัก 3 มิติ (ตามมาตรฐานข่าวกรองสากล UK NADC / Interpol):
    - มิติที่ 1 (ฐานกบดานถาวร): จุดที่หายไป >12 ชม.
    - มิติที่ 2 (จุดแวะพักสินค้าชั่วคราว): จุดที่หายไป 3-12 ชม.
    - มิติที่ 3 (จุดอับสงสัยถอดเปลี่ยนป้าย/สลับสินค้า): รอยต่อที่หายไป 1-3 ชม. ระหว่างจุดตรวจ
    """
    if df_plate is None or df_plate.empty or len(df_plate) < 2:
        return None, None, None

    df_sorted = df_plate.sort_values('Datetime').reset_index(drop=True)
    perm_base = None
    temp_stop = None
    swap_stop = None

    long_stops = df_sorted[df_sorted['Time_diff_hrs'] > 12.0]
    if not long_stops.empty:
        top_stop = long_stops.iloc[0]
        idx = df_sorted.index.get_loc(top_stop.name)
        prev_row = df_sorted.iloc[idx - 1] if idx > 0 else top_stop
        perm_base = {
            "cam_from": prev_row['จุดติดตั้งกล้อง'],
            "cam_to": top_stop['จุดติดตั้งกล้อง'],
            "lat": (top_stop['ละติจูด'] + prev_row['ละติจูด']) / 2.0,
            "lon": (top_stop['ลองจิจูด'] + prev_row['ลองจิจูด']) / 2.0,
            "hours_missing": top_stop['Time_diff_hrs']
        }

    temp_stops = df_sorted[(df_sorted['Time_diff_hrs'] >= 3.0) & (df_sorted['Time_diff_hrs'] <= 12.0)]
    if not temp_stops.empty:
        top_temp = (
            temp_stops
            .groupby(['จุดติดตั้งกล้อง', 'ละติจูด', 'ลองจิจูด'])
            .size().reset_index(name='count')
            .sort_values('count', ascending=False)
            .iloc[0]
        )
        temp_stop = {
            "cam": top_temp['จุดติดตั้งกล้อง'],
            "lat": top_temp['ละติจูด'],
            "lon": top_temp['ลองจิจูด'],
            "visit_count": top_temp['count']
        }

    # มิติที่ 3: จุดอับสงสัยสลับป้ายทะเบียน (1 - 3 ชม. ระหว่างจุดตรวจ)
    swap_gaps = df_sorted[(df_sorted['Time_diff_hrs'] >= 1.0) & (df_sorted['Time_diff_hrs'] < 3.0) & (df_sorted['dist_km'] > 15.0)]
    if not swap_gaps.empty:
        top_swap = swap_gaps.iloc[0]
        idx = df_sorted.index.get_loc(top_swap.name)
        prev_row = df_sorted.iloc[idx - 1] if idx > 0 else top_swap
        swap_stop = {
            "cam_from": prev_row['จุดติดตั้งกล้อง'],
            "cam_to": top_swap['จุดติดตั้งกล้อง'],
            "lat": (top_swap['ละติจูด'] + prev_row['ละติจูด']) / 2.0,
            "lon": (top_swap['ลองจิจูด'] + prev_row['ลองจิจูด']) / 2.0,
            "hours_missing": top_swap['Time_diff_hrs'],
            "dist_km": top_swap['dist_km']
        }

    return perm_base, temp_stop, swap_stop


# ─────────────────────────────────────────────────────────────────────────────
# ENGINE 2 HELPERS: TOS / HRI / Gap Penalty (itrap_agent logic)
# ─────────────────────────────────────────────────────────────────────────────

def _compute_tos_hri_gap(df_target, cv_cars, shared_cams, tpivot):
    """
    TOS  — Tactical Order Score: นับครั้งสลับตำแหน่งรถนำ
    HRI  — Headway Regularity Index: วัด CV ของช่องว่างเวลา
    Gap  — Missing Camera Penalty: ปรับตามจำนวนกล้องในทริปเกิดเหตุ (ไม่ใช้ประวัติ 6 เดือนทั้งปี)

    คืนค่า (leader, swaps, tos, hri, gap_penalty, gap_cnt, avg_gap)
    """
    # ─ TOS ────────────────────────────────────────────────────────
    cams_in_order = sorted(
        shared_cams,
        key=lambda c: min(
            (tpivot.get((car, c), pd.Timestamp.max) for car in cv_cars),
            default=pd.Timestamp.max
        )
    )
    leader = cv_cars[0]
    swaps  = 0
    if cams_in_order:
        fa = {car: tpivot.get((car, cams_in_order[0]))
              for car in cv_cars if (car, cams_in_order[0]) in tpivot}
        if fa:
            leader = min(fa, key=fa.get)
            for cam in cams_in_order[1:]:
                ca = {car: tpivot.get((car, cam))
                      for car in cv_cars if (car, cam) in tpivot}
                if len(ca) >= 2 and min(ca, key=ca.get) != leader:
                    swaps += 1

    tos = 1.0 if swaps == 0 else (0.85 if swaps == 1 else 0.70)

    # ─ HRI ────────────────────────────────────────────────────────
    gaps_sec = []
    for cam in shared_cams:
        cd = df_target[df_target['จุดติดตั้งกล้อง'] == cam].sort_values('Datetime')
        if len(cd) >= 2:
            ct = cd['Datetime'].tolist()
            for gi in range(1, len(ct)):
                g = (ct[gi] - ct[gi - 1]).total_seconds()
                if 0 < g < 1800:
                    gaps_sec.append(g)

    if gaps_sec:
        mn     = np.mean(gaps_sec)
        cv_val = np.std(gaps_sec) / mn if mn > 0 else 1.0
        hri    = 1.0 if cv_val < 0.5 else (0.9 if cv_val < 1.0 else 0.7)
    else:
        hri = 0.9

    # ─ Gap Penalty ────────────────────────────────────────────────
    # คำนวณเฉพาะกล้องในวันที่มีเหตุการณ์ขบวนร่วม (ไม่ใช้ประวัติ 6 เดือนทั้งปี)
    dates_in_events = df_target[df_target['จุดติดตั้งกล้อง'].isin(shared_cams)]['วันที่'].unique()
    target_date_df = df_target[df_target['วันที่'].isin(dates_in_events)]
    max_cams_on_dates = max(
        (target_date_df[target_date_df['ทะเบียนรถ'] == car]['จุดติดตั้งกล้อง'].nunique()
         for car in cv_cars),
        default=len(shared_cams)
    )
    gap_cnt = max(0, max_cams_on_dates - len(shared_cams))
    gap_pen = 1.0 if gap_cnt == 0 else (0.9 if gap_cnt <= 2 else 0.75)

    avg_gap = np.mean(gaps_sec) if gaps_sec else 240.0
    return leader, swaps, tos, hri, gap_pen, gap_cnt, avg_gap


def run_fused_engines(df_active, convoy_time_limit_min=10):
    """
    ประมวลผล 5 เครื่องยนต์สืบสวน (E1–E5) พร้อมภาษาทางการข่าวกรอง

    ── ตรรกะที่เพิ่มจาก itrap_agent ────────────────────────────────
    E1 Ghost Plate    : เหมือนเดิม (vectorized) + 3 conditions (UK NADC/Interpol)
    E2 Convoy         : + TOS, HRI, Gap Penalty, Direction Coherence
                        Window = 10 นาที (600 วินาที) | Min Shared Cams = 4 | Dist ≥ 100 km
                        TOS swaps≥2 → Hard REJECT | Direction inconsistent → Hard REJECT
                        รถที่ REJECT จาก convoy → ส่งต่อเป็น E5_Route
    E3 U-turn Border  : + Zone A จริง, Overnight (4-12h), Repeat Offender ≥3วัน
                        Min Cams = 5 | Dist ≥ 150 km | Score ≥ 80
                        + บังคับ ≥3 triggers, traffic evasion
    E4 Night Ghost    : + บังคับ ≥2 คืน, Deep Night (00-04), ไม่ซ้ำ E1/E3
    E5 Suspect        : + Route Runner (วิ่งเส้นทางยาวแต่ไม่ใช่ขบวน)
    Apex Threat       : โดน ≥2 Engine → ยกระดับเป็น "กลุ่มเป้าหมายความมั่นคงระดับสูงสุด"
    ────────────────────────────────────────────────────────────────
    """
    cloned_cases  = {}
    convoy_cases  = {}
    suspect_cases = {}

    if df_active is None or df_active.empty or 'ทะเบียนรถ' not in df_active.columns:
        return cloned_cases, convoy_cases, suspect_cases

    df = df_active

    # Pre-group by plate ครั้งเดียว → O(n) แทน O(n²)
    plate_groups = {
        plate: grp.sort_values('Datetime')
        for plate, grp in df.groupby('ทะเบียนรถ')
    }

    # ──────────────────────────────────────────────────────────────
    # 🚨 ENGINE 1: รถสวมทะเบียน (Ghost Plate Paradox)
    # ──────────────────────────────────────────────────────────────
    twin_plates = df.loc[df['is_twin'] == True, 'ทะเบียนรถ'].unique()

    for plate in twin_plates:
        p_df = plate_groups.get(plate)
        if p_df is None or p_df.empty:
            continue

        max_spd    = p_df['Speed_kmh'].max()
        num_cams   = p_df['จุดติดตั้งกล้อง'].nunique()
        total_dist = p_df['dist_km'].sum()
        seen_days  = p_df['วันที่'].nunique()

        workday_cnt = int((~p_df['Is_Weekend']).sum())
        weekend_cnt = int(p_df['Is_Weekend'].sum())
        day_pattern_text = (
            f"เน้นวันทำงาน (จันทร์-ศุกร์) จำนวน {workday_cnt} ครั้ง"
            if workday_cnt >= weekend_cnt
            else f"เน้นวันหยุด (เสาร์-อาทิตย์) จำนวน {weekend_cnt} ครั้ง"
        )

        night_cnt   = int(p_df['Is_Night'].sum())
        night_ratio = (night_cnt / max(len(p_df), 1)) * 100.0
        deep_night_cnt = int(((p_df['Hour'] >= 0) & (p_df['Hour'] < 5)).sum())
        diurnal_inv_pct = (deep_night_cnt / max(len(p_df), 1)) * 100.0
        time_pattern_text = (
            f"🚨 สัญจรดึกดื่นวิกาลหนาแน่น (Diurnal Inversion {diurnal_inv_pct:.1f}%) [00:00-04:30 น.]"
            if diurnal_inv_pct >= 50.0
            else (f"สัญจรห้วงเวลากลางคืนวิกาลหนาแน่น ({night_ratio:.1f}%)" if night_ratio >= 40 else "สัญจรห้วงเวลากลางวันปกติ")
        )

        top_cam   = p_df['จุดติดตั้งกล้อง'].value_counts().index[0] if not p_df.empty else "ไม่ระบุ"
        provinces = list(set(p_df['จังหวัด'].unique()) - {"", "ไม่ระบุ"})
        prov_str  = ", ".join(provinces) if provinces else "ไม่ระบุ"

        cloned_cases[plate] = {
            "case_id": f"CLONE_{plate}", "plate": plate,
            "engine_type": "E1", "engine_name": "🚨 รถสวมทะเบียน (Ghost Plate Paradox)",
            "threat_category": "กลุ่มเป้าหมายสวมสิทธิ์แผ่นป้ายทะเบียน",
            "verdict_badge": "🛑 สมควรดำเนินการสกัดจับและควบคุมตัวทันที",
            "verdict_text": (
                "คำวินิจฉัยการปฏิบัติการ: สมควรจัดกำลังสายตรวจเข้าดำเนินการสกัดจับ"
                "ณ จุดตรวจหน้าทางสายหลักทันที เนื่องจากปรากฏดัชนีพฤติกรรมสวมแผ่นป้ายทะเบียน (Ghost Plate Paradox)"
            ),
            "risk_score": 100, "confidence_level": 95,
            "confidence_text": (
                "🟢 ความน่าเชื่อถือทางการข่าวสูงมาก (95%) — ตรวจพบดัชนีทางฟิสิกส์"
                "การเคลื่อนที่สลับตำแหน่งข้ามพิกัดเร็วเกินขีดจำกัดทางกายภาพ (Interpol & UK NADC Standard)"
            ),
            "registered_prov": prov_str, "seen_count": len(p_df), "seen_days": seen_days,
            "night_ratio_pct": night_ratio, "top_camera": top_cam,
            "day_pattern": day_pattern_text, "time_pattern": time_pattern_text,
            "modus_operandi": (
                f"บทวิเคราะห์แผนประทุษกรรม: ยานพาหนะหมายเลขทะเบียน {plate} ปรากฏบันทึก"
                f"ด้วยความเร็วสูงสุดทางฟิสิกส์กระโดดถึง {max_spd:.0f} กม./ชม. "
                f"เริ่มต้นจากสถานี [{p_df.iloc[0]['จุดติดตั้งกล้อง']}] เมื่อ {p_df.iloc[0]['เวลา']} น. "
                f"ถึงสถานี [{p_df.iloc[-1]['จุดติดตั้งกล้อง']}] เมื่อ {p_df.iloc[-1]['เวลา']} น. "
                f"รวม {total_dist:.1f} กม. ยืนยันรถ 2 คันสวมทะเบียนเดียวกัน"
            ),
            "radar": {
                "border": 30, "night": 20 if p_df['Is_Night'].any() else 5,
                "convoy": 0,
                "foreign": 10 if any(p not in BORDER_PROVINCES for p in provinces) else 5,
                "frequency": min(20, len(p_df) * 2)
            },
            "total_cams": num_cams, "total_dist": total_dist,
            "is_twin": True, "raw_df": p_df
        }
    # ──────────────────────────────
    convoy_events = []
    df_sorted_time = df.sort_values(by=['จุดติดตั้งกล้อง', 'Datetime'])

    for location, group in df_sorted_time.groupby('จุดติดตั้งกล้อง'):
        rows = group.to_dict('records')
        i = 0
        while i < len(rows) - 1:
            cluster = [rows[i]]
            j = i + 1
            while j < len(rows):
                tdiff = (rows[j]['Datetime'] - cluster[-1]['Datetime']).total_seconds() / 60.0
                if tdiff <= convoy_time_limit_min:
                    if rows[j]['ทะเบียนรถ'] not in [c['ทะเบียนรถ'] for c in cluster]:
                        cluster.append(rows[j])
                else:
                    break
                j += 1
            if len(cluster) > 1:
                convoy_events.append({
                    'cam': location, 'datetime': cluster[0]['Datetime'],
                    'date': cluster[0]['วันที่'],
                    'cars': [c['ทะเบียนรถ'] for c in cluster],
                    'times': [c['เวลา'] for c in cluster],
                    'speeds': [c.get('Speed_kmh', 0.0) for c in cluster],
                    'cluster': cluster
                })
                i += 1
            else:
                i += 1

    pair_counts = defaultdict(list)
    for ev in convoy_events:
        cars = ev['cars']
        for i in range(len(cars)):
            for j in range(i + 1, len(cars)):
                pair = tuple(sorted([cars[i], cars[j]]))
                pair_counts[pair].append(ev)

    # เก็บ pairs ที่ถูก REJECT จาก convoy → ส่งต่อ E5_Route
    route_runner_candidates = set()

    for pair, events in pair_counts.items():
        cams_passed  = list(set(e['cam'] for e in events))
        dates_passed = sorted(list(set(e['date'] for e in events)))
        if len(cams_passed) < 4:
            continue

        # ─ ตรวจระยะทางรวมขั้นต่ำ 100 กม. (itrap_agent E2 standard) ─────
        member_cars_check = list(pair)
        p_df_dist_check = pd.concat(
            [plate_groups[p] for p in member_cars_check if p in plate_groups],
            ignore_index=True
        )
        if not p_df_dist_check.empty and (p_df_dist_check['dist_km'].sum() / 2.0) < 100.0:
            continue

        # ── ตัวกรองขบวนลำเลียง (รองรับทั้ง Single-Day และ Multi-Day Convoys) ───────
        # สัญจรร่วมกัน ≥ 2 กล้องในห้วงเวลา 30 นาที = นับเป็นขบวนลำเลียง
        # ≥2 วัน = ยืนยันขบวนซ้ำซาก (High Confidence)
        # 1 วัน  = ขบวนปฏิบัติการวันเดียว/ต้องติดตาม (Moderate Confidence)

        member_cars = list(pair)
        p_df_group  = pd.concat(
            [plate_groups[p] for p in member_cars if p in plate_groups],
            ignore_index=True
        ).sort_values('Datetime')

        # ─ Convoy max size cap: 2–6 คัน (itrap_agent/app.py บรรทัด 1642) ──────
        if len(member_cars) > 6:
            route_runner_candidates.update(member_cars)
            continue

        if p_df_group.empty:
            continue

        # Build arrival-time pivot for TOS
        tpivot = (
            p_df_group.groupby(['ทะเบียนรถ', 'จุดติดตั้งกล้อง'])['Datetime']
            .min().to_dict()
        )

        shared_cam_set = set(cams_passed)
        result = _compute_tos_hri_gap(p_df_group, member_cars, shared_cam_set, tpivot)

        if result is None:
            # REJECT โดย TOS/HRI/Gap — ทั้งคู่เป็น route runner candidates
            route_runner_candidates.update(member_cars)
            continue

        leader, swaps, tos, hri, gap_pen, gap_cnt, avg_gap_sec = result

        # ─ Direction Coherence ────────────────
        # ตรวจสอบทิศทางเฉพาะกล้องในทริปเกิดเหตุ (ไม่ใช้ประวัติ 6 เดือนทั้งปี)
        event_df = p_df_group[p_df_group['จุดติดตั้งกล้อง'].isin(shared_cam_set)]
        if 'Direction' in event_df.columns:
            lead_event_logs = event_df[event_df['ทะเบียนรถ'] == leader]
            event_dirs = [d for d in lead_event_logs['Direction'].tolist() if d != 'ไม่ระบุ']
            # Hard REJECT: ทิศทางรถนำสลับ เข้า/ออก ในทริปเดียวกัน → ไม่ใช่ขบวน (itrap_agent/app.py บรรทัด 1720)
            if len(event_dirs) >= 2 and len(set(event_dirs)) > 1:
                route_runner_candidates.update(member_cars)
                continue

        follower = [c for c in member_cars if c != leader][0]

        # Score — multi-day boost, single-day penalty
        conf_percent = min(95, 65 + (len(cams_passed) * 6))
        has_multi_days = len(dates_passed) >= 2

        # รถที่ถูก flag โดย itrap หลักแล้ว — เจอกันแม้  1 วันก็น่าสงสัย
        # ≥2 วัน = ยืนยัน (Confirmed), 1 วัน = ต้องติดตาม (Single Event)
        if not has_multi_days:
            conf_percent = max(50, conf_percent - 15)  # penalty แต่ไม่ตัดทิ้ง

        # Hard REJECT: TOS สลับตำแหน่ง ≥2 ครั้ง (itrap_agent/app.py บรรทัด 1688)
        if swaps >= 2:
            route_runner_candidates.update(member_cars)
            continue

        # Hard REJECT: gap ≤3 จุด (itrap_agent/app.py บรรทัด 1713)
        if gap_cnt >= 3:
            route_runner_candidates.update(member_cars)
            continue


        base_score = int(conf_percent * tos * hri * gap_pen)

        if base_score < 75:  # ปรับจาก 50 เป็น 75 ตาม itrap_agent standard
            route_runner_candidates.update(member_cars)
            continue

        conf_tag = "🟢 ความเชื่อมั่นสูง" if conf_percent >= 85 else "🟡 ความเชื่อมั่นปานกลาง"
        group_id = f"Group_CV_{leader.split()[0]}"

        total_dist = p_df_group['dist_km'].sum() / 2.0
        provinces  = list(set(p_df_group['จังหวัด'].unique()) - {"", "ไม่ระบุ"})
        prov_str   = ", ".join(provinces) if provinces else "ไม่ระบุ"
        night_cnt  = int(p_df_group['Is_Night'].sum())
        night_ratio = (night_cnt / max(len(p_df_group), 1)) * 100.0

        workday_cnt = int((~p_df_group['Is_Weekend']).sum())
        weekend_cnt = int(p_df_group['Is_Weekend'].sum())
        day_pattern_text = (
            f"เน้นสัญจรวันทำงาน (จันทร์-ศุกร์) จำนวน {workday_cnt} ครั้ง"
            if workday_cnt >= weekend_cnt
            else f"เน้นสัญจรวันหยุด (เสาร์-อาทิตย์) จำนวน {weekend_cnt} ครั้ง"
        )
        deep_night_cnt = int(((p_df['Hour'] >= 0) & (p_df['Hour'] < 5)).sum())
        diurnal_inv_pct = (deep_night_cnt / max(len(p_df), 1)) * 100.0
        time_pattern_text = (
            f"🚨 สัญจรดึกดื่นวิกาลหนาแน่น (Diurnal Inversion {diurnal_inv_pct:.1f}%) [00:00-04:30 น.]"
            if diurnal_inv_pct >= 50.0
            else (f"สัญจรห้วงเวลากลางคืนวิกาลหนาแน่น ({night_ratio:.1f}%)" if night_ratio >= 40 else "สัญจรห้วงเวลากลางวันปกติ")
        )

        top_cam = cams_passed[0] if cams_passed else "ไม่ระบุ"
        gm = int(avg_gap_sec // 60); gs = int(avg_gap_sec % 60)
        gap_text = f"{gm} นาที {gs} วินาที" if gm > 0 else f"{gs} วินาที"

        order_note = (
            "รักษาลำดับตลอด (TOS★)"
            if swaps == 0 else "สลับตำแหน่ง 1 ครั้ง (รถอาจติดไฟแดง)"
        )
        gap_note = (
            f"ขาดกล้อง {gap_cnt} ตัว" if gap_cnt > 0 else "ผ่านทุกกล้องร่วมกัน"
        )

        # ชื่อขบวน: แยกชัดระหว่าง Confirmed vs Single-Event
        convoy_label = (
            f"ขบวนลำเลียงยืนยัน: {leader} ➡️ {follower}"
            if has_multi_days
            else f"ขบวนพบครั้งเดียว (ต้องติดตาม): {leader} ➡️ {follower}"
        )
        verdict_badge = (
            "🛑 สมควรดำเนินการสกัดจับและควบคุมตัวทันที"
            if base_score >= 85 and has_multi_days
            else ("🟧 สมควรตั้งจุดตรวจค้นเชิงยุทธวิธีอย่างละเอียด"
               if has_multi_days
               else "🟨 ต้องติดตามและยืนยันเพิ่มเติม (พบร่วมกันเพียงครั้งเดียว)")
        )
        verdict_text = (
            f"คำวินิจฉัยการปฏิบัติการ: {verdict_badge} — "
            f"แนะนำให้ชุดปฏิบัติการปล่อยยานพาหนะคันนำ ({leader}) ผ่านจุดตรวจก่อน "
            f"เพื่อป้องกันการส่งสัญญาณแจ้งเตือน และเข้าควบคุมคันตาม ({follower}) ณ จุดคอขวดถัดไปทันที"
        )

        convoy_cases[group_id] = {
            "case_id": group_id, "group_name": convoy_label,
            "engine_type": "E2", "engine_name": "🚘 ขบวนลำเลียง (Convoy Network Engine)",
            "threat_category": "กลุ่มขบวนรถยุทธวิธีลำเลียงสิ่งของผิดกฎหมาย",
            "verdict_badge": verdict_badge, "verdict_text": verdict_text,
            "leader": leader, "follower": follower, "members": member_cars,
            "shared_cams": cams_passed, "num_shared_cams": len(cams_passed),
            "dates_passed": dates_passed, "has_multi_days": has_multi_days,
            "avg_gap_text": gap_text,
            "risk_score": (
                90 if (base_score >= 85 and has_multi_days)
                else (75 if has_multi_days else 60)
            ),
            "confidence_level": conf_percent,
            "confidence_text": (
                f"{conf_tag} ({conf_percent}%) — ผ่านร่วม {len(cams_passed)} ด่าน "
                f"| {order_note} | {gap_note} "
                f"[TOS={tos:.2f} HRI={hri:.2f} Gap={gap_pen:.2f}]"
            ),
            "registered_prov": prov_str, "seen_count": len(events),
            "seen_days": len(dates_passed), "night_ratio_pct": night_ratio,
            "top_camera": top_cam, "day_pattern": day_pattern_text,
            "time_pattern": time_pattern_text,
            "modus_operandi": (
                f"บทวิเคราะห์พฤติกรรมขบวนรถ: ก่อตัวที่ [{cams_passed[0]}] "
                f"เมื่อ {events[0]['datetime'].strftime('%H:%M:%S')} น. "
                f"สิ้นสุดที่ [{cams_passed[-1]}] เมื่อ {events[-1]['datetime'].strftime('%H:%M:%S')} น. "
                f"รวม {total_dist:.1f} กม. ระยะห่างเฉลี่ย {gap_text} {order_note}"
            ),
            "events": events,
            "radar": {
                "border": 30, "night": 20 if p_df_group['Is_Night'].any() else 5,
                "convoy": 20,
                "foreign": 10 if any(p not in BORDER_PROVINCES for p in provinces) else 5,
                "frequency": min(20, len(cams_passed) * 4)
            },
            "total_cams": len(cams_passed), "total_dist": total_dist,
            "raw_df": p_df_group
        }

    # ──────────────────────────────────────────────────────────────
    # ⚠️ ENGINE 3: Touch & Go U-Turn (Zone A Logic + Overnight)
    # ──────────────────────────────────────────────────────────────
    has_zone = 'Zone' in df.columns
    has_dir  = 'Direction' in df.columns

    # คำนวณ traffic density per hour เพื่อ evasion detection
    hourly_traffic = df.groupby(df['Datetime'].dt.hour).size()
    traffic_q20    = hourly_traffic.quantile(0.2) if not hourly_traffic.empty else 0

    e3_done = set()

    # ─ Plates already handled by E1 → skip in E3/E4 ──────────────────────────
    cloned_plate_set = set(cloned_cases.keys())

    for plate, p_df in plate_groups.items():
        if plate in cloned_plate_set or p_df.empty:
            continue


        num_cams   = p_df['จุดติดตั้งกล้อง'].nunique()
        total_dist = p_df['dist_km'].sum()
        seen_days  = p_df['วันที่'].nunique()
        provinces  = list(set(p_df['จังหวัด'].unique()) - {"", "ไม่ระบุ"})
        prov_str   = ", ".join(provinces) if provinces else "ไม่ระบุ"
        has_border_prov = any(p in BORDER_PROVINCES for p in provinces)

        # ─ E3 conditions ──────────────────────────────────────────
        # ต้องผ่านทั้งด่านชายแดน (Zone A) และด่านในประเทศ (Zone C)
        if has_zone:
            zones = p_df['Zone'].unique()
            has_zone_a = 'A' in zones
            has_zone_c = 'C' in zones
        else:
            has_zone_a = has_border_prov
            has_zone_c = num_cams >= 2

        if not (has_zone_a and has_zone_c):
            continue
        if num_cams < 5:  # ปรับจาก 3 เป็น 5 ตาม itrap_agent E3 standard
            continue

        total_dist_check = p_df['dist_km'].sum()
        if total_dist_check < 150.0:  # ประกันระยะทางจริง ≥150 กม.
            continue

        # ─ U-turn detection ───────────────────────────────────────
        time_diffs  = p_df['Datetime'].diff().dt.total_seconds().fillna(0) / 3600.0
        is_uturn    = False
        uturn_count = 0
        is_overnight_uturn = False
        overnight_count    = 0
        uturn_event_days   = set()   # นับวันที่มี U-turn จริง (ไม่ใช่แค่จำนวนครั้ง)

        # Short U-turn (1-4 ชม.)
        gap_indices = np.where((time_diffs >= 1.0) & (time_diffs <= 4.0))[0]
        for idx in gap_indices:
            if idx >= len(p_df): continue
            row_date = p_df.iloc[idx]['วันที่']
            if has_zone and has_dir:
                zb = p_df.iloc[idx - 1]['Zone']      if idx > 0 else ''
                za = p_df.iloc[idx]['Zone']
                db = p_df.iloc[idx - 1]['Direction'] if idx > 0 else ''
                da = p_df.iloc[idx]['Direction']
                if zb == 'A' and za == 'A' and db == 'ออก' and da == 'เข้า':
                    is_uturn = True
                    uturn_count += 1
                    uturn_event_days.add(row_date)
            elif has_border_prov:
                # fallback สั้น: บังคับได้เฉพาะกรณีเดียวกัน — ต้องผ่านกล้อง ≥2 จุดในวันเดียว
                # (ฉะนั้นได้ว่าออกชายแดนจริง ไม่ใช่แค่รอมนานอยู่ที่เดียว)
                prev_date = p_df.iloc[idx - 1]['วันที่']
                if row_date == prev_date:
                    day_cam_count = p_df[p_df['วันที่'] == row_date]['จุดติดตั้งกล้อง'].nunique()
                    if day_cam_count >= 2:
                        is_uturn = True
                        uturn_count += 1
                        uturn_event_days.add(row_date)

        # Overnight U-turn (4-12 ชม.) — DEA/Europol FRONTEX
        overnight_indices = np.where((time_diffs >= 4.0) & (time_diffs <= 12.0))[0]
        for idx in overnight_indices:
            if idx >= len(p_df): continue
            row_date = p_df.iloc[idx]['วันที่']
            if has_zone and has_dir:
                zb = p_df.iloc[idx - 1]['Zone']      if idx > 0 else ''
                za = p_df.iloc[idx]['Zone']
                db = p_df.iloc[idx - 1]['Direction'] if idx > 0 else ''
                da = p_df.iloc[idx]['Direction']
                if zb == 'A' and za == 'A' and db == 'ออก' and da == 'เข้า':
                    is_overnight_uturn = True
                    overnight_count += 1
                    is_uturn = True
                    uturn_event_days.add(row_date)
            elif has_border_prov:
                # fallback overnight: ยอมรับข้ามวันได้ แต่ต้องมีกล้องชายแดน ≥2 จุดในช่วงนั้น
                prev_date = p_df.iloc[idx - 1]['วันที่']
                span_cam_count = p_df[p_df['วันที่'].isin([prev_date, row_date])]['จุดติดตั้งกล้อง'].nunique()
                if span_cam_count >= 2:
                    is_overnight_uturn = True
                    overnight_count += 1
                    is_uturn = True
                    uturn_event_days.add(row_date)

        if not is_uturn:
            continue

        # ── ตัวกรองความน่าเชื่อถือ: U-turn ต้องเกิดในข้อมูล ≥2 วัน ─────────────
        # U-turn วันเดียว + ข้อมูลวันเดียว = อาจเป็นเหตุบังเอิญ (เบรกลืมของ ฯลฯ)
        # ยกเว้น: overnight U-turn มีน้ำหนักพิสูจน์สูงกว่า ยอมรับ 1 วันได้
        if not is_overnight_uturn and seen_days < 2:
            continue

        # ─ Build compound triggers (ต้องได้ ≥ 3) ─────────────────
        is_night   = p_df['Is_Night'].any()
        is_foreign = any(p not in BORDER_PROVINCES for p in provinces)

        hours_visited = p_df['Datetime'].dt.hour.unique()
        is_evasion = any(hourly_traffic.get(h, 0) <= traffic_q20 for h in hours_visited)

        avg_speed = p_df[p_df['Speed_kmh'] > 0]['Speed_kmh'].mean()
        is_speed_anomaly = pd.notna(avg_speed) and avg_speed > 110

        base_score = 60
        triggers   = []

        # Trigger 1: U-turn (บังคับ)
        uturn_txt = f"วนรอบ {uturn_count} รอบ" if uturn_count > 1 else "ตีวงกลับโฉบรับ/ส่งชายแดน"
        triggers.append(f"{uturn_txt} (ออก Zone A → แช่ 1-4 ชม. → เข้า Zone A)")
        base_score += 20

        # Trigger 1c: Overnight Border Stay — DEA/FRONTEX
        if is_overnight_uturn:
            ov_txt = f"ค้างคืน {overnight_count} รอบ" if overnight_count > 1 else "ค้างคืนชายแดน"
            triggers.append(
                f"Overnight Border Stay: {ov_txt} (ออก Zone A → ค้าง 4-12 ชม. → เข้า Zone A) "
                f"— รับ/ส่งสินค้าข้ามคืน [DEA/Europol FRONTEX]"
            )
            base_score += 20

        # Trigger 1b: Repeat Offender — DEA/ปปส.
        if seen_days >= 3:
            triggers.append(f"Repeat Offender: ปรากฏซ้ำ {seen_days} วัน — พฤติกรรมเป็นระบบ (ปปส./DEA)")
            base_score += 15
        elif seen_days == 2:
            base_score += 7

        # Trigger 2: กลางดึก + จราจรต่ำ
        if is_evasion and is_night:
            triggers.append("จงใจมุดช่องโหว่ห้วงเวลาวิกาลที่มีการจราจรต่ำ")
            base_score += 15

        # Trigger 3: รถต่างถิ่นในพื้นที่ชายแดน
        if is_foreign and has_border_prov:
            triggers.append(f"ยานพาหนะต่างถิ่น ({prov_str}) ลัดเลาะชายแดน")
            base_score += 15

        # Trigger 4: วนหลายรอบในวันเดียว
        if uturn_count >= 2:
            triggers.append(f"วนซ้ำ {uturn_count} รอบในวันเดียว — แผนลำเลียงหลายเที่ยว")
            base_score += 10

        # Trigger 5: ความเร็วสูงผิดปกติ
        if is_speed_anomaly:
            triggers.append(f"ความเร็วเฉลี่ยสูงผิดปกติ ({avg_speed:.0f} กม./ชม.) — เร่งหนีการตรวจ")
            base_score += 10

        # บังคับ ≥ 3 triggers (itrap_agent standard)
        if len(triggers) < 3:
            continue
        if base_score < 80:  # ปรับจาก 75 เป็น 80 ตาม itrap_agent E3 standard
            continue

        night_ratio   = (int(p_df['Is_Night'].sum()) / max(len(p_df), 1)) * 100.0
        workday_cnt   = int((~p_df['Is_Weekend']).sum())
        weekend_cnt   = int(p_df['Is_Weekend'].sum())
        top_cam       = p_df['จุดติดตั้งกล้อง'].value_counts().index[0] if not p_df.empty else "ไม่ระบุ"
        day_pattern_text = (
            f"เน้นสัญจรวันทำงาน {workday_cnt} ครั้ง"
            if workday_cnt >= weekend_cnt
            else f"เน้นสัญจรวันหยุด {weekend_cnt} ครั้ง"
        )
        time_pattern_text = (
            f"สัญจรกลางคืนวิกาลหนาแน่น ({night_ratio:.1f}%)"
            if night_ratio >= 40 else "สัญจรกลางวันปกติ"
        )

        conf_val = min(90, 65 + (seen_days * 8))
        conf_tag = "🟢 ความเชื่อมั่นสูง" if conf_val >= 85 else "🟡 ความเชื่อมั่นปานกลาง"

        suspect_cases[plate] = {
            "case_id": f"E3_{plate}", "plate": plate,
            "engine_type": "E3",
            "engine_name": "🔄 E3: พฤติกรรมมุดช่องโหว่ชายแดน (Touch & Go U-Turn)",
            "threat_category": "กลุ่มรถวนเวียนชายแดนแช่เวลา/รับส่งสินค้า",
            "verdict_badge": "🟧 สมควรตั้งจุดตรวจค้นเชิงยุทธวิธีอย่างละเอียด",
            "verdict_text": (
                "คำวินิจฉัยการปฏิบัติการ: สมควรจัดกำลังตั้งจุดตรวจค้นเชิงยุทธวิธีล่วงหน้า ณ ด่านเป้าหมาย "
                "เนื่องจากพบพฤติกรรมตีวงโฉบชายแดนแช่เวลา [มาตรฐาน DEA/Europol FRONTEX]"
            ),
            "risk_score": min(95, base_score),
            "confidence_level": conf_val,
            "confidence_text": f"{conf_tag} ({conf_val}%) — {' + '.join(triggers)}",
            "registered_prov": prov_str, "seen_count": len(p_df), "seen_days": seen_days,
            "night_ratio_pct": night_ratio, "top_camera": top_cam,
            "day_pattern": day_pattern_text, "time_pattern": time_pattern_text,
            "modus_operandi": (
                f"บทวิเคราะห์แผนประทุษกรรม: ตรวจพบพฤติกรรมออกแช่เวลาพื้นที่ชายแดน ({prov_str}) "
                f"รวม {uturn_count} รอบ ผ่าน {num_cams} จุดตรวจ {seen_days} วัน"
            ),
            "radar": {
                "border": 30 if has_zone_a else 15,
                "night": 30 if is_night else 0,
                "convoy": 0,
                "foreign": 20 if is_foreign else 5,
                "frequency": min(20, uturn_count * 5 + seen_days * 3)
            },
            "total_cams": num_cams, "total_dist": total_dist,
            "is_twin": False, "raw_df": p_df
        }
        e3_done.add(plate)

    # ──────────────────────────────────────────────────────────────
    # 🌙 ENGINE 4: Night Ghost — บังคับ ≥2 คืน, Deep Night bonus
    # ──────────────────────────────────────────────────────────────
    for plate, p_df in plate_groups.items():
        if plate in cloned_plate_set or p_df.empty:  # E4 ไม่ซ้ำ E1 (itrap_agent/app.py บรรทัด 1970)
            continue
        # E4 ไม่ซ้ำ E3 (Europol standard)
        if plate in e3_done:
            continue

        night_cnt   = int(p_df['Is_Night'].sum())
        night_ratio = night_cnt / max(len(p_df), 1)
        if night_ratio < 0.6:
            continue

        # ─ ต้องมี ≥2 คืนที่ผ่านกลางดึก (DEA standard) ───────────
        night_days = p_df[p_df['Is_Night']]['วันที่'].nunique()
        if night_days < 2:
            continue

        provinces  = list(set(p_df['จังหวัด'].unique()) - {"", "ไม่ระบุ"})
        prov_str   = ", ".join(provinces) if provinces else "ไม่ระบุ"
        has_border_prov = any(p in BORDER_PROVINCES for p in provinces)
        num_cams   = p_df['จุดติดตั้งกล้อง'].nunique()

        if not has_border_prov and num_cams < 4:
            continue

        # Zone A border cams
        if has_zone and 'Zone' in p_df.columns:
            border_cams = p_df[p_df['Zone'] == 'A']['จุดติดตั้งกล้อง'].nunique()
        else:
            border_cams = num_cams if has_border_prov else 0

        if border_cams < 2:
            continue

        base_score = 70
        reasons    = []

        reasons.append(f"พบการเดินทางผ่านชายแดนกลางดึก {night_cnt} ครั้ง ผ่าน {border_cams} จุดตรวจ")

        if night_ratio >= 0.9:
            base_score += 15
            reasons.append("ผ่านชายแดนเฉพาะกลางดึก (≥90%) — แผนหลบเลี่ยงชัดเจน")
        elif night_ratio >= 0.7:
            base_score += 8
            reasons.append("ผ่านชายแดนกลางดึกสูงผิดปกติ (≥70%)")

        if border_cams >= 3:
            base_score += 10
            reasons.append(f"ครอบคลุมจุดตรวจชายแดน {border_cams} จุด")

        if night_days >= 3:
            base_score += 10
            reasons.append(f"Repeat Night Offender: {night_days} คืน (ปปส./DEA standard)")

        # Deep Night bonus (00-04) — Europol FRONTEX
        deep_night = len(p_df[p_df['Hour'].isin([0, 1, 2, 3, 4]) & p_df['Is_Night']])
        if deep_night >= 2:
            base_score += 10
            reasons.append(f"ผ่านชายแดนช่วงดึกสุด 00:00-04:00 จำนวน {deep_night} ครั้ง [Europol FRONTEX]")

        if base_score < 80:
            continue

        seen_days   = p_df['วันที่'].nunique()
        night_ratio_pct = night_ratio * 100.0
        workday_cnt = int((~p_df['Is_Weekend']).sum())
        weekend_cnt = int(p_df['Is_Weekend'].sum())
        top_cam     = p_df['จุดติดตั้งกล้อง'].value_counts().index[0] if not p_df.empty else "ไม่ระบุ"
        total_dist  = p_df['dist_km'].sum()

        conf_val = min(90, 60 + (seen_days * 8))
        conf_tag = "🟢 ความเชื่อมั่นสูง" if conf_val >= 85 else "🟡 ความเชื่อมั่นปานกลาง"

        suspect_cases[plate] = {
            "case_id": f"E4_{plate}", "plate": plate,
            "engine_type": "E4",
            "engine_name": "🌙 E4: Night Ghost (รถชายแดนกลางดึกซ้ำซาก)",
            "threat_category": "กลุ่มรถขนส่งสิ่งของยามวิกาล",
            "verdict_badge": "🟧 สมควรตั้งจุดตรวจค้นเชิงยุทธวิธีอย่างละเอียด",
            "verdict_text": (
                "คำวินิจฉัยการปฏิบัติการ: สมควรจัดกำลังตั้งจุดตรวจสกัดกั้นห่วงเวลากลางคืนวิกาล "
                "เนื่องจากพบสัดส่วนสัญจรผ่านชายแดนกลางดึก ≥60% และซ้ำ ≥2 คืน (DEA/Europol FRONTEX)"
            ),
            "risk_score": min(90, base_score),
            "confidence_level": conf_val,
            "confidence_text": f"{conf_tag} ({conf_val}%) — {' | '.join(reasons)}",
            "registered_prov": prov_str, "seen_count": len(p_df), "seen_days": seen_days,
            "night_ratio_pct": night_ratio_pct, "top_camera": top_cam,
            "day_pattern": (
                f"เน้นสัญจรวันทำงาน {workday_cnt} ครั้ง"
                if workday_cnt >= weekend_cnt
                else f"เน้นสัญจรวันหยุด {weekend_cnt} ครั้ง"
            ),
            "time_pattern": f"สัญจรกลางคืนวิกาลหนาแน่น ({night_ratio_pct:.1f}%)",
            "modus_operandi": (
                f"บทวิเคราะห์แผนประทุษกรรม: เคลื่อนไหวหนาแน่นเฉพาะช่วง 22:00-04:00 น. "
                f"ซ้ำ {night_days} คืน ผ่าน {border_cams} จุดชายแดน — หลบเลี่ยงด่านกลางวัน"
            ),
            "radar": {
                "border": 35, "night": 40,
                "convoy": 0, "foreign": 0, "frequency": min(20, night_cnt * 3)
            },
            "total_cams": num_cams, "total_dist": total_dist,
            "is_twin": False, "raw_df": p_df
        }

    # ──────────────────────────────────────────────────────────────
    # 🔍 ENGINE 5: รถต้องสงสัย + Route Runner (ถูก REJECT จาก E2)
    # ──────────────────────────────────────────────────────────────
    e3e4_done = e3_done | set(k for k in suspect_cases if suspect_cases[k]['engine_type'] == 'E4')

    for plate, p_df in plate_groups.items():
        if plate in cloned_plate_set or plate in e3e4_done or plate in suspect_cases:
            continue
        if p_df.empty:
            continue

        num_cams    = p_df['จุดติดตั้งกล้อง'].nunique()
        total_dist  = p_df['dist_km'].sum()
        seen_days   = p_df['วันที่'].nunique()
        night_cnt   = int(p_df['Is_Night'].sum())
        night_ratio = (night_cnt / max(len(p_df), 1)) * 100.0
        provinces   = list(set(p_df['จังหวัด'].unique()) - {"", "ไม่ระบุ"})
        prov_str    = ", ".join(provinces) if provinces else "ไม่ระบุ"
        has_border_prov = any(p in BORDER_PROVINCES for p in provinces)

        hotspots = p_df['จุดติดตั้งกล้อง'].value_counts()
        is_scout = not hotspots.empty and hotspots.iloc[0] >= 3
        top_cam  = hotspots.index[0] if not hotspots.empty else "ไม่ระบุ"

        workday_cnt = int((~p_df['Is_Weekend']).sum())
        weekend_cnt = int(p_df['Is_Weekend'].sum())

        # ── Route Runner: REJECT จาก convoy แต่วิ่งไกลจริง ──────
        is_route_runner = (
            plate in route_runner_candidates and
            num_cams >= 4 and
            total_dist >= 80.0 and
            len(provinces) >= 2
        )

        # ── General Suspect ───────────────────────────────────────
        # ต้องมีข้อมูล ≥2 วันถึงจะขึ้น E5 General
        # ป้องกันรถโดยสารบังเอิญ/ท่องเที่ยววันเดียวที่ผ่านด่านหลายจุดในวันนั้น
        is_e5_gen = (
            seen_days >= 2 and
            (is_scout or len(provinces) > 1 or num_cams >= 5 or seen_days >= 3)
        )

        # Route Runner: ข้อมูลต้องมี ≥2 วัน ด้วย (convoy วันเดียวที่ถูก reject)
        if is_route_runner and seen_days < 2:
            is_route_runner = False

        if not (is_route_runner or is_e5_gen):
            continue

        if is_route_runner:
            eng_type   = "E5_Route"
            eng_name   = "🛣️ E5: Route Runner (รถวิ่งสายไกลลักษณะขบวน)"
            threat_cat = "กลุ่มรถวิ่งสายทางยาวที่อาจเป็นรถนำทาง/สอดแนม"
            score      = 70
            conf_val   = 80
            mo_text    = (
                f"บทวิเคราะห์แผนประทุษกรรม: รถนี้ผ่าน convoy detection แต่ไม่ผ่านการยืนยัน TOS/HRI "
                f"(อาจมีรถคู่อื่นที่ยังไม่อยู่ในข้อมูล หรือทำหน้าที่รถนำทาง/สอดแนม) "
                f"ผ่าน {num_cams} จุดตรวจ รวม {total_dist:.1f} กม. ข้าม {len(provinces)} จังหวัด"
            )
            verdict_badge = "🟧 สมควรตั้งจุดตรวจค้นเชิงยุทธวิธีอย่างละเอียด"
        else:
            eng_type   = "E5"
            eng_name   = "🔍 E5: รถต้องสงสัยทั่วไป (General Suspect Engine)"
            threat_cat = "กลุ่มรถต้องสงสัยเฝ้าระวังทั่วไป"
            score      = 65 if is_scout else 55
            conf_val   = 85 if (seen_days >= 3 and len(p_df) >= 5) else 65
            mo_text    = (
                f"บทวิเคราะห์แผนประทุษกรรม: พบสัญจรผ่านจุดตรวจต่อเนื่อง {num_cams} จุด "
                f"รวม {seen_days} วัน"
            )
            verdict_badge = "🟨 สมควรจัดกำลังเฝ้าระวังติดตามพฤติกรรม"

        conf_tag = "🟢 ความเชื่อมั่นสูง" if conf_val >= 85 else "🟡 ความเชื่อมั่นปานกลาง"

        suspect_cases[plate] = {
            "case_id": f"{eng_type}_{plate}", "plate": plate,
            "engine_type": eng_type, "engine_name": eng_name,
            "threat_category": threat_cat,
            "verdict_badge": verdict_badge,
            "verdict_text": (
                "คำวินิจฉัยการปฏิบัติการ: สมควรจัดกำลังเฝ้าระวังและติดตามพฤติการณ์ในสายทาง"
                if not is_route_runner else
                "คำวินิจฉัยการปฏิบัติการ: สมควรตั้งจุดตรวจค้นเชิงยุทธวิธี เนื่องจากอาจเป็นรถนำทางหรือสอดแนมให้ขบวนลำเลียง"
            ),
            "risk_score": score,
            "confidence_level": conf_val,
            "confidence_text": f"{conf_tag} ({conf_val}%) — {eng_name}",
            "registered_prov": prov_str, "seen_count": len(p_df), "seen_days": seen_days,
            "night_ratio_pct": night_ratio, "top_camera": top_cam,
            "day_pattern": (
                f"เน้นสัญจรวันทำงาน {workday_cnt} ครั้ง"
                if workday_cnt >= weekend_cnt
                else f"เน้นสัญจรวันหยุด {weekend_cnt} ครั้ง"
            ),
            "time_pattern": (
                f"สัญจรกลางคืนวิกาลหนาแน่น ({night_ratio:.1f}%)"
                if night_ratio >= 40 else "สัญจรกลางวันปกติ"
            ),
            "modus_operandi": mo_text,
            "radar": {
                "border": 30 if has_border_prov else 10,
                "night": 20 if night_ratio >= 40 else 5,
                "convoy": 10 if is_route_runner else 0,
                "foreign": 10 if any(p not in BORDER_PROVINCES for p in provinces) else 5,
                "frequency": min(20, len(p_df) * 2)
            },
            "total_cams": num_cams, "total_dist": total_dist,
            "is_twin": False, "raw_df": p_df
        }

    # ──────────────────────────────────────────────────────────────
    # ❤️ APEX THREAT: โดน ≥2 Engine → ยกระดับเป็น "กลุ่มเป้าหมายความมั่นคงระดับสูงสุด"
    # ตรงกับ itrap_agent/app.py บรรทัด 2046-2053
    # ──────────────────────────────────────────────────────────────
    all_result_plates = (
        set(cloned_cases.keys()) |
        set(p for v in convoy_cases.values() for p in v.get('members', []))
        | set(suspect_cases.keys())
    )
    for plate in list(all_result_plates):
        engines_hit = []
        if plate in cloned_cases:
            engines_hit.append('E1')
        if any(plate in v.get('members', []) for v in convoy_cases.values()):
            engines_hit.append('E2')
        if plate in suspect_cases:
            engines_hit.append(suspect_cases[plate]['engine_type'])

        if len(engines_hit) >= 2:
            # ยกระดับ threat_category ของทุก case ที่ปลายทางนี้
            apex_label = f"❤️‍🔥 APEX THREAT | โดน {' + '.join(engines_hit)} | กลุ่มเป้าหมายความมั่นคงระดับสูงสุด"
            apex_boost = int(min(100, (max(
                cloned_cases.get(plate, {}).get('risk_score', 0),
                suspect_cases.get(plate, {}).get('risk_score', 0)
            )) * 0.15))
            if plate in cloned_cases:
                cloned_cases[plate]['threat_category'] = apex_label
                cloned_cases[plate]['apex'] = True
                cloned_cases[plate]['apex_engines'] = engines_hit
                cloned_cases[plate]['apex_boost'] = f"+{apex_boost}"
            if plate in suspect_cases:
                suspect_cases[plate]['threat_category'] = apex_label
                suspect_cases[plate]['apex'] = True
                suspect_cases[plate]['apex_engines'] = engines_hit
                suspect_cases[plate]['apex_boost'] = f"+{apex_boost}"
            # convoy cases
            for gid, cv in convoy_cases.items():
                if plate in cv.get('members', []):
                    convoy_cases[gid]['threat_category'] = apex_label
                    convoy_cases[gid]['apex'] = True
                    convoy_cases[gid]['apex_engines'] = engines_hit
                    convoy_cases[gid]['apex_boost'] = f"+{apex_boost}"

    return cloned_cases, convoy_cases, suspect_cases
