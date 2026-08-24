#!/usr/bin/env python3
"""
Diagnostic Test: Mesolitica NanoT5-Base v2.1 Translation Engine
Model: mesolitica/nanot5-base-malaysian-translation-v2.1 (~990MB)
Target: Terjemahan ulasan Vision AI ke Bahasa Melayu Malaysia
"""

import os
import sys
import json
import time
from pathlib import Path
from dotenv import load_dotenv
import torch
from transformers import AutoTokenizer, AutoModelForSeq2SeqLM

# Konfigurasi Path Projek
PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

# Muat turun pemboleh ubah persekitaran (.env.local)[cite: 1, 3]
env_local = PROJECT_ROOT / ".env.local"
if env_local.exists():
    load_dotenv(dotenv_path=env_local)
else:
    load_dotenv()


def dapatkan_teks_vision() -> str:
    """Membaca teks ulasan Vision AI daripada payload atau sandaran."""
    fail_sasaran = [
        PROJECT_ROOT / "experiments" / "test_pexels_render_result.json",
        PROJECT_ROOT / "temp" / "pexels_vision_payload.json"
    ]
    for fail in fail_sasaran:
        if fail.exists():
            try:
                with open(fail, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    review = data.get("vision_ai_review")
                    if review:
                        print(f"📄 Membaca teks daripada fail: {fail.name}")
                        return review
            except Exception as e:
                print(f"⚠️ Ralat membaca {fail.name}: {e}")

    print("ℹ️ Menggunakan teks ulasan Vision AI standard (484 aksara)...")
    return (
        "A serene visual journey into mindful wardrobe curation, flowing gracefully from warm, "
        "minimalist beige tones to the tactile joy of organizing soft pinks and neutrals. "
        "Transitioning through clean, artistic shadows into a tidy wooden sanctuary, the color-coordinated "
        "clothes and neat baskets harmonize beautifully under gentle, inviting light. This soothing aesthetic "
        "progression captures a sophisticated lifestyle ambiance of quiet, curated elegance and peaceful "
        "domestic satisfaction."
    )


def main():
    print("=" * 75)
    print("🧪 [UJIAN DIAGNOSTIK] MESOLITICA NANOT5-BASE v2.1 (EN -> MELAYU)")
    print("   Impian Rumahku & Cerita Mama Ecosystem")
    print("=" * 75)

    teks_asal = dapatkan_teks_vision()

    print(f"\n📝 [TEKS ASAL (EN)] ({len(teks_asal)} Aksara):")
    print(f"\"{teks_asal}\"")
    print("-" * 75)

    # 1. Muat Model Mesolitica NanoT5-Base v2.1 (~990MB)
    model_name = "mesolitica/nanot5-base-malaysian-translation-v2.1"
    print(f"\n⏳ Memuatkan model '{model_name}'...")
    masa_mula_load = time.time()

    tokenizer = AutoTokenizer.from_pretrained(model_name)
    model = AutoModelForSeq2SeqLM.from_pretrained(model_name)

    durasi_load = time.time() - masa_mula_load
    print(f"✅ Model berjaya dimuatkan dalam {durasi_load:.2f} saat.")

    # 2. Proses Terjemahan
    print("\n🚀 Memulakan penterjemahan ke Bahasa Melayu...")
    masa_mula_jana = time.time()

    # Prefix arahan model NanoT5 v2.1
    prompt = f"terjemah ke Melayu: {teks_asal.strip()}"
    inputs = tokenizer(prompt, return_tensors="pt", max_length=512, truncation=True)

    with torch.no_grad():
        outputs = model.generate(
            **inputs,
            max_new_tokens=512,
            num_beams=2,
            early_stopping=True
        )

    perenggan_bm = tokenizer.decode(outputs[0], skip_special_tokens=True)
    durasi_jana = time.time() - masa_mula_jana

    # 3. Paparan Keputusan
    print("\n" + "=" * 75)
    print("📊 [KEPUTUSAN TERJEMAHAN MESOLITICA NANOT5-BASE]")
    print("=" * 75)
    print(f"⏱️ Masa Terjemah : {durasi_jana:.2f} saat (CPU Inference)")
    print(f"📏 Saiz Output   : {len(perenggan_bm)} Aksara")
    print(f"\n💬 Hasil BM Malaysia:\n")
    print(f"\"{perenggan_bm}\"")
    print("=" * 75)


if __name__ == "__main__":
    main()