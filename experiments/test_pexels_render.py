#!/usr/bin/env python3
"""
Diagnostic Experiment Runner (v3 - Multi-Keyframe Sequence & Lightweight Compression)
Impian Rumahku & Cerita Mama Ecosystem
Features:
- Single API call to Pexels (per_page=70) for Home & Living faceless B-Roll
- Picks 4 to 5 vertical clips and stitches them to 30 - 40 seconds (9:16, 1080x1920)
- Ingests random .mp4 music from assets/music/ and extracts rich metadata
- Extracts 4 chronological keyframe snapshots across the video duration
- Compresses each frame (<15KB each, total payload ~45KB)
- Injects multi-image payload to OpenRouter Vision API (Primary 2x -> Fallback 2x, temp=0.40)
- Outputs rendered video to experiments/pexels_output/ and JSON state to temp/
"""

import os
import re
import sys
import time
import json
import random
import base64
import tempfile
import requests
from io import BytesIO
from pathlib import Path
from typing import List, Dict, Any, Tuple, Optional
from PIL import Image
from dotenv import load_dotenv

# Setup Root Directory & Environment
PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

# Load Environment Variables (.env.local priority)
env_local = PROJECT_ROOT / ".env.local"
if env_local.exists():
    load_dotenv(dotenv_path=env_local)
else:
    load_dotenv()

TEMP_DIR = PROJECT_ROOT / "temp"
OUTPUT_DIR = PROJECT_ROOT / "experiments" / "pexels_output"
MUSIC_DIR = PROJECT_ROOT / "assets" / "music"

TEMP_DIR.mkdir(parents=True, exist_ok=True)
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
MUSIC_DIR.mkdir(parents=True, exist_ok=True)

# MoviePy Compatibility Layer
try:
    from moviepy import VideoFileClip, AudioFileClip, concatenate_videoclips
except ImportError:
    from moviepy.editor import VideoFileClip, AudioFileClip, concatenate_videoclips

# Mutagen ID3 Reader
try:
    from mutagen import File as MutagenFile
except ImportError:
    MutagenFile = None

# ==============================================================================
# 1. KONFIGURASI KUNCI & SENARAI TEMA HOME & LIVING
# ==============================================================================

FORBIDDEN_KEYWORDS = [
    "man", "men", "woman", "women", "girl", "girls", "boy", "boys", "person", "people",
    "lady", "guy", "guys", "female", "male", "human", "adult", "child", "kid", "teen", "teenager",
    "face", "faces", "portrait", "selfie", "vlog", "model", "posing", "smile", "smiling",
    "looking", "eyes", "head", "headshot", "profile", "closeup-of-face",
    "gamer", "streamer", "influencer", "creator", "actor",
    "dog", "dogs", "puppy", "puppies", "canine", "pig", "pigs", "pork", "swine", "boar"
]

HOME_LIVING_THEMES = [
    "kitchen spice rack organizing aesthetic",
    "aesthetic pantry glass jars organization",
    "countertop cleaning sponge aesthetic",
    "minimalist cozy living room aesthetic",
    "home closet wardrobe organizing aesthetic",
    "aesthetic desk plant sunlight room",
    "making morning coffee kitchen aesthetic",
    "folding fresh laundry tidy basket"
]


def get_env_configs() -> Dict[str, str]:
    """Membaca tetapan API Pexels dan OpenRouter secara dinamik."""
    pexels_key = (
        os.getenv("IRCM_PEXELS_API_KEY", "").strip()
        or os.getenv("PEXELS_API_KEY", "").strip()
    )
    base_url = (
        os.getenv("IRCM_OPENROUTER_BASE_URL", "").strip()
        or os.getenv("OPENROUTER_BASE_URL", "").strip()
    )
    api_key = (
        os.getenv("IRCM_OPENROUTER_API_KEY", "").strip()
        or os.getenv("OPENROUTER_API_KEY", "").strip()
    )
    primary_vision = (
        os.getenv("IRCM_MODEL_VISION", "").strip()
        or os.getenv("MODEL_VISION", "").strip()
        or "dots-studio/dots-3-note-preview:free"
    )
    fallback_vision = (
        os.getenv("IRCM_MODEL_VISION_FALLBACK_1", "").strip()
        or os.getenv("MODEL_VISION_FALLBACK_1", "").strip()
        or "nvidia/nemotron-3-nano-omni-30b-a3b-reasoning:free"
    )

    return {
        "pexels_key": pexels_key,
        "base_url": base_url if not base_url.endswith("/chat/completions") else base_url.replace("/chat/completions", ""),
        "api_key": api_key,
        "primary_vision": primary_vision,
        "fallback_vision": fallback_vision,
    }


