"""
db_adapter.py — PostgreSQL Adapter สำหรับ HWPD i-Trap
เชื่อมต่อ Oracle Cloud PostgreSQL โดยตรง — ไม่พึ่งพาบริการภายนอก
"""

import os
import io
import json
import logging
import psycopg2
import psycopg2.extras
import pandas as pd
import polars as pl
from contextlib import contextmanager
from datetime import datetime
from typing import Optional
import streamlit as st

logger = logging.getLogger(__name__)

# ─── Connection Config ────────────────────────────────────────────────────────
def _get_pg_dsn() -> str:
    """ดึง DSN สำหรับ PostgreSQL จาก secrets หรือ environment"""
    try:
        cfg = st.secrets.get("postgres", {})
        if cfg.get("dsn"):
            return cfg["dsn"]
        return (
            f"host={cfg.get('host','127.0.0.1')} "
            f"port={cfg.get('port',5432)} "
            f"dbname={cfg.get('dbname','itrap_db')} "
            f"user={cfg.get('user','itrap_admin')} "
            f"password={cfg.get('password','Hwpd@iTrap2026!Secure')}"
        )
    except Exception:
        # Fallback: ใช้ local default (สำหรับ run บน Oracle Cloud VM โดยตรง)
        return "host=127.0.0.1 port=5432 dbname=itrap_db user=itrap_admin password=Hwpd@iTrap2026!Secure"

@contextmanager
def _conn():
    """Context manager สำหรับ PostgreSQL connection"""
    con = psycopg2.connect(_get_pg_dsn())
    try:
        yield con
        con.commit()
    except Exception:
        con.rollback()
        raise
    finally:
        con.close()

def is_pg_configured() -> bool:
    """ตรวจว่า PostgreSQL พร้อมใช้งานไหม"""
    try:
        with _conn() as con:
            with con.cursor() as cur:
                cur.execute("SELECT 1")
        return True
    except Exception:
        return False

# ─── Parquet Storage (Local Disk บน Oracle Cloud) ──────────────────────────────
PARQUET_BASE = os.path.join(os.path.dirname(__file__), "data", "parquet_storage")

def _parquet_path(report_date: str) -> str:
    """คืน path ของไฟล์ parquet"""
    os.makedirs(PARQUET_BASE, exist_ok=True)
    return os.path.join(PARQUET_BASE, f"{report_date}.parquet")

def push_parquet_local(report_date: str, df_polars) -> bool:
    """บันทึก Polars DataFrame เป็น Parquet ลงใน Local Disk"""
    try:
        path = _parquet_path(report_date)
        df_polars.write_parquet(path, compression="zstd", compression_level=3)
        return True
    except Exception as e:
        logger.error(f"push_parquet_local: {e}")
        return False

def pull_parquet_local(report_date: str) -> Optional[pl.DataFrame]:
    """โหลด Parquet จาก Local Disk → Polars DataFrame"""
    try:
        path = _parquet_path(report_date)
        if not os.path.exists(path):
            return None
        return pl.read_parquet(path)
    except Exception as e:
        logger.error(f"pull_parquet_local: {e}")
        return None

def list_parquet_dates() -> list:
    """คืนรายการวันที่มีไฟล์ Parquet"""
    try:
        os.makedirs(PARQUET_BASE, exist_ok=True)
        files = sorted(
            [f.replace(".parquet", "") for f in os.listdir(PARQUET_BASE) if f.endswith(".parquet")],
            reverse=True
        )
        return files
    except Exception:
        return []

