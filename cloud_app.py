import streamlit as st
import polars as pl
import pandas as pd
import numpy as np
import folium
import os
import re
import time
import sqlite3
from datetime import datetime, timedelta, timezone
from folium import plugins
from folium.plugins import MarkerCluster, HeatMap
import streamlit.components.v1 as components
import plotly.graph_objects as go
import plotly.express as px
from collections import defaultdict
import json
from io import BytesIO

# ── Cloud Auth & Sync (optional — graceful if missing) ────────────────────────
try:
    from auth import (require_login, get_current_user, has_role,
                      logout, ROLE_LABEL, render_login_page)
    from supabase_sync import (
        push_daily_report as _cloud_push_daily,
        push_realtime_session as _cloud_push_rt,
        log_upload as _cloud_log_upload,
        show_sync_status,
        is_supabase_configured,
    )
    _CLOUD_ENABLED = True
except ImportError:
    _CLOUD_ENABLED = False
    def require_login(): pass
    def get_current_user(): return None
    def has_role(*a): return True
    def logout(): pass
    def show_sync_status(): pass
    def is_supabase_configured(): return False
    ROLE_LABEL = {}

# ==========================================
# 0. ตั้งค่าระบบและไลบรารี (Configuration)
# ==========================================
st.set_page_config(page_title="HWPD 60 i-Trap Command Center", layout="wide", page_icon="🛡️", initial_sidebar_state="expanded")

import os as _os
import sys as _sys

# ★ ตรวจสอบ environment: Streamlit Cloud (Linux) vs Windows local
_IS_CLOUD = _sys.platform != 'win32' or _os.path.exists('/mount/src')

if _IS_CLOUD:
    # Streamlit Cloud — repo อยู่ที่ /mount/src/hwpd-itrap/ (read-only)
    # ใช้ /tmp สำหรับ SQLite (writable) และดึงข้อมูลจาก Supabase
    _REPO_DIR = '/mount/src/hwpd-itrap'
    DATA_DIR  = '/tmp'
else:
    DATA_DIR  = r"D:\itrap_agent"

DB_PATH      = _os.path.join(DATA_DIR, "hwpd_master_database.db")
PARQUET_PATH = _os.path.join(DATA_DIR, "hwpd_master_data.parquet")

# บน Cloud ถ้า Parquet อยู่ใน repo ให้ใช้ path นั้นแทน (read-only แต่ OK สำหรับอ่าน)
if _IS_CLOUD:
    _repo_parquet = _os.path.join(_REPO_DIR, "hwpd_master_data.parquet")
    if _os.path.exists(_repo_parquet):
        PARQUET_PATH = _repo_parquet

BORDER_PROVINCES = {
    # ── ชายแดนพม่า (Myanmar) ──────────────────────────────────────────────
    'เชียงราย',      # แม่สาย, เชียงแสน, เชียงของ
    'เชียงใหม่',     # ใกล้พม่า อ.ฝาง
    'แม่ฮ่องสอน',   # พรมแดนพม่าทั้งจังหวัด
    'ตาก',           # แม่สอด, แม่ระมาด, ท่าสองยาง
    'กาญจนบุรี',    # เจดีย์สามองค์, พุน้ำร้อน
    'ราชบุรี',       # ใกล้ชายแดนพม่าตอนใต้
    'ประจวบคีรีขันธ์', # ด่านสิงขร
    'ระนอง',        # ด่านระนอง-เกาะสอง
    'ชุมพร',        # ใกล้ระนอง
    # ── ชายแดนลาว (Laos) ─────────────────────────────────────────────────
    'เลย',           # ท่าลี่, เชียงคาน
    'หนองคาย',      # ด่านสะพานมิตรภาพ 1
    'บึงกาฬ',       # ด่านบึงกาฬ
    'นครพนม',       # สะพานมิตรภาพ 3
    'มุกดาหาร',     # สะพานมิตรภาพ 2
    'อำนาจเจริญ',   # ใกล้ลาว
    'อุบลราชธานี',  # ช่องเม็ก, วังตาล
    'อุดรธานี',     # ใกล้หนองคาย
    'น่าน',          # ชายแดนลาวตอนบน
    'พะเยา',        # ใกล้น่าน-ลาว
    # ── ชายแดนกัมพูชา (Cambodia) ─────────────────────────────────────────
    'ศรีสะเกษ',     # ช่องสะงำ, ภูมิสรอล
    'สุรินทร์',      # ช่องจอม, ด่านจอม
    'บุรีรัมย์',    # ช่องจอม
    'สระแก้ว',      # อรัญประเทศ, บ้านคลองลึก
    'จันทบุรี',      # บ้านปากาด, บ้านผักกาด
    'ตราด',          # หาดเล็ก, บ้านใหม่
    # ── ชายแดนมาเลเซีย (Malaysia) ────────────────────────────────────────
    'สงขลา',        # สะเดา, บ้านประกอบ
    'สตูล',          # วังประจัน, บ้านประกอบ
    'ยะลา',          # เบตง
    'นราธิวาส',     # สุไหงโกลก, ตากใบ, บ้านบูเก๊ะตา
    'ปัตตานี',      # ใกล้ชายแดน
}

# ── Helper: Export Excel ────────────────────────────────────────────────
def excel_download_button(df: pd.DataFrame, filename: str, label: str = "📥 Export Excel"):
    """แสดงปุ่ม Download Excel ใต้ตาราง"""
    try:
        buf = BytesIO()
        with pd.ExcelWriter(buf, engine='openpyxl') as writer:
            df.to_excel(writer, index=False, sheet_name='HWPD_Data')
        st.download_button(
            label=label,
            data=buf.getvalue(),
            file_name=filename,
            mime='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
            use_container_width=False,
        )
    except Exception as e:
        st.caption(f"⚠️ Export ไม่สำเร็จ: {e}")

# ── Helper: AI Feedback table setup ────────────────────────────────────
def ensure_feedback_table():
    """สร้าง ai_feedback table ถ้ายังไม่มี"""
    try:
        conn = sqlite3.connect(DB_PATH)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS ai_feedback (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                target_id TEXT,
                report_date TEXT,
                engine_type TEXT,
                is_correct INTEGER,
                notes TEXT,
                feedback_date TEXT
            )
        """)
        conn.commit()
        conn.close()
    except: pass

def render_feedback_widget(target_id: str, engine_type: str, report_date: str):
    """UI สำหรับบันทึก Feedback ต่อ AI — แสดงท้าย Case Dossier"""
    ensure_feedback_table()

    # ตรวจสอบว่ามี Feedback แล้วหรือยัง
    try:
        _fc = sqlite3.connect(DB_PATH)
        _prev = pd.read_sql(
            "SELECT * FROM ai_feedback WHERE target_id=? AND report_date=? "
            "ORDER BY feedback_date DESC LIMIT 1",
            _fc, params=(target_id, report_date)
        )
        _fc.close()
    except:
        _prev = pd.DataFrame()

    st.markdown("---")
    st.markdown("#### 📊 AI Feedback — บันทึกผลการตรวจสอบในภายหลัง")

    _verdict_map = {1: "✅ ถูกต้อง — ยืนยันแล้ว", 0: "❌ ไม่ถูกต้อง", -1: "⚠️ ยังไม่ทราบ"}
    _cur_label = "⚠️ ยังไม่ทราบ"
    if not _prev.empty:
        _cur_label = _verdict_map.get(int(_prev.iloc[0]['is_correct']), "⚠️ ยังไม่ทราบ")
        st.info(f"บันทึกล่าสุด: **{_cur_label}** | {_prev.iloc[0]['feedback_date']}")

    with st.form(key=f"fb_{target_id}_{report_date}"):
        st.caption(f"เป้าหมาย: `{target_id}` | ประเภท: {engine_type} | วันที่: {report_date}")
        col_v, col_n = st.columns([2, 3])
        with col_v:
            verdict = st.radio(
                "ผลการตรวจสอบ:",
                ["✅ ถูกต้อง — ยืนยันแล้ว", "❌ ไม่ถูกต้อง", "⚠️ ยังไม่ทราบ"],
                index=["✅ ถูกต้อง — ยืนยันแล้ว", "❌ ไม่ถูกต้อง", "⚠️ ยังไม่ทราบ"].index(_cur_label),
                key=f"v_{target_id}_{report_date}"
            )
        with col_n:
            notes = st.text_area(
                "หมายเหตุ:", height=80,
                value=_prev.iloc[0]['notes'] if not _prev.empty and _prev.iloc[0]['notes'] else "",
                placeholder="รายละเอียดผลการตรวจสอบ...",
                key=f"n_{target_id}_{report_date}"
            )
        if st.form_submit_button("💾 บันทึก Feedback"):
            is_correct = 1 if "ถูกต้อง" in verdict else 0 if "ไม่ถูก" in verdict else -1
            try:
                _fw = sqlite3.connect(DB_PATH)
                _fw.execute(
                    "INSERT INTO ai_feedback "
                    "(target_id, report_date, engine_type, is_correct, notes, feedback_date) "
                    "VALUES (?,?,?,?,?,?)",
                    (target_id, report_date, engine_type, is_correct, notes,
                     datetime.now().strftime('%Y-%m-%d %H:%M:%S'))
                )
                _fw.commit()
                _fw.close()
                st.success("✅ บันทึก Feedback เรียบร้อยแล้ว")
                st.rerun()
            except Exception as _fe:
                st.error(f"❌ บันทึกไม่สำเร็จ: {_fe}")



# ── Realtime Mode Helpers ──────────────────────────────────────────────────

def ensure_realtime_table():
    try:
        conn = sqlite3.connect(DB_PATH)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS realtime_session (
                session_date TEXT PRIMARY KEY,
                raw_data_json TEXT,
                upload_count  INTEGER DEFAULT 1,
                first_record_time TEXT,
                last_record_time  TEXT,
                updated_at TEXT
            )
        """)
        conn.commit(); conn.close()
    except: pass

def save_realtime_session(active_db_pd: pd.DataFrame, session_date: str):
    """เก็บ/สะสมข้อมูล Realtime ของวันนี้"""
    ensure_realtime_table()
    try:
        conn = sqlite3.connect(DB_PATH)
        existing = conn.execute(
            "SELECT raw_data_json, upload_count FROM realtime_session WHERE session_date=?",
            (session_date,)
        ).fetchone()
        if existing and existing[0]:
            old_df = pd.read_json(existing[0])
            if 'Datetime' in old_df.columns: old_df['Datetime'] = pd.to_datetime(old_df['Datetime'])
            new_df = active_db_pd.copy()
            if 'Datetime' in new_df.columns: new_df['Datetime'] = pd.to_datetime(new_df['Datetime'])
            combined = pd.concat([old_df, new_df], ignore_index=True)
            _dd = [c for c in ['Datetime','ทะเบียน_Full','จุดติดตั้งกล้อง'] if c in combined.columns]
            if _dd: combined = combined.drop_duplicates(subset=_dd)
            upload_count = existing[1] + 1
        else:
            combined = active_db_pd.copy()
            if 'Datetime' in combined.columns: combined['Datetime'] = pd.to_datetime(combined['Datetime'])
            upload_count = 1
        first_t = str(combined['Datetime'].min()) if 'Datetime' in combined.columns else '-'
        last_t  = str(combined['Datetime'].max()) if 'Datetime' in combined.columns else '-'
        conn.execute("""INSERT OR REPLACE INTO realtime_session
            (session_date, raw_data_json, upload_count, first_record_time, last_record_time, updated_at)
            VALUES (?,?,?,?,?,?)""",
            (session_date, combined.to_json(), upload_count, first_t, last_t,
             datetime.now().strftime('%Y-%m-%d %H:%M:%S')))
        conn.commit(); conn.close()
    except: pass

@st.cache_data(ttl=1800, show_spinner=False)  # cache 30 นาที — ลด Supabase Egress
def load_realtime_session(session_date: str):
    if not is_supabase_configured():
        return None
    try:
        from supabase_sync import pull_parquet_from_cloud, get_supabase_client

        # 1. Pull metadata from cloud_realtime table
        client = get_supabase_client()
        res = client.table('cloud_realtime').select(
            'upload_count, first_record_time, last_record_time, updated_at'
        ).eq('session_date', session_date).execute()
        meta = res.data[0] if res.data else {}

        # 2. Pull the actual raw data from Cloud Storage Parquet
        df_pl = pull_parquet_from_cloud(session_date)
        if df_pl is None or df_pl.is_empty():
            return None

        df = df_pl.to_pandas()
        if 'Datetime' in df.columns:
            df['Datetime'] = pd.to_datetime(df['Datetime'])

        return {
            'df': df,
            'upload_count': meta.get('upload_count', 1),
            'first_time': meta.get('first_record_time', str(df['Datetime'].min()) if not df.empty else '-'),
            'last_time': meta.get('last_record_time', str(df['Datetime'].max()) if not df.empty else '-'),
            'updated_at': meta.get('updated_at', '-')
        }
    except Exception as _e:
        import traceback as _tb
        import streamlit as _st
        _st.session_state['_rt_load_error'] = f"{_e}\n{_tb.format_exc()}"
        return None

def generate_rt_recommendation(engine_type: str, confidence: str, n_cams: int, last_cam: str) -> str:
    if confidence == 'confirmed':
        if 'สวมทะเบียน' in engine_type:
            return (f"🚨 <b>ดำเนินการทันที</b> — ตรวจจับยานพาหนะบริเวณ <b>{last_cam}</b> "
                    f"ประสานหน่วยปฏิบัติการใกล้เคียง ตรวจสอบป้ายทะเบียนแท้จริง และบันทึกหลักฐาน")
        elif 'ขบวน' in engine_type:
            return (f"🚘 <b>แจ้งเตือนด่วน</b> — ขบวนรถสะสมผ่าน <b>{n_cams}</b> ด่านแล้ว "
                    f"ปัจจุบันอยู่บริเวณ <b>{last_cam}</b> ประสานกำลังสกัดกั้นเส้นทางข้างหน้า")
        else:
            return (f"⚠️ <b>ตรวจสอบเพิ่มเติม</b> — พฤติกรรมผิดปกติผ่าน {n_cams} กล้อง "
                    f"ขอหมายตรวจค้นยานพาหนะล่าสุดที่ <b>{last_cam}</b>")
    else:
        need = max(1, 4 - n_cams)
        return (f"👁️ <b>เฝ้าระวัง</b> — พบ {n_cams} กล้อง ยังไม่เพียงพอยืนยัน "
                f"รอข้อมูลเพิ่มอีก <b>{need} กล้อง</b> ก่อนดำเนินการ — "
                f"ติดตามจากกล้องถัดไปหลัง <b>{last_cam}</b>")

def render_realtime_tab(selected_date: str, rt_active_db: pd.DataFrame, rt_priority_df: pd.DataFrame):
    """แสดงผล Realtime Intelligence Tab — ใช้ข้อมูลที่โหลดอยู่แล้ว ไม่ต้อง serialize"""

    # ── Debug info ──────────────────────────────────────────────────────────
    _db_rows  = len(rt_active_db) if not rt_active_db.empty else 0
    _pri_rows = len(rt_priority_df) if not rt_priority_df.empty else 0
    st.caption(f"🔍 Debug: วันที่={selected_date} | active_db={_db_rows:,} rows | priority={_pri_rows} rows")

    if rt_active_db.empty:
        st.warning(f"⚠️ ไม่มีข้อมูลสำหรับวัน **{selected_date}** — กรุณาเลือกวันที่มีข้อมูล หรืออัปโหลดก่อน")
        return


    # ── ใช้ active_db โดยตรง ─────────────────────────────────────────────
    rt_df = rt_active_db  # ไม่ copy — อ่านอย่างเดียว ประหยัด RAM 142K rows
    if 'Datetime' in rt_df.columns and not pd.api.types.is_datetime64_any_dtype(rt_df['Datetime']):
        rt_df = rt_df.assign(Datetime=pd.to_datetime(rt_df['Datetime']))

    # Time range
    try:
        first_str = rt_df['Datetime'].min().strftime('%H:%M') + ' น.'
        last_str  = rt_df['Datetime'].max().strftime('%H:%M') + ' น.'
    except:
        first_str = last_str = '-'

    n_records  = len(rt_df)
    n_cams_tot = rt_df['จุดติดตั้งกล้อง'].nunique() if 'จุดติดตั้งกล้อง' in rt_df.columns else 0
    upload_count = st.session_state.get('_rt_upload_count', 1)

    # ── รัน Realtime Engine (cache ต่อ session) ────────────────────
    _rt_cache_key = f"rt_pri_{len(rt_df)}_{rt_df['Datetime'].max() if 'Datetime' in rt_df.columns else ''}"
    if st.session_state.get('_rt_cache_key') == _rt_cache_key and '_rt_pri_cache' in st.session_state:
        rt_pri = st.session_state['_rt_pri_cache']  # ใช้ cache ไม่รัน engine ซ้ำ
    else:
        with st.spinner('⚡ วิเคราะห์ Realtime... (คิดครั้งเดียว)'):
            try:
                rt_pri = run_realtime_intelligence(pl.from_pandas(rt_df))
                st.session_state['_rt_pri_cache'] = rt_pri
                st.session_state['_rt_cache_key'] = _rt_cache_key
            except Exception as _re:
                st.caption(f'⚠️ Engine error: {_re}')
                rt_pri = pd.DataFrame()

    # ── Lower-threshold → 🟡 น่าสงสัย (≥2 cameras, not already confirmed) ─
    _conf_plates = set()
    if not rt_pri.empty:
        for _r in rt_pri.to_dict('records'):   # to_dict เร็วกว่า iterrows ~5x
            for _p in (_r.get('Cars_List') or [_r.get('Target_ID', '')]):
                _conf_plates.add(str(_p))

    _watch_df = pd.DataFrame()
    try:
        if 'ทะเบียน_Full' in rt_df.columns and 'จุดติดตั้งกล้อง' in rt_df.columns:
            _cam_col = 'จุดติดตั้งกล้อง'
            _grp = (rt_df.groupby('ทะเบียน_Full')
                    .agg(n_cams=(_cam_col, 'nunique'),
                         last_time=('Datetime', 'max') if 'Datetime' in rt_df.columns else ('ทะเบียน_Full','count'),
                         n_rec=('ทะเบียน_Full', 'count'))
                    .reset_index())
            _grp = _grp[(_grp['n_cams'] >= 3) & (~_grp['ทะเบียน_Full'].isin(_conf_plates))]  # ≥ 3 กล้อง
            _grp = _grp.sort_values('n_cams', ascending=False).head(50)  # top 50 เท่านั้น
            # Precompute cam lists (vectorized unique, faster than lambda)
            _cam_map = rt_df.groupby('ทะเบียน_Full')[_cam_col].unique()
            _rows = []
            for _, _r in _grp.iterrows():
                _pl   = _r['ทะเบียน_Full']
                _cams = list(_cam_map.get(_pl, ['-']))
                _lc   = str(_cams[-1]) if _cams else '-'
                try:    _lt = pd.to_datetime(_r['last_time']).strftime('%H:%M น.')
                except: _lt = '-'
                _reas = f"พบที่ {len(_cams)} กล้อง: {', '.join(str(c) for c in _cams[:3])}{'...' if len(_cams)>3 else ''}"
                _rec  = generate_rt_recommendation('น่าสงสัย', 'watching', int(_r['n_cams']), _lc)
                _rows.append({'plate':_pl,'n_cams':_r['n_cams'],'last_cam':_lc,
                              'last_time':_lt,'cams_list':_cams,'_reason':_reas,'_rec':_rec})
            _watch_df = pd.DataFrame(_rows)
    except Exception as _we:
        _watch_df = pd.DataFrame()

    n_confirmed = len(rt_pri) if not rt_pri.empty else 0
    n_watching  = len(_watch_df)

    # ── Header ────────────────────────────────────────────────────────────
    st.markdown(f"""
    <div style='background:linear-gradient(135deg,rgba(239,68,68,0.12),rgba(245,158,11,0.08),rgba(15,23,42,0.5));
        border:1px solid rgba(239,68,68,0.35);border-radius:18px;padding:24px 28px;margin-bottom:24px;
        box-shadow:0 4px 40px rgba(239,68,68,0.08);'>
      <div style='display:flex;align-items:center;gap:14px;margin-bottom:18px;'>
        <span style='font-size:32px;'>⚡</span>
        <div>
          <div style='display:flex;align-items:center;gap:10px;'>
            <span style='font-size:18px;font-weight:800;color:#fca5a5;letter-spacing:2px;'>
              REALTIME INTELLIGENCE</span>
            <span style='background:#ef4444;color:white;padding:3px 12px;border-radius:20px;
              font-size:10px;font-weight:700;letter-spacing:1px;'>● LIVE</span>
          </div>
          <div style='font-size:12px;color:#64748b;margin-top:3px;'>
            ข้อมูลสะสมระหว่างวัน — วิเคราะห์อัตโนมัติทุกครั้งที่อัปโหลด</div>
        </div>
      </div>
      <div style='display:grid;grid-template-columns:repeat(3,1fr);gap:16px;text-align:center;'>
        <div style='background:rgba(255,255,255,0.04);border-radius:12px;padding:16px 6px;'>
          <div style='font-size:10px;color:#64748b;text-transform:uppercase;letter-spacing:1px;'>📊 รายการทั้งหมด</div>
          <div style='font-size:30px;font-weight:900;color:#f1f5f9;margin-top:5px;'>{n_records:,}</div>
        </div>
        <div style='background:rgba(239,68,68,0.1);border-radius:12px;padding:16px 6px;
          border:1px solid rgba(239,68,68,0.25);'>
          <div style='font-size:10px;color:#fca5a5;text-transform:uppercase;letter-spacing:1px;'>🔴 ยืนยัน</div>
          <div style='font-size:30px;font-weight:900;color:#f87171;margin-top:5px;'>{n_confirmed}</div>
        </div>
        <div style='background:rgba(245,158,11,0.08);border-radius:12px;padding:16px 6px;
          border:1px solid rgba(245,158,11,0.2);'>
          <div style='font-size:10px;color:#fde68a;text-transform:uppercase;letter-spacing:1px;'>🟡 น่าสงสัย</div>
          <div style='font-size:30px;font-weight:900;color:#fbbf24;margin-top:5px;'>{n_watching}</div>
        </div>
      </div>
      <div style='margin-top:16px;padding-top:14px;border-top:1px solid rgba(255,255,255,0.06);
        font-size:13px;color:#94a3b8;display:flex;gap:24px;flex-wrap:wrap;'>
        <span>⏰ เริ่มตั้งแต่ <b style='color:#e2e8f0;'>{first_str}</b></span>
        <span>🔄 อัปเดตล่าสุด <b style='color:#10b981;'>{last_str}</b></span>
        <span>📅 วันที่ <b style='color:#a5b4fc;'>{selected_date}</b></span>
      </div>
    </div>""", unsafe_allow_html=True)

    # ── Helper: show one type as table ────────────────────────────────────
    # Pre-build plate lookup once (O(n)) — avoid O(n×m) scan inside loop
    _plate_nc  = {}
    _plate_lc  = {}
    _plate_lt  = {}
    if 'ทะเบียน_Full' in rt_df.columns:
        _sorted_rt = rt_df.sort_values('Datetime') if 'Datetime' in rt_df.columns else rt_df
        _plate_nc  = _sorted_rt.groupby('ทะเบียน_Full')['จุดติดตั้งกล้อง'].nunique().to_dict() \
                     if 'จุดติดตั้งกล้อง' in rt_df.columns else {}
        _plate_lc  = _sorted_rt.groupby('ทะเบียน_Full')['จุดติดตั้งกล้อง'].last().to_dict() \
                     if 'จุดติดตั้งกล้อง' in rt_df.columns else {}
        if 'Datetime' in rt_df.columns:
            _plate_lt = (_sorted_rt.groupby('ทะเบียน_Full')['Datetime'].max()
                         .apply(lambda x: x.strftime('%H:%M น.') if pd.notna(x) else '-').to_dict())

    def _rt_table(conf_df, watch_df, kw, tab_key, icon):
        _cf = pd.DataFrame()
        if not conf_df.empty and 'ประเภท' in conf_df.columns:
            _cf = conf_df[conf_df['ประเภท'].str.contains(kw, na=False)] if kw else conf_df

        rows = []
        for _r in _cf.to_dict('records'):   # to_dict เร็วกว่า iterrows ~5x
            _cars  = _r.get('Cars_List') or [_r.get('Target_ID', '-')]
            if not isinstance(_cars, list): _cars = [str(_cars)]
            _plate_display = ' / '.join(str(c) for c in _cars[:3]) + ('...' if len(_cars) > 3 else '')
            _plate_first   = str(_cars[0]) if _cars else '-'
            _nc    = max(_plate_nc.get(c, 0) for c in _cars) if _cars else len(_cars)
            _lc    = str(_plate_lc.get(_plate_first, '-'))
            _lt    = _plate_lt.get(_plate_first, '-')
            _reas  = str(_r.get('พฤติกรรมต้องสงสัย', _r.get('เหตุผลหลัก', _r.get('เหตุผล', '-'))))[:160]
            _rec   = generate_rt_recommendation(str(_r.get('ประเภท','')), 'confirmed', _nc, _lc)
            _scr   = _r.get('Risk Score', _r.get('คะแนนรวม', 0))
            _tid   = str(_r.get('Target_ID', _plate_first))   # ← เก็บ Target_ID จริง
            rows.append({'ระดับ':'🔴 ยืนยัน','ทะเบียน':_plate_display,'กล้องที่พบ':_nc,
                         'กล้องล่าสุด':_lc,'เวลาล่าสุด':_lt,
                         'Score': str(int(float(str(_scr)))) if str(_scr).replace('.','').lstrip('-').isdigit() and str(_scr) not in ('-','') else '-',
                         '_r':_reas,'_rec':_rec,'_type':str(_r.get('ประเภท','')),'_cars':_cars,
                         '_tid':_tid})  # ← Target_ID

        for _r in watch_df.to_dict('records'):   # to_dict เร็วกว่า iterrows
            rows.append({'ระดับ':'🟡 น่าสงสัย','ทะเบียน':_r['plate'],'กล้องที่พบ':_r['n_cams'],
                         'กล้องล่าสุด':_r['last_cam'],'เวลาล่าสุด':_r['last_time'],'Score':'-',
                         '_r':_r['_reason'],'_rec':_r['_rec'],'_type':'น่าสงสัย',
                         '_cars':[_r['plate']],'_tid':_r['plate']})

        if not rows:
            st.info(f"⚠️ ยังไม่พบ {icon} ในขณะนี้ — รอข้อมูลจากกล้องเพิ่มเติม")
            return

        _full = pd.DataFrame(rows)
        _disp = _full[['ระดับ','ทะเบียน','กล้องที่พบ','กล้องล่าสุด','เวลาล่าสุด','Score']].copy()
        _disp['Score'] = _disp['Score'].astype(str)  # ป้องกัน ArrowInvalid mixed-type

        st.caption("🖱️ คลิกแถวเพื่อดูเหตุผล AI + คำแนะนำ + แผนที่ด้านล่าง")
        _ev = st.dataframe(_disp, use_container_width=True, hide_index=True,
                           on_select="rerun", selection_mode="single-row", key=f"rt_{tab_key}")
        excel_download_button(_disp, f"realtime_{tab_key}_{selected_date}.xlsx",
                              "📥 Export ตารางนี้ (Excel)")

        if _ev.selection.rows:
            _sel    = _full.iloc[_ev.selection.rows[0]]
            _isconf = _sel['ระดับ'] == '🔴 ยืนยัน'
            _border = '#ef4444' if _isconf else '#f59e0b'
            _badge  = '🔴 ยืนยันแล้ว' if _isconf else '🟡 น่าสงสัย'
            _tid    = _sel.get('_tid', _sel['ทะเบียน'])

            st.markdown("---")
            st.markdown(f"### {icon} **{_sel['ทะเบียน']}** — {_badge}")

            _cA, _cB = st.columns(2)
            with _cA:
                st.markdown(f"""
                <div style='background:rgba(15,23,42,0.88);border-left:4px solid #f59e0b;
                    padding:20px;border-radius:14px;min-height:120px;'>
                    <div style='font-size:10px;color:#94a3b8;text-transform:uppercase;
                        letter-spacing:2px;margin-bottom:10px;'>🔍 เหตุผล AI</div>
                    <div style='color:#fef3c7;font-size:14px;line-height:1.9;'>{_sel['_r']}</div>
                    <div style='margin-top:14px;padding-top:10px;border-top:1px solid rgba(255,255,255,0.07);
                        font-size:12px;color:#94a3b8;'>
                        ประเภท: <b style='color:#93c5fd;'>{_sel['_type']}</b> &nbsp;|&nbsp;
                        พบ: <b style='color:#a5b4fc;'>{_sel['กล้องที่พบ']} กล้อง</b> &nbsp;|&nbsp;
                        ล่าสุด: <b style='color:#6ee7b7;'>{_sel['เวลาล่าสุด']}</b>
                    </div>
                </div>""", unsafe_allow_html=True)
            with _cB:
                _bg = 'rgba(239,68,68,0.12)' if _isconf else 'rgba(245,158,11,0.10)'
                st.markdown(f"""
                <div style='background:{_bg};border-left:4px solid {_border};
                    padding:20px;border-radius:14px;min-height:120px;'>
                    <div style='font-size:10px;color:#94a3b8;text-transform:uppercase;
                        letter-spacing:2px;margin-bottom:10px;'>🤖 AI แนะนำ</div>
                    <div style='color:#f1f5f9;font-size:14px;line-height:1.9;'>{_sel['_rec']}</div>
                </div>""", unsafe_allow_html=True)

            # ── Case Dossier: MAP + Radar + Timeline (🔴 เท่านั้น) ────────────
            _dossier_shown = False
            if _isconf and not rt_pri.empty:
                _matched = rt_pri[rt_pri['Target_ID'] == _tid]
                if not _matched.empty:
                    render_case_dossier(_tid, rt_df, rt_pri)
                    _dossier_shown = True
                else:
                    # fallback: ลอง match ด้วย plate แรก
                    _fb = rt_pri[rt_pri['Target_ID'].str.contains(
                        str(_sel['_cars'][0]) if _sel['_cars'] else '', na=False, regex=False)]
                    if not _fb.empty:
                        render_case_dossier(_fb.iloc[0]['Target_ID'], rt_df, rt_pri)
                        _dossier_shown = True

            # ── 🟡 น่าสงสัย OR 🔴 ที่ dossier lookup ไม่เจอ ──────────────────
            # สร้าง synthetic target_info แล้วเรียก render_case_dossier เพื่อให้
            # ได้ Radar + Intel Summary + Map + Time-Space Diagram + ตาราง เหมือนกัน
            if not _dossier_shown:
                _plate_val = (_sel['_cars'][0]
                              if isinstance(_sel.get('_cars'), list) and _sel['_cars']
                              else _sel['ทะเบียน'])
                _ph = (rt_df[rt_df['ทะเบียน_Full'] == _plate_val].copy()
                       if 'ทะเบียน_Full' in rt_df.columns else pd.DataFrame())

                if not _ph.empty:
                    # ── คำนวณ Radar scores จาก raw data ────────────────────────
                    _n_cams_s  = _ph['จุดติดตั้งกล้อง'].nunique() if 'จุดติดตั้งกล้อง' in _ph.columns else 0
                    _night_n   = int((_ph['Is_Night'] == True).sum()) if 'Is_Night' in _ph.columns else 0
                    _border_n  = int((_ph['Zone'] == 'A').sum()) if 'Zone' in _ph.columns else 0
                    _r_night   = min(20, _night_n * 3)
                    _r_border  = min(30, _border_n * 5)
                    _r_shuttle = min(20, _n_cams_s * 3)
                    _r_regional = min(10, 4)
                    _score_int = _r_night + _r_border + _r_shuttle + _r_regional

                    # ── Synthetic target row → render_case_dossier ─────────────
                    _syn_row = pd.Series({
                        'Target_ID':           _plate_val,
                        'Cars_List':           [_plate_val],
                        'ประเภท':              'กลุ่มรถต้องสงสัย',
                        'พฤติกรรมต้องสงสัย':  _sel.get('_r', '-'),
                        'Risk Score':          f"{_score_int}%",
                        'Radar_Data':          {
                            'Night':    _r_night,
                            'Border':   _r_border,
                            'Shuttle':  _r_shuttle,
                            'Regional': _r_regional,
                            'Convoy':   0,
                        },
                        'เป้าหมาย':           _plate_val,
                        'คะแนนรวม':           _score_int,
                        'Total_Dist':          '-',
                        'ระยะห่างเฉลี่ย':      '-',
                    })
                    _syn_df = pd.DataFrame([_syn_row])
                    render_case_dossier(_plate_val, rt_df, _syn_df)
                else:
                    st.info("ℹ️ ไม่พบข้อมูลการเคลื่อนที่สำหรับทะเบียนนี้")


    # ── 3 sub-tabs: convoy filter Cars_List ≥ 2 ──────────────────────────────
    def _cars_len(cars):
        import ast
        if isinstance(cars, list): return len(cars)
        try: return len(ast.literal_eval(str(cars)))
        except: return 0

    _nc = 0; _nv = 0; _real_convoy = pd.DataFrame(); _susp_c = pd.DataFrame()
    if not rt_pri.empty and 'ประเภท' in rt_pri.columns:
        _clone_mask  = rt_pri['ประเภท'].str.contains('สวมทะเบียน', na=False)
        _convoy_mask = rt_pri['ประเภท'].str.contains('ขบวน', na=False)
        _nc = int(_clone_mask.sum())
        _convoy_rows = rt_pri[_convoy_mask]
        if not _convoy_rows.empty and 'Cars_List' in _convoy_rows.columns:
            _real_mask   = _convoy_rows['Cars_List'].apply(_cars_len) >= 2
            _real_convoy = _convoy_rows[_real_mask].reset_index(drop=True)
            _fake_convoy = _convoy_rows[~_real_mask]
        else:
            _real_convoy = pd.DataFrame(); _fake_convoy = _convoy_rows
        _nv = len(_real_convoy)
        _other  = rt_pri[~_clone_mask & ~_convoy_mask]
        _susp_c = pd.concat([_other, _fake_convoy], ignore_index=True)
    _ns = len(_susp_c) + n_watching

    rtt1, rtt2, rtt3 = st.tabs([f"🚗 สวมทะเบียน ({_nc})", f"🚘 ขบวนรถ ({_nv})", f"🔍 ต้องสงสัย ({_ns})"])
    with rtt1: _rt_table(rt_pri,       pd.DataFrame(), 'สวมทะเบียน', 'clone',  '🚗')
    with rtt2: _rt_table(_real_convoy,  pd.DataFrame(), '',           'convoy', '🚘')
    with rtt3: _rt_table(_susp_c,       _watch_df,      '',           'susp',   '🔍')


