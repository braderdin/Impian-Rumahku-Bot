#!/usr/bin/env python3
"""
Local LLM Translation & Copywriting Engine: Qwen 2.5 3B GGUF
Location: experiments/local_llm/qwen_local_engine.py

Features:
- Uses llama-cpp-python for high-speed CPU inference (Optimized for 2 vCPU GitHub Actions runner)
- Loads Quantized GGUF Model: Qwen/Qwen2.5-3B-Instruct-GGUF (qwen2.5-3b-instruct-q4_k_m.gguf ~2.1 GB)
- Translates & rewrites Plain English Vision Review into natural Persona Mama Bahasa Melayu (350 - 600 chars)
- Strict Malaysian BM vocabulary (zero Indonesian slangs)
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

# Konfigurasi Model
REPO_ID = "Qwen/Qwen2.5-3B-Instruct-GGUF"
MODEL_FILENAME = "qwen2.5-3b-instruct-q4_k_m.gguf"

_LLM_INSTANCE = None


def get_qwen_model_path() -> str:
    """
    Memuat turun (atau mengambil daripada cache) fail model GGUF dari Hugging Face.
    """
    print(f"📥 [QWEN ENGINE] Memeriksa & memuat turun fail GGUF: {MODEL_FILENAME}...")
    start_t = time.time()
    model_path = hf_hub_download(
        repo_id=REPO_ID,
        filename=MODEL_FILENAME,
        local_files_only=False
    )
    elapsed = time.time() - start_t
    print(f"✅ [QWEN ENGINE] Model sedia dalam cache ({elapsed:.2f}s): {model_path}")
    return model_path


def load_local_qwen_llm() -> Llama:
    """
    Menginisialisasi enjin llama-cpp-python dengan tetapan optimum untuk CPU 2-Core.
    """
    global _LLM_INSTANCE
    if _LLM_INSTANCE is not None:
        return _LLM_INSTANCE

    model_path = get_qwen_model_path()
    print("⚙️ [QWEN ENGINE] Memuatkan model ke dalam memori CPU...")
    start_t = time.time()

    # n_threads=2 : Sesuai dengan spesifikasi standard runner GitHub Actions (2 vCPU)
    # n_ctx=2048   : Ruang konteks cukup luas untuk prompt & output terjemahan
    _LLM_INSTANCE = Llama(
        model_path=model_path,
        n_ctx=2048,
        n_threads=2,
        n_batch=512,
        verbose=False
    )
    print(f"🚀 [QWEN ENGINE] Enjin LLM sedia dalam masa {time.time() - start_t:.2f}s!")
    return _LLM_INSTANCE


def clean_llm_output(text: str) -> str:
    """
    Membersihkan tag pemikiran, markdown, dan menormalkan tanda baca.
    """
    if not text:
        return ""

    # Buang tag pemikiran AI & markdown
    cleaned = re.sub(r"<think>.*?</think>", "", text, flags=re.DOTALL)
    cleaned = re.sub(r"```json\s*", "", cleaned)
    cleaned = re.sub(r"```\s*", "", cleaned)

    # Rawat tanda baca
    replacements = {
        "’": "'", "‘": "'", "“": '"', "”": '"',
        "—": "-", "–": "-", "…": "...", "\xa0": " ",
    }
    for orig, rep in replacements.items():
        cleaned = cleaned.replace(orig, rep)

    # Buang emoji jika ada (kerana skrip utama yang akan menguruskan susunan emoji)
    emoji_pattern = re.compile(
        "[\U00010000-\U0010ffff\uD800-\uDBFF\uDC00-\uDFFF\u2600-\u26FF\u2700-\u27BF]",
        flags=re.UNICODE,
    )
    cleaned = emoji_pattern.sub("", cleaned).strip().strip('"').strip("'")

    # Pastikan ayat diakhiri dengan tanda noktah yang kemas
    match = re.search(r"^([\s\S]*[.!?])", cleaned.strip())
    if match:
        cleaned = match.group(1).strip()

    return cleaned


def translate_and_adapt_to_mama_bm(
    product_name: str,
    brand: str,
    price: float,
    english_review: str
) -> Tuple[str, float, int]:
    """
    Menterjemah dan mengolah ulasan Bahasa Inggeris Vision ke Bahasa Melayu Persona Mama.
    Mengembalikan: (hasil_bm, masa_inferens_saat, bilangan_aksara)
    """
    llm = load_local_qwen_llm()

    system_prompt = (
        "Anda ialah 'Mama' daripada komuniti 'Impian Rumahku & Cerita Mama' — seorang suri rumah di Malaysia yang mesra, "
        "praktikal, dan bijak berkongsi pengalaman menggunakan barangan rumah dalam Bahasa Melayu harian yang santai dan natural.\n\n"
        "TUGASAN:\n"
        "1. Fahami intipati ulasan visual Bahasa Inggeris (Plain English) dan tajuk produk yang diberikan.\n"
        "2. Olah semula sepenuhnya ke dalam Bahasa Melayu Malaysia tulen yang kemas, memikat, dan mengalir lancar.\n"
        "3. Tekankan aspek praktikal: material/warna yang kelihatan, kemudahan membersih/mengemas, dan manfaatnya untuk urusan rumah seharian.\n"
        "4. Had Panjang Teks: Panjang teks mestilah antara 350 hingga 600 aksara.\n\n"
        "PANTANG LARANG KETAT:\n"
        "- BUKAN terjemahan harfiah/terus kata demi kata. Tulis seperti penceritaan ikhlas seorang suri rumah.\n"
        "- DILARANG guna istilah Indonesia (seperti: bisa, banget, nggak, ngak, yuk, bikin, gampang, cobain, cocok).\n"
        "- DILARANG sebut harga atau perkataan 'RM'.\n"
        "- DILARANG meletakkan sebarang pautan URL atau hashtag.\n"
        "- DILARANG letak emoji mentah (kod hiliran akan pasang emoji).\n"
        "- Terus berikan hasil perenggan Bahasa Melayu tanpa sebarang kata pembuka atau penutup."
    )

    user_prompt = (
        f"Nama Produk: {product_name}\n"
        f"Jenama: {brand}\n"
        f"Ulasan Visual Asal (English): \"{english_review}\"\n\n"
        f"Sila olah ulasan ini ke Bahasa Melayu Persona Mama (350 - 600 aksara):"
    )

    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": user_prompt},
    ]

    print("🧠 [QWEN INFERENCE] Menjana olahan Bahasa Melayu...")
    start_inference = time.time()

    response = llm.create_chat_completion(
        messages=messages,
        temperature=0.45,
        top_p=0.90,
        max_tokens=350,
        repeat_penalty=1.15
    )

    inference_time = time.time() - start_inference
    raw_content = response["choices"][0]["message"]["content"]
    final_bm = clean_llm_output(raw_content)

    return final_bm, inference_time, len(final_bm)