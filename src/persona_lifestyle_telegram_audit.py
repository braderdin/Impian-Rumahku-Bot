#!/usr/bin/env python3
"""
Persona Lifestyle Mama: Telegram Audit & Safety Gatekeeper Engine
Location: src/persona_lifestyle_telegram_audit.py

Features:
- Reads IRCM_TELEGRAM_BOT_TOKEN and IRCM_TELEGRAM_CHAT_ID dynamically.
- Formats structured HTML summary card (Time, Mood, Niche, AI Engine Used, 4-Platform Status).
- Dispatches audit card with local/Reddit image (if available) or clean text card.
- Sends blockquote audit messages for Facebook, Instagram, Threads, and Bluesky.
- Safety Gatekeeper: Verifies if at least ONE (1) social media dispatch succeeded.
- Zero Hardcoded Keys: Strictly environment-driven.
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
    """Membaca konfigurasi Telegram Bot daripada persekitaran."""
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
    """Menghantar mesej teks HTML dengan pemotongan automatik (maksimum 4000 aksara)."""
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
            return False, f"Ralat Telegram: {str(e)}"

    return True, last_res


def send_telegram_photo(
    image_source: str,
    caption: str = "",
    token: Optional[str] = None,
    chat_id: Optional[str] = None,
    parse_mode: str = "HTML"
) -> Tuple[bool, Any]:
    """Menghantar imej fizikal bersama kapsyen ringkas (< 1024 aksara) ke Telegram."""
    if not token or not chat_id:
        t_token, t_chat, err = get_telegram_config()
        if err:
            return False, err
        token, chat_id = t_token, t_chat

    url = f"https://api.telegram.org/bot{token}/sendPhoto"
    safe_caption = caption[:1020] if caption else ""

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
            print(f"⚠️ [TELEGRAM PHOTO ERROR] {e}")

    # Fallback jika URL awam
    if image_source and image_source.startswith("http"):
        try:
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
        except Exception as e:
            return False, f"Ralat Telegram Photo URL: {e}"

    return False, "Fail imej tidak sah atau gagal dihantar."


def format_platform_status(res: Dict[str, Any]) -> str:
    """Membina status visual ringkas bagi setiap saluran media sosial."""
    if not isinstance(res, dict):
        return "⚪ <i>Belum diproses</i>"

    status = res.get("status", "").lower()
    post_id = res.get("post_id") or res.get("thread_id") or res.get("media_id") or res.get("uri")
    error_msg = res.get("error", "Ralat tidak diketahui")

    if status == "success":
        id_str = f" | ID: <code>{html.escape(str(post_id)[:20])}</code>" if post_id else ""
        return f"✅ <b>BERJAYA</b>{id_str}"
    elif status == "skipped":
        reason = res.get("reason", "Dilangkau")
        return f"⚪ <i>Dilangkau ({reason})</i>"
    elif status == "failed":
        return f"❌ <b>GAGAL</b> (<code>{html.escape(str(error_msg)[:50])}</code>)"
    else:
        return "⚪ <i>Pending</i>"


def has_successful_lifestyle_post(payload: Dict[str, Any]) -> bool:
    """Pintu Keselamatan: Semak sekurang-kurangnya SATU (1) platform berjaya."""
    post_results = payload.get("post_results", {})
    for platform, res in post_results.items():
        if isinstance(res, dict) and res.get("status") == "success":
            return True
    return False


def send_lifestyle_telegram_audit_report(payload: Dict[str, Any]) -> Tuple[bool, str]:
    """Menghantar laporan penuh audit hantaran gaya hidup ke Telegram."""
    token, chat_id, err = get_telegram_config()
    if err:
        return False, err

    dt = payload.get("datetime", {})
    mood = payload.get("mood", {})
    niche = payload.get("niche", {})
    engine_used = payload.get("engine_used", "AI Engine")
    total_time = payload.get("total_duration_sec", 0.0)
    post_results = payload.get("post_results", {})
    ai_captions = payload.get("ai_captions", {})
    local_image = payload.get("local_image_path", "")
    reddit_data = payload.get("reddit_source", {})

    time_str = dt.get("formatted_full", "Hari Ini")
    mood_name = mood.get("mood_name", "Santai")
    niche_title = niche.get("niche_title", "Gaya Hidup")
    source_label = f"Reddit (r/{reddit_data.get('subreddit')})" if reddit_data else "Teks Santai Mama"

    # 1. BINA KAD RINGKASAN
    summary_card = (
        f"🌸 <b>[AUDIT LIFESTYLE] IMPIAN RUMAHKU & CERITA MAMA</b>\n"
        f"━━━━━━━━━━━━━━━━━━━━\n"
        f"🕒 <b>Waktu:</b> {time_str}\n"
        f"🎭 <b>Mood:</b> {mood_name}\n"
        f"🌿 <b>Niche:</b> {niche_title}\n"
        f"📖 <b>Sumber:</b> {source_label}\n"
        f"🧠 <b>Enjin AI:</b> <code>{engine_used}</code>\n"
        f"⏱️ <b>Masa Proses:</b> {total_time:.2f} saat\n\n"
        f"🚀 <b>STATUS MEDIA SOSIAL:</b>\n"
        f"• <b>Facebook:</b> {format_platform_status(post_results.get('facebook', {}))}\n"
        f"• <b>Threads:</b> {format_platform_status(post_results.get('threads', {}))}\n"
        f"• <b>Instagram:</b> {format_platform_status(post_results.get('instagram', {}))}\n"
        f"• <b>Bluesky:</b> {format_platform_status(post_results.get('bluesky', {}))}\n"
        f"━━━━━━━━━━━━━━━━━━━━"
    )

    # Hantar gambar jika wujud
    if local_image and os.path.exists(local_image):
        photo_ok, photo_err = send_telegram_photo(local_image, caption=summary_card, token=token, chat_id=chat_id)
        if not photo_ok:
            send_telegram_message(summary_card, token=token, chat_id=chat_id)
    else:
        send_telegram_message(summary_card, token=token, chat_id=chat_id)

    # 2. BINA MESEJ AUDIT TEKS 4 PLATFORM
    if ai_captions:
        fb_cap = html.escape(ai_captions.get("facebook", "Tiada teks"))
        th_cap = html.escape(ai_captions.get("threads", "Tiada teks"))
        ig_cap = html.escape(ai_captions.get("instagram", "Tiada teks"))
        bs_cap = html.escape(ai_captions.get("bluesky", "Tiada teks"))

        captions_audit_msg = (
            f"📝 <b>AUDIT JANAAN AYAT PERSONA MAMA</b>\n\n"
            f"🔵 <b>Facebook Feed ({len(fb_cap)} aksara):</b>\n<blockquote>{fb_cap}</blockquote>\n\n"
            f"🧵 <b>Meta Threads ({len(th_cap)} aksara):</b>\n<blockquote>{th_cap}</blockquote>\n\n"
            f"📸 <b>Instagram Feed ({len(ig_cap)} aksara):</b>\n<blockquote>{ig_cap}</blockquote>\n\n"
            f"🦋 <b>Bluesky Feed ({len(bs_cap)} aksara):</b>\n<blockquote>{bs_cap}</blockquote>"
        )
        send_telegram_message(captions_audit_msg, token=token, chat_id=chat_id)

    if has_successful_lifestyle_post(payload):
        print("📢 [AUDIT TELEGRAM] Laporan berjaya dihantar ke Telegram.")
        return True, "Audit berjaya dihantar."
    else:
        print("⚠️ [AUDIT TELEGRAM WARN] Semua platform gagal pos.")
        return False, "Semua platform gagal disiarkan."


if __name__ == "__main__":
    print("=" * 70)
    print("🧪 [TEST] Menguji Modul Telegram Audit Persona Lifestyle...")
    print("=" * 70)
    sample_payload = {
        "datetime": {"formatted_full": "Rabu, 26 Ogos 2026, 05:15 PM"},
        "mood": {"mood_name": "Santai Pertengahan Minggu"},
        "niche": {"niche_title": "Tanaman & Pasu Hiasan"},
        "engine_used": "LOCAL_QWEN35_GGUF",
        "total_duration_sec": 18.5,
        "post_results": {
            "facebook": {"status": "success", "post_id": "fb_12345"},
            "threads": {"status": "success", "thread_id": "th_67890"},
            "instagram": {"status": "skipped", "reason": "text_only_no_image"},
            "bluesky": {"status": "success", "uri": "at://did:plc:123/post/1"},
        },
        "ai_captions": {
            "facebook": "Petang macam ni seronok bila dapat tengok pokok monstera mula kembang daun baru...",
            "threads": "Petang macam ni seronok bila dapat tengok pokok monstera mula kembang daun baru...",
            "instagram": "Petang macam ni seronok bila dapat tengok pokok monstera mula kembang daun baru...",
            "bluesky": "Petang macam ni seronok bila dapat tengok pokok monstera kembang daun baru.",
        }
    }
    ok, msg = send_lifestyle_telegram_audit_report(sample_payload)
    print(f"Hasil Ujian: {ok} | Mesej: {msg}")
    print("=" * 70)