def is_safe_and_faceless(video_item: Dict[str, Any]) -> bool:
    """Menolak sebarang klip yang mengandungi perkataan muka atau manusia."""
    url_slug = str(video_item.get("url", "")).lower()
    for bad_word in FORBIDDEN_KEYWORDS:
        pattern = rf'(?:^|[\-_/]){re.escape(bad_word)}(?:$|[\-_/])'
        if re.search(pattern, url_slug):
            return False
    return True


# ==============================================================================
# 2. ENJIN CARIAN & MUAT TURUN PEXELS
# ==============================================================================

def fetch_pexels_broll_clips(
    api_key: str,
    query: str,
    needed_count: int = 5,
    batch_size: int = 70
) -> List[Dict[str, Any]]:
    """Menghantar 1 permintaan API ke Pexels (per_page=70) dan memilih 4-5 klip vertikal."""
    print(f"\n📡 [PEXELS API] Menghantar 1 request (per_page={batch_size}) Carian: '{query}'...")

    if not api_key:
        print("❌ [PEXELS ERROR] Kunci IRCM_PEXELS_API_KEY tidak ditemui.")
        return []

    url = "https://api.pexels.com/videos/search"
    headers = {"Authorization": api_key}
    params = {
        "query": query,
        "orientation": "portrait",
        "per_page": batch_size,
        "size": "medium",
    }

    try:
        res = requests.get(url, headers=headers, params=params, timeout=25)
        if res.status_code != 200:
            print(f"❌ [PEXELS HTTP ERROR] {res.status_code}: {res.text}")
            return []

        raw_videos = res.json().get("videos", [])
        print(f"  📥 Diterima {len(raw_videos)} calon video mentah dari Pexels API.")

        selected = []
        for vid in raw_videos:
            vid_id = str(vid.get("id"))
            dur = vid.get("duration", 0)
            files = vid.get("video_files", [])

            if not is_safe_and_faceless(vid):
                continue

            best_file = None
            for f in files:
                if f.get("file_type") == "video/mp4":
                    w = f.get("width") or 0
                    h = f.get("height") or 0
                    if h >= w and h >= 720:
                        best_file = f
                        break

            if not best_file and files:
                for f in files:
                    if f.get("file_type") == "video/mp4":
                        best_file = f
                        break

            if best_file and "link" in best_file:
                selected.append({
                    "id": vid_id,
                    "duration": dur,
                    "url": best_file["link"],
                    "width": best_file.get("width"),
                    "height": best_file.get("height"),
                })

            if len(selected) >= needed_count:
                break

        print(f"  🎯 Berjaya memilih {len(selected)} klip vertikal 9:16 bebas muka.")
        return selected

    except Exception as e:
        print(f"❌ [PEXELS EXCEPTION] {e}")
        return []


def download_temp_clip(url: str, prefix: str = "pex_clip") -> str:
    """Memuat turun fail video ke direktori temp/."""
    try:
        res = requests.get(url, headers={"User-Agent": "Mozilla/5.0"}, stream=True, timeout=30)
        if res.status_code == 200:
            tmp = tempfile.NamedTemporaryFile(suffix=".mp4", prefix=f"{prefix}_", dir=TEMP_DIR, delete=False)
            for chunk in res.iter_content(chunk_size=1024 * 1024):
                if chunk:
                    tmp.write(chunk)
            tmp.close()
            return tmp.name
    except Exception as e:
        print(f"  ⚠️ Ralat muat turun klip: {e}")
    return ""


# ==============================================================================
# 3. ENJIN METADATA & INTEGRASI AUDIO MP4 TEMPATAN
# ==============================================================================

