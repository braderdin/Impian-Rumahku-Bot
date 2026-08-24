#!/usr/bin/env python3
"""
Dedicated Audio Selection, Metadata & Beat-Sync Engine
Impian Rumahku & Cerita Mama Ecosystem
Features:
- Selects random .mp4 or .mp3 music from assets/music/
- Mutagen ID3 metadata extraction (Title, Artist, Genre, File Info)
- Universal audio array decoder via MoviePy (seamlessly handles .mp4 video containers)
- Librosa BPM tempo & beat tracking integration for smart video cut-points
- Audio vibe & mood detection tailored for Home & Living aesthetic storytelling
- Duration trimming with MoviePy AudioFileClip compatibility
"""

import os
import re
import sys
import random
import numpy as np
from pathlib import Path
from typing import Dict, Any, Tuple, Optional, List

# Setup Project Root Path
PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

# Mutagen Tag Reader
try:
    from mutagen import File as MutagenFile
except ImportError:
    MutagenFile = None

# Librosa Audio Analysis
try:
    import librosa
    LIBROSA_AVAILABLE = True
except ImportError:
    librosa = None
    LIBROSA_AVAILABLE = False

# MoviePy Audio Compatibility
try:
    from moviepy import AudioFileClip
except ImportError:
    from moviepy.editor import AudioFileClip

MUSIC_DIR = PROJECT_ROOT / "assets" / "music"
MUSIC_DIR.mkdir(parents=True, exist_ok=True)


def detect_audio_vibe(title: str, artist: str, tempo_bpm: float = 0.0) -> str:
    """
    Mengenal pasti emosi dan vibe muzik untuk rujukan AI Persona Mama
    berpandukan kata kunci tajuk dan nilai BPM Librosa.
    """
    text = f"{title} {artist}".lower()
    bpm_desc = f" ({int(tempo_bpm)} BPM)" if tempo_bpm > 0 else ""

    if any(k in text for k in ["cozy", "pantry", "morning", "kitchen", "peace", "calm", "acoustic", "coffee"]):
        return f"Suasana Pagi Tenang, Selesa & Terapi Susun Atur Rumah{bpm_desc}"
    elif any(k in text for k in ["upbeat", "fresh", "breeze", "clean", "spring", "bright", "work", "strut", "push"]):
        return f"Rentak Ceria & Bertenaga Mengemas Rumah{bpm_desc}"
    elif any(k in text for k in ["lofi", "relax", "soft", "ambient", "warm", "chill"]):
        return f"Lo-Fi Lembut & Santai Waktu Petang{bpm_desc}"
    
    if tempo_bpm > 115:
        return f"Rentak Moden Ceria & Dinamik{bpm_desc}"
    elif tempo_bpm > 85:
        return f"Alunan Sederhana Santai & Harmoni Ruang{bpm_desc}"
    
    return f"Muzik Estetik Santai Impian Rumahku{bpm_desc}"


def extract_music_metadata(song_path: str, filename: str) -> Dict[str, Any]:
    """
    Mengekstrak maklumat metadata tajuk, artis dan fail audio menggunakan Mutagen.
    """
    base_name = os.path.splitext(filename)[0]
    clean_title = re.sub(r'[_\-]+', ' ', base_name).strip()
    clean_title = re.sub(r'\b(30s|40s|60s|loop|reels|tiktok|sound|audio)\b', '', clean_title, flags=re.I)
    clean_title = re.sub(r'\s+', ' ', clean_title).strip().title()

    title = clean_title or "Impian Rumahku Melody"
    artist = "Impian Rumahku Composer"
    genre = "Home & Lifestyle Ambient"

    if MutagenFile and os.path.exists(song_path):
        try:
            tag = MutagenFile(song_path)
            if tag and hasattr(tag, "get"):
                raw_title = tag.get("\xa9nam") or tag.get("TIT2") or tag.get("title")
                raw_artist = tag.get("\xa9ART") or tag.get("TPE1") or tag.get("artist")
                raw_genre = tag.get("\xa9gen") or tag.get("TCON") or tag.get("genre")

                if isinstance(raw_title, list): raw_title = raw_title[0]
                if isinstance(raw_artist, list): raw_artist = raw_artist[0]
                if isinstance(raw_genre, list): raw_genre = raw_genre[0]

                if raw_title and not str(raw_title).strip().isdigit():
                    title = str(raw_title).strip()
                if raw_artist and not str(raw_artist).strip().isdigit():
                    artist = str(raw_artist).strip()
                if raw_genre:
                    genre = str(raw_genre).strip()
        except Exception:
            pass

    return {
        "title": title,
        "artist": artist,
        "genre": genre,
        "filename": filename,
        "file_path": song_path
    }


