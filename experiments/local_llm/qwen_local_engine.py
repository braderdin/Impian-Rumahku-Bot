#!/usr/bin/env python3
"""
Local LLM Translation & Copywriting Engine: Qwen 2.5 3B GGUF (Optimized Edition)
Location: experiments/local_llm/qwen_local_engine.py

Enhancements:
- Strict Token Budget (max_tokens=150) -> Cuts inference time to ~15-20s
- Strict Repetition Penalty (1.22) -> Prevents looping on the same points
- Zero-Indo Guardrail -> Enforces pure Malaysian Malay (kelabu, bilik air, duit, korang)
- Programmatic Length Scaffolding (Target: 350 - 600 chars)
"""

import os
import re
import sys
import time
from pathlib import Path
from typing import Tuple, Dict, Any
from huggingface_hub import hf_hub_download
from llama_cpp import Llama

# Setup Project Root Path
PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

REPO_ID = "Qwen/Qwen2.5-3B-Instruct-GGUF"
MODEL_FILENAME = "qwen2.5-3b-instruct-q5_k_m.gguf"

_LLM_INSTANCE = None


def get_qwen_model_path() -> str:
    print(f"📥 [QWEN ENGINE] Memeriksa fail GGUF: {MODEL_FILENAME}...")
    start_t = time.time()
    model_path = hf_hub_download(
        repo_id=REPO_ID,
        filename=MODEL_FILENAME,
        local_files_only=False
    )
    print(f"✅ [QWEN ENGINE] Model sedia ({time.time() - start_t:.2f}s): {model_path}")
    return model_path


def load_local_qwen_llm() -> Llama:
    global _LLM_INSTANCE
    if _LLM_INSTANCE is not None:
        return _LLM_INSTANCE

    model_path = get_qwen_model_path()
    print("⚙️ [QWEN ENGINE] Memuatkan model ke dalam memori CPU (2 vCPU)...")
    start_t = time.time()

    _LLM_INSTANCE = Llama(
        model_path=model_path,
        n_ctx=1024,
        n_threads=2,
        n_batch=256,
        verbose=False
    )
    print(f"🚀 [QWEN ENGINE] Enjin LLM sedia ({time.time() - start_t:.2f}s)!")
    return _LLM_INSTANCE


def clean_and_normalize_bm(text: str) -> str:
    """Membersihkan tag pemikiran, perkataan Indonesia, dan menormalkan tanda baca."""
    if not text:
        return ""

    # Buang tag AI & markdown
    cleaned = re.sub(r"<think>.*?</think>", "", text, flags=re.DOTALL)
    cleaned = re.sub(r"```[a-zA-Z]*\n?", "", cleaned)
    cleaned = re.sub(r"```", "", cleaned)

    # Kamus Penukaran Istilah Indonesia -> BM Tempatan
    indo_to_bm = {
        r"\babu-abu\b": "kelabu",
        r"\bkamar mandi\b": "bilik air",
        r"\bruang tamu\b": "ruang tamu",
        r"\buang\b": "duit",
        r"\bAnda\b": "korang",
        r"\banda\b": "korang",
        r"\bbisa\b": "boleh",
        r"\bbanget\b": "sangat",
        r"\bnggak\b": "tak",
        r"\bgampang\b": "mudah",
        r"\bbikin\b": "buat",
        r"\bditancap\b": "digantung",
        r"\bmendetail\b": "terperinci",
    }
    for pattern, replacement in indo_to_bm.items():
        cleaned = re.sub(pattern, replacement, cleaned, flags=re.IGNORECASE)

    # Buang simbol rosak & emoji mentah
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

    # Pastikan perenggan berakhir dengan tanda baca sempurna
    match = re.search(r"^([\s\S]*[.!?])", cleaned.strip())
    if match:
        cleaned = match.group(1).strip()

    return cleaned


def trim_to_target_length(text: str, min_len: int = 350, max_len: int = 600) -> str:
    """Mengawal had keras aksara supaya sentiasa berada dalam lingkungan sasaran."""
    if len(text) <= max_len:
        return text

    trimmed = text[:max_len]
    match = re.search(r"^([\s\S]*[.!?])", trimmed)
    if match and len(match.group(1).strip()) >= min_len:
        return match.group(1).strip()
    return trimmed.rstrip() + "..."


def translate_and_adapt_to_mama_bm(
    product_name: str,
    brand: str,
    price: float,
    english_review: str
) -> Tuple[str, float, int]:
    """Menterjemah dan mengolah ulasan BI ke Persona Mama BM (350 - 600 aksara)."""
    llm = load_local_qwen_llm()

    system_prompt = (
        "Anda ialah 'Mama' daripada komuniti 'Impian Rumahku & Cerita Mama' — seorang suri rumah di Malaysia yang mesra, "
        "santai, dan berkongsi ulasan barang rumah berguna dalam Bahasa Melayu harian yang tulen.\n\n"
        "TUGASAN:\n"
        "1. Fahami ulasan visual English yang diberikan.\n"
        "2. Olah semula menjadi SATU ATAU DUA perenggan santai yang ringkas, kemas dan memikat (sekitar 50 hingga 75 patah perkataan sahaja).\n"
        "3. Ceritakan tentang warna/reka bentuk yang nampak dalam gambar dan manfaat praktikalnya untuk rumah.\n"
        "4. SASARAN PANJANG: Tepat antara 350 hingga 550 aksara sahaja.\n\n"
        "PANTANG LARANG:\n"
        "- JANGAN ulang-ulang isi yang sama.\n"
        "- DILARANG guna bahasa Indonesia (jangan guna: abu-abu, kamar mandi, uang, anda, banget, bisa, bikin, gampang).\n"
        "- Gunakan istilah harian Melayu (kelabu, bilik air, ruang tamu, senang pasang, jimat ruang, kemas elok, korang).\n"
        "- DILARANG sebut harga atau 'RM'.\n"
        "- DILARANG letak link, hashtag atau emoji.\n"
        "- Terus berikan teks perenggan ulasan tanpa sebarang mukadimah."
    )

    user_prompt = (
        f"Produk: {product_name[:50]}\n"
        f"Jenama: {brand}\n"
        f"Ulasan Visual (BI): \"{english_review}\"\n\n"
        f"Tulis olahan santai Persona Mama BM (1-2 perenggan, 350-550 aksara):"
    )

    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": user_prompt},
    ]

    print("🧠 [QWEN INFERENCE] Menjana olahan Bahasa Melayu dengan kawalan had token...")
    start_inference = time.time()

    # max_tokens=140 menghadkan kepanjangan teks ke ~400-500 aksara (inferens ~15s)
    # repeat_penalty=1.22 menghalang model mengulang frasa yang sama
    response = llm.create_chat_completion(
        messages=messages,
        temperature=0.35,
        top_p=0.85,
        max_tokens=140,
        repeat_penalty=1.22
    )

    inference_time = time.time() - start_inference
    raw_content = response["choices"][0]["message"]["content"]

    cleaned_bm = clean_and_normalize_bm(raw_content)
    final_bm = trim_to_target_length(cleaned_bm, min_len=300, max_len=600)

    return final_bm, inference_time, len(final_bm)