def detect_audio_vibe(title: str, artist: str) -> str:
    """Mengenal pasti emosi dan vibe muzik untuk rujukan AI Persona Mama."""
    text = f"{title} {artist}".lower()
    if any(k in text for k in ["cozy", "pantry", "morning", "kitchen", "peace", "calm", "acoustic", "coffee"]):
        return "Suasana Pagi Tenang, Selesa & Terapi Susun Atur Rumah"
    elif any(k in text for k in ["upbeat", "fresh", "breeze", "clean", "spring", "bright", "work"]):
        return "Rentak Ceria & Bertenaga Mengemas Rumah"
    elif any(k in text for k in ["lofi", "relax", "soft", "ambient", "warm"]):
        return "Lo-Fi Lembut & Santai Waktu Petang"
    return "Muzik Estetik Santai Impian Rumahku"


def extract_music_metadata(song_path: str, filename: str) -> Dict[str, str]:
    """Mengekstrak maklumat metadata tajuk, artis dan vibe daripada fail audio."""
    base_name = os.path.splitext(filename)[0]
    clean_title = re.sub(r'[_\-]+', ' ', base_name).strip()
    clean_title = re.sub(r'\b(30s|40s|60s|loop|reels|tiktok|sound|audio)\b', '', clean_title, flags=re.I)
    clean_title = re.sub(r'\s+', ' ', clean_title).strip().title()

    title = clean_title or "Impian Rumahku Melody"
    artist = "Impian Rumahku Composer"

    if MutagenFile:
        try:
            tag = MutagenFile(song_path)
            if tag and hasattr(tag, "get"):
                raw_title = str(tag.get("\xa9nam", [""])[0] if isinstance(tag.get("\xa9nam"), list) else tag.get("\xa9nam", ""))
                raw_artist = str(tag.get("\xa9ART", [""])[0] if isinstance(tag.get("\xa9ART"), list) else tag.get("\xa9ART", ""))
                if raw_title and not raw_title.strip().isdigit():
                    title = raw_title.strip()
                if raw_artist and not raw_artist.strip().isdigit():
                    artist = raw_artist.strip()
        except Exception:
            pass

    vibe = detect_audio_vibe(title, artist)

    return {
        "title": title,
        "artist": artist,
        "vibe": vibe,
        "filename": filename,
        "file_path": song_path
    }


def pick_random_music_mp4(target_duration: int = 35) -> Tuple[Optional[Any], Dict[str, str]]:
    """Memilih fail muzik rawak .mp4 dan memotong durasi tepat 30-40 saat."""
    default_meta = {
        "title": "Aesthetic Home Ambient",
        "artist": "Cerita Mama",
        "vibe": "Santai & Tenang",
        "filename": "Default Audio",
        "file_path": ""
    }

    music_files = [f for f in os.listdir(MUSIC_DIR) if f.lower().endswith(".mp4")]
    if not music_files:
        music_files = [f for f in os.listdir(MUSIC_DIR) if f.lower().endswith((".mp3", ".m4a", ".wav"))]

    if not music_files:
        print(f"  ⚠️ Tiada fail muzik (.mp4/.mp3) di {MUSIC_DIR}. Video akan dijana tanpa muzik latar.")
        return None, default_meta

    chosen_file = random.choice(music_files)
    song_path = str(MUSIC_DIR / chosen_file)
    meta = extract_music_metadata(song_path, chosen_file)

    print(f"  🎵 [MUZIK DIPILIH]: '{meta['title']}' | Artis: '{meta['artist']}' | Vibe: '{meta['vibe']}'")

    try:
        audio = AudioFileClip(song_path)
        audio_dur = int(audio.duration)

        start = 0
        if audio_dur > target_duration + 3:
            start = random.randint(0, max(0, audio_dur - target_duration - 2))
        end = min(start + target_duration, audio_dur)

        if hasattr(audio, "subclipped"):
            cut_audio = audio.subclipped(start, end)
        else:
            cut_audio = audio.subclip(start, end)

        return cut_audio, meta
    except Exception as e:
        print(f"  ⚠️ Ralat memproses audio: {e}")
        return None, meta


