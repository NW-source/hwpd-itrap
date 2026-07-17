"""
cloud_app.py — HWPD i-Trap Cloud Intelligence View
ใช้โค้ดการแสดงผลเหมือน app.py ทุกอย่าง อ่านข้อมูลจาก Supabase
"""
import streamlit as st
import pandas as pd
import numpy as np
import plotly.graph_objects as go
import json
from io import BytesIO
from datetime import datetime

st.set_page_config(
    page_title="HWPD 60 i-Trap Command Center",
    page_icon="🛡️", layout="wide",
    initial_sidebar_state="expanded"
)

# ══ Auth & Sync ════════════════════════════════════════════════════════════════
from auth import require_login, get_current_user, has_role, logout, ROLE_LABEL
from supabase_sync import (
    pull_available_dates, pull_daily_report, pull_realtime,
    pull_suspects, pull_upload_log,
)
require_login()

# ══ CSS (เหมือน app.py ทุกอย่าง) ═════════════════════════════════════════════
st.markdown("""<style>
@import url('https://fonts.googleapis.com/css2?family=Sarabun:wght@300;400;500;600;700;800&display=swap');
html,body,.stApp,[class*="css"]{font-family:'Sarabun','TH Sarabun PSK',sans-serif!important;font-size:16px!important}
html,body{background:#0a0e1a!important}
.stApp{background:linear-gradient(135deg,#0a0e1a 0%,#0d1321 50%,#0a1628 100%)!important;min-height:100vh}
.main{background:transparent!important}
.block-container{padding-top:3.5rem!important;padding-left:2rem!important;padding-right:2rem!important;max-width:100%!important}
section[data-testid="stSidebar"]{background:linear-gradient(180deg,#0d1321 0%,#0f172a 100%)!important;border-right:1px solid rgba(59,130,246,0.15)!important}
[data-testid="stMetricValue"]{font-size:28px!important;font-weight:800!important;color:#e2e8f0!important}
[data-testid="stMetricLabel"]{font-size:13px!important;color:#94a3b8!important}
.stTabs [data-baseweb="tab-list"]{background:rgba(15,23,42,0.6)!important;border-radius:12px!important;padding:4px!important}
.stTabs [data-baseweb="tab"]{color:#94a3b8!important;font-weight:600!important;border-radius:8px!important}
.stTabs [aria-selected="true"]{background:linear-gradient(135deg,#3b82f6,#6366f1)!important;color:white!important}
.main-title{font-size:28px;font-weight:800;color:#e2e8f0;margin-bottom:4px}
.main-subtitle{font-size:14px;color:#64748b;margin-bottom:12px}
.header-divider{border:none;border-top:1px solid rgba(59,130,246,0.2);margin:12px 0 20px}
.dossier-reason{background:linear-gradient(135deg,#450a0a,#7f1d1d);border-left:5px solid #dc2626;
    padding:16px 20px;border-radius:10px;color:#fca5a5;margin-bottom:16px;font-size:15px}
.dossier-summary{background:rgba(15,23,42,0.8);border:1px solid rgba(59,130,246,0.2);
    border-radius:12px;padding:20px;margin:12px 0}
.metric-card{padding:20px 16px;border-radius:14px;text-align:center;margin-bottom:16px;
    border:1px solid rgba(255,255,255,0.07);backdrop-filter:blur(12px)}
@keyframes ticker{0%{transform:translateX(100%)}100%{transform:translateX(-200%)}}
@keyframes blink{0%,100%{opacity:1}50%{opacity:.3}}
.ticker-wrap{overflow:hidden;background:linear-gradient(90deg,#020617,#0f172a,#020617);
    padding:9px 0;border-radius:8px;color:#38bdf8;border:1px solid rgba(56,189,248,0.15);margin-bottom:16px}
.ticker-content{display:inline-block;animation:ticker 40s linear infinite;font-weight:500;font-size:13px;white-space:nowrap}
.live-dot{display:inline-block;width:8px;height:8px;border-radius:50%;background:#10b981;
    margin-right:6px;animation:blink 1.5s infinite}
</style>""", unsafe_allow_html=True)

