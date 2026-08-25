#!/usr/bin/env python3
"""
Local Vision-Language (VLM) Engine: Qwen2.5-VL 3B GGUF (Q5_K_M Edition with Resilient Fallback)
Location: experiments/local_llm/qwen_vl_local_engine.py

Features:
- Expanded Context Window (n_ctx=4096) for large vision embeddings + text generation
- 3-Tier Multi-Attempt Execution:
  * Tier 1: Full VLM (Image + Text Prompt)
  * Tier 2: Retry with Optimized Sampling (Higher Temp / Pure ChatML)
  * Tier 3: Local Text-Only Instruct (Bypass vision if image fails)
  * Tier 4: Dynamic Persona Mama Rule-Based Generator (100% Zero-Fail Guarantee)
- Strict Glitch & Foreign Alphabet Detector (Ensures only clean A-Z, 0-9, and standard punctuation)
- Automatic Indonesian-to-Malay Vocabulary Scrubber
"""

import os
import re
import sys
import time
import base64
from io import BytesIO
from pathlib import Path
from typing import Tuple, Optional, Dict, Any
from PIL import Image
from huggingface_hub import hf_hub_download
from llama_cpp import Llama

# Setup Project Root Path
PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

REPO_ID = "unsloth/Qwen2.5-VL-3B-Instruct-GGUF"
MODEL_FILENAME = "Qwen2.5-VL-3B-Instruct-Q5_K_M.gguf"
MMPROJ_FILENAME = "mmproj-F16.gguf"

_VLM_INSTANCE = None


def get_model_and_mmproj_paths() -> Tuple[str, str]:
    """Memuat turun fail GGUF Q5_K_M dan mmproj dari Hugging Face cache."""
    print(f"📥 [VLM ENGINE] Memeriksa fail model: {MODEL_FILENAME}...")
    start_t = time.time()
    model_path = hf_hub_download(
        repo_id=REPO_ID,
        filename=MODEL_FILENAME,
        local_files_only=False
    )
    print(f"📥 [VLM ENGINE] Memeriksa fail projektor visual: {MMPROJ_FILENAME}...")
    mmproj_path = hf_hub_download(
        repo_id=REPO_ID,
        filename=MMPROJ_FILENAME,
        local_files_only=False
    )
    print(f"✅ [VLM ENGINE] Fail model & vision sedia dalam cache ({time.time() - start_t:.2f}s)!")
    return model_path, mmproj_path


def load_local_qwen_vlm() -> Llama:
    """Menginisialisasi enjin Llama multimodal dengan ruang konteks 4096."""
    global _VLM_INSTANCE
    if _VLM_INSTANCE is not None:
        return _VLM_INSTANCE

    model_path, mmproj_path = get_model_and_mmproj_paths()
    print("⚙️ [VLM ENGINE] Memuatkan Qwen2.5-VL (Q5_K_M) + mmproj ke dalam memori CPU...")
    start_t = time.time()

    chat_handler = None
    try:
        from llama_cpp.llama_chat_format import Qwen2VLChatHandler
        chat_handler = Qwen2VLChatHandler(clip_model_path=mmproj_path)
    except (ImportError, AttributeError):
        try:
            from llama_cpp.llama_chat_format import Llava15ChatHandler
            chat_handler = Llava15ChatHandler(clip_model_path=mmproj_path)
        except Exception as e:
            print(f"⚠️ [VLM WARN] Gagal inisialisasi chat handler: {e}")

    # n_ctx=4096 memberi ruang besar untuk imej + token perbualan
    _VLM_INSTANCE = Llama(
        model_path=model_path,
        chat_handler=chat_handler,
        n_ctx=4096,
        n_threads=2,
        n_batch=512,
        verbose=False
    )

    print(f"🚀 [VLM ENGINE] Enjin Vision AI sedia ({time.time() - start_t:.2f}s)!")
    return _VLM_INSTANCE


def prepare_image_base64(image_path: str, max_size: int = 448) -> Optional[str]:
    """Mengecilkan resolusi imej ke 448px untuk penjimatan token visual maksimum."""
    try:
        with Image.open(image_path) as img:
            if img.mode in ("RGBA", "P"):
                img = img.convert("RGB")
            img.thumbnail((max_size, max_size), Image.Resampling.LANCZOS)
            buffer = BytesIO()
            img.save(buffer, format="JPEG", quality=75, optimize=True)
            b64_data = base64.b64encode(buffer.getvalue()).decode("utf-8")
            return f"data:image/jpeg;base64,{b64_data}"
    except Exception as e:
        print(f"⚠️ [IMAGE PREP ERROR] {e}")
        return None


