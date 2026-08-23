import os
import datetime
import requests
from dotenv import load_dotenv

# 1. Muat pembolehubah dari .env.local
load_dotenv(".env.local")

# Kunci Facebook
FB_PAGE_NAME = os.getenv("IRCM_FB_META_PAGE_NAME")
FB_PAGE_ID = os.getenv("IRCM_FB_META_PAGE_ID")
FB_APP_ID = os.getenv("IRCM_FB_META_APP_ID")
FB_APP_SECRET = os.getenv("IRCM_FB_META_APP_SECRET")
FB_PAGE_ACCESS_TOKEN = os.getenv("IRCM_FB_META_PAGE_ACCESS_TOKEN")

# Kunci Instagram
IG_ACCOUNT_ID = os.getenv("IRCM_INSTAGRAM_ACCOUNT_ID")
IG_ACCESS_TOKEN = os.getenv("IRCM_INSTAGRAM_ACCESS_TOKEN")

GRAPH_API_URL = "https://graph.facebook.com/v26.0"


def semak_tempoh_token(token_name, token_value, app_id, app_secret):
    """Menyemak status kesahan dan tarikh tamat tempoh token."""
    print(f"\n[+] Memeriksa Token: {token_name}")
    if not token_value:
        print(f"  [RALAT] Nilai {token_name} kosong dalam .env.local!")
        return False

    # Gunakan App Token atau Token sendiri untuk debugging
    app_token = f"{app_id}|{app_secret}" if (app_id and app_secret) else token_value
    debug_url = f"{GRAPH_API_URL}/debug_token"
    params = {
        "input_token": token_value,
        "access_token": app_token
    }

    try:
        res = requests.get(debug_url, params=params)
        data = res.json()

        if "error" in data:
            print(f"  [RALAT GRAPH API] {data['error'].get('message')}")
            return False

        token_data = data.get("data", {})
        is_valid = token_data.get("is_valid", False)
        expires_at = token_data.get("expires_at", 0)
        scopes = token_data.get("scopes", [])

        print(f"  Status Kesahan : {'Sah (Valid)' if is_valid else 'Tidak Sah'}")
        print(f"  Jenis Token    : {token_data.get('type')}")
        
        if expires_at == 0:
            print("  Tempoh Luput   : Never Expired (Kekal)")
        else:
            exp_date = datetime.datetime.fromtimestamp(expires_at)
            print(f"  Tempoh Luput   : Akan tamat pada {exp_date.strftime('%Y-%m-%d %H:%M:%S')}")

        print(f"  Keizinan (Scopes): {', '.join(scopes)}")
        return is_valid

    except Exception as e:
        print(f"  [RALAT SISTEM] Gagal membuat semakan token: {e}")
        return False


def uji_facebook_page_post():
    """Menguji sambungan Page dan membuat satu pos percubaan."""
    print(f"\n[+] Menguji Sambungan Facebook Page ({FB_PAGE_NAME})...")
    
    # 1. Semak maklumat Page
    me_url = f"{GRAPH_API_URL}/{FB_PAGE_ID}"
    params = {
        "fields": "id,name,link",
        "access_token": FB_PAGE_ACCESS_TOKEN
    }
    
    res = requests.get(me_url, params=params)
    data = res.json()
    
    if "error" in data:
        print(f"  [RALAT FB PAGE] Gagal sambung: {data['error'].get('message')}")
        return
        
    print(f"  Berjaya sambung ke Page: {data.get('name')} (ID: {data.get('id')})")
    
    # 2. Hantar Pos Ujian
    post_url = f"{GRAPH_API_URL}/{FB_PAGE_ID}/feed"
    payload = {
        "message": "Assalammualaikum & Salam Sejahtera! ✨\n\nIni adalah posting ujian sistem automasi Impian Rumahku & Cerita Mama. Nantikan pelbagai tips deko dan pilihan barangan Home & Living menarik nanti! 🏠💖",
        "access_token": FB_PAGE_ACCESS_TOKEN
    }
    
    post_res = requests.post(post_url, data=payload)
    post_data = post_res.json()
    
    if "id" in post_data:
        print(f"  [BERJAYA] Feed Test Post Berjaya Diterbitkan! ID Pos: {post_data['id']}")
    else:
        print(f"  [RALAT POS] Gagal menerbitkan post: {post_data.get('error', {}).get('message')}")


def uji_instagram_account():
    """Menguji sambungan akaun perniagaan Instagram."""
    print("\n[+] Menguji Sambungan Instagram Business Account...")
    if not IG_ACCOUNT_ID:
        print("  [AMARAN] IRCM_INSTAGRAM_ACCOUNT_ID tidak dijumpai dalam .env.local.")
        return

    ig_url = f"{GRAPH_API_URL}/{IG_ACCOUNT_ID}"
    params = {
        "fields": "id,username,name",
        "access_token": IG_ACCESS_TOKEN
    }

    res = requests.get(ig_url, params=params)
    data = res.json()

    if "error" in data:
        print(f"  [RALAT INSTAGRAM] Gagal sambung: {data['error'].get('message')}")
    else:
        print(f"  [BERJAYA] Berjaya sambung ke akaun IG: @{data.get('username')} ({data.get('name')})")


if __name__ == "__main__":
    print("==================================================")
    print("      UJIAN KUNCI & SAMBUNGAN META (FB & IG)      ")
    print("==================================================")

    # Semakan Token FB & IG
    semak_tempoh_token("IRCM_FB_META_PAGE_ACCESS_TOKEN", FB_PAGE_ACCESS_TOKEN, FB_APP_ID, FB_APP_SECRET)
    semak_tempoh_token("IRCM_INSTAGRAM_ACCESS_TOKEN", IG_ACCESS_TOKEN, FB_APP_ID, FB_APP_SECRET)

    # Ujian Terbitan FB & Sambungan IG
    uji_facebook_page_post()
    uji_instagram_account()

    print("\n==================================================")
    print("                UJIAN SELESAI                     ")
    print("==================================================")