# -*- coding: utf-8 -*-
import os, datetime
import pandas as pd
import streamlit as st
import plotly.graph_objects as go
import streamlit.components.v1 as components

from utils.data_processor import preprocess_vehicle_data
from utils.engines import run_fused_engines, get_2d_hideout_estimates
from utils.map_builder import create_master_map, get_map_html_with_select_all
from utils.predictor import predict_next_checkpoints
from utils.osrm_eta import format_minutes_to_hm

# ── Shared PostgreSQL Watchlist (Oracle 129.150.56.185) ────────────────────────
_PG_CFG = {
    "host": os.environ.get("ITRAP_PG_HOST", "129.150.56.185"),
    "port": int(os.environ.get("ITRAP_PG_PORT", 5432)),
    "dbname": os.environ.get("ITRAP_PG_DB", "itrap_db"),
    "user": os.environ.get("ITRAP_PG_USER", "itrap_admin"),
    "password": os.environ.get("ITRAP_PG_PASS", "Hwpd@iTrap2026!Secure"),
    "connect_timeout": 3,
}

def _pg_conn():
    """Return psycopg2 connection to shared Oracle PG, or None on failure."""
    try:
        import psycopg2
        return psycopg2.connect(**_PG_CFG)
    except Exception:
        return None

def _wl_load():
    """Load watchlist from PostgreSQL. Returns list of (plate, added_at_str)."""
    conn = _pg_conn()
    if conn is None:
        return []
    try:
        cur = conn.cursor()
        cur.execute(
            "SELECT plate, to_char(added_at AT TIME ZONE 'Asia/Bangkok', 'HH24:MI') "
            "FROM watchlist WHERE is_active = TRUE ORDER BY added_at DESC;"
        )
        rows = cur.fetchall()
        conn.close()
        return [(r[0], r[1]) for r in rows]
    except Exception:
        conn.close()
        return []

def _wl_add(plate: str, reason: str = "", risk_score: int = 0,
            province: str = "", seen_count: int = 0,
            last_checkpoint: str = "", last_seen_time: str = "",
            behavior_type: str = "", lat: float = None, lon: float = None,
            verdict: str = "", convoy_members: list = None, convoy_role: str = "single"):
    """Insert plate into shared PostgreSQL watchlist with full case metadata."""
    conn = _pg_conn()
    if conn is None:
        return False
    try:
        import json as _json
        cur = conn.cursor()
        cur.execute(
            """INSERT INTO watchlist
               (plate, reason, risk_score, added_by,
                province, seen_count, last_checkpoint, last_seen_time,
                behavior_type, lat, lon, verdict, convoy_members, convoy_role)
               VALUES (%s,%s,%s,'i-Trap Analysis',%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
               ON CONFLICT (plate) DO UPDATE SET
                 reason=EXCLUDED.reason, risk_score=EXCLUDED.risk_score,
                 province=EXCLUDED.province, seen_count=EXCLUDED.seen_count,
                 last_checkpoint=EXCLUDED.last_checkpoint,
                 last_seen_time=EXCLUDED.last_seen_time,
                 behavior_type=EXCLUDED.behavior_type,
                 lat=EXCLUDED.lat, lon=EXCLUDED.lon,
                 verdict=EXCLUDED.verdict,
                 convoy_members=EXCLUDED.convoy_members,
                 convoy_role=EXCLUDED.convoy_role,
                 is_active=TRUE, added_at=NOW();""",
            (plate, reason[:500], risk_score,
             province, seen_count, last_checkpoint, last_seen_time,
             behavior_type, lat, lon, verdict[:500] if verdict else "",
             _json.dumps(convoy_members or [], ensure_ascii=False), convoy_role)
        )
        conn.commit()
        conn.close()
        return True
    except Exception as e:
        try: conn.close()
        except: pass
        return False


def _wl_remove(plate: str):
    """Soft-delete plate from shared PostgreSQL watchlist."""
    conn = _pg_conn()
    if conn is None:
        return False
    try:
        cur = conn.cursor()
        cur.execute("UPDATE watchlist SET is_active=FALSE WHERE plate=%s;", (plate,))
        conn.commit()
        conn.close()
        return True
    except Exception:
        conn.close()
        return False

_VER = "3.0.0"

import base64
_APP_DIR = os.path.dirname(os.path.abspath(__file__))
_LOGO_CANDIDATES = [
    os.path.join(_APP_DIR, "logo.jpeg"),
    os.path.join(_APP_DIR, "logo.jpg"),
    os.path.join(_APP_DIR, "logo.png"),
    "D:/itrap_agent/logo.jpeg",
    "D:/itrap_agent/logo.jpg",
]
_LOGO_PATH = next((p for p in _LOGO_CANDIDATES if os.path.exists(p)), None)
if _LOGO_PATH:
    with open(_LOGO_PATH, "rb") as _f:
        _ext = "png" if _LOGO_PATH.endswith(".png") else "jpeg"
        LOGO_SRC = f"data:image/{_ext};base64,{base64.b64encode(_f.read()).decode('utf-8')}"
else:
    LOGO_SRC = ""

# ── Cache ──────────────────────────────────────────────────────────────────────
@st.cache_data(show_spinner=False)
def _cached_preprocess(file_bytes_list, file_names):
    import io
    frames = []
    for name, data in zip(file_names, file_bytes_list):
        try:
            buf = io.BytesIO(data)
            frames.append(pd.read_csv(buf) if name.endswith('.csv') else pd.read_excel(buf))
        except Exception:
            pass
    if not frames:
        return pd.DataFrame(), {}, {}, {}
    master = preprocess_vehicle_data(pd.concat(frames, ignore_index=True))
    c, cv, s = run_fused_engines(master, 10)
    return master, c, cv, s

@st.cache_data(show_spinner=False, max_entries=30)
def _cached_map(case_id, _df, leader, follower, ghost=False, dates=None):
    m = create_master_map(_df, leader_plate=leader, follower_plate=follower,
                          is_ghost_case=ghost, convoy_dates=dates)
    return get_map_html_with_select_all(m)

# ── Page Config ────────────────────────────────────────────────────────────────
st.set_page_config(
    page_title="i-Trap Analysis | ระบบวิเคราะห์ข่าวกรองยานพาหนะ",
    page_icon="&#128680;", layout="wide", initial_sidebar_state="expanded"
)

