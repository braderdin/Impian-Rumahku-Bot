#!/usr/bin/env python3
"""
Persona Lifestyle Mama: Dedicated OpenRouter Engine (Primary-First Sequential)
Location: src/persona_lifestyle_ai_openrouter.py

Features:
- Prioritizes IRCM_MODEL_VISION if a curated Unsplash image is present in temp/.
- Prioritizes IRCM_MODEL_PRIMARY for pure text mode.
- Fallback models (Vision fallback, Fallback 1, 2, 3) are ONLY called if the primary model fails.
- High token budget (max_tokens=700) to ensure reasoning models have room for <think> without starving output text.
- Strict socket connection timeout (5s connect, 25s read) to prevent hanging terminals.
- Persona Guardrail: Enforces 'Mama' persona, scrubs Indonesian vocabulary, and enforces zero emoji.
"""

import os
import re
import sys
import time
import base64
from io import BytesIO
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple
from PIL import Image
import requests
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


def compress_image_to_b64_under_50kb(image_path: str, max_kb: int = 50) -> Optional[str]:
    """
    Memampatkan imej ke bawah 50KB dan menukarkannya kepada Base64 data URL untuk VLM.
    """
    if not image_path or not os.path.exists(image_path):
        return None

    try:
        with Image.open(image_path) as img:
            if img.mode in ("RGBA", "P"):
                img = img.convert("RGB")

            img.thumbnail((480, 480), Image.Resampling.LANCZOS)
            quality = 80

            while quality >= 20:
                buffer = BytesIO()
                img.save(buffer, format="JPEG", quality=quality, optimize=True)
                raw_bytes = buffer.getvalue()
                size_kb = len(raw_bytes) / 1024.0

                if size_kb <= max_kb or quality <= 20:
                    b64_str = base64.b64encode(raw_bytes).decode("utf-8")
                    return f"data:image/jpeg;base64,{b64_str}"

                quality -= 10
                if quality < 50:
                    img.thumbnail((int(img.width * 0.85), int(img.height * 0.85)), Image.Resampling.LANCZOS)

    except Exception as e:
        print(f"⚠️ [OPENROUTER IMAGE WARN] Gagal memproses Base64: {e}")

    return None


def clean_openrouter_output(text: str) -> str:
    """
    Membersihkan output teks OpenRouter, membuang tag reasoning AI, dan menapis istilah asing.
    """
    if not text:
        return ""

    # Buang tag pemikiran AI dan blok markdown
    cleaned = re.sub(r"<think>.*?</think>", "", text, flags=re.DOTALL)
    cleaned = re.sub(r"(?i)here'?s\s+a\s+thinking\s+process[\s\S]*?\n\n", "", cleaned)
    cleaned = re.sub(r"```json\s*", "", cleaned)
    cleaned = re.sub(r"```\s*", "", cleaned)

    # Kamus Penguatkuasaan Tona Mama & Penyingkiran Istilah Indonesia
    word_replacements = {
        r"\baku\b": "Mama",
        r"\bAku\b": "Mama",
        r"\bsaya\b": "Mama",
        r"\bSaya\b": "Mama",
        r"\bkantoran\b": "pejabat",
        r"\bcapek\b": "penat",
        r"\bkulkas\b": "peti sejuk",
        r"\bberantakan\b": "berselerak",
        r"\babu-abu\b": "kelabu",
        r"\bkamar mandi\b": "bilik air",
        r"\buang\b": "duit",
        r"\bAnda\b": "korang",
        r"\banda\b": "korang",
        r"\bbisa\b": "boleh",
        r"\bbanget\b": "sangat",
        r"\bnggak\b": "tak",
        r"\bngak\b": "tak",
        r"\bgampang\b": "mudah",
        r"\bbikin\b": "buat",
        r"\bcobain\b": "cuba",
        r"\bcocok\b": "sesuai",
        r"\byuk\b": "jom",
        r"\bgimana\b": "macam mana",
        r"\bRabuh\b": "Rabu",
        r"\bsahul\b": "sempat",
    }
    for pattern, rep in word_replacements.items():
        cleaned = re.sub(pattern, rep, cleaned)

    # Buang simbol rosak & tanda petik aneh
    replacements = {
        "’": "'", "‘": "'", "“": '"', "”": '"',
        "—": "-", "–": "-", "…": "...", "\xa0": " ",
    }
    for orig, rep in replacements.items():
        cleaned = cleaned.replace(orig, rep)

    # Buang semua emoji Unicode sama sekali
    emoji_pattern = re.compile(
        "[\U00010000-\U0010ffff\uD800-\uDBFF\uDC00-\uDFFF\u2600-\u26FF\u2700-\u27BF]",
        flags=re.UNICODE,
    )
    cleaned = emoji_pattern.sub("", cleaned).strip().strip('"').strip("'")

    # Buang tajuk atau header jika dijana oleh model
    lines = [line.strip() for line in cleaned.split("\n") if line.strip()]
    if lines and (lines[0].lower().startswith("tajuk") or lines[0].lower().startswith("title") or lines[0].startswith("**")):
        lines.pop(0)
    cleaned = " ".join(lines)

    return cleaned.strip()