# ==============================================================================
# 4. ENJIN PERCANTUMAN VIDEO REELS (DURASI 30 - 40 SAAT)
# ==============================================================================

def render_reels_video_30_40s(
    clips_data: List[Dict[str, Any]],
    target_min: int = 30,
    target_max: int = 40
) -> Tuple[Optional[str], Dict[str, str], int]:
    """Mencantumkan 4-5 klip Pexels ke resolusi 1080x1920 (9:16) dengan durasi 30-40 saat."""
    print(f"\n🎬 [MOVIEPY STITCHER] Memulakan pemprosesan {len(clips_data)} klip video...")

    clip_count = len(clips_data)
    if clip_count < 4:
        print(f"❌ [RALAT] Klip video tidak mencukupi ({clip_count} klip). Minima 4 klip diperlukan.")
        return None, {}, 0

    target_total = 35
    per_clip_duration = target_total // clip_count
    downloaded_files = []
    loaded_clips = []

    try:
        for idx, item in enumerate(clips_data, 1):
            print(f"  📥 [Klip {idx}/{clip_count}] Memuat turun ID {item['id']}...")
            dl_path = download_temp_clip(item["url"], prefix=f"clip_{idx}")
            if dl_path and os.path.exists(dl_path):
                downloaded_files.append(dl_path)
                v_clip = VideoFileClip(dl_path)

                clip_dur = min(v_clip.duration, per_clip_duration)
                if hasattr(v_clip, "subclipped"):
                    v_clip = v_clip.subclipped(0, clip_dur)
                else:
                    v_clip = v_clip.subclip(0, clip_dur)

                # Buang audio asal Pexels
                if hasattr(v_clip, "without_audio"):
                    v_clip = v_clip.without_audio()
                else:
                    v_clip = v_clip.set_audio(None)

                # Standardkan ke 1080x1920 (9:16 Portrait)
                if hasattr(v_clip, "resized"):
                    v_clip = v_clip.resized((1080, 1920))
                elif hasattr(v_clip, "resize"):
                    v_clip = v_clip.resize((1080, 1920))

                loaded_clips.append(v_clip)

        if len(loaded_clips) < 4:
            print("❌ Gagal memuatkan sekurang-kurangnya 4 klip video.")
            return None, {}, 0

        stitched = concatenate_videoclips(loaded_clips, method="compose")
        final_duration = int(stitched.duration)

        # Hadkan dalam julat 30 hingga 40 Saat
        if final_duration < target_min:
            print(f"  ⚠️ Durasi {final_duration}s di bawah {target_min}s. Diselaraskan.")
        elif final_duration > target_max:
            if hasattr(stitched, "subclipped"):
                stitched = stitched.subclipped(0, target_max)
            else:
                stitched = stitched.subclip(0, target_max)
            final_duration = target_max

        print(f"  ⏱️ Jumlah durasi akhir video: {final_duration} saat (Menepati sasaran 30-40s).")

        bg_audio, music_meta = pick_random_music_mp4(target_duration=final_duration)
        if bg_audio:
            if hasattr(stitched, "with_audio"):
                stitched = stitched.with_audio(bg_audio)
            else:
                stitched = stitched.set_audio(bg_audio)

        timestamp_str = int(time.time())
        output_filename = f"pexels_mama_reel_{timestamp_str}.mp4"
        output_filepath = str(OUTPUT_DIR / output_filename)

        print(f"  ⚙️ Menjana fail akhir: {output_filepath}...")
        stitched.write_videofile(
            output_filepath,
            fps=24,
            codec="libx264",
            audio_codec="aac",
            preset="fast",
            threads=4,
            logger=None,
        )

        stitched.close()
        for c in loaded_clips:
            c.close()
        if bg_audio:
            bg_audio.close()

        return output_filepath, music_meta, final_duration

    finally:
        for fpath in downloaded_files:
            if os.path.exists(fpath):
                try:
                    os.remove(fpath)
                except Exception:
                    pass


# ==============================================================================
# 5. EKSTRAK 4 KEYFRAME SNAPSHOTS TERMAMPAT (TOTAL PAYLOAD ~45KB)
# ==============================================================================

