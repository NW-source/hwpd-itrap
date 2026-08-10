"""
auth.py — ระบบ Login, Role Management และ IP Brute-Force Protection สำหรับ HWPD i-Trap
"""
import hashlib
import secrets
import streamlit as st
from datetime import datetime, timezone, timedelta
from typing import Optional

# ─── Constants ────────────────────────────────────────────────────────────────
MAX_ATTEMPTS   = 10          # จำนวนครั้งสูงสุดก่อน block
BLOCK_HOURS    = 24          # ระยะเวลา block (ชั่วโมง)

# ─── Password Hashing ─────────────────────────────────────────────────────────
def hash_password(password: str) -> str:
    salt = secrets.token_hex(16)
    hashed = hashlib.pbkdf2_hmac(
        'sha256', password.encode('utf-8'), salt.encode('utf-8'), 200_000
    ).hex()
    return f"{salt}:{hashed}"

def verify_password(password: str, stored_hash: str) -> bool:
    try:
        salt, hashed = stored_hash.split(':', 1)
        check = hashlib.pbkdf2_hmac(
            'sha256', password.encode('utf-8'), salt.encode('utf-8'), 200_000
        ).hex()
        return secrets.compare_digest(check, hashed)
    except Exception:
        return False

# ─── IP Detection ─────────────────────────────────────────────────────────────
def get_client_ip() -> str:
    """ดึง IP จริงของ Client จาก Streamlit headers (Streamlit Cloud ผ่าน proxy)"""
    try:
        headers = st.context.headers
        # X-Forwarded-For: client, proxy1, proxy2 — ใช้ตัวแรก
        xff = headers.get("X-Forwarded-For", "")
        if xff:
            return xff.split(",")[0].strip()
        return headers.get("X-Real-IP", headers.get("Remote-Addr", "unknown"))
    except Exception:
        return "unknown"

