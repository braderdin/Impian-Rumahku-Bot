#!/usr/bin/env python3
"""
Shopee Supabase Database Engine & Lifecycle Manager
Sembang PC & Tech / Impian Rumahku Ecosystem
Table: public.shopee_affiliate_links
Features:
- Dynamic ENV loading with IRCM_SUPABASE_* priority
- Auto-reset lifecycle: Resets all items to FALSE when all items become TRUE
- Smart Sales Parser (handles '10k+', '999', '1.5k', etc.)
- 2-Tier Candidate Pool: Prioritizes sales >= 20, then secondary pool
- Fair Rotation (Random Shuffle) across candidates
- Cleans output to 6 essential fields for AI & Social Bot engines
- Multi-attempt fallback fetcher (5 attempts) with temp/ JSON caching
- Locks product status (shopee_status_used = TRUE) upon successful post
"""

import os
import re
import sys
import json
import random
import requests
from pathlib import Path
from typing import List, Dict, Any, Tuple, Optional
from dotenv import load_dotenv

# Setup Project Root Path
PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

# Load Environment Variables (.env.local priority)
env_local = PROJECT_ROOT / ".env.local"
if env_local.exists():
    load_dotenv(dotenv_path=env_local)
else:
    load_dotenv()

# Folder Simpanan Sementara
TEMP_DIR = PROJECT_ROOT / "temp"
TEMP_CANDIDATES_FILE = TEMP_DIR / "shopee_candidates_batch.json"


def get_supabase_config() -> Tuple[Optional[str], Optional[str], str]:
    """
    Membaca tetapan sambungan Supabase secara dinamik daripada persekitaran (.env).
    Mengutamakan nama pembolehubah IRCM_SUPABASE_*.
    """
    supabase_url = (
        os.getenv("IRCM_SUPABASE_URL", "").strip()
        or os.getenv("SUPABASE_URL", "").strip()
        or os.getenv("NEXT_PUBLIC_SUPABASE_URL", "").strip()
    )

    service_role_key = (
        os.getenv("IRCM_SUPABASE_SERVICE_ROLE_KEY", "").strip()
        or os.getenv("IRCM_SUPABASE_SECRET_KEY", "").strip()
        or os.getenv("IRCM_SUPABASE_KEY", "").strip()
        or os.getenv("IRCM_SUPABASE_ANON_KEY", "").strip()
        or os.getenv("SUPABASE_SERVICE_ROLE_KEY", "").strip()
        or os.getenv("SUPABASE_SECRET_KEY", "").strip()
        or os.getenv("SUPABASE_KEY", "").strip()
        or os.getenv("SUPABASE_ANON_KEY", "").strip()
    )

    if not supabase_url or not service_role_key:
        return None, None, "Kunci IRCM_SUPABASE_URL atau IRCM_SUPABASE_SERVICE_ROLE_KEY tidak lengkap dalam persekitaran."

    return supabase_url.rstrip("/"), service_role_key, ""


def parse_sales_count(val: Any) -> int:
    """
    Menukar format teks jualan Shopee (cth: '9k+', '30k+', '999', '1.5k', '0')
    kepada nombor bulat (integer) untuk penapisan ketepatan jualan.
    """
    if val is None:
        return 0

    text = str(val).strip().lower()
    if not text or text == "nan":
        return 0

    try:
        if "k" in text:
            match = re.search(r"([\d\.]+)\s*k", text)
            if match:
                return int(float(match.group(1)) * 1000)

        clean_num = re.sub(r"[^\d]", "", text)
        return int(clean_num) if clean_num else 0
    except Exception:
        return 0


