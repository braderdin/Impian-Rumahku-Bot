#!/usr/bin/env python3
"""
Dual-Stage Local VLM Engine: Qwen3.5-4B GGUF (Q4_K_M + mmproj-F16)
Location: experiments/local_llm/qwen35_vl_engine.py

Pipeline Flow:
1. Stage 1: Compress image < 50KB -> Analyze image & title in English (300-600 chars) -> Save to temp/.json (3x retry, 2s delay).
2. Stage 2: Read temp/.json -> Generate Malaysian Malay Persona Mama copy (300-600 chars) with price & image context (5x retry, 2s delay).
3. Fallback: Dynamic rule-based generator if text generation/validation fails.
"""

import os
import re
import sys
import time
import json
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

TEMP_DIR = PROJECT_ROOT / "temp"
TEMP_DIR.mkdir(parents=True, exist_ok=True)

# Konfigurasi Model Qwen3.5-4B GGUF & mmproj
REPO_ID = "unsloth/Qwen3.5-4B-GGUF"
MODEL_FILENAME = "Qwen3.5-4B-Q4_K_M.gguf"
MMPROJ_FILENAME = "mmproj-F16.gguf"

_QWEN35_VLM_INSTANCE = None


def get_qwen35_model_paths() -> Tuple[str, str]:
    """Memuat turun model GGUF Q4_K_M dan projektor visual mmproj dari Hugging Face cache."""
    print(f"📥 [QWEN3.5] Memeriksa fail model: {MODEL_FILENAME}...")
    start_t = time.time()
    model_path = hf_hub_download(repo_id=REPO_ID, filename=MODEL_FILENAME, local_files_only=False)
    
    print(f"📥 [QWEN3.5] Memeriksa fail projektor visual: {MMPROJ_FILENAME}...")
    mmproj_path = hf_hub_download(repo_id=REPO_ID, filename=MMPROJ_FILENAME, local_files_only=False)
    
    print(f"✅ [QWEN3.5] Fail model & projektor sedia ({time.time() - start_t:.2f}s)!")
    return model_path, mmproj_path


def load_local_qwen35_vlm() -> Llama:
    """Menginisialisasi enjin multimodal Llama dengan mmproj handler."""
    global _QWEN35_VLM_INSTANCE
    if _QWEN35_VLM_INSTANCE is not None:
        return _QWEN35_VLM_INSTANCE

    model_path, mmproj_path = get_qwen35_model_paths()
    print("⚙️ [QWEN3.5] Memuatkan Qwen3.5-4B (Q4_K_M) + mmproj ke dalam RAM/CPU...")
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
            print(f"⚠️ [QWEN3.5 WARN] Chat handler fallback aktif: {e}")

    _QWEN35_VLM_INSTANCE = Llama(
        model_path=model_path,
        chat_handler=chat_handler,
        n_ctx=4096,
        n_threads=2,
        n_batch=512,
        verbose=False
    )

    print(f"🚀 [QWEN3.5] Enjin VLM sedia ({time.time() - start_t:.2f}s)!")
    return _QWEN35_VLM_INSTANCE


def compress_image_under_50kb(image_path: str, max_kb: int = 50) -> Tuple[Optional[str], Optional[str]]:
    """
    Memampatkan imej kepada saiz di bawah 50KB secara berperingkat 
    untuk inferens visual yang pantas pada CPU.
    """
    try:
        output_path = TEMP_DIR / f"compressed_{Path(image_path).name}"
        with Image.open(image_path) as img:
            if img.mode in ("RGBA", "P"):
                img = img.convert("RGB")

            # Mula dengan resolusi maksimum 480px
            img.thumbnail((480, 480), Image.Resampling.LANCZOS)

            quality = 80
            while quality >= 20:
                buffer = BytesIO()
                img.save(buffer, format="JPEG", quality=quality, optimize=True)
                size_kb = len(buffer.getvalue()) / 1024.0

                if size_kb <= max_kb or quality <= 20:
                    with open(output_path, "wb") as f_out:
                        f_out.write(buffer.getvalue())
                    b64_data = base64.b64encode(buffer.getvalue()).decode("utf-8")
                    print(f"   🖼️ Imej dimampatkan: {size_kb:.1f} KB (Quality={quality})")
                    return f"data:image/jpeg;base64,{b64_data}", str(output_path)

                quality -= 10
                if quality < 50:
                    img.thumbnail((int(img.width * 0.85), int(img.height * 0.85)), Image.Resampling.LANCZOS)

    except Exception as e:
        print(f"⚠️ [IMAGE COMPRESSION ERROR] {e}")
        return None, None


