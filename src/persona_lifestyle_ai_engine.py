#!/usr/bin/env python3
"""
Persona Lifestyle Mama: Dual-Mode Multi-Platform AI Copywriting Engine
Location: src/persona_lifestyle_ai_engine.py

Platform Character Limits:
- Facebook Feed  : 300 - 500 characters
- Instagram Feed : 300 - 500 characters
- Meta Threads   : 300 - 480 characters
- Bluesky Feed   : 200 - 280 characters

Execution Hierarchy:
1. Local VLM / LLM: unsloth/Qwen3.5-4B-GGUF (Q4_K_M + mmproj-F16) [5x Try, 2s Delay]
2. OpenRouter Cascading Fallback:
   - IRCM_MODEL_PRIMARY (2x Try)
   - IRCM_MODEL_FALLBACK_1 (3x Try)
   - IRCM_MODEL_FALLBACK_2 (3x Try)
   - IRCM_MODEL_FALLBACK_3 (3x Try)
3. Deterministic Persona Mama Rule-Based Generator (100% Zero-Fail Guarantee)
"""

import os
import re
import sys
import time
import json
import base64
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple
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

REPO_ID = "unsloth/Qwen3.5-4B-GGUF"
MODEL_FILENAME = "Qwen3.5-4B-Q4_K_M.gguf"
MMPROJ_FILENAME = "mmproj-F16.gguf"

_LOCAL_LLM_INSTANCE = None


# =============================================================================
# 1. PEMASANGAN & PENGURUSAN MODEL LOCAL GGUF
# =============================================================================
def get_or_load_local_qwen35(require_vision: bool = False):
    """
    Memuatkan model tempatan Qwen3.5-4B (Q4_K_M) ke dalam RAM/CPU.
    """
    global _LOCAL_LLM_INSTANCE
    if _LOCAL_LLM_INSTANCE is not None:
        return _LOCAL_LLM_INSTANCE

    try:
        from huggingface_hub import hf_hub_download
        from llama_cpp import Llama

        print(f"📥 [LOCAL AI] Memeriksa fail model tempatan: {MODEL_FILENAME}...")
        model_path = hf_hub_download(repo_id=REPO_ID, filename=MODEL_FILENAME, local_files_only=False)

        chat_handler = None
        if require_vision:
            print(f"📥 [LOCAL AI] Memeriksa fail vision projector: {MMPROJ_FILENAME}...")
            mmproj_path = hf_hub_download(repo_id=REPO_ID, filename=MMPROJ_FILENAME, local_files_only=False)
            try:
                from llama_cpp.llama_chat_format import Qwen2VLChatHandler
                chat_handler = Qwen2VLChatHandler(clip_model_path=mmproj_path)
            except Exception:
                try:
                    from llama_cpp.llama_chat_format import Llava15ChatHandler
                    chat_handler = Llava15ChatHandler(clip_model_path=mmproj_path)
                except Exception as e:
                    print(f"⚠️ [CHAT HANDLER WARN] {e}")

        _LOCAL_LLM_INSTANCE = Llama(
            model_path=model_path,
            chat_handler=chat_handler,
            n_ctx=2048,
            n_threads=2,
            n_batch=256,
            verbose=False
        )
        print("🚀 [LOCAL AI] Enjin Qwen3.5-4B (Q4_K_M) sedia digunakan!")
        return _LOCAL_LLM_INSTANCE

    except Exception as e:
        print(f"⚠️ [LOCAL AI LOAD FAILED] {e}")
        return None


# =============================================================================
# 2. PENAPISAN & PEMBERSIHAN KANDUNGAN TEKS (ZERO-INDO & ZERO-EMOJI)
# =============================================================================
def scrub_and_clean_copy(text: str) -> str:
    """
    Membersihkan tag pemikiran AI, emoji mentah, markdown, dan menukarkan istilah Indonesia ke BM.
    """
    if not text:
        return ""

    # Buang tag AI & markdown
    cleaned = re.sub(r"<think>.*?</think>", "", text, flags=re.DOTALL)
    cleaned = re.sub(r"```json\s*", "", cleaned)
    cleaned = re.sub(r"```\s*", "", cleaned)

    # Penapis Kamus Indonesia -> Bahasa Melayu Tulen
    indo_to_bm = {
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
    }
    for pattern, replacement in indo_to_bm.items():
        cleaned = re.sub(pattern, replacement, cleaned, flags=re.IGNORECASE)

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

    # Buang baris pertama jika dimulakan dengan 'Tajuk:', 'Title:', dsb.
    lines = [line.strip() for line in cleaned.split("\n") if line.strip()]
    if lines and (lines[0].lower().startswith("tajuk") or lines[0].lower().startswith("title")):
        lines.pop(0)
    cleaned = " ".join(lines)

    return cleaned.strip()


