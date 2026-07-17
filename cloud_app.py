"""
cloud_app.py — HWPD i-Trap Cloud Viewer
แสดงผลจาก Supabase สำหรับลูกน้องดูออนไลน์ 24/7
ไม่มีการคำนวณ ไม่มีการ Upload — อ่านผลอย่างเดียว
"""
import streamlit as st
import pandas as pd
from datetime import datetime

# ─── Page Config ──────────────────────────────────────────────────────────────
st.set_page_config(
    page_title="HWPD 60 i-Trap | Intelligence View",
    page_icon="🛡️",
    layout="wide",
    initial_sidebar_state="expanded"
)

# ─── CSS ──────────────────────────────────────────────────────────────────────
st.markdown("""
<style>
@import url('https://fonts.googleapis.com/css2?family=Sarabun:wght@300;400;500;600;700;800&display=swap');
html, body, .stApp, [class*="css"] {
    font-family: 'Sarabun', 'TH Sarabun PSK', 'TH Sarabun New', sans-serif !important;
    font-size: 16px !important;
}
html, body { background: #0a0e1a !important; }
.stApp { background: linear-gradient(135deg, #0a0e1a 0%, #0d1321 50%, #0a1628 100%) !important; }
.block-container { padding-top: 2rem !important; padding-left: 2rem !important;
    padding-right: 2rem !important; max-width: 100% !important; }
section[data-testid="stSidebar"] {
    background: linear-gradient(180deg, #0d1321 0%, #0f172a 100%) !important;
    border-right: 1px solid rgba(59,130,246,0.15) !important;
}
[data-testid="stMetricValue"] { font-size:28px !important; font-weight:800 !important; color:#e2e8f0 !important; }
[data-testid="stMetricLabel"] { font-size:13px !important; color:#94a3b8 !important; }
</style>
""", unsafe_allow_html=True)

# ─── Auth + Sync Modules ──────────────────────────────────────────────────────
from auth import require_login, get_current_user, has_role, logout, ROLE_LABEL
from supabase_sync import (
    pull_available_dates, pull_daily_report, pull_realtime,
    pull_suspects, pull_upload_log,
)

# ─── Login Guard ──────────────────────────────────────────────────────────────
require_login()

# ─── Helper: Priority Table (ต้องนิยามก่อนเรียกใช้) ─────────────────────────
RISK_COLOR = {
    'วิกฤต':    '#ef4444',
    'สูง':      '#f97316',
    'ปานกลาง': '#eab308',
    'ต่ำ':      '#22c55e',
}

def show_priority_table(df: pd.DataFrame, table_key: str = "tbl"):
    """แสดงตารางเป้าหมายแบบ card"""
    if df.empty:
        st.info("ไม่พบรายการเป้าหมาย")
        return

    max_n  = min(200, len(df))
    show_n = st.slider("แสดง (คัน):", 10, max_n, min(50, max_n), key=f"slider_{table_key}")
    df_show = df.head(show_n)

    for _, row in df_show.iterrows():
        plate    = row.get('ทะเบียนรถ') or row.get('plate', '—')
        province = row.get('จังหวัด')   or row.get('province', '')
        risk     = row.get('ระดับความเสี่ยง') or row.get('risk_level', '—')
        eng_type = row.get('ประเภท')    or row.get('engine_type', '—')
        score    = row.get('คะแนนรวม') or row.get('total_score', 0)
        color    = RISK_COLOR.get(str(risk), '#64748b')

        st.markdown(f"""
        <div style='background:rgba(15,23,42,0.7);border-left:4px solid {color};
            padding:12px 16px;border-radius:8px;margin-bottom:8px;'>
            <div style='display:flex;justify-content:space-between;align-items:center;'>
                <div>
                    <span style='font-size:16px;font-weight:700;color:#e2e8f0;'>🚗 {plate}</span>
                    <span style='font-size:13px;color:#94a3b8;margin-left:8px;'>{province}</span>
                </div>
                <div style='text-align:right;'>
                    <span style='background:{color}22;color:{color};border:1px solid {color}44;
                        padding:2px 10px;border-radius:12px;font-size:12px;font-weight:600;'>{risk}</span>
                    <span style='color:#64748b;font-size:12px;margin-left:8px;'>คะแนน {score}</span>
                </div>
            </div>
            <div style='font-size:12px;color:#64748b;margin-top:4px;'>📋 {eng_type}</div>
        </div>
        """, unsafe_allow_html=True)

    if len(df) > show_n:
        st.caption(f"... และอีก {len(df)-show_n} รายการ (เลื่อน slider เพื่อดูเพิ่ม)")


