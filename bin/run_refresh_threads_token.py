import os
import sys
from dotenv import load_dotenv

# Memastikan laluan akar projek dimasukkan ke dalam sys.path
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

env_local_path = os.path.join(PROJECT_ROOT, ".env.local")
if os.path.exists(env_local_path):
    load_dotenv(dotenv_path=env_local_path)
else:
    load_dotenv()

from src.refresh_threads_token import (
    get_active_threads_token,
    save_threads_token_to_redis,
    refresh_threads_long_lived_token
)

def run_token_refresh_job():
    print("\n" + "=" * 70)
    print("🔄 [START] AUTO-REFRESH THREADS LONG-LIVED ACCESS TOKEN")
    print("=" * 70)

    # Menggunakan prefiks IRCM_ selaras dengan env.example
    redis_url = os.getenv("IRCM_UPSTASH_REDIS_REST_URL", "").strip()
    redis_token = os.getenv("IRCM_UPSTASH_REDIS_REST_TOKEN", "").strip()
    env_threads_token = os.getenv("IRCM_THREADS_ACCESS_TOKEN", "").strip()

    # 1. DAPATKAN TOKEN AKTIF
    print("\n🔍 [STEP 1] Mengesan token Threads aktif sedia ada...")
    active_token = get_active_threads_token(redis_url, redis_token, env_threads_token)

    if not active_token:
        print("❌ [ABORT] Tiada IRCM_THREADS_ACCESS_TOKEN dijumpai dalam Redis atau Environment.")
        sys.exit(1)

    masked_token = f"{active_token[:10]}...{active_token[-6:]}"
    print(f"  ✅ Token dikesan: {masked_token}")

    # 2. HANTAR PERMINTAAN REFRESH KE META API
    print("\n📡 [STEP 2] Menghantar permintaan pembaharuan ke Meta Threads API...")
    success, new_token, expires_in = refresh_threads_long_lived_token(active_token)

    if not success or not new_token:
        print(f"❌ [REFRESH FAILED] {new_token}")
        sys.exit(1)

    days_left = round(expires_in / 86400, 1)
    print(f"  🎉 [REFRESH SUCCESS] Token berjaya diperbaharui!")
    print(f"  ⏳ Tempoh hayat baharu: {expires_in} saat (~{days_left} Hari)")

    # 3. SIMPAN TOKEN KE UPSTASH REDIS
    if redis_url and redis_token:
        print("\n💾 [STEP 3] Menyimpan token baharu ke Upstash Redis...")
        saved = save_threads_token_to_redis(redis_url, redis_token, new_token, expires_in)
        if saved:
            print("  ✅ Token baharu berjaya disimpan di Upstash Redis (Kunci: 'auth:impianrumahku:threads_token').")
        else:
            print("  ⚠️ Gagal menyimpan ke Redis, namun token telah diperbaharui di Meta.")

    print("\n" + "=" * 70)
    print("🎉 [DONE] Token Meta Threads sentiasa segar dan selamat untuk 60 hari akan datang!")
    print("=" * 70 + "\n")

if __name__ == "__main__":
    run_token_refresh_job()