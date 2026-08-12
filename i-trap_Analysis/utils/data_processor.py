import re
import pandas as pd
import numpy as np

# ────────────────────────────────────────────────────────────────
# Haversine vectorized — แทน geodesic() แบบ loop
# ────────────────────────────────────────────────────────────────
_R_EARTH_KM = 6371.0

def haversine_km(lat1, lon1, lat2, lon2):
    """
    คำนวณระยะทาง Haversine แบบ vectorized รองรับทั้ง scalar และ numpy array
    เร็วกว่า geodesic() แบบ loop ~100-500 เท่า
    """
    lat1, lon1, lat2, lon2 = (
        np.radians(np.asarray(lat1, dtype=float)),
        np.radians(np.asarray(lon1, dtype=float)),
        np.radians(np.asarray(lat2, dtype=float)),
        np.radians(np.asarray(lon2, dtype=float)),
    )
    dlat = lat2 - lat1
    dlon = lon2 - lon1
    a = np.sin(dlat / 2.0) ** 2 + np.cos(lat1) * np.cos(lat2) * np.sin(dlon / 2.0) ** 2
    return _R_EARTH_KM * 2.0 * np.arcsin(np.sqrt(np.clip(a, 0, 1)))


BORDER_PROVINCES = {
    'เชียงราย', 'เชียงใหม่', 'แม่ฮ่องสอน', 'น่าน', 'พะเยา', 'ตาก', 'กาญจนบุรี', 'ราชบุรี',
    'เพชรบุรี', 'ประจวบคีรีขันธ์', 'ชุมพร', 'ระนอง', 'พังงา', 'สตูล', 'สงขลา', 'ยะลา', 'นราธิวาส',
    'ปัตตานี', 'ตราด', 'จันทบุรี', 'สระแก้ว', 'บุรีรัมย์', 'สุรินทร์', 'ศรีสะเกษ', 'อุบลราชธานี',
    'อำนาจเจริญ', 'มุกดาหาร', 'นครพนม', 'บึงกาฬ', 'หนองคาย', 'เลย'
}

# ── พิกัดด่านชายแดนหลัก (เหมือนกับ itrap_agent/app.py บรรทัด 1309-1345) ──────
_BORDER_ANCHORS = np.array([
    # พม่า
    (20.42, 99.88),   # แม่สาย เชียงราย
    (20.27, 100.08),  # เชียงแสน เชียงราย
    (19.30, 97.97),   # แม่ฮ่องสอน
    (18.52, 97.59),   # ปาย แม่ฮ่องสอน
    (16.72, 98.57),   # แม่สอด ตาก ★
    (16.98, 98.51),   # แม่ระมาด ตาก
    (17.57, 98.14),   # ท่าสองยาง ตาก
    (15.32, 98.40),   # เจดีย์สามองค์ กาญจนบุรี ★
    (15.22, 98.33),   # พุน้ำร้อน กาญจนบุรี
    (11.80, 99.43),   # สิงขร ประจวบคีรีขันธ์
    ( 9.97, 98.60),   # ระนอง ★
    # ลาว
    (20.26, 100.40),  # เชียงของ เชียงราย ★
    (17.87, 101.43),  # ท่าลี่ เลย
    (17.88, 102.75),  # หนองคาย ★
    (18.36, 103.65),  # บึงกาฬ ★
    (17.40, 104.78),  # นครพนม ★
    (16.54, 104.73),  # มุกดาหาร ★
    (15.20, 105.54),  # ช่องเม็ก อุบลราชธานี ★
    (17.00, 102.10),  # ท่าบก
    # กัมพูชา
    (14.38, 103.72),  # ช่องจอม สุรินทร์ ★
    (14.02, 104.13),  # ช่องสะงำ ศรีสะเกษ
    (14.61, 102.98),  # บุรีรัมย์
    (13.69, 102.52),  # อรัญประเทศ สระแก้ว ★
    (13.32, 102.53),  # บ้านคลองลึก สระแก้ว
    (12.53, 102.57),  # บ้านปากาด จันทบุรี ★
    (11.66, 102.91),  # หาดเล็ก ตราด ★
    # มาเลเซีย
    ( 6.64, 100.43),  # สะเดา สงขลา ★
    ( 6.69, 100.27),  # วังประจัน สตูล
    ( 5.78, 101.08),  # เบตง ยะลา ★
    ( 6.03, 101.97),  # สุไหงโกลก นราธิวาส ★
    ( 6.26, 102.07),  # ตากใบ นราธิวาส
], dtype=float)

_BA_LATS_R = np.radians(_BORDER_ANCHORS[:, 0])
_BA_LONS_R = np.radians(_BORDER_ANCHORS[:, 1])


