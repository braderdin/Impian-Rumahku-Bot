#!/usr/bin/env python3
"""
Shopee Telegram Audit & Safety Gatekeeper Engine
Impian Rumahku Ecosystem (Step 4 & Audit Module)
Features:
- Reads environmental keys (IRCM_TELEGRAM_BOT_TOKEN & IRCM_TELEGRAM_CHAT_ID)
- Sends Telegram Photo Summary Card (Product Details + 4-Platform Status)
- Sends AI Copywriting Audit Blockquote Message (FB, Threads, IG, Bluesky)
- Safety Gatekeeper: Verifies if at least ONE (1) social media dispatch succeeded
- Supports UTF-8 / HTML formatting with safe chunking (>4000 chars)
"""

import os
import sys
import html
import requests
from io import BytesIO
from pathlib import Path
from typing import Any, Dict, Optional, Tuple
from dotenv import load_dotenv

# Setup Project Root Path
PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

# Load Environment Variables (.env.local priority)
env_local = PROJECT_ROOT / ".env.local"
if env_local.exists():
    load_dotenv(dotenv_path=env_local)
else:
    load_dotenv()


def get_telegram_config() -> Tuple[Optional[str], Optional[str], str]:
    """
    Membaca tetapan sambungan Telegram Bot daripada persekitaran.
    """
    token = (
        os.getenv("IRCM_TELEGRAM_BOT_TOKEN", "").strip()
        or os.getenv("TELEGRAM_BOT_TOKEN", "").strip()
    )
    chat_id = (
        os.getenv("IRCM_TELEGRAM_CHAT_ID", "").strip()
        or os.getenv("TELEGRAM_CHAT_ID", "").strip()
    )

    if not token or not chat_id:
        return None, None, "Kunci IRCM_TELEGRAM_BOT_TOKEN atau IRCM_TELEGRAM_CHAT_ID tidak lengkap."

    return token, chat_id, ""


def send_telegram_message(
    text: str,
    token: Optional[str] = None,
    chat_id: Optional[str] = None,
    parse_mode: str = "HTML"
) -> Tuple[bool, Any]:
    """
    Menghantar mesej teks ke Telegram dengan format HTML.
    Memotong teks secara automatik jika melebihi had 4096 aksara Telegram.
    """
    if not token or not chat_id:
        t_token, t_chat, err = get_telegram_config()
        if err:
            return False, err
        token, chat_id = t_token, t_chat

    url = f"https://api.telegram.org/bot{token}/sendMessage"
    max_chunk = 4000
    text_chunks = [text[i:i + max_chunk] for i in range(0, len(text), max_chunk)]
    last_res = None

    for chunk in text_chunks:
        payload = {
            "chat_id": chat_id,
            "text": chunk,
            "parse_mode": parse_mode,
            "disable_web_page_preview": True,
        }
        try:
            res = requests.post(url, json=payload, timeout=20)
            last_res = res.json()
            if res.status_code != 200 or not last_res.get("ok"):
                return False, f"HTTP {res.status_code}: {res.text}"
        except Exception as e:
            return False, f"Ralat rangkaian Telegram: {str(e)}"

    return True, last_res


def send_telegram_photo(
    image_source: str,
    caption: str = "",
    token: Optional[str] = None,
    chat_id: Optional[str] = None,
    parse_mode: str = "HTML"
) -> Tuple[bool, Any]:
    """
    Menghantar gambar fizikal atau URL bersama kapsyen ringkas (< 1024 aksara) ke Telegram.
    """
    if not token or not chat_id:
        t_token, t_chat, err = get_telegram_config()
        if err:
            return False, err
        token, chat_id = t_token, t_chat

    url = f"https://api.telegram.org/bot{token}/sendPhoto"
    safe_caption = caption[:1020] if caption else ""

    # 1. Semak sama ada imej adalah fail tempatan
    if image_source and os.path.exists(image_source):
        try:
            with open(image_source, "rb") as img_file:
                files = {"photo": (os.path.basename(image_source), img_file, "image/jpeg")}
                data = {
                    "chat_id": chat_id,
                    "caption": safe_caption,
                    "parse_mode": parse_mode,
                }
                res = requests.post(url, data=data, files=files, timeout=30)
                res_json = res.json()
                if res.status_code == 200 and res_json.get("ok"):
                    return True, res_json
                return False, f"HTTP {res.status_code}: {res.text}"
        except Exception as e:
            print(f"⚠️ [TELEGRAM PHOTO WARN] Gagal hantar fail fizikal: {e}")

    # 2. Muat turun binary jika URL awam
    img_bytes = None
    if image_source and image_source.startswith("http"):
        try:
            headers = {"User-Agent": "Mozilla/5.0"}
            res_dl = requests.get(image_source, headers=headers, timeout=15)
            if res_dl.status_code == 200 and len(res_dl.content) > 100:
                img_bytes = BytesIO(res_dl.content)
                img_bytes.name = "product.jpg"
        except Exception as e:
            print(f"⚠️ [TELEGRAM PHOTO WARN] Gagal muat turun gambar URL: {e}")

    # 3. Hantar binary buffer atau URL terus
    try:
        if img_bytes:
            files = {"photo": ("product.jpg", img_bytes.getvalue(), "image/jpeg")}
            data = {
                "chat_id": chat_id,
                "caption": safe_caption,
                "parse_mode": parse_mode,
            }
            res = requests.post(url, data=data, files=files, timeout=30)
        else:
            payload = {
                "chat_id": chat_id,
                "photo": image_source,
                "caption": safe_caption,
                "parse_mode": parse_mode,
            }
            res = requests.post(url, json=payload, timeout=20)

        res_json = res.json()
        if res.status_code == 200 and res_json.get("ok"):
            return True, res_json
        return False, f"HTTP {res.status_code}: {res.text}"
    except Exception as e:
        return False, f"Ralat rangkaian Telegram: {str(e)}"


