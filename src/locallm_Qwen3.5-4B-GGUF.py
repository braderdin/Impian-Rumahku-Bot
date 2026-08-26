#!/usr/bin/env python3
"""
Enjin Utama Model Tempatan: Qwen3.5-4B GGUF (Vision + Reasoning + BM + Multimodal)
Lokasi Fail: src/locallm_Qwen3.5-4B-GGUF.py

Fungsi Fail Ini:
- Bertindak sebagai modul klien teras (Local Inference Client) merentas semua projek/skrip.
- Menguruskan pemuatan model secara 'Singleton' (model hanya dimuatkan sekali ke dalam RAM).
- Menyediakan pengurusan KV Cache 8-bit (Q8_0) & integrasi projektor Vision F16.
- Menyediakan fungsi pemanggil mudah (query API) untuk teks sahaja atau pelbagai gambar (Multimodal).
"""

import os
import re
import sys
import time
import json
import base64
from io import BytesIO
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple, Union
from PIL import Image
from dotenv import load_dotenv

# ==============================================================================
# 1. TETAPAN PATH & PERSEKITARAN
# ==============================================================================
PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

# Baca fail .env.local jika wujud (keutamaan), atau .env standard
env_local = PROJECT_ROOT / ".env.local"
if env_local.exists():
    load_dotenv(dotenv_path=env_local)
else:
    load_dotenv()


# ==============================================================================
# 2. TETAPAN & TUNING MODEL UTAMA (UBAH DI SINI MENGIKUT KEPERLUAN)
# ==============================================================================

# [TETAPAN REPO & MODEL DARI HUGGING FACE]
# Repositori asal Unsloth yang mengandungi fail kuantisasi dinamik GGUF
HF_REPO_ID = "unsloth/Qwen3.5-4B-GGUF"

# Model Teks & Asas (Kuantisasi Q4_K_M ~2.74 GB - Kualiti & kepantasan paling seimbang)
HF_MODEL_FILENAME = "Qwen3.5-4B-Q4_K_M.gguf"

# Projektor Visual / Vision Encoder (~672 MB - Membolehkan model membaca imej)
HF_MMPROJ_FILENAME = "mmproj-F16.gguf"

# [TETAPAN MEMORI & KONTEKS (TUNING LALAI UNTUK GITHUB ACTIONS / LOCAL)]
# n_ctx: Had saiz memori konteks (Input prompt + Imej + Output). 16000 terbukti selamat di RAM runner.
DEFAULT_N_CTX = 16000

# n_threads: Bilangan teras CPU untuk inferens. 2 thread amat sesuai untuk 2-vCPU runner.
DEFAULT_N_THREADS = 2

# n_batch: Jumlah token diproses serentak dalam satu batch prefill.
DEFAULT_N_BATCH = 512

# type_k & type_v: Kuantisasi Key & Value Cache (8 = GGML_TYPE_Q8_0). Menjimatkan 50% RAM tanpa cacat akal AI.
DEFAULT_KV_CACHE_TYPE = 8

# flash_attn: Mempercepatkan perhatian token visual dan mengurangkan memori kerja CPU.
DEFAULT_FLASH_ATTN = True

# [TETAPAN PENSAMPELAN (SAMPLING GENERATION PARAMETERS)]
# max_tokens: Had maksimum panjang ayat/jawapan dijana (termasuk ruang berfikir).
DEFAULT_MAX_OUTPUT_TOKENS = 4096

# temperature: 1.0 (Reasoning / Berfikir mendalam), 0.7 (Mod santai/arahan biasa).
DEFAULT_TEMPERATURE = 1.0

# top_p: Kawalan kebarangkalian kepelbagaian kosa kata.
DEFAULT_TOP_P = 0.95

# top_k: Had calon perkataan teratas yang dinilai.
DEFAULT_TOP_K = 20

# presence_penalty: Menghalang pengulangan frasa/ayat yang sama berulang kali (0.0 hingga 2.0).
DEFAULT_PRESENCE_PENALTY = 1.5