def scrub_and_clean_text(text: str) -> str:
    """Membersihkan tag pemikiran, istilah Indonesia dan simbol rosak."""
    if not text:
        return ""

    cleaned = re.sub(r"<think>.*?</think>", "", text, flags=re.DOTALL)
    cleaned = re.sub(r"```[a-zA-Z]*\n?", "", cleaned)
    cleaned = re.sub(r"```", "", cleaned)

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
    }
    for pattern, rep in indo_to_bm.items():
        cleaned = re.sub(pattern, rep, cleaned, flags=re.IGNORECASE)

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
    
    # Ambil teks sehingga tanda baca noktah terakhir
    match = re.search(r"^([\s\S]*[.!?])", cleaned.strip())
    if match:
        cleaned = match.group(1).strip()

    return cleaned


def validate_clean_latin_text(text: str, min_chars: int = 250, max_chars: int = 650) -> Tuple[bool, str]:
    """Memastikan teks hanya menggunakan abjad Latin, angka, tanda baca standard dan tiada glitch."""
    if not text or len(text) < min_chars:
        return False, f"Teks terlalu pendek ({len(text)} aksara, minima {min_chars})."

    # Penapis aksara Latin sahaja
    allowed_pattern = re.compile(r"^[a-zA-Z0-9\s.,!?'\"\–\—\-\(\)/%:;RMrm\n\r]+$")
    if not allowed_pattern.match(text):
        return False, "Dikesan aksara asing / simbol glitch luar abjad standard."

    # Semakan perkataan berulang (looping glitch)
    words = re.findall(r"\b\w+\b", text.lower())
    if words:
        counts: Dict[str, int] = {}
        for w in words:
            if len(w) > 3:
                counts[w] = counts.get(w, 0) + 1
                if counts[w] > 8:
                    return False, f"Glitch perkataan berulang: '{w}' muncul > 8 kali."

    return True, ""


def generate_fallback_mama_text(product_name: str, brand: str, price: float) -> str:
    """Penjana sandaran jika semua percubaan model gagal."""
    clean_name = re.sub(r"[【】\[\]()_~*#|/\\-]+", " ", product_name)
    words = [w for w in clean_name.split() if len(w) > 2][:4]
    short_title = " ".join(words) if words else "Barangan Rumah"

    return (
        f"Bila ada {short_title} daripada jenama {brand} ni dekat rumah, kerja harian jadi jauh lebih mudah dan teratur. "
        f"Dengan kualiti yang tahan lasak dan reka bentuk yang kemas berbaloi dengan harganya RM{price:.2f}, "
        f"ruang rumah nampak lebih tersusun rapi serta sangat praktikal untuk kegunaan sekeluarga setiap hari."
    ).strip()