# ─── cloud_daily_reports ──────────────────────────────────────────────────────
def push_daily_report_pg(report_date: str, priority_df: pd.DataFrame,
                           metrics: dict, uploaded_by: str, record_count: int = 0) -> bool:
    """Upsert รายงานประจำวันเข้า PostgreSQL"""
    try:
        priority_json = priority_df.to_dict("records") if not priority_df.empty else []
        with _conn() as con:
            with con.cursor() as cur:
                cur.execute("""
                    INSERT INTO cloud_daily_reports
                        (report_date, priority_data, dashboard_metrics, uploaded_by, record_count, created_at)
                    VALUES (%s, %s, %s, %s, %s, now())
                    ON CONFLICT (report_date) DO UPDATE SET
                        priority_data      = EXCLUDED.priority_data,
                        dashboard_metrics  = EXCLUDED.dashboard_metrics,
                        uploaded_by        = EXCLUDED.uploaded_by,
                        record_count       = EXCLUDED.record_count,
                        created_at         = now()
                """, (report_date, json.dumps(priority_json, ensure_ascii=False),
                      json.dumps(metrics, ensure_ascii=False), uploaded_by, record_count))
        return True
    except Exception as e:
        logger.error(f"push_daily_report_pg: {e}")
        return False

def pull_available_dates_pg() -> list:
    """ดึงรายการวันที่มีรายงาน"""
    try:
        with _conn() as con:
            with con.cursor() as cur:
                cur.execute("SELECT report_date::text FROM cloud_daily_reports ORDER BY report_date DESC")
                return [r[0] for r in cur.fetchall()]
    except Exception:
        return []

def pull_daily_report_pg(report_date: str) -> tuple:
    """ดึง priority_data และ dashboard_metrics สำหรับวันที่กำหนด
    คืน (priority_json_str, metrics_dict) หรือ (None, None)"""
    try:
        with _conn() as con:
            with con.cursor(cursor_factory=psycopg2.extras.DictCursor) as cur:
                cur.execute("""
                    SELECT priority_data, dashboard_metrics
                    FROM cloud_daily_reports
                    WHERE report_date = %s
                """, (report_date,))
                row = cur.fetchone()
                if row:
                    return json.dumps(row["priority_data"]), row["dashboard_metrics"]
    except Exception as e:
        logger.error(f"pull_daily_report_pg: {e}")
    return None, None

def pull_all_reports_pg() -> pd.DataFrame:
    """ดึงรายงานทั้งหมด (สำหรับหน้า Admin — ไม่รวม priority_data)"""
    try:
        with _conn() as con:
            with con.cursor(cursor_factory=psycopg2.extras.DictCursor) as cur:
                cur.execute("""
                    SELECT report_date::text, uploaded_by, record_count, created_at
                    FROM cloud_daily_reports ORDER BY report_date DESC
                """)
                rows = cur.fetchall()
                return pd.DataFrame([dict(r) for r in rows]) if rows else pd.DataFrame()
    except Exception:
        return pd.DataFrame()

def pull_all_reports_with_priority_pg() -> pd.DataFrame:
    """ดึงรายงานทั้งหมด รวม priority_data (สำหรับ Repeat Offender / cum7 / cum30)"""
    try:
        with _conn() as con:
            with con.cursor(cursor_factory=psycopg2.extras.DictCursor) as cur:
                cur.execute("""
                    SELECT report_date::text, priority_data, dashboard_metrics
                    FROM cloud_daily_reports ORDER BY report_date DESC
                """)
                rows = cur.fetchall()
                if not rows:
                    return pd.DataFrame()
                result = []
                for r in rows:
                    result.append({
                        'report_date': r['report_date'],
                        'priority_data': r['priority_data'],  # JSON list
                        'dashboard_metrics': r['dashboard_metrics'],
                    })
                return pd.DataFrame(result)
    except Exception:
        return pd.DataFrame()

# ─── cloud_realtime ───────────────────────────────────────────────────────────
def push_realtime_pg(session_date: str, priority_df: pd.DataFrame,
                     upload_count: int, first_time: str, last_time: str,
                     uploaded_by: str, record_count: int = 0) -> bool:
    try:
        priority_json = priority_df.to_dict("records") if not priority_df.empty else []
        with _conn() as con:
            with con.cursor() as cur:
                cur.execute("""
                    INSERT INTO cloud_realtime
                        (session_date, priority_json, upload_count, first_record_time,
                         last_record_time, record_count, uploaded_by, updated_at)
                    VALUES (%s, %s, %s, %s, %s, %s, %s, now())
                    ON CONFLICT (session_date) DO UPDATE SET
                        priority_json      = EXCLUDED.priority_json,
                        upload_count       = EXCLUDED.upload_count,
                        first_record_time  = EXCLUDED.first_record_time,
                        last_record_time   = EXCLUDED.last_record_time,
                        record_count       = EXCLUDED.record_count,
                        uploaded_by        = EXCLUDED.uploaded_by,
                        updated_at         = now()
                """, (session_date, json.dumps(priority_json, ensure_ascii=False),
                      upload_count, first_time, last_time, record_count, uploaded_by))
        return True
    except Exception as e:
        logger.error(f"push_realtime_pg: {e}")
        return False