# ─── IP Brute-Force Protection (PostgreSQL) ───────────────────────────────────
def check_ip_blocked(ip: str) -> dict:
    """
    ตรวจว่า IP นี้ถูก block อยู่หรือไม่
    Return: {'blocked': bool, 'blocked_until': str, 'attempts': int}
    """
    if ip == "unknown":
        return {'blocked': False, 'blocked_until': None, 'attempts': 0}
    try:
        from db_adapter import check_ip_blocked_pg
        info = check_ip_blocked_pg(ip)
        if info.get('blocked'):
            bu_str = info.get('blocked_until', '')
            if bu_str:
                bu = datetime.fromisoformat(bu_str.replace('Z', '+00:00'))
                now = datetime.now(timezone.utc)
                remaining = bu - now
                hrs  = int(remaining.total_seconds() // 3600)
                mins = int((remaining.total_seconds() % 3600) // 60)
                return {
                    'blocked': True,
                    'blocked_until': bu.astimezone(timezone(timedelta(hours=7))).strftime('%d/%m/%Y %H:%M'),
                    'remaining_hrs': hrs,
                    'remaining_mins': mins,
                    'attempts': info.get('attempts', 0),
                }
        return info
    except Exception:
        return {'blocked': False, 'blocked_until': None, 'attempts': 0}

def record_failed_attempt(ip: str) -> int:
    """
    บันทึกความพยายาม login ผิด — return จำนวนครั้งทั้งหมด
    ถ้าครบ MAX_ATTEMPTS จะ block IP ทันที
    """
    if ip == "unknown":
        return 0
    try:
        from db_adapter import check_ip_blocked_pg, update_ip_attempts_pg
        info = check_ip_blocked_pg(ip)
        new_count = info.get('attempts', 0) + 1
        blocked_until = None
        if new_count >= MAX_ATTEMPTS:
            from datetime import timedelta
            blocked_until = datetime.now(timezone.utc) + timedelta(hours=BLOCK_HOURS)
        update_ip_attempts_pg(ip, new_count, blocked_until)
        return new_count
    except Exception:
        return 0

def clear_ip_attempts(ip: str):
    """เรียกหลัง login สำเร็จ — ล้าง attempt counter"""
    try:
        from db_adapter import update_ip_attempts_pg
        update_ip_attempts_pg(ip, 0, None)
    except Exception:
        pass

# ─── PostgreSQL User Operations ───────────────────────────────────────────────
def get_user(username: str) -> Optional[dict]:
    """ดึงข้อมูล User จาก PostgreSQL"""
    try:
        from db_adapter import get_user_pg
        return get_user_pg(username.strip().lower())
    except Exception as e:
        st.session_state['_auth_error'] = str(e)
        return None

def update_last_login(username: str):
    """อัปเดต last_login — ไม่มีคอลัมน์นี้ใน system_users (ไม่จำเป็น)"""
    pass

def create_user(username: str, password: str, role: str, display_name: str) -> bool:
    """สร้าง User ใหม่ (เฉพาะ super_admin)"""
    try:
        from db_adapter import create_user_pg
        return create_user_pg(username.strip().lower(), hash_password(password), display_name, role)
    except Exception as e:
        st.error(f"❌ สร้าง User ไม่สำเร็จ: {e}")
        return False

def update_user_password(username: str, new_password: str) -> bool:
    try:
        from db_adapter import update_user_password_pg
        return update_user_password_pg(username, hash_password(new_password))
    except Exception:
        return False

def deactivate_user(username: str) -> bool:
    try:
        from db_adapter import deactivate_user_pg
        return deactivate_user_pg(username)
    except Exception:
        return False

def get_all_users() -> list:
    try:
        from db_adapter import get_all_users_pg
        df = get_all_users_pg()
        return df.to_dict('records') if not df.empty else []
    except Exception:
        return []

# ─── Session Management ───────────────────────────────────────────────────────
def get_current_user() -> Optional[dict]:
    return st.session_state.get('current_user', None)

def is_logged_in() -> bool:
    return get_current_user() is not None

def has_role(*roles) -> bool:
    user = get_current_user()
    return user is not None and user.get('role') in roles

def logout():
    st.session_state.pop('current_user', None)
    st.session_state.pop('_auth_error', None)

# ─── Login UI ─────────────────────────────────────────────────────────────────
ROLE_LABEL = {
    'super_admin': '👑 ผู้ดูแลระบบสูงสุด',
    'admin':       '🔧 แอดมิน (Upload ข้อมูล)',
    'viewer':      '👁️ ผู้ดูผล',
}

def render_login_page():
    """แสดงหน้า Login — เรียกก่อน UI หลัก พร้อมระบบ IP Blocking"""
    st.markdown("""
    <style>
    @import url('https://fonts.googleapis.com/css2?family=Sarabun:wght@300;400;500;600;700;800&display=swap');
    html, body, .stApp, [class*="css"] {
        font-family: 'Sarabun', 'TH Sarabun PSK', 'TH Sarabun New', sans-serif !important;
        font-size: 16px !important;
    }
    .login-wrap {
        max-width: 420px; margin: 60px auto 0; padding: 40px 36px;
        background: rgba(15,23,42,0.85); border-radius: 20px;
        border: 1px solid rgba(99,102,241,0.3);
        box-shadow: 0 8px 40px rgba(0,0,0,0.5);
    }
    .login-title { font-size:22px; font-weight:800; color:#93c5fd;
        text-align:center; margin-bottom:4px; }
    .login-sub   { font-size:14px; color:#64748b; text-align:center; margin-bottom:28px; }
    .block-box {
        background: rgba(239,68,68,0.15); border: 1px solid #ef4444;
        border-radius: 12px; padding: 20px; text-align: center; margin-bottom: 16px;
    }
    .block-title { font-size: 18px; font-weight: 700; color: #f87171; margin-bottom: 8px; }
    .block-msg   { font-size: 14px; color: #fca5a5; }
    .warn-box {
        background: rgba(245,158,11,0.15); border: 1px solid #f59e0b;
        border-radius: 8px; padding: 10px 14px; margin-top: 8px;
        font-size: 13px; color: #fbbf24; text-align: center;
    }
    </style>
    """, unsafe_allow_html=True)

    col = st.columns([1, 2, 1])[1]
    with col:
        # Logo
        import os
        logo = os.path.join(os.path.dirname(__file__), 'logo.jpeg')
        if os.path.exists(logo):
            st.image(logo, use_container_width=True)

        st.markdown("<div class='login-title'>🛡️ HWPD i-Trap</div>", unsafe_allow_html=True)
        st.markdown("<div class='login-sub'>Intelligence Command System — กรุณาเข้าสู่ระบบ</div>", unsafe_allow_html=True)

        # ── ตรวจสอบ IP Block ────────────────────────────────────────────────
        client_ip  = get_client_ip()
        ip_status  = check_ip_blocked(client_ip)

        if ip_status['blocked']:
            st.markdown(f"""
            <div class='block-box'>
                <div class='block-title'>🚫 IP ของคุณถูกบล็อก</div>
                <div class='block-msg'>
                    เนื่องจากพยายาม Login ผิดพลาดเกิน {MAX_ATTEMPTS} ครั้ง<br>
                    กรุณารอถึง <b>{ip_status['blocked_until']} น.</b><br>
                    (อีก {ip_status.get('remaining_hrs', 0)} ชม. {ip_status.get('remaining_mins', 0)} นาที)
                </div>
            </div>
            """, unsafe_allow_html=True)
            return  # หยุด — ไม่แสดง form

        # ── แสดงจำนวนครั้งที่เหลือ (ถ้าเคยผิดมาแล้ว) ─────────────────────
        attempts_so_far = ip_status.get('attempts', 0)
        remaining_tries = MAX_ATTEMPTS - attempts_so_far

        with st.form("login_form", clear_on_submit=False):
            username  = st.text_input("👤 ชื่อผู้ใช้ (Username)", placeholder="เช่น admin01")
            password  = st.text_input("🔑 รหัสผ่าน (Password)", type="password")
            submitted = st.form_submit_button("🔓 เข้าสู่ระบบ", use_container_width=True, type="primary")

        # ── แสดง warning เมื่อผิดมาแล้วบางส่วน ─────────────────────────────
        if attempts_so_far > 0:
            st.markdown(
                f"<div class='warn-box'>⚠️ พยายาม Login ผิดไปแล้ว <b>{attempts_so_far}</b> ครั้ง "
                f"— เหลืออีก <b>{remaining_tries}</b> ครั้งก่อนถูกบล็อก 24 ชม.</div>",
                unsafe_allow_html=True
            )

        if submitted:
            if not username or not password:
                st.error("กรุณากรอก Username และ Password")
                return

            with st.spinner("กำลังตรวจสอบ..."):
                user = get_user(username.strip().lower())

            if user and verify_password(password, user['password_hash']):
                # ✅ Login สำเร็จ — ล้าง attempt counter
                clear_ip_attempts(client_ip)
                st.session_state['current_user'] = user
                update_last_login(username.strip().lower())
                role_label = ROLE_LABEL.get(user['role'], user['role'])
                st.success(f"✅ ยินดีต้อนรับ {user.get('display_name', username)} — {role_label}")
                st.rerun()
            else:
                # ❌ Login ผิด — บันทึก attempt
                new_count = record_failed_attempt(client_ip)
                if new_count >= MAX_ATTEMPTS:
                    st.error(f"🚫 คุณพยายาม Login ผิดครบ {MAX_ATTEMPTS} ครั้ง — IP ถูกบล็อก 24 ชั่วโมง")
                    st.rerun()
                else:
                    left = MAX_ATTEMPTS - new_count
                    st.error(f"❌ Username หรือ Password ไม่ถูกต้อง (เหลือ {left} ครั้งก่อนถูกบล็อก)")

        # Debug error
        if '_auth_error' in st.session_state:
            st.caption(f"⚠️ System: {st.session_state.pop('_auth_error')}")

# ─── Role Guard Helpers ───────────────────────────────────────────────────────
def require_login():
    """เรียกที่ต้นไฟล์ — ถ้ายังไม่ login จะแสดงหน้า login แล้วหยุด"""
    if not is_logged_in():
        render_login_page()
        st.stop()

def require_role(*roles):
    """เรียกก่อน section ที่ต้องการสิทธิ์เฉพาะ"""
    if not has_role(*roles):
        st.warning("🚫 ไม่มีสิทธิ์เข้าถึงส่วนนี้")
        st.stop()
