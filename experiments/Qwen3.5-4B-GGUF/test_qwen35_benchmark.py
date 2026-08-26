#!/usr/bin/env python3
"""
Eksperimen Benchmark Had Selamat Qwen3.5-4B-GGUF (Vision + Reasoning + BM + 16K Context/Output)
Lokasi: experiments/Qwen3.5-4B-GGUF/test_qwen35_benchmark.py
"""

import os
import sys
import json
import time
import uuid
import base64
import psutil
import requests
from io import BytesIO
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple
from PIL import Image
from dotenv import load_dotenv

# 1. Setup Root Path & Environment
PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

env_local = PROJECT_ROOT / ".env.local"
if env_local.exists():
    load_dotenv(dotenv_path=env_local)
else:
    load_dotenv()

TEMP_DIR = PROJECT_ROOT / "temp"
TEMP_DIR.mkdir(parents=True, exist_ok=True)

# Parameter Model
REPO_ID = "unsloth/Qwen3.5-4B-GGUF"
MODEL_FILENAME = "Qwen3.5-4B-Q4_K_M.gguf"
MMPROJ_FILENAME = "mmproj-F16.gguf"

# Tetapan Ujian Context & Output
TEST_CONTEXT_WINDOW = 16000
TEST_MAX_OUTPUT_TOKENS = 16000
KV_CACHE_TYPE_Q8 = 8  # GGML_TYPE_Q8_0 untuk K dan V


def get_system_memory_report() -> Dict[str, str]:
    """Membaca penggunaan RAM fizikal dan Swap semasa."""
    mem = psutil.virtual_memory()
    swap = psutil.swap_memory()
    return {
        "ram_total": f"{mem.total / (1024**3):.2f} GB",
        "ram_used": f"{mem.used / (1024**3):.2f} GB ({mem.percent}%)",
        "ram_available": f"{mem.available / (1024**3):.2f} GB",
        "swap_total": f"{swap.total / (1024**3):.2f} GB",
        "swap_used": f"{swap.used / (1024**3):.2f} GB ({swap.percent}%)",
        "swap_free": f"{swap.free / (1024**3):.2f} GB"
    }


def print_memory_log(stage_name: str):
    """Mencetak status memori untuk debugging GitHub Actions."""
    stats = get_system_memory_report()
    print(f"\n📊 [MEMORY LOG | {stage_name}]")
    print(f"   🔹 RAM  : {stats['ram_used']} / {stats['ram_total']} (Baki: {stats['ram_available']})")
    print(f"   🔹 SWAP : {stats['swap_used']} / {stats['swap_total']} (Baki: {stats['swap_free']})")
    print("-" * 65)


def fetch_and_prepare_4_images() -> List[Dict[str, Any]]:
    """
    Menarik 40 imej daripada Unsplash dalam 1 request, memilih 4 imej, 
    dan memampatkan setiap imej kepada < 40KB Base64.
    """
    unsplash_key = os.getenv("IRCM_UNSPLASH_ACCESS_KEY", "").strip() or os.getenv("UNSPLASH_ACCESS_KEY", "").strip()
    if not unsplash_key:
        print("⚠️ [UNSPLASH] Kunci IRCM_UNSPLASH_ACCESS_KEY tiada. Menggunakan imej placeholder sintetik.")
        return generate_synthetic_benchmark_images(4)

    url = "https://api.unsplash.com/search/photos"
    params = {
        "query": "malaysian home kitchen plants interior",
        "per_page": 40,
        "page": 1,
        "client_id": unsplash_key
    }

    print("📡 [UNSPLASH] Menghantar 1 request untuk menarik 40 data imej...")
    try:
        res = requests.get(url, params=params, timeout=20)
        if res.status_code != 200:
            print(f"⚠️ [UNSPLASH ERROR] HTTP {res.status_code}: {res.text}")
            return generate_synthetic_benchmark_images(4)

        results = res.json().get("results", [])
        if len(results) < 4:
            return generate_synthetic_benchmark_images(4)

        selected_4 = results[:4]
        prepared_images = []

        for idx, item in enumerate(selected_4, 1):
            img_url = item.get("urls", {}).get("regular") or item.get("urls", {}).get("small")
            img_res = requests.get(img_url, timeout=15)
            
            if img_res.status_code == 200:
                # Mampatkan ke bawah 40KB
                b64_str, size_kb = compress_bytes_to_b64(img_res.content, max_kb=40)
                prepared_images.append({
                    "id": item.get("id", f"img_{idx}"),
                    "desc": item.get("alt_description") or "Visual hiasan rumah",
                    "size_kb": size_kb,
                    "b64": b64_str
                })
                print(f"   🖼️ Gambar #{idx} dimampatkan: {size_kb:.2f} KB (ID: {item.get('id')})")

        return prepared_images if len(prepared_images) == 4 else generate_synthetic_benchmark_images(4)

    except Exception as e:
        print(f"⚠️ [UNSPLASH EXCEPTION] {e}")
        return generate_synthetic_benchmark_images(4)


