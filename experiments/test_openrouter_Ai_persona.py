import os
import time
import json
import random
import re
import requests
from dotenv import load_dotenv

# Muat pembolehubah persekitaran dari .env.local
load_dotenv('.env.local')

SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_SERVICE_ROLE_KEY") or os.getenv("SUPABASE_ANON_KEY")

OPENROUTER_BASE_URL = os.getenv("OPENROUTER_BASE_URL")
OPENROUTER_API_KEY = os.getenv("OPENROUTER_API_KEY")

VISION_MODEL = os.getenv("OPENROUTER_MODEL_VISION")
TEST_MODELS = [
    os.getenv("OPENROUTER_MODEL_TEST01"),
    os.getenv("OPENROUTER_MODEL_TEST02"),
    os.getenv("OPENROUTER_MODEL_TEST03")
]

TEMP_DIR = "/home/braderdin/Sembang-PC-Tech-Bot/temp/"

def fetch_supabase_products():
    """Tarik 50 produk dari Supabase tanpa usik data asal."""
    url = f"{SUPABASE_URL}/rest/v1/shopee_affiliate_links?select=id,shopee_product_id,shopee_product_name,shopee_price,shopee_picture_url,shopee_product_url,shopee_affiliate_link&limit=50"
    headers = {
        "apikey": SUPABASE_KEY,
        "Authorization": f"Bearer {SUPABASE_KEY}"
    }
    response = requests.get(url, headers=headers)
    if response.status_code == 200:
        return response.json()
    else:
        raise Exception(f"Gagal menarik data dari Supabase: {response.text}")

def clean_thinking_output(text):
    """Tapis dan buang blok pemikiran (thinking/reasoning) model."""
    if not text:
        return ""
    text = re.sub(r'<think>.*?</think>', '', text, flags=re.DOTALL)
    return text.strip()