def trim_to_sentence_boundary(text: str, max_chars: int) -> str:
    """
    Memotong teks secara kemas pada tanda noktah ayat terakhir tanpa melebihi had aksara.
    """
    if len(text) <= max_chars:
        return text

    trimmed = text[:max_chars]
    match = re.search(r"^([\s\S]*[.!?])", trimmed)
    if match and len(match.group(1).strip()) >= (max_chars * 0.6):
        return match.group(1).strip()

    return trimmed.rstrip() + "."


def validate_lifestyle_text(text: str, min_chars: int, max_chars: int) -> Tuple[bool, str]:
    """
    Memastikan teks mematuhi panjang aksara, hanya abjad Latin standard, dan tiada looping glitch.
    """
    if not text or len(text) < min_chars:
        return False, f"Teks terlalu pendek ({len(text)} aksara, minima {min_chars})."
    if len(text) > max_chars:
        return False, f"Teks melebihi had ({len(text)} aksara, maksima {max_chars})."

    allowed_pattern = re.compile(r"^[a-zA-Z0-9\s.,!?'\"\–\—\-\(\)/%:;RMrm\n\r]+$")
    if not allowed_pattern.match(text):
        return False, "Dikesan simbol atau aksara bukan abjad Latin standard."

    words = re.findall(r"\b\w+\b", text.lower())
    if words:
        counts: Dict[str, int] = {}
        for w in words:
            if len(w) > 3:
                counts[w] = counts.get(w, 0) + 1
                if counts[w] > 8:
                    return False, f"Glitch dikesan: perkataan '{w}' berulang melebihi 8 kali."

    return True, ""


# =============================================================================
# 3. PENJANAAN AI TEMPATAN & FALLBACK OPENROUTER
# =============================================================================
def get_openrouter_config() -> Tuple[Optional[str], Optional[str], List[str]]:
    """Membaca konfigurasi OpenRouter dan model fallback."""
    base_url = os.getenv("IRCM_OPENROUTER_BASE_URL", "").strip()
    api_key = os.getenv("IRCM_OPENROUTER_API_KEY", "").strip()

    models = [
        os.getenv("IRCM_MODEL_PRIMARY", "").strip(),
        os.getenv("IRCM_MODEL_FALLBACK_1", "").strip(),
        os.getenv("IRCM_MODEL_FALLBACK_2", "").strip(),
        os.getenv("IRCM_MODEL_FALLBACK_3", "").strip(),
    ]
    valid_models = [m for m in models if m]
    endpoint = base_url if base_url.endswith("/chat/completions") else f"{base_url.rstrip('/')}/chat/completions"
    return endpoint, api_key, valid_models


def call_local_qwen_generation(
    system_prompt: str,
    user_prompt: str,
    max_tokens: int = 200,
    max_retries: int = 5,
    min_len: int = 300,
    max_len: int = 500,
    base64_image: Optional[str] = None
) -> Optional[str]:
    """Menjalankan inferens tempatan Qwen3.5-4B dengan 5x percubaan."""
    llm = get_or_load_local_qwen35(require_vision=bool(base64_image))
    if not llm:
        return None

    if base64_image:
        user_content = [
            {"type": "text", "text": user_prompt},
            {"type": "image_url", "image_url": {"url": base64_image}},
        ]
    else:
        user_content = user_prompt

    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": user_content},
    ]

    print(f"🧠 [LOCAL AI ATTEMPT] Memulakan penjanaan tempatan Qwen3.5-4B (Sasaran: {min_len}-{max_len} aksara)...")
    for attempt in range(1, max_retries + 1):
        try:
            res = llm.create_chat_completion(
                messages=messages,
                temperature=0.35 + (attempt * 0.05),
                top_p=0.85,
                max_tokens=max_tokens,
                repeat_penalty=1.20,
            )
            raw = res["choices"][0]["message"]["content"]
            cleaned = scrub_and_clean_copy(raw)
            trimmed = trim_to_sentence_boundary(cleaned, max_len)

            is_valid, reason = validate_lifestyle_text(trimmed, min_chars=min_len, max_chars=max_len)
            if is_valid:
                print(f"   ✅ [Local AI Berjaya] Percubaan #{attempt} diterima ({len(trimmed)} aksara).")
                return trimmed
            else:
                print(f"   ⚠️ [Local AI Percubaan {attempt}/{max_retries} Tidak Sah]: {reason}")
        except Exception as e:
            print(f"   ⚠️ [Local AI Ralat ({attempt}/{max_retries})]: {e}")

        time.sleep(2)

    return None


