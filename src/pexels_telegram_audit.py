#!/usr/bin/env python3
"""
Telegram Audit & Multi-Platform Gatekeeper Engine
Impian Rumahku & Cerita Mama Ecosystem
Features:
- Dispatches formatted Telegram Summary Cards (Video Snapshot + 4-Platform Status)
- Dispatches AI Storytelling & Vision Review in formatted HTML Blockquotes
- Safety Gatekeeper: Verifies if at least ONE (1) social media platform succeeded
- Full UTF-8 & HTML safe escaping with auto-chunking (>4000 characters)
"""

import os
import sys
import html
import requests
from io import BytesIO
from pathlib import Path
from typing import Dict, Any, Tuple, Optional

# Setup Project Root Path
PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.pexels_config import get_telegram_config


def send_telegram_html_message(
    text: str,
    token: Optional[str] = None,
    chat_id: Optional[str] = None
) -> Tuple[bool, Any]:
    """
    Menghantar mesej teks berformat HTML ke Telegram dengan pemotongan selamat (>4000 aksara).
    """
    if not token or not chat_id:
        t_tok, t_chat, err = get_telegram_config()
        if err or not t_tok or not t_chat:
            return False, err
        token, chat_id = t_tok, t_chat

    url = f"https://api.telegram.org/bot{token}/sendMessage"
    max_chunk = 4000
    chunks = [text[i:i + max_chunk] for i in range(0, len(text), max_chunk)]
    last_res = None

    for chunk in chunks:
        payload = {
            "chat_id": chat_id,
            "text": chunk,
            "parse_mode": "HTML",
            "disable_web_page_preview": True,
        }
        try:
            res = requests.post(url, json=payload, timeout=20)
            last_res = res.json()
            if res.status_code != 200 or not last_res.get("ok"):
                return False, f"Telegram HTTP {res.status_code}: {res.text}"
        except Exception as e:
            return False, f"Ralat rangkaian Telegram: {str(e)}"

    return True, last_res


def send_telegram_photo_card(
    image_source: str,
    caption: str = "",
    token: Optional[str] = None,
    chat_id: Optional[str] = None
) -> Tuple[bool, Any]:
    """
    Menghantar gambar fizikal atau URI Base64 bersama kapsyen ringkas (<1024 aksara) ke Telegram.
    """
    if not token or not chat_id:
        t_tok, t_chat, err = get_telegram_config()
        if err or not t_tok or not t_chat:
            return False, err
        token, chat_id = t_tok, t_chat

    url = f"https://api.telegram.org/bot{token}/sendPhoto"
    safe_caption = caption[:1020] if caption else ""

    # Hantar fail fizikal
    if image_source and os.path.exists(image_source):
        try:
            with open(image_source, "rb") as img_file:
                files = {"photo": (os.path.basename(image_source), img_file, "image/jpeg")}
                data = {
                    "chat_id": chat_id,
                    "caption": safe_caption,
                    "parse_mode": "HTML",
                }
                res = requests.post(url, data=data, files=files, timeout=30)
                res_json = res.json()
                if res.status_code == 200 and res_json.get("ok"):
                    return True, res_json
                return False, f"HTTP {res.status_code}: {res.text}"
        except Exception as e:
            print(f"⚠️ [TELEGRAM PHOTO WARN] Gagal menghantar fail fizikal: {e}")

    # Fallback: Hantar mesej teks jika gambar tiada
    return send_telegram_html_message(caption, token=token, chat_id=chat_id)


def format_platform_status(res: Dict[str, Any]) -> str:
    """
    Membina paparan status visual bagi setiap saluran media sosial.
    """
    if not isinstance(res, dict):
        return "⚪ <i>Belum diproses</i>"

    status = res.get("status", "").lower()
    post_id = res.get("post_id") or res.get("thread_id") or res.get("media_id") or res.get("uri")
    permalink = res.get("permalink") or res.get("post_url") or ""
    error_msg = res.get("error", "Ralat tidak diketahui")

    if status == "success" or res.get("success") is True:
        link_str = f' (<a href="{permalink}">Lihat Hantaran</a>)' if permalink else ""
        id_str = f" | ID: <code>{html.escape(str(post_id)[:22])}</code>" if post_id else ""
        return f"✅ <b>BERJAYA</b>{id_str}{link_str}"
    elif status == "failed" or "error" in res:
        return f"❌ <b>GAGAL</b> (<code>{html.escape(str(error_msg)[:55])}</code>)"
    else:
        return "⚪ <i>Dilangkau</i>"