def compress_bytes_to_b64(raw_bytes: bytes, max_kb: int = 40) -> Tuple[str, float]:
    """Memampatkan data gambar kepada JPEG < 40KB dan menukar ke Base64 Data URL."""
    img = Image.open(BytesIO(raw_bytes))
    if img.mode in ("RGBA", "P"):
        img = img.convert("RGB")

    img.thumbnail((480, 480), Image.Resampling.LANCZOS)
    quality = 75

    while quality >= 15:
        buf = BytesIO()
        img.save(buf, format="JPEG", quality=quality, optimize=True)
        size_kb = len(buf.getvalue()) / 1024.0
        if size_kb <= max_kb or quality <= 15:
            b64 = base64.b64encode(buf.getvalue()).decode("utf-8")
            return f"data:image/jpeg;base64,{b64}", size_kb
        quality -= 10
        if quality < 45:
            img.thumbnail((int(img.width * 0.85), int(img.height * 0.85)), Image.Resampling.LANCZOS)

    b64 = base64.b64encode(buf.getvalue()).decode("utf-8")
    return f"data:image/jpeg;base64,{b64}", size_kb


def generate_synthetic_benchmark_images(count: int = 4) -> List[Dict[str, Any]]:
    """Sandaran sintetik sekiranya API Unsplash tidak tersedia."""
    print("🎨 Menjana 4 imej sintetik di bawah 40KB untuk pengujian...")
    images = []
    colors = [(180, 80, 80), (80, 180, 80), (80, 80, 180), (180, 180, 80)]
    for i in range(count):
        img = Image.new("RGB", (320, 320), color=colors[i % len(colors)])
        buf = BytesIO()
        img.save(buf, format="JPEG", quality=60)
        size_kb = len(buf.getvalue()) / 1024.0
        b64 = base64.b64encode(buf.getvalue()).decode("utf-8")
        images.append({
            "id": f"synthetic_{i+1}",
            "desc": f"Synthetic Test Canvas {i+1}",
            "size_kb": size_kb,
            "b64": f"data:image/jpeg;base64,{b64}"
        })
    return images