# ── CSS (single clean block) ───────────────────────────────────────────────────
_CSS = (
    "<link rel='preconnect' href='https://fonts.googleapis.com'>"
    "<link href='https://fonts.googleapis.com/css2?family=Sarabun:wght@400;600;700;800&display=swap' rel='stylesheet'>"
    "<style>"
    "html,body,.stApp,[class*='st-'],p,div,label{font-family:'Sarabun','TH Sarabun New',sans-serif!important;font-size:14px!important;line-height:1.65!important;color:#e2e8f0!important;}"
    "h1{font-size:22px!important;}h2{font-size:20px!important;}h3{font-size:18px!important;}h4{font-size:16px!important;}h5{font-size:15px!important;font-weight:700;}"
    ".stApp{background:#0f1117!important;color:#e2e8f0!important;}"
    ".stAppHeader{background:#0f1117!important;border-bottom:1px solid #1e293b;}"
    "[data-testid='stSidebar']{background:linear-gradient(180deg,#111827,#0f172a)!important;border-right:1px solid #1e293b!important;}"
    "[data-testid='stSidebar'] *{color:#cbd5e1!important;font-size:13px!important;}"
    ".sb-title{font-size:10px!important;font-weight:700;letter-spacing:.1em;text-transform:uppercase;color:#475569!important;padding:14px 0 5px;border-top:1px solid #1e293b;margin-top:6px;display:block;}"
    ".top-hdr{background:linear-gradient(135deg,#0f172a,#1e1b4b,#0f172a);border:1px solid #312e81;border-radius:14px;padding:20px 28px;margin-bottom:18px;display:flex;justify-content:space-between;align-items:center;}"
    ".hdr-left{flex:1;}"
    ".hdr-title{font-size:22px!important;font-weight:800;color:#f1f5f9;margin:0;line-height:1.2!important;}"
    ".hdr-sub{font-size:12px!important;color:#94a3b8;margin-top:5px;}"
    ".hdr-status{display:inline-flex;align-items:center;gap:6px;background:rgba(16,185,129,.12);border:1px solid rgba(16,185,129,.3);border-radius:20px;padding:4px 12px;font-size:11px!important;color:#6ee7b7;font-weight:600;margin-top:6px;}"
    ".sdot{width:7px;height:7px;border-radius:50%;background:#10b981;box-shadow:0 0 6px #10b981;flex-shrink:0;animation:pulse 2s infinite;}"
    "@keyframes pulse{0%,100%{opacity:1}50%{opacity:.4}}"
    ".hdr-badge{background:rgba(99,102,241,.15);border:1px solid rgba(99,102,241,.4);border-radius:10px;padding:10px 16px;text-align:right;flex-shrink:0;min-width:130px;}"
    ".hdr-badge .ver{font-size:10px!important;color:#818cf8;font-weight:700;}"
    ".hdr-badge .ts{font-size:11px!important;color:#64748b;margin-top:3px;}"
    ".mgrid{display:grid;grid-template-columns:repeat(4,1fr);gap:14px;margin-bottom:18px;}"
    ".mc{background:#1e293b!important;border:1px solid #334155;border-radius:12px;padding:18px 20px;position:relative;overflow:hidden;transition:transform .2s;}"
    ".mc:hover{transform:translateY(-2px);box-shadow:0 8px 24px rgba(0,0,0,.3);}"
    ".mc::after{content:'';position:absolute;top:0;left:0;right:0;height:3px;border-radius:12px 12px 0 0;}"
    ".mc.r::after{background:linear-gradient(90deg,#dc2626,#ef4444);}"
    ".mc.a::after{background:linear-gradient(90deg,#d97706,#f59e0b);}"
    ".mc.b::after{background:linear-gradient(90deg,#2563eb,#60a5fa);}"
    ".mc.p::after{background:linear-gradient(90deg,#7c3aed,#a78bfa);}"
    ".mlbl{font-size:10px!important;color:#94a3b8;font-weight:700;text-transform:uppercase;letter-spacing:.05em;margin:0 0 8px;}"
    ".mval{font-size:28px!important;font-weight:800;margin:0;line-height:1!important;}"
    ".mval.r{color:#f87171;}.mval.a{color:#fbbf24;}.mval.b{color:#60a5fa;}.mval.p{color:#a78bfa;}"
    ".msub{font-size:11px!important;color:#94a3b8;margin-top:4px;}"
    ".stTabs [data-baseweb='tab-list']{gap:4px;border-bottom:1px solid #1e293b;background:transparent!important;}"
    ".stTabs [data-baseweb='tab']{height:44px;background:#1e293b!important;border-radius:10px 10px 0 0;padding:0 20px;font-weight:600!important;font-size:13px!important;color:#cbd5e1!important;border:1px solid #334155!important;border-bottom:none!important;}"
    ".stTabs [aria-selected='true']{background:linear-gradient(135deg,#1d4ed8,#4f46e5)!important;color:#ffffff!important;border-color:#4f46e5!important;}.stTabs [aria-selected='true'] *{color:#ffffff!important;}.stTabs [aria-selected='false'] p,.stTabs [aria-selected='false'] span{color:#cbd5e1!important;}"
    ".stTabs [data-baseweb='tab'] p,.stTabs [data-baseweb='tab'] span{color:inherit!important;font-size:13px!important;}"
    ".stTabs [data-baseweb='tab-panel']{background:#0f1117;border:1px solid #1e293b;border-radius:0 12px 12px 12px;padding:20px;}"
    ".vcard{border-radius:12px;padding:18px 22px;margin-bottom:16px;border-left:5px solid;}"
    ".vcard.crit{background:rgba(220,38,38,.08);border-color:#dc2626;}"
    ".vcard.high{background:rgba(217,119,6,.08);border-color:#d97706;}"
    ".vcard.med{background:rgba(37,99,235,.08);border-color:#2563eb;}"
    ".vhdr{display:flex;justify-content:space-between;align-items:flex-start;gap:12px;flex-wrap:wrap;}"
    ".vtitle{font-size:15px!important;font-weight:700;color:#f1f5f9;margin:0;flex:1;}"
    ".rbadge{flex-shrink:0;padding:5px 14px;border-radius:20px;font-weight:800;font-size:13px!important;white-space:nowrap;}"
    ".rbadge.crit{background:#dc2626;color:#fff;}.rbadge.high{background:#d97706;color:#fff;}.rbadge.med{background:#2563eb;color:#fff;}"
    ".apexb{display:inline-block;background:linear-gradient(135deg,#7c3aed,#dc2626);color:#fff;padding:3px 12px;border-radius:20px;font-size:10px!important;font-weight:700;}"
    ".ibox{background:#1e293b!important;border:1px solid #334155;border-radius:10px;padding:16px;height:100%;}"
    ".ibox h5{color:#60a5fa;font-size:13px!important;margin:0 0 12px;font-weight:700;}"
    ".irow{display:flex;gap:8px;margin:5px 0;font-size:12px!important;color:#cbd5e1;line-height:1.5!important;}"
    ".irow b{color:#94a3b8;min-width:155px;flex-shrink:0;}"
    ".tcard{background:#1e293b;border:1px solid #334155;border-radius:12px;padding:16px;border-top:4px solid;display:flex;flex-direction:column;gap:8px;height:100%;box-sizing:border-box;}"
    ".tcard.r{border-top-color:#dc2626;}.tcard.p{border-top-color:#9333ea;}.tcard.b{border-top-color:#2563eb;}"
    ".tcard h5{font-size:13px!important;font-weight:700;margin:0;color:#f1f5f9;}"
    ".trow{font-size:12px!important;color:#cbd5e1;margin:3px 0;line-height:1.6!important;}"
    ".trow b{color:#94a3b8;}"
    ".ttip{margin-top:auto;padding-top:10px;border-top:1px solid #334155;font-size:11px!important;color:#64748b;line-height:1.5!important;}"
    ".witem{background:#1e293b;border:1px solid #334155;border-left:3px solid #dc2626;border-radius:8px;padding:8px 12px;margin-bottom:6px;}"
    ".witem .plate{font-size:13px!important;font-weight:700;color:#f87171;}"
    ".witem .note{font-size:10px!important;color:#64748b;margin-top:2px;}"
    # Hide Streamlit material icon text bleed + fix Upload button overlap
    "[data-testid='stSidebarCollapseButton']{display:none!important;}"
    "[data-testid='stFileUploaderDropzone']{background:#1e293b!important;border:1px dashed #334155!important;border-radius:10px!important;}"
    "[data-testid='stFileUploaderDropzone'] [data-testid='stBaseButton-secondary']{position:relative!important;min-width:130px!important;height:36px!important;background:#334155!important;border:1px solid #475569!important;border-radius:8px!important;}"
    "[data-testid='stFileUploaderDropzone'] [data-testid='stBaseButton-secondary'] *{display:none!important;}"
    "[data-testid='stFileUploaderDropzone'] [data-testid='stBaseButton-secondary']::after{content:'📂 เลือกไฟล์ Upload';color:#f1f5f9!important;font-size:12px!important;font-weight:700!important;font-family:'Sarabun',sans-serif!important;display:flex!important;align-items:center!important;justify-content:center!important;width:100%!important;height:100%!important;}"
    "[data-testid='stFileUploaderFileData']{background:#1e293b!important;border:1px solid #334155!important;border-radius:8px!important;padding:6px 10px!important;margin-bottom:4px!important;}"
    "[data-testid='stFileUploaderFileData'] *{color:#e2e8f0!important;font-size:12px!important;}"
    "[data-testid='stFileUploaderFileData'] button{position:static!important;min-width:auto!important;height:auto!important;background:transparent!important;border:none!important;padding:2px!important;}"
    "[data-testid='stFileUploaderFileData'] button *{display:inline-block!important;}"
    "[data-testid='stFileUploaderFileData'] button::after{content:''!important;display:none!important;}"
    "[data-testid='stFileUploaderDropzone'] small{color:#64748b!important;font-size:11px!important;}.stMarkdown p{font-size:13px!important;line-height:1.65!important;color:#e2e8f0!important;}"
    ".stMarkdown h4,.stMarkdown h5{color:#f1f5f9!important;}"
    # Force light text in all Streamlit elements
    "[data-testid='stDataFrame'] *{color:#e2e8f0!important;font-size:12px!important;}"
    "[data-testid='stDataFrame'] thead th{background:#1e3a5f!important;color:#93c5fd!important;font-weight:700!important;border-bottom:2px solid #334155!important;}"
    "[data-testid='stDataFrame'] tbody tr{background:#1e293b!important;border-bottom:1px solid #334155!important;}"
    "[data-testid='stDataFrame'] tbody tr:hover{background:#243249!important;}"
    "[data-testid='stDataFrame'] tbody td{color:#e2e8f0!important;padding:8px 12px!important;}"
    ".dvn-scroller *{color:#e2e8f0!important;}"
    "[data-testid='column'] *{color:#e2e8f0!important;}"
    ".stCaption,.stCaption *{color:#94a3b8!important;font-size:12px!important;}"
    "[data-testid='stWidgetLabel']>div>p{color:#94a3b8!important;font-size:12px!important;}"
    "[data-testid='stSlider'] *{color:#cbd5e1!important;}"
    "[data-testid='stFileUploader'] *{color:#cbd5e1!important;}"
    "[data-testid='stTextInput'] input{color:#e2e8f0!important;background:#1e293b!important;border:1px solid #334155!important;}"
    "button[kind='primary']{background:linear-gradient(135deg,#1d4ed8,#4f46e5)!important;color:#fff!important;}"
    "button[kind='secondary']{background:#1e293b!important;color:#cbd5e1!important;border:1px solid #334155!important;}"
    "[class*='stSuccess']{background:rgba(16,185,129,.12)!important;color:#6ee7b7!important;border:1px solid rgba(16,185,129,.3)!important;}"
    "[class*='stError']{background:rgba(220,38,38,.12)!important;color:#fca5a5!important;}"
    "[class*='stInfo']{background:rgba(37,99,235,.1)!important;color:#93c5fd!important;}"
    "[data-testid='stExpander'] summary{color:#94a3b8!important;font-size:12px!important;}"
    "[data-testid='stExpander'] [data-testid='stCodeBlock'] code{font-size:11px!important;}"
    "::-webkit-scrollbar{width:5px;height:5px;}::-webkit-scrollbar-track{background:#1e293b;}::-webkit-scrollbar-thumb{background:#334155;border-radius:3px;}"
    "@media print{[data-testid='stSidebar'],.stAppHeader,button,iframe{display:none!important;}.stApp{background:#fff!important;color:#000!important;}}"
    "</style>"
)
st.markdown(_CSS, unsafe_allow_html=True)