# =============================================================================
# STEP 1: VISION OCR & ENGLISH REVIEW GENERATOR (3X RETRY) -> SAVE JSON
# =============================================================================
def stage_1_analyze_vision_english(
    product_id: str,
    product_name: str,
    brand: str,
    price: float,
    affiliate_link: str,
    image_path: str,
    max_retries: int = 3,
    delay_sec: int = 2
) -> Tuple[bool, str, str]:
    """
    Menganalisis gambar (<50KB) & tajuk produk, menjana ulasan Bahasa Inggeris (300-600 aksara),
    dan menyimpannya ke dalam fail .json di temp/.
    """
    vlm = load_local_qwen35_vlm()
    base64_img, comp_img_path = compress_image_under_50kb(image_path, max_kb=50)
    
    if not base64_img:
        return False, "Gagal memampatkan imej ke bawah 50KB.", ""

    clean_title = re.sub(r"[【】\[\]()_~*#|/\\-]+", " ", product_name).strip()[:60]
    json_output_path = TEMP_DIR / f"qwen35_stage1_{product_id}.json"

    system_prompt = (
        "You are an expert product vision analyzer. Analyze the provided product image and title.\n"
        "TASK:\n"
        "1. Identify visible product characteristics (color, shape, visible textures/materials, design).\n"
        "2. Write a clear, concise visual description and practical home utility review in simple English.\n"
        "3. TARGET LENGTH: Strictly between 300 and 600 characters.\n"
        "4. DO NOT mention price, emojis, links, or repetitive lines. Output purely the description text."
    )

    user_text = f"Product Title: {clean_title}\nBrand: {brand}\nProvide a 300-600 character visual analysis:"

    messages = [
        {"role": "system", "content": system_prompt},
        {
            "role": "user",
            "content": [
                {"type": "text", "text": user_text},
                {"type": "image_url", "image_url": {"url": base64_img}},
            ],
        },
    ]

    print(f"\n🔍 [STAGE 1] Menjalankan Vision OCR/Analysis Bahasa Inggeris (Had: 300-600 aksara)...")
    
    for attempt in range(1, max_retries + 1):
        print(f"   🔄 Percubaan {attempt}/{max_retries}...")
        try:
            start_t = time.time()
            response = vlm.create_chat_completion(
                messages=messages,
                temperature=0.35 + (attempt * 0.05),
                top_p=0.85,
                max_tokens=220,
                repeat_penalty=1.18,
            )
            raw_content = response["choices"][0]["message"]["content"]
            clean_en = scrub_and_clean_text(raw_content)
            
            if 250 <= len(clean_en) <= 650:
                # Simpan metadata & hasil stage 1 ke temp/.json
                payload_json = {
                    "shopee_product_id": str(product_id),
                    "shopee_product_name": product_name,
                    "shopee_brand": brand,
                    "shopee_price": price,
                    "shopee_affiliate_link": affiliate_link,
                    "compressed_image_path": comp_img_path,
                    "english_vision_review": clean_en,
                    "english_char_count": len(clean_en),
                    "stage_1_duration_sec": round(time.time() - start_t, 2),
                    "created_at": time.time()
                }

                with open(json_output_path, "w", encoding="utf-8") as f_json:
                    json.dump(payload_json, f_json, indent=2, ensure_ascii=False)

                print(f"   ✅ [Stage 1 Berjaya] Disimpan ke {json_output_path.name} ({len(clean_en)} aksara)")
                return True, clean_en, str(json_output_path)
            else:
                print(f"   ⚠️ Panjang teks tidak menepati sasaran ({len(clean_en)} aksara).")

        except Exception as e:
            print(f"   ⚠️ [Ralat Stage 1 Execution]: {e}")

        if attempt < max_retries:
            time.sleep(delay_sec)

    return False, "Stage 1 gagal selepas 3 percubaan.", ""


