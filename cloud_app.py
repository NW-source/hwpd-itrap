"""
cloud_app.py — HWPD i-Trap Cloud Intelligence View
หน้าตาเหมือน app.py เพียงแต่อ่านข้อมูลจาก Supabase
"""
import streamlit as st
import pandas as pd
import json
from datetime import datetime

st.set_page_config(
    page_title="HWPD 60 i-Trap | Intelligence Command",
    page_icon="🛡️", layout="wide",
    initial_sidebar_state="expanded"
)

# ══ CSS เหมือน app.py ════════════════════════════════════════════════════════
st.markdown("""
<style>
@import url('https://fonts.googleapis.com/css2?family=Sarabun:wght@300;400;500;600;700;800&display=swap');
html,body,.stApp,[class*="css"]{font-family:'Sarabun','TH Sarabun PSK',sans-serif!important;font-size:16px!important}
html,body{background:#0a0e1a!important}
.stApp{background:linear-gradient(135deg,#0a0e1a 0%,#0d1321 50%,#0a1628 100%)!important}
.block-container{padding-top:1.5rem!important;padding-left:2rem!important;padding-right:2rem!important;max-width:100%!important}
section[data-testid="stSidebar"]{background:linear-gradient(180deg,#0d1321 0%,#0f172a 100%)!important;border-right:1px solid rgba(59,130,246,0.15)!important}
[data-testid="stMetricValue"]{font-size:26px!important;font-weight:800!important;color:#e2e8f0!important}
[data-testid="stMetricLabel"]{font-size:13px!important;color:#94a3b8!important}
.stTabs [data-baseweb="tab-list"]{background:rgba(15,23,42,0.6)!important;border-radius:12px!important;padding:4px!important}
.stTabs [data-baseweb="tab"]{color:#94a3b8!important;font-weight:600!important;border-radius:8px!important}
.stTabs [aria-selected="true"]{background:linear-gradient(135deg,#3b82f6,#6366f1)!important;color:white!important}

/* Priority Card */
.pri-card{background:rgba(15,23,42,0.75);border-radius:12px;padding:14px 18px;margin-bottom:10px;
    border:1px solid rgba(255,255,255,0.06);transition:transform .15s ease;}
.pri-card:hover{transform:translateY(-2px);}
.badge{display:inline-block;padding:2px 10px;border-radius:20px;font-size:12px;font-weight:700}
.badge-red  {background:rgba(239,68,68,.15);color:#ef4444;border:1px solid rgba(239,68,68,.3)}
.badge-ora  {background:rgba(249,115,22,.15);color:#f97316;border:1px solid rgba(249,115,22,.3)}
.badge-yel  {background:rgba(234,179,8,.15);color:#eab308;border:1px solid rgba(234,179,8,.3)}
.badge-grn  {background:rgba(16,185,129,.15);color:#10b981;border:1px solid rgba(16,185,129,.3)}
.badge-blue {background:rgba(59,130,246,.15);color:#60a5fa;border:1px solid rgba(59,130,246,.3)}

/* Ticker */
@keyframes ticker{0%{transform:translateX(100%)}100%{transform:translateX(-200%)}}
@keyframes blink{0%,100%{opacity:1}50%{opacity:.3}}
.ticker-wrap{overflow:hidden;background:linear-gradient(90deg,#020617,#0f172a,#020617);
    padding:9px 0;border-radius:8px;color:#38bdf8;border:1px solid rgba(56,189,248,0.15);margin-bottom:16px}
.ticker-content{display:inline-block;animation:ticker 40s linear infinite;font-weight:500;font-size:13px;white-space:nowrap}
.live-dot{display:inline-block;width:8px;height:8px;border-radius:50%;background:#10b981;
    margin-right:6px;animation:blink 1.5s infinite}
</style>
""", unsafe_allow_html=True)

# ══ Auth ══════════════════════════════════════════════════════════════════════
from auth import require_login, get_current_user, has_role, logout, ROLE_LABEL
from supabase_sync import (
    pull_available_dates, pull_daily_report, pull_realtime,
    pull_suspects, pull_upload_log,
)
require_login()