# ── Session State ──────────────────────────────────────────────────────────────
_DEF = {
    'master_df': pd.DataFrame(), 'cloned_cases': {}, 'convoy_cases': {},
    'suspect_cases': {}, 'loaded_key': None, 'watch_list': [], 'uploader_key': 0,
    'wl_loaded_from_pg': False,
}
for k, v in _DEF.items():
    if k not in st.session_state:
        st.session_state[k] = v

# โหลด Watchlist จาก PostgreSQL Oracle ครั้งแรก
if not st.session_state.get('wl_loaded_from_pg'):
    _pg_rows = _wl_load()
    if _pg_rows:
        st.session_state.watch_list = _pg_rows
    st.session_state.wl_loaded_from_pg = True

# ── Header ─────────────────────────────────────────────────────────────────────
now_s = datetime.datetime.now().strftime("%d/%m/%Y %H:%M")
has   = not st.session_state.master_df.empty
nveh  = st.session_state.master_df['ทะเบียนรถ'].nunique() if has else 0
_BUILD_DATE = "2026-08-10"  # keep as str; Python 3.14 f-string parser rejects 08 as octal literal
st.markdown(f"""
<div class="top-hdr">
  <div class="hdr-left">
    <div class="hdr-title">{'<img src="' + LOGO_SRC + '" style="height:32px;width:32px;border-radius:8px;vertical-align:middle;margin-right:10px;object-fit:cover;box-shadow:0 0 10px rgba(220,38,38,0.5);">' if LOGO_SRC else '&#128680; '}i-Trap Analysis</div>
    <div class="hdr-sub">ศูนย์วิเคราะห์ข่าวกรองยานพาหนะเชิงยุทธวิธี &mdash; Tactical Vehicle Intelligence Platform</div>
    <div class="hdr-status"><div class="sdot"></div>
      {'ออนไลน์ · ข้อมูลพร้อมใช้ · ' + f'{nveh:,} คัน' if has else 'ออนไลน์ · รอนำเข้าข้อมูล'}
    </div>
  </div>
  <div class="hdr-badge">
    <div class="ver">v{_VER}</div>
    <div class="ts">&#128336; {now_s} น.</div>
    <div class="ts">Build: {_BUILD_DATE}</div>
  </div>
</div>
""", unsafe_allow_html=True)

