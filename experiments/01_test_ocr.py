import sys
import os

# Memastikan modul src boleh diakses
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

import time
import json
import random
import requests
from dotenv import load_dotenv

from src.ocr_vision_image_reader import analyze_image_to_json, clean_thinking_output

# Muat pembolehubah persekitaran dari .env.local
load_dotenv('.env.local')

UNSPLASH_ACCESS_KEY = os.getenv("IRCM_UNSPLASH_ACCESS_KEY")
OPENROUTER_BASE_URL = os.getenv("IRCM_OPENROUTER_BASE_URL")
OPENROUTER_API_KEY = os.getenv("IRCM_OPENROUTER_API_KEY")

MODELS_TO_TEST = [
    os.getenv("IRCM_MODEL_PRIMARY"),
    os.getenv("IRCM_MODEL_FALLBACK_1"),
    os.getenv("IRCM_MODEL_FALLBACK_2")
]

OUTPUT_DIR = "/home/braderdin/Impian-Rumahku-Bot/experiments/unsplash_output/"

def fetch_unsplash_images():
    """Meminta senarai gambar bertemakan Home Decor & Living dari Unsplash."""
    print("[+] Meminta gambar bertemakan Home Decor dari Unsplash...")
    if not UNSPLASH_ACCESS_KEY:
        raise ValueError("[RALAT] IRCM_UNSPLASH_ACCESS_KEY tidak ditemui dalam .env.local!")

    url = "https://api.unsplash.com/photos/random"
    headers = {
        "Authorization": f"Client-ID {UNSPLASH_ACCESS_KEY}"
    }
    params = {
        "count": 10,
        "query": "home decor interior minimalist kitchen cozy room"
    }

    try:
        response = requests.get(url, headers=headers, params=params, timeout=30)
        if response.status_code == 200:
            print("  [Berjaya] Berjaya menarik gambar dari Unsplash.")
            return response.json()
        else:
            print(f"  [Ralat Unsplash] Status {response.status_code}: {response.text}")
            return []
    except Exception as e:
        print(f"  [Ralat Sambungan] Gagal berhubung dengan Unsplash API: {e}")
        return []

def download_and_save_image(photo_obj):
    """Menyimpan 1 gambar pilihan ke folder output."""
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    image_url = photo_obj['urls']['regular']
    photo_id = photo_obj['id']
    file_path = os.path.join(OUTPUT_DIR, f"unsplash_{photo_id}.jpg")
    
    print(f"[+] Memuat turun 1 gambar pilihan (ID: {photo_id})...")
    try:
        img_res = requests.get(image_url, timeout=30)
        if img_res.status_code == 200:
            with open(file_path, 'wb') as f:
                f.write(img_res.content)
            print(f"  [Simpan] Fail gambar disimpan di: {file_path}")
        else:
            print(f"  [Amaran] Gagal memuat turun fail fizikal. Status: {img_res.status_code}")
    except Exception as e:
        print(f"  [Ralat] Gagal menyimpan imej: {e}")
        
    return image_url