def pull_realtime_pg(session_date: str) -> Optional[dict]:
    try:
        with _conn() as con:
            with con.cursor(cursor_factory=psycopg2.extras.DictCursor) as cur:
                cur.execute("SELECT * FROM cloud_realtime WHERE session_date = %s", (session_date,))
                row = cur.fetchone()
                if row:
                    d = dict(row)
                    return {
                        'priority_df':  pd.DataFrame(d.get('priority_json') or []),
                        'upload_count': d.get('upload_count', 1),
                        'first_time':   d.get('first_record_time'),
                        'last_time':    d.get('last_record_time'),
                        'record_count': d.get('record_count', 0),
                        'uploaded_by':  d.get('uploaded_by'),
                        'updated_at':   str(d.get('updated_at', '')),
                    }
    except Exception as e:
        logger.error(f"pull_realtime_pg: {e}")
    return None

# ─── historical_suspects ──────────────────────────────────────────────────────
def push_historical_suspects_pg(hs_df: pd.DataFrame) -> bool:
    if hs_df.empty:
        return False
    try:
        records = [(
            str(r.get('plate', '')), str(r.get('threat_type', '')),
            int(r.get('max_risk_score', 0)), str(r.get('last_seen_date', '')),
            int(r.get('seen_count', 1))
        ) for _, r in hs_df.iterrows()]
        with _conn() as con:
            with con.cursor() as cur:
                psycopg2.extras.execute_values(cur, """
                    INSERT INTO historical_suspects
                        (plate, threat_type, max_risk_score, last_seen_date, seen_count, updated_at)
                    VALUES %s
                    ON CONFLICT (plate) DO UPDATE SET
                        threat_type    = EXCLUDED.threat_type,
                        max_risk_score = GREATEST(historical_suspects.max_risk_score, EXCLUDED.max_risk_score),
                        last_seen_date = EXCLUDED.last_seen_date,
                        seen_count     = GREATEST(historical_suspects.seen_count, EXCLUDED.seen_count),
                        updated_at     = now()
                """, [(p, t, s, d, c, ) for p, t, s, d, c in records],
                template="(%s,%s,%s,%s,%s,now())")
        return True
    except Exception as e:
        logger.error(f"push_historical_suspects_pg: {e}")
        return False

def pull_historical_suspects_pg(limit: int = 500) -> pd.DataFrame:
    try:
        with _conn() as con:
            with con.cursor(cursor_factory=psycopg2.extras.DictCursor) as cur:
                cur.execute("SELECT * FROM historical_suspects ORDER BY max_risk_score DESC LIMIT %s", (limit,))
                rows = cur.fetchall()
                return pd.DataFrame([dict(r) for r in rows]) if rows else pd.DataFrame()
    except Exception:
        return pd.DataFrame()

# ─── whitelist_master ─────────────────────────────────────────────────────────
def pull_whitelist_pg() -> set:
    try:
        with _conn() as con:
            with con.cursor() as cur:
                cur.execute("SELECT plate FROM whitelist_master")
                return {r[0] for r in cur.fetchall()}
    except Exception:
        return set()

def pull_whitelist_df_pg() -> pd.DataFrame:
    try:
        with _conn() as con:
            with con.cursor(cursor_factory=psycopg2.extras.DictCursor) as cur:
                cur.execute("SELECT * FROM whitelist_master ORDER BY added_at DESC")
                rows = cur.fetchall()
                return pd.DataFrame([dict(r) for r in rows]) if rows else pd.DataFrame(columns=['plate','note','added_by','added_at'])
    except Exception:
        return pd.DataFrame(columns=['plate','note','added_by','added_at'])