# ==============================================================================
# 3. PENGURUS MODEL (SINGLETON HOLDER)
# ==============================================================================
# Memastikan model kekal dalam RAM dan tidak dimuat turun/dimuatkan berulang kali
_CACHED_LLM_INSTANCE = None
_IS_VISION_LOADED = False


def get_or_load_qwen35_model(
    require_vision: bool = True,
    n_ctx: int = DEFAULT_N_CTX,
    n_threads: int = DEFAULT_N_THREADS,
    verbose: bool = False
):
    """
    Fungsi Pemuat Model Berpusat:
    - Memuat turun atau menyemak cache Hugging Face secara automatik.
    - Mengintegrasikan 'Llava15ChatHandler' secara dinamik untuk pemprosesan imej.
    - Mengembalikan objek model yang sedia menerima request.
    """
    global _CACHED_LLM_INSTANCE, _IS_VISION_LOADED

    # Jika model sudah sedia ada dalam memori dan menepati keperluan vision, guna semula
    if _CACHED_LLM_INSTANCE is not None:
        if require_vision and not _IS_VISION_LOADED:
            pass  # Perlu muat semula jika sesi lepas teks sahaja tetapi kini perlukan vision
        else:
            return _CACHED_LLM_INSTANCE

    try:
        from huggingface_hub import hf_hub_download
        from llama_cpp import Llama

        print(f"📥 [LOCALLM] Memeriksa / memuat fail model: {HF_MODEL_FILENAME}...")
        model_path = hf_hub_download(repo_id=HF_REPO_ID, filename=HF_MODEL_FILENAME, local_files_only=False)

        chat_handler = None
        if require_vision:
            print(f"📥 [LOCALLM] Memeriksa / memuat projector vision: {HF_MMPROJ_FILENAME}...")
            mmproj_path = hf_hub_download(repo_id=HF_REPO_ID, filename=HF_MMPROJ_FILENAME, local_files_only=False)
            
            # Pemuat Dinamik Fallback Chat Handler
            try:
                from llama_cpp.llama_chat_format import Qwen2VLChatHandler
                chat_handler = Qwen2VLChatHandler(clip_model_path=mmproj_path)
                print("👁️ [LOCALLM] Chat Handler: Qwen2VLChatHandler dimuatkan.")
            except Exception:
                try:
                    from llama_cpp.llama_chat_format import Llava15ChatHandler
                    chat_handler = Llava15ChatHandler(clip_model_path=mmproj_path)
                    print("👁️ [LOCALLM] Chat Handler: Fallback Llava15ChatHandler sedia digunakan.")
                except Exception as e:
                    print(f"⚠️ [LOCALLM WARN] Gagal mengaktifkan vision handler: {e}")

        # Inisialisasi Llama CPP dengan konfigurasi selamat
        _CACHED_LLM_INSTANCE = Llama(
            model_path=model_path,
            chat_handler=chat_handler,
            n_ctx=n_ctx,
            n_threads=n_threads,
            n_batch=DEFAULT_N_BATCH,
            type_k=DEFAULT_KV_CACHE_TYPE,
            type_v=DEFAULT_KV_CACHE_TYPE,
            flash_attn=DEFAULT_FLASH_ATTN,
            verbose=verbose
        )

        _IS_VISION_LOADED = require_vision and (chat_handler is not None)
        print("🚀 [LOCALLM] Enjin Tempatan Qwen3.5-4B sedia menerima payload!")
        return _CACHED_LLM_INSTANCE

    except Exception as e:
        print(f"❌ [LOCALLM ERROR] Gagal memuatkan model tempatan: {e}")
        return None


# ==============================================================================
# 4. FUNGSI PEMPROSESAN IMEJ & FORMATTING UTILITY
# ==============================================================================

