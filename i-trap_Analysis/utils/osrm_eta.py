import requests
from utils.data_processor import haversine_km


def get_hybrid_eta(start_lat, start_lon, end_lat, end_lon, hist_times=None, default_geodesic_km=0.0):
    """
    คำนวณระยะทางและเวลาขับขี่ลูกผสม (Hybrid ETA):
    OSRM API + Historical Passage Times + Haversine Estimate (แทน geodesic)

    Optimization: ใช้ haversine_km แทน geodesic() ประหยัด dependency และเร็วกว่า
    """
    osrm_dist = None
    osrm_dur  = None

    if default_geodesic_km <= 0.0:
        default_geodesic_km = float(haversine_km(start_lat, start_lon, end_lat, end_lon))

    try:
        url = (
            f"http://router.project-osrm.org/route/v1/driving/"
            f"{start_lon},{start_lat};{end_lon},{end_lat}?overview=false"
        )
        resp = requests.get(url, timeout=2.5).json()
        if resp.get("code") == "Ok":
            osrm_dist = resp["routes"][0]["distance"] / 1000.0
            osrm_dur  = resp["routes"][0]["duration"] / 60.0
    except Exception:
        pass

    h_min = min(hist_times) if hist_times else None
    h_max = max(hist_times) if hist_times else None

    if osrm_dur and osrm_dist and osrm_dist < default_geodesic_km * 3.5:
        p_min, p_max = osrm_dur * 0.85, osrm_dur * 1.30
        road_dist = osrm_dist
    else:
        road_dist = default_geodesic_km * 1.3
        p_min, p_max = (road_dist / 120.0) * 60.0, (road_dist / 50.0) * 60.0

    if h_min and h_max:
        f_min, f_max = min(h_min, p_min), max(h_max, p_max)
    else:
        f_min, f_max = p_min, p_max

    if f_min >= f_max:
        f_min = max(1.0, f_min - 2.0)
        f_max = f_min + 3.0

    return f_min, f_max, road_dist


def format_minutes_to_hm(minutes):
    """แปลงนาทีเป็นข้อความ ชั่วโมง/นาที"""
    try:
        mins = int(round(float(minutes)))
        if mins < 60:
            return f"{mins} นาที"
        hours   = mins // 60
        rem_mins = mins % 60
        if rem_mins == 0:
            return f"{hours} ชั่วโมง"
        return f"{hours} ชั่วโมง {rem_mins} นาที"
    except (ValueError, TypeError):
        return "ไม่ระบุ"