def push_whitelist_plate_pg(plate: str, note: str = '', added_by: str = 'admin') -> bool:
    try:
        with _conn() as con:
            with con.cursor() as cur:
                cur.execute("""
                    INSERT INTO whitelist_master (plate, note, added_by, added_at)
                    VALUES (%s, %s, %s, now())
                    ON CONFLICT (plate) DO UPDATE SET note=EXCLUDED.note, added_by=EXCLUDED.added_by, added_at=now()
                """, (plate.strip().upper(), note, added_by))
        return True
    except Exception as e:
        logger.error(f"push_whitelist: {e}")
        return False

def delete_whitelist_plate_pg(plate: str) -> bool:
    try:
        with _conn() as con:
            with con.cursor() as cur:
                cur.execute("DELETE FROM whitelist_master WHERE plate = %s", (plate,))
        return True
    except Exception:
        return False

# ─── upload_log ───────────────────────────────────────────────────────────────
def log_upload_pg(username: str, display_name: str, filename: str,
                   report_date: str, record_count: int) -> bool:
    try:
        with _conn() as con:
            with con.cursor() as cur:
                cur.execute("""
                    INSERT INTO upload_log (username, display_name, filename, report_date, record_count, uploaded_at)
                    VALUES (%s, %s, %s, %s, %s, now())
                """, (username, display_name, filename, report_date, record_count))
        return True
    except Exception:
        return False

def pull_upload_log_pg(limit: int = 50) -> pd.DataFrame:
    try:
        with _conn() as con:
            with con.cursor(cursor_factory=psycopg2.extras.DictCursor) as cur:
                cur.execute("SELECT * FROM upload_log ORDER BY uploaded_at DESC LIMIT %s", (limit,))
                rows = cur.fetchall()
                return pd.DataFrame([dict(r) for r in rows]) if rows else pd.DataFrame()
    except Exception:
        return pd.DataFrame()

# ─── ai_feedback ──────────────────────────────────────────────────────────────
def push_ai_feedback_pg(target_id: str, engine_type: str, report_date: str,
                         is_correct: int, notes: str, user_id: str, user_display: str) -> bool:
    try:
        with _conn() as con:
            with con.cursor() as cur:
                cur.execute("""
                    INSERT INTO ai_feedback
                        (target_id, engine_type, report_date, is_correct, notes, user_id, user_display, feedback_date)
                    VALUES (%s, %s, %s, %s, %s, %s, %s, now())
                """, (target_id, engine_type, report_date, is_correct, notes, user_id, user_display))
        return True
    except Exception as e:
        logger.error(f"push_ai_feedback: {e}")
        return False

def pull_ai_feedback_pg(report_date: str = None) -> pd.DataFrame:
    try:
        with _conn() as con:
            with con.cursor(cursor_factory=psycopg2.extras.DictCursor) as cur:
                if report_date:
                    cur.execute("SELECT * FROM ai_feedback WHERE report_date=%s ORDER BY feedback_date DESC", (report_date,))
                else:
                    cur.execute("SELECT * FROM ai_feedback ORDER BY feedback_date DESC LIMIT 500")
                rows = cur.fetchall()
                return pd.DataFrame([dict(r) for r in rows]) if rows else pd.DataFrame()
    except Exception:
        return pd.DataFrame()

# ─── target_status ────────────────────────────────────────────────────────────
def push_target_status_pg(target_id: str, status: str, updated_by: str = 'admin') -> bool:
    try:
        with _conn() as con:
            with con.cursor() as cur:
                cur.execute("""
                    INSERT INTO target_status (target_id, status, updated_by, last_update)
                    VALUES (%s, %s, %s, now())
                    ON CONFLICT (target_id) DO UPDATE SET status=EXCLUDED.status, updated_by=EXCLUDED.updated_by, last_update=now()
                """, (target_id, status, updated_by))
        return True
    except Exception:
        return False