def compress_image_to_base64_data_url(
    image_source: Union[str, Path, bytes],
    max_kb: int = 40,
    max_dimension: int = 480
) -> Optional[str]:
    """
    Fungsi Pemampat Imej:
    - Menerima laluan fail fizikal atau data bait mentah.
    - Memampatkan imej ke dimensi maksimum 480px dan saiz < 40KB (atau nilai max_kb).
    - Menukar imej kepada format 'data:image/jpeg;base64,...' yang sedia dibaca oleh model vision.
    """
    try:
        if isinstance(image_source, (str, Path)):
            if not os.path.exists(str(image_source)):
                print(f"⚠️ [LOCALLM IMAGE] Fail imej tidak wujud: {image_source}")
                return None
            img = Image.open(str(image_source))
        else:
            img = Image.open(BytesIO(image_source))

        if img.mode in ("RGBA", "P"):
            img = img.convert("RGB")

        # Kecilkan dimensi untuk mengurangkan beban visual token
        img.thumbnail((max_dimension, max_dimension), Image.Resampling.LANCZOS)

        quality = 75
        while quality >= 15:
            buf = BytesIO()
            img.save(buf, format="JPEG", quality=quality, optimize=True)
            size_kb = len(buf.getvalue()) / 1024.0
            if size_kb <= max_kb or quality <= 15:
                b64_str = base64.b64encode(buf.getvalue()).decode("utf-8")
                return f"data:image/jpeg;base64,{b64_str}"
            quality -= 10
            if quality < 45:
                img.thumbnail((int(img.width * 0.85), int(img.height * 0.85)), Image.Resampling.LANCZOS)

        b64_str = base64.b64encode(buf.getvalue()).decode("utf-8")
        return f"data:image/jpeg;base64,{b64_str}"

    except Exception as e:
        print(f"⚠️ [LOCALLM IMAGE COMPRESS ERROR] {e}")
        return None


def clean_reasoning_and_tags(raw_text: str) -> str:
    """
    Fungsi Pembersih Teks:
    - Membuang blok tag pemikiran AI (<think>...</think>).
    - Membuang pembungkus markdown JSON (```json ... ```) jika ada.
    """
    if not raw_text:
        return ""
    cleaned = re.sub(r"<think>[\s\S]*?</think>", "", raw_text, flags=re.DOTALL)
    cleaned = re.sub(r"```json\s*", "", cleaned)
    cleaned = re.sub(r"```\s*", "", cleaned)
    return cleaned.strip()


def extract_json_payload(raw_text: str) -> Optional[Dict[str, Any]]:
    """
    Fungsi Pengekstrak JSON:
    - Mengekstrak blok dictionary JSON daripada teks janaan model secara selamat.
    """
    cleaned = clean_reasoning_and_tags(raw_text)
    match = re.search(r"\{[\s\S]*\}", cleaned)
    if match:
        try:
            return json.loads(match.group(0).strip())
        except Exception:
            pass
    return None


# ==============================================================================
# 5. FUNGSI UTAMA INFERENS (API-LIKE CALLER)
# ==============================================================================