# ══ Sidebar ═══════════════════════════════════════════════════════════════════
st.sidebar.markdown("""
<div style='text-align:center;padding:14px 0 8px'>
  <div style='font-size:38px'>🛡️</div>
  <div style='font-size:15px;font-weight:800;color:#93c5fd;letter-spacing:2px'>HWPD 60 i-Trap</div>
  <div style='font-size:11px;color:#64748b;margin-top:3px'>Intelligence Command System</div>
  <div style='font-size:11px;color:#10b981;margin-top:4px'>☁️ Cloud View — Live</div>
</div>
<hr style='border-color:rgba(59,130,246,0.2);margin:6px 0'>
""", unsafe_allow_html=True)

_cu = get_current_user()
if _cu:
    _rl = ROLE_LABEL.get(_cu.get('role',''), _cu.get('role',''))
    st.sidebar.markdown(
        f"<div style='background:rgba(99,102,241,.12);padding:8px 12px;border-radius:8px;margin-bottom:6px'>"
        f"<span style='font-size:11px;color:#94a3b8'>ผู้ใช้งาน</span><br>"
        f"<b style='color:#e2e8f0'>{_cu.get('display_name',_cu.get('username',''))}</b><br>"
        f"<span style='font-size:11px;color:#818cf8'>{_rl}</span></div>",
        unsafe_allow_html=True)
    if st.sidebar.button("🔓 ออกจากระบบ", use_container_width=True):
        logout(); st.rerun()

st.sidebar.markdown("---")
st.sidebar.markdown("### 📅 เลือกวันที่รายงาน")
available_dates = pull_available_dates()
selected_date   = st.sidebar.selectbox("วันที่:", available_dates,
                                        format_func=lambda d: f"📅 {d}") if available_dates else None
st.sidebar.markdown("---")
if st.sidebar.button("🔄 รีเฟรชข้อมูล", use_container_width=True):
    pull_available_dates.clear(); pull_daily_report.clear()
    pull_realtime.clear(); pull_suspects.clear(); pull_upload_log.clear()
    st.rerun()

if has_role('super_admin','admin'):
    with st.sidebar.expander("📋 ประวัติอัปโหลด", expanded=False):
        log_df = pull_upload_log(8)
        if not log_df.empty:
            for _, r in log_df.iterrows():
                ts = str(r.get('uploaded_at',''))[:16].replace('T',' ')
                st.markdown(f"<div style='font-size:12px;padding:4px 0;border-bottom:1px solid rgba(255,255,255,.06)'>"
                            f"<b style='color:#60a5fa'>{r.get('display_name') or r.get('username','?')}</b><br>"
                            f"📅 {r.get('report_date','?')} | {ts}<br>"
                            f"<span style='color:#64748b'>{int(r.get('record_count',0)):,} records</span></div>",
                            unsafe_allow_html=True)

# ══ Helper Functions ═══════════════════════════════════════════════════════════
def get_plate(row: dict) -> str:
    """ดึงทะเบียนหลัก — รองรับทุกรูปแบบ"""
    cars = row.get('Cars_List')
    if isinstance(cars, list) and cars:
        return ' / '.join(str(c) for c in cars[:3]) + ('…' if len(cars) > 3 else '')
    if isinstance(cars, str):
        try:
            c = json.loads(cars)
            if isinstance(c, list) and c: return c[0]
        except: pass
        return cars
    for col in ('เป้าหมาย','Target_ID','plate','ทะเบียนรถ'):
        if v := row.get(col): return str(v)
    return '—'

def get_type_badge(eng_type: str) -> str:
    t = str(eng_type)
    if 'ขบวน' in t or 'convoy' in t.lower():   return '<span class="badge badge-red">🔴 ขบวน</span>'
    if 'กลุ่ม' in t or 'group' in t.lower():   return '<span class="badge badge-ora">🟠 กลุ่มรถ</span>'
    if 'ซ้ำ'   in t or 'repeat' in t.lower():  return '<span class="badge badge-yel">🟡 วิ่งซ้ำ</span>'
    if 'เป้า'  in t or 'target' in t.lower():  return '<span class="badge badge-red">🎯 เป้าหมาย</span>'
    return f'<span class="badge badge-blue">{t or "ไม่ระบุ"}</span>'