def pull_target_status_pg(target_id: str) -> str:
    try:
        with _conn() as con:
            with con.cursor() as cur:
                cur.execute("SELECT status FROM target_status WHERE target_id=%s", (target_id,))
                row = cur.fetchone()
                return row[0] if row else '🔴 เฝ้าระวังใหม่'
    except Exception:
        return '🔴 เฝ้าระวังใหม่'

def pull_target_status_df_pg() -> pd.DataFrame:
    try:
        with _conn() as con:
            with con.cursor(cursor_factory=psycopg2.extras.DictCursor) as cur:
                cur.execute("SELECT target_id, status FROM target_status")
                rows = cur.fetchall()
                return pd.DataFrame([dict(r) for r in rows]) if rows else pd.DataFrame(columns=['target_id','status'])
    except Exception:
        return pd.DataFrame(columns=['target_id','status'])

# ─── ip_blocklist ─────────────────────────────────────────────────────────────
def check_ip_blocked_pg(ip: str) -> dict:
    try:
        with _conn() as con:
            with con.cursor(cursor_factory=psycopg2.extras.DictCursor) as cur:
                cur.execute("SELECT * FROM ip_blocklist WHERE ip_address=%s", (ip,))
                row = cur.fetchone()
                if not row:
                    return {'blocked': False, 'blocked_until': None, 'attempts': 0}
                d = dict(row)
                bu = d.get('blocked_until')
                if bu and bu > datetime.now(bu.tzinfo):
                    return {'blocked': True, 'blocked_until': str(bu), 'attempts': d.get('attempts', 0)}
                return {'blocked': False, 'blocked_until': None, 'attempts': d.get('attempts', 0)}
    except Exception:
        return {'blocked': False, 'blocked_until': None, 'attempts': 0}

def update_ip_attempts_pg(ip: str, attempts: int, blocked_until=None) -> bool:
    try:
        with _conn() as con:
            with con.cursor() as cur:
                cur.execute("""
                    INSERT INTO ip_blocklist (ip_address, attempts, blocked_until, last_attempt_at)
                    VALUES (%s, %s, %s, now())
                    ON CONFLICT (ip_address) DO UPDATE SET
                        attempts=%s, blocked_until=%s, last_attempt_at=now()
                """, (ip, attempts, blocked_until, attempts, blocked_until))
        return True
    except Exception:
        return False

# ─── system_users ─────────────────────────────────────────────────────────────
def get_user_pg(username: str) -> Optional[dict]:
    try:
        with _conn() as con:
            with con.cursor(cursor_factory=psycopg2.extras.DictCursor) as cur:
                cur.execute("SELECT * FROM system_users WHERE username=%s AND is_active=TRUE", (username,))
                row = cur.fetchone()
                return dict(row) if row else None
    except Exception:
        return None

def get_all_users_pg() -> pd.DataFrame:
    try:
        with _conn() as con:
            with con.cursor(cursor_factory=psycopg2.extras.DictCursor) as cur:
                cur.execute("SELECT username, display_name, role, is_active, created_at FROM system_users ORDER BY created_at DESC")
                rows = cur.fetchall()
                return pd.DataFrame([dict(r) for r in rows]) if rows else pd.DataFrame()
    except Exception:
        return pd.DataFrame()

def create_user_pg(username: str, password_hash: str, display_name: str, role: str = 'viewer') -> bool:
    try:
        with _conn() as con:
            with con.cursor() as cur:
                cur.execute("""
                    INSERT INTO system_users (username, password_hash, display_name, role, is_active, created_at)
                    VALUES (%s, %s, %s, %s, TRUE, now())
                    ON CONFLICT (username) DO NOTHING
                """, (username, password_hash, display_name, role))
        return True
    except Exception:
        return False

def update_user_password_pg(username: str, new_hash: str) -> bool:
    try:
        with _conn() as con:
            with con.cursor() as cur:
                cur.execute("UPDATE system_users SET password_hash=%s WHERE username=%s", (new_hash, username))
        return True
    except Exception:
        return False

def deactivate_user_pg(username: str) -> bool:
    try:
        with _conn() as con:
            with con.cursor() as cur:
                cur.execute("UPDATE system_users SET is_active=FALSE WHERE username=%s", (username,))
        return True
    except Exception:
        return False