def query_local_qwen35(
    prompt: str,
    system_prompt: str = "Anda ialah pembantu AI Bahasa Melayu yang bijak, teliti dan mesra.",
    images: Optional[List[Union[str, Path, bytes]]] = None,
    max_tokens: int = DEFAULT_MAX_OUTPUT_TOKENS,
    temperature: float = DEFAULT_TEMPERATURE,
    top_p: float = DEFAULT_TOP_P,
    top_k: int = DEFAULT_TOP_K,
    presence_penalty: float = DEFAULT_PRESENCE_PENALTY,
    enable_thinking: bool = True,
    custom_n_ctx: int = DEFAULT_N_CTX
) -> Tuple[bool, str, Dict[str, Any]]:
    """
    Fungsi Utama Menjalankan Inferens (Panggil fungsi ini dari mana-mana fail):
    
    Parameter:
    - prompt (str)          : Arahan atau soalan pengguna.
    - system_prompt (str)   : Peranan / Persona AI (System Context).
    - images (list)         : Senarai fail imej fizikal / data URL / bytes (hadkan 1-4 imej).
    - max_tokens (int)      : Had token output dijana.
    - temperature (float)   : 1.0 (Reasoning aktif) / 0.7 (Mod santai).
    - enable_thinking (bool): True = Paparkan penaakulan <think>, False = Output terus.
    - custom_n_ctx (int)    : Saiz memori konteks yang diingini.
    
    Pulangan (Return Tuple):
    - is_success (bool)     : True jika janaan berjaya, False jika gagal.
    - raw_response (str)    : Teks penuh jawapan model (termasuk <think> jika ada).
    - meta_info (dict)      : Maklumat masa pemprosesan, kelajuan token, dan usage.
    """
    has_images = bool(images and len(images) > 0)
    llm = get_or_load_qwen35_model(require_vision=has_images, n_ctx=custom_n_ctx)

    if llm is None:
        return False, "Ralat: Enjin model Qwen3.5 gagal dimuatkan.", {}

    # 1. Bina Kandungan Pengguna (Teks + Imej jika ada)
    if has_images:
        user_content: List[Dict[str, Any]] = [{"type": "text", "text": prompt}]
        for idx, img_item in enumerate(images, 1):
            if isinstance(img_item, str) and img_item.startswith("data:image/"):
                b64_url = img_item
            else:
                b64_url = compress_image_to_base64_data_url(img_item, max_kb=40)
            
            if b64_url:
                user_content.append({"type": "image_url", "image_url": {"url": b64_url}})
            else:
                print(f"⚠️ [LOCALLM WARN] Imej #{idx} gagal diproses, melangkau imej ini.")
    else:
        user_content = prompt

    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": user_content}
    ]

    extra_kwargs = {}
    if not enable_thinking:
        # Menutup mod berfikir jika hanya mahu ulasan pantas
        extra_kwargs["chat_template_kwargs"] = {"enable_thinking": False}

    t0 = time.time()
    try:
        response = llm.create_chat_completion(
            messages=messages,
            temperature=temperature,
            top_p=top_p,
            top_k=top_k,
            presence_penalty=presence_penalty,
            max_tokens=max_tokens,
            **extra_kwargs
        )

        elapsed = time.time() - t0
        raw_text = response["choices"][0]["message"]["content"]
        usage = response.get("usage", {})
        completion_tokens = usage.get("completion_tokens", len(raw_text.split()))
        tok_per_sec = completion_tokens / elapsed if elapsed > 0 else 0

        meta = {
            "elapsed_seconds": round(elapsed, 2),
            "tokens_generated": completion_tokens,
            "tokens_per_second": round(tok_per_sec, 2),
            "usage": usage,
            "has_images": has_images
        }

        return True, raw_text, meta

    except Exception as e:
        elapsed = time.time() - t0
        print(f"❌ [LOCALLM INFERENCE ERROR] {e}")
        return False, str(e), {"elapsed_seconds": round(elapsed, 2), "error": str(e)}


# ==============================================================================
# 6. UJIAN DIAGNOSTIK TEMPATAN (STANDALONE RUN)
# ==============================================================================
if __name__ == "__main__":
    print("=" * 70)
    print("🧪 [DIAGNOSTIC TEST] Menguji Modul Utama src/locallm_Qwen3.5-4B-GGUF.py")
    print("=" * 70)

    test_prompt = "Hai Qwen! Terangkan secara ringkas dalam 2 ayat Bahasa Melayu tentang kelebihan menjaga pokok hiasan di ruang tamu rumah."
    
    print(f"💬 Prompt: \"{test_prompt}\"\n")
    success, output, meta_data = query_local_qwen35(
        prompt=test_prompt,
        enable_thinking=True,
        max_tokens=1024
    )

    if success:
        print(f"✅ [JANAAN BERJAYA] ({meta_data.get('elapsed_seconds')}s | {meta_data.get('tokens_per_second')} tok/s)\n")
        print("--- Output Teks Penuh ---")
        print(output)
        print("\n--- Output Selepas Pembersihan Tag Reasoning ---")
        print(clean_reasoning_and_tags(output))
    else:
        print(f"❌ [JANAAN GAGAL]: {output}")
    print("=" * 70)