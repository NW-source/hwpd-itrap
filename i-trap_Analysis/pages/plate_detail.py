# -*- coding: utf-8 -*-
"""
plate_detail.py — Streamlit Plate Detail Page
รับ query param ?plate=กข1234&src=line
แสดงข้อมูล watchlist + แผนที่ (static สำหรับมือถือ, Folium สำหรับ PC)
"""
import os, json, re
import streamlit as st
import psycopg2

# ── Config ────────────────────────────────────────────────────────────────────
_PG_CFG = {
    "host": os.environ.get("ITRAP_PG_HOST", "127.0.0.1"),
    "port": 5432, "dbname": "itrap_db",
    "user": "itrap_admin",
    "password": "Hwpd@iTrap2026!Secure",
    "connect_timeout": 3,
}

st.set_page_config(
    page_title="i-Trap Plate Detail",
    page_icon="🚨",
    layout="wide",
    initial_sidebar_state="collapsed",
)

# ── CSS ───────────────────────────────────────────────────────────────────────
st.markdown("""
<style>
@import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;600;700;900&display=swap');
html,body,[class*="css"]{font-family:'Inter',sans-serif;background:#0f172a!important;color:#f1f5f9;}
.stApp{background:#0f172a;}
.detail-card{background:#1e293b;border:1px solid #334155;border-radius:16px;padding:24px;margin-bottom:16px;}
.risk-bar-bg{background:#334155;border-radius:99px;height:10px;width:100%;margin:6px 0;}
.risk-bar-fill{border-radius:99px;height:10px;}
.badge{display:inline-block;padding:4px 12px;border-radius:99px;font-size:12px;font-weight:700;margin:4px 2px;}
</style>
""", unsafe_allow_html=True)

# ── Read query params ─────────────────────────────────────────────────────────
params  = st.query_params
plate_q = params.get("plate", "")
src     = params.get("src", "")   # "line" = มือถือ
is_mobile = (src == "line")

if not plate_q:
    st.error("ไม่ระบุทะเบียน — กรุณาเปิดผ่านลิงก์จาก LINE")
    st.stop()

# ── Query PostgreSQL ──────────────────────────────────────────────────────────
@st.cache_data(ttl=60, show_spinner=False)
def fetch_plate(plate: str):
    try:
        conn = psycopg2.connect(**_PG_CFG)
        cur  = conn.cursor()
        plate_norm = re.sub(r"\s+", "", plate)
        cur.execute("""
            SELECT plate, province, seen_count, last_checkpoint,
                   last_seen_time, behavior_type, risk_score,
                   reason, verdict, convoy_members, convoy_role,
                   lat, lon, added_at
            FROM watchlist
            WHERE is_active = TRUE
              AND REPLACE(plate,' ','') ILIKE %s
            ORDER BY added_at DESC LIMIT 1
        """, [f"%{plate_norm}%"])
        row = cur.fetchone()
        conn.close()
        if not row:
            return None
        cols = ["plate","province","seen_count","last_checkpoint",
                "last_seen_time","behavior_type","risk_score",
                "reason","verdict","convoy_members","convoy_role","lat","lon","added_at"]
        return dict(zip(cols, row))
    except Exception as e:
        return None

data = fetch_plate(plate_q)

# ── Not Found ─────────────────────────────────────────────────────────────────
if not data:
    st.markdown(f"""
    <div class="detail-card" style="text-align:center;padding:40px;">
      <div style="font-size:48px;margin-bottom:12px;">❌</div>
      <div style="font-size:24px;font-weight:700;color:#f1f5f9;">ไม่พบข้อมูล</div>
      <div style="color:#64748b;margin-top:8px;">ทะเบียน <b style="color:#f1f5f9;">{plate_q}</b> ไม่อยู่ใน Watchlist</div>
    </div>""", unsafe_allow_html=True)
    st.stop()

# ── Found — Header ─────────────────────────────────────────────────────────────
plate    = data["plate"]
score    = data["risk_score"] or 0
province = data["province"] or "-"
btype    = data["behavior_type"] or "-"
members  = data["convoy_members"] or []
if isinstance(members, str):
    try: members = json.loads(members)
    except: members = []
is_conv  = data["convoy_role"] in ("lead", "follow")

def risk_color(s):
    if s >= 80: return "#ef4444"
    if s >= 50: return "#f59e0b"
    return "#10b981"

def behavior_emoji(t):
    t = (t or "").lower()
    if "ghost" in t:  return "👻 Ghost Plate"
    if "convoy" in t: return "🚛 Convoy"
    if "border" in t or "u-turn" in t: return "🔄 Border U-Turn"
    if "night" in t:  return "🌙 Night Ghost"
    return f"⚠️ {t}" if t else "⚠️ ไม่ระบุ"

rc = risk_color(score)
st.markdown(f"""
<div style="background:linear-gradient(135deg,#7f1d1d,#1e293b);border-radius:20px;
            padding:28px;margin-bottom:20px;border:1px solid #ef4444;">
  <div style="font-size:12px;color:#fca5a5;font-weight:700;letter-spacing:.15em;margin-bottom:4px;">
    🚨 HWPD i-Trap Intelligence — WATCHLIST
  </div>
  <div style="font-size:36px;font-weight:900;color:#ffffff;margin-bottom:4px;">{plate}</div>
  <div style="font-size:14px;color:#fca5a5;">📍 {province} &nbsp;|&nbsp; 🎯 {behavior_emoji(btype)}</div>
</div>""", unsafe_allow_html=True)