def score_to_bar(score) -> str:
    try:
        s = float(score)
        w = min(100, max(0, s / 2))
        color = '#ef4444' if s >= 120 else '#f97316' if s >= 80 else '#eab308' if s >= 40 else '#22c55e'
        return (f"<div style='background:rgba(255,255,255,.08);border-radius:4px;height:6px;margin-top:4px'>"
                f"<div style='width:{w}%;background:{color};height:6px;border-radius:4px'></div></div>")
    except: return ''

def render_priority_cards(df: pd.DataFrame, tab_key: str = "x"):
    if df.empty:
        st.info("✅ ยังไม่พบรถต้องสงสัยในระบบ")
        return

    n = len(df)
    if n > 20:
        show_n = st.slider("แสดง (คัน):", 10, min(n, 200), min(50, n), key=f"sld_{tab_key}")
    else:
        show_n = n

    st.markdown(f"<div style='color:#64748b;font-size:13px;margin-bottom:8px'>แสดง {show_n} / {n} รายการ — <b style='color:#60a5fa'>คลิกที่รถเพื่อดูรายละเอียด ▼</b></div>",
                unsafe_allow_html=True)

    for idx, (_, row) in enumerate(df.head(show_n).iterrows()):
        r      = row.to_dict()
        plate  = get_plate(r)
        typ    = str(r.get('ประเภท', r.get('engine_type', '')))
        score  = r.get('Risk Score', r.get('risk_score', r.get('คะแนนรวม', 0)))
        behav  = str(r.get('พฤติกรรมต้องสงสัย', r.get('เหตุผลหลัก', r.get('เหตุผล', '—'))))
        cam    = str(r.get('จุดตรวจพบล่าสุด', r.get('last_cam', '—')))
        t_last = str(r.get('เวลาโผล่ล่าสุด',  r.get('last_time', '—')))[:5]
        n_cams = r.get('ผ่านร่วมกัน (ด่าน)', r.get('กล้องที่พบ', '—'))
        score_disp = int(float(score)) if str(score).replace('.','').isdigit() else score

        # Color border by type
        border_color = '#ef4444' if 'ขบวน' in typ or 'เป้า' in typ else \
                       '#f97316' if 'กลุ่ม' in typ else \
                       '#eab308' if 'ซ้ำ'   in typ else '#3b82f6'

        # Expander label = plate + badge + score (คลิกได้)
        exp_label = f"🚗 {plate}  |  {typ or 'ไม่ระบุ'}  |  ⭐ {score_disp} คะแนน  |  📍 {cam}"

        with st.expander(exp_label, expanded=False):
            # ── ข้อมูลหลัก ─────────────────────────────────────
            c1, c2, c3 = st.columns(3)
            with c1:
                st.markdown("**🚗 ทะเบียน**")
                # Cars_List
                cars = r.get('Cars_List')
                if isinstance(cars, list) and cars:
                    for car in cars:
                        st.markdown(f"- `{car}`")
                elif isinstance(cars, str) and cars not in ('', '-', 'nan'):
                    try:
                        import json as _j
                        cl = _j.loads(cars)
                        for car in (cl if isinstance(cl, list) else [cl]):
                            st.markdown(f"- `{car}`")
                    except:
                        st.markdown(f"- `{cars}`")
                else:
                    st.markdown(f"`{plate}`")

            with c2:
                st.markdown("**📊 ข้อมูลการตรวจพบ**")
                st.markdown(f"- ประเภท: **{typ or '—'}**")
                st.markdown(f"- คะแนนความเสี่ยง: **{score_disp}**")
                st.markdown(f"- จำนวนด่านที่ผ่าน: **{n_cams}**")
                st.markdown(f"- จุดตรวจล่าสุด: **{cam}**")
                st.markdown(f"- เวลาล่าสุด: **{t_last} น.**")

            with c3:
                st.markdown("**📏 ข้อมูลเพิ่มเติม**")
                dist  = r.get('Total_Dist', r.get('ระยะห่างเฉลี่ย', '—'))
                speed = r.get('Speed_Warp', '—')
                st.markdown(f"- ระยะทาง: **{dist}**")
                st.markdown(f"- ความเร็ว: **{speed}**")
                target_id = r.get('Target_ID', plate)
                st.markdown(f"- Target ID: `{target_id}`")

            # ── พฤติกรรมต้องสงสัย ──────────────────────────────
            st.markdown("---")
            st.markdown("**🔍 พฤติกรรมต้องสงสัย / เหตุผลการแจ้งเตือน**")
            st.warning(behav if behav not in ('—','nan','') else "ไม่มีข้อมูลเพิ่มเติม")

            # ── Radar Data (ถ้ามี) ─────────────────────────────
            radar = r.get('Radar_Data')
            if radar and str(radar) not in ('','nan','None'):
                st.markdown("**📡 ข้อมูลเส้นทาง (Radar)**")
                try:
                    if isinstance(radar, str):
                        import json as _j
                        radar = _j.loads(radar)
                    if isinstance(radar, list) and len(radar) > 0:
                        radar_df = pd.DataFrame(radar)
                        # แสดงเฉพาะคอลัมน์สำคัญ
                        show_cols = [c for c in ['cam','time','speed','lat','lon','plate'] if c in radar_df.columns]
                        if show_cols:
                            st.dataframe(radar_df[show_cols].head(20), use_container_width=True, hide_index=True)
                        else:
                            st.dataframe(radar_df.head(20), use_container_width=True, hide_index=True)
                except:
                    st.code(str(radar)[:500])