def send_telegram_audit_report(report_data: Dict[str, Any]):
    """Menghantar laporan audit terperinci ke Telegram."""
    bot_token = os.getenv("IRCM_TELEGRAM_BOT_TOKEN", "").strip()
    chat_id = os.getenv("IRCM_TELEGRAM_CHAT_ID", "").strip()

    if not bot_token or not chat_id:
        print("⚠️ [TELEGRAM] Token atau Chat ID tiada. Laporan Telegram dilangkau.")
        return

    status_icon = "✅ BERJAYA" if report_data.get("status") == "SUCCESS" else "❌ GAGAL"
    
    msg_text = (
        f"🧪 <b>LAPORAN BENCHMARK QWEN3.5-4B GGUF</b>\n"
        f"━━━━━━━━━━━━━━━━━━━━━━\n"
        f"<b>Status:</b> {status_icon}\n"
        f"<b>Model:</b> {MODEL_FILENAME}\n"
        f"<b>Vision Handler:</b> {MMPROJ_FILENAME}\n"
        f"<b>Context Window Ditetapkan:</b> {TEST_CONTEXT_WINDOW:,} Tokens\n"
        f"<b>Max Output Token:</b> {TEST_MAX_OUTPUT_TOKENS:,} Tokens\n"
        f"<b>KV Cache:</b> Q8_0 (8-bit Quantized)\n"
        f"<b>Reasoning Mode:</b> Aktif (<think>)\n"
        f"━━━━━━━━━━━━━━━━━━━━━━\n"
        f"⏱️ <b>Masa Model Loading:</b> {report_data.get('load_time_sec', 0):.2f}s\n"
        f"⏱️ <b>Masa Inferens:</b> {report_data.get('inference_time_sec', 0):.2f}s\n"
        f"📊 <b>Token Dijana:</b> {report_data.get('tokens_generated', 0)} Tokens\n"
        f"⚡ <b>Kelajuan:</b> {report_data.get('tokens_per_sec', 0):.2f} Tok/s\n"
        f"━━━━━━━━━━━━━━━━━━━━━━\n"
        f"💾 <b>Puncak Penggunaan Memori:</b>\n"
        f"• RAM: {report_data.get('ram_used_peak', 'N/A')}\n"
        f"• Swap: {report_data.get('swap_used_peak', 'N/A')}\n"
        f"━━━━━━━━━━━━━━━━━━━━━━\n"
        f"📁 <b>Fail JSON Hasil:</b> <code>{report_data.get('json_file', 'N/A')}</code>\n"
    )

    url = f"https://api.telegram.org/bot{bot_token}/sendMessage"
    payload = {
        "chat_id": chat_id,
        "text": msg_text,
        "parse_mode": "HTML"
    }

    try:
        res = requests.post(url, json=payload, timeout=15)
        if res.status_code == 200:
            print("📲 [TELEGRAM] Laporan audit berjaya dihantar ke Telegram!")
        else:
            print(f"⚠️ [TELEGRAM HTTP {res.status_code}] {res.text}")
    except Exception as e:
        print(f"⚠️ [TELEGRAM ERROR] {e}")


