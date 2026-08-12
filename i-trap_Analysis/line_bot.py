# -*- coding: utf-8 -*-
"""
line_bot.py — HWPD i-Trap LINE Messaging API Bot (v2)
=====================================================
- ค้นหาทะเบียน + จังหวัด (fuzzy match 77 จังหวัด)
- ตอบ Flex Message 3 สถานะ: ไม่พบ / พบรถเดี่ยว / พบขบวน
- ดึงข้อมูลจาก PostgreSQL watchlist โดยตรง
"""
import os, re, json, logging
from datetime import datetime
from difflib import get_close_matches
import psycopg2
from fastapi import FastAPI, Request, HTTPException
from fastapi.responses import JSONResponse

try:
    from linebot.v3 import WebhookHandler
    from linebot.v3.messaging import (
        ApiClient, Configuration, MessagingApi,
        ReplyMessageRequest, FlexMessage, FlexContainer, TextMessage,
    )
    from linebot.v3.webhooks import MessageEvent, TextMessageContent
    from linebot.v3.exceptions import InvalidSignatureError
    _LINE_SDK_OK = True
except ImportError:
    _LINE_SDK_OK = False

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger("itrap-linebot")

# ── Config ────────────────────────────────────────────────────────────────────
CHANNEL_ACCESS_TOKEN = os.environ.get("LINE_CHANNEL_ACCESS_TOKEN", "")
CHANNEL_SECRET       = os.environ.get("LINE_CHANNEL_SECRET", "")
ITRAP_HOST           = os.environ.get("ITRAP_HOST", "129.150.56.185")

_PG_CFG = {
    "host": "127.0.0.1", "port": 5432,
    "dbname": "itrap_db", "user": "itrap_admin",
    "password": "Hwpd@iTrap2026!Secure", "connect_timeout": 3,
}

app = FastAPI(title="HWPD i-Trap LINE Bot")

line_cfg = None
handler  = None
if _LINE_SDK_OK and CHANNEL_ACCESS_TOKEN and CHANNEL_SECRET:
    line_cfg = Configuration(access_token=CHANNEL_ACCESS_TOKEN)
    handler  = WebhookHandler(CHANNEL_SECRET)