def has_successful_post(payload: Dict[str, Any]) -> bool:
    """
    Pintu Keselamatan (Gatekeeper):
    Menyemak sama ada sekurang-kurangnya SATU (1) platform berjaya membuat hantaran.
    """
    post_results = payload.get("post_results", {})
    for platform, res in post_results.items():
        if isinstance(res, dict) and res.get("status") == "success":
            return True
    return False


def format_platform_status(res: Dict[str, Any]) -> str:
    """
    Membina status visual ringkas bagi setiap saluran media sosial.
    """
    if not isinstance(res, dict):
        return "⚪ <i>Belum diproses</i>"

    status = res.get("status", "").lower()
    post_id = (
        res.get("post_id")
        or res.get("thread_id")
        or res.get("media_id")
        or res.get("uri")
    )
    post_url = res.get("post_url") or res.get("permalink") or ""
    error_msg = res.get("error", "Ralat tidak diketahui")

    if status == "success":
        link_str = f' (<a href="{post_url}">Pautan</a>)' if post_url else ""
        id_str = f" | ID: <code>{html.escape(str(post_id)[:24])}</code>" if post_id else ""
        return f"✅ <b>BERJAYA</b>{id_str}{link_str}"
    elif status == "failed":
        return f"❌ <b>GAGAL</b> (<code>{html.escape(str(error_msg)[:60])}</code>)"
    else:
        return "⚪ <i>Dilangkau</i>"