def assign_zone_vectorized(lats: np.ndarray, lons: np.ndarray, radius_km: float = 50.0) -> np.ndarray:
    """
    กำหนด Zone A/C ให้แต่ละแถว โดยใช้ haversine broadcasting
    Zone A = ภายใน radius_km จากด่านชายแดนหลักใดก็ตาม
    Zone C = ด่านภายในประเทศ (ไม่ติดชายแดน)
    ตรงกับ logic ของ itrap_agent/app.py บรรทัด 1350-1360
    """
    lats_r = np.radians(lats)[:, np.newaxis]   # (n, 1)
    lons_r = np.radians(lons)[:, np.newaxis]   # (n, 1)
    dlat = _BA_LATS_R - lats_r                 # (n, m)
    dlon = _BA_LONS_R - lons_r                 # (n, m)
    a = (np.sin(dlat / 2.0) ** 2 +
         np.cos(lats_r) * np.cos(_BA_LATS_R) * np.sin(dlon / 2.0) ** 2)
    dists = _R_EARTH_KM * 2.0 * np.arcsin(np.sqrt(np.clip(a, 0, 1)))  # (n, m)
    is_border = (dists <= radius_km).any(axis=1)  # (n,)
    return np.where(is_border, 'A', 'C')


def normalize_plate(plate_str, province_str=""):
    """ปรับมาตรฐานป้ายทะเบียนตาม DLT"""
    plate = str(plate_str).strip()
    prov = str(province_str).strip() if province_str and str(province_str).lower() != 'nan' else ""
    if prov and prov != 'ไม่ระบุ' and prov not in plate:
        plate = f"{plate} {prov}".strip()
    return plate


def fix_year(date_str):
    """แปลง พ.ศ. เป็น ค.ศ."""
    try:
        s = str(date_str).strip().replace('/', '-')
        parts = s.split('-')
        if len(parts) == 3:
            year = int(parts[0])
            if year > 2500:
                parts[0] = str(year - 543)
                return '-'.join(parts)
    except Exception:
        pass
    return str(date_str)


# ────────────────────────────────────────────────────────────────
# OCR Confusion Matrix — ตรงกับ _OCR_CONFUSION ใน itrap_agent/app.py
# ใช้คัดกรอง False Positive จากกล้องอ่านป้ายผิด
# ────────────────────────────────────────────────────────────────
_OCR_CONFUSION_PAIRS = [
    ('ย', 'บ'), ('ย', 'ข'), ('ย', 'ษ'), ('บ', 'ข'), ('บ', 'ษ'),
    ('ค', 'ด'), ('ค', 'ต'), ('ด', 'ต'),
    ('ว', 'น'), ('ล', 'า'),
]

# ตัวคูณปรับระยะทาง Haversine เป็นระยะทางถนนจริง (เหมือนกับ itrap_agent/app.py บรรทัด 1362)
_ROAD_FACTOR = 1.35


def _ocr_error_score(plate: str, all_plates_today: set) -> int:
    """
    คำนวณคะแนนความเป็นไปได้ที่ป้ายทะเบียนนี้เป็น OCR อ่านผิด (ตรงกับ itrap_agent/app.py)
    ถ้าคะแนน >= 60 → ถือว่าเป็น OCR Error ไม่ใช่รถสวมทะเบียนจริง
    """
    score = 0
    prefix = plate.split()[0] if plate else ''

    # +40: ป้ายปรากฏที่กล้องเดียวเท่านั้น (ข้อมูลน้อยเกินไป)
    # (จะเช็คใน caller เพราะต้องมี p_df)

    # +30: มีป้ายอื่นที่ต่างกันเพียงตัวอักษร OCR-confusion ในชุดข้อมูลวันเดียวกัน
    for c1, c2 in _OCR_CONFUSION_PAIRS:
        if c1 in prefix:
            alt = prefix.replace(c1, c2, 1)
            if any(alt in p for p in all_plates_today if p != plate):
                score += 30
                break
        if c2 in prefix:
            alt = prefix.replace(c2, c1, 1)
            if any(alt in p for p in all_plates_today if p != plate):
                score += 30
                break
    return score