# ── Info Grid ─────────────────────────────────────────────────────────────────
c1, c2 = st.columns(2)
with c1:
    st.markdown(f"""<div class="detail-card">
      <div style="font-size:11px;color:#94a3b8;font-weight:600;margin-bottom:12px;">📊 ข้อมูลการพบ</div>
      <div style="font-size:28px;font-weight:900;color:#f1f5f9;">{data['seen_count'] or '-'} ครั้ง</div>
      <div style="color:#64748b;font-size:12px;">จำนวนที่ผ่านกล้อง</div>
      <hr style="border-color:#334155;margin:12px 0;">
      <div style="font-size:12px;color:#94a3b8;">📌 จุดล่าสุด</div>
      <div style="font-size:14px;color:#f1f5f9;font-weight:600;margin-top:4px;">
        {data['last_checkpoint'] or '-'}
      </div>
      <div style="font-size:12px;color:#64748b;">🕐 {data['last_seen_time'] or '-'}</div>
    </div>""", unsafe_allow_html=True)

with c2:
    bar_pct = min(score, 100)
    risk_lbl = "สูงมาก" if score >= 80 else ("ปานกลาง" if score >= 50 else "ต่ำ")
    st.markdown(f"""<div class="detail-card">
      <div style="font-size:11px;color:#94a3b8;font-weight:600;margin-bottom:12px;">⚠️ Risk Score</div>
      <div style="font-size:36px;font-weight:900;color:{rc};">{score}<span style="font-size:16px;color:#64748b;">/100</span></div>
      <div class="risk-bar-bg"><div class="risk-bar-fill" style="width:{bar_pct}%;background:{rc};"></div></div>
      <div style="font-size:12px;color:{rc};font-weight:700;">{risk_lbl}</div>
      <hr style="border-color:#334155;margin:12px 0;">
      <div style="font-size:12px;color:#94a3b8;">📝 เหตุผล</div>
      <div style="font-size:12px;color:#cbd5e1;margin-top:4px;">{data['reason'] or '-'}</div>
    </div>""", unsafe_allow_html=True)

# ── Convoy Members ────────────────────────────────────────────────────────────
if is_conv and members:
    role_lbl = "นำขบวน 🚛" if data["convoy_role"] == "lead" else "ตามขบวน 🚗"
    items_html = "".join(f'<div style="padding:6px 0;border-bottom:1px solid #334155;color:#e2e8f0;font-size:14px;">🚗 {m}</div>' for m in members)
    st.markdown(f"""<div class="detail-card">
      <div style="font-size:11px;color:#94a3b8;font-weight:600;margin-bottom:12px;">🚛 ขบวนรถ — {role_lbl}</div>
      {items_html}
    </div>""", unsafe_allow_html=True)

# ── MAP ───────────────────────────────────────────────────────────────────────
lat, lon = data.get("lat"), data.get("lon")
st.markdown("### 🗺️ แผนที่จุดพบล่าสุด")

if lat and lon:
    if is_mobile:
        # มือถือ: Static image (OpenStreetMap) + ปุ่ม Google Maps
        zoom = 15
        all_pts = [(lat, lon)] + [(lat, lon) for _ in members]  # placeholder convoy pts
        markers_param = f"&markers={lat},{lon},red"
        static_url = (
            f"https://staticmap.openstreetmap.de/staticmap.php"
            f"?center={lat},{lon}&zoom={zoom}&size=600x300{markers_param}"
        )
        gmaps_url = f"https://www.google.com/maps?q={lat},{lon}"
        st.image(static_url, use_container_width=True,
                 caption=f"📌 {data['last_checkpoint'] or plate}")
        st.link_button("📍 เปิดใน Google Maps", gmaps_url, use_container_width=True)
    else:
        # คอม: Folium interactive map
        try:
            import folium
            from streamlit_folium import st_folium
            m = folium.Map(location=[lat, lon], zoom_start=14, tiles="CartoDB dark_matter")
            folium.Marker(
                [lat, lon],
                popup=f"{plate}<br>{data['last_checkpoint']}<br>{data['last_seen_time']}",
                tooltip=plate,
                icon=folium.Icon(color="red", icon="car", prefix="fa"),
            ).add_to(m)
            # convoy markers (ถ้ามี)
            if is_conv and members:
                for i, mem in enumerate(members):
                    # convoy members ใช้ lat/lon เดียวกันก่อน (จนกว่าจะมีข้อมูล)
                    folium.Marker(
                        [lat + (i+1)*0.0005, lon + (i+1)*0.0005],
                        tooltip=mem,
                        icon=folium.Icon(color="blue", icon="car", prefix="fa"),
                    ).add_to(m)
            st_folium(m, use_container_width=True, height=420)
            gmaps_url = f"https://www.google.com/maps?q={lat},{lon}"
            st.link_button("📍 เปิดใน Google Maps", gmaps_url)
        except ImportError:
            st.info("ติดตั้ง streamlit-folium เพื่อดูแผนที่แบบ interactive")
            gmaps_url = f"https://www.google.com/maps?q={lat},{lon}"
            st.link_button("📍 เปิดใน Google Maps", gmaps_url, use_container_width=True)
else:
    st.info("⚠️ ไม่มีพิกัดที่พบล่าสุด — กรุณาอัปเดตข้อมูลผ่าน i-Trap Analysis")
    st.link_button("🔎 เปิด i-Trap Dashboard", f"http://{os.environ.get('ITRAP_HOST','129.150.56.185')}:8501",
                   use_container_width=True)