# ── Province Fuzzy Map (77 จังหวัด) ─────────────────────────────────────────
_PROV_MAP = {
    # กรุงเทพ
    "กทม":"กรุงเทพมหานคร","กรุงเทพ":"กรุงเทพมหานคร","กรุงเทพมหานคร":"กรุงเทพมหานคร","bkk":"กรุงเทพมหานคร",
    # ภาคกลาง
    "นนท์":"นนทบุรี","นนทบุรี":"นนทบุรี",
    "ปทุม":"ปทุมธานี","ปทุมธานี":"ปทุมธานี",
    "อยุธยา":"พระนครศรีอยุธยา","พระนครศรีอยุธยา":"พระนครศรีอยุธยา",
    "สระบุรี":"สระบุรี","อ่างทอง":"อ่างทอง","สิงห์บุรี":"สิงห์บุรี",
    "ลพบุรี":"ลพบุรี","ชัยนาท":"ชัยนาท","อุทัยธานี":"อุทัยธานี",
    "นครสวรรค์":"นครสวรรค์","กำแพงเพชร":"กำแพงเพชร",
    "สมุทรปราการ":"สมุทรปราการ","สมปก":"สมุทรปราการ",
    "สมุทรสาคร":"สมุทรสาคร","สมุทรสงคราม":"สมุทรสงคราม",
    "ราชบุรี":"ราชบุรี","กาญจนบุรี":"กาญจนบุรี","กาญจน์":"กาญจนบุรี",
    "สุพรรณบุรี":"สุพรรณบุรี","สุพรรณ":"สุพรรณบุรี",
    "นครปฐม":"นครปฐม","เพชรบุรี":"เพชรบุรี","เพชร":"เพชรบุรี",
    "ประจวบ":"ประจวบคีรีขันธ์","ประจวบคีรีขันธ์":"ประจวบคีรีขันธ์",
    # ภาคเหนือ
    "เชียงใหม่":"เชียงใหม่","เชียงใหม":"เชียงใหม่","chiangmai":"เชียงใหม่",
    "เชียงราย":"เชียงราย","chiangrai":"เชียงราย",
    "ลำปาง":"ลำปาง","ลำพูน":"ลำพูน",
    "แม่ฮ่องสอน":"แม่ฮ่องสอน","แมฮองสอน":"แม่ฮ่องสอน",
    "น่าน":"น่าน","พะเยา":"พะเยา","แพร่":"แพร่",
    "ตาก":"ตาก","สุโขทัย":"สุโขทัย",
    "อุตรดิตถ์":"อุตรดิตถ์","อุตรดิต":"อุตรดิตถ์",
    "พิษณุโลก":"พิษณุโลก","พิษณุ":"พิษณุโลก",
    "พิจิตร":"พิจิตร","เพชรบูรณ์":"เพชรบูรณ์","เพชรบูรณ":"เพชรบูรณ์",
    # ภาคอีสาน
    "โคราช":"นครราชสีมา","นครราชสีมา":"นครราชสีมา","โคราท":"นครราชสีมา",
    "ขอนแก่น":"ขอนแก่น","ขก":"ขอนแก่น",
    "อุบล":"อุบลราชธานี","อุบลราชธานี":"อุบลราชธานี","อุบลฯ":"อุบลราชธานี",
    "อุดร":"อุดรธานี","อุดรธานี":"อุดรธานี","อุดรฯ":"อุดรธานี",
    "สกลนคร":"สกลนคร","สกล":"สกลนคร",
    "นครพนม":"นครพนม","มุกดาหาร":"มุกดาหาร",
    "ร้อยเอ็ด":"ร้อยเอ็ด","กาฬสินธุ์":"กาฬสินธุ์","กาฬสินธุ":"กาฬสินธุ์",
    "มหาสารคาม":"มหาสารคาม","บึงกาฬ":"บึงกาฬ",
    "หนองคาย":"หนองคาย","หนองบัวลำภู":"หนองบัวลำภู",
    "เลย":"เลย","ชัยภูมิ":"ชัยภูมิ",
    "สุรินทร์":"สุรินทร์","บุรีรัมย์":"บุรีรัมย์","บุรีรัมย":"บุรีรัมย์","บุรีรัมย์":"บุรีรัมย์",
    "ศรีสะเกษ":"ศรีสะเกษ","ยโสธร":"ยโสธร","อำนาจเจริญ":"อำนาจเจริญ",
    # ภาคตะวันออก
    "ชล":"ชลบุรี","ชลบุรี":"ชลบุรี","พัทยา":"ชลบุรี",
    "ระยอง":"ระยอง","จันทบุรี":"จันทบุรี","จันทบุรี":"จันทบุรี",
    "ตราด":"ตราด","ฉะเชิงเทรา":"ฉะเชิงเทรา","ฉะเชิงเทรา":"ฉะเชิงเทรา",
    "ปราจีนบุรี":"ปราจีนบุรี","สระแก้ว":"สระแก้ว","นครนายก":"นครนายก",
    # ภาคใต้
    "สุราษฎร์":"สุราษฎร์ธานี","สุราษฎร์ธานี":"สุราษฎร์ธานี","สุราษฎร":"สุราษฎร์ธานี",
    "นครศรีธรรมราช":"นครศรีธรรมราช","นครศรี":"นครศรีธรรมราช","นครศรีฯ":"นครศรีธรรมราช",
    "ภูเก็ต":"ภูเก็ต","ภูเก็ท":"ภูเก็ต","phuket":"ภูเก็ต",
    "กระบี่":"กระบี่","พังงา":"พังงา","ตรัง":"ตรัง",
    "สตูล":"สตูล","พัทลุง":"พัทลุง",
    "สงขลา":"สงขลา","หาดใหญ่":"สงขลา",
    "ปัตตานี":"ปัตตานี","ยะลา":"ยะลา","นราธิวาส":"นราธิวาส","นรา":"นราธิวาส",
    "ระนอง":"ระนอง","ชุมพร":"ชุมพร",
}
_PROV_FULL_LIST = list(set(_PROV_MAP.values()))

def resolve_province(text: str) -> str | None:
    """แปลงชื่อจังหวัดย่อ/ผิดพลาด → ชื่อเต็ม"""
    t = text.strip()
    if t in _PROV_MAP:
        return _PROV_MAP[t]
    # fuzzy fallback
    close = get_close_matches(t, list(_PROV_MAP.keys()) + _PROV_FULL_LIST, n=1, cutoff=0.6)
    if close:
        return _PROV_MAP.get(close[0], close[0])
    return None

# ── Plate Parsing ─────────────────────────────────────────────────────────────
_PLATE_RE = re.compile(
    r"([ก-ฮ]{1,3})\s*(\d{1,4})"
    r"|(\d{1,4})\s*([ก-ฮ]{1,3})"        # เลขก่อน
    r"|([ก-ฮ]{1,4}\s*\d{1,4}[ก-ฮ]{0,2})"  # ป้ายพิเศษ
)

