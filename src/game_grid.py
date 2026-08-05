"""Rendu des grilles « Trouve l'intrus ».

Génère une image d'une grille d'emojis identiques dont une seule case diffère
(l'intrus). Deux variantes :

* grille normale (phase de recherche) ;
* grille « reveal » : tout est estompé sauf l'intrus, entouré d'un cercle
  lumineux, pour une révélation instantanée et satisfaisante.

Les emojis couleur sont rendus via Noto Color Emoji (strike bitmap 109 px,
redimensionné à la taille de case).
"""

from __future__ import annotations

import functools
import random
from typing import Tuple

from PIL import Image, ImageDraw, ImageFont

EMOJI_FONT = "/usr/share/fonts/truetype/noto/NotoColorEmoji.ttf"
TEXT_FONT = "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"
_STRIKE = 109  # seule taille bitmap disponible dans Noto Color Emoji

# Palette « mignon » : fond crème, panneau doux, accents chauds.
BG = (255, 244, 230)
PANEL = (255, 252, 246)
INK = (43, 43, 58)           # texte foncé
CIRCLE = (255, 74, 110)      # rose/rouge vif pour le cercle du reveal


def _centered_text(draw, cy, text, size, fill, w, outline=None):
    """Écrit ``text`` centré horizontalement, ancré verticalement sur ``cy``."""
    font = ImageFont.truetype(TEXT_FONT, size)
    tb = draw.textbbox((0, 0), text, font=font)
    tw, th = tb[2] - tb[0], tb[3] - tb[1]
    x = (w - tw) // 2 - tb[0]
    y = cy - th // 2 - tb[1]
    if outline:
        for dx in (-3, 0, 3):
            for dy in (-3, 0, 3):
                if dx or dy:
                    draw.text((x + dx, y + dy), text, font=font, fill=outline)
    draw.text((x, y), text, font=font, fill=fill)


@functools.lru_cache(maxsize=64)
def _emoji_tile(ch: str, size: int) -> Image.Image:
    """Rend un emoji centré dans une tuile RGBA de côté ``size``."""
    font = ImageFont.truetype(EMOJI_FONT, _STRIKE)
    big = Image.new("RGBA", (_STRIKE + 40, _STRIKE + 40), (0, 0, 0, 0))
    ImageDraw.Draw(big).text((20, 20), ch, font=font, embedded_color=True)
    big = big.crop(big.getbbox())
    # met à l'échelle en gardant le ratio
    scale = size / max(big.width, big.height)
    big = big.resize((max(1, int(big.width * scale)),
                      max(1, int(big.height * scale))), Image.LANCZOS)
    tile = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    tile.alpha_composite(big, ((size - big.width) // 2, (size - big.height) // 2))
    return tile


def _rounded(draw: ImageDraw.ImageDraw, box, radius, fill):
    draw.rounded_rectangle(box, radius=radius, fill=fill)


def render_grid(base: str, intruder: str, cols: int, rows: int, seed: int,
                w: int, h: int, reveal: bool = False,
                title: str | None = None, banner: str | None = None,
                cta: str | None = None
                ) -> Tuple[Image.Image, Tuple[int, int], int]:
    """Construit la grille et renvoie (image RGB, centre_intrus, taille_case)."""
    rng = random.Random(seed)
    intruder_idx = rng.randrange(cols * rows)

    img = Image.new("RGB", (w, h), BG)
    draw = ImageDraw.Draw(img)

    # Zone réservée : haut (titre/timer) et bas (CTA).
    top_margin = int(h * 0.15)
    bottom_margin = int(h * 0.10)
    side = int(w * 0.06)
    grid_w = w - 2 * side
    grid_h = h - top_margin - bottom_margin

    # Panneau arrondi de fond pour la grille.
    _rounded(draw, [side * 0.6, top_margin - side * 0.4,
                    w - side * 0.6, h - bottom_margin + side * 0.4],
             radius=int(w * 0.05), fill=PANEL)

    cell = min(grid_w // cols, grid_h // rows)
    emoji_size = int(cell * 0.82)
    # centre la grille dans la zone disponible
    gx = (w - cell * cols) // 2
    gy = top_margin + (grid_h - cell * rows) // 2

    intruder_center = (gx + cell // 2, gy + cell // 2)
    for idx in range(cols * rows):
        r, c = divmod(idx, cols)
        cx = gx + c * cell
        cy = gy + r * cell
        ch = intruder if idx == intruder_idx else base
        tile = _emoji_tile(ch, emoji_size)
        off = (cell - emoji_size) // 2
        img.paste(tile, (cx + off, cy + off), tile)
        if idx == intruder_idx:
            intruder_center = (cx + cell // 2, cy + cell // 2)

    if reveal:
        # Estompe toute la grille puis remet l'intrus en pleine lumière.
        veil = Image.new("RGBA", (w, h), (*PANEL, 205))
        img = Image.alpha_composite(img.convert("RGBA"), veil).convert("RGB")
        draw = ImageDraw.Draw(img)
        icx, icy = intruder_center
        off = (cell - emoji_size) // 2
        tile = _emoji_tile(intruder, emoji_size)
        img.paste(tile, (icx - emoji_size // 2, icy - emoji_size // 2), tile)
        # cercle lumineux (double trait pour un effet « glow »)
        rad = int(cell * 0.62)
        for width, col in ((int(cell * 0.10), (*CIRCLE, )),
                           (int(cell * 0.05), (255, 180, 200))):
            draw.ellipse([icx - rad, icy - rad, icx + rad, icy + rad],
                         outline=col, width=max(3, width))

    # Textes (titre en haut, bandeau + CTA en bas).
    if title:
        _centered_text(draw, int(h * 0.055), title, int(w * 0.052), INK, w)
    if banner:
        by = int(h * 0.92)
        bh = int(h * 0.052)
        font = ImageFont.truetype(TEXT_FONT, int(w * 0.058))
        tb = draw.textbbox((0, 0), banner, font=font)
        pill_w = (tb[2] - tb[0]) + int(w * 0.10)
        _rounded(draw, [(w - pill_w) // 2, by - bh, (w + pill_w) // 2, by + bh],
                 radius=bh, fill=CIRCLE)
        _centered_text(draw, by, banner, int(w * 0.058), (255, 255, 255), w)
    if cta:
        _centered_text(draw, int(h * 0.975), cta, int(w * 0.036), INK, w)

    return img, intruder_center, cell