def send_shopee_audit_report(payload: Dict[str, Any]) -> Tuple[bool, str]:
    """
    Menghantar laporan lengkap aliran kerja Shopee ke saluran Telegram Audit:
    1. Kad Ringkasan Foto Produk + Butiran Harga Terkunci + Status 4 Platform.
    2. Mesej Audit Teks Kapsyen AI bagi setiap platform.
    """
    token, chat_id, err = get_telegram_config()
    if err:
        return False, err

    prod_id = html.escape(str(payload.get("shopee_product_id") or payload.get("product_id") or "N/A"))
    prod_name = html.escape(str(payload.get("shopee_product_name") or payload.get("product_name") or "Produk Shopee"))
    brand = html.escape(str(payload.get("shopee_brand") or payload.get("brand") or "Impian Rumahku"))
    price = payload.get("shopee_price") or payload.get("price") or 0.0
    aff_link = payload.get("shopee_affiliate_link") or payload.get("affiliate_link") or ""
    pic_source = payload.get("local_image_path") or payload.get("shopee_picture_url") or payload.get("picture_url") or ""
    
    post_results = payload.get("post_results", {})
    ai_captions = payload.get("ai_captions", {})

    price_val = float(price) if str(price).replace('.', '', 1).isdigit() else 0.0

    # 1. BINA KAD RINGKASAN STATUS
    summary_card = (
        f"🛍️ <b>[AUDIT] IMPIAN RUMAHKU & CERITA MAMA</b>\n"
        f"━━━━━━━━━━━━━━━━━━━━\n"
        f"📦 <b>Produk:</b> {prod_name[:65]}...\n"
        f"🆔 <b>ID Produk:</b> <code>{prod_id}</code>\n"
        f"🏷️ <b>Jenama:</b> {brand}\n"
        f"💰 <b>Harga Terkunci:</b> RM {price_val:.2f}\n"
        f"🔗 <b>Pautan:</b> <a href=\"{aff_link}\">Buka di Shopee</a>\n\n"
        f"🚀 <b>STATUS MEDIA SOSIAL:</b>\n"
        f"• <b>Facebook:</b> {format_platform_status(post_results.get('facebook', {}))}\n"
        f"• <b>Bluesky:</b> {format_platform_status(post_results.get('bluesky', {}))}\n"
        f"• <b>Threads:</b> {format_platform_status(post_results.get('threads', {}))}\n"
        f"• <b>Instagram:</b> {format_platform_status(post_results.get('instagram', {}))}\n"
        f"━━━━━━━━━━━━━━━━━━━━"
    )

    # Hantar kad foto ke Telegram
    photo_ok, photo_err = send_telegram_photo(pic_source, caption=summary_card, token=token, chat_id=chat_id)
    if not photo_ok:
        send_telegram_message(summary_card, token=token, chat_id=chat_id)

    # 2. BINA MESEJ AUDIT TEKS AI (JIKA ADA TEKS DISERTAKAN)
    if ai_captions:
        fb_cap = html.escape(ai_captions.get("facebook", "Tiada teks FB"))
        bs_cap = html.escape(ai_captions.get("bluesky", "Tiada teks Bluesky"))
        th_cap = html.escape(ai_captions.get("threads", "Tiada teks Threads"))
        ig_cap = html.escape(ai_captions.get("instagram", "Tiada teks Instagram"))

        captions_audit_msg = (
            f"📝 <b>AUDIT JANAAN AYAT PERSONA MAMA (ID: <code>{prod_id}</code>)</b>\n\n"
            f"🔵 <b>Facebook Page:</b>\n<blockquote>{fb_cap}</blockquote>\n\n"
            f"🦋 <b>Bluesky Feed:</b>\n<blockquote>{bs_cap}</blockquote>\n\n"
            f"🧵 <b>Meta Threads:</b>\n<blockquote>{th_cap}</blockquote>\n\n"
            f"📸 <b>Instagram Feed:</b>\n<blockquote>{ig_cap}</blockquote>"
        )
        send_telegram_message(captions_audit_msg, token=token, chat_id=chat_id)

    # Semakan Pintu Keselamatan
    if has_successful_post(payload):
        print("📢 [TELEGRAM AUDIT SUCCESS] Laporan audit berjaya dihantar ke Telegram.")
        return True, "Laporan audit berjaya dihantar."
    else:
        print("⚠️ [TELEGRAM AUDIT WARN] Semua platform gagal pos. Sila semak pautan & token.")
        return False, "Semua platform media sosial gagal disiarkan."


if __name__ == "__main__":
    print("=" * 70)
    print("🧪 [TEST RUN] Menguji Modul Telegram Audit Impian Rumahku...")
    print("=" * 70)

    # Data ujian dummy
    sample_audit_payload = {
        "shopee_product_id": "17063022271",
        "shopee_product_name": "Strong Roller sticker Sticky Lint Roller Dust Hair Removal Reusable Dust Roller",
        "shopee_brand": "UGGSS Automotive Mall",
        "shopee_price": 1.59,
        "shopee_affiliate_link": "https://s.shopee.com.my/40fx3EQQvT",
        "local_image_path": str(PROJECT_ROOT / "temp" / "shopee_17063022271.jpg"),
        "shopee_picture_url": "https://down-my.img.susercontent.com/file/7f1db6afc8e5000c05ebc9380cc06181",
        "post_results": {
            "facebook": {"status": "success", "post_id": "122099934285450068"},
            "bluesky": {"status": "success", "uri": "at://did:plc:nrwxc2ntoi3fmj3ihzbgroge/app.bsky.feed.post/3mtrepjzvur2v"},
            "threads": {"status": "success", "thread_id": "17956706985000503"},
            "instagram": {"status": "success", "media_id": "18120846748681453"},
        },
        "ai_captions": {
            "facebook": "Tengok roller warna pink ni terus teringat habuk dengan bulu kucing yang melekat...",
            "bluesky": "Perekat kuat ini memudahkan membersihkan rambut, debu dari sofa dan karpet.",
            "threads": "Mama suka betul dengan Strong Roller sticker Sticky ni, warna pink cerahnya menarik...",
            "instagram": "Mama suka betul dengan roller ni, warna merah jambu cerah tu menarik dan senang simpan di laci...",
        }
    }

    ok, msg = send_shopee_audit_report(sample_audit_payload)
    print(f"Hasil Ujian Audit: {ok} | Mesej: {msg}")
    print("=" * 70)