# ── Sidebar ────────────────────────────────────────────────────────────────────
with st.sidebar:
    st.markdown(f"""
    <div style="text-align:center;padding:16px 0 12px;">
      {'<img src="' + LOGO_SRC + '" style="width:60px;height:60px;border-radius:14px;object-fit:cover;box-shadow:0 0 16px rgba(220,38,38,0.5);border:2px solid #334155;">' if LOGO_SRC else '<div style="font-size:52px;line-height:1;filter:drop-shadow(0 0 12px rgba(220,38,38,0.4));">&#128680;</div>'}
      <div style="font-size:15px;font-weight:800;color:#e2e8f0;margin-top:8px;">i-Trap Analysis</div>
      <div style="font-size:11px;color:#475569;margin-top:2px;">Tactical Intelligence Platform</div>
    </div>""", unsafe_allow_html=True)

    # ── Section 1: Import ──
    st.markdown('<span class="sb-title">&#128193; นำเข้าข้อมูล</span>', unsafe_allow_html=True)
    up_key = f"file_uploader_{st.session_state.uploader_key}"
    uploaded = st.file_uploader("ไฟล์ .csv / .xlsx", accept_multiple_files=True,
                                type=['csv','xlsx'], key=up_key, label_visibility="collapsed")
    if uploaded:
        names_html = "".join(f"<div style='font-size:11px;color:#94a3b8;margin-top:2px;'>• {f.name}</div>" for f in uploaded)
        st.markdown(f"""<div style="background:rgba(37,99,235,.1);border:1px solid #1e40af;border-radius:8px;padding:8px 12px;margin-bottom:8px;">
          <div style="font-size:11px;color:#60a5fa;font-weight:600;">&#128206; {len(uploaded)} ไฟล์พร้อมประมวลผล</div>{names_html}</div>""",
          unsafe_allow_html=True)
    c1, c2 = st.columns(2)
    btn_load  = c1.button("⚡ ประมวลผล", type="primary", use_container_width=True)
    btn_reset = c2.button("&#128465; ล้าง", use_container_width=True)
    st.markdown("""
    <details style="margin-top:4px;">
      <summary style="cursor:pointer;font-size:12px;color:#64748b;padding:4px 0;">
        &#128421; ส่งไฟล์ใหญ่ทาง SCP
      </summary>
      <div style="background:#111827;border-radius:6px;padding:10px;margin-top:6px;font-size:11px;color:#94a3b8;font-family:monospace;">
        scp C:\data\scan.csv ubuntu@&lt;IP&gt;:~/data/
      </div>
      <div style="font-size:11px;color:#475569;margin-top:4px;">เปลี่ยน &lt;IP&gt; เป็น IP Oracle VM</div>
    </details>
    """, unsafe_allow_html=True)

    if btn_reset:
        st.session_state.uploader_key += 1
        for k, v in _DEF.items():
            if k != 'uploader_key': st.session_state[k] = v
        _cached_preprocess.clear(); _cached_map.clear(); st.rerun()

    # ── Section 2: Settings ──
    st.markdown('<span class="sb-title">&#9881; ตั้งค่าวิเคราะห์</span>', unsafe_allow_html=True)
    min_risk = st.slider("&#127919; Risk Score ขั้นต่ำ", 60, 95, 80, 5)
    min_cams = st.slider("&#128247; กล้องร่วมขั้นต่ำ (E2/E3)", 2, 8, 5, 1)

    st.markdown(f'<div style="padding:14px 0 0;border-top:1px solid #1e293b;margin-top:14px;font-size:10px;color:#334155;text-align:center;">i-Trap v{_VER} · CONFIDENTIAL</div>',
                unsafe_allow_html=True)

# ── Load ───────────────────────────────────────────────────────────────────────
if btn_load and uploaded:
    _cached_map.clear()
    fnames = [f.name for f in uploaded]
    fbytes = [f.read() for f in uploaded]
    key    = str(sorted([(n,len(b)) for n,b in zip(fnames,fbytes)]))
    if key != st.session_state.loaded_key:
        with st.sidebar, st.spinner("⚡ ประมวลผล..."):
            md, cc, cv, ss = _cached_preprocess(tuple(fbytes), tuple(fnames))
        st.session_state.update(master_df=md, cloned_cases=cc,
                                convoy_cases=cv, suspect_cases=ss, loaded_key=key)
        if not md.empty:
            st.sidebar.success(f"&#9989; {md['ทะเบียนรถ'].nunique():,} คัน")
        else:
            st.sidebar.error("&#10060; ไม่พบข้อมูล &mdash; ตรวจสอบรูปแบบไฟล์")

