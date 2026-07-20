"""
supabase_sync.py — Sync ผลลัพธ์ระหว่าง Local ↔ Supabase Cloud
"""
import streamlit as st
import pandas as pd
import json
from datetime import datetime
from typing import Optional

# ─── Connection ───────────────────────────────────────────────────────────────
@st.cache_resource(show_spinner=False)
def get_supabase_client():
    """สร้าง Supabase client (cached — สร้างครั้งเดียว)"""
    from supabase import create_client
    url = st.secrets["supabase"]["url"]
    key = st.secrets["supabase"]["key"]
    return create_client(url, key)

def is_supabase_configured() -> bool:
    """ตรวจว่า Supabase ตั้งค่าไว้ไหม"""
    try:
        return bool(st.secrets.get("supabase", {}).get("url"))
    except Exception:
        return False

# ─── PUSH Functions (Local → Supabase) ────────────────────────────────────────
def push_daily_report(report_date: str, priority_df: pd.DataFrame,
                       metrics: dict, uploaded_by: str, record_count: int = 0) -> bool:
    """Push ผลวิเคราะห์รายวันขึ้น Supabase"""
    if not is_supabase_configured():
        return False
    try:
        client = get_supabase_client()
        priority_json = priority_df.to_dict('records') if not priority_df.empty else []
        client.table('cloud_daily_reports').upsert({
            'report_date':       report_date,
            'priority_data':     priority_json,
            'dashboard_metrics': metrics,
            'uploaded_by':       uploaded_by,
            'record_count':      record_count,
            'created_at':        datetime.now().isoformat()
        }).execute()
        return True
    except Exception as e:
        st.session_state['_sync_error'] = str(e)
        return False

def push_realtime_session(session_date: str, priority_df: pd.DataFrame,
                           upload_count: int, first_time: str, last_time: str,
                           uploaded_by: str, record_count: int = 0) -> bool:
    """Push ผล Realtime ขึ้น Supabase"""
    if not is_supabase_configured():
        return False
    try:
        client = get_supabase_client()
        priority_json = priority_df.to_dict('records') if not priority_df.empty else []
        client.table('cloud_realtime').upsert({
            'session_date':      session_date,
            'priority_json':     priority_json,
            'upload_count':      upload_count,
            'first_record_time': first_time,
            'last_record_time':  last_time,
            'record_count':      record_count,
            'uploaded_by':       uploaded_by,
            'updated_at':        datetime.now().isoformat()
        }).execute()
        return True
    except Exception as e:
        st.session_state['_sync_error'] = str(e)
        return False

def push_suspects(suspects_df: pd.DataFrame) -> bool:
    """Push รถวิ่งซ้ำ (Repeat Offenders) ขึ้น Supabase
    BUG-03 FIX: รวม cloud_suspects → historical_suspects เพื่อกัน duplicate
    """
    if not is_supabase_configured() or suspects_df.empty:
        return False
    try:
        client = get_supabase_client()
        records = []
        for _, row in suspects_df.iterrows():
            records.append({
                'plate':          str(row.get('plate', row.get('ทะเบียน', ''))),
                'threat_type':    str(row.get('threat_type', row.get('ประเภทหลัก', ''))),
                'max_risk_score': int(row.get('max_risk_score', row.get('คะแนนสูงสุด', 0))),
                'last_seen_date': str(row.get('last_seen_date', row.get('ล่าสุด', ''))),
                'seen_count':     int(row.get('seen_count', row.get('วันที่พบ', 1))),
                'updated_at':     datetime.now().isoformat()
            })
        for i in range(0, len(records), 100):
            client.table('historical_suspects').upsert(
                records[i:i+100], on_conflict='plate'
            ).execute()
        return True
    except Exception as e:
        st.session_state['_sync_error'] = str(e)
        return False

def log_upload(username: str, display_name: str, filename: str,
               report_date: str, record_count: int) -> bool:
    """บันทึกประวัติการ Upload"""
    if not is_supabase_configured():
        return False
    try:
        client = get_supabase_client()
        client.table('upload_log').insert({
            'username':     username,
            'display_name': display_name,
            'filename':     filename,
            'report_date':  report_date,
            'record_count': record_count,
            'uploaded_at':  datetime.now().isoformat()
        }).execute()
        return True
    except Exception:
        return False