# =============================================================================
# STEP 2: BM PERSONA MAMA ADAPTATION FROM JSON (5X RETRY + FALLBACK)
# =============================================================================
def stage_2_generate_bm_copy_from_json(
    json_file_path: str,
    max_retries: int = 5,
    delay_sec: int = 2
) -> Tuple[str, float, int, str]:
    """
    Membaca data JSON dari Stage 1 dan menjana olahan ulasan Bahasa Melayu Persona Mama 
    (300-600 aksara) merangkumi visual, nama produk dan harga RM.
    """
    vlm = load_local_qwen35_vlm()

    with open(json_file_path, "r", encoding="utf-8") as f_json:
        data = json.load(f_json)

    product_name = data.get("shopee_product_name", "")
    brand = data.get("shopee_brand", "Shopee Preferred")
    price = float(data.get("shopee_price", 0.0))
    en_review = data.get("english_vision_review", "")
    clean_title = re.sub(r"[【】\[\]()_~*#|/\\-]+", " ", product_name).strip()[:50]

    system_prompt = (
        "Anda ialah 'Mama' daripada komuniti 'Impian Rumahku & Cerita Mama' — seorang suri rumah di Malaysia yang mesra, "
        "santai, dan suka berkongsi ulasan barangan rumah praktikal dalam Bahasa Melayu harian tulen.\n\n"
        "TUGASAN:\n"
        "1. Rujuk ulasan visual dan info produk yang diberikan.\n"
        "2. Tulis 1 ulasan santai gaya Mama dalam Bahasa Melayu Malaysia.\n"
        "3. Sebutkan warna/reka bentuk visual, kegunaan praktikal untuk rumah, dan kaitkan dengan nilai harganya (RM).\n"
        "4. SASARAN PANJANG: Tepat antara 300 hingga 550 aksara (sekitar 50-75 patah perkataan).\n\n"
        "PANTANG LARANG:\n"
        "- DILARANG guna istilah Indonesia (jangan guna: abu-abu, kamar mandi, uang, anda, banget, bisa, bikin, gampang).\n"
        "- Gunakan perkataan Melayu: kelabu, bilik air, jimat ruang, kemas elok, senang guna, korang.\n"
        "- DILARANG meletakkan link, hashtag, atau emoji.\n"
        "- Terus berikan teks ulasan tanpa mukadimah."
    )

    user_text = (
        f"Nama Produk: {clean_title}\n"
        f"Jenama: {brand}\n"
        f"Harga: RM{price:.2f}\n"
        f"Pemerhatian Visual (BI): \"{en_review}\"\n\n"
        f"Tulis ulasan santai Persona Mama BM (300-550 aksara):"
    )

    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": user_text},
    ]

    print(f"\n🇲🇾 [STAGE 2] Menjana Olahan BM Persona Mama (5x Percubaan, Sasaran: 300-600 aksara)...")
    start_total_t = time.time()

    for attempt in range(1, max_retries + 1):
        print(f"   🔄 Percubaan {attempt}/{max_retries}...")
        try:
            res = vlm.create_chat_completion(
                messages=messages,
                temperature=0.40 if attempt == 1 else 0.55,
                top_p=0.85,
                max_tokens=220,
                repeat_penalty=1.20,
            )
            raw_text = res["choices"][0]["message"]["content"]
            clean_bm = scrub_and_clean_text(raw_text)
            is_valid, reason = validate_clean_latin_text(clean_bm, min_chars=280, max_chars=600)

            if is_valid:
                elapsed = time.time() - start_total_t
                print(f"   ✅ [Stage 2 Berjaya] Teks sah diterima ({len(clean_bm)} aksara).")
                return clean_bm, elapsed, len(clean_bm), "AI_GENERATED"
            else:
                print(f"   ⚠️ Tidak sah ({attempt}/{max_retries}): {reason}")

        except Exception as e:
            print(f"   ⚠️ [Ralat Stage 2]: {e}")

        if attempt < max_retries:
            time.sleep(delay_sec)

    # Fallback jika 5 percubaan gagal
    print("🛡️ [STAGE 2 FALLBACK] Mengaktifkan penjana ulasan berasaskan peraturan.")
    fallback_text = generate_fallback_mama_text(product_name, brand, price)
    elapsed = time.time() - start_total_t
    return fallback_text, elapsed, len(fallback_text), "RULE_BASED_FALLBACK"