#!/usr/bin/env python3
"""
Hardcore Faceless Home & Living Visual Seeds Bank
Impian Rumahku & Cerita Mama Ecosystem
Features:
- 40 curated English faceless B-Roll search keywords for Home & Living, organizing & decor
- Strict exclusion of human faces, models, gamers, and sensitive animals
- ASCII sanitization helper to clean raw AI text outputs
- Random seed sampler for AI prompt inspiration and hardcoded fallback
"""

import re
import random
from typing import List

# ==============================================================================
# 40 HARDCORE FACELESS HOME & LIVING VISUAL SEEDS (B-ROLL & OBJECT FOCUS ONLY)
# ==============================================================================
PEXELS_HOME_LIVING_SEEDS = [
    "kitchen spice rack organizing aesthetic",
    "aesthetic pantry glass jars organization",
    "countertop cleaning sponge aesthetic",
    "minimalist cozy living room aesthetic",
    "home closet wardrobe organizing aesthetic",
    "aesthetic desk plant sunlight room",
    "making morning coffee kitchen aesthetic",
    "folding fresh laundry tidy basket",
    "aesthetic ceramic dinnerware kitchen",
    "fridge organization clear acrylic bins",
    "neat kitchen drawer cutlery organizer",
    "bedroom aesthetic morning sunlight bed",
    "aesthetic wooden cutting board kitchen",
    "linen closet towels neatly folded",
    "coffee beans brewing espresso machine",
    "minimalist dining table flowers vase",
    "home entryway shoes rack organizer",
    "kitchen sink dishwashing aesthetic bubbles",
    "bathroom vanity skincare shelf organizing",
    "aesthetic modern bookshelf decor",
    "baking dough rolling pin aesthetic",
    "tea brewing glass teapot aesthetic",
    "aesthetic scented candle burning cozy",
    "folding clothes wardrobe hangers",
    "aesthetic water kettle boiling steam",
    "kitchen knife cutting vegetables board",
    "wicker storage baskets home organizing",
    "window morning sunlight curtains breeze",
    "wiping kitchen induction stove clean",
    "coffee cup steaming on wooden table",
    "modern pantry cereal dispenser jars",
    "aesthetic glass tumbler ice cold drink",
    "washing fruits sink running water",
    "indoor houseplant watering leaves spray",
    "wooden kitchen utensils in ceramic holder",
    "aesthetic bed making linen duvet cozy",
    "bathroom clean towels stack aesthetic",
    "vacuum cleaner cleaning modern rug",
    "pouring milk into coffee glass mug",
    "sunlight casting shadows clean wall"
]


def sanitize_keyword(kw: str) -> str:
    """
    Membersihkan aksara rosak mojibake atau simbol bukan ASCII daripada kata kunci AI.
    Mengehadkan kepada perkataan abjad Latin standard (2-4 perkataan sahaja).
    """
    if not kw:
        return ""
    clean = re.sub(r'[^a-zA-Z0-9\s]', ' ', str(kw))
    words = [w.strip() for w in clean.split() if len(w.strip()) > 1]
    return " ".join(words[:4]).lower().strip()


def get_random_seeds(count: int = 5) -> List[str]:
    """
    Mengambil sampel rawak kata kunci benih untuk dijadikan rujukan inspirasi AI prompt.
    """
    sample_size = min(count, len(PEXELS_HOME_LIVING_SEEDS))
    return random.sample(PEXELS_HOME_LIVING_SEEDS, sample_size)


def get_fallback_seeds(count: int = 10) -> List[str]:
    """
    Memulangkan senarai kata kunci sandaran yang telah dibersihkan sekiranya AI offline.
    """
    shuffled = random.sample(PEXELS_HOME_LIVING_SEEDS, min(count, len(PEXELS_HOME_LIVING_SEEDS)))
    return [sanitize_keyword(k) for k in shuffled]