def push_parquet_to_cloud(report_date: str, df_polars, keep_days: int = 30) -> bool:
    """บีบอัด DataFrame แล้วอัปโหลดขึ้น Supabase Storage (itrap-parquet bucket)
    + ลบไฟล์เก่า > keep_days วัน อัตโนมัติ เพื่อป้องกัน Storage เต็ม
    (default 30 วัน = สอดคล้องกับ Repeat Offender window 30 วัน)
    """
    if not is_supabase_configured():
        return False
    try:
        import io
        from datetime import timedelta
        client = get_supabase_client()

        # ── Upload ไฟล์ใหม่ ──────────────────────────────────────────────
        buf = io.BytesIO()
        df_polars.write_parquet(buf, compression='zstd', compression_level=3)
        buf.seek(0)
        parquet_bytes = buf.read()
        path = f"{report_date}/merged.parquet"
        client.storage.from_("itrap-parquet").upload(
            path, parquet_bytes,
            file_options={"content-type": "application/octet-stream", "upsert": "true"}
        )

        # ── BUG-01 FIX: ลบไฟล์เก่า > keep_days วัน ──────────────────────
        try:
            cutoff_date = (datetime.strptime(report_date, '%Y-%m-%d')
                           - timedelta(days=keep_days)).strftime('%Y-%m-%d')
            file_list = client.storage.from_("itrap-parquet").list()
            old_paths = [
                f"{f['name']}/merged.parquet"
                for f in (file_list or [])
                if isinstance(f.get('name'), str) and f['name'] < cutoff_date
            ]
            if old_paths:
                client.storage.from_("itrap-parquet").remove(old_paths)
        except Exception:
            pass  # cleanup failure ไม่กระทบ upload หลัก

        return True
    except Exception as e:
        st.session_state['_sync_error'] = f"push_parquet: {str(e)[:80]}"
        return False

def pull_parquet_from_cloud(report_date: str):
    """ดาวน์โหลด parquet จาก Supabase Storage → Polars DataFrame"""
    if not is_supabase_configured():
        return None
    try:
        import io, polars as pl
        client = get_supabase_client()
        path = f"{report_date}/merged.parquet"
        data = client.storage.from_("itrap-parquet").download(path)
        if not data:
            return None
        return pl.read_parquet(io.BytesIO(data))
    except Exception:
        return None


# ─── Whitelist (ระบบกลาง — ทุก Admin ใช้ร่วมกัน) ────────────────────────────
def pull_whitelist() -> set:
    """ดึง whitelist จาก Supabase → คืนเป็น set ของทะเบียน"""
    if not is_supabase_configured():
        return set()
    try:
        client = get_supabase_client()
        result = client.table('whitelist_master').select('plate').execute()
        return set(r['plate'] for r in (result.data or []))
    except Exception:
        return set()

def pull_whitelist_df() -> pd.DataFrame:
    """ดึง whitelist ทั้งหมดเป็น DataFrame (สำหรับแสดงผลใน UI)"""
    if not is_supabase_configured():
        return pd.DataFrame(columns=['plate', 'note', 'added_by', 'added_at'])
    try:
        client = get_supabase_client()
        result = client.table('whitelist_master').select('*').order('added_at', desc=True).execute()
        return pd.DataFrame(result.data or [])
    except Exception:
        return pd.DataFrame(columns=['plate', 'note', 'added_by', 'added_at'])

def push_whitelist_plate(plate: str, note: str = '', added_by: str = 'admin') -> bool:
    """เพิ่มทะเบียนเข้า whitelist ใน Supabase"""
    if not is_supabase_configured():
        return False
    try:
        client = get_supabase_client()
        client.table('whitelist_master').upsert({
            'plate':    plate.strip().upper(),
            'note':     note,
            'added_by': added_by,
            'added_at': datetime.now().isoformat()
        }).execute()
        return True
    except Exception as e:
        st.session_state['_sync_error'] = f"whitelist_add: {str(e)[:80]}"
        return False

def delete_whitelist_plate(plate: str) -> bool:
    """ลบทะเบียนออกจาก whitelist ใน Supabase"""
    if not is_supabase_configured():
        return False
    try:
        client = get_supabase_client()
        client.table('whitelist_master').delete().eq('plate', plate).execute()
        return True
    except Exception:
        return False


# ─── Historical Suspects (ระบบกลาง — สะสมจากทุก Admin) ──────────────────────
def push_historical_suspects(hs_df: pd.DataFrame) -> bool:
    """Upsert historical_suspects ขึ้น Supabase (merge กับข้อมูลที่มีอยู่)"""
    if not is_supabase_configured() or hs_df.empty:
        return False
    try:
        client = get_supabase_client()
        records = []
        for _, row in hs_df.iterrows():
            records.append({
                'plate':          str(row.get('plate', '')),
                'threat_type':    str(row.get('threat_type', '')),
                'max_risk_score': int(row.get('max_risk_score', 0)),
                'last_seen_date': str(row.get('last_seen_date', '')),
                'seen_count':     int(row.get('seen_count', 1)),
                'updated_at':     datetime.now().isoformat()
            })
        for i in range(0, len(records), 100):
            client.table('historical_suspects').upsert(
                records[i:i+100], on_conflict='plate'
            ).execute()
        return True
    except Exception as e:
        st.session_state['_sync_error'] = f"suspects_push: {str(e)[:80]}"
        return False

def pull_historical_suspects(limit: int = 500) -> pd.DataFrame:
    """ดึง historical_suspects จาก Supabase"""
    if not is_supabase_configured():
        return pd.DataFrame()
    try:
        client = get_supabase_client()
        result = (client.table('historical_suspects')
                  .select('*')
                  .order('max_risk_score', desc=True)
                  .limit(limit)
                  .execute())
        return pd.DataFrame(result.data or [])
    except Exception:
        return pd.DataFrame()