# 🛡️ CSS Dual-Theme (Dark + Light)
if 'theme' not in st.session_state:
    st.session_state['theme'] = 'dark'

_dark_css = """    /* ═══ DARK MODE ═══ */



    @import url('https://fonts.googleapis.com/css2?family=Sarabun:wght@300;400;500;600;700;800&display=swap');
    html, body { font-family: 'Sarabun', 'TH Sarabun PSK', 'TH Sarabun New', sans-serif !important; font-size: 16px !important; background: #0a0e1a !important; }
    .stApp { background: linear-gradient(135deg, #0a0e1a 0%, #0d1321 50%, #0a1628 100%) !important; min-height: 100vh; }
    .main { background: transparent !important; }
    .block-container { padding-top: 3.5rem !important; padding-left: 2rem !important; padding-right: 2rem !important; max-width: 100% !important; }
    /* Sidebar */
    section[data-testid="stSidebar"] { background: linear-gradient(180deg, #0d1321 0%, #0f172a 100%) !important; border-right: 1px solid rgba(59,130,246,0.15) !important; }
    section[data-testid="stSidebar"] > div { background: transparent !important; }
    /* Sidebar text colors (NOT wildcard to preserve collapse button) */
    section[data-testid="stSidebar"] p,
    section[data-testid="stSidebar"] span,
    section[data-testid="stSidebar"] label,
    section[data-testid="stSidebar"] .stMarkdown { color: #e2e8f0 !important; }
    section[data-testid="stSidebar"] hr { border-color: rgba(59,130,246,0.2) !important; }
    /* Sidebar buttons (stButton only, not native collapse button) */
    section[data-testid="stSidebar"] .stButton > button { background: rgba(30,41,59,0.7) !important; border: 1px solid rgba(59,130,246,0.25) !important; color: #93c5fd !important; border-radius: 8px !important; font-size: 13px !important; font-weight: 600 !important; width: 100% !important; transition: all 0.2s ease !important; }
    section[data-testid="stSidebar"] .stButton > button:hover { background: rgba(59,130,246,0.25) !important; border-color: rgba(59,130,246,0.5) !important; color: #dbeafe !important; }
    /* Radio */
    section[data-testid="stSidebar"] .stRadio label { color: #cbd5e1 !important; }
    /* Universal Tabs CSS */
    [data-testid="stTabs"] button, .stTabs button, [data-baseweb="tab"] { 
        background: rgba(15,23,42,0.5) !important; 
        border-radius: 12px !important; 
        padding: 16px 32px !important; 
        margin-right: 8px !important; 
        border: 1px solid rgba(59,130,246,0.2) !important;
    }
    [data-testid="stTabs"] button *, .stTabs button *, [data-baseweb="tab"] * { 
        color: #94a3b8 !important; 
        font-size: 24px !important; 
        font-weight: 800 !important; 
    }
    /* Hover */
    [data-testid="stTabs"] button:hover, .stTabs button:hover, [data-baseweb="tab"]:hover { 
        background: rgba(59,130,246,0.3) !important; 
        border-color: rgba(96,165,250,0.5) !important;
    }
    [data-testid="stTabs"] button:hover *, .stTabs button:hover *, [data-baseweb="tab"]:hover * { 
        color: #ffffff !important; 
    }
    /* Active */
    [data-testid="stTabs"] button[aria-selected="true"], .stTabs button[aria-selected="true"], [data-baseweb="tab"][aria-selected="true"] { 
        background: linear-gradient(135deg, rgba(30, 58, 138, 1.0), rgba(30, 64, 175, 1.0)) !important; 
        border: 2px solid rgba(96, 165, 250, 0.8) !important; 
        box-shadow: 0 4px 16px rgba(59, 130, 246, 0.4) !important; 
    }
    [data-testid="stTabs"] button[aria-selected="true"] *, .stTabs button[aria-selected="true"] *, [data-baseweb="tab"][aria-selected="true"] * { 
        color: #ffffff !important; 
        font-weight: 900 !important; 
    }
    /* Hide red bottom line */
    [data-testid="stTabs"] button[aria-selected="true"] > div, .stTabs button[aria-selected="true"] > div, [data-baseweb="tab"][aria-selected="true"] > div, [data-baseweb="tab-highlight"] { 
        display: none !important; 
    }
    /* Enforce space between tabs */
    [data-testid="stTabs"] > div > div { gap: 8px !important; }
    /* Text */
    h1, h2, h3 { color: #e2e8f0 !important; font-weight: 700 !important; }
    h4 { color: #94a3b8 !important; font-weight: 600 !important; }
    p, div, span { color: #cbd5e1; }
    hr { border-color: rgba(59,130,246,0.1) !important; margin: 20px 0 !important; }
    /* Inputs */
    [data-testid="stSelectbox"] > div > div { background: #ffffff !important; border: 1px solid #94a3b8 !important; border-radius: 8px !important; color: #0f172a !important; }
    [data-testid="stSelectbox"] div[data-baseweb="select"] span { color: #0f172a !important; font-size: 18px !important; font-weight: 700 !important; }
    [data-testid="stSelectbox"] div[data-baseweb="select"] div[role="button"] { color: #0f172a !important; font-size: 18px !important; font-weight: 700 !important; }
    [data-testid="stSelectbox"] ul[role="listbox"] { background: #ffffff !important; color: #0f172a !important; }
    [data-testid="stSelectbox"] ul[role="listbox"] li { color: #0f172a !important; font-size: 18px !important; font-weight: 700 !important; padding-top: 12px !important; padding-bottom: 12px !important; }
    .stTextInput input { background: rgba(15,23,42,0.8) !important; border: 1px solid rgba(59,130,246,0.2) !important; border-radius: 8px !important; color: #e2e8f0 !important; }
    .stButton > button { background: linear-gradient(135deg, rgba(29,78,216,0.3), rgba(99,102,241,0.3)) !important; border: 1px solid rgba(59,130,246,0.3) !important; color: #93c5fd !important; border-radius: 8px !important; font-weight: 600 !important; font-size: 13px !important; transition: all 0.2s ease !important; }
    .stButton > button:hover { background: linear-gradient(135deg, rgba(29,78,216,0.5), rgba(99,102,241,0.5)) !important; color: #dbeafe !important; box-shadow: 0 4px 16px rgba(59,130,246,0.2) !important; transform: translateY(-1px); }
    /* ปุ่มที่ไม่มี use_container_width (ไม่มี inline style width) → pill เล็ก กึ่งกลาง */
    :not([data-testid="stSidebar"]) .stButton > button:not([style]) {
        width: fit-content !important; min-width: 80px !important;
        padding: 5px 18px !important; font-size: 12px !important;
        border-radius: 20px !important; display: block !important; margin: 0 auto !important;
    }
    :not([data-testid="stSidebar"]) .stButton:has(> button:not([style])) {
        display: flex !important; justify-content: center !important;
    }
    [data-testid="stAlert"] { background: rgba(15,23,42,0.7) !important; border-radius: 10px !important; border: 1px solid rgba(59,130,246,0.2) !important; color: #94a3b8 !important; }
    [data-testid="stFileUploader"] { background: rgba(15,23,42,0.6) !important; border: 2px dashed rgba(59,130,246,0.25) !important; border-radius: 12px !important; }
    [data-testid="stCheckbox"] label { color: #e2e8f0 !important; }
    .stDataFrame { border-radius: 12px !important; overflow: hidden !important; border: 1px solid rgba(59,130,246,0.12) !important; }
    [data-testid="stDataFrame"] > div { background: rgba(15,23,42,0.6) !important; }
    /* ═══ SHARED (both themes) ═══ */
    @keyframes pulse-border { 0% { box-shadow: 0 0 0 0 rgba(239,68,68,0.6); } 70% { box-shadow: 0 0 0 12px rgba(239,68,68,0); } 100% { box-shadow: 0 0 0 0 rgba(239,68,68,0); } }
    @keyframes shimmer { 0% { left: -100%; } 100% { left: 200%; } }
    @keyframes blink-green { 0%, 100% { opacity: 1; box-shadow: 0 0 6px #10b981; } 50% { opacity: 0.3; box-shadow: none; } }
    @keyframes ticker { 0% { transform: translateX(100%); } 100% { transform: translateX(-100%); } }
    .live-dot { display: inline-block; width: 9px; height: 9px; border-radius: 50%; background-color: #10b981; margin-right: 8px; animation: blink-green 1.5s infinite; }
    .ticker-wrap { width: 100%; overflow: hidden; background: linear-gradient(90deg, #020617, #0f172a, #020617); padding: 9px 0; margin-bottom: 16px; white-space: nowrap; border-radius: 8px; color: #38bdf8; border: 1px solid rgba(56,189,248,0.15); }
    .ticker-content { display: inline-block; animation: ticker 35s linear infinite; font-weight: 500; font-family: 'Sarabun', 'TH Sarabun PSK', sans-serif; letter-spacing: 1.5px; font-size: 13px; }
    .metric-card { padding: 20px 16px; border-radius: 14px; text-align: center; margin-bottom: 16px; border: 1px solid rgba(255,255,255,0.07); position: relative; overflow: hidden; backdrop-filter: blur(12px); transition: transform 0.2s ease, box-shadow 0.2s ease; }
    .metric-card::before { content: ''; position: absolute; top: 0; left: 0; right: 0; height: 3px; border-radius: 14px 14px 0 0; }
    .metric-card:hover { transform: translateY(-3px); }
    .card-apex { background: linear-gradient(145deg, rgba(159,18,57,0.18), rgba(30,10,25,0.65)); box-shadow: 0 4px 24px rgba(159,18,57,0.15); }
    .card-apex::before { background: linear-gradient(90deg, #9f1239, #e11d48); }
    .card-apex .metric-value { color: #fda4af; } .card-apex .metric-label { color: #fecdd3; }
    .card-clone { background: linear-gradient(145deg, rgba(234,88,12,0.16), rgba(30,15,5,0.65)); box-shadow: 0 4px 24px rgba(234,88,12,0.12); }
    .card-clone::before { background: linear-gradient(90deg, #ea580c, #f97316); }
    .card-clone .metric-value { color: #fdba74; } .card-clone .metric-label { color: #fed7aa; }
    .card-car { background: linear-gradient(145deg, rgba(59,130,246,0.16), rgba(5,15,40,0.65)); box-shadow: 0 4px 24px rgba(59,130,246,0.12); }
    .card-car::before { background: linear-gradient(90deg, #2563eb, #3b82f6); }
    .card-car .metric-value { color: #93c5fd; } .card-car .metric-label { color: #bfdbfe; }
    .card-anomaly { background: linear-gradient(145deg, rgba(99,102,241,0.16), rgba(10,5,40,0.65)); box-shadow: 0 4px 24px rgba(99,102,241,0.12); }
    .card-anomaly::before { background: linear-gradient(90deg, #6366f1, #8b5cf6); }
    .card-anomaly .metric-value { color: #a5b4fc; } .card-anomaly .metric-label { color: #c7d2fe; }
    .card-watch { background: linear-gradient(145deg, rgba(234,179,8,0.16), rgba(30,20,5,0.65)); box-shadow: 0 4px 24px rgba(234,179,8,0.12); }
    .card-watch::before { background: linear-gradient(90deg, #ca8a04, #eab308); }
    .card-watch .metric-value { color: #fde047; } .card-watch .metric-label { color: #fef08a; }
    .metric-value { font-size: 44px; font-weight: 800; margin: 8px 0 4px; line-height: 1; letter-spacing: -2px; }
    .metric-label { font-size: 11px; font-weight: 600; text-transform: uppercase; letter-spacing: 1px; opacity: 0.9; }
    .apex-threat-banner { background: linear-gradient(135deg, #4c0519 0%, #881337 50%, #4c0519 100%); color: #fecdd3; padding: 16px 20px; border-radius: 12px; font-size: 16px; font-weight: 700; margin-bottom: 20px; text-align: center; border: 1px solid rgba(251,113,133,0.3); animation: pulse-border 2s infinite; position: relative; overflow: hidden; }
    .apex-threat-banner::before { content: ''; position: absolute; top: 0; left: -100%; width: 60%; height: 100%; background: linear-gradient(90deg, transparent, rgba(255,255,255,0.05), transparent); animation: shimmer 3s infinite; }
    .risk-orange { background: linear-gradient(135deg, rgba(154,52,18,0.15), rgba(30,15,5,0.4)); border-left: 4px solid #f97316; padding: 12px 16px; border-radius: 8px; color: #fdba74; font-weight: 600; font-size: 14px; margin-bottom: 16px; }
    .risk-blue { background: linear-gradient(135deg, rgba(29,78,216,0.15), rgba(5,15,40,0.4)); border-left: 4px solid #3b82f6; padding: 12px 16px; border-radius: 8px; color: #93c5fd; font-weight: 600; font-size: 14px; margin-bottom: 16px; }
    .risk-purple { background: linear-gradient(135deg, rgba(76,29,149,0.15), rgba(10,5,40,0.4)); border-left: 4px solid #8b5cf6; padding: 12px 16px; border-radius: 8px; color: #c4b5fd; font-weight: 600; font-size: 14px; margin-bottom: 16px; }
    .risk-red { background: linear-gradient(135deg, rgba(127,29,29,0.2), rgba(30,10,10,0.4)); border-left: 4px solid #ef4444; padding: 12px 16px; border-radius: 8px; color: #fca5a5; font-weight: 600; font-size: 14px; margin-bottom: 16px; }
    .risk-yellow { background: linear-gradient(135deg, rgba(133,77,14,0.15), rgba(30,20,5,0.4)); border-left: 4px solid #f59e0b; padding: 12px 16px; border-radius: 8px; color: #fcd34d; font-weight: 600; font-size: 14px; margin-bottom: 16px; }
    .dossier-reason { background: linear-gradient(135deg, rgba(127,29,29,0.2), rgba(30,10,10,0.5)); border: 1px solid rgba(239,68,68,0.25); padding: 16px 20px; border-radius: 12px; color: #fca5a5; font-size: 15px; margin-bottom: 16px; }
    .dossier-summary { background: rgba(15,23,42,0.75); border: 1px solid rgba(59,130,246,0.15); padding: 18px; border-radius: 12px; font-size: 14px; color: #cbd5e1; height: 100%; backdrop-filter: blur(8px); }
    .dossier-summary strong, .dossier-summary b { color: #93c5fd !important; }
    .osrm-metric { background: rgba(16,185,129,0.08); border-left: 4px solid #10b981; padding: 14px 18px; margin-bottom: 16px; font-size: 14px; color: #6ee7b7; border-radius: 8px; }
    .tactical-brief { background: rgba(15,23,42,0.85); border-left: 4px solid #e11d48; padding: 16px 20px; border-radius: 10px; color: #cbd5e1; font-size: 14px; margin-bottom: 20px; line-height: 1.8; }
    .tactical-brief b { color: #93c5fd; } .tactical-brief u { color: #fbbf24; }
    .watch-card { background: rgba(30,25,5,0.7); border: 1px solid rgba(234,179,8,0.2); border-left: 4px solid #eab308; padding: 14px 16px; border-radius: 10px; margin-bottom: 10px; color: #fef08a; font-size: 13px; }
    .watch-card b { color: #fde047; }
    .badge-today { background: #dc2626; color: white; padding: 2px 8px; border-radius: 12px; font-size: 11px; font-weight: 700; letter-spacing: 0.5px; }
    .stDataFrame { border-radius: 12px !important; overflow: hidden !important; }
    .map-legend { position: absolute; bottom: 30px; right: 30px; z-index: 1000; background: rgba(10,14,26,0.92); padding: 12px 16px; border-radius: 10px; border: 1px solid rgba(59,130,246,0.25); font-size: 13px; color: #e2e8f0; }
    .main-title { text-align: center; font-size: 1.9rem; font-weight: 800; background: linear-gradient(135deg, #f1f5f9 0%, #93c5fd 50%, #818cf8 100%); -webkit-background-clip: text; -webkit-text-fill-color: transparent; background-clip: text; margin-bottom: 2px; line-height: 1.2; }
    .main-subtitle { text-align: center; font-size: 0.88rem; color: #64748b !important; margin-top: 0; letter-spacing: 0.5px; margin-bottom: 10px; }
    .header-divider { height: 1px; background: linear-gradient(90deg, transparent, rgba(59,130,246,0.4), rgba(99,102,241,0.4), transparent); margin: 6px 0 16px 0; border: none; }
    /* ── Selectbox dropdown popup (Dark Mode) ── */
    [role="listbox"] { background: #0d1321 !important; border: 1px solid rgba(59,130,246,0.3) !important; border-radius: 10px !important; box-shadow: 0 8px 32px rgba(0,0,0,0.5) !important; }
    [role="option"] { color: #cbd5e1 !important; background: #0d1321 !important; }
    [role="option"]:hover { background: #ffffff !important; color: #0f172a !important; }
    [aria-selected="true"][role="option"] { background: #ffffff !important; color: #0f172a !important; font-weight: 600 !important; }
    li[data-baseweb="list-item"] { color: #cbd5e1 !important; background: #0d1321 !important; }
    [data-baseweb="popover"] { background: #0d1321 !important; border: 1px solid rgba(59,130,246,0.25) !important; border-radius: 10px !important; }
    /* Selectbox selected value text */
    [data-testid="stSelectbox"] [data-baseweb="select"] > div { background: rgba(15,23,42,0.8) !important; border: 1px solid rgba(59,130,246,0.25) !important; }
    [data-testid="stSelectbox"] span { color: #cbd5e1 !important; }
    /* --- FIX SELECTBOX DARK MODE --- */
    div[data-testid="stSelectbox"] label p { color: #cbd5e1 !important; font-weight: 600; }
    div[data-testid="stSelectbox"] [data-baseweb="select"] * { color: #f8fafc !important; }
"""