def main():
    print("==================================================")
    print("  UJIAN INTEGRASI (VISION ENGLISH -> PERSONA BM)  ")
    print("==================================================")

    # 1. Tarik gambar dari Unsplash
    photos = fetch_unsplash_images()
    if not photos:
        print("❌ Tiada gambar diperoleh. Ujian dihentikan.")
        return

    # 2. Pilih 1 gambar sahaja
    selected_photo = random.choice(photos)
    image_url = download_and_save_image(selected_photo)
    product_name = "Inspirasi Dekorasi & Ruang Kediaman Selesa"

    # 3. Jalankan Modul Vision (Output JSON Bahasa Inggeris)
    try:
        json_filepath = analyze_image_to_json(image_url, product_name=product_name)
    except Exception as e:
        print(f"❌ Ralat semasa analisis Vision: {e}")
        return

    # 4. Baca data JSON rujukan
    if not os.path.exists(json_filepath):
        print(f"❌ Fail JSON tidak ditemui di laluan: {json_filepath}")
        return

    with open(json_filepath, 'r', encoding='utf-8') as f:
        vision_data = json.load(f)

    headers_openrouter = {
        "Authorization": f"Bearer {OPENROUTER_API_KEY}",
        "Content-Type": "application/json"
    }

    valid_models = [m for m in MODELS_TO_TEST if m]
    if not valid_models:
        print("❌ Tiada model Persona AI dikonfigurasi dalam fail persekitaran!")
        return

    # 5. Model Teks Persona AI menterjemah & mengarang dalam Bahasa Melayu
    for m_idx, model_name in enumerate(valid_models):
        print(f"\n--- [Model {m_idx+1}/{len(valid_models)}] Menguji Model Persona: {model_name} ---")
        
        success = False
        final_output = ""

        for attempt in range(1, 3):
            try:
                persona_system_prompt = (
                    "Anda adalah 'Mama', seorang suri rumah dan pencipta kandungan media sosial di Malaysia untuk "
                    "'Impian Rumahku & Cerita Mama'. Perwatakan anda sangat mesra, suka bercerita santai (storytelling), "
                    "dan menggunakan gaya bahasa harian Malaysia yang meyakinkan ('korang', 'memang best', 'cantik sangat', 'kemas betul').\n\n"
                    "Tugasan anda:\n"
                    "Baca data analisis visual (JSON dalam Bahasa Inggeris) yang diberikan, kemudian ubah maklumat tersebut "
                    "menjadi hantaran promosi media sosial dalam BAHASA MELAYU MALAYSIA TULEN seolah-olah anda sendiri yang menghias ruang itu.\n\n"
                    "PERINGATAN KRITIKAL:\n"
                    "1. Panjang teks WAJIB di antara 500 hingga 750 aksara sahaja (termasuk ruang kosong). Jangan kurang dan jangan lebih.\n"
                    "2. Gunakan Bahasa Melayu Malaysia sepenuhnya. Elakkan penggunaan perkataan bahasa serantau luar.\n"
                    "3. Selitkan cadangan mencari barangan deko berkaitan di Shopee secara natural.\n"
                    "4. Berikan teks hantaran terus tanpa sebarang proses pemikiran (thinking tag) atau teks pembuka."
                )

                user_prompt = (
                    f"Rujuk data analisis visual bilik (JSON) berikut dan hasilkan kapsyen promosi media sosial:\n"
                    f"{json.dumps(vision_data.get('visual_analysis_en', {}), ensure_ascii=False, indent=2)}\n\n"
                    f"Pastikan panjang teks tepat di antara 500 hingga 750 aksara."
                )

                payload = {
                    "model": model_name,
                    "messages": [
                        {"role": "system", "content": persona_system_prompt},
                        {"role": "user", "content": user_prompt}
                    ]
                }

                response = requests.post(OPENROUTER_BASE_URL, headers=headers_openrouter, json=payload, timeout=60)
                
                if response.status_code == 200:
                    res_json = response.json()
                    raw_content = res_json['choices'][0]['message']['content']
                    final_output = clean_thinking_output(raw_content)
                    success = True
                    break
                else:
                    print(f"  [Amaran] Cubaan {attempt} gagal (Status {response.status_code}): {response.text}")
            except Exception as e:
                print(f"  [Ralat] Percubaan {attempt}: {e}")
            
            if attempt < 2:
                time.sleep(1)

        if success:
            print(f"  [Berjaya] Output daripada model {model_name}:")
            print("~" * 60)
            print(final_output)
            print("~" * 60)
            print(f"  📏 Jumlah Aksara: {len(final_output)} (Sasaran Ketat: 500-750 aksara)")
        else:
            print(f"  [Gagal] Model {model_name} tidak membalas.")

        print("  ⏳ Jeda 1 saat...")
        time.sleep(1)

    print("\n==================================================")
    print("             UJIAN 1 GAMBAR SELESAI               ")
    print("==================================================")

if __name__ == "__main__":
    main()