# ══ Main Content ═══════════════════════════════════════════════════════════════
# Header
now_th = datetime.now().strftime('%d/%m/%Y %H:%M')
st.markdown(f"""
<div style='background:rgba(15,23,42,.6);border:1px solid rgba(56,189,248,.15);border-radius:10px;
    padding:10px 20px;margin-bottom:16px'>
  <span class="live-dot"></span>
  <span style='font-size:13px;color:#38bdf8;font-weight:600'>SYSTEM ONLINE</span>
  <span style='font-size:12px;color:#475569;margin-left:12px'>| HWPD 60 COMMAND CENTER ACTIVE | {now_th}</span>
</div>
""", unsafe_allow_html=True)

st.markdown("""
<div style='padding:8px 0 16px'>
  <div style='font-size:24px;font-weight:800;color:#e2e8f0'>
    🛡️ ข้อมูลสรุปเป้าหมายสำคัญ (Intelligence Brief)
  </div>
  <div style='font-size:13px;color:#64748b;margin-top:4px'>
    ศูนย์ปฏิบัติการข่าวกรองสกัดกั้นยาเสพติดชายแดน | HWPD 60 i-Trap Command Center
  </div>
</div>
""", unsafe_allow_html=True)

if not selected_date:
    st.warning("⏳ ยังไม่มีข้อมูลใน Cloud — Admin ต้องอัปโหลดข้อมูลก่อนครับ")
    st.stop()

# Load data
report      = pull_daily_report(selected_date)
priority_df = report.get('priority_df', pd.DataFrame())
rec_count   = report.get('record_count', 0)
uploader    = report.get('uploaded_by', 'ไม่ระบุ')

today_str   = datetime.now().strftime('%Y-%m-%d')
rt_data     = pull_realtime(today_str) if selected_date == today_str else None

# Metrics
n_targets   = len(priority_df)
n_confirmed = 0; n_watch = 0
if not priority_df.empty and 'ประเภท' in priority_df.columns:
    n_confirmed = int(priority_df['ประเภท'].str.contains('ขบวน|กลุ่มรถ|เป้าหมาย', na=False).sum())
    n_watch     = n_targets - n_confirmed

c1,c2,c3,c4,c5 = st.columns(5)
with c1: st.metric("🚗 บันทึกทั้งหมด",  f"{rec_count:,}")
with c2: st.metric("🎯 เป้าหมายทั้งหมด", f"{n_targets:,}")
with c3: st.metric("🔴 ยืนยัน",          f"{n_confirmed:,}")
with c4: st.metric("🟡 น่าสงสัย",        f"{n_watch:,}")
with c5: st.metric("⚡ Realtime วันนี้", f"{rt_data.get('record_count',0):,}" if rt_data else "—")

st.markdown("---")

