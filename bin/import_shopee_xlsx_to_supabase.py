#!/usr/bin/env python3
"""
Bulk Import Engine for Shopee Affiliate Excel (.xlsx) to Supabase Database
Sembang PC & Tech Ecosystem (Shopee Dedicated Table: shopee_affiliate_links)
Features:
- Reads all generated Excel files from shopee_affiliate_xlsx/
- Memory Bank tracking (data/imported_shopee_xlsx.json) to avoid reprocessing
- Individual Item Upsert: Skips only duplicate items without aborting the entire file
- Status Preservation: Preserves shopee_status_used=TRUE for previously posted products
- Smart Auto-Categorization based on title and brand keywords
- Batch upload (50 records/batch) via Supabase PostgREST API
"""

import os
import re
import sys
import json
import warnings
import pandas as pd
import requests
from pathlib import Path
from typing import Set, Dict, Any, List
from dotenv import load_dotenv

# Suppress openpyxl stylesheet warnings
warnings.filterwarnings("ignore", category=UserWarning, module="openpyxl")

# Set Project Root Path
PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

# Load Environment Variables (.env.local priority)
env_local = PROJECT_ROOT / ".env.local"
if env_local.exists():
    load_dotenv(dotenv_path=env_local)
else:
    load_dotenv()

# Folder & File Paths
INPUT_XLSX_DIR = PROJECT_ROOT / "shopee_affiliate_xlsx"
DATA_DIR = PROJECT_ROOT / "data"
MEMORY_FILE = DATA_DIR / "imported_shopee_xlsx.json"

# Konfigurasi Supabase mengikut nama kunci IRCM_
SUPABASE_URL = (
    os.getenv("IRCM_SUPABASE_URL", "").strip()
    or os.getenv("SUPABASE_URL", "").strip()
    or os.getenv("NEXT_PUBLIC_SUPABASE_URL", "").strip()
).rstrip("/")

SUPABASE_KEY = (
    os.getenv("IRCM_SUPABASE_SERVICE_ROLE_KEY", "").strip()
    or os.getenv("IRCM_SUPABASE_SECRET_KEY", "").strip()
    or os.getenv("IRCM_SUPABASE_KEY", "").strip()
    or os.getenv("IRCM_SUPABASE_ANON_KEY", "").strip()
    or os.getenv("SUPABASE_SERVICE_ROLE_KEY", "").strip()
    or os.getenv("SUPABASE_SECRET_KEY", "").strip()
    or os.getenv("SUPABASE_KEY", "").strip()
    or os.getenv("SUPABASE_ANON_KEY", "").strip()
)


# =============================================================================
# 1. ENJIN PENGECAMAN KATEGORI PINTAR
# =============================================================================

def auto_detect_category(title: str, brand: str = "") -> str:
    """Mengecam kategori produk secara automatik berdasarkan tajuk dan jenama."""
    text = f"{title} {brand}".lower()

    # 1. Kerusi Gaming & Ergonomik
    if any(k in text for k in ['chair', 'kerusi', 'office chair', 'gaming chair', 'ergonomic chair', 'reclining', 'mesh chair']):
        return "🪑 Kerusi Gaming & Ergonomik"

    # 2. Penyejuk & Kipas PC (AIO, Liquid Cooler, Fan, Radiator)
    if any(k in text for k in ['cooler', 'cooling', 'fan', 'aio', 'liquid cooler', 'water cooling', 'heatsink', 'radiator', 'thermalright', 'arctic liquid', 'cooler master']):
        return "🖥️ Penyejuk & Kipas PC"

    # 3. Komponen Utama PC (Motherboard, CPU, GPU, RAM, SSD, PSU, Case)
    if any(k in text for k in ['motherboard', 'mainboard', 'b760', 'b850', 'b650', 'b550', 'b450', 'am5', 'am4', 'lga 1700', 'lga 1851', 'ram ddr', 'ddr5', 'ddr4', 'ryzen', 'intel core', 'graphics card', 'rtx', 'gtx', 'gpu', 'power supply', 'psu', 'ssd', 'nvme', 'm.2', 'pc case', 'casing pc']):
        return "⚙️ Komponen & Perkakasan PC"

    # 4. Aksesori Gaming, Audio & Gajet Setup
    if any(k in text for k in ['keyboard', 'mouse', 'mousepad', 'desk mat', 'monitor', 'screen', 'stand', 'speaker', 'headset', 'earphone', 'headphone', 'microphone', 'mic', 'webcam', 'cable', 'charger', 'hub', 'docking', 'card reader', 'adapter', 'bluetooth', 'otg', 'power bank', 'gan ']):
        return "🎧 Aksesori Gaming & Audio"

    # 5. Peralatan Dapur & Rumah
    if any(k in text for k in ['kitchen', 'dapur', 'pan', 'pot', 'cookware', 'blender', 'air fryer', 'knife', 'pisau', 'kuali', 'periuk', 'kettle', 'rak dapur', 'bekas makanan', 'vacuum']):
        return "🍳 Peralatan Dapur & Rumah"

    # 6. Hobi, Outdoor & Memancing
    if any(k in text for k in ['fishing', 'pancing', 'joran', 'reel pancing', 'tackle', 'outdoor', 'camping', 'tent', 'backpack', 'beg travel', 'khemah', 'lampu suluh', 'hiking']):
        return "🎣 Hobi & Outdoor / Memancing"

    return "📦 Tawaran Gajet & Gaya Hidup"