# ══ Helper Functions (เหมือน app.py) ══════════════════════════════════════════
def excel_download_button(df: pd.DataFrame, filename: str, label: str = "📥 Export Excel"):
    try:
        buf = BytesIO()
        with pd.ExcelWriter(buf, engine='openpyxl') as writer:
            df.to_excel(writer, index=False, sheet_name='HWPD_Data')
        st.download_button(label=label, data=buf.getvalue(), file_name=filename,
            mime='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
            use_container_width=False)
    except Exception as e:
        st.caption(f"⚠️ Export ไม่สำเร็จ: {e}")

def color_score(val):
    try:
        v = int(str(val).replace('%', ''))
        color  = '#fecdd3' if v >= 90 else '#fed7aa' if v >= 75 else '#fef08a'
        text_c = '#881337' if v >= 90 else '#9a3412' if v >= 75 else '#854d0e'
        return f'background-color:{color};color:{text_c};font-weight:bold;border-radius:4px;'
    except:
        return ''

def get_plate_display(row: dict) -> str:
    cars = row.get('Cars_List')
    if isinstance(cars, list) and cars:
        return ' / '.join(str(c) for c in cars[:3]) + ('…' if len(cars) > 3 else '')
    if isinstance(cars, str):
        try:
            cl = json.loads(cars)
            if isinstance(cl, list): return ' / '.join(str(c) for c in cl[:3])
        except: return cars
    for col in ('เป้าหมาย','Target_ID','plate'):
        if v := row.get(col): return str(v)
    return '—'