# ── Welcome ──────────────────────────────────────────────────────────────
if st.session_state.master_df.empty:
    _logo_html = (
        '<div style="position:relative;display:inline-block;margin-bottom:32px;">' +
        '<div style="position:absolute;inset:-7px;border-radius:34px;' +
        'background:conic-gradient(from 0deg,#ef4444,#f97316,#facc15,#ef4444);' +
        'animation:herospin 4s linear infinite;opacity:0.75;filter:blur(6px);"></div>' +
        f'<img src="{LOGO_SRC}" style="position:relative;width:200px;height:200px;' +
        'object-fit:cover;border-radius:28px;border:3px solid rgba(255,255,255,0.1);' +
        'box-shadow:0 0 60px rgba(239,68,68,0.35);display:block;">' +
        '</div>'
        if LOGO_SRC else
        '<div style="font-size:120px;line-height:1;margin-bottom:32px;'
        'filter:drop-shadow(0 0 40px rgba(220,38,38,0.6));">&#128680;</div>'
    )
    st.markdown(f"""
<style>
@keyframes herospin {{from{{transform:rotate(0deg)}}to{{transform:rotate(360deg)}}}}
@keyframes heroin {{from{{opacity:0;transform:translateY(24px)}}to{{opacity:1;transform:translateY(0)}}}}
.itrap-hero {{ animation: heroin 0.9s ease forwards; }}
</style>
<div class="itrap-hero" style="display:flex;flex-direction:column;align-items:center;
     justify-content:center;padding:50px 20px 50px;text-align:center;min-height:65vh;">
  {_logo_html}
  <h1 style="color:#f1f5f9;font-weight:900;margin:0 0 8px;font-size:42px;
             letter-spacing:-1.5px;text-shadow:0 0 50px rgba(239,68,68,0.35);">
    i-Trap Analysis
  </h1>
  <div style="font-size:12px;font-weight:800;letter-spacing:.25em;text-transform:uppercase;
              margin-bottom:20px;background:linear-gradient(90deg,#ef4444,#f97316,#facc15);
              -webkit-background-clip:text;-webkit-text-fill-color:transparent;">
    Tactical Vehicle Intelligence Platform
  </div>
  <div style="width:80px;height:2px;margin-bottom:20px;
       background:linear-gradient(90deg,transparent,#ef4444,transparent);"></div>
  <p style="color:#94a3b8;font-size:14px;max-width:500px;line-height:2;margin:0 0 44px;">
    ระบบวิเคราะห์ข่าวกรองยานพาหนะเชิงยุทธวิธี<br>
    <span style="color:#64748b;">อัปโหลดไฟล์ .csv / .xlsx ทางแถบซ้าย แล้วกด</span>
    <span style="color:#fbbf24;font-weight:700;">&#9889; ประมวลผล</span>
  </p>
  <div style="display:grid;grid-template-columns:repeat(4,1fr);gap:18px;max-width:780px;width:100%;">
    <div style="background:linear-gradient(145deg,#1e293b,#0f172a);
         border:1px solid #1e3a5f;border-top:3px solid #ef4444;border-radius:16px;padding:24px 16px;">
      <div style="font-size:40px;line-height:1.2;">&#128680;</div>
      <div style="color:#f87171;font-weight:800;margin-top:14px;font-size:14px;">Ghost Plate</div>
      <div style="font-size:11px;color:#64748b;margin-top:6px;">รถสวมทะเบียน</div>
    </div>
    <div style="background:linear-gradient(145deg,#1e293b,#0f172a);
         border:1px solid #1e3a5f;border-top:3px solid #f59e0b;border-radius:16px;padding:24px 16px;">
      <div style="font-size:40px;line-height:1.2;">&#128664;</div>
      <div style="color:#fbbf24;font-weight:800;margin-top:14px;font-size:14px;">Convoy</div>
      <div style="font-size:11px;color:#64748b;margin-top:6px;">ขบวนลำเลียง</div>
    </div>
    <div style="background:linear-gradient(145deg,#1e293b,#0f172a);
         border:1px solid #1e3a5f;border-top:3px solid #3b82f6;border-radius:16px;padding:24px 16px;">
      <div style="font-size:40px;line-height:1.2;">&#128260;</div>
      <div style="color:#60a5fa;font-weight:800;margin-top:14px;font-size:14px;">Border U-Turn</div>
      <div style="font-size:11px;color:#64748b;margin-top:6px;">มุดช่องโหว์ชายแดน</div>
    </div>
    <div style="background:linear-gradient(145deg,#1e293b,#0f172a);
         border:1px solid #1e3a5f;border-top:3px solid #8b5cf6;border-radius:16px;padding:24px 16px;">
      <div style="font-size:40px;line-height:1.2;">&#127769;</div>
      <div style="color:#a78bfa;font-weight:800;margin-top:14px;font-size:14px;">Night Ghost</div>
      <div style="font-size:11px;color:#64748b;margin-top:6px;">รถชายแดนกลางดึก</div>
    </div>
  </div>
</div>""", unsafe_allow_html=True)