def has_any_successful_post(post_results: Dict[str, Any]) -> bool:
    """
    Pintu Keselamatan (Gatekeeper):
    Mengesahkan sekurang-kurangnya SATU (1) platform berjaya membuat hantaran.
    """
    for platform, res in post_results.items():
        if isinstance(res, dict):
            if res.get("status") == "success" or res.get("success") is True or "post_id" in res or "media_id" in res or "thread_id" in res or "uri" in res:
                return True
    return False


def send_pexels_reels_audit_report(payload: Dict[str, Any]) -> Tuple[bool, str]:
    """
    Menghantar laporan lengkap audit Reels ke Telegram:
    1. Kad Ringkasan Foto Snapshot + Metadata Muzik + Status 4 Platform.
    2. Mesej Audit Teks AI Persona Mama (BM) & Ulasan Vision (EN).
    """
    token, chat_id, err = get_telegram_config()
    if err or not token or not chat_id:
        return False, err or "Konfigurasi Telegram Audit tiada."

    video_title = html.escape(str(payload.get("video_title", "Pexels Aesthetic Reel")))
    theme_kw = html.escape(str(payload.get("video_theme_keyword", "Home & Living")))
    duration = payload.get("video_duration_seconds", 35)
    
    music_meta = payload.get("music_metadata", {})
    music_title = html.escape(str(music_meta.get("title", "Aesthetic Melody")))
    music_artist = html.escape(str(music_meta.get("artist", "Impian Rumahku Composer")))
    music_vibe = html.escape(str(music_meta.get("vibe", "Santai & Tenang")))

    post_results = payload.get("post_results", {})
    mama_caption = payload.get("final_caption_bm", "")
    vision_review = payload.get("vision_review_en", "")
    snapshot_path = payload.get("snapshot_image_path", "")

    # 1. BINA KAD RINGKASAN STATUS
    summary_card = (
        f"🎬 <b>[AUDIT REELS] IMPIAN RUMAHKU & CERITA MAMA</b>\n"
        f"━━━━━━━━━━━━━━━━━━━━\n"
        f"✨ <b>Tema:</b> {video_title}\n"
        f"🔍 <b>Kata Kunci:</b> <code>{theme_kw}</code>\n"
        f"⏱️ <b>Durasi:</b> {duration} Saat (9:16 Portrait)\n"
        f"🎵 <b>Muzik:</b> {music_title} ({music_artist})\n"
        f"🌸 <b>Vibe:</b> {music_vibe}\n\n"
        f"🚀 <b>STATUS MEDIA SOSIAL (4 PLATFORM):</b>\n"
        f"• <b>Facebook Reels:</b> {format_platform_status(post_results.get('facebook', {}))}\n"
        f"• <b>Instagram Reels:</b> {format_platform_status(post_results.get('instagram', {}))}\n"
        f"• <b>Meta Threads:</b> {format_platform_status(post_results.get('threads', {}))}\n"
        f"• <b>Bluesky Video:</b> {format_platform_status(post_results.get('bluesky', {}))}\n"
        f"━━━━━━━━━━━━━━━━━━━━"
    )

    # Hantar Kad Foto / Teks
    photo_ok, _ = send_telegram_photo_card(snapshot_path, caption=summary_card, token=token, chat_id=chat_id)
    if not photo_ok:
        send_telegram_html_message(summary_card, token=token, chat_id=chat_id)

    # 2. BINA MESEJ AUDIT TEKS AI
    audit_text_parts = []
    if mama_caption:
        safe_mama = html.escape(mama_caption)
        audit_text_parts.append(
            f"📝 <b>PENCERITAAN AI PERSONA MAMA (BM):</b>\n<blockquote>{safe_mama}</blockquote>"
        )
    if vision_review:
        safe_vision = html.escape(vision_review)
        audit_text_parts.append(
            f"👁️ <b>SINTESIS 4-FRAME VISION REVIEW (EN):</b>\n<blockquote>{safe_vision}</blockquote>"
        )

    if audit_text_parts:
        full_audit_msg = "\n\n".join(audit_text_parts)
        send_telegram_html_message(full_audit_msg, token=token, chat_id=chat_id)

    # Semakan Gatekeeper
    if has_any_successful_post(post_results):
        print("📢 [TELEGRAM AUDIT SUCCESS] Laporan audit hantaran video berjaya dihantar ke Telegram.")
        return True, "Laporan audit berjaya dihantar."
    else:
        print("⚠️ [TELEGRAM AUDIT WARN] Semua platform media sosial gagal disiarkan.")
        return False, "Semua platform media sosial gagal disiarkan."