def trim_to_sentence_boundary(text: str, max_chars: int) -> str:
    """
    Memotong teks pada noktah ayat terakhir secara kemas (menghalang perkataan terpotong separuh).
    """
    if len(text) <= max_chars:
        return text.strip()

    trimmed = text[:max_chars].strip()
    last_punc = max(trimmed.rfind('.'), trimmed.rfind('!'), trimmed.rfind('?'))
    if last_punc != -1 and last_punc >= int(max_chars * 0.55):
        return trimmed[:last_punc + 1].strip()

    last_space = trimmed.rfind(' ')
    if last_space != -1:
        return trimmed[:last_space].strip() + "."

    return trimmed + "."


def validate_openrouter_text(text: str, min_chars: int = 250, max_chars: int = 500) -> Tuple[bool, str]:
    """
    Semakan kualiti teks janaan OpenRouter.
    """
    if not text or len(text) < min_chars:
        return False, f"Teks terlalu pendek ({len(text)} aksara, minima {min_chars})."
    if len(text) > max_chars:
        return False, f"Teks melebihi had ({len(text)} aksara, maksima {max_chars})."

    allowed_pattern = re.compile(r"^[a-zA-Z0-9\s.,!?'\"\–\—\-\(\)/%:;RMrm\n\r]+$")
    if not allowed_pattern.match(text):
        return False, "Dikesan aksara bukan abjad Latin standard."

    words = re.findall(r"\b\w+\b", text.lower())
    if words:
        counts = {}
        for w in words:
            if len(w) > 3:
                counts[w] = counts.get(w, 0) + 1
                if counts[w] > 8:
                    return False, f"Glitch: perkataan '{w}' berulang >8 kali."

    return True, ""