else:
    # ── Dashboard ───────────────────────────────────────────────────────────────
    md  = st.session_state.master_df
    cc  = st.session_state.cloned_cases
    cv  = st.session_state.convoy_cases
    ss  = st.session_state.suspect_cases

    cv_disp = {k:v for k,v in cv.items() if v.get('risk_score',0)>=min_risk and v.get('total_cams',0)>=min_cams}
    ss_disp = {k:v for k,v in ss.items() if v.get('risk_score',0)>=min_risk
               and (v.get('engine_type','') in ('E1','E4') or v.get('total_cams',0)>=min_cams)}
    apex = sum(1 for v in {**cc,**ss,**cv}.values() if v.get('apex'))

    # Metric bar
    dr = ""
    if 'Datetime' in md.columns:
        d0,d1 = md['Datetime'].min(), md['Datetime'].max()
        if pd.notna(d0) and pd.notna(d1):
            dr = f"{d0.strftime('%d/%m/%y')} &ndash; {d1.strftime('%d/%m/%y')}"
    st.markdown(f"""
    <div class="mgrid">
      <div class="mc r"><div class="mlbl">&#128680; รถสวมทะเบียน (E1)</div>
        <div class="mval r">{len(cc):,}</div><div class="msub">Ghost Plate Cases</div></div>
      <div class="mc a"><div class="mlbl">&#128664; ขบวนลำเลียง (E2)</div>
        <div class="mval a">{len(cv_disp):,}</div><div class="msub">จาก {len(cv):,} ขบวน</div></div>
      <div class="mc b"><div class="mlbl">&#9888; รถต้องสงสัย (E3-E5)</div>
        <div class="mval b">{len(ss_disp):,}</div><div class="msub">จาก {len(ss):,} เคส</div></div>
      <div class="mc p"><div class="mlbl">&#10084;&#128293; Apex Threat</div>
        <div class="mval p">{apex:,}</div><div class="msub">{dr if dr else f'{md["ทะเบียนรถ"].nunique():,} คัน'}</div></div>
    </div>""", unsafe_allow_html=True)

    tab1, tab2, tab3 = st.tabs([
        f"&#128680;  Ghost Plate  ({len(cc)})",
        f"&#128664;  Convoy  ({len(cv_disp)})",
        f"&#9888;  Suspect  ({len(ss_disp)})"
    ])

    # ── Dossier renderer ────────────────────────────────────────────────────────
    def dossier(c, is_convoy=False):
        title  = c.get('group_name', c.get('plate',''))
        score  = c.get('risk_score',0)
        cls    = "crit" if score>=90 else ("high" if score>=75 else "med")
        apex_h = (f'<span class="apexb">&#10084;&#128293; APEX · {" + ".join(c.get("apex_engines",[]))}</span>'
                  if c.get('apex') else "")

        h1, h2, h3 = st.columns([6, 2, 1])
        with h1:
            st.markdown(f"<div style='font-size:11px;color:#64748b;'>{c.get('engine_name','')}</div>"
                        f"<div style='font-size:18px;font-weight:800;color:#f1f5f9;margin-bottom:4px;'>&#128203; {title}</div>"
                        f"{apex_h}", unsafe_allow_html=True)
        with h2:
            # ── ปุ่มนำเข้า Watch List ──────────────────────────────────
            plate_key = c.get('plate', c.get('leader',''))
            in_watch  = any(w[0] == plate_key for w in st.session_state.watch_list)
            if in_watch:
                st.markdown(f"""<div style="background:rgba(220,38,38,.15);border:1px solid #991b1b;
                    border-radius:8px;padding:6px 10px;text-align:center;
                    font-size:11px;color:#fca5a5;font-weight:600;">
                    &#128204; อยู่ใน Watch List</div>""", unsafe_allow_html=True)
            else:
                if st.button("&#128204; นำเข้า Watch List", key=f"wl_{c['case_id']}",
                             use_container_width=True, type="primary",
                             help=f"บันทึก {plate_key} เพื่อส่งแจ้งเตือน LINE"):
                    import datetime as _dt
                    _ts = _dt.datetime.now().strftime("%H:%M")
                    st.session_state.watch_list.append((plate_key, _ts))

                    # รวบรวมข้อมูล case ทั้งหมด
                    _score    = int(c.get('score', 0))
                    _reason   = " | ".join(c.get('reasons', []))
                    _prov     = c.get('province', c.get('จังหวัด', ''))
                    _seen     = int(c.get('total_cams', c.get('seen_count', 0)))
                    _chk      = c.get('apex_location', c.get('last_checkpoint', ''))
                    _time     = c.get('last_time', c.get('last_seen_time', ''))
                    _btype    = c.get('engine_type', c.get('behavior_type', ''))
                    _lat      = c.get('lat') or c.get('latitude')
                    _lon      = c.get('lon') or c.get('longitude')
                    _verdict  = c.get('verdict_text', '')
                    # convoy
                    _cv_role  = "lead" if c.get('is_lead') else ("follow" if c.get('is_follow') else "single")
                    _cv_mem   = list(c.get('convoy_members', c.get('related_plates', [])))

                    _saved = _wl_add(
                        plate_key, _reason, _score,
                        province=_prov, seen_count=_seen,
                        last_checkpoint=_chk, last_seen_time=_time,
                        behavior_type=_btype, lat=_lat, lon=_lon,
                        verdict=_verdict, convoy_members=_cv_mem, convoy_role=_cv_role,
                    )
                    if _saved:
                        st.toast(f"✅ บันทึก {plate_key} ลง Watch List แล้ว!", icon="🗄️")
                    else:
                        st.toast(f"⚠️ บันทึกใน session เท่านั้น (DB offline)", icon="⚠️")
                    st.rerun()

        with h3:
            components.html("""<button onclick="window.print()" style="
                background:#1e293b;color:#94a3b8;border:1px solid #334155;
                padding:7px 10px;border-radius:8px;font-size:11px;font-weight:600;
                cursor:pointer;width:100%;">&#128424; PDF</button>""", height=38)

        st.markdown(f"""
        <div class="vcard {cls}">
          <div class="vhdr">
            <div class="vtitle">{c.get('verdict_badge','')}</div>
            <div class="rbadge {cls}">&#9888; {score}/100</div>
          </div>
          <div style="font-size:13px;color:#cbd5e1;margin-top:8px;line-height:1.6;">{c.get('verdict_text','')}</div>
          <div style="font-size:12px;color:#94a3b8;border-top:1px solid #334155;padding-top:8px;margin-top:8px;">
            &#128202; ความเชื่อมั่น: {c.get('confidence_text','')}
          </div>
        </div>""", unsafe_allow_html=True)

        # Radar + Intel
        cr, ci = st.columns([4,6])
        with cr:
            r = c.get('radar',{})
            fig = go.Figure(go.Scatterpolar(
                r=[r.get('border',0),r.get('night',0),r.get('convoy',0),r.get('foreign',0),r.get('frequency',0)],
                theta=['ชายแดน','กลางดึก','ขบวนกลุ่ม','ต่างถิ่น','ความถี่'],
                fill='toself',
                fillcolor='rgba(220,38,38,.2)' if score>=90 else 'rgba(217,119,6,.2)' if score>=75 else 'rgba(37,99,235,.2)',
                line=dict(color='#ef4444' if score>=90 else '#f59e0b' if score>=75 else '#60a5fa', width=2)
            ))
            fig.update_layout(
                polar=dict(radialaxis=dict(visible=True,range=[0,35],showticklabels=False,gridcolor='#334155'),
                           angularaxis=dict(gridcolor='#334155'),bgcolor='rgba(30,41,59,.6)'),
                paper_bgcolor='rgba(0,0,0,0)', plot_bgcolor='rgba(0,0,0,0)',
                font=dict(color='#94a3b8',size=11,family='Sarabun,sans-serif'),
                margin=dict(l=35,r=35,t=20,b=20), height=255)
            st.plotly_chart(fig, use_container_width=True, key=f"rad_{c['case_id']}")
        with ci:
            st.markdown(f"""
            <div class="ibox">
              <h5>&#128203; สรุปข้อมูลเป้าหมาย</h5>
              <div class="irow"><b>&#128204; จังหวัดที่จดทะเบียน:</b> {c.get('registered_prov','')}</div>
              <div class="irow"><b>&#128202; พบสะสม:</b> {c.get('seen_count',0)} ครั้ง / {c.get('seen_days',0)} วัน</div>
              <div class="irow"><b>&#127769; สัดส่วนกลางดึก:</b> {c.get('night_ratio_pct',0):.1f}%</div>
              <div class="irow"><b>&#128205; จุดตรวจบ่อยสุด:</b> {c.get('top_camera','')}</div>
              <div class="irow"><b>&#128197; รูปแบบวัน:</b> {c.get('day_pattern','')}</div>
              <div class="irow"><b>⏱ รูปแบบเวลา:</b> {c.get('time_pattern','')}</div>
              <div style="margin-top:10px;padding-top:10px;border-top:1px solid #334155;font-size:12px;color:#93c5fd;line-height:1.6;">
                &#128664; <b>แผนประทุษกรรม:</b><br>{c.get('modus_operandi','')}
              </div>
            </div>""", unsafe_allow_html=True)

        # ── Tactical boxes (2 กล่อง: สกัดจับ + แหล่งกบดาน) ─────────────────────
        st.markdown('<div style="height:10px;"></div>', unsafe_allow_html=True)
        car_df  = c['raw_df']
        top_cam = c.get('top_camera','')

        # Top-3 จุดตรวจพร้อมสถิติ
        if not car_df.empty and 'จุดติดตั้งกล้อง' in car_df.columns:
            cam_stats = (car_df.groupby('จุดติดตั้งกล้อง')
                         .agg(count=('จุดติดตั้งกล้อง','count'),
                              peak_hour=('Hour', lambda x: x.mode().iloc[0] if len(x.mode())>0 else 0))
                         .sort_values('count', ascending=False)
                         .head(3).reset_index())
        else:
            cam_stats = pd.DataFrame()

        def _cam_row(rank, row):
            medal = ["&#129351;","&#129352;","&#129353;"][rank]
            h = int(row['peak_hour'])
            return (f"<div style='display:flex;justify-content:space-between;align-items:center;"
                    f"padding:7px 10px;margin:5px 0;background:rgba(255,255,255,.04);"
                    f"border-radius:8px;border-left:3px solid {'#ef4444' if rank==0 else '#f59e0b' if rank==1 else '#60a5fa'};'>"
                    f"<div><span style='font-size:15px;'>{medal}</span> "
                    f"<span style='color:#e2e8f0;font-size:12px;font-weight:600;'>{row['จุดติดตั้งกล้อง']}</span></div>"
                    f"<div style='text-align:right;'>"
                    f"<div style='color:#fbbf24;font-size:13px;font-weight:700;'>{int(row['count'])} ครั้ง</div>"
                    f"<div style='color:#94a3b8;font-size:10px;'>ช่วง {h:02d}:00&ndash;{(h+2)%24:02d}:00</div>"
                    f"</div></div>")

        top3_html = ""
        for i, row in cam_stats.iterrows():
            top3_html += _cam_row(i, row)

        choke = car_df[car_df['จุดติดตั้งกล้อง']==top_cam] if top_cam else pd.DataFrame()
        bhr   = int(choke['Hour'].mode().iloc[0]) if not choke.empty and len(choke['Hour'].mode())>0 else 0
        hr_txt= f"{bhr:02d}:00 &ndash; {(bhr+2)%24:02d}:00 น."

        pb, ts_h, sw = get_2d_hideout_estimates(car_df)
        p_txt = f"[{pb['cam_from']}]→[{pb['cam_to']}] ({pb['hours_missing']:.1f} ชม.)" if pb else "ไม่พบ"
        t_txt = f"[{ts_h['cam']}] (แวะซ้ำ {ts_h['visit_count']} ครั้ง)" if ts_h else "ไม่พบ"
        s_txt = f"[{sw['cam_from']}]→[{sw['cam_to']}] ({sw['dist_km']:.0f} กม. / {sw['hours_missing']:.1f} ชม.)" if sw else "ไม่พบ"

        q1, q2 = st.columns(2)
        with q1:
            st.markdown(f"""<div class="tcard r">
              <h5>&#128680; 1. สกัดจับจุดไหน</h5>
              <div style="font-size:10px;color:#64748b;font-weight:700;letter-spacing:.08em;text-transform:uppercase;margin-bottom:6px;">Top-3 จุดตรวจ</div>
              {top3_html if top3_html else '<div class="trow" style="color:#475569;">ไม่มีข้อมูล</div>'}
              <div class="ttip">&#128737; ประจำจุดก่อน 15 นาที เพื่อจำกัดเสรีการหลบหนี</div>
            </div>""", unsafe_allow_html=True)
        with q2:
            st.markdown(f"""<div class="tcard p">
              <h5>&#129399; 2. แหล่งกบดาน</h5>
              <div class="trow"><b>กบดาน (&gt;12 ชม.):</b><br><span style="color:#f87171;">{p_txt}</span></div>
              <div class="trow"><b>จุดพักชั่วคราว:</b><br><span style="color:#fbbf24;">{t_txt}</span></div>
              <div class="trow"><b>จุดอับสงสัย:</b><br><span style="color:#a78bfa;">{s_txt}</span></div>
              <div class="ttip">&#128737; ตรวจ CCTV ท้องถิ่นในรัศมีรอยต่อจุดหายไป</div>
            </div>""", unsafe_allow_html=True)

        st.markdown('<div style="height:12px;"></div>', unsafe_allow_html=True)

        # Map
        et   = c.get('engine_type','E1')
        mttl = "&#128506; แผนที่ Ghost Plate Paradox" if et=='E1' else ("&#128506; แผนที่ขบวนรถ (Convoy)" if et=='E2' else "&#128506; แผนที่เส้นทาง")
        st.markdown(f"<div style='color:#94a3b8;font-size:13px;font-weight:700;margin-bottom:6px;'>{mttl}</div>",
                    unsafe_allow_html=True)
        mhtml = _cached_map(c['case_id'], car_df,
                            c.get('leader', c.get('plate','')), c.get('follower',''),
                            ghost=(et=='E1'), dates=c.get('dates_passed',[]))
        components.html(mhtml, height=450)

        # Timeline
        if is_convoy and 'events' in c:
            st.markdown("<div style='color:#94a3b8;font-size:13px;font-weight:700;margin:12px 0 6px;'>&#9200; ไทม์ไลน์ขบวนรถ</div>",
                        unsafe_allow_html=True)
            ldr,flw = c.get('leader',''), c.get('follower','')
            for di, ev_date in enumerate(sorted(set(e['date'] for e in c['events']))):
                evs = [e for e in c['events'] if e['date']==ev_date and len(e.get('cluster',[]))>=2]
                if not evs: continue
                st.markdown(f"<div style='color:#60a5fa;font-size:13px;font-weight:700;margin:8px 0 4px;'>&#128197; {ev_date}</div>",
                            unsafe_allow_html=True)
                fig2 = go.Figure()
                cxs = [e['cam'] for e in evs]
                fig2.add_trace(go.Scatter(x=cxs, y=[f"รถนำ: {ldr}"]*len(cxs),
                    mode='lines+markers+text', text=[e['cluster'][0]['Datetime'].strftime('%H:%M') for e in evs],
                    textposition='top center', textfont=dict(size=11,color='#f87171'),
                    name=f"รถนำ: {ldr}", line=dict(color='#ef4444',width=3), marker=dict(size=11,color='#ef4444')))
                fig2.add_trace(go.Scatter(x=cxs, y=[f"รถตาม: {flw}"]*len(cxs),
                    mode='lines+markers+text', text=[e['cluster'][1]['Datetime'].strftime('%H:%M') for e in evs],
                    textposition='bottom center', textfont=dict(size=11,color='#60a5fa'),
                    name=f"รถตาม: {flw}", line=dict(color='#3b82f6',width=3,dash='dot'),
                    marker=dict(size=11,symbol='diamond',color='#3b82f6')))
                fig2.update_layout(paper_bgcolor='#1e293b', plot_bgcolor='#1e293b',
                    font=dict(color='#94a3b8',size=11,family='Sarabun'),
                    xaxis=dict(showgrid=True,gridcolor='#334155',tickangle=-20,tickfont=dict(size=9)),
                    yaxis=dict(showgrid=True,gridcolor='#334155'),
                    legend=dict(orientation='h',yanchor='bottom',y=1.02,xanchor='right',x=1,font=dict(color='#94a3b8')),
                    margin=dict(l=50,r=40,t=50,b=90), height=290)
                st.plotly_chart(fig2, use_container_width=True, key=f"cv_{c['case_id']}_{di}")
        else:
            if not car_df.empty:
                st.markdown("<div style='color:#94a3b8;font-size:13px;font-weight:700;margin:12px 0 6px;'>&#9200; เส้นทางรายวัน (≥5 กล้อง)</div>",
                            unsafe_allow_html=True)
                dinfo = sorted([{'d':d,'nc':car_df[car_df['วันที่']==d]['จุดติดตั้งกล้อง'].nunique(),
                                  'np':len(car_df[car_df['วันที่']==d])}
                                 for d in car_df['วันที่'].unique()],
                                key=lambda x:(x['nc'],x['np']), reverse=True)
                for di,inf in enumerate([x for x in dinfo if x['nc']>=5]):
                    day = car_df[car_df['วันที่']==inf['d']].sort_values('Datetime')
                    st.markdown(f"<div style='color:#60a5fa;font-size:13px;font-weight:700;margin:8px 0 4px;'>&#128197; {inf['d']} &mdash; {inf['nc']} จุด ({inf['np']} ครั้ง)</div>",
                                unsafe_allow_html=True)
                    fig3 = go.Figure(go.Scatter(
                        x=day['จุดติดตั้งกล้อง'].tolist(), y=[c.get('plate','')]*len(day),
                        mode='lines+markers+text', text=day['Datetime'].dt.strftime('%H:%M').tolist(),
                        textposition='top center', textfont=dict(size=11,color='#60a5fa'),
                        line=dict(color='#3b82f6',width=2.5), marker=dict(size=11,color='#3b82f6')))
                    fig3.update_layout(paper_bgcolor='#1e293b', plot_bgcolor='#1e293b',
                        font=dict(color='#94a3b8',size=11,family='Sarabun'),
                        xaxis=dict(showgrid=True,gridcolor='#334155',tickangle=-20,tickfont=dict(size=9)),
                        yaxis=dict(showgrid=True,gridcolor='#334155'),
                        margin=dict(l=50,r=40,t=35,b=90), height=220, showlegend=False)
                    st.plotly_chart(fig3, use_container_width=True, key=f"dy_{c['case_id']}_{di}")

        # Convoy formation table
        if is_convoy and 'events' in c:
            st.markdown("<div style='color:#94a3b8;font-size:13px;font-weight:700;margin:12px 0 6px;'>&#128279; ตารางขบวนรถ</div>",
                        unsafe_allow_html=True)
            rows = [{'จุดตรวจ':e['cam'],'วันที่':e['date'],'จำนวนคัน':len(e['cars']),
                     'ทะเบียน':" ➡ ".join(e['cars']),'เวลา':" ➡ ".join(e.get('times',[])),
                     'ความเร็ว':" ➡ ".join(f"{s:.0f}" for s in e.get('speeds',[]))} for e in c['events']]
            st.dataframe(pd.DataFrame(rows), use_container_width=True)

        # Raw evidence
        st.markdown("<div style='color:#94a3b8;font-size:13px;font-weight:700;margin:12px 0 6px;'>&#128196; พยานหลักฐานฉบับเต็ม</div>",
                    unsafe_allow_html=True)
        dcols = [x for x in ['วันที่','เวลา','ทะเบียนรถ','จุดติดตั้งกล้อง','จังหวัด','Speed_kmh'] if x in car_df.columns]
        st.dataframe(car_df[dcols].rename(columns={'Speed_kmh':'ความเร็ว(กม./ชม.)','จุดติดตั้งกล้อง':'จุดตรวจ'}),
                     use_container_width=True)

    # ── Tab 1 ────────────────────────────────────────────────────────────────
    with tab1:
        st.markdown("#### &#128680; รถสวมทะเบียน &mdash; Ghost Plate Paradox")
        if not cc:
            st.markdown('<div style="background:rgba(16,185,129,.08);border:1px solid #065f46;border-radius:10px;padding:16px;color:#6ee7b7;text-align:center;">&#9989; ไม่พบรถสวมทะเบียน</div>', unsafe_allow_html=True)
        else:
            rows = [{'ทะเบียน':v['plate'],'&#9888;Risk':v['risk_score'],'&#127919;Conf%':v['confidence_level'],
                     'จังหวัด':v['registered_prov'],'วัน':v['seen_days'],'ครั้ง':v['seen_count'],
                     'จุดบ่อยสุด':v['top_camera'],'APEX':'● APEX' if v.get('apex') else '','_k':k}
                    for k,v in cc.items()]
            df1 = pd.DataFrame(rows).sort_values('&#9888;Risk', ascending=False).reset_index(drop=True)
            st.caption(f"&#128070; คลิกแถวเพื่อดูรายละเอียด | {len(rows)} เคส")
            ev1 = st.dataframe(df1.drop(columns=['_k']), use_container_width=True,
                               on_select='rerun', selection_mode='single-row', key='t1')
            sel = df1.iloc[ev1.selection.rows[0]]['_k'] if ev1.selection.rows else df1.iloc[0]['_k']
            st.markdown('<hr style="border-color:#1e293b;margin:14px 0;">', unsafe_allow_html=True)
            dossier(cc[sel])

    # ── Tab 2 ────────────────────────────────────────────────────────────────
    with tab2:
        st.markdown(f"#### &#128664; ขบวนลำเลียง &mdash; Convoy Fleet *(Risk≥{min_risk}, กล้อง≥{min_cams})*")
        if not cv:
            st.markdown('<div style="background:rgba(16,185,129,.08);border:1px solid #065f46;border-radius:10px;padding:16px;color:#6ee7b7;text-align:center;">&#9989; ไม่พบขบวนรถ</div>', unsafe_allow_html=True)
        elif not cv_disp:
            st.info(f"ตรวจพบ {len(cv)} ขบวน แต่ไม่ผ่านเกณฑ์ &mdash; ลองปรับ Slider ที่ Sidebar")
        else:
            rows = [{'สมาชิก':f"{v.get('leader','')} ➡ {v.get('follower','')}",
                     '&#9888;Risk':v['risk_score'],'&#127919;Conf%':v['confidence_level'],
                     'กล้อง':v.get('total_cams',0),'วัน':v['seen_days'],
                     'ยืนยัน':'&#9989;ยืนยัน' if v.get('has_multi_days') else '&#9888;ติดตาม',
                     'APEX':'● APEX' if v.get('apex') else '','_k':k}
                    for k,v in cv_disp.items()]
            df2 = pd.DataFrame(rows).sort_values('&#9888;Risk', ascending=False).reset_index(drop=True)
            st.caption(f"&#128070; คลิกแถวเพื่อดูรายละเอียด | {len(rows)} ขบวน")
            ev2 = st.dataframe(df2.drop(columns=['_k']), use_container_width=True,
                               on_select='rerun', selection_mode='single-row', key='t2')
            sel = df2.iloc[ev2.selection.rows[0]]['_k'] if ev2.selection.rows else df2.iloc[0]['_k']
            st.markdown('<hr style="border-color:#1e293b;margin:14px 0;">', unsafe_allow_html=True)
            dossier(cv[sel], is_convoy=True)

    # ── Tab 3 ────────────────────────────────────────────────────────────────
    with tab3:
        st.markdown(f"#### &#9888; รถต้องสงสัย &mdash; Suspect Vehicles *(Risk≥{min_risk}, กล้อง≥{min_cams})*")
        if not ss:
            st.markdown('<div style="background:rgba(16,185,129,.08);border:1px solid #065f46;border-radius:10px;padding:16px;color:#6ee7b7;text-align:center;">&#9989; ไม่พบรถต้องสงสัย</div>', unsafe_allow_html=True)
        elif not ss_disp:
            st.info(f"ตรวจพบ {len(ss)} เคส แต่ไม่ผ่านเกณฑ์ &mdash; ลองปรับ Slider ที่ Sidebar")
        else:
            rows = [{'ทะเบียน':v['plate'],'ประเภท':v['engine_name'],
                     '&#9888;Risk':v['risk_score'],'&#127919;Conf%':v['confidence_level'],
                     'จังหวัด':v['registered_prov'],'วัน':v['seen_days'],'ครั้ง':v['seen_count'],
                     'จุดบ่อยสุด':v['top_camera'],'APEX':'● APEX' if v.get('apex') else '','_k':k}
                    for k,v in ss_disp.items()]
            df3 = pd.DataFrame(rows).sort_values('&#9888;Risk', ascending=False).reset_index(drop=True)
            st.caption(f"&#128070; คลิกแถวเพื่อดูรายละเอียด | {len(rows)} เคส")
            ev3 = st.dataframe(df3.drop(columns=['_k']), use_container_width=True,
                               on_select='rerun', selection_mode='single-row', key='t3')
            sel = df3.iloc[ev3.selection.rows[0]]['_k'] if ev3.selection.rows else df3.iloc[0]['_k']
            st.markdown('<hr style="border-color:#1e293b;margin:14px 0;">', unsafe_allow_html=True)
            dossier(ss[sel])
