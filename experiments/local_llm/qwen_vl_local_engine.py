#!/usr/bin/env python3
"""
Local Vision-Language (VLM) Engine: Qwen2.5-VL 3B GGUF (Q5_K_M Edition)
Location: experiments/local_llm/qwen_vl_local_engine.py

Features:
- Loads unsloth/Qwen2.5-VL-3B-Instruct-GGUF (Qwen2.5-VL-3B-Instruct-Q5_K_M.gguf ~2.22 GB)
- Loads Multimodal Projector (mmproj-F16.gguf ~1.34 GB)
- Direct Image-to-BM Persona Mama generation (No OpenRouter Vision needed)
- Memory-safe image pre-scaling (512x512) for rapid CPU inference
- Zero Indonesian slangs scrubber & sentence boundary protector
"""

import os
import re
import sys
import time
import base64
from io import BytesIO
from pathlib import Path
from typing import Tuple, Optional
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
    """Menginisialisasi enjin Llama multimodal untuk CPU 2-Core."""
    global _VLM_INSTANCE
    if _VLM_INSTANCE is not None:
        return _VLM_INSTANCE

    model_path, mmproj_path = get_model_and_mmproj_paths()
    print("⚙️ [VLM ENGINE] Memuatkan Qwen2.5-VL (Q5_K_M) + mmproj ke dalam memori CPU...")
    start_t = time.time()

    # Inisialisasi Vision Chat Handler
    chat_handler = None
    try:
        from llama_cpp.llama_chat_format import Qwen2VLChatHandler
        chat_handler = Qwen2VLChatHandler(clip_model_path=mmproj_path)
    except (ImportError, AttributeError):
        try:
            from llama_cpp.llama_chat_format import Llava15ChatHandler
            chat_handler = Llava15ChatHandler(clip_model_path=mmproj_path)
        except Exception as e:
            print(f"⚠️ [VLM WARN] Gagal inisialisasi chat handler spesifik: {e}")

    _VLM_INSTANCE = Llama(
        model_path=model_path,
        chat_handler=chat_handler,
        n_ctx=2048,
        n_threads=2,
        n_batch=256,
        verbose=False
    )

    print(f"🚀 [VLM ENGINE] Enjin Vision AI sedia ({time.time() - start_t:.2f}s)!")
    return _VLM_INSTANCE


def prepare_image_base64(image_path: str, max_size: int = 512) -> Optional[str]:
    """Mengecilkan resolusi imej ke 512px agar inferens CPU laju dan jimat RAM."""
    try:
        with Image.open(image_path) as img:
            if img.mode in ("RGBA", "P"):
                img = img.convert("RGB")
            img.thumbnail((max_size, max_size), Image.Resampling.LANCZOS)
            buffer = BytesIO()
            img.save(buffer, format="JPEG", quality=80, optimize=True)
            b64_data = base64.b64encode(buffer.getvalue()).decode("utf-8")
            return f"data:image/jpeg;base64,{b64_data}"
    except Exception as e:
        print(f"⚠️ [IMAGE PREP ERROR] {e}")
        return None


def clean_and_scrub_bm_copy(text: str) -> str:
    """Membersihkan tag pemikiran, istilah Indonesia, dan tanda baca rosak."""
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


def generate_local_qwen_vl_copy(
    product_name: str,
    brand: str,
    price: float,
    local_image_path: str
) -> Tuple[str, float, int]:
    """
    Menjana ulasan promosi Persona Mama BM terus daripada gambar & data produk.
    Mengembalikan: (hasil_bm, masa_inferens_saat, bilangan_aksara)
    """
    vlm = load_local_qwen_vlm()
    base64_img = prepare_image_base64(local_image_path)

    system_prompt = (
        "Anda ialah 'Mama' daripada komuniti 'Impian Rumahku & Cerita Mama' — seorang suri rumah di Malaysia yang mesra, "
        "praktikal, dan suka berkongsi barang rumah berguna dalam Bahasa Melayu harian yang santai dan natural.\n\n"
        "TUGASAN:\n"
        "1. Teliti gambar produk fizikal, tajuk produk, dan harga yang diberikan.\n"
        "2. Tulis 1 atau 2 perenggan ulasan santai gaya Mama dalam Bahasa Melayu Malaysia tulen (sekitar 50 hingga 75 patah perkataan sahaja).\n"
        "3. Huraikan warna, bentuk, bahan, atau kegunaan praktikal yang kelihatan pada gambar serta bagaimana ia memudahkan urusan rumah.\n"
        "4. SASARAN PANJANG: Tepat antara 350 hingga 550 aksara.\n\n"
        "PANTANG LARANG KETAT:\n"
        "- DILARANG guna istilah Indonesia (jangan guna: abu-abu, kamar mandi, uang, anda, banget, bisa, bikin, gampang, cobain).\n"
        "- Gunakan istilah harian Melayu (kelabu, bilik air, senang lap, jimat ruang, kemas elok, korang).\n"
        "- DILARANG sebut harga atau perkataan 'RM' dalam perenggan cerita.\n"
        "- DILARANG meletakkan link, hashtag, atau emoji (kod sistem akan pasang secara automatik).\n"
        "- Terus berikan teks ulasan tanpa sebarang mukadimah atau tajuk header."
    )

    user_text = (
        f"Nama Produk: {product_name[:60]}\n"
        f"Jenama: {brand}\n"
        f"Harga: RM{price:.2f}\n\n"
        f"Sila teliti gambar produk dan tulis ulasan santai Persona Mama BM (350-550 aksara):"
    )

    content_list = [{"type": "text", "text": user_text}]
    if base64_img:
        content_list.append({"type": "image_url", "image_url": {"url": base64_img}})

    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": content_list},
    ]

    print("🧠 [QWEN-VL INFERENCE] Memproses imej dan menjana ulasan BM...")
    start_inference = time.time()

    # Had max_tokens=180 memberi ruang mencukupi (~450-550 aksara) tanpa terpotong
    response = vlm.create_chat_completion(
        messages=messages,
        temperature=0.38,
        top_p=0.85,
        max_tokens=180,
        repeat_penalty=1.20
    )

    inference_time = time.time() - start_inference
    raw_content = response["choices"][0]["message"]["content"]
    final_bm = clean_and_scrub_bm_copy(raw_content)

    return final_bm, inference_time, len(final_bm)