# =============================================================================
# 2. BANK MEMORI FAIL EXCEL
# =============================================================================

def load_imported_memory() -> Set[str]:
    """Memuatkan senarai fail XLSX yang telah berjaya dimuat naik ke Supabase."""
    if not MEMORY_FILE.exists():
        return set()
    try:
        with open(MEMORY_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
            if isinstance(data, list):
                return set(data)
    except Exception as e:
        print(f"⚠️ [MEMORY WARN] Gagal membaca fail memori import: {e}")
    return set()


def save_imported_memory(processed_set: Set[str]):
    """Menyimpan rekod fail XLSX yang siap diimport ke format JSON."""
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    try:
        with open(MEMORY_FILE, "w", encoding="utf-8") as f:
            json.dump(sorted(list(processed_set)), f, indent=2, ensure_ascii=False)
    except Exception as e:
        print(f"⚠️ [MEMORY WARN] Gagal mengemas kini fail memori import: {e}")


# =============================================================================
# 3. ALIRAN UTAMA PENGIMPORT PUKAL SHOPEE
# =============================================================================

def bulk_import_shopee_to_supabase():
    print("\n" + "=" * 75)
    print("🛍️ [START] PENGIMPORT PUKAL SHOPEE EXCEL KE SUPABASE CLOUD")
    print("=" * 75)

    if not SUPABASE_URL or not SUPABASE_KEY:
        print("❌ [ERROR] IRCM_SUPABASE_URL atau IRCM_SUPABASE_SERVICE_ROLE_KEY tidak dijumpai dalam persekitaran (.env.local)!")
        return

    if not INPUT_XLSX_DIR.exists():
        print(f"❌ Direktori input tidak wujud: {INPUT_XLSX_DIR}")
        return

    imported_memory = load_imported_memory()
    print(f"🧠 [MEMORY BANK] {len(imported_memory)} fail Excel telah direkodkan sebelum ini.")

    all_xlsx_files = sorted(list(INPUT_XLSX_DIR.glob("link_affiliate_shopee_*.xlsx")))
    if not all_xlsx_files:
        print(f"⚠️ Tiada fail .xlsx dijumpai di: {INPUT_XLSX_DIR}")
        return

    pending_files = [f for f in all_xlsx_files if f.name not in imported_memory]
    skipped_count = len(all_xlsx_files) - len(pending_files)

    if skipped_count > 0:
        print(f"⏭️ {skipped_count} fail Excel dilangkau kerana telah selesai diimport.")

    if not pending_files:
        print("✅ Kesemua fail Excel Shopee telah dimuat naik ke Supabase. Tiada fail baharu.")
        return

    print(f"🎯 Dijumpai {len(pending_files)} fail Excel baharu untuk diimport.\n")

    # Header REST API Supabase
    headers = {
        "apikey": SUPABASE_KEY,
        "Authorization": f"Bearer {SUPABASE_KEY}",
        "Content-Type": "application/json",
        "Prefer": "resolution=merge-duplicates",
    }

    # Semak status_used sedia ada di Supabase untuk memelihara status hantaran lama
    print("🔍 Menyemak rekod lama di Supabase untuk mengekalkan status 'TRUE'...")
    existing_used_ids = set()
    try:
        check_url = f"{SUPABASE_URL}/rest/v1/shopee_affiliate_links?select=shopee_product_id&shopee_status_used=eq.true"
        r_check = requests.get(check_url, headers=headers, timeout=20)
        if r_check.status_code == 200:
            existing_used_ids = {str(item["shopee_product_id"]).strip() for item in r_check.json() if "shopee_product_id" in item}
            print(f"  🛡️ {len(existing_used_ids)} produk berstatus TRUE ditemui. Status ini akan dipelihara.")
    except Exception as e:
        print(f"  ⚠️ Amaran sambungan semakan status: {e}")

    total_inserted_all_files = 0

    for file_idx, xlsx_file in enumerate(pending_files, start=1):
        print("\n" + "-" * 75)
        print(f"📂 [FAIL {file_idx}/{len(pending_files)}] Membaca: {xlsx_file.name}")
        print("-" * 75)

        try:
            df = pd.read_excel(xlsx_file)
        except Exception as e:
            print(f"❌ Ralat membaca {xlsx_file.name}: {e}")
            continue

        if df.empty:
            print(f"⚠️ Fail {xlsx_file.name} kosong. Ditandakan sebagai selesai.")
            imported_memory.add(xlsx_file.name)
            save_imported_memory(imported_memory)
            continue

        file_records: List[Dict[str, Any]] = []
        seen_file_ids: Set[str] = set()
        file_duplicate_skip_count = 0

        for _, row in df.iterrows():
            raw_id = row.get("product_id")
            if pd.isna(raw_id):
                continue

            p_id = str(int(raw_id) if isinstance(raw_id, (int, float)) else raw_id).strip()
            name = str(row.get("product_name", "")).strip()
            aff_link = str(row.get("affiliate_link", "")).strip()
            pic_url = str(row.get("picture_url", "")).strip()

            if not p_id or not name or not aff_link or not pic_url or aff_link.lower() == "nan":
                continue

            # Elak pertindihan ID dalam fail yang sama
            if p_id in seen_file_ids:
                file_duplicate_skip_count += 1
                continue

            seen_file_ids.add(p_id)

            brand = str(row.get("brand", "Shopee Preferred")).strip()
            if not brand or brand.lower() == "nan":
                brand = "Shopee Preferred"

            try:
                price_val = float(row.get("price", 0.0))
            except Exception:
                price_val = 0.0

            sales_cnt = str(row.get("sales_count", "0")).strip()
            comm_rate = str(row.get("commission_rate", "0%")).strip()
            comm_amt = str(row.get("commission_amount", "RM 0.00")).strip()
            prod_url = str(row.get("product_url", "")).strip()

            category = auto_detect_category(name, brand)
            is_used = True if p_id in existing_used_ids else False

            # Susun data mengikut skema shopee_affiliate_links di Supabase
            record = {
                "shopee_product_id": p_id,
                "shopee_product_name": name,
                "shopee_brand": brand,
                "shopee_price": price_val,
                "shopee_sales_count": sales_cnt if sales_cnt != "nan" else "0",
                "shopee_commission_rate": comm_rate if comm_rate != "nan" else "0%",
                "shopee_commission_amount": comm_amt if comm_amt != "nan" else "RM 0.00",
                "shopee_picture_url": pic_url,
                "shopee_product_url": prod_url if prod_url != "nan" else "",
                "shopee_affiliate_link": aff_link,
                "shopee_category": category,
                "shopee_status_used": is_used,
            }
            file_records.append(record)

        if not file_records:
            print(f"⚠️ Tiada rekod sah dijumpai dalam {xlsx_file.name}.")
            continue

        print(f"📊 Sah untuk dimuat naik: {len(file_records)} produk (Pertindihan dalaman dilangkau: {file_duplicate_skip_count}).")

        # Muat naik ke Supabase menggunakan kaedah Batch Upsert (50 produk / request)
        endpoint = f"{SUPABASE_URL}/rest/v1/shopee_affiliate_links?on_conflict=shopee_product_id"
        batch_size = 50
        file_success_count = 0
        has_batch_error = False

        for i in range(0, len(file_records), batch_size):
            batch = file_records[i : i + batch_size]
            try:
                res = requests.post(endpoint, headers=headers, json=batch, timeout=25)
                if res.status_code in [200, 201]:
                    file_success_count += len(batch)
                else:
                    has_batch_error = True
                    print(f"  ❌ Ralat kelompok {i+1}-{i+len(batch)}: HTTP {res.status_code} | {res.text}")
            except Exception as e:
                has_batch_error = True
                print(f"  ❌ Ralat sambungan: {e}")

        total_inserted_all_files += file_success_count
        print(f"✅ {file_success_count}/{len(file_records)} produk dari {xlsx_file.name} berjaya disimpan/dikemas kini di Supabase.")

        # Hanya kunci fail ke memori jika tiada ralat kritikal
        if not has_batch_error and file_success_count > 0:
            imported_memory.add(xlsx_file.name)
            save_imported_memory(imported_memory)
            print(f"🧠 Memori Dikemas Kini: '{xlsx_file.name}' dikunci.")

    print("\n" + "=" * 75)
    print("🎉 [PROSES IMPORT PUKAL SELESAI]")
    print("=" * 75)
    print(f"📦 Jumlah Keseluruhan Produk Berjaya Diproses: {total_inserted_all_files}")
    print(f"📁 Pangkalan Data Sasaran: public.shopee_affiliate_links")
    print(f"📄 Rekod Memori Disimpan : {MEMORY_FILE}")
    print("=" * 75 + "\n")


if __name__ == "__main__":
    bulk_import_shopee_to_supabase()