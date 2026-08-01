"""Approvisionnement des visuels de fond, un par scène.

Backends de stock (choisis automatiquement selon la clé d'API présente dans
l'environnement) :

* Pexels   — ``PEXELS_API_KEY``   (gratuit : https://www.pexels.com/api/)
* Pixabay  — ``PIXABAY_API_KEY``  (gratuit : https://pixabay.com/api/docs/)
* Unsplash — ``UNSPLASH_ACCESS_KEY``

Repli hors-ligne : un fond « cosmique » procédural est généré avec Pillow
(dégradé sombre déterministe + vignette + champ d'étoiles) à partir de la
requête. Aucune connexion n'est requise, ce qui rend l'usine fonctionnelle
partout ; sur une machine avec clé d'API, les vraies photos sont utilisées.

Tous les backends renvoient un PNG déjà recadré au format cible (cover).
"""

from __future__ import annotations

import hashlib
import io
import math
import os
import random
from typing import Optional

import requests
from PIL import Image, ImageDraw, ImageFilter


TIMEOUT = 25


# --------------------------------------------------------------------------- #
# Recadrage « cover » commun
# --------------------------------------------------------------------------- #
def _cover(img: Image.Image, w: int, h: int) -> Image.Image:
    """Recadre/redimensionne en remplissant WxH sans déformer (type CSS cover)."""
    img = img.convert("RGB")
    src_ratio = img.width / img.height
    dst_ratio = w / h
    if src_ratio > dst_ratio:            # source trop large -> on rogne les côtés
        new_w = int(img.height * dst_ratio)
        left = (img.width - new_w) // 2
        img = img.crop((left, 0, left + new_w, img.height))
    else:                                # source trop haute -> on rogne haut/bas
        new_h = int(img.width / dst_ratio)
        top = (img.height - new_h) // 2
        img = img.crop((0, top, img.width, top + new_h))
    return img.resize((w, h), Image.LANCZOS)


def _darken(img: Image.Image, factor: float = 0.55) -> Image.Image:
    """Assombrit l'image pour que les sous-titres blancs restent lisibles."""
    overlay = Image.new("RGB", img.size, (0, 0, 0))
    return Image.blend(img, overlay, 1 - factor)


# --------------------------------------------------------------------------- #
# Backends stock
# --------------------------------------------------------------------------- #
def _fetch_pexels(query: str) -> Optional[bytes]:
    key = os.environ.get("PEXELS_API_KEY")
    if not key:
        return None
    r = requests.get(
        "https://api.pexels.com/v1/search",
        headers={"Authorization": key},
        params={"query": query, "orientation": "portrait", "per_page": 1},
        timeout=TIMEOUT,
    )
    r.raise_for_status()
    photos = r.json().get("photos", [])
    if not photos:
        return None
    src = photos[0]["src"].get("portrait") or photos[0]["src"]["large"]
    return requests.get(src, timeout=TIMEOUT).content


def _fetch_pixabay(query: str) -> Optional[bytes]:
    key = os.environ.get("PIXABAY_API_KEY")
    if not key:
        return None
    r = requests.get(
        "https://pixabay.com/api/",
        params={"key": key, "q": query, "orientation": "vertical",
                "image_type": "photo", "per_page": 3, "safesearch": "true"},
        timeout=TIMEOUT,
    )
    r.raise_for_status()
    hits = r.json().get("hits", [])
    if not hits:
        return None
    return requests.get(hits[0]["largeImageURL"], timeout=TIMEOUT).content


def _fetch_unsplash(query: str) -> Optional[bytes]:
    key = os.environ.get("UNSPLASH_ACCESS_KEY")
    if not key:
        return None
    r = requests.get(
        "https://api.unsplash.com/search/photos",
        headers={"Authorization": f"Client-ID {key}"},
        params={"query": query, "orientation": "portrait", "per_page": 1},
        timeout=TIMEOUT,
    )
    r.raise_for_status()
    results = r.json().get("results", [])
    if not results:
        return None
    return requests.get(results[0]["urls"]["regular"], timeout=TIMEOUT).content


