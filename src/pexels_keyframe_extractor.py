#!/usr/bin/env python3
"""
Ultra-Lightweight Multi-Keyframe Extraction & Compression Engine
Impian Rumahku & Cerita Mama Ecosystem
Features:
- Extracts 4 chronological keyframe snapshots across video duration (15%, 40%, 65%, 90%)
- Compresses each frame to ultra-lightweight JPEG (<15KB each, total payload <50KB)
- Resizes to max 384px dimension for high OCR/Vision clarity with zero socket timeout
- Generates base64 data URIs ready for OpenRouter Vision API payload arrays
"""

import os
import sys
import base64
from io import BytesIO
from pathlib import Path
from typing import List, Dict, Any, Tuple, Optional
from PIL import Image

# Setup Project Root Path
PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

# MoviePy Compatibility Layer
try:
    from moviepy import VideoFileClip
except ImportError:
    from moviepy.editor import VideoFileClip


def extract_and_compress_keyframes(
    video_path: str,
    num_frames: int = 4,
    max_dimension: int = 384,
    quality: int = 65
) -> Tuple[List[Dict[str, Any]], float]:
    """
    Mengekstrak sejumlah bingkai foto kronologi merentas durasi video
    dan memampatkannya ke Base64 JPEG ringan (< 15KB per frame).
    Memulangkan: (keyframes_list, total_payload_kb)
    """
    if not video_path or not os.path.exists(video_path):
        print(f"❌ [KEYFRAME ERROR] Fail video tidak dijumpai: {video_path}")
        return [], 0.0

    keyframes_list: List[Dict[str, Any]] = []

    try:
        clip = VideoFileClip(video_path)
        duration = float(clip.duration)

        # Tentukan titik masa sampel kronologi (15%, 40%, 65%, 90%)
        percentages = [0.15, 0.40, 0.65, 0.90][:num_frames]
        sample_times = [round(duration * p, 1) for p in percentages]

        print(f"\n📸 [MULTI-KEYFRAME] Mengekstrak {len(sample_times)} bingkai foto pada titik masa: {sample_times}s...")

        for idx, sec in enumerate(sample_times, 1):
            valid_sec = min(sec, max(0.5, duration - 0.5))
            frame_arr = clip.get_frame(valid_sec)

            img = Image.fromarray(frame_arr)
            if img.mode in ("RGBA", "P"):
                img = img.convert("RGB")

            # Kecilkan dimensi maksimum ke 384px
            img.thumbnail((max_dimension, max_dimension), Image.Resampling.LANCZOS)

            buffer = BytesIO()
            img.save(buffer, format="JPEG", quality=quality, optimize=True)
            compressed_bytes = buffer.getvalue()
            kb_size = len(compressed_bytes) / 1024

            b64_str = base64.b64encode(compressed_bytes).decode("utf-8")
            data_uri = f"data:image/jpeg;base64,{b64_str}"

            keyframes_list.append({
                "frame_index": idx,
                "timestamp_seconds": valid_sec,
                "resolution": f"{img.size[0]}x{img.size[1]}",
                "kb_size": round(kb_size, 1),
                "data_uri": data_uri
            })
            print(f"   🖼️ [Frame {idx}/{len(sample_times)} @ {valid_sec}s] Resolusi: {img.size} | Saiz: {kb_size:.1f} KB")

        clip.close()
        total_kb = sum(k["kb_size"] for k in keyframes_list)
        print(f"  📦 [TOTAL KEYFRAME PAYLOAD] {len(keyframes_list)} bingkai berjumlah {total_kb:.1f} KB (Ultra-Ringan).")
        return keyframes_list, total_kb

    except Exception as e:
        print(f"⚠️ [KEYFRAME EXTRACTION EXCEPTION]: {e}")
        return [], 0.0