_light_css = """    /* ═══ LIGHT MODE ═══ */
    @import url('https://fonts.googleapis.com/css2?family=Sarabun:wght@300;400;500;600;700;800&display=swap');
    html, body { font-family: 'Sarabun', 'TH Sarabun PSK', 'TH Sarabun New', sans-serif !important; font-size: 16px !important; background: #f8fafc !important; color: #1e293b !important; }
    .stApp { background: #f8fafc !important; min-height: 100vh; }
    .main { background: #f8fafc !important; }
    .block-container { padding-top: 3.5rem !important; padding-left: 2rem !important; padding-right: 2rem !important; max-width: 100% !important; background: #f8fafc !important; }
    /* Sidebar */
    section[data-testid="stSidebar"] { background: #ffffff !important; border-right: 1px solid #e2e8f0 !important; }
    section[data-testid="stSidebar"] > div { background: transparent !important; }
    section[data-testid="stSidebar"] p,
    section[data-testid="stSidebar"] span,
    section[data-testid="stSidebar"] label,
    section[data-testid="stSidebar"] .stMarkdown { color: #1e293b !important; }
    section[data-testid="stSidebar"] hr { border-color: #e2e8f0 !important; }
    section[data-testid="stSidebar"] .stButton > button { background: #f1f5f9 !important; border: 1px solid #cbd5e1 !important; color: #334155 !important; border-radius: 8px !important; font-size: 13px !important; font-weight: 600 !important; width: 100% !important; transition: all 0.2s ease !important; }
    section[data-testid="stSidebar"] .stButton > button:hover { background: #e0e7ff !important; border-color: #6366f1 !important; color: #312e81 !important; }
    /* light: ปุ่มไม่มี use_container_width → pill เล็ก กึ่งกลาง */
    :not([data-testid="stSidebar"]) .stButton > button:not([style]) {
        width: fit-content !important; min-width: 80px !important;
        padding: 5px 18px !important; font-size: 12px !important;
        border-radius: 20px !important; display: block !important; margin: 0 auto !important;
    }
    :not([data-testid="stSidebar"]) .stButton:has(> button:not([style])) {
        display: flex !important; justify-content: center !important;
    }
    section[data-testid="stSidebar"] .stRadio label { color: #475569 !important; }
    .stTabs [data-baseweb="tab-list"] { background: #f1f5f9 !important; border-radius: 12px !important; padding: 6px !important; border: 1px solid #cbd5e1 !important; gap: 8px !important; }
    .stTabs [data-baseweb="tab"] { background: transparent !important; border-radius: 8px !important; color: #475569 !important; font-size: 18px !important; font-weight: 600 !important; padding: 12px 24px !important; }
    .stTabs [data-baseweb="tab"]:hover { color: #0f172a !important; background: #e2e8f0 !important; }
    .stTabs [aria-selected="true"] { background: linear-gradient(135deg, #3b82f6, #2563eb) !important; color: #ffffff !important; box-shadow: 0 4px 12px rgba(37, 99, 235, 0.3) !important; border: none !important; }
    .stTabs [aria-selected="true"] { background: #ffffff !important; color: #1e40af !important; font-weight: 700 !important; border: 1px solid #bfdbfe !important; box-shadow: 0 1px 4px rgba(0,0,0,0.08) !important; }
    h1, h2, h3 { color: #0f172a !important; font-weight: 700 !important; }
    h4 { color: #475569 !important; font-weight: 600 !important; }
    p, div, span { color: #334155 !important; }
    hr { border-color: #e2e8f0 !important; margin: 20px 0 !important; }
    [data-testid="stSelectbox"] > div > div { background: #ffffff !important; border: 1px solid #cbd5e1 !important; border-radius: 8px !important; color: #1e293b !important; }
    /* Selectbox dropdown options (portal renders at body level) */
    [role="listbox"] { background: #ffffff !important; }
    [role="option"] { color: #1e293b !important; background: #ffffff !important; }
    [role="option"]:hover, [aria-selected="true"][role="option"] { background: #dbeafe !important; color: #1e40af !important; }
    li[data-baseweb="list-item"] { color: #1e293b !important; background: #ffffff !important; }
    /* Input & select text */
    input, select, textarea { color: #1e293b !important; background: #ffffff !important; }
    [data-baseweb="select"] span, [data-baseweb="select"] div { color: #1e293b !important; }
    [data-baseweb="select"] > div { background: #ffffff !important; }
    .stTextInput input { background: #ffffff !important; border: 1px solid #cbd5e1 !important; border-radius: 8px !important; color: #1e293b !important; }
    .stTextArea textarea { background: #ffffff !important; border: 1px solid #cbd5e1 !important; border-radius: 8px !important; color: #1e293b !important; }
    .stButton > button { background: linear-gradient(135deg, #eff6ff, #e0e7ff) !important; border: 1px solid #bfdbfe !important; color: #1e40af !important; border-radius: 8px !important; font-weight: 600 !important; font-size: 13px !important; transition: all 0.2s ease !important; }
    .stButton > button:hover { background: linear-gradient(135deg, #dbeafe, #c7d2fe) !important; border-color: #6366f1 !important; box-shadow: 0 4px 12px rgba(99,102,241,0.2) !important; transform: translateY(-1px); }
    [data-testid="stCheckbox"] label { color: #1e293b !important; }
    /* Dropdown popup list items */
    [data-baseweb="popover"] { background: #ffffff !important; border: 1px solid #e2e8f0 !important; box-shadow: 0 4px 20px rgba(0,0,0,0.12) !important; }
    [data-baseweb="popover"] li { color: #1e293b !important; background: #ffffff !important; }
    [data-baseweb="popover"] li:hover { background: #eff6ff !important; color: #1e40af !important; }
    [data-baseweb="menu"] { background: #ffffff !important; }
    [data-baseweb="menu"] ul li { color: #1e293b !important; background: #ffffff !important; }
    [data-baseweb="select"] span { color: #1e293b !important; }
    /* Radio buttons */
    .stRadio label p, .stRadio label span { color: #334155 !important; }
    /* Metrics */
    [data-testid="stMetricValue"] { color: #0f172a !important; }
    [data-testid="stMetricLabel"] { color: #475569 !important; }
    [data-testid="stMetricDelta"] { color: #047857 !important; }
    /* Info / Warning / Alert boxes */
    .stAlert { border-radius: 10px !important; }
    [data-testid="stAlert"] p { color: #1e293b !important; }
    /* Expander */
    .streamlit-expanderHeader { color: #1e293b !important; background: #f1f5f9 !important; border-radius: 8px !important; }
    .streamlit-expanderContent { background: #ffffff !important; color: #334155 !important; }
    /* Form */
    [data-testid="stForm"] { background: #f8fafc !important; border: 1px solid #e2e8f0 !important; border-radius: 12px !important; padding: 16px !important; }
    /* Caption / small text */
    .stCaption p { color: #64748b !important; }
    /* Markdown in main area */
    .stMarkdown p, .stMarkdown li, .stMarkdown span { color: #334155 !important; }
    .stMarkdown strong, .stMarkdown b { color: #1e293b !important; }
    .stMarkdown h4 { color: #1e40af !important; }
    /* File uploader */
    [data-testid="stFileUploader"] label { color: #334155 !important; }
    .stDataFrame { border-radius: 12px !important; overflow: hidden !important; border: 1px solid #e2e8f0 !important; }
    /* ═══ SHARED (both themes) ═══ */
    @keyframes pulse-border { 0% { box-shadow: 0 0 0 0 rgba(239,68,68,0.6); } 70% { box-shadow: 0 0 0 12px rgba(239,68,68,0); } 100% { box-shadow: 0 0 0 0 rgba(239,68,68,0); } }
    @keyframes shimmer { 0% { left: -100%; } 100% { left: 200%; } }
    @keyframes blink-green { 0%, 100% { opacity: 1; box-shadow: 0 0 6px #10b981; } 50% { opacity: 0.3; box-shadow: none; } }
    @keyframes ticker { 0% { transform: translateX(100%); } 100% { transform: translateX(-100%); } }
    .live-dot { display: inline-block; width: 9px; height: 9px; border-radius: 50%; background-color: #10b981; margin-right: 8px; animation: blink-green 1.5s infinite; }
    .ticker-wrap { width: 100%; overflow: hidden; background: linear-gradient(90deg, #020617, #0f172a, #020617); padding: 9px 0; margin-bottom: 16px; white-space: nowrap; border-radius: 8px; color: #38bdf8; border: 1px solid rgba(56,189,248,0.15); }
    .ticker-content { display: inline-block; animation: ticker 35s linear infinite; font-weight: 500; font-family: 'Sarabun', 'TH Sarabun PSK', sans-serif; letter-spacing: 1.5px; font-size: 13px; }
    .metric-card { padding: 20px 16px; border-radius: 14px; text-align: center; margin-bottom: 16px; border: 1px solid rgba(255,255,255,0.07); position: relative; overflow: hidden; backdrop-filter: blur(12px); transition: transform 0.2s ease, box-shadow 0.2s ease; }
    .metric-card::before { content: ''; position: absolute; top: 0; left: 0; right: 0; height: 3px; border-radius: 14px 14px 0 0; }
    .metric-card:hover { transform: translateY(-3px); }
    .card-apex { background: linear-gradient(145deg, rgba(159,18,57,0.18), rgba(30,10,25,0.65)); box-shadow: 0 4px 24px rgba(159,18,57,0.15); }
    .card-apex::before { background: linear-gradient(90deg, #9f1239, #e11d48); }
    .card-apex .metric-value { color: #fda4af; } .card-apex .metric-label { color: #fecdd3; }
    .card-clone { background: linear-gradient(145deg, rgba(234,88,12,0.16), rgba(30,15,5,0.65)); box-shadow: 0 4px 24px rgba(234,88,12,0.12); }
    .card-clone::before { background: linear-gradient(90deg, #ea580c, #f97316); }
    .card-clone .metric-value { color: #fdba74; } .card-clone .metric-label { color: #fed7aa; }
    .card-car { background: linear-gradient(145deg, rgba(59,130,246,0.16), rgba(5,15,40,0.65)); box-shadow: 0 4px 24px rgba(59,130,246,0.12); }
    .card-car::before { background: linear-gradient(90deg, #2563eb, #3b82f6); }
    .card-car .metric-value { color: #93c5fd; } .card-car .metric-label { color: #bfdbfe; }
    .card-anomaly { background: linear-gradient(145deg, rgba(99,102,241,0.16), rgba(10,5,40,0.65)); box-shadow: 0 4px 24px rgba(99,102,241,0.12); }
    .card-anomaly::before { background: linear-gradient(90deg, #6366f1, #8b5cf6); }
    .card-anomaly .metric-value { color: #a5b4fc; } .card-anomaly .metric-label { color: #c7d2fe; }
    .card-watch { background: linear-gradient(145deg, rgba(234,179,8,0.16), rgba(30,20,5,0.65)); box-shadow: 0 4px 24px rgba(234,179,8,0.12); }
    .card-watch::before { background: linear-gradient(90deg, #ca8a04, #eab308); }
    .card-watch .metric-value { color: #fde047; } .card-watch .metric-label { color: #fef08a; }
    .metric-value { font-size: 44px; font-weight: 800; margin: 8px 0 4px; line-height: 1; letter-spacing: -2px; }
    .metric-label { font-size: 11px; font-weight: 600; text-transform: uppercase; letter-spacing: 1px; opacity: 0.9; }
    .apex-threat-banner { background: linear-gradient(135deg, #4c0519 0%, #881337 50%, #4c0519 100%); color: #fecdd3; padding: 16px 20px; border-radius: 12px; font-size: 16px; font-weight: 700; margin-bottom: 20px; text-align: center; border: 1px solid rgba(251,113,133,0.3); animation: pulse-border 2s infinite; position: relative; overflow: hidden; }
    .apex-threat-banner::before { content: ''; position: absolute; top: 0; left: -100%; width: 60%; height: 100%; background: linear-gradient(90deg, transparent, rgba(255,255,255,0.05), transparent); animation: shimmer 3s infinite; }
    .risk-orange { background: linear-gradient(135deg, rgba(154,52,18,0.15), rgba(30,15,5,0.4)); border-left: 4px solid #f97316; padding: 12px 16px; border-radius: 8px; color: #fdba74; font-weight: 600; font-size: 14px; margin-bottom: 16px; }
    .risk-blue { background: linear-gradient(135deg, rgba(29,78,216,0.15), rgba(5,15,40,0.4)); border-left: 4px solid #3b82f6; padding: 12px 16px; border-radius: 8px; color: #93c5fd; font-weight: 600; font-size: 14px; margin-bottom: 16px; }
    .risk-purple { background: linear-gradient(135deg, rgba(76,29,149,0.15), rgba(10,5,40,0.4)); border-left: 4px solid #8b5cf6; padding: 12px 16px; border-radius: 8px; color: #c4b5fd; font-weight: 600; font-size: 14px; margin-bottom: 16px; }
    .risk-red { background: linear-gradient(135deg, rgba(127,29,29,0.2), rgba(30,10,10,0.4)); border-left: 4px solid #ef4444; padding: 12px 16px; border-radius: 8px; color: #fca5a5; font-weight: 600; font-size: 14px; margin-bottom: 16px; }
    .risk-yellow { background: linear-gradient(135deg, rgba(133,77,14,0.15), rgba(30,20,5,0.4)); border-left: 4px solid #f59e0b; padding: 12px 16px; border-radius: 8px; color: #fcd34d; font-weight: 600; font-size: 14px; margin-bottom: 16px; }
    .dossier-reason { background: linear-gradient(135deg, rgba(127,29,29,0.2), rgba(30,10,10,0.5)); border: 1px solid rgba(239,68,68,0.25); padding: 16px 20px; border-radius: 12px; color: #fca5a5; font-size: 15px; margin-bottom: 16px; }
    .dossier-summary { background: rgba(15,23,42,0.75); border: 1px solid rgba(59,130,246,0.15); padding: 18px; border-radius: 12px; font-size: 14px; color: #cbd5e1; height: 100%; backdrop-filter: blur(8px); }
    .dossier-summary strong, .dossier-summary b { color: #93c5fd !important; }
    .osrm-metric { background: rgba(16,185,129,0.08); border-left: 4px solid #10b981; padding: 14px 18px; margin-bottom: 16px; font-size: 14px; color: #6ee7b7; border-radius: 8px; }
    .tactical-brief { background: rgba(15,23,42,0.85); border-left: 4px solid #e11d48; padding: 16px 20px; border-radius: 10px; color: #cbd5e1; font-size: 14px; margin-bottom: 20px; line-height: 1.8; }
    .tactical-brief b { color: #93c5fd; } .tactical-brief u { color: #fbbf24; }
    .watch-card { background: rgba(30,25,5,0.7); border: 1px solid rgba(234,179,8,0.2); border-left: 4px solid #eab308; padding: 14px 16px; border-radius: 10px; margin-bottom: 10px; color: #fef08a; font-size: 13px; }
    .watch-card b { color: #fde047; }
    .badge-today { background: #dc2626; color: white; padding: 2px 8px; border-radius: 12px; font-size: 11px; font-weight: 700; letter-spacing: 0.5px; }
    .stDataFrame { border-radius: 12px !important; overflow: hidden !important; }
    .map-legend { position: absolute; bottom: 30px; right: 30px; z-index: 1000; background: rgba(10,14,26,0.92); padding: 12px 16px; border-radius: 10px; border: 1px solid rgba(59,130,246,0.25); font-size: 13px; color: #e2e8f0; }
    .main-title { text-align: center; font-size: 1.9rem; font-weight: 800; background: linear-gradient(135deg, #f1f5f9 0%, #93c5fd 50%, #818cf8 100%); -webkit-background-clip: text; -webkit-text-fill-color: transparent; background-clip: text; margin-bottom: 2px; line-height: 1.2; }
    .main-subtitle { text-align: center; font-size: 0.88rem; color: #64748b !important; margin-top: 0; letter-spacing: 0.5px; margin-bottom: 10px; }
    .header-divider { height: 1px; background: linear-gradient(90deg, transparent, rgba(59,130,246,0.4), rgba(99,102,241,0.4), transparent); margin: 6px 0 16px 0; border: none; }

    /* --- FIX LIGHT MODE COLORS --- */
    .tactical-brief { background: #f8fafc !important; border-left: 4px solid #e11d48 !important; color: #0f172a !important; }
    .tactical-brief p, .tactical-brief div, .tactical-brief span { color: #0f172a !important; }
    .tactical-brief b, .tactical-brief strong { color: #1d4ed8 !important; }
    .tactical-brief u { color: #b45309 !important; text-decoration: none; font-weight: 600; }
    
    div[data-testid="stSelectbox"] label p { color: #1e293b !important; font-weight: 600; }
    div[data-testid="stSelectbox"] [data-baseweb="select"] * { color: #0f172a !important; }
    
    .card-apex { background: linear-gradient(135deg, #ffe4e6 0%, #fecdd3 50%, #fecaca 100%) !important; box-shadow: 0 4px 15px rgba(225,29,72,0.15) !important; border: 1px solid rgba(225,29,72,0.2) !important; }
    .card-clone { background: linear-gradient(135deg, #ffedd5 0%, #fed7aa 50%, #fdba74 100%) !important; box-shadow: 0 4px 15px rgba(234,88,12,0.15) !important; border: 1px solid rgba(234,88,12,0.2) !important; }
    .card-car { background: linear-gradient(135deg, #dbeafe 0%, #bfdbfe 50%, #93c5fd 100%) !important; box-shadow: 0 4px 15px rgba(37,99,235,0.15) !important; border: 1px solid rgba(37,99,235,0.2) !important; }
    .card-anomaly { background: linear-gradient(135deg, #f3e8ff 0%, #e9d5ff 50%, #d8b4fe 100%) !important; box-shadow: 0 4px 15px rgba(147,51,234,0.15) !important; border: 1px solid rgba(147,51,234,0.2) !important; }
    .card-watch { background: linear-gradient(135deg, #fef9c3 0%, #fef08a 50%, #fde047 100%) !important; box-shadow: 0 4px 15px rgba(202,138,4,0.15) !important; border: 1px solid rgba(202,138,4,0.2) !important; }
    
    .card-apex .metric-value, .card-apex .metric-label,
    .card-clone .metric-value, .card-clone .metric-label,
    .card-car .metric-value, .card-car .metric-label,
    .card-anomaly .metric-value, .card-anomaly .metric-label,
    .card-watch .metric-value, .card-watch .metric-label {
        color: #0f172a !important; text-shadow: none !important;
    }

    /* --- SOFT PASTEL CARDS & TICKER (LIGHT MODE) --- */
    .ticker-wrap, .ticker-wrap * { color: #ffffff !important; }
    .ticker-content { color: #ffffff !important; font-weight: 600; letter-spacing: 2px; }
    
    .card-apex { background: linear-gradient(135deg, #fff1f2 0%, #ffe4e6 100%) !important; box-shadow: 0 4px 10px rgba(0,0,0,0.03) !important; border: 1px solid rgba(225,29,72,0.1) !important; }
    .card-clone { background: linear-gradient(135deg, #fff7ed 0%, #ffedd5 100%) !important; box-shadow: 0 4px 10px rgba(0,0,0,0.03) !important; border: 1px solid rgba(234,88,12,0.1) !important; }
    .card-car { background: linear-gradient(135deg, #f0f9ff 0%, #e0f2fe 100%) !important; box-shadow: 0 4px 10px rgba(0,0,0,0.03) !important; border: 1px solid rgba(14,165,233,0.1) !important; }
    .card-anomaly { background: linear-gradient(135deg, #faf5ff 0%, #f3e8ff 100%) !important; box-shadow: 0 4px 10px rgba(0,0,0,0.03) !important; border: 1px solid rgba(168,85,247,0.1) !important; }
    .card-watch { background: linear-gradient(135deg, #fefce8 0%, #fef9c3 100%) !important; box-shadow: 0 4px 10px rgba(0,0,0,0.03) !important; border: 1px solid rgba(234,179,8,0.1) !important; }
    
    .card-apex .metric-value, .card-apex .metric-label,
    .card-clone .metric-value, .card-clone .metric-label,
    .card-car .metric-value, .card-car .metric-label,
    .card-anomaly .metric-value, .card-anomaly .metric-label,
    .card-watch .metric-value, .card-watch .metric-label {
        color: #1e293b !important; text-shadow: none !important;
    }

    /* --- GLOBAL THAI FONT OVERRIDE --- */
    :root {
        --font: 'Sarabun', 'TH Sarabun PSK', sans-serif !important;
        --font-sans-serif: 'Sarabun', 'TH Sarabun PSK', sans-serif !important;
        --font-serif: 'Sarabun', 'TH Sarabun PSK', serif !important;
    }
    
    .stApp, p, h1, h2, h3, h4, h5, h6, span:not([class*="icon"]):not([class*="material"]), div, li, label, button, input {
        font-family: 'Sarabun', 'TH Sarabun PSK', sans-serif !important;
    }
    
    /* Ensure Material Icons still work */
    span[class*="material-symbols"], span[class*="icon"], i[class*="icon"], [data-testid="stIconMaterial"] {
        font-family: 'Material Symbols Rounded', 'Material Icons', sans-serif !important;
    }
"""

_active_css = _dark_css if st.session_state.get('theme', 'dark') == 'dark' else _light_css

st.markdown(f"""
    <link href="https://fonts.googleapis.com/css2?family=Inter:wght@300;400;500;600;700;800;900&family=JetBrains+Mono:wght@400;600&display=swap" rel="stylesheet">
    <style>{_active_css}</style>
""", unsafe_allow_html=True)

if 'nav_tab' not in st.session_state:
    st.session_state['nav_tab'] = "🏠 สรุปสถานการณ์ (Overview)"

def change_tab(tab_name):
    st.session_state['nav_tab'] = tab_name