def parse_message(text: str) -> tuple[str | None, str | None]:
    """คืน (plate_normalized, province_full) จากข้อความ"""
    text = text.strip()
    # หาทะเบียน
    m = _PLATE_RE.search(text)
    if not m:
        return None, None
    plate_raw = m.group(0)
    plate_norm = re.sub(r"\s+", " ", plate_raw).strip()

    # หาจังหวัด — ตัดส่วนทะเบียนออกแล้วหาคำที่เหลือ
    remaining = text[m.end():].strip() + " " + text[:m.start()].strip()
    remaining = remaining.strip()
    prov = resolve_province(remaining) if remaining else None

    return plate_norm, prov

def is_plate_query(text: str) -> bool:
    return bool(_PLATE_RE.search(text.strip()))

# ── PostgreSQL Watchlist Query ────────────────────────────────────────────────
def query_watchlist(plate: str, province: str | None = None) -> dict | None:
    """ค้นหาทะเบียนใน watchlist; คืน dict หรือ None ถ้าไม่พบ"""
    try:
        conn = psycopg2.connect(**_PG_CFG)
        cur  = conn.cursor()

        # normalize plate for search (remove spaces)
        plate_q = re.sub(r"\s+", "", plate)

        q = """
            SELECT plate, province, seen_count, last_checkpoint,
                   last_seen_time, behavior_type, risk_score,
                   reason, verdict, convoy_members, convoy_role,
                   lat, lon
            FROM watchlist
            WHERE is_active = TRUE
              AND REPLACE(plate, ' ', '') ILIKE %s
        """
        params = [f"%{plate_q}%"]

        if province:
            q += " AND (province ILIKE %s OR province IS NULL)"
            params.append(f"%{province}%")

        q += " ORDER BY added_at DESC LIMIT 1"
        cur.execute(q, params)
        row = cur.fetchone()
        conn.close()

        if not row:
            return None

        cols = ["plate","province","seen_count","last_checkpoint",
                "last_seen_time","behavior_type","risk_score",
                "reason","verdict","convoy_members","convoy_role","lat","lon"]
        return dict(zip(cols, row))
    except Exception as e:
        log.error(f"query_watchlist error: {e}")
        return None

# ── Flex Message Builder ──────────────────────────────────────────────────────
def _txt(text, size="sm", color="#e2e8f0", weight="regular", wrap=False, margin="xs"):
    return {"type":"text","text":str(text),"size":size,"color":color,
            "weight":weight,"wrap":wrap,"margin":margin}

def _row(label, value, value_color="#e2e8f0"):
    return {
        "type":"box","layout":"horizontal","margin":"xs",
        "contents":[
            {"type":"text","text":label,"size":"xs","color":"#94a3b8","flex":3},
            {"type":"text","text":str(value),"size":"sm","color":value_color,
             "flex":5,"wrap":True,"weight":"bold"},
        ]
    }

def _risk_color(score: int) -> str:
    if score >= 80: return "#ef4444"
    if score >= 50: return "#f59e0b"
    return "#10b981"

def _risk_label(score: int) -> str:
    if score >= 80: return "สูงมาก 🔴"
    if score >= 50: return "ปานกลาง 🟡"
    return "ต่ำ 🟢"

def _behavior_emoji(btype: str) -> str:
    t = (btype or "").lower()
    if "ghost" in t: return "👻 Ghost Plate"
    if "convoy" in t: return "🚛 Convoy"
    if "border" in t or "u-turn" in t: return "🔄 Border U-Turn"
    if "night" in t: return "🌙 Night Ghost"
    return f"⚠️ {btype}" if btype else "⚠️ ไม่ระบุ"

def build_flex_not_found(plate: str) -> dict:
    """Flex: ไม่พบในระบบ (ไม่มีปุ่ม)"""
    return {
        "type":"bubble","size":"kilo",
        "header":{
            "type":"box","layout":"vertical","backgroundColor":"#0f172a","paddingAll":"14px",
            "contents":[
                _txt("🔍 HWPD i-Trap Intelligence","xs","#94a3b8","bold"),
                _txt(plate,"xl","#f1f5f9","bold"),
            ]
        },
        "body":{
            "type":"box","layout":"vertical","backgroundColor":"#1e293b",
            "paddingAll":"16px","spacing":"sm",
            "contents":[
                _txt("❌ ไม่มีข้อมูลในระบบ","md","#94a3b8","regular",True,"md"),
                _txt("ทะเบียนนี้ไม่พบใน Watchlist","xs","#64748b"),
            ]
        },
    }