def capture_and_compress_multi_keyframes(
    video_path: str,
    num_frames: int = 4,
    max_dimension: int = 384,
    quality: int = 65
) -> List[Dict[str, Any]]:
    """
    Mengekstrak 4 bingkai foto pada titik kronologi berbeza merentas durasi video.
    Setiap bingkai dimampatkan ke JPEG ~10KB untuk memastikan kelajuan maksimum API.
    """
    frames_data = []
    try:
        clip = VideoFileClip(video_path)
        duration = clip.duration

        # Titik masa sampel: 15%, 40%, 65%, dan 90% durasi video
        percentages = [0.15, 0.40, 0.65, 0.90][:num_frames]
        sample_times = [round(duration * p, 1) for p in percentages]

        print(f"\n📸 [MULTI-KEYFRAME] Mengekstrak {num_frames} bingkai foto pada saat: {sample_times}...")

        for idx, sec in enumerate(sample_times, 1):
            valid_sec = min(sec, max(0.5, duration - 0.5))
            frame_arr = clip.get_frame(valid_sec)

            img = Image.fromarray(frame_arr)
            if img.mode in ("RGBA", "P"):
                img = img.convert("RGB")

            img.thumbnail((max_dimension, max_dimension), Image.Resampling.LANCZOS)

            buffer = BytesIO()
            img.save(buffer, format="JPEG", quality=quality, optimize=True)
            compressed_bytes = buffer.getvalue()
            kb_size = len(compressed_bytes) / 1024

            b64_str = base64.b64encode(compressed_bytes).decode("utf-8")
            data_uri = f"data:image/jpeg;base64,{b64_str}"

            frames_data.append({
                "frame_index": idx,
                "timestamp_seconds": valid_sec,
                "resolution": f"{img.size[0]}x{img.size[1]}",
                "kb_size": round(kb_size, 1),
                "data_uri": data_uri
            })
            print(f"   🖼️ [Frame {idx}/{num_frames} @ {valid_sec}s] Resolusi: {img.size} | Saiz: {kb_size:.1f} KB")

        clip.close()
        total_kb = sum(f["kb_size"] for f in frames_data)
        print(f"  📦 [TOTAL VISION PAYLOAD] {len(frames_data)} keping foto berjumlah {total_kb:.1f} KB (Sangat Ringan).")
        return frames_data

    except Exception as e:
        print(f"⚠️ [MULTI-KEYFRAME ERROR] Gagal mengekstrak bingkai video: {e}")
        return []


def clean_vision_response(text: str) -> str:
    """Membersihkan tag pemikiran AI, simbol rosak dan mengehadkan teks <= 500 aksara."""
    if not text:
        return ""
    cleaned = re.sub(r"<think>.*?</think>", "", text, flags=re.DOTALL)
    cleaned = re.sub(r"```json\s*", "", cleaned)
    cleaned = re.sub(r"```\s*", "", cleaned)
    cleaned = cleaned.strip().strip('"').strip("'")

    if len(cleaned) > 500:
        trimmed = cleaned[:500]
        match = re.search(r"^([\s\S]*[.!?])", trimmed)
        cleaned = match.group(1).strip() if match else trimmed.rstrip() + "..."
    return cleaned