# ==========================================
# 1. จัดการฐานข้อมูล (SQLite สำหรับ Report + Parquet สำหรับ Big Data)
# ==========================================
def init_db():
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS daily_reports (
            report_date TEXT PRIMARY KEY,
            priority_data TEXT,
            dashboard_metrics TEXT
        )
    ''')
    cursor.execute('CREATE TABLE IF NOT EXISTS whitelist_master (ทะเบียนรถ TEXT PRIMARY KEY, หมายเหตุ TEXT)')
    cursor.execute('CREATE TABLE IF NOT EXISTS target_status (Target_ID TEXT PRIMARY KEY, status TEXT, last_update TEXT)')
    conn.commit()
    conn.close()

if not _IS_CLOUD:
    init_db()   # local เท่านั้น — cloud ใช้ Supabase ไม่ต้องการ SQLite
else:
    try:
        init_db()   # พยายาม init /tmp fallback
    except Exception:
        pass        # cloud ใช้ Supabase เป็นหลัก ถ้า SQLite ไม่ได้ก็ผ่านไป

# ─── Supabase Keep-Alive ping (ป้องกัน free tier pause หลัง 7 วัน) ───────────
if _IS_CLOUD:
    try:
        from supabase_sync import get_supabase_client as _get_sb
        _get_sb().table('users').select('username').limit(1).execute()
    except Exception:
        pass  # ถ้า Supabase หยุดชั่วคราว app ยังทำงาน degraded mode ต่อได้

@st.cache_data(ttl=300)
def load_historical_data():
    if os.path.exists(PARQUET_PATH):
        try:
            df_pl = pl.read_parquet(PARQUET_PATH)
            return df_pl
        except Exception:
            return pl.DataFrame()
    return pl.DataFrame()

def save_to_memory(new_df_pl, current_db_pl, cloud_db_pl=None):
    """Merge: new CSV + local parquet + cloud parquet → deduplicate → save"""
    if new_df_pl.is_empty(): return current_db_pl

    sources = []
    if not current_db_pl.is_empty(): sources.append(current_db_pl)
    if cloud_db_pl is not None and not cloud_db_pl.is_empty():
        sources.append(cloud_db_pl)
    sources.append(new_df_pl)

    combined = pl.concat(sources, how="vertical_relaxed") if len(sources) > 1 else new_df_pl
    combined = combined.unique(subset=["ทะเบียน_Full", "Datetime", "จุดติดตั้งกล้อง"], keep="first")

    sixty_days_ago = datetime.now() - timedelta(days=60)  # เก็บข้อมูลย้อนหลัง 60 วัน
    combined = combined.filter(pl.col("Datetime") >= sixty_days_ago)

    combined.write_parquet(PARQUET_PATH, compression="zstd")
    return combined


def save_daily_report(report_date, priority_df, active_db_pd):
    metrics = {}
    if not priority_df.empty:
        apex_df = priority_df[priority_df['ประเภท'] == "กลุ่มเป้าหมายความมั่นคงระดับสูงสุด"]
        metrics['cat_apex'] = len(apex_df)
        metrics['cat_cloned'] = len(priority_df[priority_df['ประเภท'] == "กลุ่มเป้าหมายสวมทะเบียน"])
        metrics['cat_convoy_car'] = len(priority_df[priority_df['ประเภท'] == "กลุ่มรถยนต์เคลื่อนที่แบบขบวน"])
        metrics['cat_others'] = len(priority_df[priority_df['ประเภท'] == "กลุ่มรถต้องสงสัย"])
        
        targeted_cars = set()
        for cars in priority_df['Cars_List']: targeted_cars.update(cars)
        target_logs = active_db_pd[active_db_pd['ทะเบียน_Full'].isin(targeted_cars)].copy()
        
        if not target_logs.empty:
            risk_map = {}
            for _, row in priority_df.iterrows():
                for car in row['Cars_List']:
                    risk_map[car] = max(risk_map.get(car, 0), row['Risk Score'])
            target_logs['Risk_Score'] = target_logs['ทะเบียน_Full'].map(risk_map)
            
            cam_stats = target_logs.groupby('จุดติดตั้งกล้อง').agg(
                lat=('ละติจูด', 'first'), lon=('ลองจิจูด', 'first'),
                volume=('ทะเบียน_Full', 'nunique'), 
                avg_score=('Risk_Score', 'mean'), max_score=('Risk_Score', 'max')
            ).reset_index()
            
            plate_to_type = {}
            for _, row in priority_df.iterrows():
                for car in row['Cars_List']:
                    plate_to_type[car] = row['ประเภท']
            
            cam_threats = target_logs.groupby('จุดติดตั้งกล้อง')['ทะเบียน_Full'].apply(lambda x: list(set([plate_to_type.get(c, "") for c in x]))).reset_index()
            cam_stats = pd.merge(cam_stats, cam_threats, on='จุดติดตั้งกล้อง')
            cam_stats['primary_threat'] = cam_stats['ทะเบียน_Full'].apply(lambda x: x[0] if len(x)>0 else "")
            
            metrics['map_stats'] = cam_stats.to_dict('records')
            active_db_pd['Hour'] = active_db_pd['Datetime'].dt.hour
            target_logs['Hour'] = target_logs['Datetime'].dt.hour
            target_logs['Threat_Type'] = target_logs['ทะเบียน_Full'].map(plate_to_type)
            
            hours = list(range(24))
            total_hourly = active_db_pd.groupby('Hour')['ทะเบียน_Full'].nunique().reindex(hours, fill_value=0)
            target_total_hr = target_logs.groupby('Hour')['ทะเบียน_Full'].nunique().reindex(hours, fill_value=0)
            
            metrics['clock'] = {
                'total_hourly': total_hourly.tolist(),
                'apex_hr': target_logs[target_logs['Threat_Type'] == 'กลุ่มเป้าหมายความมั่นคงระดับสูงสุด'].groupby('Hour')['ทะเบียน_Full'].nunique().reindex(hours, fill_value=0).tolist(),
                'cloned_hr': target_logs[target_logs['Threat_Type'] == 'กลุ่มเป้าหมายสวมทะเบียน'].groupby('Hour')['ทะเบียน_Full'].nunique().reindex(hours, fill_value=0).tolist(),
                'convoy_hr': target_logs[target_logs['Threat_Type'] == 'กลุ่มรถยนต์เคลื่อนที่แบบขบวน'].groupby('Hour')['ทะเบียน_Full'].nunique().reindex(hours, fill_value=0).tolist(),
                'border_hr': target_logs[target_logs['Threat_Type'] == 'กลุ่มรถต้องสงสัย'].groupby('Hour')['ทะเบียน_Full'].nunique().reindex(hours, fill_value=0).tolist(),
            }
            
            peak_target_hr = target_total_hr.idxmax() if target_total_hr.max() > 0 else 0
            hr_data = target_logs[target_logs['Hour'] == peak_target_hr]
            most_threat = target_logs['Threat_Type'].mode()[0] if not target_logs.empty else "-"
            
            metrics['tactical'] = {
                'peak_hr': int(peak_target_hr),
                'peak_cam': hr_data['จุดติดตั้งกล้อง'].mode()[0] if not hr_data.empty else "-",
                'main_threat': most_threat,
                'max_risk_ratio': float((target_total_hr / total_hourly.replace(0, 1) * 100).max())
            }
            
            tactical_table = target_logs.groupby(['Hour', 'จุดติดตั้งกล้อง']).agg(
                เป้าหมายที่พบ=('ทะเบียน_Full', 'nunique'),
                ระดับความเสี่ยง=('Risk_Score', 'max')
            ).reset_index().sort_values(by=['Hour', 'เป้าหมายที่พบ'], ascending=[True, False]).head(8)
            metrics['tactical_table'] = tactical_table.to_dict('records')


    # ★ บันทึก historical_suspects
    try:
        conn2 = sqlite3.connect(DB_PATH)
        suspects_df = priority_df[priority_df['Risk Score'] >= 80].copy() if not priority_df.empty else pd.DataFrame()
        if not suspects_df.empty:
            for _, row in suspects_df.iterrows():
                for plate in row.get('Cars_List', []):
                    conn2.execute("""
                        INSERT INTO historical_suspects (plate, threat_type, max_risk_score, last_seen_date, seen_count)
                        VALUES (?, ?, ?, ?, 1)
                        ON CONFLICT(plate) DO UPDATE SET
                            threat_type = CASE WHEN excluded.max_risk_score > historical_suspects.max_risk_score THEN excluded.threat_type ELSE historical_suspects.threat_type END,
                            max_risk_score = MAX(historical_suspects.max_risk_score, excluded.max_risk_score),
                            last_seen_date = excluded.last_seen_date,
                            seen_count = historical_suspects.seen_count + 1
                    """, (plate, row['ประเภท'], int(row['Risk Score']), report_date))
        conn2.commit()
        conn2.close()
    except Exception as _e:
        pass

    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute('''
        INSERT OR REPLACE INTO daily_reports (report_date, priority_data, dashboard_metrics)
        VALUES (?, ?, ?)
    ''', (report_date, priority_df.to_json(orient='records', force_ascii=False), json.dumps(metrics, ensure_ascii=False)))
    conn.commit()
    conn.close()

# ==========================================
# 2. กระบวนการคัดกรองข้อมูล (Data Pre-processing)
# ==========================================
def normalize_plate(plate):
    p = str(plate).replace(" ", "").upper()
    p = p.replace('O', '0').replace('I', '1').replace('B', '8')
    p = re.sub(r'[\u200B-\u200D\uFEFF]', '', p)
    drop_words = ['ไม่ทราบ', 'ไม่มี', 'NULL', 'NONE', 'NAN', 'UNKNOWN', '-']
    if any(w in p for w in drop_words) or p == '': return None
    return p

def classify_vehicle(plate):
    if re.match(r'^[789]\d', plate): return "รถบรรทุก"
    elif re.search(r'[ก-ฮ]', plate): return "รถยนต์ทั่วไป"
    return "ไม่ทราบประเภท"

def calculate_haversine(lat1, lon1, lat2, lon2):
    lat1, lon1, lat2, lon2 = map(np.radians, [lat1, lon1, lat2, lon2])
    dlat = lat2 - lat1
    dlon = lon2 - lon1
    a = np.sin(dlat/2.0)**2 + np.cos(lat1) * np.cos(lat2) * np.sin(dlon/2.0)**2
    return 6371.0 * (2 * np.arcsin(np.sqrt(a)))

def preliminary_data_check(files):
    if not files: return None
    df_list = [pd.read_csv(f) if f.name.endswith('.csv') else pd.read_excel(f) for f in files]
    df_pd = pd.concat(df_list, ignore_index=True)
    del df_list  # free individual file DataFrames after concat
    
    total_raw = len(df_pd)
    rename_dict = {'ทะเบียน': 'ทะเบียนรถ', 'ป้ายทะเบียน': 'ทะเบียนรถ'}
    df_pd = df_pd.rename(columns=rename_dict)
    
    if 'ทะเบียนรถ' in df_pd.columns:
        df_pd['clean_plate'] = df_pd['ทะเบียนรถ'].apply(normalize_plate)
        valid_rows = df_pd['clean_plate'].notna().sum()
        invalid_rows = total_raw - valid_rows
    else:
        valid_rows = 0
        invalid_rows = total_raw
        
    return {"total": total_raw, "valid": valid_rows, "invalid": invalid_rows, "raw_df": df_pd}

def process_raw_data_polars(df_pd):
    if df_pd is None or df_pd.empty: return pl.DataFrame()
    
    rename_dict = {'กล้อง': 'จุดติดตั้งกล้อง', 'สถานที่': 'จุดติดตั้งกล้อง', 'latitude': 'ละติจูด', 'lat': 'ละติจูด', 'longitude': 'ลองจิจูด', 'lng': 'ลองจิจูด'}
    df_pd = df_pd.rename(columns=rename_dict)
    for col in ['ทะเบียนรถ', 'จุดติดตั้งกล้อง', 'วันที่', 'เวลา', 'จังหวัด']:
        if col not in df_pd.columns: df_pd[col] = ""
    
    # ★ PERF: normalize_plate — vectorized (ไม่ใช้ .apply)
    _s = df_pd['ทะเบียนรถ'].astype(str)
    _s = _s.str.replace(' ', '', regex=False).str.upper()
    _s = _s.str.replace('O', '0', regex=False).str.replace('I', '1', regex=False).str.replace('B', '8', regex=False)
    for _zc in ['\u200b', '\u200c', '\u200d', '\ufeff']:  # zero-width chars
        _s = _s.str.replace(_zc, '', regex=False)
    _drop_pat = r'ไม่ทราบ|ไม่มี|NULL|NONE|NAN|UNKNOWN'
    _invalid = _s.str.contains(_drop_pat, case=False, na=True) | (_s.str.len() == 0) | (_s == '-')
    _s = _s.where(~_invalid, other=None)
    df_pd['ทะเบียนรถ'] = _s
    df_pd['จังหวัด'] = df_pd['จังหวัด'].fillna('').astype(str).str.strip().str.replace('None', '').str.replace('nan', '')
    df_pd = df_pd.dropna(subset=['ทะเบียนรถ'])

    # ★ Filter ตามมาตรฐาน DLT: รถยนต์=[ก-ฮ]{1-3}+\d{1-4} | ใหม่=\d{1-2}+[ก-ฮ]+\d | รถบรรทุก=6หลักพอดี + จังหวัด
    _plate_car        = df_pd['ทะเบียนรถ'].str.match(r'^[ก-ฮ]{1,3}\d{1,4}$', na=False)        # รถยนต์ทั่วไป
    _plate_car_new    = df_pd['ทะเบียนรถ'].str.match(r'^\d{1,2}[ก-ฮ]{1,3}\d{1,4}$', na=False) # รูปแบบใหม่ (1กฤ1234)
    _plate_truck      = df_pd['ทะเบียนรถ'].str.match(r'^[1-9]\d{5}$', na=False)                         # รถบรรทุก/ขนส่ง 6หลัก (prefix 10-99+4หลัก)
    _prov_valid       = df_pd['จังหวัด'].str.len() > 0
    _valid_plate      = (_plate_car | _plate_car_new | _plate_truck) & _prov_valid
    df_pd = df_pd[_valid_plate].copy()

    # ★ Format ทะเบียน_Full พร้อมเว้นวรรค: ขต1068อุบลราชธานี → ขต 1068 อุบลราชธานี | 1ข789 → 1ข 789
    _pr = df_pd['ทะเบียนรถ'].astype(str)
    _pv = df_pd['จังหวัด'].astype(str)
    # Extract prefix (all non-trailing-digits) + suffix (trailing digits)
    _prefix_part = _pr.str.extract(r'^(.*?)\d+$', expand=False).fillna('')
    _suffix_part = _pr.str.extract(r'(\d+)$', expand=False).fillna('')
    _has_prefix  = _prefix_part.str.len() > 0
    _has_suffix  = _suffix_part.str.len() > 0
    _fmt_plate   = np.where(_has_prefix & _has_suffix, _prefix_part + ' ' + _suffix_part, _pr)
    df_pd['ทะเบียน_Full'] = _fmt_plate + ' ' + _pv  # "ขต 1068 อุบลราชธานี" or "1ข 789 กรุงเทพ"


    df_pd['ละติจูด'] = pd.to_numeric(df_pd['ละติจูด'], errors='coerce').fillna(0.0)
    df_pd['ลองจิจูด'] = pd.to_numeric(df_pd['ลองจิจูด'], errors='coerce').fillna(0.0)
    df_pd = df_pd[(df_pd['ละติจูด'] != 0.0) & (df_pd['ลองจิจูด'] != 0.0)].copy()
    
    # ★ PERF: fix_year — vectorized (ไม่ใช้ .apply)
    _dy = df_pd['วันที่'].astype(str).str.replace('/', '-', regex=False)
    _year_int = pd.to_numeric(_dy.str[:4], errors='coerce').fillna(0).astype(int)
    _be_mask = _year_int > 2500
    if _be_mask.any():
        _ce_year = (_year_int[_be_mask] - 543).astype(str).str.zfill(4)
        _dy = _dy.copy()
        _dy[_be_mask] = _ce_year + _dy[_be_mask].str[4:]
    df_pd['วันที่'] = _dy
    df_pd['Datetime'] = pd.to_datetime(df_pd['วันที่'] + ' ' + df_pd['เวลา'], errors='coerce')
    df_pd = df_pd.dropna(subset=['Datetime']).reset_index(drop=True)
    # ★ PERF: classify_vehicle — vectorized
    _cv_s = df_pd['ทะเบียนรถ'].astype(str)
    _is_truck = _cv_s.str.match(r'^[789]\d', na=False)
    _has_thai = _cv_s.str.contains(r'[ก-ฮ]', regex=True, na=False)
    df_pd['ประเภทรถ'] = np.where(_is_truck, 'รถบรรทุก', np.where(_has_thai, 'รถยนต์ทั่วไป', 'ไม่ทราบประเภท'))
    
    df = pl.from_pandas(df_pd)
    
    df = df.sort(['ทะเบียน_Full', 'จุดติดตั้งกล้อง', 'Datetime'])
    df = df.with_columns(
        time_diff_cam=(pl.col('Datetime').diff().dt.total_milliseconds() / 1000).over(['ทะเบียน_Full', 'จุดติดตั้งกล้อง'])
    )
    df = df.filter(pl.col('time_diff_cam').is_null() | (pl.col('time_diff_cam') > 180))
    
    df = df.sort(['ทะเบียน_Full', 'Datetime'])
    df = df.with_columns([
        pl.col('ละติจูด').shift(1).over('ทะเบียน_Full').alias('prev_lat'),
        pl.col('ลองจิจูด').shift(1).over('ทะเบียน_Full').alias('prev_lon'),
        pl.col('Datetime').shift(1).over('ทะเบียน_Full').alias('prev_time'),
        pl.col('จุดติดตั้งกล้อง').shift(1).over('ทะเบียน_Full').alias('prev_cam')
    ])
    
    df = df.with_columns(
        dist_km_straight=pl.struct(['prev_lat', 'prev_lon', 'ละติจูด', 'ลองจิจูด']).map_batches(
            lambda s: calculate_haversine(s.struct.field('prev_lat').to_numpy(), s.struct.field('prev_lon').to_numpy(), s.struct.field('ละติจูด').to_numpy(), s.struct.field('ลองจิจูด').to_numpy())
        )
    )
    
    df = df.with_columns(dist_km=pl.col('dist_km_straight') * 1.35)
    df = df.with_columns(
        time_diff_hr=(pl.col('Datetime') - pl.col('prev_time')).dt.total_milliseconds() / 3600000.0
    )
    df = df.with_columns(
        Speed_kmh=pl.when(pl.col('time_diff_hr') > 0).then(pl.col('dist_km') / pl.col('time_diff_hr')).otherwise(0.0)
    )
    
    BORDER_ANCHORS = [
        # ── พม่า (Myanmar) ──────────────────────────────────────────
        (20.42, 99.88),   # แม่สาย เชียงราย
        (20.27, 100.08),  # เชียงแสน เชียงราย
        (19.30, 97.97),   # แม่ฮ่องสอน (เมือง)
        (18.52, 97.59),   # ปาย แม่ฮ่องสอน
        (16.72, 98.57),   # แม่สอด ตาก ★ ด่านหลัก
        (16.98, 98.51),   # แม่ระมาด ตาก
        (17.57, 98.14),   # ท่าสองยาง ตาก
        (15.32, 98.40),   # เจดีย์สามองค์ กาญจนบุรี ★ ด่านหลัก
        (15.22, 98.33),   # พุน้ำร้อน กาญจนบุรี
        (11.80, 99.43),   # สิงขร ประจวบคีรีขันธ์
        ( 9.97, 98.60),   # ระนอง ★ ด่านหลัก
        # ── ลาว (Laos) ──────────────────────────────────────────────
        (20.26, 100.40),  # เชียงของ เชียงราย ★ สะพานมิตรภาพ 4
        (17.87, 101.43),  # ท่าลี่ เลย
        (17.88, 102.75),  # หนองคาย ★ สะพานมิตรภาพ 1
        (18.36, 103.65),  # บึงกาฬ ★ ด่านบึงกาฬ
        (17.40, 104.78),  # นครพนม ★ สะพานมิตรภาพ 3
        (16.54, 104.73),  # มุกดาหาร ★ สะพานมิตรภาพ 2
        (15.20, 105.54),  # ช่องเม็ก อุบลราชธานี ★ ด่านหลัก
        (17.00, 102.10),  # เวียงจันทน์ฝั่งไทย (ท่าบก)
        # ── กัมพูชา (Cambodia) ──────────────────────────────────────
        (14.38, 103.72),  # ช่องจอม สุรินทร์ ★ ด่านหลัก
        (14.02, 104.13),  # ช่องสะงำ ศรีสะเกษ
        (14.61, 102.98),  # บุรีรัมย์ (ช่อง)
        (13.69, 102.52),  # อรัญประเทศ สระแก้ว ★ ด่านหลัก
        (13.32, 102.53),  # บ้านคลองลึก สระแก้ว
        (12.53, 102.57),  # บ้านปากาด จันทบุรี ★ ด่านหลัก
        (11.66, 102.91),  # หาดเล็ก ตราด ★ ด่านหลัก
        # ── มาเลเซีย (Malaysia) ─────────────────────────────────────
        ( 6.64, 100.43),  # สะเดา สงขลา ★ ด่านหลัก
        ( 6.69, 100.27),  # วังประจัน สตูล
        ( 5.78, 101.08),  # เบตง ยะลา ★ ด่านหลัก
        ( 6.03, 101.97),  # สุไหงโกลก นราธิวาส ★ ด่านหลัก
        ( 6.26, 102.07),  # ตากใบ นราธิวาส
    ]
    _BA = np.array(BORDER_ANCHORS)  # shape (8, 2)
    _ba_lats_r = np.radians(_BA[:, 0])
    _ba_lons_r = np.radians(_BA[:, 1])

    def _assign_zones_batch(lats_np, lons_np):
        # ★ PERF: numpy broadcasting — เร็วกว่า np.vectorize > 50x
        lats_r = np.radians(lats_np)[:, np.newaxis]   # (n,1)
        lons_r = np.radians(lons_np)[:, np.newaxis]   # (n,1)
        dlat = _ba_lats_r - lats_r   # (n,8)
        dlon = _ba_lons_r - lons_r   # (n,8)
        a = (np.sin(dlat / 2) ** 2 +
             np.cos(lats_r) * np.cos(_ba_lats_r) * np.sin(dlon / 2) ** 2)
        dists = 6371.0 * 2 * np.arcsin(np.sqrt(np.clip(a, 0, 1)))  # (n,8)
        is_border = (dists <= 50.0).any(axis=1)  # (n,)
        return np.where(is_border, 'A', 'C')

    df = df.with_columns(
        Zone=pl.struct(['ละติจูด', 'ลองจิจูด']).map_batches(
            lambda s: _assign_zones_batch(s.struct.field('ละติจูด').to_numpy(), s.struct.field('ลองจิจูด').to_numpy())
        )
    )
    df = df.with_columns(Is_Night=pl.col('Datetime').dt.hour().is_in([22, 23, 0, 1, 2, 3, 4]))
    
    return df

# ==========================================
# 3. กลไกประเมินพฤติการณ์ (The Orchestrator & 3 Engines)
# ==========================================
def run_intelligence_orchestrator(active_db_pl,
                                   e2_cam_pre=5, e2_shared=5, e2_dist=150, e2_score=90,
                                   e3_cams=6,   e3_dist=200, e3_score=95):
    active_db = active_db_pl.to_pandas()
    
    conn = sqlite3.connect(DB_PATH)
    wl_df = pd.read_sql("SELECT ทะเบียนรถ FROM whitelist_master", conn)
    conn.close()
    whitelist_plates = set(wl_df['ทะเบียนรถ'].tolist())
    
    if not active_db.empty and 'ทะเบียน_Full' in active_db.columns:
        active_db = active_db[~active_db['ทะเบียน_Full'].isin(whitelist_plates)]

        # ── Smart Direction Inference ─────────────────────────────────────────
        # ขั้น 1: อ่านจากชื่อกล้อง (ถ้ากล้องระบุไว้)
        def get_direction_from_name(cam):
            cam_str = str(cam)
            if 'เข้า' in cam_str: return 'เข้า'
            if 'out' in cam_str.lower() or 'ออก' in cam_str: return 'ออก'
            return 'ไม่ระบุ'
        active_db['Direction'] = active_db['จุดติดตั้งกล้อง'].apply(get_direction_from_name)

        # ขั้น 2: กล้องที่ 'ไม่ระบุ' — ใช้ลำดับเวลา + พิกัดภูมิศาสตร์วิเคราะห์
        # หลักการ: ถ้ารถเคลื่อนที่จากทิศใต้→เหนือ (lat เพิ่ม) = 'เข้า' พื้นที่ภายใน
        # อ้างอิงจากพิกัดชายแดนลาว/กัมพูชา (เหนือ=ชายแดน, ใต้=ในประเทศ)
        if 'ละติจูด' in active_db.columns and 'ลองจิจูด' in active_db.columns:
            try:
                _no_dir = active_db['Direction'] == 'ไม่ระบุ'
                if _no_dir.any():
                    _sorted = active_db.sort_values(['ทะเบียน_Full', 'Datetime'])
                    _sorted['_prev_lat'] = _sorted.groupby('ทะเบียน_Full')['ละติจูด'].shift(1)
                    _sorted['_prev_lon'] = _sorted.groupby('ทะเบียน_Full')['ลองจิจูด'].shift(1)
                    _sorted['_dlat'] = _sorted['ละติจูด'] - _sorted['_prev_lat']
                    _sorted['_dlon'] = _sorted['ลองจิจูด'] - _sorted['_prev_lon']

                    def _infer_dir(row):
                        if row['Direction'] != 'ไม่ระบุ': return row['Direction']
                        if pd.isna(row.get('_dlat')): return 'ไม่ระบุ'
                        if abs(row['_dlat']) < 0.005 and abs(row['_dlon']) < 0.005:
                            return 'ไม่ระบุ'
                        if abs(row['_dlat']) >= abs(row['_dlon']):
                            return 'เข้า' if row['_dlat'] > 0 else 'ออก'
                        else:
                            return 'เข้า' if row['_dlon'] > 0 else 'ออก'

                    _inferred = _sorted.apply(_infer_dir, axis=1)
                    active_db = _sorted.copy()
                    active_db['Direction'] = _inferred
                    active_db = active_db.drop(columns=['_prev_lat','_prev_lon','_dlat','_dlon'], errors='ignore')
            except Exception:
                pass  # fallback: ใช้ค่าเดิม 'ไม่ระบุ'
        # ────────────────────────────────────────────────────────────────────
    
    engine_results = defaultdict(lambda: {"engines": set(), "reasons": [], "cars": set(), "score": 0, "type": "", "radar": {}, "cams": "-", "gap": "-"})
    
    # ----------------------------------------
    # 🚨 ENGINE 1: รถแฝด / สวมทะเบียน (Time-Travel Paradox) - THE GHOST CATCHER UPDATED
    # ----------------------------------------
    if not active_db.empty and 'Speed_kmh' in active_db.columns:
        # E1 ตะแกรง 3 เงื่อนไข (UK NADC + Interpol standard):
        e1_speed_mask   = (active_db['Speed_kmh'] > 250) & (active_db['dist_km'] >= 60)     # UK NADC: ≥ 250 km/h
        e1_paradox_mask = (active_db['time_diff_hr'] < (1/60)) & (active_db['dist_km'] >= 100)  # พร้อมกัน 2 กล้อง ≥ 100 km
        e1_sameregion   = (active_db['time_diff_hr'] <= 1.0) & (active_db['dist_km'] >= 200) # Interpol: 1 ชม. ≥ 200 km
        _cam_diff = active_db['จุดติดตั้งกล้อง'] != active_db['prev_cam']
        e1_mask   = (e1_speed_mask | e1_paradox_mask | e1_sameregion) & _cam_diff
        e1_plates = active_db[e1_mask]['ทะเบียน_Full'].unique()

        # Map plate → detection type สำหรับ reason text ที่แม่นยำ
        _e1_type = {}
        for _p in active_db[e1_speed_mask   & _cam_diff]['ทะเบียน_Full'].unique(): _e1_type[_p] = 'speed'
        for _p in active_db[e1_paradox_mask & _cam_diff]['ทะเบียน_Full'].unique():
            if _p not in _e1_type: _e1_type[_p] = 'paradox'
        for _p in active_db[e1_sameregion   & _cam_diff]['ทะเบียน_Full'].unique():
            if _p not in _e1_type: _e1_type[_p] = 'region'

        for plate in e1_plates:
            df_target = active_db[active_db['ทะเบียน_Full'] == plate].sort_values('Datetime')
            if df_target.empty: continue

            max_speed = df_target['Speed_kmh'].max()
            r_night   = 20 if df_target.iloc[-1]['Is_Night'] else 0
            _dtype    = _e1_type.get(plate, 'speed')
            if _dtype == 'speed':
                _reason = f"ความเร็วเกินขีดฟิสิกส์ ({max_speed:.0f} กม./ชม.) ระหว่างสองกล้อง — ป้ายเดียวกันวิ่งบนถนนสองสาย [UK NADC]"
            elif _dtype == 'paradox':
                _reason = f"ปรากฏพร้อมกัน 2 กล้องที่ห่างกันเกิน 100 กม. ในขณะเดียวกัน — Time-Space Paradox [Interpol]"
            else:
                _reason = f"ปรากฏใน 2 พื้นที่ห่างกัน ≥ 200 กม. ภายใน 1 ชั่วโมง — ไม่สามารถเดินทางได้จริง [Interpol Same-Region]"

            engine_results[plate]["engines"].add("E1")
            engine_results[plate]["reasons"].append(_reason)
            engine_results[plate]["score"]      = max(engine_results[plate]["score"], 100)
            engine_results[plate]["cars"].add(plate)
            engine_results[plate]["radar"]      = {"Night": r_night, "Border": 30, "Shuttle": 0, "Regional": 0, "Convoy": 0}
            engine_results[plate]["speed_warp"] = f"{max_speed:.0f}"
    else:
        e1_plates = []


    # ----------------------------------------
    # 🚘 ENGINE 2: โครงข่ายขบวนรถลำเลียง (The Bounded Convoy) - LOCAL OVERLOAD TRAFIX
    # ----------------------------------------
    if not active_db.empty and 'ทะเบียน_Full' in active_db.columns:
        df_cars = active_db[active_db['ประเภทรถ'] == 'รถยนต์ทั่วไป']

        # ==========================================
        # 2.3 E2_CAR: ขบวนแก๊งรถยนต์ (วิ่งทางไกล ทิศทางชายแดน ผ่าน >= 4 ด่าน)
        # ==========================================
        cam_counts_car = df_cars.groupby('ทะเบียน_Full')['จุดติดตั้งกล้อง'].nunique()
        valid_car_plates = cam_counts_car[cam_counts_car >= e2_cam_pre].index
        convoy_db_car = df_cars[df_cars['ทะเบียน_Full'].isin(valid_car_plates)].copy()
        
        pair_cams_car = defaultdict(set)
        for cam, group in convoy_db_car.groupby('จุดติดตั้งกล้อง'):
            group = group.sort_values('Datetime')
            times_sec = group['Datetime'].values.astype('datetime64[s]').astype(np.int64)
            plates = group['ทะเบียน_Full'].values
            n = len(plates)
            for i in range(n):
                for j in range(i + 1, n):
                    if times_sec[j] - times_sec[i] > 600: break 
                    c1, c2 = plates[i], plates[j]
                    if c1 != c2:
                        pair_cams_car[tuple(sorted([str(c1), str(c2)]))].add(cam)
                        
        adj_car = defaultdict(set)
        for pair, cams in pair_cams_car.items():
            if len(cams) >= e2_shared:  # ผ่านร่วมกัน >= e2_shared ด่าน (sync กับ app.py)
                adj_car[pair[0]].add(pair[1])
                adj_car[pair[1]].add(pair[0])
                
        visited_car = set()
        convoys_car = []
        for node in adj_car:
            if node not in visited_car:
                comp = set()
                q = [node]
                while q:
                    curr = q.pop(0)
                    if curr not in visited_car:
                        visited_car.add(curr)
                        comp.add(curr)
                        q.extend([n for n in adj_car[curr] if n not in visited_car])
                comp_list = sorted(list(comp))
                if 2 <= len(comp_list) <= 6:
                    df_target = active_db[active_db['ทะเบียน_Full'].isin(comp_list)]
                    is_valid = True
                    cams_passed = set()
                    for cam, c_group in df_target.groupby('จุดติดตั้งกล้อง'):
                        if len(c_group) >= 2:
                            if (c_group['Datetime'].max() - c_group['Datetime'].min()).total_seconds() > 600: 
                                is_valid = False
                                break
                            cams_passed.add(cam)
                    if is_valid and len(cams_passed) >= e2_shared:  # sync กับ app.py
                        gap_val = df_target.groupby('จุดติดตั้งกล้อง').apply(lambda x: (x['Datetime'].max() - x['Datetime'].min()).total_seconds()).mean()
                        convoys_car.append({'cars': comp_list, 'cams': len(cams_passed),
                                             'gap': gap_val, 'shared_cams': cams_passed})

        for cv in convoys_car:
            df_target = active_db[active_db['ทะเบียน_Full'].isin(cv['cars'])]
            if df_target.empty: continue

            # ── TOS / HRI / Gap Penalty ────────────────────────────────
            _shared_cams = cv.get('shared_cams', set())

            # Build (plate, cam) → first arrival time dict  [O(n)]
            _tpivot = (df_target.groupby(['ทะเบียน_Full', 'จุดติดตั้งกล้อง'])['Datetime']
                       .min().to_dict())

            # ─ TOS: Order Consistency ─
            _cams_in_order = sorted(
                _shared_cams,
                key=lambda c: min(
                    (_tpivot.get((car, c), pd.Timestamp.max) for car in cv['cars']),
                    default=pd.Timestamp.max
                )
            )
            _leader = cv['cars'][0]; _swaps = 0
            if _cams_in_order:
                _fa = {car: _tpivot.get((car, _cams_in_order[0]))
                       for car in cv['cars'] if (car, _cams_in_order[0]) in _tpivot}
                if _fa:
                    _leader = min(_fa, key=_fa.get)
                    for _cam in _cams_in_order[1:]:
                        _ca = {car: _tpivot.get((car, _cam))
                               for car in cv['cars'] if (car, _cam) in _tpivot}
                        if len(_ca) >= 2 and min(_ca, key=_ca.get) != _leader:
                            _swaps += 1
            # ≥ 2 swaps → REJECT (not a real convoy)
            if _swaps >= 2: continue
            _tos = 1.0 if _swaps == 0 else 0.85

            # ─ HRI: Headway Regularity Index ─
            _gaps_sec = []
            for _cam in _shared_cams:
                _cd = df_target[df_target['จุดติดตั้งกล้อง'] == _cam].sort_values('Datetime')
                if len(_cd) >= 2:
                    _ct = _cd['Datetime'].tolist()
                    for _gi in range(1, len(_ct)):
                        _g = (_ct[_gi] - _ct[_gi-1]).total_seconds()
                        if 0 < _g < 600: _gaps_sec.append(_g)
            if _gaps_sec:
                _mn = np.mean(_gaps_sec)
                _cv_val = np.std(_gaps_sec) / _mn if _mn > 0 else 1.0
                _hri = 1.0 if _cv_val < 0.5 else (0.9 if _cv_val < 1.0 else 0.7)
            else:
                _hri = 0.9

            # ─ Gap Penalty: missing cameras ─
            _max_ind = max(
                df_target[df_target['ทะเบียน_Full'] == car]['จุดติดตั้งกล้อง'].nunique()
                for car in cv['cars']
            )
            _gap_cnt = max(0, _max_ind - cv['cams'])
            if _gap_cnt >= 3: continue   # ≥ 3 miss → REJECT
            _gpen = 1.0 if _gap_cnt == 0 else (0.9 if _gap_cnt == 1 else 0.75)
            # ───────────────────────────────────────────────────

            lead_car  = _leader
            lead_logs = df_target[df_target['ทะเบียน_Full'] == lead_car].sort_values('Datetime')
            dirs = [d for d in lead_logs['Direction'] if d != 'ไม่ระบุ']
            if len(set(dirs)) > 1: continue

            # All-cars direction coherence (Interpol: ≥ 2/3 ต้องสอดคล้องกับรถนำ)
            if dirs:
                _exp_dir = list(set(dirs))[0]
                _dir_ok  = sum(
                    1 for car in cv['cars']
                    if any(d == _exp_dir
                           for d in df_target[df_target['ทะเบียน_Full'] == car]['Direction']
                           if d != 'ไม่ระบุ')
                )
                if _dir_ok < max(2, int(len(cv['cars']) * 0.67)):
                    continue  # ขบวนทิศทางไม่สอดคล้องกัน — ไม่ใช่ขบวนจริง

            total_dist = lead_logs['dist_km'].sum(skipna=True)
            provinces = set(df_target['จังหวัด'].unique()) - {""}
            is_cross_region = len(provinces) > 1
            has_border_plate = any(p in BORDER_PROVINCES for p in provinces)

            if total_dist < e2_dist and not is_cross_region and not has_border_plate: continue

            avg_speed = df_target[df_target['Speed_kmh'] > 0]['Speed_kmh'].mean()
            speed_txt = f" (ความเร็วกลุ่ม {avg_speed:.0f} กม./ชม.)" if pd.notna(avg_speed) else ""

            base_convoy_score = 65
            compound_reasons  = []

            if has_border_plate:
                base_convoy_score += 15
                compound_reasons.append("มีรถทะเบียนจังหวัดชายแดนในขบวน")
            if is_cross_region:
                base_convoy_score += 15
                compound_reasons.append("ใช้ป้ายทะเบียนข้ามภูมิภาค")
            if set(dirs) == {'เข้า'} or set(dirs) == {'ออก'}:
                base_convoy_score += 15
                compound_reasons.append(f"มุ่งหน้าทิศทาง [{list(set(dirs))[0]}] ชัดเจน")

            # Apply TOS × HRI × Gap multipliers
            base_convoy_score = int(base_convoy_score * _tos * _hri * _gpen)

            if base_convoy_score < e2_score: continue

            _order_txt = (
                f"รักษาลำดับตลอด (TOS★)"
                if _swaps == 0 else f"สลับตำแหน่ง 1 ครั้ง (รถอาจติดไฟแดง)"
            )
            _gap_txt = f"ขาดกล้อง {_gap_cnt} ตัว" if _gap_cnt > 0 else "ผ่านทุกกล้องร่วมกัน"
            compound_reasons.append(
                f"[ขบวนลำเลียง] รถนำ: {lead_car} | {_order_txt} | {_gap_txt} | "
                f"เคลื่อนที่ ({total_dist:.0f} กม.) ผ่าน {cv['cams']} ด่าน{speed_txt} "
                f"[TOS={_tos:.2f} HRI={_hri:.2f} Gap={_gpen:.2f}]"
            )

            group_id = f"Group_Car_{lead_car}"
            for c in cv['cars']: engine_results[group_id]["cars"].add(c)
            engine_results[group_id]["lead_car"] = str(lead_car)  # ★ เก็บ lead_car ไว้ใน data โดยตรง
            engine_results[group_id]["engines"].add("E2_Car")
            engine_results[group_id]["reasons"].append(" | ".join(compound_reasons))
            engine_results[group_id]["score"] = max(engine_results[group_id]["score"], min(100, base_convoy_score))
            engine_results[group_id]["radar"] = {"Night": 10, "Border": 20 if has_border_plate else 0,
                                                   "Shuttle": 0, "Regional": 15 if is_cross_region else 0, "Convoy": 30}
            engine_results[group_id]["cams"]       = f"{cv['cams']}"
            engine_results[group_id]["total_dist"] = total_dist

            avg_gap_sec = cv['gap']
            gm = int(avg_gap_sec // 60); gs = int(avg_gap_sec % 60)
            gap_text = (f"{gm} นาที {gs} วินาที" if gm > 0 and gs > 0
                        else (f"{gm} นาที" if gm > 0 else f"{gs} วินาที"))
            engine_results[group_id]["gap"] = gap_text


    # ----------------------------------------
    # 🔄 ENGINE 3: พฤติกรรมมุดช่องโหว่ชายแดน (Touch & Go U-Turn)
    # ----------------------------------------
    if not active_db.empty and 'Datetime' in active_db.columns:
        hourly_traffic = active_db.groupby([active_db['Datetime'].dt.hour]).size()
        traffic_q20 = hourly_traffic.quantile(0.2) if not hourly_traffic.empty else 0
        
        freq_counts = active_db.groupby('ทะเบียน_Full').size()
        e3_candidates_raw = freq_counts[freq_counts >= 3].index
        
        # ★ PERF: Pre-compute all filter criteria with groupby ONCE (ลด loop จาก 187k → ~ร้อยทะเบียน)
        _e3_sub = active_db[active_db['ทะเบียน_Full'].isin(e3_candidates_raw) &
                             ~active_db['ทะเบียน_Full'].isin(e1_plates)]
        if not _e3_sub.empty:
            _e3_g = _e3_sub.groupby('ทะเบียน_Full', sort=False)
            _e3_unique_days  = _e3_g['Datetime'].apply(lambda x: x.dt.date.nunique())
            _e3_cam_count    = _e3_g['จุดติดตั้งกล้อง'].nunique()
            _e3_dist_sum     = _e3_g['dist_km'].sum()
            _e3_has_A        = _e3_g['Zone'].apply(lambda x: 'A' in x.values)
            _e3_has_C        = _e3_g['Zone'].apply(lambda x: 'C' in x.values)
            # ★ ไม่กรองด้วย unique_days — ยิ่งซ้ำหลายวัน ยิ่งอันตราย (DEA/ปปส. standard)
            _e3_pass = ((_e3_cam_count >= e3_cams) &
                        (_e3_dist_sum >= e3_dist) & _e3_has_A & _e3_has_C)
            e3_candidates = _e3_pass[_e3_pass].index.tolist()
        else:
            e3_candidates = []
        
        for plate in e3_candidates:
            # ★ หมายเหตุ: เงื่อนไขตะแกรง 1,2,4 กรองล่วงหน้าแล้ว — ยังคง logic U-turn, evasion ครบถ้วน
            df_target = active_db[active_db['ทะเบียน_Full'] == plate].sort_values('Datetime')
            if df_target.empty: continue
            
            unique_days = df_target['Datetime'].dt.date.nunique()
            # ★ ไม่ตัดรถซ้ำหลายวันออก — เก็บไว้เป็น score booster (DEA/ปปส.)
            if df_target['จุดติดตั้งกล้อง'].nunique() < e3_cams: continue
            if df_target['dist_km'].sum(skipna=True) < e3_dist: continue
            zones = df_target['Zone'].unique()
            if 'C' not in zones or 'A' not in zones: continue
            
            is_night = any(df_target['Is_Night'])
            is_border = 'A' in df_target['Zone'].values
            province = str(df_target['จังหวัด'].iloc[-1]) if not df_target.empty else ""
            is_foreign = province not in BORDER_PROVINCES
            
            is_drop_pick = False
            _uturn_count = 0      # นับจำนวนรอบที่วน (multiple crossing runs)
            time_diffs = df_target['Datetime'].diff().dt.total_seconds() / 3600.0
            # ★ ตะแกรง U-turn: ต้องเป็น Zone A ที่ "ออก" และ Zone A ที่ "เข้า" (เข้มขึ้น)
            gap_indices = np.where((time_diffs >= 1.0) & (time_diffs <= 4.0))[0]

            for idx in gap_indices:
                if idx >= len(df_target): continue
                zone_before = df_target['Zone'].iloc[idx-1]
                zone_after  = df_target['Zone'].iloc[idx]
                dir_before  = df_target['Direction'].iloc[idx-1]
                dir_after   = df_target['Direction'].iloc[idx]

                # ★ เข้มขึ้น: ต้องเป็น Zone A ทั้งก่อนและหลัง + ทิศทางกลับ
                if (zone_before == 'A' and zone_after == 'A'
                        and dir_before == 'ออก' and dir_after == 'เข้า'):
                    is_drop_pick = True
                    _uturn_count += 1

            # ── Overnight U-turn (4-12 ชม.) Zone A — DEA/Europol FRONTEX ──
            _is_overnight_uturn = False
            _overnight_count    = 0
            overnight_indices = np.where((time_diffs >= 4.0) & (time_diffs <= 12.0))[0]
            for idx in overnight_indices:
                if idx >= len(df_target): continue
                zb = df_target['Zone'].iloc[idx-1]
                za = df_target['Zone'].iloc[idx]
                db_dir = df_target['Direction'].iloc[idx-1]
                da_dir = df_target['Direction'].iloc[idx]
                if zb == 'A' and za == 'A' and db_dir == 'ออก' and da_dir == 'เข้า':
                    _is_overnight_uturn = True
                    _overnight_count   += 1
                    is_drop_pick = True

            if not is_drop_pick: continue   # ถ้าไม่ใช่ U-turn Zone-A จริง → เตะทิ้ง

            is_evasion = False
            hours_visited = df_target['Datetime'].dt.hour
            if any(hourly_traffic.get(h, 0) <= traffic_q20 for h in hours_visited):
                is_evasion = True

            avg_speed = df_target[df_target['Speed_kmh'] > 0]['Speed_kmh'].mean()
            speed_txt = f" (ความเร็วเฉลี่ย {avg_speed:.0f} กม./ชม.)" if pd.notna(avg_speed) else ""
            is_speed_anomaly = pd.notna(avg_speed) and avg_speed > 110

            base_score = 60
            compound_triggers = []

            # Trigger 1: U-turn (เงื่อนไขบังคับ)
            _uturn_txt = (f"วนรอบ {_uturn_count} รอบ" if _uturn_count > 1
                          else "ตีวงกลับโฉบรับ/ส่งชายแดน")
            compound_triggers.append(f"{_uturn_txt} (ออก Zone A → แช่ 1-4 ชม. → เข้า Zone A)")
            base_score += 20

            # Trigger 1c: Overnight U-turn — DEA/Europol FRONTEX
            if _is_overnight_uturn:
                _ov_txt = (f"ค้างคืน {_overnight_count} รอบ" if _overnight_count > 1 else "ค้างคืนชายแดน")
                compound_triggers.append(
                    f"Overnight Border Stay: {_ov_txt} (ออก Zone A → ค้าง 4-12 ชม. → เข้า Zone A) "
                    f"— รับ/ส่งสินค้าข้ามคืน [DEA/Europol FRONTEX]"
                )
                base_score += 20

            # Trigger 1b: Repeat Offender — DEA/ปปส. standard: ยิ่งซ้ำหลายวัน ยิ่งอันตราย
            if unique_days >= 3:
                compound_triggers.append(f"Repeat Offender: ปรากฏซ้ำ {unique_days} วัน — พฤติกรรมเป็นระบบ (ปปส./DEA)")
                base_score += 15
            elif unique_days == 2:
                base_score += 7  # small boost for 2-day repeat (no trigger added)

            # Trigger 2: กลางดึก + จราจรต่ำ (เงื่อนไขเสริม)
            if is_evasion and is_night:
                compound_triggers.append("จงใจมุดช่องโหว่ห้วงเวลาวิกาลที่มีการจราจรต่ำ")
                base_score += 15

            # Trigger 3: รถต่างถิ่นในพื้นที่ชายแดน (เงื่อนไขเสริม)
            if is_foreign and is_border:
                compound_triggers.append(f"ยานพาหนะต่างถิ่น ({province}) ลัดเลาะชายแดน")
                base_score += 15

            # Trigger 4 (bonus): วนหลายรอบในวันเดียว
            if _uturn_count >= 2:
                compound_triggers.append(f"วนซ้ำ {_uturn_count} รอบในวันเดียว — แผนลำเลียงหลายเที่ยว")
                base_score += 10

            # Trigger 5 (bonus): ความเร็วสูงผิดปกติ
            if is_speed_anomaly:
                compound_triggers.append(f"ความเร็วเฉลี่ยสูงผิดปกติ ({avg_speed:.0f} กม./ชม.) — เร่งหนีการตรวจ")
                base_score += 10

            if base_score < e3_score: continue

            # ★ ต้องมี ≥3 triggers: U-turn บังคับ + กลางดึก + รถต่างถิ่น (หรือ bonus อย่างน้อย 1)
            if len(compound_triggers) < 3: continue

            engine_results[plate]["engines"].add("E3")
            engine_results[plate]["reasons"].append(" + ".join(compound_triggers) + speed_txt)
            engine_results[plate]["score"]  = max(engine_results[plate]["score"], min(95, base_score))
            engine_results[plate]["cars"].add(plate)
            engine_results[plate]["radar"]  = {
                "Night":    30 if is_night    else 0,
                "Border":   30 if is_border   else 0,
                "Shuttle":  20 if _uturn_count >= 2 else 10,
                "Regional": 20 if is_foreign  else 0,
                "Convoy":   0
            }
            engine_results[plate]["total_dist"] = df_target['dist_km'].sum(skipna=True)
            engine_results[plate]["cams"]       = f"{df_target['จุดติดตั้งกล้อง'].nunique()}"

    # ----------------------------------------
    # 🌙 ENGINE 4: Night Ghost — รถชายแดนกลางดึกซ้ำซาก
    # ----------------------------------------
    if not active_db.empty and 'Is_Night' in active_db.columns and 'Zone' in active_db.columns:
        border_db   = active_db[active_db['Zone'] == 'A']
        border_night = border_db[border_db['Is_Night'] == True]

        if not border_night.empty:
            # ★ PERF: pre-compute counts แทน loop
            _e4_night_counts = border_night.groupby('ทะเบียน_Full').size()
            _e4_total_counts = active_db.groupby('ทะเบียน_Full').size()
            _e4_border_cams  = border_night.groupby('ทะเบียน_Full')['จุดติดตั้งกล้อง'].nunique()

            _e4_night_counts = _e4_night_counts[_e4_night_counts >= 3]
            _e4_unique_days = border_night.groupby('ทะเบียน_Full')['Datetime'].apply(
                lambda x: x.dt.date.nunique())
            _e4_night_counts = _e4_night_counts[
                _e4_night_counts.index.map(lambda p: _e4_unique_days.get(p, 1) >= 2)]
            _e4_candidates = _e4_night_counts.index

            for plate in _e4_candidates:
                if plate in e1_plates: continue
                # Fix 4a: E4 ไม่ซ้ำกับ E3 (Europol standard: ไม่นับซ้ำรถที่มี U-turn แล้ว)
                if "E3" in engine_results.get(plate, {}).get("engines", set()): continue

                night_count   = _e4_night_counts.get(plate, 0)
                total_count   = _e4_total_counts.get(plate, 1)
                border_cams   = _e4_border_cams.get(plate, 0)

                if border_cams < 2: continue

                night_ratio = night_count / max(total_count, 1)
                if night_ratio < 0.6: continue  # ต้อง >= 60% ผ่านชายแดนเป็นกลางดึก

                base_score = 70
                reasons    = []

                reasons.append(
                    f"พบการเดินทางผ่านชายแดนกลางดึก {night_count} ครั้ง ผ่าน {border_cams} จุดตรวจ"
                )

                if night_ratio >= 0.9:
                    base_score += 15
                    reasons.append("ผ่านชายแดนเฉพาะกลางดึก (≥90%) — แผนหลบเลี่ยงชัดเจน")
                elif night_ratio >= 0.7:
                    base_score += 8
                    reasons.append("ผ่านชายแดนกลางดึกสูงผิดปกติ (≥70%)")

                if border_cams >= 3:
                    base_score += 10
                    reasons.append(f"ครอบคลุมจุดตรวจชายแดน {border_cams} จุด ในคืนเดียว")

                # Fix 4b: Deep Night (00-04) vs Late Night (22-23) — Europol FRONTEX
                df_e4_plate = active_db[(active_db['ทะเบียน_Full'] == plate) & (active_db['Zone'] == 'A')]
                _deep_night  = len(df_e4_plate[df_e4_plate['Datetime'].dt.hour.isin([0, 1, 2, 3, 4])])
                if _deep_night >= 2:
                    base_score += 10
                    reasons.append(f"ผ่านชายแดนช่วงดึกสุด 00:00-04:00 จำนวน {_deep_night} ครั้ง — ความเสี่ยงสูงสุด [Europol FRONTEX]"
                )

                df_target = active_db[active_db['ทะเบียน_Full'] == plate]
                avg_speed = df_target[df_target['Speed_kmh'] > 0]['Speed_kmh'].mean()
                speed_txt = f" (ความเร็วเฉลี่ย {avg_speed:.0f} กม./ชม.)" if pd.notna(avg_speed) else ""

                if base_score < 80: continue

                engine_results[plate]["engines"].add("E4")
                engine_results[plate]["reasons"].append(" | ".join(reasons) + speed_txt)
                engine_results[plate]["score"] = max(
                    engine_results[plate]["score"], min(90, base_score)
                )
                engine_results[plate]["cars"].add(plate)
                engine_results[plate]["radar"] = {
                    "Night": 40, "Border": 35, "Shuttle": 0, "Regional": 0, "Convoy": 0
                }
                engine_results[plate]["cams"] = str(border_cams)

    # ----------------------------------------
    # 👑 THE ORCHESTRATOR 
    # ----------------------------------------
    priority_list = []
    if not active_db.empty:
        # Pre-compute camera counts per plate for fast lookup
        _plate_cam_counts = active_db.groupby('ทะเบียน_Full')['จุดติดตั้งกล้อง'].nunique()

        for target_id, data in engine_results.items():
            if not data["cars"]: continue
            
            is_e1 = "E1" in data["engines"]
            is_e4 = "E4" in data["engines"]

            # 5-camera filter: ยกเว้น E1 (physics) และ E4 (border night ไม่ต้องการ 5 กล้อง)
            if not is_e1 and not is_e4:
                cam_count = _plate_cam_counts.reindex(list(data["cars"])).fillna(0).max()
                if cam_count < 5:
                    continue
            
            main_engines = set([e.split('_')[0] for e in data["engines"]])
            is_apex = len(main_engines) >= 2
            
            if is_apex: final_type = "กลุ่มเป้าหมายความมั่นคงระดับสูงสุด"
            elif "E1" in data["engines"]: final_type = "กลุ่มเป้าหมายสวมทะเบียน"
            elif "E2_Car" in data["engines"]: final_type = "กลุ่มรถยนต์เคลื่อนที่แบบขบวน"
            elif "E4" in data["engines"]: final_type = "กลุ่มรถต้องสงสัย"
            elif "E3" in data["engines"]: final_type = "กลุ่มรถต้องสงสัย"
                
            target_cars_df = active_db[active_db['ทะเบียน_Full'].isin(data["cars"])].sort_values('Datetime')
            if target_cars_df.empty: continue 
            
            last_row = target_cars_df.iloc[-1]

            # ★ เรียง Cars_List: lead_car อยู่ index 0 เสมอ (แก้ bug set() ไม่มี order)
            _all_cars_str = [str(c) for c in data["cars"]]
            _lead_str = data.get("lead_car")
            if _lead_str and _lead_str in _all_cars_str:
                _all_cars_str = [_lead_str] + [c for c in _all_cars_str if c != _lead_str]

            priority_list.append({
                "Target_ID": target_id,
                "เป้าหมาย": " / ".join(_all_cars_str),
                "ประเภท": final_type,
                "พฤติกรรมต้องสงสัย": " | ".join(data["reasons"]),
                "ผ่านร่วมกัน (ด่าน)": data["cams"],
                "ระยะห่างเฉลี่ย": data["gap"],
                "Risk Score": min(100, data["score"]),
                "ระดับ": "🔴 ยืนยัน" if min(100, data["score"]) >= 85 else "🟡 น่าสงสัย",
            "Apex_Flag": "👑 APEX" if is_apex else "",
            "Apex_Boost": f"+{int(data['score'] * 0.15)}" if is_apex else "0",
                "จุดตรวจพบล่าสุด": f"📍 {last_row['จุดติดตั้งกล้อง']}",
                "เวลาโผล่ล่าสุด": str(last_row['เวลา']),
                "Cars_List": _all_cars_str,
                "Radar_Data": data["radar"],
                "Speed_Warp": data.get("speed_warp", "-"),
                "Total_Dist": f"{data.get('total_dist', 0):.1f}" if ("E3" in data["engines"] or "E2_Car" in data["engines"]) else "-"
            })


    if priority_list:
        return pd.DataFrame(priority_list).sort_values(by="Risk Score", ascending=False).reset_index(drop=True)
    else:
        return pd.DataFrame(columns=["Target_ID", "เป้าหมาย", "ประเภท", "พฤติกรรมต้องสงสัย", "ผ่านร่วมกัน (ด่าน)", "ระยะห่างเฉลี่ย", "Risk Score", "ระดับ", "จุดตรวจพบล่าสุด", "เวลาโผล่ล่าสุด", "Cars_List", "Radar_Data", "Speed_Warp", "Total_Dist"])

# ==========================================
# 4. ส่วนแสดงผลปฏิบัติการ (Dashboard & UI)
# ==========================================
def show_watch_list(active_db, selected_date):
    """แสดงรถในอดีตที่น่าสงสัย — ตาราง + checkbox + Export Excel"""
    st.markdown("<div class='risk-yellow'>⭐ รายงาน: ทะเบียนที่น่าติดตาม (ประวัติพฤติกรรมต้องสงสัยในอดีต)</div><br>", unsafe_allow_html=True)
    try:
        conn_w = sqlite3.connect(DB_PATH)
        hs_df = pd.read_sql("""
            SELECT plate, threat_type, max_risk_score, last_seen_date, seen_count
            FROM historical_suspects
            ORDER BY max_risk_score DESC, seen_count DESC
        """, conn_w)
        conn_w.close()
    except:
        hs_df = pd.DataFrame()

    if hs_df.empty:
        st.info("📭 ยังไม่มีข้อมูลประวัติ — ระบบจะสะสมข้อมูลหลังจากทำการประมวลผลครั้งแรก")
        return

    today_plates = set(active_db['ทะเบียน_Full'].unique()) if not active_db.empty else set()
    today_dt = pd.to_datetime(selected_date)

    def calc_watch_score(row):
        days_ago = (today_dt - pd.to_datetime(row['last_seen_date'])).days if row['last_seen_date'] else 999
        recency_bonus = max(0, 30 - days_ago) / 30.0 * 30
        freq_bonus = min(row['seen_count'] * 5, 20)
        seen_today_bonus = 25 if row['plate'] in today_plates else 0
        return min(100, int(row['max_risk_score'] * 0.5 + recency_bonus + freq_bonus + seen_today_bonus))

    hs_df['Watch Score'] = hs_df.apply(calc_watch_score, axis=1)
    hs_df['_today_sort'] = hs_df['plate'].apply(lambda p: 0 if p in today_plates else 1)
    hs_df['สถานะวันนี้'] = hs_df['plate'].apply(lambda p: '🔴 ตรวจพบวันนี้' if p in today_plates else '⬜ ยังไม่พบ')
    hs_df = hs_df.sort_values(['_today_sort', 'Watch Score'], ascending=[True, False]).reset_index(drop=True)
    hs_df = hs_df.drop(columns=['_today_sort'])

    seen_today = hs_df[hs_df['plate'].isin(today_plates)]
    not_seen   = hs_df[~hs_df['plate'].isin(today_plates)]

    # ── Metrics ────────────────────────────────────────────────────────
    col_w1, col_w2, col_w3 = st.columns(3)
    with col_w1: st.metric("📋 รถใน Watch List", len(hs_df))
    with col_w2: st.metric("🔴 ตรวจพบวันนี้", len(seen_today))
    with col_w3: st.metric("⬜ ยังไม่พบวันนี้", len(not_seen))

    st.markdown("---")
    st.markdown("#### 📋 รายการทะเบียนทั้งหมดใน Watch List")
    st.caption("☑️ เลือกรายการเพื่อดูรายละเอียด | กด Shift เพื่อเลือกหลายรายการ")

    # ── Table + detail side-by-side ────────────────────────────────────
    col_tbl, col_det = st.columns([6, 4])

    with col_tbl:
        col_order  = ['สถานะวันนี้', 'plate', 'threat_type', 'max_risk_score',
                      'Watch Score', 'seen_count', 'last_seen_date']
        rename_map = {
            'plate': 'ทะเบียน', 'threat_type': 'ประเภทภัยคุกคาม',
            'max_risk_score': 'Risk Score', 'seen_count': 'พบกี่ครั้ง',
            'last_seen_date': 'เคยพบล่าสุด',
        }
        tbl = hs_df[col_order].rename(columns=rename_map)
        event = st.dataframe(
            tbl, use_container_width=True, hide_index=True,
            on_select="rerun", selection_mode="multi-row", key="wl_table"
        )
        excel_download_button(tbl, f"watchlist_{selected_date}.xlsx",
                              "📥 Export Watch List (Excel)")

    with col_det:
        if event.selection.rows:
            for idx in event.selection.rows:
                row = hs_df.iloc[idx]
                is_today = row['plate'] in today_plates
                threat_icon = {'สวม': '🚨', 'ขบวน': '🚘', 'ผิด': '🔄'}.get(
                    next((k for k in ['สวม', 'ขบวน', 'ผิด']
                          if k in str(row['threat_type'])), ''), '⚠️')
                cams_today = (active_db[active_db['ทะเบียน_Full'] == row['plate']]
                              ['จุดติดตั้งกล้อง'].unique().tolist()
                              if is_today and not active_db.empty else [])
                last_cam = (active_db[active_db['ทะเบียน_Full'] == row['plate']]
                            .sort_values('Datetime').iloc[-1]['จุดติดตั้งกล้อง']
                            if is_today and not active_db.empty
                            and len(active_db[active_db['ทะเบียน_Full'] == row['plate']]) > 0
                            else '-')
                with st.expander(
                    f"{threat_icon} {row['plate']} — Watch Score: {row['Watch Score']}",
                    expanded=True
                ):
                    st.markdown(f"**ประเภทภัยคุกคาม:** {row['threat_type']}")
                    st.markdown(f"**Risk Score:** {row['max_risk_score']} | **Watch Score:** {row['Watch Score']}")
                    st.markdown(f"**พบทั้งหมด:** {row['seen_count']} ครั้ง")
                    st.markdown(f"**เคยพบล่าสุด:** {row['last_seen_date']}")
                    if is_today:
                        st.markdown(f"**🔴 วันนี้ผ่าน {len(cams_today)} กล้อง**")
                        st.markdown(f"**กล้องล่าสุด:** {last_cam}")
                        if cams_today:
                            st.markdown(f"**กล้องที่ผ่าน:** {', '.join(cams_today[:5])}"
                                        f"{'...' if len(cams_today)>5 else ''}")
        else:
            st.info("← เลือกรายการจากตารางเพื่อดูรายละเอียด")

def color_score(val):
    try:
        v = int(str(val).replace('%', ''))
        color = '#fecdd3' if v >= 90 else '#fed7aa' if v >= 75 else '#fef08a'
        text_c = '#881337' if v >= 90 else '#9a3412' if v >= 75 else '#854d0e'
        return f'background-color: {color}; color: {text_c}; font-weight: bold; border-radius: 4px;'
    except:
        return ''


# ─────────────────────────────────────────────────────────────────────────
# 🔁 Repeat Offender Intelligence
# ─────────────────────────────────────────────────────────────────────────
def repeat_offender_analysis(reports_df, reference_date, window_days=30, min_days=3):
    """ค้นหาทะเบียนที่ trigger detection ≥ min_days ในช่วง window_days จาก Supabase DataFrame"""
    try:
        if reports_df is None or reports_df.empty:
            return pd.DataFrame()
        
        ref_dt   = pd.to_datetime(reference_date)
        start_dt = ref_dt - timedelta(days=window_days)
        
        reports_df['date'] = pd.to_datetime(reports_df['report_date'])
        mask = (reports_df['date'] >= start_dt) & (reports_df['date'] <= ref_dt)
        df_filtered = reports_df[mask]
        
        if df_filtered.empty:
            return pd.DataFrame()
            
        rows = [(row['report_date'], row['priority_data']) for _, row in df_filtered.iterrows()]
    except Exception as e:
        return pd.DataFrame()

    if not rows:
        return pd.DataFrame()

    records = []
    import gc as _gc_rep
    for report_date, priority_data in rows:
        try:
            if isinstance(priority_data, str):
                import json
                p_data = json.loads(priority_data)
            else:
                p_data = priority_data
                
            pdf = pd.DataFrame(p_data)
            if pdf.empty: continue
            import re as _re_plt
            # ─ define helpers ที่นี่เสมอ ไม่ว่าจะมี column เป้าหมาย หรือไม่ ─
            def _vp(s):
                for pt in str(s).split('/'):
                    pt = pt.strip()
                    ps2 = _re_plt.sub(r'\s+', '', pt)
                    if _re_plt.search(r'[ก-ฮ]\d', ps2) and _re_plt.search(r'\d[ก-ฮ]', ps2): return True
                    if _re_plt.match(r'^[1-9]\d{5}[ก-ฮ]', ps2): return True
                return False
            def _fp(s):
                parts = []
                for part in str(s).split('/'):
                    part = part.strip()
                    part = _re_plt.sub(r'([ก-ฮ])(\d)', r'\1 \2', part)
                    part = _re_plt.sub(r'(\d)([ก-ฮ])', r'\1 \2', part)
                    part = _re_plt.sub(r' +', ' ', part).strip()
                    parts.append(part)
                return ' / '.join(parts)
            if 'เป้าหมาย' in pdf.columns:
                pdf = pdf[pdf['เป้าหมาย'].apply(_vp)].reset_index(drop=True)
                if not pdf.empty:
                    pdf['เป้าหมาย'] = pdf['เป้าหมาย'].apply(_fp)
            if pdf.empty: continue
            for _, row in pdf.iterrows():
                score_val = row.get('Risk Score', 0)
                try: score_val = float(str(score_val).replace('%',''))
                except: score_val = 0
                if score_val < 80: continue
                for plate in row.get('Cars_List', []):
                    ps = _re_plt.sub(r'\s+', '', str(plate).strip())
                    if not ((_re_plt.search(r'[ก-ฮ]\d', ps) and _re_plt.search(r'\d[ก-ฮ]', ps)) or _re_plt.match(r'^[1-9]\d{5}[ก-ฮ]', ps)): continue
                    plate_fmt = _fp(str(plate).strip())
                    records.append({
                        'plate': plate_fmt,
                        'ประเภท': row.get('ประเภท', ''),
                        'score': score_val,
                        'report_date': report_date,
                        'เหตุผล': str(row.get('พฤติกรรมต้องสงสัย', ''))[:120],
                    })
        except: pass
        finally:
            try: del pdf  # free intermediate DataFrame per iteration
            except: pass

    if not records:
        return pd.DataFrame()

    df = pd.DataFrame(records)
    summary = df.groupby('plate').agg(
        วันที่พบ=('report_date', 'nunique'),
        ประเภทหลัก=('ประเภท', lambda x: x.mode()[0] if len(x)>0 else ''),
        คะแนนสูงสุด=('score', 'max'),
        ครั้งแรก=('report_date', 'min'),
        ล่าสุด=('report_date', 'max'),
        dates_list=('report_date', lambda x: sorted(list(set(x)))),
        เหตุผลรวม=('เหตุผล', lambda x: ' | '.join(list(set(x))[:3]))
    ).reset_index()

    summary = summary[summary['วันที่พบ'] >= min_days].sort_values('วันที่พบ', ascending=False)
    return summary


def render_repeat_offender_dossier(plate, historical_db, dates_list):
    """แสดงรายละเอียด Repeat Offender — map + table เหมือนฟังก์ชันอื่น"""
    if historical_db is None or historical_db.empty or 'ทะเบียน_Full' not in historical_db.columns:
        st.info("⚠️ ไม่พบข้อมูลรายละเอียดในระบบ")
        return

    df_plate = historical_db[historical_db['ทะเบียน_Full'] == plate].sort_values('Datetime')
    if df_plate.empty:
        st.info(f"⚠️ ไม่พบเส้นทางของ {plate} ในฐานข้อมูล")
        return

    df_plate = df_plate.copy()
    df_plate['_date'] = df_plate['Datetime'].dt.date.astype(str)

    DAY_COLORS    = ['blue','red','green','orange','purple','pink','cadetblue','darkred']
    DAY_COLORS_HEX = ['#3b82f6','#ef4444','#22c55e','#f97316','#8b5cf6','#ec4899','#06b6d4','#dc2626']

    # ── 1. Day-summary table ────────────────────────────────────────────
    st.markdown(f"**📋 สรุปรายวัน: {plate}**")
    rows_sum = []
    for i, d in enumerate(dates_list):
        dd = df_plate[df_plate['_date'] == d]
        if dd.empty: continue
        ch = DAY_COLORS_HEX[i % len(DAY_COLORS_HEX)]
        rows_sum.append({
            'วัน': f"<span style='background:{ch};color:#fff;padding:2px 8px;border-radius:4px;font-weight:bold'>{d}</span>",
            'กล้องที่ผ่าน': f"{dd['จุดติดตั้งกล้อง'].nunique()} จุด",
            'เวลาแรก': dd['Datetime'].min().strftime('%H:%M'),
            'เวลาสุดท้าย': dd['Datetime'].max().strftime('%H:%M'),
            'ระยะทาง(กม.)': f"{dd['dist_km'].sum(skipna=True):.0f}",
            'Zone': ', '.join(str(z) for z in dd['Zone'].unique()) if 'Zone' in dd.columns else '-',
        })
    if rows_sum:
        st.write(pd.DataFrame(rows_sum).to_html(index=False, escape=False), unsafe_allow_html=True)

    st.markdown("---")

    # ── 2. Detailed records table (เหมือนฟังก์ชันอื่น) ───────────────────
    st.markdown("**📑 ตารางข้อมูลอ้างอิงรายจุดตรวจ**")
    detail_cols = ['Datetime','จุดติดตั้งกล้อง','Speed_kmh','Direction','Zone','ละติจูด','ลองจิจูด']
    avail_cols  = [c for c in detail_cols if c in df_plate.columns]
    detail_df   = df_plate[avail_cols].copy()
    detail_df.insert(0, 'วันที่', df_plate['_date'])
    detail_df['Datetime'] = detail_df['Datetime'].dt.strftime('%H:%M:%S') if 'Datetime' in detail_df.columns else '-'
    detail_df = detail_df.rename(columns={
        'Datetime': 'เวลา', 'Speed_kmh': 'ความเร็ว(กม./ชม.)',
        'Direction': 'ทิศทาง', 'ละติจูด': 'Lat', 'ลองจิจูด': 'Lon'
    })
    st.dataframe(detail_df, use_container_width=True, height=220)
    excel_download_button(detail_df, f"route_{plate}.xlsx", "📥 Export เส้นทาง (Excel)")

    st.markdown("---")

    # ── 3. Map with day-filter panel on the left ───────────────────────
    st.markdown("**🗺️ แผนที่เส้นทางแต่ละวัน**")

    valid = df_plate.dropna(subset=['ละติจูด','ลองจิจูด'])
    if valid.empty:
        st.info("ไม่มีข้อมูลพิกัดสำหรับแสดงแผนที่")
        return

    col_cb, col_map = st.columns([1, 4])

    # ── Left: colored checkbox list ─────────────────────────────────────
    selected_dates = []
    with col_cb:
        st.markdown(
            "<div style='font-size:12px;font-weight:600;color:#475569;"
            "margin-bottom:8px'>🗓️ เลือกวันที่</div>",
            unsafe_allow_html=True
        )
        for i, d in enumerate(dates_list):
            hex_color = DAY_COLORS_HEX[i % len(DAY_COLORS_HEX)]
            sw, chk = st.columns([0.15, 0.85])
            with sw:
                st.markdown(
                    f"<div style='width:12px;height:12px;background:{hex_color};"
                    f"border-radius:3px;margin-top:7px'></div>",
                    unsafe_allow_html=True
                )
            with chk:
                if st.checkbox(d, value=True, key=f"rep_day_{plate}_{i}_{d}"):
                    selected_dates.append(d)

    # ── Right: map built from selected days ─────────────────────────────
    with col_map:
        if not selected_dates:
            st.info("เลือกอย่างน้อย 1 วันเพื่อแสดงแผนที่")
        else:
            center_lat = valid['ละติจูด'].mean()
            center_lon = valid['ลองจิจูด'].mean()
            m = folium.Map(location=[center_lat, center_lon], zoom_start=8)

            for i, d in enumerate(dates_list):
                if d not in selected_dates: continue
                dd = df_plate[df_plate['_date'] == d].dropna(subset=['ละติจูด','ลองจิจูด'])
                if dd.empty: continue
                f_color   = DAY_COLORS[i % len(DAY_COLORS)]
                hex_color = DAY_COLORS_HEX[i % len(DAY_COLORS_HEX)]

                for _, r in dd.iterrows():
                    spd = r.get('Speed_kmh', 0)
                    spd_txt = f"{spd:.0f} กม./ชม." if pd.notna(spd) and spd > 0 else "ไม่ระบุ"
                    popup_html = (
                        f"<b>{r['จุดติดตั้งกล้อง']}</b><br>"
                        f"วันที่: {d}<br>"
                        f"เวลา: {r['Datetime'].strftime('%H:%M:%S')}<br>"
                        f"ความเร็ว: {spd_txt}<br>"
                        f"ทิศทาง: {r.get('Direction','ไม่ระบุ')}"
                    )
                    folium.CircleMarker(
                        location=(r['ละติจูด'], r['ลองจิจูด']),
                        radius=6, color=hex_color, fill=True, fill_opacity=0.85,
                        popup=folium.Popup(popup_html, max_width=250),
                        tooltip=f"{d} | {r['จุดติดตั้งกล้อง']}"
                    ).add_to(m)

                coords = list(zip(dd['ละติจูด'].tolist(), dd['ลองจิจูด'].tolist()))
                if len(coords) >= 2:
                    folium.PolyLine(
                        locations=coords, color=hex_color, weight=4, opacity=0.8,
                        tooltip=f"เส้นทาง {d} ({len(coords)} จุด)"
                    ).add_to(m)
                    folium.Marker(
                        location=coords[0],
                        icon=folium.Icon(color=f_color, icon='play', prefix='fa'),
                        tooltip=f"เริ่มต้น {d}: {dd['จุดติดตั้งกล้อง'].iloc[0]}"
                    ).add_to(m)
                    folium.Marker(
                        location=coords[-1],
                        icon=folium.Icon(color=f_color, icon='flag', prefix='fa'),
                        tooltip=f"สิ้นสุด {d}: {dd['จุดติดตั้งกล้อง'].iloc[-1]}"
                    ).add_to(m)

            components.html(m.get_root().render(), height=460)


def run_realtime_intelligence(active_db_pl):
    """Realtime intelligence: thresholds ผ่อนลง เหมาะข้อมูลที่ยังไม่ครบวัน
    E2: แต่ละคัน≥ 4 กล้อง, shared ≥ 4, dist ≥ 100km, score ≥ 75
    E3: ≥ 5 กล้อง, dist ≥ 150km, U-turn ✅, score ≥ 80
    """
    return run_intelligence_orchestrator(
        active_db_pl,
        e2_cam_pre=4, e2_shared=4, e2_dist=100, e2_score=75,
        e3_cams=5,   e3_dist=150, e3_score=80
    )


# ─────────────────────────────────────────────────────────────────────────────
# 🗺️ CACHED MAP BUILDERS — rendered once per unique dataset, not per click
# ─────────────────────────────────────────────────────────────────────────────
@st.cache_data(ttl=600, show_spinner=False)
def _build_clone_map_html(lat_mean: float, lon_mean: float,
                           normal_coords: tuple, ghost_coords: tuple,
                           show_real: bool = True, show_fake: bool = True) -> str:
    """Build ghost/clone map HTML — cached per unique coord set."""
    m = folium.Map(location=[lat_mean, lon_mean], zoom_start=9)
    if show_real:
        for lat, lon, tm, cam in normal_coords:
            folium.Marker(location=(lat, lon), popup=f"{tm} - {cam}",
                          icon=folium.Icon(color='blue', icon='car', prefix='fa')).add_to(m)
        if len(normal_coords) > 1:
            plugins.AntPath([(lat, lon) for lat, lon, _, _ in normal_coords],
                            color='blue', weight=4).add_to(m)
    if show_fake:
        for lat, lon, tm, cam, spd in ghost_coords:
            popup_html = (f"<b>🚨 พิกัดผิดปกติ (คาดว่ารถสวมทะเบียน)</b>"
                          f"<br>เวลา: {tm}<br>จุดตรวจ: {cam}"
                          f"<br>ความเร็วประเมิน: {spd:.0f} กม./ชม.")
            folium.Marker(location=(lat, lon), popup=popup_html,
                          icon=folium.Icon(color='red', icon='warning-sign')).add_to(m)
    return m.get_root().render()


@st.cache_data(ttl=600, show_spinner=False)
def _build_tactical_map_html(lat_mean: float, lon_mean: float,
                              car_tracks: tuple, is_convoy: bool) -> str:
    """Build tactical track map HTML — cached per unique car/coord combination."""
    m = folium.Map(location=[lat_mean, lon_mean], zoom_start=9)
    hex_pastel  = ['#9f1239', '#1e3a8a', '#047857', '#4338ca', '#b45309', '#be123c'] * 5
    cool_colors = ['#1e3a8a', '#0369a1', '#047857', '#4338ca', '#334155', '#0f766e']
    for idx, (car, coords, times, cams) in enumerate(car_tracks):
        if is_convoy:
            f_color = 'red'  if idx == 0 else 'blue'
            h_color = '#dc2626' if idx == 0 else cool_colors[(idx - 1) % len(cool_colors)]
        else:
            f_color, h_color = 'blue', hex_pastel[idx % len(hex_pastel)]
        for (lat, lon), tm, cam in zip(coords, times, cams):
            folium.Marker(location=(lat, lon),
                          popup=f"<b>{car}</b><br>{tm} - {cam}",
                          icon=folium.Icon(color=f_color, icon='car', prefix='fa')).add_to(m)
        if len(coords) > 1:
            plugins.AntPath(coords, color=h_color, weight=4,
                            dash_array=([10, 20] if is_convoy else [0])).add_to(m)
    return m.get_root().render()


def render_case_dossier(selected_target, active_db, priority_df):
    # Safety: หาก active_db ไม่มีคอลัมน์ที่ต้องการ

    if active_db is None or active_db.empty or 'ทะเบียน_Full' not in active_db.columns:
        st.info("⚠️ ไม่พบข้อมูลรายละเอียด — กรุณาโหลดข้อมูลวันที่เลือกใหม่อีกครั้งผ่าน Admin Portal")
        return
    _target_rows = priority_df[priority_df['Target_ID'].astype(str).str.strip() == str(selected_target).strip()]
    if _target_rows.empty:
        st.warning(f"⚠️ ไม่พบเป้าหมาย '{selected_target}' — กรุณา Refresh หน้า")
        return
    target_info = _target_rows.iloc[0]
    cars = target_info['Cars_List']
    case_data = active_db[active_db['ทะเบียน_Full'].isin(cars)].sort_values('Datetime')
    
    is_clone = "สวมทะเบียน" in target_info['ประเภท']
    is_convoy = "ขบวน" in target_info['ประเภท']
    is_anomaly = "ผิดปกติ" in target_info['ประเภท']
    
    total_dist_km = 0.0
    total_time_hr = 0.0
    
    if len(cars) > 0:
        main_car_df = case_data[case_data['ทะเบียน_Full'] == cars[0]].sort_values('Datetime')
        if len(main_car_df) > 1:
            first_row = main_car_df.iloc[0]
            last_row = main_car_df.iloc[-1]
            total_time_hr = (last_row['Datetime'] - first_row['Datetime']).total_seconds() / 3600.0
            
            if total_time_hr > 0:
                total_straight_km = sum(calculate_haversine(main_car_df.iloc[i-1]['ละติจูด'], main_car_df.iloc[i-1]['ลองจิจูด'], main_car_df.iloc[i]['ละติจูด'], main_car_df.iloc[i]['ลองจิจูด']) for i in range(1, len(main_car_df)))
                total_dist_km = total_straight_km * 1.35
                    
    st.markdown("<div class='dossier-section print-hidden'><hr style='border: 2px solid #94a3b8;'></div>", unsafe_allow_html=True)
    
    col_header, col_btn = st.columns([8, 2])
    with col_header:
        st.markdown(f"## 📂 ข้อมูลเป้าหมายเฝ้าระวัง: {selected_target}")
    with col_btn:
        components.html("""
            <button onclick="window.parent.print()" style="width: 100%; padding: 10px; background-color: #0f172a; color: white; border: none; border-radius: 5px; cursor: pointer; font-weight: bold; font-family: sans-serif; box-shadow: 0 2px 4px rgba(0,0,0,0.2);">
                🖨️ พิมพ์ข้อมูลแฟ้มคดี
            </button>
        """, height=50)

    conn = sqlite3.connect(DB_PATH)
    status_row = conn.execute("SELECT status FROM target_status WHERE Target_ID=?", (selected_target,)).fetchone()
    current_status = status_row[0] if status_row else "🔴 เฝ้าระวังใหม่"
    
    st.markdown("#### 🎯 ระบุสถานะเป้าหมาย (Action Status)")
    status_options = ["🔴 เฝ้าระวังใหม่", "🟡 สั่งการตรวจสอบแล้ว", "🟢 เคลียร์เป้าหมาย/จับกุมแล้ว"]
    new_status = st.selectbox("ปรับปรุงสถานะ:", status_options, index=status_options.index(current_status), key=f"status_{selected_target}", label_visibility="collapsed")
    
    if new_status != current_status:
        conn.execute("INSERT OR REPLACE INTO target_status (Target_ID, status, last_update) VALUES (?, ?, ?)", (selected_target, new_status, datetime.now().strftime("%Y-%m-%d %H:%M:%S")))
        conn.commit()
        st.success(f"✅ อัปเดตสถานะเป็น: {new_status} เรียบร้อยแล้ว! (มีผลทันทีในตารางเป้าหมาย)")
        st.session_state['force_refresh'] = True 
    conn.close()
    
    # === Layout แยกตาม Engine ===
    if is_clone:
        col_map, col_info = st.columns([6, 4])
        with col_info:
            st.markdown(f"<div class='dossier-reason'><b>🚨 ภัยคุกคามระดับวิกฤต: </b><br><span style='font-size:16px;'>{target_info['พฤติกรรมต้องสงสัย']}</span></div>", unsafe_allow_html=True)
            st.markdown("### 🔍 วิเคราะห์พยานหลักฐาน (Forensic Box)")
            show_real = st.checkbox("🟢 แสดงเส้นทางรถคันจริง (Real Trajectory)", value=True)
            show_fake = st.checkbox("🚨 แสดงพิกัดรถสวมทะเบียน (Ghost Placements)", value=True)
            
            total_reads = len(case_data)
            cam_str = ", ".join([f"{k}" for k, v in case_data['จุดติดตั้งกล้อง'].value_counts().head(3).items()])
            prov_str = ", ".join(list(set(case_data['จังหวัด'].unique()) - {""}))
            
            # 🧹 Clean HTML Summary 
            summary_md = f"""
**📌 จังหวัดที่จดทะเบียน:** {prov_str}

**📊 สถิติการตรวจพบสะสม:** {total_reads} ครั้ง

**📍 จุดตรวจที่ปรากฏตัวบ่อยที่สุด:** {cam_str}
            """
            st.markdown("<div class='dossier-summary'>", unsafe_allow_html=True)
            st.markdown("#### 📋 สรุปข้อมูลประวัติเป้าหมาย (Intelligence Summary)")
            st.markdown(summary_md)
            st.markdown("</div>", unsafe_allow_html=True)
            
        with col_map:
            st.markdown("### 🗺️ แผนที่แยกเงารถสวมทะเบียน (2D Ghost Tracker)")
            c_df = case_data[case_data['ทะเบียน_Full'] == cars[0]].sort_values('Datetime')
            _normal_coords = []
            _ghost_coords  = []
            for _r in c_df.itertuples():
                _spd = getattr(_r, 'Speed_kmh', 0)
                if _spd and pd.notna(_spd) and _spd > 200:
                    _ghost_coords.append((_r.ละติจูด, _r.ลองจิจูด, _r.เวลา, _r.จุดติดตั้งกล้อง, _spd))
                else:
                    _normal_coords.append((_r.ละติจูด, _r.ลองจิจูด, _r.เวลา, _r.จุดติดตั้งกล้อง))
            _lat_m = case_data['ละติจูด'].mean()
            _lon_m = case_data['ลองจิจูด'].mean()
            with st.spinner('🗺️ โหลดแผนที่...'):
                _map_html = _build_clone_map_html(
                    _lat_m, _lon_m,
                    tuple(_normal_coords), tuple(_ghost_coords),
                    show_real, show_fake
                )
            components.html(_map_html, height=400)

    else:
        if target_info['ประเภท'] == "กลุ่มเป้าหมายความมั่นคงระดับสูงสุด":
            st.markdown(f"<div class='dossier-reason'><b>🚨 ภัยคุกคามระดับวิกฤต: </b><br><span style='font-size:16px;'>{target_info['พฤติกรรมต้องสงสัย']}</span></div>", unsafe_allow_html=True)
        else:
            st.markdown(f"<div class='dossier-reason' style='background-color:#f8fafc; border-color:#cbd5e1; color:#0f172a;'><b>⚠️ ตรวจพบพฤติการณ์ต้องสงสัย:</b> {target_info['พฤติกรรมต้องสงสัย']} <br><span style='font-size:14px; opacity:0.8;'>(ระดับภัยคุกคาม: {target_info['Risk Score']})</span></div>", unsafe_allow_html=True)
            
        col_radar, col_summary = st.columns([4, 6])
        with col_radar:
            radar_data = target_info.get("Radar_Data", {})
            r_vals = [radar_data.get('Night',0), radar_data.get('Border',0), radar_data.get('Shuttle',0), radar_data.get('Regional',0), radar_data.get('Convoy',0)]
            theta_vals = ['ห้วงเวลาวิกาล (Max 20)', 'พื้นที่ชายแดน (Max 30)', 'ความถี่ในการผ่าน (Max 20)', 'ยานพาหนะต่างถิ่น (Max 10)', 'การเคลื่อนที่แบบกลุ่ม (Max 20)']
            r_vals.append(r_vals[0])
            theta_vals.append(theta_vals[0])
            fig_radar = go.Figure()
            fig_radar.add_trace(go.Scatterpolar(r=r_vals, theta=theta_vals, fill='toself', name='พฤติกรรมเป้าหมาย', line_color='#9f1239', fillcolor='rgba(159, 18, 57, 0.4)'))
            fig_radar.update_layout(polar=dict(radialaxis=dict(visible=True, range=[0, 30], showticklabels=False), gridshape='linear'), showlegend=False, height=300, margin=dict(t=20, b=20, l=40, r=40), title=dict(text="📊 แผนภูมิวิเคราะห์รูปแบบพฤติกรรม (Risk Radar)", font=dict(size=14)), paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)")
            st.plotly_chart(fig_radar, use_container_width=True, key=f"radar_chart_{selected_target}")
            
        with col_summary:
            total_reads = len(case_data)
            night_reads = len(case_data[case_data['Is_Night'] == True])
            night_pct = (night_reads / total_reads) * 100 if total_reads > 0 else 0
            cam_str = ", ".join([f"{k} ({v} ครั้ง)" for k, v in case_data['จุดติดตั้งกล้อง'].value_counts().head(2).items()])
            prov_str = ", ".join(list(set(case_data['จังหวัด'].unique()) - {""}))
            
            # 🧹 Clean HTML Summary & ขยายความ Intelligence Summary
            dwell_str = ""
            if is_anomaly:
                border_logs = main_car_df[main_car_df['Zone'] == 'A']
                if not border_logs.empty and len(border_logs) > 1:
                    dwell_hrs = (border_logs['Datetime'].max() - border_logs['Datetime'].min()).total_seconds() / 3600.0
                    if dwell_hrs > 0: 
                        dwell_str = f"**⏱️ ระยะเวลาแช่ตัวโซนชายแดน:** {dwell_hrs:.1f} ชั่วโมง\n\n"

            summary_md = f"""
**📌 จังหวัดที่จดทะเบียน:** {prov_str}

**📊 สถิติการตรวจพบสะสม:** {total_reads} ครั้ง

{dwell_str}**🌙 สัดส่วนการปฏิบัติการยามวิกาล:** {night_pct:.1f}% ({night_reads} ครั้ง)

**📍 จุดตรวจที่ปรากฏตัวบ่อยที่สุด:** {cam_str}
"""
            
            if is_convoy:
                cams_in_order = main_car_df['จุดติดตั้งกล้อง'].unique().tolist()
                start_cam = cams_in_order[0] if cams_in_order else "-"
                end_cam = cams_in_order[-1] if cams_in_order else "-"
                start_time = main_car_df['Datetime'].min().strftime('%H:%M:%S')
                gap_str = target_info.get("ระยะห่างเฉลี่ย", "-")
                total_dist_val = target_info.get("Total_Dist", f"{total_dist_km:.1f}") if target_info.get("Total_Dist", "-") != "-" else f"{total_dist_km:.1f}"
                summary_md += f"\n\n---\n**🚘 บทวิเคราะห์พฤติกรรมขบวนรถ (AI Insight):**\nขบวนรถก่อตัวที่ด่าน **{start_cam}** เมื่อเวลา **{start_time}** และสิ้นสุดที่ด่าน **{end_cam}** ระยะทางรวม **{total_dist_val}** กม. โดยมีระยะห่างเฉลี่ย **{gap_str}** ไม่พบพฤติกรรมการสลับคันนำ"
                
            elif is_anomaly:
                cams_in_order = main_car_df['จุดติดตั้งกล้อง'].unique().tolist()
                start_cam = cams_in_order[0] if len(cams_in_order)>0 else "-"
                end_cam = cams_in_order[-1] if len(cams_in_order)>0 else "-"
                total_dist_val = target_info.get("Total_Dist", f"{total_dist_km:.1f}")
                dwell_val = f"{dwell_hrs:.1f}" if 'dwell_hrs' in locals() and dwell_hrs > 0 else "1-4"
                
                summary_md += f"\n\n---\n**🔄 บทวิเคราะห์มุดช่องโหว่ (AI Insight):**\nเป้าหมายขับออกนอกพื้นที่ผ่านด่าน **{start_cam}** หายไปจากระบบเป็นเวลา **{dwell_val}** ชั่วโมง ก่อนจะปรากฏตัวอีกครั้งที่ด่าน **{end_cam}** ระยะทางสัญจรรวม **{total_dist_val}** กม."

            st.markdown("<div class='dossier-summary'>", unsafe_allow_html=True)
            st.markdown("#### 📋 สรุปข้อมูลประวัติเป้าหมาย (Intelligence Summary)")
            st.markdown(summary_md)
            st.markdown("</div>", unsafe_allow_html=True)
            
        if total_time_hr > 0 and len(main_car_df) > 1:
            actual_speed = total_dist_km / total_time_hr
            st.markdown(f"<div class='osrm-metric'>📍 <b>ประเมินพิกัดและระยะทาง (Offline Engine):</b> ทำการประเมินอัตราเร็วเฉลี่ยด้วยค่าชดเชยทางกายภาพ ได้ผลลัพธ์ <b>{actual_speed:.0f} กม./ชม.</b> (ระยะทาง {total_dist_km:.1f} กม. ภายในระยะเวลา {total_time_hr:.1f} ชม.)</div>", unsafe_allow_html=True)
            
        st.markdown("### 🗺️ แผนที่ระบุพิกัดเป้าหมายทางยุทธวิธี (2D Map)")
        # เตรียมข้อมูลเป็น tuple สำหรับ cached builder
        _car_tracks = []
        for _idx, _c in enumerate(cars):
            _cd = case_data[case_data['ทะเบียน_Full'] == _c].sort_values('Datetime')
            _coords = tuple((_r.ละติจูด, _r.ลองจิจูด) for _r in _cd.itertuples())
            _times  = tuple(str(_r.เวลา)     for _r in _cd.itertuples())
            _cams   = tuple(str(_r.จุดติดตั้งกล้อง) for _r in _cd.itertuples())
            _car_tracks.append((_c, _coords, _times, _cams))
        _lat_m = case_data['ละติจูด'].mean()
        _lon_m = case_data['ลองจิจูด'].mean()
        with st.spinner('🗺️ โหลดแผนที่...'):
            _map_html = _build_tactical_map_html(
                _lat_m, _lon_m, tuple(_car_tracks), is_convoy
            )
        components.html(_map_html, height=400)

    if is_convoy:
        st.markdown("### 🔗 ตารางวิเคราะห์โครงข่ายขบวนรถ (Convoy Formation Analysis)")
        convoy_details = []
        cams_in_order = case_data.sort_values('Datetime').drop_duplicates('จุดติดตั้งกล้อง', keep='first')['จุดติดตั้งกล้อง'].tolist()
        
        for cam in cams_in_order:
            cam_data = case_data[case_data['จุดติดตั้งกล้อง'] == cam].sort_values('Datetime')
            if len(cam_data) > 1: 
                dt_str = cam_data.iloc[0]['Datetime'].strftime('%Y/%m/%d')
                num_cars = len(cam_data)
                
                lead_plate = cam_data.iloc[0]['ทะเบียน_Full']
                
                plates = []
                roles = []
                times = []
                speeds = []
                
                for idx, row in cam_data.iterrows():
                    plates.append(row['ทะเบียน_Full'])
                    roles.append("รถนำ(Scout)" if row['ทะเบียน_Full'] == lead_plate else "รถตาม")
                    times.append(row['Datetime'].strftime('%H:%M:%S'))
                    spd = row['Speed_kmh']
                    speeds.append(f"{spd:.0f}" if pd.notna(spd) and spd > 0 else "-")
                        
                convoy_details.append({
                    "จุดตรวจจับร่วม": cam,
                    "วันที่": dt_str,
                    "จำนวนยานพาหนะในกลุ่มขบวน": num_cars,
                    "ลำดับหมายเลขทะเบียนในกลุ่มขบวน": " ➡️ ".join(plates),
                    "บทบาท": " ➡️ ".join(roles),
                    "ห้วงเวลาที่สัญจรผ่าน": " ➡️ ".join(times),
                    "ความเร็ว (กม./ชม.)": " ➡️ ".join(speeds)
                })
        
        if convoy_details:
            df_convoy = pd.DataFrame(convoy_details)
            df_convoy = df_convoy.sort_values(by=['จำนวนยานพาหนะในกลุ่มขบวน', 'วันที่'], ascending=[False, True])
            st.dataframe(df_convoy, use_container_width=True, hide_index=True)
            
    st.markdown("---")
    st.markdown("### ⏱️ โครงข่ายเวลา-สถานที่ (Staggered Grid Time-Space Diagram)")
    
    fig_ts = go.Figure()
    hex_pastel = ['#9f1239', '#1e3a8a', '#047857', '#4338ca', '#b45309', '#be123c'] * 5
    cool_colors = ['#1e3a8a', '#0369a1', '#047857', '#4338ca', '#334155', '#0f766e']
    
    cams_in_order = case_data.sort_values('Datetime').drop_duplicates('จุดติดตั้งกล้อง', keep='first')['จุดติดตั้งกล้อง'].tolist()
    cam_to_x = {cam: idx for idx, cam in enumerate(cams_in_order)}
    short_cams = [re.split(r',|\sกอง|\sสถานี|\sตำรวจ', str(cam))[0].strip() for cam in cams_in_order]
    
    t_min_cam = case_data.groupby('จุดติดตั้งกล้อง')['Datetime'].min().to_dict()
    
    for idx, c in enumerate(cars):
        c_df = case_data[case_data['ทะเบียน_Full'] == c].sort_values('Datetime')
        
        if is_clone:
            normal_df = c_df[c_df['Speed_kmh'] <= 200] if show_real else pd.DataFrame()
            ghost_df = c_df[c_df['Speed_kmh'] > 200] if show_fake else pd.DataFrame()
        else:
            normal_df = c_df
            ghost_df = pd.DataFrame()
            
        icon_str = "🚚" if "บรร取ุก" in str(c_df.iloc[0]['ประเภทรถ']) or "บรรทุก" in str(c_df.iloc[0]['ประเภทรถ']) else "🚗"
        
        if is_convoy:
            if idx == 0:
                line_color, car_name = '#dc2626', f"🔴 รถนำ: {c}"
            else:
                line_color, car_name = cool_colors[(idx-1) % len(cool_colors)], f"🚙 รถตาม: {c}"
        elif is_clone:
            line_color, car_name = '#10b981', f"รถจริง: {c}"
        else:
            line_color, car_name = hex_pastel[idx % len(hex_pastel)], f"เป้าหมาย: {c}"
        
        if not normal_df.empty:
            x_vals = []
            text_vals = []
            for _, r in normal_df.iterrows():
                cam = r['จุดติดตั้งกล้อง']
                base_x = cam_to_x[cam]
                time_diff_min = (r['Datetime'] - t_min_cam[cam]).total_seconds() / 60.0
                offset_x = base_x + (min(time_diff_min, 60) * 0.015) 
                x_vals.append(offset_x)
                text_vals.append(f"{icon_str} {r['Datetime'].strftime('%H:%M:%S')}")
                
            fig_ts.add_trace(go.Scatter(
                x=x_vals, y=[car_name]*len(normal_df), mode='lines+markers+text',
                name=car_name, text=text_vals, textposition="top center", 
                textfont=dict(size=13, color='black'),
                marker=dict(size=10, color=line_color, line=dict(color='white', width=1)),
                line=dict(width=3, color=line_color)
            ))
            
        if not ghost_df.empty:
            gx_vals = []
            gtext_vals = []
            for _, r in ghost_df.iterrows():
                cam = r['จุดติดตั้งกล้อง']
                base_x = cam_to_x.get(cam, len(cams_in_order))
                time_diff_min = (r['Datetime'] - t_min_cam.get(cam, r['Datetime'])).total_seconds() / 60.0
                offset_x = base_x + (min(time_diff_min, 60) * 0.015)
                gx_vals.append(offset_x)
                gtext_vals.append(f"🚨 {r['Datetime'].strftime('%H:%M:%S')}")
                
            fig_ts.add_trace(go.Scatter(
                x=gx_vals, y=[f"รถแฝด: {c}"]*len(ghost_df), mode='markers+text',
                name=f"รถแฝด: {c}", text=gtext_vals, textposition="top center", 
                textfont=dict(size=14, color='red'),
                marker=dict(size=15, color='red', symbol='x')
            ))
            
    fig_ts.update_layout(
        xaxis_title="จุดติดตั้งกล้อง (เรียงตามลำดับผ่าน)", yaxis_title="สถานะ/พฤติกรรม (นำ-ตาม)",
        showlegend=True, height=max(600, len(cars) * 100), margin=dict(l=20, r=20, t=40, b=50),
        plot_bgcolor='rgba(248, 250, 252, 0.8)', paper_bgcolor='rgba(0,0,0,0)',
        legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1),
        xaxis=dict(
            tickmode='array', tickvals=list(range(len(cams_in_order))), ticktext=short_cams,
            showgrid=True, gridcolor='#cbd5e1', gridwidth=1.5, tickangle=-45
        ), 
        yaxis=dict(type='category', showgrid=True, gridcolor='#f1f5f9', autorange='reversed')
    )
    
    st.plotly_chart(fig_ts, use_container_width=True, key=f"ts_horizontal_{selected_target}")

    st.markdown("---")
    st.markdown("### 📋 ตารางพยานหลักฐาน (Raw Evidence Data)")
    
    raw_evidence = case_data[['วันที่', 'เวลา', 'ทะเบียน_Full', 'จุดติดตั้งกล้อง', 'ประเภทรถ', 'Speed_kmh']].copy()
    raw_evidence['Speed_kmh'] = raw_evidence['Speed_kmh'].round(1)
    raw_evidence = raw_evidence.rename(columns={'วันที่': 'วันที่เกิดเหตุ', 'เวลา': 'เวลาโผล่', 'ทะเบียน_Full': 'หมายเลขทะเบียน', 'จุดติดตั้งกล้อง': 'พิกัดจุดตรวจ', 'ประเภทรถ': 'ประเภท', 'Speed_kmh': 'อัตราเร็ว (กม./ชม.)'})
    st.dataframe(raw_evidence.reset_index(drop=True), use_container_width=True)
    excel_download_button(raw_evidence.reset_index(drop=True),
                          f"evidence_{selected_target}.xlsx", "📥 Export พยานหลักฐาน (Excel)")

    # ── AI Feedback widget (เฉพาะ Admin ขึ้นไป) ──────────────────────────────
    if has_role('super_admin', 'admin'):
        _eng_type = target_info.get('ประเภท', 'ไม่ระบุ') if 'target_info' in dir() else 'ไม่ระบุ'
        _rpt_date = (str(active_db['Datetime'].dt.date.max())
                     if not active_db.empty and 'Datetime' in active_db.columns
                     else datetime.now().strftime('%Y-%m-%d'))
        render_feedback_widget(str(selected_target), str(_eng_type), _rpt_date)
    else:
        st.info("📋 การบันทึก AI Feedback เป็นสิทธิ์เฉพาะเจ้าหน้าที่ระดับ Admin ขึ้นไป")


    st.markdown("</div>", unsafe_allow_html=True)

def show_clickable_table(df_display, table_key, active_db, priority_df):
    if df_display.empty:
        st.info("🟢 ไม่พบเป้าหมายที่อยู่ในเกณฑ์เฝ้าระวัง")
        return
        
    conn = sqlite3.connect(DB_PATH)
    status_df = pd.read_sql("SELECT Target_ID, status FROM target_status", conn)
    conn.close()
    
    df_clean = df_display.copy()
    if not status_df.empty:
        df_clean = df_clean.merge(status_df, on='Target_ID', how='left')
    else:
        df_clean['status'] = np.nan
        
    df_clean['สถานะ'] = df_clean['status'].fillna("🔴 เฝ้าระวังใหม่")
    df_clean['Risk Score'] = df_clean['Risk Score'].fillna(0).astype(int).astype(str) + "%"
    
    if table_key == "t_cloned":
        cols_order = ['สถานะ', 'ระดับ', 'เป้าหมาย', 'Speed_Warp', 'เวลาโผล่ล่าสุด', 'จุดตรวจพบล่าสุด', 'พฤติกรรมต้องสงสัย', 'Risk Score']
        df_clean = df_clean.rename(columns={'Speed_Warp': 'ความเร็วที่ผิดปกติ (กม./ชม.)'})
        cols_order[3] = 'ความเร็วที่ผิดปกติ (กม./ชม.)'
    elif table_key == "t_others":
        cols_order = ['สถานะ', 'ระดับ', 'เป้าหมาย', 'ผ่านร่วมกัน (ด่าน)', 'Total_Dist', 'จุดตรวจพบล่าสุด', 'พฤติกรรมต้องสงสัย', 'Risk Score']
        df_clean = df_clean.rename(columns={'ผ่านร่วมกัน (ด่าน)': 'จำนวนด่านที่ผ่าน (ด่าน)', 'Total_Dist': 'ระยะทางสะสม (กม.)'})
        cols_order[3] = 'จำนวนด่านที่ผ่าน (ด่าน)'
        cols_order[4] = 'ระยะทางสะสม (กม.)'
    else:
        cols_order = ['สถานะ', 'ระดับ', 'เป้าหมาย', 'ผ่านร่วมกัน (ด่าน)', 'ระยะห่างเฉลี่ย', 'จุดตรวจพบล่าสุด', 'พฤติกรรมต้องสงสัย', 'Risk Score']
    # กรอง cols_order ให้เฉพาะที่มีใน df_clean
    cols_order = [c for c in cols_order if c in df_clean.columns]
    # บันทึก Target_ID map ก่อนตัดคอลัมน์
    _id_map = {i: str(df_clean.iloc[i]['Target_ID']).strip()
               for i in range(len(df_clean)) if 'Target_ID' in df_clean.columns}
    df_clean = df_clean[cols_order].copy()
    
    # Phase 1: ถ้า back ถูกขอส่ง run ก่อน ให้ init widget state ก่อนสร้าง (Streamlit อนุญาต)
    _back_req_key = f"back_req_{table_key}"
    if st.session_state.pop(_back_req_key, False):
        try:
            st.session_state[f"tbl_{table_key}"] = {"selection": {"rows": [], "columns": []}}
        except Exception:
            pass  # widget instantiated แล้วในรอบนี้ — รอ rerun หน้าถัดไป

    event = st.dataframe(
        df_clean,  # ไม่ใช้ style.map — ลด memory overhead ต่อทุก cell
        use_container_width=True, on_select="rerun", selection_mode="single-row", hide_index=True,
        key=f"tbl_{table_key}",
        column_config={
            'เป้าหมาย': st.column_config.TextColumn(
                'เป้าหมาย', width='large'
            ),
            'พฤติกรรมต้องสงสัย': st.column_config.TextColumn(
                'พฤติกรรมต้องสงสัย', width='large'
            ),
        }
    )
    excel_download_button(df_clean, f"priority_{table_key}.xlsx", "📥 Export ตารางนี้ (Excel)")
    
    if len(event.selection.rows) > 0:
        selected_idx = event.selection.rows[0]
        target_id = _id_map.get(selected_idx, '')
        if not target_id:
            st.warning("⚠️ ไม่สามารถระบุเป้าหมายได้ กรุณา Refresh")
        else:
            # Phase 2: ปุ่ม back ตั้ง back_req (ไม่ใช่ widget key โดยตรง) แล้ว rerun
            st.markdown("---")
            _bcol, _ = st.columns([1, 5])
            with _bcol:
                if st.button("🔙 ปิดรายละเอียด", key=f"back_{table_key}", use_container_width=True):
                    st.session_state[_back_req_key] = True  # ตั้ง key แยก (ไม่ใช่ widget key)
                    st.rerun()
            # ใช้ df_display เป็น lookup source เสมอเจอ Target_ID
            render_case_dossier(target_id, active_db, df_display)


# ==========================================
# 5. สถาปัตยกรรมหน้าจอหลัก (Decoupled UI)
# ==========================================
# ── Login Guard — ต้อง Login ก่อนเห็น UI ─────────────────────────────────────
require_login()

# ── System Health Check (ป้องกัน crash จาก Supabase throttle) ──────────────
if _IS_CLOUD and not st.session_state.get('_health_checked'):
    try:
        from supabase_sync import get_supabase_client as _hc_sb
        _hc_sb().table('users').select('username').limit(1).execute()
        st.session_state['_supabase_ok'] = True
    except Exception as _hc_e:
        st.session_state['_supabase_ok'] = False
        _hc_msg = str(_hc_e)[:120]
        st.warning(f"⚠️ ระบบ Cloud ทำงานในโหมดจำกัด — Supabase ไม่พร้อมชั่วคราว ({_hc_msg})\n\nข้อมูล Upload และ Login ยังใช้งานได้ปกติ")
    st.session_state['_health_checked'] = True
# ── Logo Banner ──────────────────────────────────────────────────────────────
import os as _os
_logo_path = _os.path.join(_os.path.dirname(__file__), 'logo.jpeg')
if _os.path.exists(_logo_path):
    st.image(_logo_path, use_container_width=True)

st.markdown("""
    <div class='main-title'>🛡️ HWPD 60 Intelligence Target &amp; Trap</div>
    <div class='main-subtitle'>ศูนย์ปฏิบัติการข่าวกรองสกัดกั้นบนสายทาง &nbsp;|&nbsp; HWPD 60 i-Trap Command Center</div>
    <hr class='header-divider'>
""", unsafe_allow_html=True)


_th = st.session_state.get('theme', 'dark')
_th_icon = '🌙' if _th == 'dark' else '☀️'
_th_label = 'Dark Mode' if _th == 'dark' else 'Light Mode'

st.sidebar.markdown("""
    <div style='text-align:center; padding: 14px 0 8px 0;'>
        <div style='font-size:42px; margin-bottom:6px;'>🛡️</div>
        <div style='font-size:17px; font-weight:800; color:#93c5fd; letter-spacing:2px; text-transform:uppercase;'>HWPD 60 i-Trap</div>
        <div style='font-size:12px; color:#64748b; letter-spacing:0.8px; margin-top:4px; font-weight:500;'>Intelligence Command System</div>
    </div>
    <hr style='border-color: rgba(59,130,246,0.2); margin: 8px 0 8px 0;'>
""", unsafe_allow_html=True)

# ── User Info + Logout ────────────────────────────────────────────────────────
_cur_user = get_current_user()
if _cur_user:
    _role_lbl = ROLE_LABEL.get(_cur_user.get('role', ''), _cur_user.get('role', ''))
    st.sidebar.markdown(
        f"<div style='background:rgba(99,102,241,0.12);padding:8px 12px;border-radius:8px;margin-bottom:6px;'>"
        f"<span style='font-size:12px;color:#94a3b8;'>ผู้ใช้งาน</span><br>"
        f"<span style='font-size:14px;font-weight:700;color:#e2e8f0;'>{_cur_user.get('display_name', _cur_user.get('username',''))}</span><br>"
        f"<span style='font-size:11px;color:#818cf8;'>{_role_lbl}</span>"
        f"</div>",
        unsafe_allow_html=True
    )
    if st.sidebar.button("🔓 ออกจากระบบ", key="logout_btn", use_container_width=True):
        logout()
        st.rerun()

if st.sidebar.button(f"{_th_icon} {_th_label}", key="theme_toggle_btn", use_container_width=True):
    st.session_state['theme'] = 'light' if _th == 'dark' else 'dark'
    st.rerun()

# Cloud sync status
if _CLOUD_ENABLED:
    show_sync_status()


# ── Portal Switch — แสดงตาม Role ─────────────────────────────────────────────
_is_admin_role = False
_portal_options = ["📊 ผู้บังคับบัญชา (Executive Dashboard)"]
mode = "📊 ผู้บังคับบัญชา (Executive Dashboard)"


if mode == "⚙️ แอดมิน (Admin Portal)":

    st.sidebar.markdown("---")
    
    _admin_tabs = [
        "🗂️ นำเข้าข้อมูล (Data Pipeline)",
        "📜 บัญชีรถยกเว้น (White-list)",
        "📊 AI Accuracy Dashboard",
    ]
    if has_role('super_admin'):
        _admin_tabs.append("👥 จัดการผู้ใช้ (User Management)")

    tab_upload, tab_whitelist, tab_accuracy, *_extra_tabs = st.tabs(_admin_tabs)
    tab_users = _extra_tabs[0] if _extra_tabs else None


    with tab_upload:
        st.header("🗂️ การจัดการฐานข้อมูล (Data Pipeline)")
        uploaded_files = st.file_uploader("นำเข้าแฟ้มประวัติจุดตรวจ LPR (CSV/Excel)", accept_multiple_files=True)
        
        if "dq_preview" not in st.session_state:
            st.session_state.dq_preview = None

        if uploaded_files:
            if st.button("🔍 1. ตรวจสอบคุณภาพข้อมูลเบื้องต้น (Data Quality Check)"):
                with st.spinner("กำลังวิเคราะห์โครงสร้างไฟล์..."):
                    st.session_state.dq_preview = preliminary_data_check(uploaded_files)
                    
            if st.session_state.dq_preview:
                dq = st.session_state.dq_preview
                st.info(f"📊 **รายงานคุณภาพข้อมูล:** พบข้อมูลทั้งหมด **{dq['total']:,}** รายการ | สมบูรณ์: **{dq['valid']:,}** รายการ | ป้ายทะเบียนอ่านไม่ได้ (ทิ้ง): **{dq['invalid']:,}** รายการ")
                
                if st.button("🚀 2. ยืนยันและเริ่มประมวลผล (Confirm & Execute Engines)"):
                    with st.spinner("🧠 ระบบกำลังใช้ Polars Engine ประมวลผลข้อมูลระดับ Big Data..."):
                        historical_db_pl = load_historical_data()
                        new_db_pl = process_raw_data_polars(dq['raw_df'])
                        
                        if not new_db_pl.is_empty():
                            # ★ ดึงวันที่จากข้อมูล CSV จริง
                            try:
                                _data_dates = new_db_pl['Datetime'].cast(pl.Date).unique().sort()
                                report_date = str(_data_dates[0]) if len(_data_dates) > 0 else datetime.now().strftime('%Y-%m-%d')
                            except:
                                report_date = datetime.now().strftime('%Y-%m-%d')

                            # ★★ Multi-Admin Merge: ดึง parquet ที่มีอยู่แล้วจาก Cloud ──────
                            cloud_db_pl = None
                            if _CLOUD_ENABLED and is_supabase_configured():
                                with st.spinner(f"☁️ กำลังดึงข้อมูลวันที่ {report_date} จาก Cloud เพื่อ Merge..."):
                                    from supabase_sync import pull_parquet_from_cloud
                                    cloud_db_pl = pull_parquet_from_cloud(report_date)
                                if cloud_db_pl is not None and not cloud_db_pl.is_empty():
                                    st.info(f"☁️ พบข้อมูลวันนี้ใน Cloud {len(cloud_db_pl):,} รายการ — กำลัง Merge รวมกัน")

                            # ★★ Merge: local parquet + cloud parquet + new CSV ───────────────
                            active_db_pl = save_to_memory(new_db_pl, historical_db_pl, cloud_db_pl)
                            load_historical_data.clear()

                            if not active_db_pl.is_empty():
                                # กรองเฉพาะวัน report_date
                                try:
                                    _report_date_lit = pl.lit(report_date).str.to_date()
                                    active_db_pl_for_date = active_db_pl.filter(
                                        pl.col("Datetime").cast(pl.Date) == _report_date_lit
                                    )
                                except Exception:
                                    active_db_pl_for_date = new_db_pl

                                if active_db_pl_for_date.is_empty():
                                    active_db_pl_for_date = new_db_pl

                                st.caption(f"📊 วิเคราะห์ข้อมูลรวม {len(active_db_pl_for_date):,} รายการ"
                                           f" (วัน {report_date} — ใหม่ {len(new_db_pl):,} + Cloud {len(cloud_db_pl) if cloud_db_pl is not None else 0:,} + Local เดิม)")

                                priority_df = run_intelligence_orchestrator(
                                    active_db_pl_for_date,
                                    e2_cam_pre=4, e2_shared=4, e2_dist=100, e2_score=80,
                                    e3_cams=5,   e3_dist=150, e3_score=80
                                )

                                active_db_pd = active_db_pl_for_date.to_pandas()
                                save_daily_report(report_date, priority_df, active_db_pd)
                                save_realtime_session(active_db_pd, report_date)

                                # ── ☁️ Push ผลลัพธ์ + parquet ขึ้น Supabase Cloud ────────────
                                if _CLOUD_ENABLED and is_supabase_configured():
                                    _cu = get_current_user()
                                    _uname = _cu.get('username', 'local') if _cu else 'local'
                                    _dname = _cu.get('display_name', '') if _cu else ''
                                    _fname = st.session_state.get('_upload_filename', 'unknown.csv')
                                    with st.spinner("☁️ กำลัง Sync ขึ้น Cloud..."):
                                        from supabase_sync import push_parquet_to_cloud
                                        # ★★ Push merged parquet กลับ Cloud (ให้ Admin คนอื่น pull ได้)
                                        push_parquet_to_cloud(report_date, active_db_pl_for_date)
                                        # Push priority results
                                        _metrics_dict = {}
                                        _cloud_push_daily(
                                            report_date, priority_df, _metrics_dict,
                                            _uname, len(active_db_pd)
                                        )
                                        # Push realtime summary
                                        _cloud_push_rt(
                                            report_date, priority_df, 1,
                                            str(active_db_pd['Datetime'].min()) if 'Datetime' in active_db_pd.columns else '',
                                            str(active_db_pd['Datetime'].max()) if 'Datetime' in active_db_pd.columns else '',
                                            _uname, len(active_db_pd)
                                        )
                                        _cloud_log_upload(_uname, _dname, _fname, report_date, len(active_db_pd))
                                    st.caption("☁️ Sync Cloud สำเร็จ (รวม Parquet Merge)")



                                st.success(f"✅ ประมวลผลสำเร็จ! ข้อมูลถูกบันทึกลงฐานข้อมูลเรียบร้อยแล้ว (Report Date: {report_date})")
                                st.session_state.dq_preview = None 
                                
                                # เคลียร์ cache ของ realtime session เพื่อให้โหลดข้อมูลใหม่ทันที
                                load_realtime_session.clear()
                                
                                st.session_state['nav_tab'] = "🏠 สรุปสถานการณ์ (Overview)"
                                time.sleep(1.5)
                                st.rerun()
                            else:
                                st.warning("⚠️ ข้อมูลในระบบว่างเปล่าหลังจากการกรอง ไม่สามารถวิเคราะห์ได้")
                        else:
                            st.error("❌ ไม่พบข้อมูลที่ถูกต้องในไฟล์ที่อัปโหลด")

    with tab_whitelist:
        st.header("📜 การจัดการบัญชีรถยกเว้น (White-list)")
        st.write("ทะเบียนรถในบัญชีนี้ จะถูก AI มองข้าม (Bypass) เพื่อลดการแจ้งเตือนรถของเจ้าหน้าที่ปฏิบัติงาน")
        
        col_w1, col_w2 = st.columns([7, 3])
        with col_w1:
            new_wl_plate = st.text_input("เพิ่มทะเบียนรถ (เช่น กค1234กรุงเทพมหานคร):")
            new_wl_note = st.text_input("หมายเหตุ (เช่น รถสายตรวจ สภ.เมือง):")
        with col_w2:
            st.write("")
            st.write("")
            if st.button("➕ เพิ่มเข้าบัญชีขาว"):
                if new_wl_plate:
                    clean_p = normalize_plate(new_wl_plate)
                    if clean_p:
                        conn = sqlite3.connect(DB_PATH)
                        conn.execute("INSERT OR REPLACE INTO whitelist_master (ทะเบียนรถ, หมายเหตุ) VALUES (?, ?)", (clean_p, new_wl_note))
                        conn.commit()
                        conn.close()
                        st.success(f"เพิ่ม {clean_p} เรียบร้อยแล้ว")
                    else:
                        st.error("รูปแบบทะเบียนไม่ถูกต้อง")
        
        st.markdown("---")
        conn = sqlite3.connect(DB_PATH)
        wl_df = pd.read_sql("SELECT ทะเบียนรถ, หมายเหตุ FROM whitelist_master", conn)
        conn.close()
        st.write("📋 **รายชื่อรถในบัญชีขาวปัจจุบัน:**")
        st.dataframe(wl_df, use_container_width=True, hide_index=True)
        if not wl_df.empty:
            del_plate = st.selectbox("เลือกทะเบียนที่ต้องการลบออกจากบัญชีขาว:", wl_df['ทะเบียนรถ'])
            if st.button("🗑️ ลบรายการ"):
                conn = sqlite3.connect(DB_PATH)
                conn.execute("DELETE FROM whitelist_master WHERE ทะเบียนรถ=?", (del_plate,))
                conn.commit()
                conn.close()
                st.rerun()

    with tab_accuracy:
        st.header("📊 AI Accuracy Dashboard — ความแม่นยำของระบบ")
        ensure_feedback_table()
        try:
            _dbc = sqlite3.connect(DB_PATH)
            _all_fb = pd.read_sql("SELECT * FROM ai_feedback ORDER BY feedback_date DESC", _dbc)
            _dbc.close()
        except:
            _all_fb = pd.DataFrame()

        if _all_fb.empty:
            st.info("📭 ยังไม่มี Feedback — กรุณากดยืนยันผลการตรวจสอบในหน้า Case Dossier")
        else:
            _confirmed = _all_fb[_all_fb['is_correct'] != -1]
            _correct   = _all_fb[_all_fb['is_correct'] == 1]
            _wrong     = _all_fb[_all_fb['is_correct'] == 0]
            _total_acc = (len(_correct) / len(_confirmed) * 100) if len(_confirmed) > 0 else 0

            # ── Summary metrics ──────────────────────────────────────────
            ma1, ma2, ma3, ma4 = st.columns(4)
            with ma1: st.metric("📋 Feedback ทั้งหมด", len(_all_fb))
            with ma2: st.metric("✅ ถูกต้อง", len(_correct))
            with ma3: st.metric("❌ ไม่ถูกต้อง", len(_wrong))
            with ma4: st.metric("🎯 Accuracy รวม", f"{_total_acc:.0f}%")

            # ── Accuracy by engine type ─────────────────────────────────
            if not _confirmed.empty:
                st.markdown("---")
                st.markdown("#### 📊 ความแม่นยำแยกตามประเภท")
                _acc_rows = []
                for _eng in _confirmed['engine_type'].unique():
                    _edf = _confirmed[_confirmed['engine_type'] == _eng]
                    _nc  = len(_edf[_edf['is_correct'] == 1])
                    _nt  = len(_edf)
                    _ac  = _nc / _nt * 100 if _nt > 0 else 0
                    _acc_rows.append({
                        'ประเภท Engine': _eng,
                        '✅ ถูกต้อง': _nc,
                        '❌ ไม่ถูก': _nt - _nc,
                        'รวม': _nt,
                        'Accuracy': f'{_ac:.0f}%',
                    })
                _acc_df = pd.DataFrame(_acc_rows)
                st.dataframe(_acc_df, use_container_width=True, hide_index=True)
                excel_download_button(_acc_df, "ai_accuracy.xlsx", "📥 Export Accuracy Report (Excel)")

            # ── Full feedback log ──────────────────────────────────────────
            st.markdown("---")
            st.markdown("#### 📋 ประวัติ Feedback ทั้งหมด")
            _vm = {1: '✅ ถูกต้อง', 0: '❌ ไม่ถูก', -1: '⚠️ ยังไม่ทราบ'}
            _log = _all_fb.copy()
            _log['ผล'] = _log['is_correct'].map(_vm)
            _log_disp = _log[['target_id','engine_type','report_date','ผล','notes','feedback_date']]
            _log_disp = _log_disp.rename(columns={
                'target_id': 'เป้าหมาย', 'engine_type': 'ประเภท',
                'report_date': 'วันที่รายงาน', 'notes': 'หมายเหตุ',
                'feedback_date': 'วันที่ให้ Feedback'
            })
            st.dataframe(_log_disp, use_container_width=True, hide_index=True)
            excel_download_button(_log_disp, "ai_feedback_log.xlsx", "📥 Export Feedback Log (Excel)")

    # ── TAB: จัดการผู้ใช้ (Super Admin only) ──────────────────────────────────
    if tab_users and has_role('super_admin'):
        with tab_users:
            st.header("👥 จัดการผู้ใช้ระบบ (User Management)")
            from auth import get_all_users, update_user_password, deactivate_user, create_user

            all_users = get_all_users()

            # ── รายชื่อผู้ใช้ทั้งหมด ────────────────────────────────────────
            st.markdown("### 📋 รายชื่อผู้ใช้ทั้งหมด")
            if all_users:
                user_table = []
                for u in all_users:
                    role_icon = {"super_admin": "👑 Super Admin", "admin": "🔧 Admin", "viewer": "👁️ Viewer"}.get(u.get('role', ''), u.get('role', ''))
                    user_table.append({
                        "สถานะ":     "✅ Active" if u.get('is_active') else "❌ Inactive",
                        "ชื่อแสดง":   u.get('display_name', ''),
                        "Username":   u.get('username', ''),
                        "Role":       role_icon,
                        "เข้าใช้ล่าสุด": str(u.get('last_login', '—'))[:16].replace('T', ' '),
                        "สร้างเมื่อ":   str(u.get('created_at', '—'))[:10],
                    })
                st.dataframe(pd.DataFrame(user_table), use_container_width=True, hide_index=True)
            else:
                st.info("ไม่พบข้อมูลผู้ใช้")

            st.markdown("---")

            col_pw, col_role = st.columns(2)

            # ── เปลี่ยนรหัสผ่าน ──────────────────────────────────────────────
            with col_pw:
                st.markdown("### 🔑 เปลี่ยนรหัสผ่าน")
                user_list = [u['username'] for u in all_users] if all_users else []
                chg_user = st.selectbox("เลือก User:", user_list, key="local_chg_user")
                new_pw1  = st.text_input("รหัสผ่านใหม่:", type="password", key="local_pw1")
                new_pw2  = st.text_input("ยืนยันรหัสผ่าน:", type="password", key="local_pw2")
                if st.button("💾 บันทึกรหัสผ่านใหม่", use_container_width=True, key="local_btn_pw"):
                    if not new_pw1:
                        st.error("กรุณากรอกรหัสผ่านใหม่")
                    elif new_pw1 != new_pw2:
                        st.error("❌ รหัสผ่านทั้งสองไม่ตรงกัน")
                    elif len(new_pw1) < 6:
                        st.error("❌ รหัสผ่านต้องมีอย่างน้อย 6 ตัวอักษร")
                    else:
                        ok = update_user_password(chg_user, new_pw1)
                        if ok:
                            st.success(f"✅ เปลี่ยนรหัสผ่านของ **{chg_user}** สำเร็จ!")
                        else:
                            st.error("❌ เปลี่ยนรหัสผ่านไม่สำเร็จ — ตรวจสอบการเชื่อมต่อ Supabase")

            # ── เปลี่ยน Role / ปิด User ──────────────────────────────────────
            with col_role:
                st.markdown("### ⚙️ จัดการ Role / สถานะ")
                safe_users = [u['username'] for u in all_users if u['username'] != 'supuseradmin'] if all_users else []
                mgmt_user = st.selectbox("เลือก User:", safe_users, key="local_mgmt_user")
                new_role  = st.selectbox("Role ใหม่:", ["viewer", "admin", "super_admin"], key="local_mgmt_role")
                col_r1, col_r2 = st.columns(2)
                with col_r1:
                    if st.button("🔄 เปลี่ยน Role", use_container_width=True, key="local_btn_role"):
                        try:
                            from supabase_sync import get_supabase_client
                            get_supabase_client().table('users').update({'role': new_role}).eq('username', mgmt_user).execute()
                            st.success(f"✅ เปลี่ยน role ของ {mgmt_user} เป็น {new_role}")
                        except Exception as e:
                            st.error(f"❌ {e}")
                with col_r2:
                    if st.button("🚫 ปิด User", use_container_width=True, key="local_btn_deact"):
                        ok = deactivate_user(mgmt_user)
                        if ok:
                            st.success(f"✅ ปิด account {mgmt_user} แล้ว")
                        else:
                            st.error("❌ ไม่สำเร็จ")

            st.markdown("---")

            # ── สร้าง User ใหม่ ────────────────────────────────────────────────
            st.markdown("### ➕ สร้างผู้ใช้ใหม่")
            c1, c2, c3, c4 = st.columns(4)
            with c1: n_uname = st.text_input("Username:", key="local_n_uname")
            with c2: n_dname = st.text_input("ชื่อแสดง:", key="local_n_dname")
            with c3: n_role  = st.selectbox("Role:", ["viewer", "admin", "super_admin"], key="local_n_role")
            with c4: n_pw    = st.text_input("รหัสผ่าน:", type="password", key="local_n_pw")
            if st.button("✅ สร้าง User ใหม่", use_container_width=True, key="local_btn_create"):
                if n_uname and n_pw and n_dname:
                    ok = create_user(n_uname.strip().lower(), n_pw, n_role, n_dname)
                    if ok:
                        st.success(f"✅ สร้าง User **{n_uname}** ({n_role}) สำเร็จ! — ให้รีเฟรชหน้านี้เพื่อเห็นรายชื่อใหม่")
                    else:
                        st.error("❌ สร้างไม่สำเร็จ — อาจมี Username นี้อยู่แล้ว")
                else:
                    st.error("กรุณากรอกข้อมูลให้ครบทุกช่อง")

elif mode == "📊 ผู้บังคับบัญชา (Executive Dashboard)":
    
    st.sidebar.markdown("---")
    
    # Load dates from Supabase FIRST
    available_dates = []
    if _CLOUD_ENABLED and is_supabase_configured():
        from supabase_sync import get_supabase_client
        supabase = get_supabase_client()
        try:
            res = supabase.table('cloud_daily_reports').select('report_date').order('report_date', desc=True).execute()
            if res.data:
                available_dates = [r['report_date'] for r in res.data]
        except: pass
        
    _tz_th = timezone(timedelta(hours=7))  # Bangkok UTC+7
    _cloud_today = datetime.now(_tz_th).strftime('%Y-%m-%d')

    if 'confirmed_date' not in st.session_state:
        st.session_state['confirmed_date'] = _cloud_today

    # เพิ่มวันนี้เข้า list ถ้ายังไม่มี (เพื่อให้ Realtime tab แสดงได้)
    if _cloud_today not in available_dates:
        available_dates = [_cloud_today] + available_dates

    if not available_dates or available_dates == [_cloud_today]:
        selected_date = _cloud_today
    else:
        # Determine index for selectbox
        idx = 0
        if st.session_state['confirmed_date'] in available_dates:
            idx = available_dates.index(st.session_state['confirmed_date'])
        elif available_dates:
            st.session_state['confirmed_date'] = available_dates[0]

        with st.sidebar.form("sidebar_date_form", border=False):
            st.markdown("<div style='font-size:14px; font-weight:600; color:#fbbf24; margin-bottom:8px;'>📅 ตัวกรองข้อมูลรายวัน</div>", unsafe_allow_html=True)
            c1, c2 = st.columns([6, 4])
            with c1:
                s_date = st.selectbox("เลือกวันที่:", available_dates, index=idx, label_visibility="collapsed")
            with c2:
                if st.form_submit_button("✅ ยืนยัน", use_container_width=True):
                    st.session_state['confirmed_date'] = s_date
                    st.rerun()
        selected_date = st.session_state['confirmed_date']

    st.sidebar.markdown("---")
    st.sidebar.markdown("### 🧭 เมนูเจาะลึกสถานการณ์")
    if st.sidebar.button("🏠 สรุปสถานการณ์ (Overview)", use_container_width=True): change_tab("🏠 สรุปสถานการณ์ (Overview)")
    if st.sidebar.button("🚨 รถสวมทะเบียน", use_container_width=True): change_tab("🚨 รถสวมทะเบียน")
    if st.sidebar.button("🚘 ขบวนรถลำเลียง", use_container_width=True): change_tab("🚘 ขบวนรถลำเลียง")
    if st.sidebar.button("🔍 รถพฤติกรรมต้องสงสัย", use_container_width=True): change_tab("🔄 พฤติกรรมมุดชายแดน")
    if st.sidebar.button("⭐ รถที่น่าสนใจ (Watch List)", use_container_width=True): change_tab("⭐ รถที่น่าสนใจ")
    
    if available_dates:

        st.markdown("""
        <div class="ticker-wrap">
            <div class="ticker-content">
                📡 CLOUD SYSTEM ONLINE | SECURE CONNECTION ESTABLISHED | HWPD 60 COMMAND CENTER ACTIVE...
            </div>
        </div>
        """, unsafe_allow_html=True)
        
        col_t1, col_t2 = st.columns([8, 2])
        
        # --- Main Date Selector Form ---
        with col_t2:
            with st.form("main_date_form", border=False):
                st.markdown("<div style='font-size:14px; font-weight:600; color:#e2e8f0; margin-bottom:8px;'>📅 เลือกวันที่รายงาน:</div>", unsafe_allow_html=True)
                c1, c2 = st.columns([6, 4])
                with c1:
                    m_date = st.selectbox("เลือกวันที่รายงาน:", available_dates, index=idx, label_visibility="collapsed")
                with c2:
                    if st.form_submit_button("✅ ยืนยัน", use_container_width=True):
                        st.session_state['confirmed_date'] = m_date
                        st.rerun()
                    
        selected_date = st.session_state['confirmed_date']
        with col_t1:
            st.markdown(f"<div style='padding: 10px; background-color: #f8fafc; border-left: 5px solid #10b981; border-radius: 5px; color: #0f172a;'><span class='live-dot'></span><b>Cloud Sync: Active</b> | กำลังแสดงผลรายงานข่าวกรองประจำวันที่: <b>{selected_date}</b></div>", unsafe_allow_html=True)
            
        priority_df = pd.DataFrame()
        metrics = {}
        reports_full_df = pd.DataFrame()
        
        historical_db_pl = pl.DataFrame()
        
        # Pull data from Supabase
        if _CLOUD_ENABLED and is_supabase_configured():
            with st.spinner("☁️ กำลังโหลดข้อมูลจาก Cloud..."):
                try:
                    # 1. Pull All Reports for historical reference
                    all_res = supabase.table('cloud_daily_reports').select('*').order('report_date', desc=True).execute()
                    if all_res.data:
                        reports_full_df = pd.DataFrame(all_res.data)
                        
                    # 2. Pull target date priority
                    res = supabase.table('cloud_daily_reports').select('priority_data, dashboard_metrics').eq('report_date', selected_date).execute()
                    if res.data and len(res.data) > 0:
                        import json
                        
                        p_data = res.data[0]['priority_data']
                        # if it's already a list (from supabase jsonb), use it directly
                        if isinstance(p_data, str):
                            p_data = json.loads(p_data)
                        priority_df = pd.DataFrame(p_data)
                        
                        import ast, re as _re
                        # ★ Filter + Format ตามมาตรฐาน DLT
                        if not priority_df.empty and 'เป้าหมาย' in priority_df.columns:
                            def _valid_priority_plate(target_str):
                                for part in str(target_str).split('/'):
                                    part = part.strip()
                                    ps = _re.sub(r' ', '', part)
                                    if _re.search(r'[ก-ฮ]\d', ps) and _re.search(r'\d[ก-ฮ]', ps): return True
                                    if _re.match(r'^[1-9]\d{5}[ก-ฮ]', ps): return True
                                return False
                            def _fmt_priority_plate(target_str):
                                parts = []
                                for part in str(target_str).split('/'):
                                    part = part.strip()
                                    part = _re.sub(r'([ก-ฮ])(\d)', r'\1 \2', part)
                                    part = _re.sub(r'(\d)([ก-ฮ])', r'\1 \2', part)
                                    part = _re.sub(r' +', ' ', part).strip()
                                    parts.append(part)
                                return ' / '.join(parts)
                            priority_df = priority_df[priority_df['เป้าหมาย'].apply(_valid_priority_plate)].reset_index(drop=True)
                            if not priority_df.empty:
                                priority_df['เป้าหมาย'] = priority_df['เป้าหมาย'].apply(_fmt_priority_plate)

                        # convert strings back to list/dict for UI render
                        if 'Cars_List' in priority_df.columns:
                            priority_df['Cars_List'] = priority_df['Cars_List'].apply(lambda x: ast.literal_eval(x) if isinstance(x, str) else x)
                        if 'Radar_Data' in priority_df.columns:
                            priority_df['Radar_Data'] = priority_df['Radar_Data'].apply(lambda x: ast.literal_eval(x) if isinstance(x, str) else x)
                        if 'dates_list' in priority_df.columns:
                            priority_df['dates_list'] = priority_df['dates_list'].apply(lambda x: ast.literal_eval(x) if isinstance(x, str) else x)
                            
                        m_data = res.data[0]['dashboard_metrics']
                        if isinstance(m_data, str):
                            m_data = json.loads(m_data) if m_data else {}
                        metrics = m_data if m_data else {}
                except Exception as e:
                    st.error(f"⚠️ Error loading report: {e}")
                
                # 3. Pull Parquet Data for maps & dossier (cached 30 min ลด egress)
                @st.cache_data(ttl=1800, show_spinner=False)
                def _cached_parquet(date: str):
                    from supabase_sync import pull_parquet_from_cloud as _ppc
                    result = _ppc(date)
                    return result if result is not None else pl.DataFrame()
                historical_db_pl = _cached_parquet(selected_date)
                
        if not historical_db_pl.is_empty():
            active_db_all = historical_db_pl.to_pandas()
            del historical_db_pl; import gc as _gc; _gc.collect()  # free Polars copy immediately
            _sel_date = pd.to_datetime(selected_date).date()
            active_db = active_db_all[active_db_all['Datetime'].dt.date == _sel_date].copy()
            if active_db.empty:
                active_db = active_db_all
        else:
            active_db_all = pd.DataFrame()
            active_db = pd.DataFrame()



        def _compute_fallback_metrics(priority_df, active_db_pd):
            import pandas as pd
            metrics = {}
            if not priority_df.empty and not active_db_pd.empty:
                apex_df = priority_df[priority_df['ประเภท'] == "กลุ่มเป้าหมายความมั่นคงระดับสูงสุด"]
                metrics['cat_apex'] = len(apex_df)
                metrics['cat_cloned'] = len(priority_df[priority_df['ประเภท'] == "กลุ่มเป้าหมายสวมทะเบียน"])
                metrics['cat_convoy_car'] = len(priority_df[priority_df['ประเภท'] == "กลุ่มรถยนต์เคลื่อนที่แบบขบวน"])
                metrics['cat_others'] = len(priority_df[priority_df['ประเภท'] == "กลุ่มรถต้องสงสัย"])
                
                targeted_cars = set()
                for cars in priority_df['Cars_List']: targeted_cars.update(cars)
                target_logs = active_db_pd[active_db_pd['ทะเบียน_Full'].isin(targeted_cars)].copy()
                
                if not target_logs.empty:
                    risk_map = {}
                    for _, row in priority_df.iterrows():
                        for car in row['Cars_List']:
                            risk_map[car] = max(risk_map.get(car, 0), row['Risk Score'])
                    target_logs['Risk_Score'] = target_logs['ทะเบียน_Full'].map(risk_map)
                    
                    cam_stats = target_logs.groupby('จุดติดตั้งกล้อง').agg(
                        lat=('ละติจูด', 'first'), lon=('ลองจิจูด', 'first'),
                        volume=('ทะเบียน_Full', 'nunique'), 
                        avg_score=('Risk_Score', 'mean'), max_score=('Risk_Score', 'max')
                    ).reset_index()
                    
                    plate_to_type = {}
                    for _, row in priority_df.iterrows():
                        for car in row['Cars_List']:
                            plate_to_type[car] = row['ประเภท']
                            
                    metrics['map_stats'] = cam_stats.to_dict('records')
                    
                    # Fix pandas warning for datetime
                    if not pd.api.types.is_datetime64_any_dtype(active_db_pd['Datetime']):
                        active_db_pd['Datetime'] = pd.to_datetime(active_db_pd['Datetime'])
                    if not pd.api.types.is_datetime64_any_dtype(target_logs['Datetime']):
                        target_logs['Datetime'] = pd.to_datetime(target_logs['Datetime'])
                        
                    active_db_pd['Hour'] = active_db_pd['Datetime'].dt.hour
                    target_logs['Hour'] = target_logs['Datetime'].dt.hour
                    target_logs['Threat_Type'] = target_logs['ทะเบียน_Full'].map(plate_to_type)
                    
                    hours = list(range(24))
                    total_hourly = active_db_pd.groupby('Hour')['ทะเบียน_Full'].nunique().reindex(hours, fill_value=0)
                    target_total_hr = target_logs.groupby('Hour')['ทะเบียน_Full'].nunique().reindex(hours, fill_value=0)
                    
                    metrics['clock'] = {
                        'total_hourly': total_hourly.tolist(),
                        'apex_hr': target_logs[target_logs['Threat_Type'] == 'กลุ่มเป้าหมายความมั่นคงระดับสูงสุด'].groupby('Hour')['ทะเบียน_Full'].nunique().reindex(hours, fill_value=0).tolist(),
                        'cloned_hr': target_logs[target_logs['Threat_Type'] == 'กลุ่มเป้าหมายสวมทะเบียน'].groupby('Hour')['ทะเบียน_Full'].nunique().reindex(hours, fill_value=0).tolist(),
                        'convoy_hr': target_logs[target_logs['Threat_Type'] == 'กลุ่มรถยนต์เคลื่อนที่แบบขบวน'].groupby('Hour')['ทะเบียน_Full'].nunique().reindex(hours, fill_value=0).tolist(),
                        'border_hr': target_logs[target_logs['Threat_Type'] == 'กลุ่มรถต้องสงสัย'].groupby('Hour')['ทะเบียน_Full'].nunique().reindex(hours, fill_value=0).tolist(),
                    }
                    
                    peak_target_hr = target_total_hr.idxmax() if target_total_hr.max() > 0 else 0
                    hr_data = target_logs[target_logs['Hour'] == peak_target_hr]
                    most_threat = target_logs['Threat_Type'].mode()[0] if not target_logs.empty else "-"
                    
                    metrics['tactical'] = {
                        'peak_hr': int(peak_target_hr),
                        'peak_cam': hr_data['จุดติดตั้งกล้อง'].mode()[0] if not hr_data.empty else "-",
                        'main_threat': most_threat,
                        'max_risk_ratio': float((target_total_hr / total_hourly.replace(0, 1) * 100).max())
                    }
                    
                    tactical_table = target_logs.groupby(['Hour', 'จุดติดตั้งกล้อง']).agg(
                        เป้าหมายที่พบ=('ทะเบียน_Full', 'nunique'),
                        ระดับความเสี่ยง=('Risk_Score', 'max')
                    ).reset_index().sort_values(by=['Hour', 'เป้าหมายที่พบ'], ascending=[True, False]).head(8)
                    metrics['tactical_table'] = tactical_table.to_dict('records')
            return metrics

        if not metrics:
            metrics = _compute_fallback_metrics(priority_df, active_db)

        filtered_df = priority_df[priority_df['Risk Score'].astype(str).str.replace('%', '').astype(float) >= 80].copy() if not priority_df.empty else pd.DataFrame()

        # ── ค่า default เพื่อป้องกัน NameError เมื่อ filtered_df ว่าง ────────────
        apex_df      = pd.DataFrame()
        _watch_today = 0
        cat_cloned   = 0
        cat_convoy_car = 0
        cat_others   = 0

        if not filtered_df.empty and metrics:
            
            cat_cloned = len(filtered_df[filtered_df['ประเภท'] == "กลุ่มเป้าหมายสวมทะเบียน"])
            cat_convoy_car = len(filtered_df[filtered_df['ประเภท'] == "กลุ่มรถยนต์เคลื่อนที่แบบขบวน"])
            cat_others = len(filtered_df[filtered_df['ประเภท'] == "กลุ่มรถต้องสงสัย"])
            # คำนวณ apex_df และ _watch_today ก่อน nav_tab check เพื่อให้ทุกหน้าเข้าถึงได้
            apex_df = filtered_df[filtered_df['ประเภท'] == "กลุ่มเป้าหมายความมั่นคงระดับสูงสุด"].copy()
            try:
                _wconn2 = sqlite3.connect(DB_PATH)
                _wl_df2 = pd.read_sql("SELECT plate FROM historical_suspects WHERE seen_count >= 1", _wconn2)
                _today_plates2 = set(active_db['ทะเบียน_Full'].unique()) if not active_db.empty else set()
                _watch_today = len(_wl_df2[_wl_df2['plate'].isin(_today_plates2)]) if not _wl_df2.empty else 0
                _wconn2.close()
            except: _watch_today = 0

            if st.session_state['nav_tab'] == "🏠 สรุปสถานการณ์ (Overview)":
                
                if not apex_df.empty:
                    st.markdown("""
                    <div class='apex-threat-banner'>
                        🚨 กลุ่มเป้าหมายความมั่นคงระดับสูงสุด (Apex Threats) 🚨<br>
                        <span style='font-size:14px; font-weight:normal;'>ตรวจพบเป้าหมายที่มีพฤติกรรมภัยคุกคามซ้อนทับกัน โปรดวิทยุสั่งการสกัดกั้นทันที!</span>
                    </div>
                    """, unsafe_allow_html=True)
                    show_clickable_table(apex_df, "t_apex", active_db, filtered_df)
                    st.markdown("---")

                reports_full_df['date'] = pd.to_datetime(reports_full_df['report_date'])
                _today_d = pd.to_datetime(datetime.now().strftime('%Y-%m-%d'))
                mask_7 = (reports_full_df['date'] <= _today_d) & (reports_full_df['date'] > _today_d - timedelta(days=7))
                mask_30 = (reports_full_df['date'] <= _today_d) & (reports_full_df['date'] > _today_d - timedelta(days=30))
                
                def calc_cum(mask):
                    c_apex, c_clone, c_car, c_other = 0, 0, 0, 0
                    for p_data in reports_full_df[mask]['priority_data']:
                        try:
                            if isinstance(p_data, str):
                                import json
                                p_data = json.loads(p_data)
                            pdf = pd.DataFrame(p_data)
                            if not pdf.empty:
                                fdf = pdf[pdf['Risk Score'].astype(str).str.replace('%', '').astype(float) >= 80]
                                c_apex += len(fdf[fdf['ประเภท'] == "กลุ่มเป้าหมายความมั่นคงระดับสูงสุด"])
                                c_clone += len(fdf[fdf['ประเภท'] == "กลุ่มเป้าหมายสวมทะเบียน"])
                                c_car += len(fdf[fdf['ประเภท'] == "กลุ่มรถยนต์เคลื่อนที่แบบขบวน"])
                                c_other += len(fdf[fdf['ประเภท'] == "กลุ่มรถต้องสงสัย"])
                        except: pass
                    return c_apex, c_clone, c_car, c_other

                cum7_apex, cum7_clone, cum7_car, cum7_other = calc_cum(mask_7)
                cum30_apex, cum30_clone, cum30_car, cum30_other = calc_cum(mask_30)

                st.markdown("### 📊 ข้อมูลสรุปเป้าหมายสำคัญ (Intelligence Brief)")
                _tz_th     = timezone(timedelta(hours=7))  # Bangkok UTC+7
                _today_str = datetime.now(_tz_th).strftime('%Y-%m-%d')  # ★ sync กับเวลาไทยบน Cloud
                _sel_str   = str(selected_date)[:10]

                if _sel_str == _today_str:
                    tab_realtime, tab_daily, tab_repeat = st.tabs([
                        "⚡ Realtime",
                        "📅 ประจำวัน (Daily)",
                        "🔁 รถวิ่งซ้ำ (30 วัน)",
                    ])
                else:
                    tab_daily, = st.tabs([
                        "📅 ประจำวัน (Daily)",
                    ])
                    # Create dummy context managers
                    from contextlib import nullcontext
                    tab_realtime = nullcontext()
                    tab_repeat = nullcontext()

                with tab_realtime:
                    # ── ✅ Realtime = วันปัจจุบันเท่านั้น ─────────────────────

                    if _sel_str != _today_str:
                        pass

                    else:
                        # ── วันนี้ → โหลดจาก realtime_session table ───────────
                        _rt_session = load_realtime_session(_today_str)

                        if _rt_session is None or _rt_session['df'].empty:
                            # แสดง debug error ถ้ามี
                            _load_err = st.session_state.pop('_rt_load_error', None)
                            if _load_err:
                                st.error(f"❌ โหลดข้อมูล Realtime ไม่สำเร็จ:")
                                st.code(_load_err)
                            else:
                                st.markdown(f"""
                            <div style='background:rgba(245,158,11,0.10);border-left:4px solid #f59e0b;
                                padding:24px;border-radius:12px;margin:16px 0;'>
                                <div style='font-size:32px;margin-bottom:12px;'>⏳</div>
                                <div style='font-size:18px;font-weight:700;color:#fbbf24;margin-bottom:8px;'>
                                    ยังไม่มีข้อมูล Realtime วันนี้ ({_today_str})
                                </div>
                                <div style='font-size:14px;color:#94a3b8;line-height:1.8;'>
                                    ระบบพร้อมรอรับข้อมูล — กรุณาให้ Admin อัปโหลดไฟล์ CSV
                                    ผ่าน <b style='color:#a5b4fc;'>Admin Portal</b> เพื่อเริ่มการวิเคราะห์ Realtime<br><br>
                                    ⚡ เมื่ออัปโหลดแล้ว หน้านี้จะแสดงผลวิเคราะห์อัตโนมัติ
                                </div>
                            </div>
                            """, unsafe_allow_html=True)

                        else:
                            # ── มีข้อมูล → render realtime tab ───────────────
                            st.session_state['_rt_upload_count'] = _rt_session.get('upload_count', 1)
                            _rt_today_df = _rt_session['df']
                            try:
                                render_realtime_tab(_today_str, _rt_today_df, priority_df)
                            except Exception as _rte:
                                import traceback
                                st.error(f"❌ Realtime Error: {_rte}")
                                st.code(traceback.format_exc())


                with tab_daily:
                    # Load watch list count
                    try:
                        _wconn = sqlite3.connect(DB_PATH)
                        _wl_df = pd.read_sql("SELECT plate FROM historical_suspects WHERE seen_count >= 1", _wconn)
                        _today_plates = set(active_db['ทะเบียน_Full'].unique()) if not active_db.empty else set()
                        _watch_today = len(_wl_df[_wl_df['plate'].isin(_today_plates)]) if not _wl_df.empty else 0
                        _wconn.close()
                    except: _watch_today = 0

                    import streamlit.components.v1 as _cv1
                    col1, col2, col3, col4, col5 = st.columns(5)
                    with col1:
                        st.markdown(f"<div class='metric-card card-apex'><div class='metric-label'>🚨 ระดับสูงสุด</div><div class='metric-value'>{len(apex_df)}</div></div>", unsafe_allow_html=True)
                    with col2:
                        st.markdown(f"<div class='metric-card card-clone'><div class='metric-label'>🚗 สวมทะเบียน</div><div class='metric-value'>{cat_cloned}</div></div>", unsafe_allow_html=True)
                        if st.button("🔍 เจาะลึก", key="btn_clone_d"): change_tab("🚨 รถสวมทะเบียน"); st.rerun()
                    with col3:
                        st.markdown(f"<div class='metric-card card-car'><div class='metric-label'>🏎️ ขบวนรถยนต์</div><div class='metric-value'>{cat_convoy_car}</div></div>", unsafe_allow_html=True)
                        if st.button("🔍 เจาะลึก", key="btn_car_d"): change_tab("🚘 ขบวนรถลำเลียง"); st.rerun()
                    with col4:
                        st.markdown(f"<div class='metric-card card-anomaly'><div class='metric-label'>🔄 รถต้องสงสัย</div><div class='metric-value'>{cat_others}</div></div>", unsafe_allow_html=True)
                        if st.button("🔍 เจาะลึก", key="btn_anomaly_d"): change_tab("🔄 พฤติกรรมมุดชายแดน"); st.rerun()
                    with col5:
                        st.markdown(f"<div class='metric-card card-watch'><div class='metric-label'>⭐ Watch List วันนี้</div><div class='metric-value'>{_watch_today}</div></div>", unsafe_allow_html=True)
                        if st.button("🔍 เจาะลึก", key="btn_watch_d"): change_tab("⭐ รถที่น่าสนใจ"); st.rerun()
                    # ── JS: resize drill buttons via components.html (executes in iFrame, same origin) ──
                    _cv1.html("""<script>
(function go(){
  try{
    var doc=window.parent.document;
    var all=doc.querySelectorAll('[data-testid="baseButton-secondary"]');
    var found=0;
    all.forEach(function(b){
      if((b.innerText||b.textContent).indexOf('เจาะลึก')>=0){
        found++;
        b.style.cssText=[
          'width:fit-content','padding:5px 20px','font-size:12px',
          'border-radius:20px','display:block','margin:4px auto 0',
          'background:linear-gradient(135deg,rgba(255,255,255,.1),rgba(255,255,255,.04))',
          'border:1px solid rgba(255,255,255,.2)','box-shadow:none',
          'letter-spacing:.3px','cursor:pointer'
        ].join('!important;')+'!important';
        var wrap=b.closest('[data-testid="stButton"]');
        if(wrap) wrap.style.cssText='display:flex;justify-content:center;';
      }
    });
    if(found<4) setTimeout(go,300);
  }catch(e){setTimeout(go,400);}
})();
</script>""",height=0)
                        

                with tab_repeat:
                    if _sel_str != _today_str:
                        st.empty()
                    else:
                        _rep = repeat_offender_analysis(reports_full_df, selected_date, window_days=30, min_days=2)

                        if _rep.empty:
                            st.info("⚠️ ยังไม่พบทะเบียนที่ปรากฏซ้ำ ≥ 2 วัน ในช่วง 30 วันที่ผ่านมา — ต้องมีข้อมูลอย่างน้อย 2 วันในระบบ")
                        else:
                            # ── Summary cards ──────────────────────────────────────
                            _r_clone  = _rep[_rep['ประเภทหลัก'].str.contains("สวมทะเบียน", na=False)]
                            _r_convoy = _rep[_rep['ประเภทหลัก'].str.contains("ขบวน", na=False)]
                            _r_susp   = _rep[~_rep['ประเภทหลัก'].str.contains("สวมทะเบียน|ขบวน", na=False)]

                            rc1, rc2, rc3 = st.columns(3)
                            with rc1: st.markdown(f"<div class='metric-card card-clone'><div class='metric-label'>🚗 สวมทะเบียนซ้ำ</div><div class='metric-value'>{len(_r_clone)}</div><div style='font-size:11px;color:#94a3b8'>≥2 วัน / 30 วัน</div></div>", unsafe_allow_html=True)
                            with rc2: st.markdown(f"<div class='metric-card card-car'><div class='metric-label'>🏎️ ขบวนรถซ้ำ</div><div class='metric-value'>{len(_r_convoy)}</div><div style='font-size:11px;color:#94a3b8'>≥2 วัน / 30 วัน</div></div>", unsafe_allow_html=True)
                            with rc3: st.markdown(f"<div class='metric-card card-anomaly'><div class='metric-label'>🔍 รถต้องสงสัยซ้ำ</div><div class='metric-value'>{len(_r_susp)}</div><div style='font-size:11px;color:#94a3b8'>≥2 วัน / 30 วัน</div></div>", unsafe_allow_html=True)

                            st.markdown("---")
                            _hist_db = active_db_all if not active_db_all.empty else active_db

                            # ── Helper: province extractor ──────────────────────────
                            def _get_province(plate_str):
                                parts = str(plate_str).strip().split()
                                return parts[-1] if len(parts) >= 2 else '-'

                            def _day_badge(n):
                                if n >= 10: return "🔴"
                                elif n >= 5: return "🟠"
                                elif n >= 3: return "🟡"
                                return "🟢"

                            # ── Helper: show one group as table ────────────────────
                            def _show_repeat_table(group_df, tab_key, icon):
                                if group_df.empty:
                                    st.info("ไม่มีข้อมูลในกลุ่มนี้")
                                    return

                                # โหลด status ทั้งหมดครั้งเดียว
                                try:
                                    _sc = sqlite3.connect(DB_PATH)
                                    _st_df = pd.read_sql(
                                        "SELECT plate, status FROM target_status", _sc)
                                    _sc.close()
                                    _st_map = dict(zip(_st_df['plate'], _st_df['status']))
                                except:
                                    _st_map = {}

                                # หากล้องล่าสุดจาก _hist_db
                                def _last_cam(plate):
                                    if _hist_db.empty: return '-'
                                    sub = _hist_db[_hist_db['ทะเบียน_Full'] == plate]
                                    if sub.empty: return '-'
                                    return sub.sort_values('Datetime').iloc[-1]['จุดติดตั้งกล้อง']

                                tbl = pd.DataFrame({
                                    'สถานะ': group_df['plate'].apply(
                                        lambda p: _st_map.get(p, '🔴 เฝ้าระวังใหม่')),
                                    'ทะเบียน': group_df['plate'],
                                    'จำนวนวันที่พบ': group_df['วันที่พบ'].astype(int),
                                    'วันแรกที่พบ': group_df['ครั้งแรก'],
                                    'วันล่าสุดที่พบ': group_df['ล่าสุด'],
                                    'กล้องล่าสุด': group_df['plate'].apply(_last_cam),
                                    'Risk Score': group_df['คะแนนสูงสุด'].astype(int),
                                })

                                st.caption("คลิกแถวเพื่อดูแผนที่และรายละเอียดด้านล่าง")
                                event = st.dataframe(
                                    tbl, use_container_width=True, hide_index=True,
                                    on_select="rerun", selection_mode="single-row",
                                    key=f"rep_tbl_{tab_key}"
                                )
                                excel_download_button(
                                    tbl, f"repeat_{tab_key}_{selected_date}.xlsx",
                                    "📥 Export ตารางนี้ (Excel)"
                                )

                                if event.selection.rows:
                                    idx   = event.selection.rows[0]
                                    rrow  = group_df.iloc[idx]
                                    freq  = rrow['วันที่พบ']
                                    score = rrow['คะแนนสูงสุด']
                                    st.markdown("---")
                                    st.markdown(
                                        f"#### {icon} รายละเอียด: **{rrow['plate']}** "
                                        f"| พบซ้ำ {freq} วัน | Score {score:.0f}"
                                    )
                                    render_repeat_offender_dossier(
                                        rrow['plate'], _hist_db, rrow['dates_list']
                                    )


                            # ── 3 sub-tabs ──────────────────────────────────────────
                            rt1, rt2, rt3 = st.tabs([
                                f"🚗 สวมทะเบียนซ้ำ ({len(_r_clone)})",
                                f"🏎️ ขบวนรถซ้ำ ({len(_r_convoy)})",
                                f"🔍 ต้องสงสัยซ้ำ ({len(_r_susp)})",
                            ])
                            with rt1:
                                _show_repeat_table(_r_clone.reset_index(drop=True),  "clone",  "🚗")
                            with rt2:
                                _show_repeat_table(_r_convoy.reset_index(drop=True), "convoy", "🏎️")
                            with rt3:
                                _show_repeat_table(_r_susp.reset_index(drop=True),   "susp",   "🔍")




                st.markdown("### 🗺️ แผนที่ประเมินความเสี่ยงทางยุทธวิธี (2D Risk Hotspots & Heatmap)")
                m_agg = folium.Map(location=[15.0, 102.0], zoom_start=6) 
                map_stats = metrics.get('map_stats', [])
                if map_stats:
                    heat_data = [[row['lat'], row['lon'], row['volume']] for row in map_stats]
                    HeatMap(heat_data, radius=25, blur=15, min_opacity=0.4).add_to(m_agg)
                    
                    mc = MarkerCluster().add_to(m_agg)
                    m_agg.location = [map_stats[0]['lat'], map_stats[0]['lon']]
                    for row_stat in map_stats:
                        vol = row_stat['volume']
                        primary = str(row_stat.get('primary_threat', ''))
                        
                        if "สวมทะเบียน" in primary: color = 'orange'
                        elif "ขบวน" in primary: color = 'darkblue'
                        else: color = 'purple'
                        
                        folium.Marker(
                            location=[row_stat['lat'], row_stat['lon']],
                            popup=f"<b>จุดตรวจ:</b> {row_stat.get('จุดติดตั้งกล้อง', '')}<br><b>เป้าหมายผ่าน:</b> {vol} คัน<br><b>ภัยคุกคามหลัก:</b> {primary}",
                            icon=folium.Icon(color=color, icon='info-sign')
                        ).add_to(mc)
                        
                    legend_html = """
                     <div class="map-legend">
                     <b>สัญลักษณ์ภัยคุกคาม:</b><br>
                     &nbsp; <i class="fa fa-map-marker fa-1x" style="color:orange"></i> สวมทะเบียน<br>
                     &nbsp; <i class="fa fa-map-marker fa-1x" style="color:darkblue"></i> ขบวนรถลำเลียง<br>
                     &nbsp; <i class="fa fa-map-marker fa-1x" style="color:purple"></i> รถต้องสงสัย
                     </div>
                     """
                    m_agg.get_root().html.add_child(folium.Element(legend_html))
                        
                components.html(m_agg.get_root().render(), height=450)
                st.markdown("---")

                st.markdown("### 🕒 นาฬิกาประเมินสถานการณ์เชิงยุทธวิธี (Advanced Tactical Crime Clock)")
                clock_data = metrics.get('clock', {})
                tactical_data = metrics.get('tactical', {})
                
                if clock_data:
                    hours = list(range(24))
                    total_max = max(clock_data['total_hourly']) if max(clock_data['total_hourly']) > 0 else 1
                    all_threats = clock_data['apex_hr'] + clock_data['cloned_hr'] + clock_data['convoy_hr'] + clock_data['border_hr']
                    target_max = max(all_threats) if max(all_threats) > 0 else 1
                    
                    norm_total = [(v / total_max) * 100 for v in clock_data['total_hourly']]
                    norm_apex = [(v / target_max) * 100 for v in clock_data['apex_hr']]
                    norm_cloned = [(v / target_max) * 100 for v in clock_data['cloned_hr']]
                    norm_convoy = [(v / target_max) * 100 for v in clock_data['convoy_hr']]
                    norm_border = [(v / target_max) * 100 for v in clock_data['border_hr']]
                    
                    fig_clock = go.Figure()
                    fig_clock.add_trace(go.Scatterpolar(r=norm_total + [norm_total[0]], theta=[f"{i:02d}:00" for i in hours] + ["00:00"], fill='toself', name='ปริมาณการจราจรทั่วไป', line_color='rgba(148, 163, 184, 0.4)', fillcolor='rgba(148, 163, 184, 0.15)'))
                    fig_clock.add_trace(go.Scatterpolar(r=norm_apex + [norm_apex[0]], theta=[f"{i:02d}:00" for i in hours] + ["00:00"], fill='toself', name='กลุ่มเป้าหมายความมั่นคงระดับสูงสุด', line_color='rgba(159, 18, 57, 0.9)', fillcolor='rgba(159, 18, 57, 0.5)'))
                    fig_clock.add_trace(go.Scatterpolar(r=norm_cloned + [norm_cloned[0]], theta=[f"{i:02d}:00" for i in hours] + ["00:00"], fill='toself', name='กลุ่มเป้าหมายสวมทะเบียน', line_color='rgba(234, 88, 12, 0.9)', fillcolor='rgba(234, 88, 12, 0.3)'))
                    fig_clock.add_trace(go.Scatterpolar(r=norm_convoy + [norm_convoy[0]], theta=[f"{i:02d}:00" for i in hours] + ["00:00"], fill='toself', name='กลุ่มโครงข่ายขบวนรถ', line_color='rgba(30, 58, 138, 0.9)', fillcolor='rgba(30, 58, 138, 0.4)'))
                    fig_clock.add_trace(go.Scatterpolar(r=norm_border + [norm_border[0]], theta=[f"{i:02d}:00" for i in hours] + ["00:00"], fill='toself', name='กลุ่มรถต้องสงสัย', line_color='rgba(126, 34, 206, 0.9)', fillcolor='rgba(126, 34, 206, 0.4)'))
                    
                    fig_clock.update_layout(polar=dict(radialaxis=dict(visible=False, range=[0, 100]), angularaxis=dict(direction="clockwise", rotation=90, categoryorder='array', categoryarray=[f"{i:02d}:00" for i in range(24)])), showlegend=True, height=550, margin=dict(t=40, b=40, l=40, r=40), legend=dict(orientation="h", yanchor="bottom", y=-0.2, xanchor="center", x=0.5), paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)")
                    
                    col_c1, col_c2 = st.columns([55, 45])
                    with col_c1: st.plotly_chart(fig_clock, use_container_width=True)
                    with col_c2:
                        st.markdown(f"""
                        <div class='tactical-brief'>
                            <b>🤖 รายงานสรุปการประเมินสถานการณ์ (AI Tactical Brief):</b><br><br>
                            <b>1. มิติเวลา (Temporal):</b> ตรวจพบความหนาแน่นสูงสุดของเป้าหมายหลัก <b>[{tactical_data.get('main_threat', '-')}]</b> ในห้วงเวลา <b>{tactical_data.get('peak_hr', 0):02d}:00 - {tactical_data.get('peak_hr', 0)+1:02d}:00 น.</b><br>
                            <b>2. มิติพื้นที่ (Spatial):</b> จุดบอดและคอขวดที่เฝ้าระวังและสกัดกั้นที่แนะนำคือ บริเวณจุดตรวจ <u>{tactical_data.get('peak_cam', '-')}</u> ซึ่งมีเป้าหมายลัดเลาะผ่านมากที่สุด<br>
                            <b>3. มิติพฤติกรรม (Behavioral):</b> มีสัดส่วนเป้าหมายแฝงตัวเทียบกับปริมาณการจราจรปกติสูงถึง <b>{tactical_data.get('max_risk_ratio', 0):.1f}%</b> (ชี้ให้เห็นความจงใจใช้เส้นทางหลบเลี่ยงในช่วงที่รถพลุกพล่านน้อย)
                        </div>
                        """, unsafe_allow_html=True)
                        st.markdown("**📋 ตารางข้อมูลสถานการณ์: ห้วงเวลา และ จุดติดตั้งกล้อง**")
                        if metrics.get('tactical_table'):
                            st.dataframe(pd.DataFrame(metrics['tactical_table']), use_container_width=True, hide_index=True)

            elif st.session_state['nav_tab'] == "🚨 รถสวมทะเบียน":
                _mb1,_mb2,_mb3,_mb4,_mb5 = st.columns(5)
                with _mb1: st.markdown(f"<div class='metric-card card-apex'><div class='metric-label'>🚨 ระดับสูงสุด</div><div class='metric-value'>{len(apex_df)}</div></div>", unsafe_allow_html=True)
                with _mb2: st.markdown(f"<div class='metric-card card-clone'><div class='metric-label'>🚗 สวมทะเบียน</div><div class='metric-value'>{cat_cloned}</div></div>", unsafe_allow_html=True)
                with _mb3: st.markdown(f"<div class='metric-card card-car'><div class='metric-label'>🏎️ ขบวนรถยนต์</div><div class='metric-value'>{cat_convoy_car}</div></div>", unsafe_allow_html=True)
                with _mb4: st.markdown(f"<div class='metric-card card-anomaly'><div class='metric-label'>🔄 ต้องสงสัย</div><div class='metric-value'>{cat_others}</div></div>", unsafe_allow_html=True)
                with _mb5: st.markdown(f"<div class='metric-card card-watch'><div class='metric-label'>⭐ Watch List</div><div class='metric-value'>{_watch_today}</div></div>", unsafe_allow_html=True)
                st.markdown("<div class='risk-orange'>🚨 รายงานเจาะลึก: กลุ่มเป้าหมายสวมทะเบียน (อัตราเร็วเหนือขีดจำกัดทางกายภาพ)</div><br>", unsafe_allow_html=True)
                show_clickable_table(filtered_df[filtered_df['ประเภท'] == "กลุ่มเป้าหมายสวมทะเบียน"], "t_cloned", active_db, filtered_df)

            elif st.session_state['nav_tab'] == "🚘 ขบวนรถลำเลียง":
                _mb1,_mb2,_mb3,_mb4,_mb5 = st.columns(5)
                with _mb1: st.markdown(f"<div class='metric-card card-apex'><div class='metric-label'>🚨 ระดับสูงสุด</div><div class='metric-value'>{len(apex_df)}</div></div>", unsafe_allow_html=True)
                with _mb2: st.markdown(f"<div class='metric-card card-clone'><div class='metric-label'>🚗 สวมทะเบียน</div><div class='metric-value'>{cat_cloned}</div></div>", unsafe_allow_html=True)
                with _mb3: st.markdown(f"<div class='metric-card card-car'><div class='metric-label'>🏎️ ขบวนรถยนต์</div><div class='metric-value'>{cat_convoy_car}</div></div>", unsafe_allow_html=True)
                with _mb4: st.markdown(f"<div class='metric-card card-anomaly'><div class='metric-label'>🔄 ต้องสงสัย</div><div class='metric-value'>{cat_others}</div></div>", unsafe_allow_html=True)
                with _mb5: st.markdown(f"<div class='metric-card card-watch'><div class='metric-label'>⭐ Watch List</div><div class='metric-value'>{_watch_today}</div></div>", unsafe_allow_html=True)
                st.markdown("<div class='risk-blue'>🏎️ รายงานเจาะลึก: โครงข่ายขบวนรถลำเลียง (พฤติกรรมวิ่งนำ-ตามทางไกล)</div><br>", unsafe_allow_html=True)
                show_clickable_table(filtered_df[filtered_df['ประเภท'] == "กลุ่มรถยนต์เคลื่อนที่แบบขบวน"], "t_convoy_car", active_db, filtered_df)

            elif st.session_state['nav_tab'] == "🔄 พฤติกรรมมุดชายแดน":
                _mb1,_mb2,_mb3,_mb4,_mb5 = st.columns(5)
                with _mb1: st.markdown(f"<div class='metric-card card-apex'><div class='metric-label'>🚨 ระดับสูงสุด</div><div class='metric-value'>{len(apex_df)}</div></div>", unsafe_allow_html=True)
                with _mb2: st.markdown(f"<div class='metric-card card-clone'><div class='metric-label'>🚗 สวมทะเบียน</div><div class='metric-value'>{cat_cloned}</div></div>", unsafe_allow_html=True)
                with _mb3: st.markdown(f"<div class='metric-card card-car'><div class='metric-label'>🏎️ ขบวนรถยนต์</div><div class='metric-value'>{cat_convoy_car}</div></div>", unsafe_allow_html=True)
                with _mb4: st.markdown(f"<div class='metric-card card-anomaly'><div class='metric-label'>🔄 ต้องสงสัย</div><div class='metric-value'>{cat_others}</div></div>", unsafe_allow_html=True)
                with _mb5: st.markdown(f"<div class='metric-card card-watch'><div class='metric-label'>⭐ Watch List</div><div class='metric-value'>{_watch_today}</div></div>", unsafe_allow_html=True)
                st.markdown("<div class='risk-purple'>🔄 รายงานเจาะลึก: กลุ่มรถต้องสงสัย (วนลูป / แช่ตัว / มุดช่องโหว่)</div><br>", unsafe_allow_html=True)
                show_clickable_table(filtered_df[filtered_df['ประเภท'] == "กลุ่มรถต้องสงสัย"], "t_others", active_db, filtered_df)

            elif st.session_state['nav_tab'] == "⭐ รถที่น่าสนใจ":
                show_watch_list(active_db, selected_date)

        else:
            # filtered_df ว่าง — แต่ถ้าวันนี้ ให้ลองแสดง Realtime tab ก่อน
            from datetime import timezone as _tz_mod
            _tz_th_fb = _tz_mod(timedelta(hours=7))
            _today_str_fb = datetime.now(_tz_th_fb).strftime('%Y-%m-%d')
            _sel_str_fb   = str(selected_date)[:10]

            if (_sel_str_fb == _today_str_fb and
                    st.session_state.get('nav_tab', '') == "🏠 สรุปสถานการณ์ (Overview)"):
                # ลองดึง Realtime session (เคลียร์ cache ก่อนเพื่อให้ได้ข้อมูลล่าสุด)
                load_realtime_session.clear()
                _rt_fb = load_realtime_session(_today_str_fb)
                if _rt_fb and not _rt_fb['df'].empty:
                    st.info("📊 ข้อมูล Realtime พร้อมแล้ว — รอผลการประมวลผล (score ≥ 80%) อาจใช้เวลาสักครู่")
                    try:
                        render_realtime_tab(_today_str_fb, _rt_fb['df'], priority_df)
                    except Exception as _rte_fb:
                        st.error(f"❌ Realtime Error: {_rte_fb}")
                else:
                    _load_err_fb = st.session_state.pop('_rt_load_error', None)
                    if _load_err_fb:
                        st.error("❌ โหลด Realtime ไม่สำเร็จ:")
                        st.code(_load_err_fb)
                    else:
                        st.success("🟢 ไม่พบข้อมูลเป้าหมายเฝ้าระวัง (>80%) และยังไม่มี Realtime Session วันนี้")
            else:
                st.success("🟢 ไม่พบข้อมูลเป้าหมายเฝ้าระวังความเสี่ยงสูง (>80%) ในวันที่เลือก")