# ─── Sidebar ──────────────────────────────────────────────────────────────────
st.sidebar.markdown("""
<div style='text-align:center; padding:14px 0 8px 0;'>
    <div style='font-size:40px;'>🛡️</div>
    <div style='font-size:16px; font-weight:800; color:#93c5fd; letter-spacing:2px;'>HWPD 60 i-Trap</div>
    <div style='font-size:12px; color:#64748b; margin-top:4px;'>Intelligence Command System</div>
    <div style='font-size:11px; color:#10b981; margin-top:6px;'>☁️ Cloud View — Live Data</div>
</div>
<hr style='border-color:rgba(59,130,246,0.2); margin:8px 0;'>
""", unsafe_allow_html=True)

# User info
_cu = get_current_user()
if _cu:
    _rl = ROLE_LABEL.get(_cu.get('role', ''), _cu.get('role', ''))
    st.sidebar.markdown(
        f"<div style='background:rgba(99,102,241,0.12);padding:8px 12px;border-radius:8px;margin-bottom:8px;'>"
        f"<span style='font-size:12px;color:#94a3b8;'>ผู้ใช้งาน</span><br>"
        f"<span style='font-size:14px;font-weight:700;color:#e2e8f0;'>{_cu.get('display_name', _cu.get('username',''))}</span><br>"
        f"<span style='font-size:11px;color:#818cf8;'>{_rl}</span>"
        f"</div>", unsafe_allow_html=True
    )
    if st.sidebar.button("🔓 ออกจากระบบ", use_container_width=True):
        logout()
        st.rerun()

st.sidebar.markdown("---")

# Date Picker
st.sidebar.markdown("### 📅 เลือกวันที่")
available_dates = pull_available_dates()

if available_dates:
    selected_date = st.sidebar.selectbox(
        "วันที่รายงาน:",
        available_dates,
        format_func=lambda d: f"📅 {d}"
    )
else:
    st.sidebar.warning("ยังไม่มีข้อมูลใน Cloud")
    selected_date = None

st.sidebar.markdown("---")

if st.sidebar.button("🔄 รีเฟรชข้อมูล", use_container_width=True):
    pull_available_dates.clear()
    pull_daily_report.clear()
    pull_realtime.clear()
    pull_suspects.clear()
    pull_upload_log.clear()
    st.rerun()

# Upload log (admin ขึ้นไปเท่านั้น)
if has_role('super_admin', 'admin'):
    st.sidebar.markdown("### 📋 อัปโหลดล่าสุด")
    log_df = pull_upload_log(10)
    if not log_df.empty:
        for _, row in log_df.iterrows():
            ts    = str(row.get('uploaded_at', ''))[:16].replace('T', ' ')
            uname = row.get('display_name') or row.get('username', '?')
            rdate = row.get('report_date', '?')
            cnt   = row.get('record_count', 0)
            st.sidebar.markdown(
                f"<div style='background:rgba(15,23,42,0.6);padding:6px 10px;border-radius:6px;"
                f"margin-bottom:4px;font-size:12px;'>"
                f"<span style='color:#60a5fa;font-weight:600;'>{uname}</span><br>"
                f"📅 {rdate} | 🕐 {ts}<br>"
                f"<span style='color:#64748b;'>{cnt:,} records</span>"
                f"</div>", unsafe_allow_html=True
            )
    else:
        st.sidebar.caption("ยังไม่มีประวัติ")

# ─── Header ───────────────────────────────────────────────────────────────────
st.markdown("""
<div style='text-align:center; padding:20px 0 10px 0;'>
    <div style='font-size:26px; font-weight:800; color:#e2e8f0; margin-bottom:4px;'>
        🛡️ HWPD 60 Intelligence Target & Trap
    </div>
    <div style='font-size:13px; color:#64748b;'>
        ศูนย์ปฏิบัติการข่าวกรองสกัดกั้นยาเสพติดชายแดน | Cloud Intelligence View
    </div>
</div>
<hr style='border-color:rgba(59,130,246,0.15); margin-bottom:16px;'>
""", unsafe_allow_html=True)

# ─── No data guard ────────────────────────────────────────────────────────────
if not selected_date:
    st.info("⏳ ยังไม่มีข้อมูลใน Cloud — รอให้ Admin อัปโหลดข้อมูลก่อนครับ")
    st.stop()

# ─── Load data ────────────────────────────────────────────────────────────────
report     = pull_daily_report(selected_date)
priority_df = report.get('priority_df', pd.DataFrame())
rec_count  = report.get('record_count', 0)
uploader   = report.get('uploaded_by', 'ไม่ระบุ')

today_str  = datetime.now().strftime('%Y-%m-%d')
rt_data    = pull_realtime(today_str) if selected_date == today_str else None

# ─── Metrics ──────────────────────────────────────────────────────────────────
st.markdown(f"### 📊 ภาพรวม — วันที่ {selected_date}")