# ══ Case Dossier (Cloud Version — ใช้ข้อมูลจาก priority_df) ══════════════════
def render_case_dossier_cloud(selected_target: str, priority_df: pd.DataFrame):
    """แสดงแฟ้มคดี จาก priority_df (ไม่ต้องใช้ active_db)"""
    rows = priority_df[priority_df['Target_ID'] == selected_target]
    if rows.empty:
        st.warning("ไม่พบข้อมูลเป้าหมายนี้")
        return

    target_info = rows.iloc[0]
    typ   = str(target_info.get('ประเภท', ''))
    is_clone   = "สวมทะเบียน" in typ
    is_convoy  = "ขบวน" in typ

    # Cars list
    cars = target_info.get('Cars_List', [])
    if isinstance(cars, str):
        try:    cars = json.loads(cars)
        except: cars = [cars]
    if not isinstance(cars, list): cars = [str(cars)]

    st.markdown(f"## 📂 ข้อมูลเป้าหมายเฝ้าระวัง: {selected_target}")
    st.markdown("<hr style='border:2px solid #94a3b8'>", unsafe_allow_html=True)

    # ── พฤติกรรม ──
    behav = str(target_info.get('พฤติกรรมต้องสงสัย', '—'))
    if is_clone:
        st.markdown(f"<div class='dossier-reason'><b>🚨 ภัยคุกคามระดับวิกฤต:</b><br>"
                    f"<span style='font-size:16px'>{behav}</span></div>", unsafe_allow_html=True)
    else:
        score = target_info.get('Risk Score', '—')
        st.markdown(f"<div class='dossier-reason' style='background:linear-gradient(135deg,#1e1b4b,#312e81);"
                    f"border-color:#6366f1;color:#c7d2fe'>"
                    f"<b>⚠️ ตรวจพบพฤติการณ์ต้องสงสัย:</b> {behav}<br>"
                    f"<span style='font-size:14px;opacity:.8'>(ระดับภัยคุกคาม: {score})</span></div>",
                    unsafe_allow_html=True)

    # ── Radar Chart + Summary ──
    col_radar, col_summary = st.columns([4, 6])

    with col_radar:
        radar_raw = target_info.get("Radar_Data", {})
        if isinstance(radar_raw, str):
            try:    radar_raw = json.loads(radar_raw)
            except: radar_raw = {}
        if isinstance(radar_raw, dict) and radar_raw:
            r_vals = [radar_raw.get('Night',0), radar_raw.get('Border',0),
                      radar_raw.get('Shuttle',0), radar_raw.get('Regional',0),
                      radar_raw.get('Convoy',0)]
            theta_vals = ['ห้วงเวลาวิกาล\n(Max 20)', 'พื้นที่ชายแดน\n(Max 30)',
                          'ความถี่ผ่านด่าน\n(Max 20)', 'ยานพาหนะต่างถิ่น\n(Max 10)',
                          'เคลื่อนที่แบบกลุ่ม\n(Max 20)']
            r_vals.append(r_vals[0]); theta_vals.append(theta_vals[0])
            fig_radar = go.Figure()
            fig_radar.add_trace(go.Scatterpolar(
                r=r_vals, theta=theta_vals, fill='toself',
                name='พฤติกรรมเป้าหมาย', line_color='#9f1239',
                fillcolor='rgba(159,18,57,0.4)'))
            fig_radar.update_layout(
                polar=dict(radialaxis=dict(visible=True, range=[0,30], showticklabels=False),
                           gridshape='linear'),
                showlegend=False, height=300,
                margin=dict(t=20,b=20,l=40,r=40),
                title=dict(text="📊 แผนภูมิวิเคราะห์รูปแบบพฤติกรรม (Risk Radar)", font=dict(size=14)),
                paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)")
            st.plotly_chart(fig_radar, use_container_width=True,
                            key=f"radar_{selected_target}")
        else:
            st.info("ไม่มีข้อมูล Radar Chart")

    with col_summary:
        n_cams     = target_info.get('ผ่านร่วมกัน (ด่าน)', '—')
        last_cam   = target_info.get('จุดตรวจพบล่าสุด', '—')
        last_time  = str(target_info.get('เวลาโผล่ล่าสุด', '—'))[:5]
        dist       = target_info.get('ระยะห่างเฉลี่ย', target_info.get('Total_Dist', '—'))
        speed      = target_info.get('Speed_Warp', '—')

        cars_display = '\n'.join(f"  - `{c}`" for c in cars) if cars else '  - ไม่ระบุ'

        summary_md = f"""
**🚗 รายการยานพาหนะในกลุ่ม:**
{cars_display}

**📷 จำนวนด่านที่ผ่าน:** {n_cams}

**📍 จุดตรวจล่าสุด:** {last_cam}

**🕐 เวลาล่าสุด:** {last_time} น.

**📏 ระยะทาง:** {dist}

**💨 ความเร็วผิดปกติ:** {speed}
"""
        if is_convoy:
            summary_md += f"\n\n---\n**🚘 บทวิเคราะห์ขบวนรถ (AI Insight):**\nขบวนรถ {len(cars)} คัน ผ่านด่าน **{n_cams}** จุด โดยมีพฤติกรรม: {behav}"
        elif is_clone:
            summary_md += f"\n\n---\n**🚨 บทวิเคราะห์สวมทะเบียน (AI Insight):**\n{behav}"

        st.markdown("<div class='dossier-summary'>", unsafe_allow_html=True)
        st.markdown("#### 📋 สรุปข้อมูลประวัติเป้าหมาย (Intelligence Summary)")
        st.markdown(summary_md)
        st.markdown("</div>", unsafe_allow_html=True)

    # ── ข้อมูลโดยละเอียดทุกคอลัมน์ ──
    st.markdown("---")
    with st.expander("📄 ดูข้อมูลทั้งหมดของเป้าหมายนี้", expanded=False):
        row_dict = {k: v for k, v in target_info.items()
                    if k not in ('Radar_Data', 'Cars_List') and pd.notna(v) and v != ''}
        for k, v in row_dict.items():
            st.markdown(f"**{k}:** `{v}`")

    excel_download_button(
        pd.DataFrame([target_info.to_dict()]).drop(columns=['Radar_Data'], errors='ignore'),
        f"evidence_{selected_target}.xlsx", "📥 Export ข้อมูลเป้าหมาย (Excel)"
    )