def check_and_reset_shopee_status() -> Tuple[bool, str]:
    """
    Menyemak baki produk berstatus shopee_status_used=false.
    Jika semua produk telah digunakan (baki 0), set semula semua rekod kepada false.
    """
    supabase_url, api_key, err = get_supabase_config()
    if err:
        return False, err

    headers = {
        "apikey": api_key,
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
        "Prefer": "count=exact",
    }

    check_url = f"{supabase_url}/rest/v1/shopee_affiliate_links?select=shopee_product_id&shopee_status_used=eq.false&limit=1"
    try:
        res = requests.get(check_url, headers=headers, timeout=15)
        content_range = res.headers.get("content-range", "")
        unused_count = 0
        if "/" in content_range:
            total_part = content_range.split("/")[1]
            if total_part.isdigit():
                unused_count = int(total_part)

        if unused_count > 0:
            return True, f"Masih terdapat {unused_count} produk sedia ada (shopee_status_used=false)."

        # Jika 0, reset semula semua kepada FALSE
        print("🔄 [AUTO-RESET] Semua produk Shopee telah digunakan (TRUE). Mengemas kini semula kepada FALSE...")
        reset_url = f"{supabase_url}/rest/v1/shopee_affiliate_links?shopee_status_used=eq.true"
        payload = {"shopee_status_used": False}
        patch_res = requests.patch(reset_url, json=payload, headers=headers, timeout=25)

        if patch_res.status_code in [200, 204]:
            return True, "Semua produk Shopee berjaya di-reset semula kepada status_used=false."
        else:
            return False, f"Gagal reset status: HTTP {patch_res.status_code} | {patch_res.text}"

    except Exception as e:
        return False, f"Ralat rangkaian semasa semakan/reset status: {str(e)}"


def _clean_product_schema(record: Dict[str, Any]) -> Dict[str, Any]:
    """
    Menapis dan memastikan hanya 6 medan utama dipulangkan untuk kegunaan modul bot.
    """
    price_val = record.get("shopee_price", 0.0)
    try:
        price_float = float(price_val)
    except Exception:
        price_float = 0.0

    return {
        "shopee_product_id": str(record.get("shopee_product_id", "")).strip(),
        "shopee_product_name": str(record.get("shopee_product_name", "")).strip(),
        "shopee_brand": str(record.get("shopee_brand", "Shopee Preferred")).strip(),
        "shopee_price": price_float,
        "shopee_picture_url": str(record.get("shopee_picture_url", "")).strip(),
        "shopee_affiliate_link": str(record.get("shopee_affiliate_link", "")).strip(),
    }


def fetch_shopee_candidate_batch(limit: int = 300, offset: int = 0) -> Tuple[bool, List[Dict[str, Any]], str]:
    """
    Menarik kelompok calon produk Shopee (shopee_status_used = false).
    - Memastikan auto-reset status jika baki produk 0.
    - Mengutamakan produk dengan jualan >= 20.
    - Mengacak (random shuffle) setiap kelompok supaya semua produk mendapat peluang sama rata.
    """
    reset_ok, reset_msg = check_and_reset_shopee_status()
    if not reset_ok:
        print(f"⚠️ [RESET STATUS WARN] {reset_msg}")

    supabase_url, api_key, err = get_supabase_config()
    if err:
        return False, [], err

    headers = {
        "apikey": api_key,
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }

    endpoint = (
        f"{supabase_url}/rest/v1/shopee_affiliate_links"
        f"?shopee_status_used=eq.false"
        f"&order=id.asc"
        f"&limit={limit}"
        f"&offset={offset}"
    )

    try:
        res = requests.get(endpoint, headers=headers, timeout=20)
        if res.status_code != 200:
            return False, [], f"Supabase Fetch Error (HTTP {res.status_code}): {res.text}"

        raw_records = res.json()
        if not isinstance(raw_records, list) or len(raw_records) == 0:
            return True, [], "Tiada calon produk dijumpai pada offset ini."

        # Bahagikan produk kepada 2 kumpulan mengikut nilai jualan
        high_sales: List[Dict[str, Any]] = []
        low_sales: List[Dict[str, Any]] = []

        for item in raw_records:
            cleaned = _clean_product_schema(item)
            if not cleaned["shopee_product_id"] or not cleaned["shopee_affiliate_link"]:
                continue

            sales_count_num = parse_sales_count(item.get("shopee_sales_count", "0"))
            if sales_count_num >= 20:
                high_sales.append(cleaned)
            else:
                low_sales.append(cleaned)

        # Rawakkan (shuffle) kedua-dua kumpulan untuk pusingan adil
        random.shuffle(high_sales)
        random.shuffle(low_sales)

        # Gabungkan: Keutamaan kepada jualan >= 20, disusuli kumpulan sandaran
        combined_candidates = high_sales + low_sales

        summary_msg = (
            f"Berjaya menarik {len(combined_candidates)} calon produk "
            f"(Jualan >= 20: {len(high_sales)} item, Sandaran: {len(low_sales)} item)."
        )
        return True, combined_candidates, summary_msg

    except Exception as e:
        return False, [], f"Ralat sambungan Supabase: {str(e)}"