def build_flex_found(data: dict, plate_input: str) -> dict:
    """Flex: พบใน Watchlist (รถเดี่ยว หรือ ขบวน)"""
    plate    = data["plate"]
    score    = data["risk_score"] or 0
    rc       = _risk_color(score)
    rl       = _risk_label(score)
    is_conv  = data["convoy_role"] in ("lead","follow")
    members  = data["convoy_members"] or []
    if isinstance(members, str):
        try: members = json.loads(members)
        except: members = []

    detail_url = f"http://{ITRAP_HOST}:8501/?plate={plate}&src=line"

    # Body rows
    rows = []
    rows.append({"type":"separator","margin":"sm"})

    if data["province"]:
        rows.append(_row("📍 จังหวัด", data["province"]))
    rows.append(_row("🎯 ประเภท", _behavior_emoji(data["behavior_type"])))
    if data["seen_count"]:
        rows.append(_row("📸 พบ", f"{data['seen_count']:,} ครั้ง"))
    if data["last_checkpoint"]:
        t = data["last_seen_time"] or ""
        rows.append(_row("📌 จุดล่าสุด", f"{data['last_checkpoint']} {t}".strip()))

    rows.append({"type":"separator","margin":"sm"})
    rows.append(_row("⚠️ Risk Score", f"{score}/100  {rl}", rc))

    # Convoy members
    if is_conv and members:
        rows.append({"type":"separator","margin":"sm"})
        role_label = "นำขบวน 🚛" if data["convoy_role"] == "lead" else "ตามขบวน 🚗"
        rows.append(_txt(f"รถในขบวน ({role_label})","xs","#94a3b8","bold",False,"sm"))
        for m in members[:5]:
            rows.append(_txt(f"  • {m}","xs","#cbd5e1"))

    rows.append({"type":"separator","margin":"sm"})
    rows.append({
        "type":"button","style":"primary","color":"#1d4ed8","height":"sm","margin":"sm",
        "action":{"type":"uri","label":"🗺️ ดูข้อมูล + แผนที่","uri":detail_url}
    })

    return {
        "type":"bubble","size":"kilo",
        "header":{
            "type":"box","layout":"vertical","backgroundColor":"#7f1d1d","paddingAll":"14px",
            "contents":[
                _txt("🚨 HWPD i-Trap Intelligence","xs","#fca5a5","bold"),
                _txt(plate,"xl","#ffffff","bold"),
                _txt("✅ พบใน Watchlist","sm","#fca5a5"),
            ]
        },
        "body":{
            "type":"box","layout":"vertical","backgroundColor":"#1e293b",
            "paddingAll":"14px","spacing":"xs","contents":rows,
        },
    }

# ── Webhook ───────────────────────────────────────────────────────────────────
@app.post("/webhook")
async def webhook(request: Request):
    if not _LINE_SDK_OK or not handler:
        raise HTTPException(status_code=503, detail="LINE SDK not configured")
    sig  = request.headers.get("X-Line-Signature","")
    body = (await request.body()).decode("utf-8")
    try:
        handler.handle(body, sig)
    except InvalidSignatureError:
        raise HTTPException(status_code=400, detail="Invalid signature")
    except Exception as e:
        log.error(f"handler error: {e}")
    return JSONResponse(content={"status":"ok"})

@app.get("/health")
async def health():
    return {"status":"ok","line_configured":bool(CHANNEL_ACCESS_TOKEN and CHANNEL_SECRET),
            "ts":datetime.now().isoformat()}

# ── Event Handler ─────────────────────────────────────────────────────────────
if _LINE_SDK_OK and handler:
    @handler.add(MessageEvent, message=TextMessageContent)
    def on_message(event: MessageEvent):
        text = event.message.text.strip()
        if not is_plate_query(text):
            return

        plate, province = parse_message(text)
        if not plate:
            return

        log.info(f"Lookup: plate={plate!r} province={province!r}")

        try:
            data = query_watchlist(plate, province)
            if data:
                flex_j = build_flex_found(data, plate)
            else:
                flex_j = build_flex_not_found(plate)

            with ApiClient(line_cfg) as ac:
                MessagingApi(ac).reply_message(ReplyMessageRequest(
                    reply_token=event.reply_token,
                    messages=[FlexMessage(
                        alt_text=f"ผลค้นหาทะเบียน {plate}",
                        contents=FlexContainer.from_dict(flex_j),
                    )]
                ))
        except Exception as e:
            log.error(f"reply error: {e}")
            try:
                with ApiClient(line_cfg) as ac:
                    MessagingApi(ac).reply_message(ReplyMessageRequest(
                        reply_token=event.reply_token,
                        messages=[TextMessage(text=f"❌ ระบบขัดข้อง กรุณาลองใหม่")]
                    ))
            except Exception:
                pass

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("line_bot:app", host="0.0.0.0", port=int(os.environ.get("LINE_BOT_PORT",8080)), workers=1)