# --------------------------------------------------------------------------- #
# Repli procédural : fond cosmique déterministe
# --------------------------------------------------------------------------- #
# Palette sombre « cosmos » ; la teinte est choisie de façon déterministe à
# partir de la requête pour que chaque scène ait sa propre ambiance.
_PALETTE = [
    ((8, 14, 38), (30, 18, 66)),      # bleu nuit -> violet
    ((6, 20, 34), (12, 46, 58)),      # abysse -> sarcelle
    ((26, 10, 30), (58, 16, 40)),     # prune -> magenta sombre
    ((10, 16, 30), (40, 30, 20)),     # nuit -> brun chaud (noyau/foudre)
    ((4, 22, 26), (16, 40, 34)),      # vert profond (océan/aurore)
]


def _procedural(query: str, w: int, h: int) -> Image.Image:
    seed = int(hashlib.md5(query.encode()).hexdigest(), 16)
    rng = random.Random(seed)
    top, bottom = _PALETTE[seed % len(_PALETTE)]

    # Dégradé vertical.
    base = Image.new("RGB", (w, h))
    px = base.load()
    for y in range(h):
        t = y / (h - 1)
        # léger easing pour un fond plus « profond »
        t = t * t * (3 - 2 * t)
        r = int(top[0] + (bottom[0] - top[0]) * t)
        g = int(top[1] + (bottom[1] - top[1]) * t)
        b = int(top[2] + (bottom[2] - top[2]) * t)
        for x in range(w):
            px[x, y] = (r, g, b)

    # Halo lumineux décentré (comme une source stellaire).
    glow = Image.new("L", (w, h), 0)
    gd = ImageDraw.Draw(glow)
    cx = int(w * rng.uniform(0.25, 0.75))
    cy = int(h * rng.uniform(0.20, 0.45))
    rad = int(min(w, h) * rng.uniform(0.35, 0.55))
    gd.ellipse([cx - rad, cy - rad, cx + rad, cy + rad], fill=90)
    glow = glow.filter(ImageFilter.GaussianBlur(rad // 2))
    tint = Image.new("RGB", (w, h), (120, 140, 210))
    base = Image.composite(Image.blend(base, tint, 0.5), base, glow)

    # Champ d'étoiles.
    draw = ImageDraw.Draw(base)
    for _ in range(int(w * h / 5500)):
        x, y = rng.randint(0, w - 1), rng.randint(0, h - 1)
        b = rng.randint(120, 255)
        if rng.random() < 0.08:               # quelques étoiles plus grosses
            draw.ellipse([x - 1, y - 1, x + 1, y + 1], fill=(b, b, b))
        else:
            draw.point((x, y), fill=(b, b, b))

    # Vignette pour concentrer le regard au centre.
    vig = Image.new("L", (w, h), 0)
    vd = ImageDraw.Draw(vig)
    vd.ellipse([-w * 0.25, -h * 0.15, w * 1.25, h * 1.15], fill=255)
    vig = vig.filter(ImageFilter.GaussianBlur(min(w, h) // 6))
    dark = Image.new("RGB", (w, h), (0, 0, 0))
    base = Image.composite(base, dark, vig)
    return base


# --------------------------------------------------------------------------- #
# Point d'entrée
# --------------------------------------------------------------------------- #
def fetch_image(query: str, out_path: str, w: int, h: int) -> str:
    """Produit un PNG WxH pour ``query`` et renvoie ``out_path``.

    Ordre d'essai : Pexels -> Pixabay -> Unsplash -> fond procédural.
    Toute erreur réseau bascule silencieusement vers le repli suivant.
    """
    raw: Optional[bytes] = None
    for fetch in (_fetch_pexels, _fetch_pixabay, _fetch_unsplash):
        try:
            raw = fetch(query)
        except Exception:
            raw = None
        if raw:
            break

    if raw:
        img = _darken(_cover(Image.open(io.BytesIO(raw)), w, h))
    else:
        img = _procedural(query, w, h)

    img.save(out_path)
    return out_path