def analyze_multi_keyframes_with_vision(
    keyframes_list: List[Dict[str, Any]],
    video_title: str,
    music_meta: Dict[str, str],
    cfg: Dict[str, str]
) -> Tuple[str, str]:
    """
    Menghantar 4 bingkai foto video ke OpenRouter Vision API:
    - Primary Model 2x (delay 2s)
    - Fallback Model 1 2x (delay 2s)
    - Temperature = 0.40, Had panjang ~500 aksara.
    """
    endpoint = f"{cfg['base_url']}/chat/completions"
    api_key = cfg["api_key"]
    primary_model = cfg["primary_vision"]
    fallback_model = cfg["fallback_vision"]

    if not api_key or not cfg["base_url"] or not keyframes_list:
        return "Visual review not generated due to missing OpenRouter credentials.", "none"

    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }

    system_prompt = (
        "You are an articulate, educated 30-something English lifestyle creator and home aesthetic curator.\n"
        "TASK:\n"
        "You are given 4 chronological keyframe snapshots capturing different scenes of an aesthetic home and lifestyle video reel.\n"
        "Observe the progression of scenes across these frames and provide a cohesive, vibrant micro-review in ENGLISH.\n"
        "Describe the visible aesthetic details, tidy organization, pleasant lighting, and soothing lifestyle ambiance.\n\n"
        "STRICT RULES:\n"
        "1. Write strictly in natural, eloquent ENGLISH.\n"
        "2. Total length MUST be around 350 to 500 characters.\n"
        "3. Synthesize the visual flow seen across the chronological frames into one smooth paragraph.\n"
        "4. Return ONLY the review paragraph with clean punctuation without emojis, hashtags, or conversational intros."
    )

    user_text = (
        f"Video Theme: {video_title}\n"
        f"Background Music: {music_meta.get('title')} ({music_meta.get('artist')})\n"
        f"Music Vibe: {music_meta.get('vibe')}\n\n"
        f"Review these 4 sequential scenes and provide your versatile English aesthetic review (around 500 characters):"
    )

    # Susun payload pelbagai imej (Multi-Image Content Array)
    user_content: List[Dict[str, Any]] = [{"type": "text", "text": user_text}]
    for kf in keyframes_list:
        user_content.append({
            "type": "image_url",
            "image_url": {"url": kf["data_uri"]}
        })

    models_to_try = [
        (primary_model, "Primary Vision"),
        (fallback_model, "Fallback Vision 1"),
    ]

    for model_name, model_label in models_to_try:
        print(f"\n🧠 [VISION ENGINE] Mencuba {model_label}: '{model_name}' (4 Frames)...")
        payload = {
            "model": model_name,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_content},
            ],
            "temperature": 0.40,
        }

        for attempt in range(1, 3):
            print(f"   📡 [Percubaan {attempt}/2] Menghantar permintaan ke {model_name}...")
            try:
                res = requests.post(endpoint, headers=headers, json=payload, timeout=(10, 40))
                if res.status_code == 200:
                    raw = res.json().get("choices", [{}])[0].get("message", {}).get("content", "")
                    cleaned = clean_vision_response(raw)
                    if len(cleaned) >= 200:
                        print(f"   ✅ [{model_label} Berjaya] Ulasan sintesis 4 frame dijana ({len(cleaned)} aksara)!")
                        return cleaned, model_name
                    else:
                        print(f"   ⚠️ [Output Terlalu Pendek] ({len(cleaned)} aksara).")
                else:
                    print(f"   ⚠️ [HTTP {res.status_code}] {res.text[:80]}")
            except Exception as e:
                print(f"   ⚠️ [Ralat Sambungan Vision]: {e}")

            if attempt < 2:
                print("   ⏳ Menunggu 2 saat sebelum percubaan seterusnya...")
                time.sleep(2)

        print(f"   ❌ {model_label} gagal selepas 2 percubaan. Beralih ke model sandaran seterusnya...")

    # Fallback Asas jika semua model gagal
    fallback_text = (
        f"This beautifully composed home aesthetic reel gracefully transitions through thoughtfully curated living spaces. "
        f"From organized countertop surfaces to warm, sunlit corners, each scene seamlessly highlights modern functionality and calming tidy aesthetics. "
        f"Paired with soothing background melodies, it inspires delightful everyday decluttering and peaceful home living."
    )
    return fallback_text, "hardcoded_fallback"


# ==============================================================================
# 6. PELAKSANA UTAMA (MAIN TEST RUNNER)
# ==============================================================================