def call_openrouter_cascading_fallback(
    system_prompt: str,
    user_prompt: str,
    min_len: int = 300,
    max_len: int = 500
) -> Optional[str]:
    """Panggilan sandaran bertingkat kepada OpenRouter jika model tempatan gagal."""
    endpoint, api_key, models = get_openrouter_config()
    if not endpoint or not api_key or not models:
        return None

    headers = {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"}

    for model_name in models:
        print(f"📡 [OPENROUTER FALLBACK] Mencuba model: {model_name}...")
        for attempt in range(1, 3):
            try:
                payload = {
                    "model": model_name,
                    "messages": [
                        {"role": "system", "content": system_prompt},
                        {"role": "user", "content": user_prompt},
                    ],
                    "temperature": 0.40,
                }
                res = requests.post(endpoint, headers=headers, json=payload, timeout=30)
                if res.status_code == 200:
                    raw = res.json().get("choices", [{}])[0].get("message", {}).get("content", "")
                    cleaned = scrub_and_clean_copy(raw)
                    trimmed = trim_to_sentence_boundary(cleaned, max_len)

                    is_valid, reason = validate_lifestyle_text(trimmed, min_chars=min_len, max_chars=max_len)
                    if is_valid:
                        print(f"   ✅ [OpenRouter Berjaya: {model_name}] ({len(trimmed)} aksara).")
                        return trimmed
            except Exception as e:
                print(f"   ⚠️ [OpenRouter Ralat ({model_name} {attempt}/2)]: {e}")
            time.sleep(2)

    return None


def generate_rule_based_lifestyle_fallback(context_payload: Dict[str, Any], platform: str) -> str:
    """Penjana sandaran peraturan dinamik (100% Zero-Fail Guarantee)."""
    niche_title = context_payload.get("niche", {}).get("niche_title", "Kehidupan Harian")
    period = context_payload.get("datetime", {}).get("period", "Hari Ini")

    fb_text = (
        f"Waktu {period.lower()} macam ni memang seronok bila dapat luangkan masa tenangkan fikiran di rumah. "
        f"Bila cerita pasal {niche_title.lower()}, banyak perkara kecil yang sebenarnya memudahkan urusan harian kita sekeluarga. "
        f"Ruang rumah nampak lebih tersusun rapi dan suasana pun jadi lebih tenang tanpa perlu pening kepala."
    )
    if platform == "bluesky":
        return fb_text[:250].rsplit(" ", 1)[0] + "."
    elif platform == "threads":
        return fb_text[:450].rsplit(" ", 1)[0] + "."
    return fb_text


# =============================================================================
# 4. PENGENDALI UTAMA PENJANAAN 4 PLATFORM
# =============================================================================
def generate_all_lifestyle_captions(
    context_payload: Dict[str, Any],
    local_image_path: Optional[str] = None
) -> Tuple[Dict[str, str], str]:
    """
    Menjana teks ulasan santai Persona Mama yang diselaraskan untuk 4 platform.
    Memulangkan: (dict_captions, engine_mode_used)
    """
    dt = context_payload.get("datetime", {})
    mood = context_payload.get("mood", {})
    niche = context_payload.get("niche", {})
    memories = context_payload.get("recent_memories", [])
    reddit = context_payload.get("reddit_source", {})

    memories_str = "\n".join([f"- {m}" for m in memories]) if memories else "Tiada topik baru lagi."
    reddit_context = f"Rujukan Inspirasi: {reddit.get('title', '')} - {reddit.get('description', '')}" if reddit else "Inspirasi rutin harian rumah."

    # Encode image ke Base64 jika ada
    b64_img = None
    if local_image_path and os.path.exists(local_image_path):
        try:
            with open(local_image_path, "rb") as img_f:
                b64_img = f"data:image/jpeg;base64,{base64.b64encode(img_f.read()).decode('utf-8')}"
        except Exception:
            pass

    system_prompt = (
        "Anda ialah 'Mama' daripada 'Impian Rumahku & Cerita Mama' — wanita Melayu awal 30-an, suri rumah berdikari di Malaysia yang praktikal, "
        "mesra, dan suka berkongsi cerita kehidupan santai tanpa gaya kaku.\n\n"
        "TUGASAN:\n"
        "Tulis 1 perenggan perkongsian santai gaya Mama dalam Bahasa Melayu Malaysia tulen (sekitar 50 hingga 75 patah perkataan).\n"
        "Fokus pada situasi kehidupan harian yang praktikal mengikut topik dan suasana masa yang diberikan.\n\n"
        "PANTANG LARANG KETAT:\n"
        "- DILARANG meletakkan emoji atau simbol grafik sama sekali.\n"
        "- DILARANG guna istilah Indonesia (jangan guna: abu-abu, kamar mandi, uang, anda, banget, bisa, bikin, gampang, yuk, cobain).\n"
        "- Gunakan perkataan Melayu: kelabu, bilik air, duit, korang, jimat ruang, kemas elok, senang guna, sedap mata memandang.\n"
        "- DILARANG beritahu ini dihasilkan oleh AI atau automasi. Tulis seperti manusia sebenar.\n"
        "- DILARANG letak link, hashtag, atau baris tajuk 'Tajuk:'. Terus mula bercerita."
    )

    user_prompt = (
        f"Konteks Waktu: {dt.get('formatted_full', '')} ({mood.get('mood_name', '')})\n"
        f"Suasana: {dt.get('period_context', '')}\n"
        f"Niche/Topik: {niche.get('niche_title', '')}\n"
        f"Fokus Cerita: {niche.get('prompt_hook', '')}\n"
        f"{reddit_context}\n"
        f"Topik Terdahulu (JANGAN ULANG ISI SAMA):\n{memories_str}\n\n"
        f"Tulis ulasan santai Mama BM (350-480 aksara):"
    )

    # 1. Cuba Penjanaan Master Story Melalui Local AI
    master_story = call_local_qwen_generation(
        system_prompt=system_prompt,
        user_prompt=user_prompt,
        max_tokens=180,
        max_retries=5,
        min_len=300,
        max_len=490,
        base64_image=b64_img
    )
    engine_used = "LOCAL_QWEN35_GGUF"

    # 2. Cuba OpenRouter Jika Local Gagal
    if not master_story:
        print("🔄 Beralih ke OpenRouter Cascading Fallback...")
        master_story = call_openrouter_cascading_fallback(
            system_prompt=system_prompt,
            user_prompt=user_prompt,
            min_len=300,
            max_len=490
        )
        engine_used = "OPENROUTER_FALLBACK"

    # 3. Rule-Based Fallback Jika Semua Gagal
    if not master_story:
        print("🛡️ Mengaktifkan Rule-Based Mama Fallback...")
        master_story = generate_rule_based_lifestyle_fallback(context_payload, "facebook")
        engine_used = "RULE_BASED_FALLBACK"

    # 4. Selaraskan Had Aksara Setiap Saluran
    captions = {
        "facebook": trim_to_sentence_boundary(master_story, 500),
        "instagram": trim_to_sentence_boundary(master_story, 500),
        "threads": trim_to_sentence_boundary(master_story, 480),
        "bluesky": trim_to_sentence_boundary(master_story, 275),
    }

    return captions, engine_used


if __name__ == "__main__":
    print("=" * 70)
    print("🧪 [TEST] Menguji Enjin AI Persona Lifestyle (Local + Fallback)...")
    print("=" * 70)

    from src.persona_lifestyle_context import build_lifestyle_context_payload

    dummy_context = build_lifestyle_context_payload()
    result_caps, used_engine = generate_all_lifestyle_captions(dummy_context)

    print(f"\n🚀 Mod Enjin Digunakan: {used_engine}\n")
    for platform, text in result_caps.items():
        print(f"📱 [{platform.upper()}] ({len(text)} aksara):")
        print(f"\"{text}\"\n")
    print("=" * 70)