def get_openrouter_queue(has_image: bool = False) -> Tuple[str, str, List[Tuple[str, str]]]:
    """
    Menyusun hierarki panggilan OpenRouter secara berurutan:
    - Model Utama didahulukan (Vision jika ada imej, Primary jika teks sahaja)[cite: 18].
    - Model Fallback hanya dimasukkan di belakang sebagai sandaran kecemasan[cite: 18].
    Memulangkan: (endpoint, api_key, [(model_name, role_label)])[cite: 18]
    """
    base_url = os.getenv("IRCM_OPENROUTER_BASE_URL", "").strip()
    api_key = os.getenv("IRCM_OPENROUTER_API_KEY", "").strip()
    endpoint = base_url if base_url.endswith("/chat/completions") else f"{base_url.rstrip('/')}/chat/completions"

    queue: List[Tuple[str, str]] = []

    # 1. Aliran Jika Ada Gambar Unsplash
    if has_image:
        m_vis = os.getenv("IRCM_MODEL_VISION", "").strip()
        m_vis_fb = os.getenv("IRCM_MODEL_VISION_FALLBACK_1", "").strip()
        if m_vis:
            queue.append((m_vis, "PRIMARY VISION"))
        if m_vis_fb and m_vis_fb != m_vis:
            queue.append((m_vis_fb, "FALLBACK VISION 1"))

    # 2. Aliran Teks Utama
    m_primary = os.getenv("IRCM_MODEL_PRIMARY", "").strip()
    m_fb1 = os.getenv("IRCM_MODEL_FALLBACK_1", "").strip()
    m_fb2 = os.getenv("IRCM_MODEL_FALLBACK_2", "").strip()
    m_fb3 = os.getenv("IRCM_MODEL_FALLBACK_3", "").strip()

    if m_primary and (m_primary, "PRIMARY VISION") not in queue:
        queue.append((m_primary, "PRIMARY TEXT"))
    if m_fb1 and m_fb1 not in [q[0] for q in queue]:
        queue.append((m_fb1, "FALLBACK TEXT 1"))
    if m_fb2 and m_fb2 not in [q[0] for q in queue]:
        queue.append((m_fb2, "FALLBACK TEXT 2"))
    if m_fb3 and m_fb3 not in [q[0] for q in queue]:
        queue.append((m_fb3, "FALLBACK TEXT 3"))

    return endpoint, api_key, queue