# Tabs
tab_rt, tab_daily, tab_repeat = st.tabs([
    "⚡ Realtime (วันนี้)",
    f"📅 ประจำวัน ({selected_date})",
    "🔁 รถวิ่งซ้ำ (Repeat Offenders)"
])

# ── TAB Realtime ──────────────────────────────────────────────────────────────
with tab_rt:
    if selected_date != today_str:
        st.info(f"⚠️ Realtime ใช้ได้เฉพาะวันที่ {today_str} — กรุณาเลือกวันนี้ใน Sidebar")
    elif rt_data is None:
        st.markdown("""
        <div style='background:rgba(245,158,11,.1);border-left:4px solid #f59e0b;
            padding:24px;border-radius:12px;margin-top:16px'>
          <div style='font-size:28px'>⏳</div>
          <div style='font-size:18px;font-weight:700;color:#fbbf24;margin-top:8px'>
            ยังไม่มีข้อมูล Realtime วันนี้
          </div>
          <div style='font-size:14px;color:#94a3b8;margin-top:8px'>
            รอ Admin อัปโหลดข้อมูลกะแรกของวัน — กด 🔄 รีเฟรชข้อมูล ทุก 15 นาที
          </div>
        </div>""", unsafe_allow_html=True)
    else:
        rt_priority = rt_data.get('priority_df', pd.DataFrame())
        cr1,cr2,cr3,cr4 = st.columns(4)
        with cr1: st.metric("⚡ Records วันนี้",   f"{rt_data.get('record_count',0):,}")
        with cr2:
            ft = str(rt_data.get('first_time',''))[:5]
            lt = str(rt_data.get('last_time',''))[:5]
            st.metric("🕐 ช่วงเวลา", f"{ft} – {lt} น.")
        with cr3: st.metric("📤 Upload ครั้งที่",   str(rt_data.get('upload_count',1)))
        with cr4: st.metric("🎯 เป้าหมายพบ",       str(len(rt_priority)) if not rt_priority.empty else "0")

        st.markdown("---")
        if not rt_priority.empty:
            st.markdown(f"#### 🎯 รถเป้าหมาย Realtime ({len(rt_priority)} คัน)")
            render_priority_cards(rt_priority, "rt")
        else:
            st.success("✅ ยังไม่พบรถต้องสงสัยในช่วงนี้")

# ── TAB Daily ─────────────────────────────────────────────────────────────────
with tab_daily:
    if priority_df.empty:
        st.info(f"ยังไม่มีผลวิเคราะห์สำหรับวันที่ {selected_date}")
    else:
        # Ticker
        plates_str = " ▸ ".join(
            get_plate(r) for _, r in priority_df.head(15).iterrows()
        )
        st.markdown(f"""
        <div class="ticker-wrap">
          <span class="ticker-content">
            <span class="live-dot"></span>
            <b>PRIORITY TARGETS {selected_date}</b> &nbsp; ▸ &nbsp; {plates_str}
          </span>
        </div>""", unsafe_allow_html=True)

        st.markdown(
            f"#### 🎯 รายชื่อรถเป้าหมาย ประจำวันที่ {selected_date} ({n_targets} คัน)")
        st.caption(f"📤 อัปโหลดโดย: **{uploader}** | 📊 ข้อมูล {rec_count:,} รายการ")
        render_priority_cards(priority_df, "daily")

# ── TAB Repeat Offenders ──────────────────────────────────────────────────────
with tab_repeat:
    suspect_df = pull_suspects(200)
    if suspect_df.empty:
        st.info("ยังไม่มีข้อมูลรถวิ่งซ้ำใน Cloud")
    else:
        st.markdown(f"#### 🔁 รถที่ปรากฏซ้ำในระบบ ({len(suspect_df)} คัน)")
        col_map = {'plate':'ทะเบียน','seen_count':'ครั้งที่พบ',
                   'last_seen':'พบล่าสุด','engine_types':'ประเภทภัยคุกคาม','risk_score':'คะแนน'}
        avail = [c for c in col_map if c in suspect_df.columns]
        st.dataframe(suspect_df[avail].rename(columns=col_map),
                     use_container_width=True, hide_index=True)
