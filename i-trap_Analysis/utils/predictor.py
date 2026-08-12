import re
import pandas as pd
import numpy as np
from datetime import datetime
from utils.data_processor import haversine_km
from utils.osrm_eta import get_hybrid_eta


def predict_next_checkpoints(df_plate, target_node_selection):
    """
    🔮 4-Layer Predictive Engine:
    Layer 1: Time-Contextual Filter (Day 05:00-18:59 vs Night 19:00-04:59)
    Layer 2: N-Gram Sequence Matching (Origin Camera Context)
    Layer 3: Immediate Intercept Node (ด่าน 1 เผชิญเหตุแรกสุด)
    Layer 4: Strategic Choke Point Node (ด่าน 2 คอขวดเชิงยุทธศาสตร์)

    Optimization: ใช้ haversine_km แทน geodesic() ทุกจุด
    """
    if df_plate.empty or target_node_selection not in df_plate['จุดติดตั้งกล้อง'].values:
        return None

    tdf = df_plate.sort_values('Datetime').reset_index(drop=True)
    target_rows = tdf[tdf['จุดติดตั้งกล้อง'] == target_node_selection]
    if target_rows.empty:
        return None

    last_time = target_rows.iloc[-1]['Datetime']
    is_night  = (last_time.hour >= 19) or (last_time.hour < 5)
    time_context = "กลางคืน (19:00 - 04:59 น.)" if is_night else "กลางวัน (05:00 - 18:59 น.)"

    node_indices   = target_rows.index.tolist()
    prev_node_name = None
    last_idx = node_indices[-1]
    if last_idx > 0:
        prev_node_name = tdf.iloc[last_idx - 1]['จุดติดตั้งกล้อง']

    next_node_records = []
    choke_point_records = []

    for idx in node_indices:
        row_time     = tdf.loc[idx, 'Datetime']
        row_is_night = (row_time.hour >= 19) or (row_time.hour < 5)

        if row_is_night == is_night or len(node_indices) < 3:
            history_prev_node = tdf.iloc[idx - 1]['จุดติดตั้งกล้อง'] if idx > 0 else None

            if prev_node_name == history_prev_node or len(node_indices) < 3:
                next_idx = idx + 1
                while next_idx < len(tdf):
                    if tdf.iloc[next_idx]['จุดติดตั้งกล้อง'] != target_node_selection:
                        hrs_diff = (tdf.iloc[next_idx]['Datetime'] - tdf.iloc[idx]['Datetime']).total_seconds() / 3600.0
                        if hrs_diff <= 24.0:
                            next_node_records.append(tdf.iloc[next_idx])

                            # Choke point (ด่าน 2)
                            trip_idx = next_idx + 1
                            while trip_idx < len(tdf):
                                trip_hrs = (tdf.iloc[trip_idx]['Datetime'] - tdf.iloc[next_idx]['Datetime']).total_seconds() / 3600.0
                                if trip_hrs <= 24.0 and tdf.iloc[trip_idx]['จุดติดตั้งกล้อง'] != tdf.iloc[next_idx]['จุดติดตั้งกล้อง']:
                                    choke_point_records.append(tdf.iloc[trip_idx])
                                else:
                                    break
                                trip_idx += 1
                        break
                    next_idx += 1

    if not next_node_records:
        return {
            "time_context": time_context,
            "has_prediction": False,
            "message": f"ไม่พบประวัติการเดินทางต่อเนื่องจาก [{target_node_selection}] ไปยังสถานีอื่นในกรอบเวลา 24 ชม."
        }

    next_df = pd.DataFrame(next_node_records)
    total_transitions = len(next_df)
    next_stats = (
        next_df.groupby(['จุดติดตั้งกล้อง', 'ละติจูด', 'ลองจิจูด'])
        .size().reset_index(name='count')
        .sort_values('count', ascending=False)
    )

    closest_next = next_stats.iloc[0]

    # พิกัดจุดตั้งต้น (target node)
    target_row_ref = tdf[tdf['จุดติดตั้งกล้อง'] == target_node_selection].iloc[0]
    p_start_lat = float(target_row_ref['ละติจูด'])
    p_start_lon = float(target_row_ref['ลองจิจูด'])

    # ─── ระยะทาง ด่าน 1 — haversine แทน geodesic ───────────────
    dist_c = float(haversine_km(
        p_start_lat, p_start_lon,
        float(closest_next['ละติจูด']), float(closest_next['ลองจิจูด'])
    ))
    min_c, max_c, road_dist_c = get_hybrid_eta(
        p_start_lat, p_start_lon,
        float(closest_next['ละติจูด']), float(closest_next['ลองจิจูด']),
        [], dist_c
    )
    prob_c = (closest_next['count'] / max(total_transitions, 1)) * 100.0

    # ─── ด่าน 2 (Strategic Choke Point) ─────────────────────────
    best_next = None
    prob_b, dist_b, min_b, max_b = 0.0, 0.0, 0.0, 0.0

    if choke_point_records:
        choke_df = pd.DataFrame(choke_point_records)
        choke_df = choke_df[choke_df['จุดติดตั้งกล้อง'] != closest_next['จุดติดตั้งกล้อง']]
        if not choke_df.empty:
            choke_stats = (
                choke_df.groupby(['จุดติดตั้งกล้อง', 'ละติจูด', 'ลองจิจูด'])
                .size().reset_index(name='count')
                .sort_values('count', ascending=False)
            )
            # ─── vectorized distance filter แทน geodesic loop ──────────
            cl_lat = float(closest_next['ละติจูด'])
            cl_lon = float(closest_next['ลองจิจูด'])
            choke_dists = haversine_km(
                cl_lat, cl_lon,
                choke_stats['ละติจูด'].values.astype(float),
                choke_stats['ลองจิจูด'].values.astype(float)
            )
            valid_mask = choke_dists > 2.0
            valid_cp2  = choke_stats[valid_mask]

            if not valid_cp2.empty:
                best_next = valid_cp2.iloc[0]
                prob_b = (best_next['count'] / max(len(choke_df), 1)) * 100.0
                dist_b = float(haversine_km(
                    p_start_lat, p_start_lon,
                    float(best_next['ละติจูด']), float(best_next['ลองจิจูด'])
                ))
                min_b, max_b, _ = get_hybrid_eta(
                    p_start_lat, p_start_lon,
                    float(best_next['ละติจูด']), float(best_next['ลองจิจูด']),
                    [], dist_b
                )

    # 🚨 ตรวจสอบ U-Turn Alert
    base_target_name  = re.sub(r'_(เข้า|ออก).*', '', target_node_selection)
    base_t_cam_name   = re.sub(r'_(เข้า|ออก).*', '', closest_next['จุดติดตั้งกล้อง'])
    is_uturn = (base_target_name == base_t_cam_name)

    return {
        "time_context": time_context,
        "has_prediction": True,
        "prev_node": prev_node_name,
        "target_node": target_node_selection,
        "start_coords": (p_start_lat, p_start_lon),
        "node_1": {
            "cam": closest_next['จุดติดตั้งกล้อง'],
            "lat": float(closest_next['ละติจูด']),
            "lon": float(closest_next['ลองจิจูด']),
            "prob": prob_c,
            "dist_km": dist_c,
            "min_mins": min_c,
            "max_mins": max_c,
            "count": int(closest_next['count'])
        },
        "node_2": {
            "cam": best_next['จุดติดตั้งกล้อง'],
            "lat": float(best_next['ละติจูด']),
            "lon": float(best_next['ลองจิจูด']),
            "prob": prob_b,
            "dist_km": dist_b,
            "min_mins": min_b,
            "max_mins": max_b,
            "count": int(best_next['count'])
        } if best_next is not None else None,
        "is_uturn": is_uturn,
        "total_transitions": total_transitions
    }