def analyze_tempo_and_beat_timestamps(song_path: str, max_duration: int = 45) -> Tuple[float, List[float]]:
    """
    Menggunakan MoviePy untuk membaca gelombang audio (.mp4/.mp3) secara sejagat,
    kemudian menyalurkan array mono ke Librosa bagi mengesan tempo (BPM) dan cap masa rentak ketukan.
    Memulangkan: (tempo_bpm, list_of_beat_times_in_seconds).
    """
    if not LIBROSA_AVAILABLE or not os.path.exists(song_path):
        return 0.0, []

    sr = 22050
    audio_clip = None

    try:
        # Baca audio melalui MoviePy untuk mengelakkan isu 'Format not recognised' pada fail .mp4
        audio_clip = AudioFileClip(song_path)
        actual_duration = min(float(audio_clip.duration), float(max_duration))

        if hasattr(audio_clip, "subclipped"):
            sub_audio = audio_clip.subclipped(0, actual_duration)
        else:
            sub_audio = audio_clip.subclip(0, actual_duration)

        sound_array = sub_audio.to_soundarray(fps=sr)
        sub_audio.close()
        audio_clip.close()

        # Tukar stereo ke mono jika perlu
        if sound_array.ndim > 1:
            y = np.mean(sound_array, axis=1).astype(np.float32)
        else:
            y = sound_array.astype(np.float32)

        # Analisis Beat Tracking Librosa
        tempo, beat_frames = librosa.beat.beat_track(y=y, sr=sr)
        bpm_val = float(tempo.item()) if hasattr(tempo, "item") else float(tempo)
        beat_times = librosa.frames_to_time(beat_frames, sr=sr).tolist()

        print(f"  🥁 [LIBROSA BEAT-SYNC] Tempo Dikesan: {bpm_val:.1f} BPM | {len(beat_times)} Ketukan Rentak.")
        return round(bpm_val, 1), [round(t, 2) for t in beat_times]

    except Exception as e:
        print(f"  ⚠️ [LIBROSA WARN] Gagal menganalisis rentak: {e}")
        return 0.0, []
    finally:
        if audio_clip:
            try:
                audio_clip.close()
            except Exception:
                pass


def get_random_music_track(target_duration: int = 35) -> Tuple[Optional[Any], Dict[str, Any]]:
    """
    Memilih fail muzik rawak (.mp4 / .mp3), menganalisis rentak Librosa,
    dan memulangkan klip AudioFileClip yang telah dipotong mengikut durasi sasaran.
    """
    default_meta = {
        "title": "Aesthetic Home Ambient",
        "artist": "Cerita Mama",
        "genre": "Home & Living",
        "vibe": "Santai & Tenang",
        "filename": "Default Audio",
        "file_path": "",
        "tempo_bpm": 0.0,
        "beat_timestamps": []
    }

    # Utamakan fail format .mp4, disusuli format audio lain
    music_files = [f for f in os.listdir(MUSIC_DIR) if f.lower().endswith(".mp4")]
    if not music_files:
        music_files = [f for f in os.listdir(MUSIC_DIR) if f.lower().endswith((".mp3", ".m4a", ".wav"))]

    if not music_files:
        print(f"  ⚠️ [AUDIO WARN] Tiada fail muzik (.mp4/.mp3) di {MUSIC_DIR}. Video akan dijana tanpa muzik.")
        return None, default_meta

    chosen_file = random.choice(music_files)
    song_path = str(MUSIC_DIR / chosen_file)
    meta = extract_music_metadata(song_path, chosen_file)

    # Analisis Librosa BPM & Beats menggunakan pengekstrak MoviePy array
    bpm, beats = analyze_tempo_and_beat_timestamps(song_path, max_duration=target_duration + 5)
    meta["tempo_bpm"] = bpm
    meta["beat_timestamps"] = beats
    meta["vibe"] = detect_audio_vibe(meta["title"], meta["artist"], tempo_bpm=bpm)

    print(f"  🎵 [MUZIK TERPILIH]: '{meta['title']}' | Artis: '{meta['artist']}' | Vibe: '{meta['vibe']}'")

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
        print(f"  ⚠️ [AUDIO PROCESS ERROR]: {e}")
        return None, meta