def generate_lifestyle_captions_openrouter(
    context_payload: Dict[str, Any],
    local_image_path: Optional[str] = None
) -> Tuple[Optional[Dict[str, str]], str]:
    """
    Penjanaan teks menggunakan OpenRouter mengikut keutamaan Model Utama[cite: 18].
    Memulangkan: (captions_dict, model_name_used)[cite: 18]
    """
    b64_img = compress_image_to_b64_under_50kb(local_image_path, max_kb=50) if local_image_path else None
    endpoint, api_key, models_queue = get_openrouter_queue(has_image=bool(b64_img))

    if not endpoint or not api_key or not models_queue:
        return None, "FAILED"

    dt = context_payload.get("datetime", {})
    mood = context_payload.get("mood", {})
    niche = context_payload.get("niche", {})
    reddit = context_payload.get("reddit_source", {})
    memories = context_payload.get("recent_memories", [])
    memories_str = ", ".join(memories) if memories else "Rutin biasa"
    reddit_context = f"Rujukan Visual: {reddit.get('title', '')} - {reddit.get('description', '')[:100]}" if reddit else "Inspirasi rutin praktikal suri rumah"

    system_prompt = (
        "Anda ialah 'Mama' daripada 'Impian Rumahku & Cerita Mama' — wanita Melayu awal 30-an, suri rumah berdikari di Malaysia yang praktikal, "
        "mesra, dan suka berkongsi cerita kehidupan santai tanpa gaya kaku.\n\n"
        "TUGASAN:\n"
        "Tulis 1 perenggan perkongsian santai gaya Mama dalam Bahasa Melayu Malaysia tulen (sekitar 50 hingga 70 patah perkataan).\n"
        "Fokus pada situasi kehidupan harian yang praktikal mengikut topik dan suasana masa yang diberikan.\n\n"
        "PANTANG LARANG KETAT:\n"
        "- WAJIB bahasakan diri sebagai 'Mama' (DILARANG guna perkataan 'aku' atau 'saya').\n"
        "- DILARANG meletakkan emoji atau simbol grafik sama sekali.\n"
        "- DILARANG guna istilah Indonesia (kantoran, capek, kulkas, berantakan, abu-abu, kamar mandi, uang, anda, banget, bisa, bikin, gampang, yuk, cobain).\n"
        "- Gunakan perkataan Melayu: pejabat, penat, peti sejuk, berselerak, kelabu, bilik air, duit, korang, jimat ruang, kemas elok, senang guna, sedap mata memandang.\n"
        "- DILARANG beritahu ini dihasilkan oleh AI. Tulis seperti manusia sebenar.\n"
        "- DILARANG letak link, hashtag, atau baris tajuk 'Tajuk:'. Terus mula bercerita."
    )

    user_prompt = (
        f"Konteks Waktu: {dt.get('formatted_full', '')} ({mood.get('mood_name', '')})\n"
        f"Suasana: {dt.get('period_context', '')}\n"
        f"Niche/Topik: {niche.get('niche_title', '')}\n"
        f"Fokus Cerita: {niche.get('prompt_hook', '')}\n"
        f"{reddit_context}\n"
        f"Topik Terdahulu (JANGAN ULANG ISI SAMA): {memories_str}\n\n"
        f"Tulis ulasan santai Mama BM (350-480 aksara):"
    )

    headers = {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"}

    for model_name, role_label in models_queue:
        print(f"📡 [OPENROUTER ENGINE] Menggunakan {role_label}: {model_name}...")

        if b64_img and "VISION" in role_label:
            user_content = [
                {"type": "text", "text": user_prompt},
                {"type": "image_url", "image_url": {"url": b64_img}},
            ]
        else:
            user_content = user_prompt

        payload = {
            "model": model_name,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_content},
            ],
            "temperature": 0.40,
            "max_tokens": 700  # Bajet token mencukupi bagi mengelakkan <think> memakan ruang output[cite: 18]
        }

        for attempt in range(1, 3):
            try:
                # Had masa soket ketat (5s connect, 25s read)
                res = requests.post(endpoint, headers=headers, json=payload, timeout=(5, 25))
                if res.status_code == 200:
                    raw = res.json().get("choices", [{}])[0].get("message", {}).get("content", "")
                    cleaned = clean_openrouter_output(raw)
                    trimmed = trim_to_sentence_boundary(cleaned, 490)

                    is_valid, reason = validate_openrouter_text(trimmed, min_chars=250, max_chars=500)
                    if is_valid:
                        print(f"   ✅ [{role_label} Berjaya] ({len(trimmed)} aksara)")
                        return {
                            "facebook": trim_to_sentence_boundary(trimmed, 500),
                            "instagram": trim_to_sentence_boundary(trimmed, 500),
                            "threads": trim_to_sentence_boundary(trimmed, 480),
                            "bluesky": trim_to_sentence_boundary(trimmed, 275),
                        }, f"OPENROUTER ({model_name})"
                    else:
                        print(f"   ⚠️ [{role_label} Format Ditolak ({attempt}/2)]: {reason}")
                elif res.status_code == 429:
                    print(f"   ⚠️ [{role_label} HTTP 429 Sesak ({attempt}/2)]. Menunggu seketika...")
                else:
                    print(f"   ⚠️ [{role_label} HTTP {res.status_code}] {res.text[:70]}")
            except requests.exceptions.Timeout:
                print(f"   ⚠️ [{role_label} Timeout ({attempt}/2)] Sambungan tamat masa (5s/25s).")
            except Exception as e:
                print(f"   ⚠️ [{role_label} Error ({attempt}/2)]: {e}")

            time.sleep(2)

        print(f"   ⚠️ [{role_label} Gagal]. Beralih ke model seterusnya...")

    return None, "FAILED"


if __name__ == "__main__":
    print("=" * 70)
    print("🧪 [TEST] Menguji Enjin Dedicated OpenRouter (Primary-First)...")
    print("=" * 70)

    from src.persona_lifestyle_context import build_lifestyle_context_payload

    dummy_context = build_lifestyle_context_payload()
    result_caps, model_used = generate_lifestyle_captions_openrouter(dummy_context)

    if result_caps:
        print(f"\n🚀 Berjaya Menggunakan Model: {model_used}\n")
        for platform, text in result_caps.items():
            print(f"📱 [{platform.upper()}] ({len(text)} aksara):")
            print(f"\"{text}\"\n")
    else:
        print("\n❌ Gagal menjana melalui OpenRouter.")
    print("=" * 70)