def fetch_candidates_with_fallback(
    max_attempts: int = 5,
    batch_size: int = 300,
    save_temp: bool = True
) -> Tuple[bool, List[Dict[str, Any]], str]:
    """
    Mengambil calon produk dengan sokongan fallback percubaan sehingga 5 kali
    sekiranya kelompok awal gagal tapisan Redis/Vektor pada offset sebelumnya.
    Menyimpan senarai ke temp/shopee_candidates_batch.json jika save_temp=True.
    """
    TEMP_DIR.mkdir(parents=True, exist_ok=True)

    for attempt in range(1, max_attempts + 1):
        offset = (attempt - 1) * batch_size
        print(f"📡 [DB ATTEMPT {attempt}/{max_attempts}] Menarik kelompok {batch_size} produk (Offset: {offset})...")

        ok, candidates, msg = fetch_shopee_candidate_batch(limit=batch_size, offset=offset)
        if ok and candidates:
            print(f"  ✅ {msg}")

            if save_temp:
                try:
                    with open(TEMP_CANDIDATES_FILE, "w", encoding="utf-8") as f:
                        json.dump(candidates, f, indent=2, ensure_ascii=False)
                    print(f"  💾 Calon produk disimpan sementara ke: {TEMP_CANDIDATES_FILE.name}")
                except Exception as e:
                    print(f"  ⚠️ Gagal menyimpan fail temp: {e}")

            return True, candidates, msg

        print(f"  ⚠️ Percubaan {attempt} tiada rekod atau ralat: {msg}")

    return False, [], f"Gagal mendapatkan calon produk selepas {max_attempts} percubaan fallback."


def mark_shopee_product_as_used(product_id: str) -> Tuple[bool, str]:
    """
    Menandakan shopee_status_used = true untuk shopee_product_id tertentu di Supabase
    selepas berjaya disiarkan ke platform media sosial.
    """
    supabase_url, api_key, err = get_supabase_config()
    if err:
        return False, err

    clean_id = str(product_id).strip()
    if not clean_id:
        return False, "Product ID tidak sah."

    endpoint = f"{supabase_url}/rest/v1/shopee_affiliate_links?shopee_product_id=eq.{clean_id}"
    headers = {
        "apikey": api_key,
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
        "Prefer": "return=representation",
    }
    payload = {"shopee_status_used": True}

    try:
        res = requests.patch(endpoint, json=payload, headers=headers, timeout=15)
        if res.status_code in [200, 204]:
            return True, f"Produk Shopee ID {clean_id} berjaya ditandakan shopee_status_used=true di Supabase."
        else:
            return False, f"Supabase Update Error (HTTP {res.status_code}): {res.text}"
    except Exception as e:
        return False, f"Ralat sambungan Supabase: {str(e)}"


if __name__ == "__main__":
    print("=" * 70)
    print("🧪 [TEST RUN] Menguji Enjin Pangkalan Data Shoabase Shopee...")
    print("=" * 70)
    success, batch, message = fetch_candidates_with_fallback(max_attempts=5, batch_size=300)
    if success and batch:
        print(f"\n🎉 Ujian Berjaya! Jumlah calon diterima: {len(batch)}")
        print(f"📦 Contoh Produk Rawak Terpilih Pertama:")
        print(json.dumps(batch[0], indent=2, ensure_ascii=False))
    else:
        print(f"\n❌ Ujian Gagal: {message}")