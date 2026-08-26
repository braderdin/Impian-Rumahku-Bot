#!/usr/bin/env python3
"""
Persona Lifestyle Mama: Dedicated Local GGUF Engine
Location: src/persona_lifestyle_ai_gguf.py
Features:
- Powered by unsloth/Qwen3.5-4B-GGUF (Q4_K_M + mmproj-F16).
- Preserves the original proven prompt & generation logic from commit e9653a9.
- Generates 1 comprehensive Persona Mama story in BM and adapts to 4 platforms.
"""

import os
import re
import sys
import time
import base64
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple
from dotenv import load_dotenv

# Setup Project Root Path
PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

env_local = PROJECT_ROOT / ".env.local"
if env_local.exists():
    load_dotenv(dotenv_path=env_local)
else:
    load_dotenv()

REPO_ID = "unsloth/Qwen3.5-4B-GGUF"
MODEL_FILENAME = "Qwen3.5-4B-Q4_K_M.gguf"
MMPROJ_FILENAME = "mmproj-F16.gguf"

try:
    import llama_cpp
    HAS_LLAMA_CPP = True
except ImportError:
    HAS_LLAMA_CPP = False

_LOCAL_LLM_INSTANCE = None


def get_or_load_local_qwen35(require_vision: bool = False):
    """Memuatkan model tempatan Qwen3.5-4B ke dalam memori."""
    global _LOCAL_LLM_INSTANCE
    if not HAS_LLAMA_CPP:
        return None

    if _LOCAL_LLM_INSTANCE is not None:
        return _LOCAL_LLM_INSTANCE

    try:
        from huggingface_hub import hf_hub_download
        from llama_cpp import Llama

        print(f"📥 [GGUF ENGINE] Memeriksa fail model tempatan: {MODEL_FILENAME}...")
        model_path = hf_hub_download(repo_id=REPO_ID, filename=MODEL_FILENAME, local_files_only=False)

        chat_handler = None
        if require_vision:
            print(f"📥 [GGUF ENGINE] Memeriksa projector vision: {MMPROJ_FILENAME}...")
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
        print("🚀 [GGUF ENGINE] Enjin Qwen3.5-4B (Q4_K_M) sedia digunakan!")
        return _LOCAL_LLM_INSTANCE

    except Exception as e:
        print(f"⚠️ [GGUF LOAD FAILED] {e}")
        return None


def clean_gguf_output(text: str) -> str:
    """Membersihkan output teks dan menapis istilah asing."""
    if not text:
        return ""

    cleaned = re.sub(r"<think>.*?</think>", "", text, flags=re.DOTALL)
    cleaned = re.sub(r"```json\s*", "", cleaned)
    cleaned = re.sub(r"```\s*", "", cleaned)

    word_replacements = {
        r"\baku\b": "Mama",
        r"\bAku\b": "Mama",
        r"\bsaya\b": "Mama",
        r"\bSaya\b": "Mama",
        r"\bkulkas\b": "peti sejuk",
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

    replacements = {
        "’": "'", "‘": "'", "“": '"', "”": '"',
        "—": "-", "–": "-", "…": "...", "\xa0": " ",
    }
    for orig, rep in replacements.items():
        cleaned = cleaned.replace(orig, rep)

    emoji_pattern = re.compile(
        "[\U00010000-\U0010ffff\uD800-\uDBFF\uDC00-\uDFFF\u2600-\u26FF\u2700-\u27BF]",
        flags=re.UNICODE,
    )
    cleaned = emoji_pattern.sub("", cleaned).strip().strip('"').strip("'")

    lines = [line.strip() for line in cleaned.split("\n") if line.strip()]
    if lines and (lines[0].lower().startswith("tajuk") or lines[0].lower().startswith("title") or lines[0].startswith("**")):
        lines.pop(0)
    cleaned = " ".join(lines)

    return cleaned.strip()


def trim_to_sentence_boundary(text: str, max_chars: int) -> str:
    """Memotong teks pada noktah ayat terakhir secara kemas."""
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


def validate_gguf_text(text: str, min_chars: int = 250, max_chars: int = 500) -> Tuple[bool, str]:
    """Semakan kualiti abjad dan panjang teks."""
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


def generate_lifestyle_captions_gguf(
    context_payload: Dict[str, Any],
    local_image_path: Optional[str] = None
) -> Optional[Dict[str, str]]:
    """Penjanaan teks menggunakan model tempatan Qwen3.5-4B GGUF."""
    if not HAS_LLAMA_CPP:
        return None

    b64_img = None
    if local_image_path and os.path.exists(local_image_path):
        try:
            with open(local_image_path, "rb") as img_f:
                b64_img = f"data:image/jpeg;base64,{base64.b64encode(img_f.read()).decode('utf-8')}"
        except Exception:
            pass

    llm = get_or_load_local_qwen35(require_vision=bool(b64_img))
    if not llm:
        return None

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
        "- DILARANG guna istilah Indonesia (kulkas, abu-abu, kamar mandi, uang, anda, banget, bisa, bikin, gampang, yuk, cobain).\n"
        "- Gunakan perkataan Melayu: kelabu, bilik air, duit, korang, jimat ruang, kemas elok, senang guna, sedap mata memandang.\n"
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

    if b64_img:
        user_content = [
            {"type": "text", "text": user_prompt},
            {"type": "image_url", "image_url": {"url": b64_img}},
        ]
    else:
        user_content = user_prompt

    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": user_content},
    ]

    print("🧠 [GGUF ENGINE] Menjana Master Story melalui Local Qwen3.5-4B...")
    for attempt in range(1, 4):
        try:
            res = llm.create_chat_completion(
                messages=messages,
                temperature=0.35 + (attempt * 0.05),
                top_p=0.85,
                max_tokens=180,
                repeat_penalty=1.20,
            )
            raw = res["choices"][0]["message"]["content"]
            cleaned = clean_gguf_output(raw)
            trimmed = trim_to_sentence_boundary(cleaned, 490)

            is_valid, reason = validate_gguf_text(trimmed, min_chars=250, max_chars=500)
            if is_valid:
                print(f"   ✅ [GGUF Berjaya] Percubaan #{attempt} diterima ({len(trimmed)} aksara).")
                return {
                    "facebook": trim_to_sentence_boundary(trimmed, 500),
                    "instagram": trim_to_sentence_boundary(trimmed, 500),
                    "threads": trim_to_sentence_boundary(trimmed, 480),
                    "bluesky": trim_to_sentence_boundary(trimmed, 275),
                }
            else:
                print(f"   ⚠️ [GGUF Output Tidak Sah ({attempt}/3)]: {reason}")
        except Exception as e:
            print(f"   ⚠️ [GGUF Error ({attempt}/3)]: {e}")

        time.sleep(1.5)

    return None