def clean_and_scrub_bm_copy(text: str) -> str:
    """Membersihkan tag pemikiran, istilah Indonesia, dan menormalkan tanda baca."""
    if not text:
        return ""

    cleaned = re.sub(r"<think>.*?</think>", "", text, flags=re.DOTALL)
    cleaned = re.sub(r"```[a-zA-Z]*\n?", "", cleaned)
    cleaned = re.sub(r"```", "", cleaned)

    # Penapis Istilah Bahasa Melayu Tulen
    indo_to_bm = {
        r"\babu-abu\b": "kelabu",
        r"\bkamar mandi\b": "bilik air",
        r"\buang\b": "duit",
        r"\bAnda\b": "korang",
        r"\banda\b": "korang",
        r"\bbisa\b": "boleh",
        r"\bbanget\b": "sangat",
        r"\bnggak\b": "tak",
        r"\bgampang\b": "mudah",
        r"\bbikin\b": "buat",
        r"\bcobain\b": "cuba",
        r"\bspoons\b": "sudu",
        r"\bspoon\b": "sudu",
        r"\bknife\b": "pisau",
        r"\bknives\b": "set pisau",
    }
    for pattern, replacement in indo_to_bm.items():
        cleaned = re.sub(pattern, replacement, cleaned, flags=re.IGNORECASE)

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

    # Pastikan perenggan diakhiri tanda noktah yang sempurna
    match = re.search(r"^([\s\S]*[.!?])", cleaned.strip())
    if match:
        cleaned = match.group(1).strip()

    return cleaned


def validate_text_quality(text: str) -> Tuple[bool, str]:
    """
    Menyemak sama ada teks mempunyai panjang mencukupi dan bebas daripada aksara asing/glitch.
    """
    if not text or len(text) < 120:
        return False, f"Teks terlalu pendek ({len(text)} aksara, minima 120)."

    # Hanya benarkan abjad Latin, nombor, dan tanda baca lazim
    allowed_pattern = re.compile(r"^[a-zA-Z0-9\s.,!?'\"\–\—\-\(\)/%:;RMrm\n\r]+$")
    if not allowed_pattern.match(text):
        return False, "Dikesan simbol/aksara asing (bukan abjad Latin standard)."

    # Semak perkataan berulang (looping glitch)
    words = re.findall(r"\b\w+\b", text.lower())
    if words:
        counts: Dict[str, int] = {}
        for w in words:
            if len(w) > 3:
                counts[w] = counts.get(w, 0) + 1
                if counts[w] > 8:
                    return False, f"Glitch dikesan: Perkataan '{w}' berulang melebihi 8 kali."

    return True, ""


def generate_fallback_persona_mama(product_name: str, brand: str, price: float) -> str:
    """
    Penjana teks Persona Mama berasaskan peraturan dinamik jika semua percubaan AI gagal.
    """
    clean_name = re.sub(r"[【】\[\]()_~*#|/\\-]+", " ", product_name)
    words = [w for w in clean_name.split() if len(w) > 2][:4]
    short_title = " ".join(words) if words else "Barangan Rumah"

    return (
        f"Memang seronok dan memudahkan kerja harian bila ada {short_title} ni dekat rumah. "
        f"Barang daripada {brand} ni direka kemas, tahan lasak, dan sangat praktikal untuk kegunaan seisi keluarga setiap hari. "
        f"Bukan sahaja menjimatkan masa mengemas, malah ruang rumah pun nampak tersusun rapi dan sedap mata memandang tanpa pening kepala."
    ).strip()