def run_benchmark():
    """Fungsi utama pelaksanaan benchmark."""
    print("=" * 70)
    print("🚀 MEMULAKAN BENCHMARK: QWEN3.5-4B GGUF (16K CTX / 16K OUT / Q8 KV)")
    print("=" * 70)

    print_memory_log("SEBELUM MODEL DIMUATKAN")

    # 1. Muat Turun / Semak Fail Model
    from huggingface_hub import hf_hub_download
    from llama_cpp import Llama
    from llama_cpp.llama_chat_format import Qwen2VLChatHandler

    t0_load = time.time()
    print(f"📥 Memuat turun / memuatkan {MODEL_FILENAME} & {MMPROJ_FILENAME}...")
    model_path = hf_hub_download(repo_id=REPO_ID, filename=MODEL_FILENAME, local_files_only=False)
    mmproj_path = hf_hub_download(repo_id=REPO_ID, filename=MMPROJ_FILENAME, local_files_only=False)

    # 2. Inisialisasi Vision Handler & Model Llama
    chat_handler = Qwen2VLChatHandler(clip_model_path=mmproj_path)

    print(f"⚙️ Mengkonfigurasi Llama: n_ctx={TEST_CONTEXT_WINDOW}, type_k=8 (Q8), type_v=8 (Q8), flash_attn=True...")
    llm = Llama(
        model_path=model_path,
        chat_handler=chat_handler,
        n_ctx=TEST_CONTEXT_WINDOW,
        n_threads=2,          # Sesuai untuk GitHub Actions 2-Core vCPU
        n_batch=512,
        type_k=KV_CACHE_TYPE_Q8,
        type_v=KV_CACHE_TYPE_Q8,
        flash_attn=True,
        verbose=True
    )
    load_duration = time.time() - t0_load
    print(f"✅ Model berjaya dimuatkan dalam masa {load_duration:.2f} saat.")
    print_memory_log("SELEPAS MODEL DIMUATKAN (KV CACHE DISEDIAKAN)")

    # 3. Sediakan 4 Imej Unsplash
    images_payload = fetch_and_prepare_4_images()
    print_memory_log("SELEPAS 4 GAMBAR DIPROSES")

    # 4. Bina Kandungan Mesej
    system_prompt = (
        "Anda ialah pakar analisis visual dan gaya hidup harian di Malaysia. "
        "Tugasan anda adalah meneliti gambar-gambar yang diberikan dan membina penilaian terperinci "
        "dalam Bahasa Melayu tulen. Berikan penaakulan yang mendalam dan hasilkan struktur JSON yang lengkap."
    )

    user_content_list: List[Dict[str, Any]] = [
        {
            "type": "text",
            "text": (
                "Sila teliti keempat-empat gambar yang disertakan di bawah. "
                "Lakukan analisis mendalam terhadap susun atur, suasana, praktikaliti untuk suri rumah di Malaysia, "
                "dan elemen estetik. Janakan output akhir dalam format JSON yang mengandungi kunci: "
                "'analisis_keseluruhan', 'penilaian_setiap_gambar' (senarai 4 item), 'cadangan_praktikal_bm', "
                "dan 'skor_estetik_10'."
            )
        }
    ]

    for img_item in images_payload:
        user_content_list.append({
            "type": "image_url",
            "image_url": {"url": img_item["b64"]}
        })

    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": user_content_list}
    ]

    print("\n🧠 Memulakan inferens dengan mod Reasoning Aktif (Sampling: temp=1.0, top_p=0.95)...")
    t0_infer = time.time()
    
    audit_data: Dict[str, Any] = {
        "status": "FAILED",
        "load_time_sec": load_duration,
        "inference_time_sec": 0,
        "tokens_generated": 0,
        "tokens_per_sec": 0,
        "ram_used_peak": "N/A",
        "swap_used_peak": "N/A",
        "json_file": "N/A"
    }

    try:
        # Parameter rasmi Qwen3.5 untuk mod reasoning
        response = llm.create_chat_completion(
            messages=messages,
            temperature=1.0,
            top_p=0.95,
            top_k=20,
            presence_penalty=1.5,
            repeat_penalty=1.0,
            max_tokens=TEST_MAX_OUTPUT_TOKENS,
        )

        infer_duration = time.time() - t0_infer
        raw_output = response["choices"][0]["message"]["content"]
        usage_info = response.get("usage", {})
        completion_tokens = usage_info.get("completion_tokens", len(raw_output.split()))
        tok_per_sec = completion_tokens / infer_duration if infer_duration > 0 else 0

        print(f"\n🎉 [INFERENS SELESAI] Masa: {infer_duration:.2f}s | Token: {completion_tokens} | Kelajuan: {tok_per_sec:.2f} tok/s")
        print_memory_log("KEMUNCAK SELEPAS INFERENS")

        # 5. Simpan Hasil JSON Unik
        unique_id = f"{int(time.time())}_{uuid.uuid4().hex[:6]}"
        output_json_path = TEMP_DIR / f"qwen35_benchmark_{unique_id}.json"

        result_payload = {
            "benchmark_meta": {
                "timestamp": int(time.time()),
                "model": MODEL_FILENAME,
                "context_window_setting": TEST_CONTEXT_WINDOW,
                "max_output_setting": TEST_MAX_OUTPUT_TOKENS,
                "kv_cache": "Q8_0",
                "load_time_sec": load_duration,
                "inference_time_sec": infer_duration,
                "tokens_generated": completion_tokens,
                "tokens_per_second": tok_per_sec
            },
            "images_evaluated": [
                {"id": x["id"], "desc": x["desc"], "size_kb": x["size_kb"]} for x in images_payload
            ],
            "raw_response": raw_output
        }

        with open(output_json_path, "w", encoding="utf-8") as f_out:
            json.dump(result_payload, f_out, indent=2, ensure_ascii=False)

        print(f"💾 [HASIL DISIMPAN] Fail JSON: {output_json_path}")

        # Kemas kini data audit
        mem_peak = get_system_memory_report()
        audit_data.update({
            "status": "SUCCESS",
            "inference_time_sec": infer_duration,
            "tokens_generated": completion_tokens,
            "tokens_per_sec": tok_per_sec,
            "ram_used_peak": mem_peak["ram_used"],
            "swap_used_peak": mem_peak["swap_used"],
            "json_file": str(output_json_path.name)
        })

    except Exception as e:
        print(f"\n❌ [RALAT INFERENS GGUF]: {e}")
        mem_peak = get_system_memory_report()
        audit_data.update({
            "status": "FAILED",
            "ram_used_peak": mem_peak["ram_used"],
            "swap_used_peak": mem_peak["swap_used"],
            "error_msg": str(e)
        })

    finally:
        # 6. Hantar Laporan ke Telegram
        send_telegram_audit_report(audit_data)
        print("=" * 70)


if __name__ == "__main__":
    run_benchmark()