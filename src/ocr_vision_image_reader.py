import os
import time
import json
import re
import requests
from dotenv import load_dotenv

# Muat pembolehubah persekitaran dari .env.local
load_dotenv('.env.local')

OPENROUTER_BASE_URL = os.getenv("IRCM_OPENROUTER_BASE_URL")
OPENROUTER_API_KEY = os.getenv("IRCM_OPENROUTER_API_KEY")
VISION_MODEL = os.getenv("IRCM_MODEL_VISION")

TEMP_DIR = "temp/"

def clean_thinking_output(text):
    """Tapis dan buang blok pemikiran (thinking/reasoning) model AI."""
    if not text:
        return ""
    text = re.sub(r'<think>.*?</think>', '', text, flags=re.DOTALL)
    return text.strip()

def analyze_image_to_json(image_url, product_name="Home Decor Inspiration"):
    """
    Menghantar URL gambar ke model Vision OpenRouter.
    Menjana huraian visual terperinci dalam format JSON berstruktur (Bahasa Inggeris).
    """
    print(f"\n[+] Menjalankan Model Vision ({VISION_MODEL})...")
    
    if not OPENROUTER_BASE_URL or not OPENROUTER_API_KEY or not VISION_MODEL:
        raise ValueError("[RALAT] Konfigurasi OpenRouter atau Model Vision tidak lengkap dalam persekitaran!")

    os.makedirs(TEMP_DIR, exist_ok=True)
    timestamp = int(time.time())
    json_filename = os.path.join(TEMP_DIR, f"vision_analysis_{timestamp}.json")

    headers = {
        "Authorization": f"Bearer {OPENROUTER_API_KEY}",
        "Content-Type": "application/json"
    }

    # Prompt Vision dalam Bahasa Inggeris untuk ketepatan analisis objek & suasana
    vision_system_prompt = (
        "You are an expert visual interior analyst. Analyze the provided image and generate a rich, accurate "
        "description in a strict valid JSON format. "
        "Your JSON output MUST strictly include these fields:\n"
        "- main_subject_and_focus: The primary object, furniture, or area in focus.\n"
        "- surrounding_elements_and_background: Details on layout, secondary decor items, and room setup.\n"
        "- ocr_detected_text: Any readable brand names, labels, or text visible in the image (or 'None').\n"
        "- lighting_color_and_ambiance: Lighting sources (natural/warm), dominant color palette, and room mood.\n"
        "- materials_and_textures: Distinct surfaces and materials (e.g., solid wood, matte metal, linen fabric, ceramic, glass).\n"
        "Return ONLY the valid JSON object without any extra conversational text or markdown codeblocks."
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
                        "text": f"Please perform a deep visual breakdown for this image referencing: {product_name}"
                    },
                    {
                        "type": "image_url",
                        "image_url": {"url": image_url}
                    }
                ]
            }
        ]
    }

    vision_analysis_raw = "{}"
    success = False

    for attempt in range(1, 3):
        try:
            print(f"  [Cuba {attempt}/2] Menghantar permintaan analisis ke OpenRouter API...")
            response = requests.post(OPENROUTER_BASE_URL, headers=headers, json=vision_payload, timeout=60)
            
            if response.status_code == 200:
                res_json = response.json()
                raw_content = res_json['choices'][0]['message']['content']
                vision_analysis_raw = clean_thinking_output(raw_content)
                success = True
                print("  [Berjaya] Analisis visual Bahasa Inggeris berjaya diterima.")
                break
            else:
                print(f"  [Amaran] Percubaan {attempt} gagal (Status {response.status_code}): {response.text}")
        except Exception as e:
            print(f"  [Ralat] Percubaan {attempt}: {e}")
        
        if attempt < 2:
            time.sleep(2)

    try:
        parsed_vision = json.loads(vision_analysis_raw)
    except Exception:
        parsed_vision = {"raw_description": vision_analysis_raw}

    final_json_data = {
        "product_name": product_name,
        "image_url": image_url,
        "vision_model_used": VISION_MODEL,
        "visual_analysis_en": parsed_vision,
        "analyzed_at": time.strftime("%Y-%m-%d %H:%M:%S")
    }

    with open(json_filename, 'w', encoding='utf-8') as f:
        json.dump(final_json_data, f, ensure_ascii=False, indent=4)
    
    print(f"  [Simpan] Fail JSON analisis disimpan di: {json_filename}")
    return json_filename