def generate_local_qwen_vl_copy(
    product_name: str,
    brand: str,
    price: float,
    local_image_path: str
) -> Tuple[str, float, int]:
    """
    Menjana ulasan promosi Persona Mama BM dengan sistem perlindungan kegagalan 3-Peringkat.
    """
    vlm = load_local_qwen_vlm()
    base64_img = prepare_image_base64(local_image_path)
    start_time = time.time()

    clean_title = re.sub(r"[【】\[\]()_~*#|/\\-]+", " ", product_name).strip()[:50]

    system_prompt = (
        "Anda ialah 'Mama' daripada komuniti 'Impian Rumahku & Cerita Mama' — seorang suri rumah Malaysia yang ceria, "
        "praktikal, dan berkongsi pengalaman menggunakan barang rumah berguna dalam Bahasa Melayu harian yang santai.\n\n"
        "TUGASAN:\n"
        "1. Teliti gambar dan tajuk produk yang diberikan.\n"
        "2. Tulis 1 atau 2 perenggan ulasan santai gaya Mama dalam Bahasa Melayu Malaysia (sekitar 50 hingga 75 patah perkataan).\n"
        "3. Sebutkan warna, bahan, atau fungsi praktikal yang memudahkan kerja rumah atau memasak.\n"
        "4. SASARAN PANJANG: Antara 350 hingga 550 aksara.\n\n"
        "PANTANG LARANG:\n"
        "- DILARANG guna istilah Indonesia (jangan guna: abu-abu, kamar mandi, uang, anda, banget, bisa, bikin, gampang, cobain).\n"
        "- Gunakan istilah harian Melayu (kelabu, bilik air, senang potong, jimat ruang, kemas elok, korang).\n"
        "- DILARANG sebut harga atau perkataan 'RM'.\n"
        "- DILARANG letak link, hashtag, atau emoji.\n"
        "- Terus berikan teks ulasan tanpa sebarang mukadimah."
    )

    user_text = (
        f"Produk: {clean_title}\n"
        f"Jenama: {brand}\n"
        f"Tolong olah ulasan santai Persona Mama BM (350-550 aksara):"
    )

    # =========================================================================
    # PERCUBAAN 1 & 2: VLM MODALITI PENUH (GAMBAR + TEKS)
    # =========================================================================
    if base64_img:
        messages_vlm = [
            {"role": "system", "content": system_prompt},
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": user_text},
                    {"type": "image_url", "image_url": {"url": base64_img}},
                ],
            },
        ]

        for attempt in range(1, 3):
            print(f"🧠 [VLM ATTEMPT {attempt}/2] Memproses imej dan menjana ulasan BM...")
            try:
                response = vlm.create_chat_completion(
                    messages=messages_vlm,
                    temperature=0.45 if attempt == 1 else 0.65,
                    top_p=0.90,
                    max_tokens=260,
                    repeat_penalty=1.18,
                )
                raw_content = response["choices"][0]["message"]["content"]
                clean_bm = clean_and_scrub_bm_copy(raw_content)
                is_valid, reason = validate_text_quality(clean_bm)

                if is_valid:
                    elapsed = time.time() - start_time
                    print(f"   ✅ [VLM Berjaya] Teks diterima ({len(clean_bm)} aksara).")
                    return clean_bm, elapsed, len(clean_bm)
                else:
                    print(f"   ⚠️ [VLM Tidak Sah ({attempt}/2)]: {reason}")
            except Exception as e:
                print(f"   ⚠️ [Ralat VLM Execution]: {e}")

            time.sleep(1)

    # =========================================================================
    # PERCUBAAN 3: LOCAL TEXT-ONLY INSTRUCT FALLBACK
    # (Gunakan enjin Qwen yang sama tanpa lapisan imej jika projektor visual gagal)
    # =========================================================================
    print("🔄 [FALLBACK TIER 2] Mencuba mod teks tempatan tanpa projektor imej...")
    messages_text = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": user_text},
    ]

    try:
        response_text = vlm.create_chat_completion(
            messages=messages_text,
            temperature=0.40,
            top_p=0.85,
            max_tokens=220,
            repeat_penalty=1.20,
        )
        raw_text_only = response_text["choices"][0]["message"]["content"]
        clean_text_only = clean_and_scrub_bm_copy(raw_text_only)
        is_valid, reason = validate_text_quality(clean_text_only)

        if is_valid:
            elapsed = time.time() - start_time
            print(f"   ✅ [Text-Only Berjaya] Teks diterima ({len(clean_text_only)} aksara).")
            return clean_text_only, elapsed, len(clean_text_only)
    except Exception as e:
        print(f"   ⚠️ [Ralat Text-Only Fallback]: {e}")

    # =========================================================================
    # PERCUBAAN 4: DYNAMIC RULE-BASED PERSONA MAMA
    # =========================================================================
    print("🛡️ [FALLBACK TIER 3] Menggunakan penjana ulasan Persona Mama terjamin.")
    guaranteed_copy = generate_fallback_persona_mama(product_name, brand, price)
    elapsed = time.time() - start_time
    return guaranteed_copy, elapsed, len(guaranteed_copy)