# ══ Clickable Table (เหมือน app.py) ══════════════════════════════════════════
def show_clickable_table_cloud(df_display: pd.DataFrame, table_key: str, priority_df: pd.DataFrame):
    if df_display.empty:
        st.info("🟢 ไม่พบเป้าหมายที่อยู่ในเกณฑ์เฝ้าระวัง")
        return

    df_clean = df_display.copy()
    df_clean['สถานะ']     = "🔴 เฝ้าระวัง"
    df_clean['Risk Score'] = df_clean['Risk Score'].fillna(0).astype(int).astype(str) + "%"

    # เลือก column ตาม type
    if 'Speed_Warp' in df_clean.columns and 'สวมทะเบียน' in str(df_clean.get('ประเภท', '')):
        cols_order = ['สถานะ', 'เป้าหมาย', 'Speed_Warp', 'เวลาโผล่ล่าสุด', 'จุดตรวจพบล่าสุด', 'พฤติกรรมต้องสงสัย', 'Risk Score']
    else:
        cols_order = ['สถานะ', 'เป้าหมาย', 'ผ่านร่วมกัน (ด่าน)', 'ระยะห่างเฉลี่ย', 'จุดตรวจพบล่าสุด', 'พฤติกรรมต้องสงสัย', 'Risk Score']

    avail_cols = [c for c in cols_order if c in df_clean.columns]
    df_show    = df_clean[avail_cols].copy()

    event = st.dataframe(
        df_show.style.map(color_score, subset=['Risk Score']),
        use_container_width=True, on_select="rerun",
        selection_mode="single-row", hide_index=True,
        key=f"tbl_{table_key}"
    )
    excel_download_button(df_show, f"priority_{table_key}.xlsx", "📥 Export ตารางนี้ (Excel)")

    if len(event.selection.rows) > 0:
        selected_idx = event.selection.rows[0]
        target_id    = df_display.iloc[selected_idx]['Target_ID']
        render_case_dossier_cloud(target_id, priority_df)