n_targets  = len(priority_df) if not priority_df.empty else 0
n_critical = 0
n_high     = 0
if not priority_df.empty and 'ระดับความเสี่ยง' in priority_df.columns:
    n_critical = int((priority_df['ระดับความเสี่ยง'] == 'วิกฤต').sum())
    n_high     = int((priority_df['ระดับความเสี่ยง'] == 'สูง').sum())
n_rt = rt_data.get('record_count', 0) if rt_data else 0

c1, c2, c3, c4, c5 = st.columns(5)
with c1: st.metric("🚗 บันทึกทั้งหมด", f"{rec_count:,}")
with c2: st.metric("🎯 รถเป้าหมาย",     f"{n_targets:,}")
with c3: st.metric("🔴 วิกฤต",          f"{n_critical:,}")
with c4: st.metric("🟠 สูง",            f"{n_high:,}")
with c5: st.metric("⚡ Realtime วันนี้", f"{n_rt:,}" if rt_data else "—")

st.markdown("---")

# ─── Tabs ─────────────────────────────────────────────────────────────────────
tab_rt, tab_daily, tab_suspect = st.tabs([
    "⚡ Realtime (วันนี้)",
    f"📅 ประจำวัน ({selected_date})",
    "🔁 รถวิ่งซ้ำ (Repeat Offenders)"
])

# ══ TAB 1: REALTIME ═══════════════════════════════════════════════════════════
with tab_rt:
    if selected_date != today_str:
        st.info(f"⚠️ Realtime ใช้ได้เฉพาะวันปัจจุบัน ({today_str})\nกรุณาเลือกวันที่ {today_str} ในเมนูซ้าย")
    elif rt_data is None:
        st.markdown("""
        <div style='background:rgba(245,158,11,0.1);border-left:4px solid #f59e0b;
            padding:24px;border-radius:12px;margin:16px 0;'>
            <div style='font-size:28px;margin-bottom:8px;'>⏳</div>
            <div style='font-size:18px;font-weight:700;color:#fbbf24;'>ยังไม่มีข้อมูล Realtime วันนี้</div>
            <div style='font-size:14px;color:#94a3b8;margin-top:8px;'>
                รอให้ Admin อัปโหลดข้อมูลกะแรกของวันครับ — หน้านี้จะอัปเดตอัตโนมัติ
            </div>
        </div>
        """, unsafe_allow_html=True)
    else:
        rt_priority = rt_data.get('priority_df', pd.DataFrame())
        cr1, cr2, cr3 = st.columns(3)
        with cr1: st.metric("⚡ Records วันนี้", f"{rt_data.get('record_count', 0):,}")
        with cr2:
            ft = str(rt_data.get('first_time', ''))[:5]
            lt = str(rt_data.get('last_time', ''))[:5]
            st.metric("🕐 ช่วงเวลา", f"{ft} – {lt}")
        with cr3: st.metric("📤 Upload ครั้งที่", f"{rt_data.get('upload_count', 1)}")

        if not rt_priority.empty:
            st.markdown(f"#### 🎯 รถเป้าหมาย Realtime ({len(rt_priority)} คัน)")
            show_priority_table(rt_priority, "rt")
        else:
            st.success("✅ ยังไม่พบรถต้องสงสัยในช่วงนี้")

# ══ TAB 2: DAILY ══════════════════════════════════════════════════════════════
with tab_daily:
    if priority_df.empty:
        st.info(f"ยังไม่มีผลวิเคราะห์สำหรับวันที่ {selected_date}")
    else:
        st.markdown(f"#### 🎯 รายชื่อรถเป้าหมาย — วันที่ {selected_date} ({len(priority_df)} คัน)")
        st.caption(f"📤 อัปโหลดโดย: **{uploader}** | 📊 จากข้อมูล **{rec_count:,}** รายการ")
        show_priority_table(priority_df, "daily")

# ══ TAB 3: REPEAT OFFENDERS ═══════════════════════════════════════════════════
with tab_suspect:
    suspect_df = pull_suspects(200)
    if suspect_df.empty:
        st.info("ยังไม่มีข้อมูลรถวิ่งซ้ำ")
    else:
        st.markdown(f"#### 🔁 รถที่ปรากฏซ้ำในระบบ ({len(suspect_df)} คัน)")
        col_map = {
            'plate':        'ทะเบียน',
            'seen_count':   'จำนวนครั้ง',
            'last_seen':    'พบล่าสุด',
            'engine_types': 'ประเภทภัยคุกคาม',
            'risk_score':   'คะแนนความเสี่ยง'
        }
        avail_cols = [c for c in col_map if c in suspect_df.columns]
        st.dataframe(
            suspect_df[avail_cols].rename(columns=col_map),
            use_container_width=True,
            hide_index=True
        )
