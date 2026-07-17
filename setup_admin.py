"""
setup_admin.py — สร้าง Admin Users ครั้งแรก (ไม่ใช้ Streamlit)
"""
import sys, os, hashlib, secrets as _sec

# อ่าน secrets.toml โดยตรง
try:
    import toml
except ImportError:
    print("กรุณา: pip install toml")
    sys.exit(1)

secrets_path = os.path.join(os.path.dirname(__file__), '.streamlit', 'secrets.toml')
with open(secrets_path, 'r', encoding='utf-8') as f:
    _secrets = toml.load(f)

SUPABASE_URL = _secrets['supabase']['url']
SUPABASE_KEY = _secrets['supabase']['key']

from supabase import create_client

def hash_password(password: str) -> str:
    salt = _sec.token_hex(16)
    hashed = hashlib.pbkdf2_hmac('sha256', password.encode(), salt.encode(), 200_000).hex()
    return f"{salt}:{hashed}"

def create_user(client, username, password, role, display_name):
    try:
        client.table('users').insert({
            'username':      username.lower().strip(),
            'password_hash': hash_password(password),
            'role':          role,
            'display_name':  display_name,
            'is_active':     True
        }).execute()
        print(f"  ✅ {username:<15} [{role}]  — {display_name}")
    except Exception as e:
        if '23505' in str(e) or 'duplicate' in str(e).lower():
            print(f"  ⚠️  {username:<15} มีอยู่แล้ว (ข้ามไป)")
        else:
            print(f"  ❌ {username}: {e}")

# ─── รายชื่อ Users ตั้งต้น ─────────────────────────────────────
# แก้ไขชื่อ/รหัสผ่านก่อนรัน ถ้าต้องการ
DEFAULT_USERS = [
    # (username,      password,         role,          display_name          )
    ("superadmin",  "HWPD60@2569!",   "super_admin", "ผู้ดูแลระบบหลัก"      ),
    ("admin01",     "Admin01@2569",   "admin",       "แอดมิน กะเช้า"        ),
    ("admin02",     "Admin02@2569",   "admin",       "แอดมิน กะบ่าย"        ),
    ("admin03",     "Admin03@2569",   "admin",       "แอดมิน กะดึก"         ),
    ("viewer01",    "View01@2569",    "viewer",      "เจ้าหน้าที่ดูผล ชุด 1"),
]

print("=" * 55)
print("  HWPD i-Trap — สร้าง Admin Users")
print("=" * 55)
print(f"  Supabase: {SUPABASE_URL}\n")

client = create_client(SUPABASE_URL, SUPABASE_KEY)

print("กำลังสร้าง Users...")
for u, p, r, d in DEFAULT_USERS:
    create_user(client, u, p, r, d)

print("\n" + "=" * 55)
print("  Username / Password เริ่มต้น:")
print("  ┌─────────────────────────────────────────────┐")
print("  │ superadmin  /  HWPD60@2569!   [Super Admin] │")
print("  │ admin01     /  Admin01@2569   [Admin]        │")
print("  │ admin02     /  Admin02@2569   [Admin]        │")
print("  │ admin03     /  Admin03@2569   [Admin]        │")
print("  │ viewer01    /  View01@2569    [Viewer]        │")
print("  └─────────────────────────────────────────────┘")
print("  ⚠️  กรุณาเปลี่ยนรหัสผ่านหลังเข้าระบบครั้งแรก!")
print("=" * 55)