# ─── Target Status (ระบบกลาง — ผบ./Admin อัปเดตได้ทุกที่) ───────────────────
def push_target_status(target_id: str, status: str, updated_by: str = 'admin') -> bool:
    """อัปเดตสถานะเป้าหมายใน Supabase"""
    if not is_supabase_configured():
        return False
    try:
        client = get_supabase_client()
        client.table('target_status').upsert({
            'target_id':   target_id,
            'status':      status,
            'updated_by':  updated_by,
            'last_update': datetime.now().isoformat()
        }).execute()
        return True
    except Exception as e:
        st.session_state['_sync_error'] = f"status_push: {str(e)[:80]}"
        return False

def pull_target_status(target_id: str) -> str:
    """ดึงสถานะของ target_id เดียว"""
    if not is_supabase_configured():
        return '🔴 เฝ้าระวังใหม่'
    try:
        client = get_supabase_client()
        result = (client.table('target_status')
                  .select('status')
                  .eq('target_id', target_id)
                  .execute())
        if result.data:
            return result.data[0]['status']
        return '🔴 เฝ้าระวังใหม่'
    except Exception:
        return '🔴 เฝ้าระวังใหม่'

def pull_target_status_df() -> pd.DataFrame:
    """ดึง target_status ทั้งหมดเป็น DataFrame"""
    if not is_supabase_configured():
        return pd.DataFrame(columns=['target_id', 'status'])
    try:
        client = get_supabase_client()
        result = client.table('target_status').select('target_id,status').execute()
        return pd.DataFrame(result.data or [])
    except Exception:
        return pd.DataFrame(columns=['target_id', 'status'])


# ─── PULL Functions (Supabase → Display) ──────────────────────────────────────
@st.cache_data(ttl=120, show_spinner=False)
def pull_available_dates() -> list:
    """ดึงรายการวันที่มีรายงาน"""
    # BUG-02 FIX: guard ก่อน crash ถ้าไม่มี Supabase secret
    if not is_supabase_configured():
        return []
    try:
        client = get_supabase_client()
        result = client.table('cloud_daily_reports').select('report_date').order('report_date', desc=True).execute()
        return [r['report_date'] for r in (result.data or [])]
    except Exception:
        return []

@st.cache_data(ttl=60, show_spinner=False)
def pull_daily_report(report_date: str) -> dict:
    """ดึงผลวิเคราะห์รายวัน"""
    try:
        client = get_supabase_client()
        result = client.table('cloud_daily_reports').select('*').eq('report_date', report_date).execute()
        if result.data:
            row = result.data[0]
            priority_df = pd.DataFrame(row.get('priority_data') or [])
            metrics = row.get('dashboard_metrics') or {}
            return {'priority_df': priority_df, 'metrics': metrics,
                    'uploaded_by': row.get('uploaded_by'), 'record_count': row.get('record_count', 0)}
    except Exception:
        pass
    return {'priority_df': pd.DataFrame(), 'metrics': {}, 'uploaded_by': None, 'record_count': 0}

@st.cache_data(ttl=30, show_spinner=False)
def pull_realtime(session_date: str) -> Optional[dict]:
    """ดึงผล Realtime"""
    try:
        client = get_supabase_client()
        result = client.table('cloud_realtime').select('*').eq('session_date', session_date).execute()
        if result.data:
            row = result.data[0]
            priority_df = pd.DataFrame(row.get('priority_json') or [])
            return {
                'priority_df':  priority_df,
                'upload_count': row.get('upload_count', 1),
                'first_time':   row.get('first_record_time'),
                'last_time':    row.get('last_record_time'),
                'record_count': row.get('record_count', 0),
                'uploaded_by':  row.get('uploaded_by'),
                'updated_at':   row.get('updated_at'),
            }
    except Exception:
        pass
    return None

@st.cache_data(ttl=300, show_spinner=False)
def pull_suspects(limit: int = 200) -> pd.DataFrame:
    """ดึงรถวิ่งซ้ำ"""
    try:
        client = get_supabase_client()
        result = client.table('cloud_suspects').select('*').order('seen_count', desc=True).limit(limit).execute()
        return pd.DataFrame(result.data or [])
    except Exception:
        return pd.DataFrame()

@st.cache_data(ttl=60, show_spinner=False)
def pull_upload_log(limit: int = 50) -> pd.DataFrame:
    """ดึงประวัติการ Upload"""
    try:
        client = get_supabase_client()
        result = client.table('upload_log').select('*').order('uploaded_at', desc=True).limit(limit).execute()
        return pd.DataFrame(result.data or [])
    except Exception:
        return pd.DataFrame()

# ─── Sync Status ──────────────────────────────────────────────────────────────
def show_sync_status():
    """แสดง sync status ใน sidebar"""
    if not is_supabase_configured():
        st.sidebar.caption("⚠️ Supabase: ไม่ได้ตั้งค่า (Local Only)")
        return
    err = st.session_state.pop('_sync_error', None)
    if err:
        st.sidebar.error(f"☁️ Sync Error: {err[:80]}")
    else:
        st.sidebar.caption("☁️ Cloud Sync: พร้อม")