# ══ Sidebar ════════════════════════════════════════════════════════════════════
st.sidebar.markdown("""
<div style='text-align:center;padding:14px 0 8px'>
  <div style='font-size:40px'>🛡️</div>
  <div style='font-size:16px;font-weight:800;color:#93c5fd;letter-spacing:2px'>HWPD 60 i-Trap</div>
  <div style='font-size:11px;color:#64748b;margin-top:3px'>Intelligence Command System</div>
  <div style='font-size:11px;color:#10b981;margin-top:4px'>☁️ Cloud View — Live Data</div>
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
st.sidebar.markdown("### 🧭 เมนูหลัก")

available_dates = pull_available_dates()
selected_date = st.sidebar.selectbox(
    "📅 เลือกวันที่รายงาน:", available_dates,
    format_func=lambda d: f"📅 {d}"
) if available_dates else None

st.sidebar.markdown("---")
if st.sidebar.button("🔄 รีเฟรชข้อมูล", use_container_width=True):
    pull_available_dates.clear(); pull_daily_report.clear()
    pull_realtime.clear(); pull_suspects.clear(); pull_upload_log.clear()
    st.rerun()

if has_role('super_admin','admin'):
    with st.sidebar.expander("📋 ประวัติอัปโหลด"):
        log_df = pull_upload_log(8)
        if not log_df.empty:
            for _, r in log_df.iterrows():
                ts = str(r.get('uploaded_at',''))[:16].replace('T',' ')
                st.markdown(
                    f"<div style='font-size:12px;padding:4px 0;border-bottom:1px solid rgba(255,255,255,.06)'>"
                    f"<b style='color:#60a5fa'>{r.get('display_name') or r.get('username','?')}</b><br>"
                    f"📅 {r.get('report_date','?')} | {ts}<br>"
                    f"<span style='color:#64748b'>{int(r.get('record_count',0)):,} records</span></div>",
                    unsafe_allow_html=True)

# ══ Main UI ════════════════════════════════════════════════════════════════════
# Logo
import os as _os
_logo = _os.path.join(_os.path.dirname(__file__), 'logo.jpeg')
if _os.path.exists(_logo):
    st.image(_logo, use_container_width=True)

st.markdown("""
<div class='main-title'>🛡️ HWPD 60 Intelligence Target &amp; Trap</div>
<div class='main-subtitle'>ศูนย์ปฏิบัติการข่าวกรองสกัดกั้นบนสายทาง &nbsp;|&nbsp; HWPD 60 i-Trap Command Center</div>
<hr class='header-divider'>
""", unsafe_allow_html=True)

if not available_dates:
    st.info("📭 ยังไม่มีรายงานในระบบ กรุณาให้ Admin ทำการอัปโหลดและประมวลผลข้อมูลก่อนครับ")
    st.stop()

# Ticker
st.markdown("""<div class='ticker-wrap'><div class='ticker-content'>
  📡 SYSTEM ONLINE | SECURE CONNECTION ESTABLISHED | HWPD 60 COMMAND CENTER ACTIVE...
</div></div>""", unsafe_allow_html=True)

col_t1, col_t2 = st.columns([8, 2])
with col_t2:
    selected_date = st.selectbox("📅 เลือกวันที่รายงาน:", available_dates, key="main_date")
with col_t1:
    st.markdown(
        f"<div style='padding:10px;background:#f8fafc;border-left:5px solid #10b981;"
        f"border-radius:5px;color:#0f172a'>"
        f"<span class='live-dot'></span><b>Live Sync: Active</b> | "
        f"กำลังแสดงผลรายงานข่าวกรองประจำวันที่: <b>{selected_date}</b></div>",
        unsafe_allow_html=True)

# Load data from Supabase
report      = pull_daily_report(selected_date)
priority_df = report.get('priority_df', pd.DataFrame())
rec_count   = report.get('record_count', 0)
uploader    = report.get('uploaded_by', 'ไม่ระบุ')

today_str  = datetime.now().strftime('%Y-%m-%d')
rt_data    = pull_realtime(today_str) if selected_date == today_str else None

if priority_df.empty:
    st.info(f"📭 ยังไม่มีผลวิเคราะห์สำหรับวันที่ {selected_date}")
    st.stop()

# ── ข้อมูลสรุปเป้าหมายสำคัญ ──────────────────────────────────────────────────
st.markdown("## 📊 ข้อมูลสรุปเป้าหมายสำคัญ (Intelligence Brief)")

tab_rt, tab_daily, tab_repeat = st.tabs([
    "⚡ Realtime (วันนี้)",
    f"📅 ประจำวัน ({selected_date})",
    "🔁 รถวิ่งซ้ำ (30 วัน)"
])

# ── TAB REALTIME ──────────────────────────────────────────────────────────────
with tab_rt:
    if selected_date != today_str:
        st.info(f"Realtime ใช้ได้เฉพาะวันที่ {today_str} — เลือกวันนี้ใน sidebar")
    elif rt_data is None:
        st.markdown(f"""
        <div style='background:rgba(245,158,11,.08);border-left:4px solid #f59e0b;
            padding:16px;border-radius:10px'>
          <span class='live-dot'></span>
          <b style='color:#fbbf24'>Live Sync: Standby</b> | กำลังแสดงผลรายงานข่าวกรองประจำวันที่: <b>{selected_date}</b>
          <br><br>ยังไม่มีข้อมูล Realtime วันนี้ — รอ Admin อัปโหลดข้อมูลกะแรกของวัน
        </div>""", unsafe_allow_html=True)
    else:
        rt_priority = rt_data.get('priority_df', pd.DataFrame())
        cr1,cr2,cr3 = st.columns(3)
        ft = str(rt_data.get('first_time',''))[:5]
        lt = str(rt_data.get('last_time',''))[:5]
        with cr1: st.metric("⚡ บันทึกวันนี้",   f"{rt_data.get('record_count',0):,}")
        with cr2: st.metric("🕐 ช่วงเวลา",       f"{ft}–{lt} น.")
        with cr3: st.metric("🎯 เป้าหมายพบ",     str(len(rt_priority)) if not rt_priority.empty else "0")
        st.markdown("---")
        if not rt_priority.empty:
            st.markdown(f"#### 🎯 รถเป้าหมาย Realtime ({len(rt_priority)} คัน)")
            show_clickable_table_cloud(rt_priority, "rt", rt_priority)
        else:
            st.success("✅ ยังไม่พบรถต้องสงสัยในช่วงนี้")

# ── TAB DAILY ─────────────────────────────────────────────────────────────────
with tab_daily:
    n_total   = len(priority_df)
    n_convoy  = int(priority_df['ประเภท'].str.contains('ขบวน', na=False).sum()) if 'ประเภท' in priority_df.columns else 0
    n_clone   = int(priority_df['ประเภท'].str.contains('สวมทะเบียน', na=False).sum()) if 'ประเภท' in priority_df.columns else 0
    n_others  = n_total - n_convoy - n_clone

    c1,c2,c3,c4,c5 = st.columns(5)
    with c1: st.metric("🚗 บันทึกทั้งหมด",  f"{rec_count:,}")
    with c2: st.metric("🎯 รถเป้าหมาย",     f"{n_total}")
    with c3: st.metric("🚘 ขบวนรถ",         f"{n_convoy}")
    with c4: st.metric("🎭 สวมทะเบียน",     f"{n_clone}")
    with c5: st.metric("🔍 อื่นๆ",           f"{n_others}")

    st.caption(f"📤 อัปโหลดโดย: **{uploader}** | 📊 ข้อมูล {rec_count:,} รายการ | วันที่ {selected_date}")
    st.markdown("---")

    # Sub-tabs ตาม engine type (เหมือน app.py)
    sub_tabs = st.tabs(["🎯 ทั้งหมด", "🚘 ขบวนรถ", "🎭 สวมทะเบียน", "🔍 พฤติกรรมต้องสงสัย"])

    with sub_tabs[0]:
        st.markdown(f"#### 🎯 เป้าหมายทั้งหมด ({n_total} คัน)")
        show_clickable_table_cloud(priority_df, "all", priority_df)

    with sub_tabs[1]:
        if 'ประเภท' in priority_df.columns:
            convoy_df = priority_df[priority_df['ประเภท'].str.contains('ขบวน', na=False)]
        else:
            convoy_df = pd.DataFrame()
        st.markdown(f"#### 🚘 รถขบวน ({len(convoy_df)} คัน)")
        show_clickable_table_cloud(convoy_df, "convoy", priority_df)

    with sub_tabs[2]:
        if 'ประเภท' in priority_df.columns:
            clone_df = priority_df[priority_df['ประเภท'].str.contains('สวมทะเบียน', na=False)]
        else:
            clone_df = pd.DataFrame()
        st.markdown(f"#### 🎭 รถสวมทะเบียน ({len(clone_df)} คัน)")
        show_clickable_table_cloud(clone_df, "clone", priority_df)

    with sub_tabs[3]:
        if 'ประเภท' in priority_df.columns:
            other_df = priority_df[~priority_df['ประเภท'].str.contains('ขบวน|สวมทะเบียน', na=False)]
        else:
            other_df = priority_df
        st.markdown(f"#### 🔍 รถพฤติกรรมต้องสงสัย ({len(other_df)} คัน)")
        show_clickable_table_cloud(other_df, "others", priority_df)

# ── TAB REPEAT OFFENDERS ──────────────────────────────────────────────────────
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
        excel_download_button(suspect_df[avail].rename(columns=col_map),
                              "repeat_offenders.xlsx", "📥 Export รายชื่อรถวิ่งซ้ำ")
