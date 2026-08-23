#!/usr/bin/env python3
"""
Shopee Auto-Poster Pipeline: Step 2 Runner (Vision & English Persona Review)
Location: bin/run_shopee_ocr_vison_reader.py
"""

import sys
import json
from pathlib import Path

# Setup Project Root Path
PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

# Import Enjin Teras Vision dari src/
from src.shopee_ocr_vision_reader import analyze_product_image_with_vision

TEMP_DIR = PROJECT_ROOT / "temp"
PAYLOAD_FILE = TEMP_DIR / "shopee_payload.json"
VISION_OCR_FILE = TEMP_DIR / "shopee_vision_ocr.json"


def run_vision_step():
    print("\n" + "=" * 75)
    print("👁️ [STEP 2] MENJALANKAN ENJIN VISION MAMA ENGLISH (OPENROUTER)")
    print("=" * 75)

    if not PAYLOAD_FILE.exists():
        print(f"❌ [ABORT] Fail payload '{PAYLOAD_FILE.name}' tiada. Sila jalankan Step 1 dahulu.")
        sys.exit(1)

    with open(PAYLOAD_FILE, "r", encoding="utf-8") as f:
        payload = json.load(f)

    # Jalankan analisis penglihatan menggunakan enjin src/
    vision_result = analyze_product_image_with_vision(payload, max_attempts=3, delay_seconds=2)

    # Kemas kini state payload
    payload["step"] = 2
    payload["mama_english_review"] = vision_result.get("mama_english_review", "")
    payload["local_image_path"] = vision_result.get("local_image_path", "")
    payload["review_char_count"] = vision_result.get("review_char_count", 0)
    payload["vision_model_used"] = vision_result.get("vision_model_used", "")

    # Simpan ke temp/shopee_payload.json
    with open(PAYLOAD_FILE, "w", encoding="utf-8") as f:
        json.dump(payload, f, indent=2, ensure_ascii=False)

    # Selaraskan juga ke temp/shopee_vision_ocr.json untuk keserasian modul media sosial
    with open(VISION_OCR_FILE, "w", encoding="utf-8") as f:
        json.dump(payload, f, indent=2, ensure_ascii=False)

    print(f"\n💾 [PAYLOAD UPDATED] Fail '{PAYLOAD_FILE.name}' & '{VISION_OCR_FILE.name}' diselaraskan.")
    print("=" * 75 + "\n")


if __name__ == "__main__":
    run_vision_step()