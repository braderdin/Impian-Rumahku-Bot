#!/usr/bin/env python3
"""
Persona Lifestyle Mama: Step 4 Runner (Telegram Audit, Gatekeeper & DB Lock Commit)
Location: bin/run_persona_lifestyle_audit_and_commit.py

Workflow:
- Step 4A: Sends full audit report & cards to Telegram Bot.
- Gatekeeper: Verifies if at least ONE (1) social media platform succeeded.
  * If ALL failed: Aborts immediately without committing keys to prevent wasting the topic.
- Step 4B: Commits topic lock to Upstash Redis (10-Day TTL) & pushes to recent topics memory.
- Step 4C: Upserts semantic embedding to Upstash Vector DB (2-Day Window).
- Step 4D: Cleans up temporary image files while preserving JSON payloads for repo tracking.
"""

import sys
import json
import time
from pathlib import Path

# Setup Project Root Path
PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

# Import Enjin Teras dari src/
from src.persona_lifestyle_telegram_audit import (
    send_lifestyle_telegram_audit_report,
    has_successful_lifestyle_post,
)
from src.persona_lifestyle_filter import commit_lifestyle_topic_lock

TEMP_DIR = PROJECT_ROOT / "temp"
PAYLOAD_FILE = TEMP_DIR / "lifestyle_payload.json"


def print_banner(text: str):
    print("\n" + "═" * 78)
    print(f"📊 {text.upper()}")
    print("═" * 78)


def cleanup_temp_image_files(local_image_path: str = ""):
    """
    Memadam fail imej fizikal sementara untuk menjimatkan storan,
    sambil mengekalkan fail JSON payload untuk semakan di GitHub.
    """
    if local_image_path:
        img_p = Path(local_image_path)
        try:
            if img_p.exists():
                img_p.unlink()
                print(f"   🧹 [CLEANUP] Fail imej '{img_p.name}' berjaya dipadam.")
        except Exception as e:
            print(f"   ⚠️ [CLEANUP WARN] Gagal memadam imej: {e}")

    # Bersihkan sebarang imej sisa reddit_*.jpg di folder temp
    for temp_img in TEMP_DIR.glob("reddit_*.jpg"):
        try:
            temp_img.unlink()
        except Exception:
            pass

    print("   💾 [STATE PRESERVED] Fail JSON dalam temp/ dikekalkan untuk audit repositori.")


def run_lifestyle_audit_and_commit_step():
    print_banner("[STEP 4] AUDIT TELEGRAM, PINTU KESELAMATAN & TRANSAKSI KUNCI PENAPIS")

    # 1. Semak fail state payload
    if not PAYLOAD_FILE.exists():
        print(f"❌ [ABORT] Fail payload '{PAYLOAD_FILE.name}' tidak dijumpai. Tiada data untuk diaudit.")
        sys.exit(1)

    try:
        with open(PAYLOAD_FILE, "r", encoding="utf-8") as f:
            payload = json.load(f)
    except Exception as e:
        print(f"❌ [ABORT] Gagal membaca fail payload: {e}")
        sys.exit(1)

    topic_id = payload.get("topic_id", "N/A")
    topic_text = payload.get("topic_lock_text", "")
    niche_key = payload.get("niche", {}).get("niche_key", "lifestyle")
    local_img = payload.get("local_image_path", "")
    post_results = payload.get("post_results", {})

    print(f"📦 ID Topik       : {topic_id}")
    print(f"🌿 Niche          : {payload.get('niche', {}).get('niche_title', 'Gaya Hidup')}")
    print(f"🧠 Enjin Digunakan: {payload.get('engine_used', 'AI Engine')}")

    # 2. Hantar Laporan Audit Lengkap ke Telegram
    print("\n📢 Menghantar laporan audit terperinci ke saluran Telegram...")
    audit_ok, audit_msg = send_lifestyle_telegram_audit_report(payload)
    if audit_ok:
        print("✅ [AUDIT SUCCESS] Laporan audit berjaya dihantar ke Telegram.")
    else:
        print(f"⚠️ [AUDIT WARN] Telegram Audit: {audit_msg}")

    # 3. Pintu Keselamatan (Safety Gatekeeper)
    success_any = has_successful_lifestyle_post(payload)

    if not success_any:
        print("\n" + "!" * 78)
        print("❌ [GATEKEEPER BLOCKED] Semua platform media sosial gagal membuat hantaran!")
        print("🛑 Transaksi ke Redis (10 Hari) dan Vector DB (2 Hari) DIBATALKAN.")
        print("ℹ️  Topik ini TIDAK akan dikunci supaya boleh dicuba semula pada sesi seterusnya.")
        print("!" * 78)

        for platform, res in post_results.items():
            err_detail = res.get("error", "Status bukan success") if isinstance(res, dict) else "Tiada maklumat"
            print(f"   • {platform.capitalize()}: {err_detail}")

        sys.exit(1)

    print("\n✅ [GATEKEEPER PASSED] Sekurang-kurangnya 1 platform berjaya pos. Meneruskan penguncian...")

    # 4. Transaksi Kunci: Redis (10 Hari + Buffer Memori) & Vector DB (2 Hari)
    print("\n🔒 Mengunci rekod topik ke Upstash Redis & Upstash Vector DB...")
    lock_ok = commit_lifestyle_topic_lock(
        topic_id=topic_id,
        topic_text=topic_text,
        category=niche_key
    )

    if lock_ok:
        print("✅ Transaksi Kunci Selesai: Topik dikunci daripada sebarang pengulangan!")
    else:
        print("⚠️ [LOCK WARN] Gagal merekodkan transaksi kunci secara penuh.")

    # 5. Pembersihan Fail Imej Sementara
    print("\n🧹 Membersihkan fail imej tempatan...")
    cleanup_temp_image_files(local_img)

    print_banner("SELURUH SALURAN LIFESTYLE MAMA SELESAI DENGAN JAYANYA")


if __name__ == "__main__":
    run_lifestyle_audit_and_commit_step()