def preprocess_vehicle_data(df_raw):
    """
    Data Cleansing & 3D Reality Guard (Vectorized):
    1. Standardize column names & Plate Normalization
    2. Year fix (BE → AD)
    3. Anti-Bounce Guard (ลบจุดซ้ำ ≤1km ใน 2 นาที)
    4. Physical Speed Guard (>250 km/h UK NADC) & Twin Paradox tagging (3 conditions)
    5. Day-of-week & Time-of-day feature extraction
    6. Zone A/C assignment (itrap_agent logic) — คำนวณจากพิกัดกล้อง
    7. Direction เข้า/ออก — ดึงจากชื่อจุดติดตั้งกล้อง (itrap_agent logic)
    8. OCR Error Filter — ตัดป้ายที่น่าจะอ่านผิดออกจาก is_twin
    """
    df = df_raw.copy()

    rename_dict = {
        'ทะเบียน': 'ทะเบียนรถ', 'ป้ายทะเบียน': 'ทะเบียนรถ', 'เลขทะเบียน': 'ทะเบียนรถ',
        'Province': 'จังหวัด', 'จังหวัดที่จดทะเบียน': 'จังหวัด', 'หมวดจังหวัด': 'จังหวัด',
        'กล้อง': 'จุดติดตั้งกล้อง', 'พิกัด': 'จุดติดตั้งกล้อง', 'สถานที่': 'จุดติดตั้งกล้อง',
        'latitude': 'ละติจูด', 'lat': 'ละติจูด', 'longitude': 'ลองจิจูด', 'lng': 'ลองจิจูด',
        'speed': 'Speed_kmh', 'ความเร็ว': 'Speed_kmh'
    }
    df = df.rename(columns=rename_dict)

    required_cols = ['ทะเบียนรถ', 'จุดติดตั้งกล้อง', 'วันที่', 'เวลา']
    for col in required_cols:
        if col not in df.columns:
            df[col] = "ไม่ระบุ"

    if 'ละติจูด' not in df.columns or 'ลองจิจูด' not in df.columns:
        df['ละติจูด'] = 0.0
        df['ลองจิจูด'] = 0.0
    if 'จังหวัด' not in df.columns:
        df['จังหวัด'] = ""

    df['จังหวัด']     = df['จังหวัด'].astype(str).str.strip().replace('nan', '')
    df['ทะเบียนรถ']   = df.apply(lambda r: normalize_plate(r['ทะเบียนรถ'], r['จังหวัด']), axis=1)
    df['ละติจูด']     = pd.to_numeric(df['ละติจูด'], errors='coerce').fillna(0.0)
    df['ลองจิจูด']    = pd.to_numeric(df['ลองจิจูด'], errors='coerce').fillna(0.0)

    df = df[(df['ละติจูด'] != 0.0) & (df['ลองจิจูด'] != 0.0)].copy()
    if df.empty:
        return df

    df['วันที่'] = df['วันที่'].astype(str).str.strip().apply(fix_year)
    df['เวลา']  = df['เวลา'].astype(str).str.strip()
    df['Datetime'] = pd.to_datetime(df['วันที่'] + ' ' + df['เวลา'], errors='coerce')
    df = df.dropna(subset=['Datetime']).copy()
    df = df.sort_values(by=['ทะเบียนรถ', 'Datetime']).reset_index(drop=True)

    # ─── Vectorized calculations ───────────────────────────────────────────────
    same_plate  = df['ทะเบียนรถ'] == df['ทะเบียนรถ'].shift(1)
    prev_lat    = df['ละติจูด'].shift(1)
    prev_lon    = df['ลองจิจูด'].shift(1)
    prev_dt     = df['Datetime'].shift(1)

    dist_km_raw = haversine_km(
        df['ละติจูด'].values, df['ลองจิจูด'].values,
        prev_lat.values, prev_lon.values
    )
    dist_km_raw = np.where(same_plate, dist_km_raw, 0.0)

    time_diff_hrs_raw = (df['Datetime'] - prev_dt).dt.total_seconds().fillna(0.0) / 3600.0
    time_diff_hrs_raw = np.where(same_plate, time_diff_hrs_raw, 0.0)

    # Anti-Bounce Guard: ลบจุดซ้ำ ≤1km & ≤2 นาที
    is_bounce = same_plate & (dist_km_raw <= 1.0) & (time_diff_hrs_raw <= (2.0 / 60.0))
    df = df[~is_bounce].copy().reset_index(drop=True)

    # คำนวณใหม่หลัง drop bounce
    same_plate    = df['ทะเบียนรถ'] == df['ทะเบียนรถ'].shift(1)
    prev_lat      = df['ละติจูด'].shift(1)
    prev_lon      = df['ลองจิจูด'].shift(1)
    prev_dt       = df['Datetime'].shift(1)
    prev_cam      = df['จุดติดตั้งกล้อง'].shift(1)

    # ── dist_km = Haversine × 1.35 (Road Correction Factor — itrap_agent/app.py บรรทัด 1362) ──
    dist_km_haversine = haversine_km(
        df['ละติจูด'].values, df['ลองจิจูด'].values,
        prev_lat.values, prev_lon.values
    )
    dist_km = np.where(same_plate, dist_km_haversine * _ROAD_FACTOR, 0.0)

    time_diff_hrs = (df['Datetime'] - prev_dt).dt.total_seconds().fillna(0.0) / 3600.0
    time_diff_hrs = np.where(same_plate, time_diff_hrs, 0.0)

    safe_hrs  = np.where((time_diff_hrs > 0) & (time_diff_hrs <= 4.0), time_diff_hrs, np.nan)
    speed_kmh = np.where(~np.isnan(safe_hrs), dist_km / safe_hrs, 0.0)
    speed_kmh = np.where(same_plate, speed_kmh, 0.0)

    direction_raw = np.where(
        same_plate, "มาจาก " + prev_cam.astype(str), "จุดเริ่มต้น/ไม่ระบุ"
    )

    # ── Twin Paradox Tagging (3 conditions — ตรงกับ itrap_agent/app.py บรรทัด 1471-1473) ──────
    # Condition A: Speed Paradox (UK NADC) — เร็วเกินขีดจำกัดทางกายภาพ
    cond_a = (speed_kmh > 250.0) & (dist_km >= 60.0)
    # Condition B: Simultaneous Paradox — ปรากฏตัว 2 กล้องห่างกัน < 1 นาที
    cond_b = (time_diff_hrs < (1.0 / 60.0)) & (dist_km >= 100.0)
    # Condition C: Same-Region Paradox (Interpol) — ข้ามภูมิภาค ≥200 กม. ใน ≤1 ชม.
    cond_c = (time_diff_hrs <= 1.0) & (dist_km >= 200.0)

    is_twin_raw = same_plate & (cond_a | cond_b | cond_c)

    # ── OCR Error Filter — ตัด False Positive จากกล้องอ่านป้ายผิด ───────────────
    # ถ้าป้ายนี้น่าจะเป็น OCR อ่านผิด (คะแนน >= 60) ให้ยกเลิก is_twin
    all_plates_set = set(df['ทะเบียนรถ'].unique())
    ocr_filtered_twin = is_twin_raw.copy()
    twin_plates_candidate = df.loc[is_twin_raw, 'ทะเบียนรถ'].unique()
    for p in twin_plates_candidate:
        p_mask = df['ทะเบียนรถ'] == p
        p_rows = df[p_mask]
        ocr_score = 0
        # +40 ถ้าป้ายปรากฏที่กล้องเดียวเท่านั้น
        if p_rows['จุดติดตั้งกล้อง'].nunique() <= 1:
            ocr_score += 40
        # +30 จาก OCR confusion matrix
        ocr_score += _ocr_error_score(p, all_plates_set)
        if ocr_score >= 60:
            # ยกเลิก is_twin สำหรับป้ายนี้ทั้งหมด
            ocr_filtered_twin = ocr_filtered_twin & ~p_mask

    df['_is_twin_raw'] = ocr_filtered_twin
    df['is_twin'] = df.groupby('ทะเบียนรถ')['_is_twin_raw'].transform('any')
    df = df.drop(columns=['_is_twin_raw'])

    df['Speed_kmh']     = speed_kmh
    df['Time_diff_hrs'] = time_diff_hrs
    df['dist_km']       = dist_km
    df['ทิศทาง']         = direction_raw

    # Feature extraction
    df['DayOfWeek'] = df['Datetime'].dt.dayofweek
    df['Is_Weekend'] = df['DayOfWeek'].isin([5, 6])
    df['Is_Night']   = df['Datetime'].dt.hour.isin([22, 23, 0, 1, 2, 3, 4])
    df['Hour']       = df['Datetime'].dt.hour

    # ─── Zone A/C (itrap_agent logic) ──────────────────────────────────────────
    # Zone A = ≤50 กม. จากด่านชายแดนหลัก, Zone C = ในประเทศ
    df['Zone'] = assign_zone_vectorized(
        df['ละติจูด'].values, df['ลองจิจูด'].values, radius_km=50.0
    )

    # ─── Direction เข้า/ออก (itrap_agent logic) ────────────────────────────────
    # ดึงจากชื่อจุดติดตั้งกล้อง — ตรงกับบรรทัด 1397-1401 ของ itrap_agent/app.py
    cam_str = df['จุดติดตั้งกล้อง'].astype(str)
    df['Direction'] = np.where(
        cam_str.str.contains('เข้า', na=False), 'เข้า',
        np.where(cam_str.str.contains('ออก|out', na=False, regex=True), 'ออก', 'ไม่ระบุ')
    )

    return df