def run_pexels_render_experiment():
    print("=" * 75)
    print("🧪 [DIAGNOSTIC TEST v3] ENJIN RENDERING VIDEO PEXELS 30-40s + 4-KEYFRAME VISION")
    print("   Impian Rumahku & Cerita Mama Ecosystem")
    print("=" * 75)

    cfg = get_env_configs()
    selected_theme = random.choice(HOME_LIVING_THEMES)
    video_title = selected_theme.title()

    print(f"🎯 [TEMA DIPILIH]: '{video_title}'")

    # 1. Pexels API Batch Fetch (70 video) -> Pilih 4-5 klip
    clips = fetch_pexels_broll_clips(
        api_key=cfg["pexels_key"],
        query=selected_theme,
        needed_count=5,
        batch_size=70
    )

    if len(clips) < 4:
        print(f"❌ [ABORT] Tidak cukup klip Pexels ({len(clips)} diperoleh). Sila semak kata kunci atau kuota API.")
        return

    print(f"\n📋 [SENARAI KLIP TERPILIH ({len(clips)} Video)]:")
    for idx, c in enumerate(clips, 1):
        print(f"   {idx}. Pexels ID: {c['id']} | Resolusi: {c['width']}x{c['height']} | Durasi Asal: {c['duration']}s")

    # 2. Cantumkan 4-5 Klip + Audio .mp4 Tempatan (Sasaran: 30 - 40 Saat)
    rendered_path, music_meta, duration_sec = render_reels_video_30_40s(clips, target_min=30, target_max=40)

    if not rendered_path or not os.path.exists(rendered_path):
        print("❌ [ABORT] Gagal menjana fail video akhir.")
        return

    # 3. Ekstrak 4 Keyframe Kronologi (<15KB setiap satu)
    keyframes = capture_and_compress_multi_keyframes(rendered_path, num_frames=4, max_dimension=384, quality=65)

    # 4. Analisis Vision AI (4 Frames)
    print("\n👁️ [STEP VISION AI] Memulakan ulasan estetik visual 4-Frame (Suhu: 0.40, Had: ~500 aksara)...")
    vision_review, model_used = analyze_multi_keyframes_with_vision(
        keyframes_list=keyframes,
        video_title=video_title,
        music_meta=music_meta,
        cfg=cfg
    )

    # 5. Simpan Payload Debugging ke temp/
    debug_payload = {
        "status": "success",
        "video_title": video_title,
        "video_theme_keyword": selected_theme,
        "rendered_video_path": rendered_path,
        "video_duration_seconds": duration_sec,
        "keyframes_extracted": [
            {"frame": kf["frame_index"], "timestamp": kf["timestamp_seconds"], "size": f"{kf['kb_size']} KB"}
            for kf in keyframes
        ],
        "clips_used": clips,
        "music_metadata": music_meta,
        "vision_ai_review": vision_review,
        "vision_model_used": model_used,
        "review_char_count": len(vision_review),
        "timestamp": time.strftime("%Y-%m-%d %H:%M:%S", time.localtime()),
    }

    debug_json_path = TEMP_DIR / "test_pexels_render_result.json"
    with open(debug_json_path, "w", encoding="utf-8") as f:
        json.dump(debug_payload, f, indent=2, ensure_ascii=False)

    # 6. Paparan Terminal Lengkap
    print("\n" + "=" * 75)
    print("📊 [HASIL KEPUTUSAN EKSPERIMEN LENGKAP]")
    print("=" * 75)
    print(f"🎬 Tajuk Video         : {video_title}")
    print(f"📁 Lokasi Video Siap   : {rendered_path}")
    print(f"⏱️ Durasi Video        : {duration_sec} Saat (Sasaran 30 - 40s)")
    print(f"🖼️ Bilangan Keyframes  : {len(keyframes)} Bingkai Kronologi (Total: {sum(k['kb_size'] for k in keyframes):.1f} KB)")
    print(f"🎵 Muzik Latar         : {music_meta.get('title')} ({music_meta.get('artist')})")
    print(f"✨ Vibe Muzik          : {music_meta.get('vibe')}")
    print(f"🧠 Model Vision AI     : {model_used}")
    print(f"📏 Panjang Ulasan      : {len(vision_review)} Aksara (Sasaran: ~500 aksara)")
    print("-" * 75)
    print(f"📝 ULASAN BAHASA INGGERIS VISION AI:\n\"{vision_review}\"")
    print("-" * 75)
    print(f"💾 Payload JSON disimpan sementara di: {debug_json_path}")
    print("=" * 75)


if __name__ == "__main__":
    run_pexels_render_experiment()