def main():
    print("🚀 Memulakan ujian AI Persona OpenRouter (Universal Vision & Local Copywriting)...")
    
    # 1. Tarik 50 produk dari Supabase
    products = fetch_supabase_products()
    if not products:
        print("❌ Tiada produk ditemui dalam pangkalan data Supabase.")
        return
    
    # 2. Pilih 1 produk secara rawak
    product = random.choice(products)
    print(f"📦 Produk Dipilih -> ID: {product['id']} | Tajuk: {product['shopee_product_name']}")
    
    os.makedirs(TEMP_DIR, exist_ok=True)
    json_filename = os.path.join(TEMP_DIR, f"product_analysis_{product['id']}.json")
    
    headers = {
        "Authorization": f"Bearer {OPENROUTER_API_KEY}",
        "Content-Type": "application/json"
    }
    
    # 3. Model Vision menjana huraian visual universal dalam Bahasa Melayu Malaysia tulen
    print(f"\n🔍 Menjalankan Model Vision ({VISION_MODEL}) untuk analisis visual universal...")
    vision_analysis_raw = "{}"
    
    if VISION_MODEL:
        for attempt in range(1, 3):
            try:
                vision_system_prompt = (
                    "Anda adalah pakar analisis visual profesional. Sila teliti gambar yang diberikan dan berikan huraian mendalam "
                    "dalam format JSON universal. Gunakan BAHASA MELAYU MALAYSIA TULEN sepenuhnya. "
                    "DILARANG SAMA SEKALI menggunakan terma atau ejaan bahasa Indonesia (contoh: wajib guna 'kelabu' bukan 'abu', "
                    "'jenama' bukan 'marca', 'pengecasan' bukan 'pengchargahan', 'peranti' bukan 'perangkat'). "
                    "Format JSON anda WAJIB merangkumi:\n"
                    "- subjek_utama_dan_fokus: Objek atau perkara paling penting dalam gambar.\n"
                    "- elemen_dan_objek_sekitar: Kedudukan objek lain dan latar belakang.\n"
                    "- teks_yang_dikesan_ocr: Segala perkataan atau tulisan yang kelihatan pada gambar.\n"
                    "- suasana_dan_estetika: Pencahayaan, warna, dan mood gambar.\n"
                    "- butiran_fizikal_atau_tekstur: Permukaan, bahan, atau bentuk fizikal objek.\n"
                    "Berikan output dalam bentuk struktur JSON yang sah sahaja tanpa teks tambahan."
                )

                vision_payload = {
                    "model": VISION_MODEL,
                    "messages": [
                        {"role": "system", "content": vision_system_prompt},
                        {
                            "role": "user",
                            "content": [
                                {
                                    "type": "text",
                                    "text": f"Sila analisis visual gambar ini untuk rujukan produk: {product['shopee_product_name']}"
                                },
                                {
                                    "type": "image_url",
                                    "image_url": {"url": product['shopee_picture_url']}
                                }
                            ]
                        }
                    ]
                }
                
                response = requests.post(OPENROUTER_BASE_URL, headers=headers, json=vision_payload, timeout=60)
                if response.status_code == 200:
                    res_json = response.json()
                    raw_content = res_json['choices'][0]['message']['content']
                    vision_analysis_raw = clean_thinking_output(raw_content)
                    print("✅ Analisis visual universal berjaya dijana oleh Model Vision.")
                    break
                else:
                    print(f"⚠️ Percubaan Vision {attempt} gagal (Status {response.status_code}): {response.text}")
            except Exception as e:
                print(f"⚠️ Ralat Vision cubaan {attempt}: {e}")
            
            time.sleep(1)

    # Cuba parse huraian JSON dari vision, jika gagal simpan sebagai teks biasa
    try:
        parsed_vision = json.loads(vision_analysis_raw)
    except Exception:
        parsed_vision = {"huraian_mentah": vision_analysis_raw}

    # 4. Simpan struktur data lengkap ke dalam fail .json sementara
    final_json_data = {
        "product_id": product['id'],
        "shopee_product_id": product.get('shopee_product_id'),
        "title": product['shopee_product_name'],
        "price": product['shopee_price'],
        "image_url": product['shopee_picture_url'],
        "affiliate_link": product['shopee_affiliate_link'],
        "universal_image_analysis": parsed_vision,
        "analyzed_at": time.strftime("%Y-%m-%d %H:%M:%S")
    }
    
    with open(json_filename, 'w', encoding='utf-8') as f:
        json.dump(final_json_data, f, ensure_ascii=False, indent=4)
    print(f"📁 Fail .json sementara dikemaskini di: {json_filename}")
    
    # 5. Ujian model teks (Test 1, 2, 3) bertindak sebagai Content Creator Malaysia
    valid_test_models = [m for m in TEST_MODELS if m]
    
    for idx, model_name in enumerate(valid_test_models):
        print(f"\n--- Menguji Model Persona [{idx+1}/{len(valid_test_models)}]: {model_name} ---")
        
        success = False
        final_output = ""
        
        for attempt in range(1, 3):
            try:
                with open(json_filename, 'r', encoding='utf-8') as jf:
                    loaded_json_data = json.load(jf)

                persona_system_prompt = (
                    "Anda adalah seorang content creator dan pemasar media sosial profesional di Malaysia yang mesra, "
                    "pandai bercerita (storytelling), dan menggunakan gaya bahasa tempatan Malaysia yang santai serta meyakinkan "
                    "(seperti penggunaan gaya 'korang', 'memang best', 'rugi tak sambar'). "
                    "Tugas anda adalah membaca data produk dan analisis visual universal (JSON) yang disediakan, kemudian "
                    "ubah maklumat itu menjadi hantaran promosi media sosial yang sangat menarik seolah-olah anda sendiri yang guna produk tersebut.\n\n"
                    "PERINGATAN KRITIKAL:\n"
                    "1. Panjang teks WAJIB di antara 500 hingga 750 aksara sahaja (termasuk ruang kosong). Jangan kurang dan jangan lebih.\n"
                    "2. Gunakan Bahasa Melayu Malaysia yang natural dan moden sepenuhnya. Elakkan sama sekali gaya bahasa serantau luar.\n"
                    "3. Sertakan pautan affiliate yang diberikan dengan cara yang sangat menarik di bahagian akhir atau tengah ayat.\n"
                    "4. Berikan jawapan akhir secara terus tanpa sebarang proses pemikiran (thinking) di dalam teks output."
                )

                user_prompt = (
                    f"Sila rujuk data lengkap produk dan huraian visual berikut untuk membina hantaran promosi media sosial:\n"
                    f"{json.dumps(loaded_json_data, ensure_ascii=False, indent=2)}\n"
                    f"Pastikan panjang teks tepat antara 500 hingga 750 aksara."
                )

                payload = {
                    "model": model_name,
                    "messages": [
                        {"role": "system", "content": persona_system_prompt},
                        {"role": "user", "content": user_prompt}
                    ]
                }
                
                response = requests.post(OPENROUTER_BASE_URL, headers=headers, json=payload, timeout=60)
                
                if response.status_code == 200:
                    res_json = response.json()
                    raw_content = res_json['choices'][0]['message']['content']
                    final_output = clean_thinking_output(raw_content)
                    success = True
                    break
                else:
                    print(f"⚠️ Percubaan {attempt} gagal (Status {response.status_code}): {response.text}")
            except Exception as e:
                print(f"⚠️ Ralat pada percubaan {attempt}: {e}")
            
            if attempt < 2:
                time.sleep(1)
        
        if success:
            print(f"✅ Berjaya dari model {model_name}:")
            print("~" * 60)
            print(final_output)
            print("~" * 60)
            print(f"📏 Jumlah Aksara: {len(final_output)} (Sasaran Ketat: 500-750 aksara)")
        else:
            print(f"❌ Gagal mendapatkan respons selepas 2 cubaan untuk model {model_name}")
            
        print("⏳ Delay 1 saat sebelum beralih ke model seterusnya...")
        time.sleep(1)

if __name__ == "__main__":
    main()