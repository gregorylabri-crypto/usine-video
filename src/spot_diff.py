"""Scènes « cherche les 7 différences » (sans IA, entièrement contrôlées).

On compose une scène dense à partir d'emojis positionnés en bandes (ciel /
milieu / sol) sur un fond dégradé, façon illustration. On dérive ensuite une
variante avec exactement N différences *subtiles* (ajout, retrait, changement
de couleur, taille, miroir, déplacement, remplacement). Comme chaque différence
est appliquée par nous, on connaît sa position exacte → la révélation
(cercles) est garantie juste, contrairement à une approche par diff d'images IA.
"""

from __future__ import annotations

import functools
import random
from dataclasses import dataclass, replace
from typing import Dict, List, Tuple

from PIL import Image, ImageDraw, ImageFont

EMOJI_FONT = "/usr/share/fonts/truetype/noto/NotoColorEmoji.ttf"
_STRIKE = 109


@dataclass
class Sprite:
    ch: str
    cx: int
    cy: int
    size: int
    flip: bool = False
    hue: int = 0          # décalage de teinte (0-255)


# --------------------------------------------------------------------------- #
# Rendu d'une tuile emoji (avec miroir / teinte / échelle)
# --------------------------------------------------------------------------- #
@functools.lru_cache(maxsize=256)
def _base_tile(ch: str, size: int) -> Image.Image:
    font = ImageFont.truetype(EMOJI_FONT, _STRIKE)
    big = Image.new("RGBA", (_STRIKE + 40, _STRIKE + 40), (0, 0, 0, 0))
    ImageDraw.Draw(big).text((20, 20), ch, font=font, embedded_color=True)
    bbox = big.getbbox()
    big = big.crop(bbox)
    scale = size / max(big.width, big.height)
    return big.resize((max(1, int(big.width * scale)),
                       max(1, int(big.height * scale))), Image.LANCZOS)


def _hue_shift(img: Image.Image, deg: int) -> Image.Image:
    r, g, b, a = img.split()
    hsv = Image.merge("RGB", (r, g, b)).convert("HSV")
    h, s, v = hsv.split()
    h = h.point(lambda p: (p + deg) % 256)
    rgb = Image.merge("HSV", (h, s, v)).convert("RGB")
    return Image.merge("RGBA", (*rgb.split(), a))


def tile_for(sprite: Sprite) -> Image.Image:
    t = _base_tile(sprite.ch, sprite.size)
    if sprite.flip:
        t = t.transpose(Image.FLIP_LEFT_RIGHT)
    if sprite.hue:
        t = _hue_shift(t, sprite.hue)
    return t


# --------------------------------------------------------------------------- #
# Thèmes
# --------------------------------------------------------------------------- #
# Chaque thème : couleurs de fond + bandes (y relatif, props avec quantité).
THEMES: Dict[str, dict] = {
    "jardin": {
        "bg_style": "outdoor",
        "bg_top": (170, 214, 246),
        "bg_bottom": (188, 226, 150),
        "ground": 0.62,
        "bands": [
            (0.04, 0.26, [("☀️", 1), ("☁️", 3), ("🐦", 2)]),
            (0.30, 0.58, [("🌳", 2), ("🦋", 3), ("🐝", 2), ("🎈", 1), ("🍎", 2)]),
            (0.64, 0.94, [("🌷", 3), ("🌻", 2), ("🌼", 3), ("🌸", 2),
                          ("🍄", 2), ("🐰", 1), ("🐞", 2), ("🌿", 3)]),
        ],
        "add_pool": ["🌼", "🦋", "🐞", "🍄", "⭐", "🌸"],
        "swap": {"🌷": "🌸", "🌸": "🌷", "🌻": "🌼", "🌼": "🌻",
                 "🐝": "🐞", "🐞": "🐝", "☁️": "🌥️", "🦋": "🐝",
                 "🍄": "🌰", "🍎": "🍏", "🐦": "🐤"},
    },
    # Chats & chatons : scène cosy « monde des chats » (chats + objets).
    # band_scale rend les éléments du sol plus petits → effet « chatons ».
    "chats": {
        "bg_style": "outdoor",
        "bg_top": (255, 231, 238),      # crème rosé (mur)
        "bg_bottom": (247, 221, 197),   # beige chaud (sol)
        "ground": 0.58,
        "band_scale": [0.85, 1.18, 0.82],
        "bands": [
            (0.05, 0.28, [("🎀", 2), ("🦋", 2), ("🐾", 3), ("🧶", 2), ("🪀", 1)]),
            (0.30, 0.56, [("😺", 1), ("😸", 1), ("🐱", 1), ("🐈", 1),
                          ("😻", 1), ("🐈‍⬛", 1)]),
            (0.60, 0.94, [("🐱", 3), ("😸", 2), ("😺", 1), ("🧶", 2), ("🐟", 2),
                          ("🥛", 1), ("📦", 1), ("🐁", 2), ("🐾", 2), ("🍥", 1)]),
        ],
        "add_pool": ["🐾", "🧶", "🐟", "🎀", "🐁", "⭐", "🍥"],
        "swap": {"😺": "😸", "😸": "😺", "😹": "😸", "😻": "😺",
                 "🐱": "😺", "🐈": "🐱", "🐈‍⬛": "🐈", "🐟": "🐠",
                 "🐠": "🐟", "🐁": "🐭", "🎀": "🧶"},
    },
    # Ménagerie / animaux mignons (extérieur nature).
    "animaux": {
        "bg_style": "outdoor",
        "bg_top": (168, 210, 246),
        "bg_bottom": (176, 220, 138),
        "ground": 0.56,
        "bands": [
            (0.04, 0.26, [("🦋", 3), ("🐦", 2), ("🐝", 2), ("☁️", 2)]),
            (0.28, 0.56, [("🐵", 1), ("🦁", 1), ("🐯", 1), ("🐻", 1),
                          ("🐼", 1), ("🦊", 1), ("🐨", 1)]),
            (0.58, 0.94, [("🐶", 2), ("🐱", 2), ("🐰", 2), ("🐹", 1),
                          ("🐷", 1), ("🐸", 1), ("🐢", 1), ("🐔", 1),
                          ("🐭", 1), ("🐮", 1)]),
        ],
        "add_pool": ["🦋", "🐞", "🐝", "🐤", "🐢", "⭐", "🍄"],
        "swap": {"🐯": "🦁", "🦁": "🐯", "🐻": "🐨", "🐨": "🐻",
                 "🐰": "🐹", "🐹": "🐰", "🐺": "🦊", "🦊": "🐺",
                 "🐸": "🐢", "🐮": "🐷", "🐷": "🐮", "🐭": "🐹",
                 "🐶": "🐱", "🐱": "🐶", "🐔": "🐤"},
    },
    # Ambiance « labo de sorcier / alchimie » (intérieur sombre), inspirée de la
    # référence : fioles, potions, bougies, toile d'araignée, grimoires…
    "alchimie": {
        "bg_style": "indoor",
        "bg_top": (44, 36, 66),
        "bg_bottom": (22, 18, 34),
        "bands": [
            (0.05, 0.30, [("🕸️", 1), ("🕯️", 2), ("🌙", 1), ("🦇", 2), ("⭐", 2)]),
            (0.32, 0.60, [("🔮", 1), ("📖", 2), ("🧪", 3), ("⚗️", 2), ("🦉", 1)]),
            (0.62, 0.94, [("🧪", 2), ("⚗️", 2), ("📜", 2), ("🗝️", 1),
                          ("💀", 1), ("🕯️", 2), ("🐍", 1), ("🍄", 2)]),
        ],
        "add_pool": ["🕷️", "⭐", "🍄", "🦇", "🕯️", "🔑"],
        "swap": {"🧪": "⚗️", "⚗️": "🧪", "🔮": "🌙", "🕯️": "🪔",
                 "📖": "📕", "📜": "📃", "💀": "👻", "🐍": "🦎",
                 "🦉": "🦇", "🗝️": "🔑"},
    },
}

# Taille par défaut selon l'emoji (les gros éléments de décor plus grands).
_SIZES = {"☀️": 150, "☁️": 130, "🌳": 175, "🎈": 120, "🍎": 90,
          "🕸️": 150, "🔮": 118, "📖": 112, "💀": 104, "🦉": 112, "⏳": 104,
          "🌙": 96, "🕯️": 84, "🕷️": 74,
          "🐻": 112, "🐼": 112, "🦁": 114, "🐯": 110, "🐨": 108, "🐵": 102,
          "🐷": 98, "🐮": 102, "🦊": 100,
          "🧶": 88, "🐟": 82, "🐠": 82, "🥛": 78, "📦": 100, "🎀": 72,
          "🐾": 64, "🐁": 74, "🍥": 82, "🪀": 78}
_DEFAULT_SIZE = 92


def _size_of(ch: str) -> int:
    return _SIZES.get(ch, _DEFAULT_SIZE)


# --------------------------------------------------------------------------- #
# Génération de la scène
# --------------------------------------------------------------------------- #
def generate_scene(theme: str, seed: int, w: int, h: int) -> List[Sprite]:
    spec = THEMES[theme]
    rng = random.Random(seed)
    sprites: List[Sprite] = []
    placed: List[Tuple[int, int, int]] = []   # (cx, cy, rayon) anti-collision

    def free(cx, cy, r) -> bool:
        for px, py, pr in placed:
            if (cx - px) ** 2 + (cy - py) ** 2 < (0.62 * (r + pr)) ** 2:
                return False
        return True

    band_scale = spec.get("band_scale", [1.0] * len(spec["bands"]))
    for bi, (y0, y1, props) in enumerate(spec["bands"]):
        for ch, qty in props:
            size = int(_size_of(ch) * band_scale[bi])
            for _ in range(qty):
                for _try in range(40):
                    cx = rng.randint(int(w * 0.07), int(w * 0.93))
                    cy = rng.randint(int(h * y0), int(h * y1))
                    if free(cx, cy, size):
                        sprites.append(Sprite(ch, cx, cy, size))
                        placed.append((cx, cy, size))
                        break
    return sprites


def make_variant(sprites: List[Sprite], theme: str, seed: int, n: int,
                 w: int, h: int) -> Tuple[List[Sprite], List[Tuple[int, int]]]:
    """Retourne (sprites modifiés, centres des n différences)."""
    spec = THEMES[theme]
    rng = random.Random(seed * 31 + 7)
    variant = list(sprites)
    diffs: List[Tuple[int, int]] = []

    # Types de mutations répartis pour de la variété (au moins un ajout/retrait).
    plan = ["add", "remove", "recolor", "scale", "flip", "shift", "swap"]
    while len(plan) < n:
        plan.append(rng.choice(["recolor", "scale", "shift", "swap"]))
    plan = plan[:n]

    # Indices candidats (on évite les très gros éléments pour rester subtil).
    candidates = [i for i, s in enumerate(sprites) if s.size <= 120]
    rng.shuffle(candidates)
    used = set()

    def next_candidate():
        while candidates:
            i = candidates.pop()
            if i not in used:
                used.add(i)
                return i
        return None

    def free_spot(size):
        for _ in range(60):
            cx = rng.randint(int(w * 0.08), int(w * 0.92))
            cy = rng.randint(int(h * 0.35), int(h * 0.92))
            ok = all((cx - s.cx) ** 2 + (cy - s.cy) ** 2 > (0.6 * (size + s.size)) ** 2
                     for s in variant)
            if ok:
                return cx, cy
        return rng.randint(int(w * 0.1), int(w * 0.9)), rng.randint(int(h * 0.4), int(h * 0.9))

    for mut in plan:
        if mut == "add":
            ch = rng.choice(spec["add_pool"])
            size = _size_of(ch)
            cx, cy = free_spot(size)
            variant.append(Sprite(ch, cx, cy, size))
            diffs.append((cx, cy))
            continue

        idx = next_candidate()
        if idx is None:
            continue
        s = sprites[idx]
        pos = variant.index(s)
        if mut == "remove":
            variant.pop(pos)
        elif mut == "recolor":
            variant[pos] = replace(s, hue=rng.choice([70, 110, 150, 190]))
        elif mut == "scale":
            variant[pos] = replace(s, size=int(s.size * rng.choice([0.72, 1.28])))
        elif mut == "flip":
            variant[pos] = replace(s, flip=True)
        elif mut == "shift":
            dx = rng.choice([-1, 1]) * int(s.size * 0.7)
            dy = rng.choice([-1, 1]) * int(s.size * 0.5)
            variant[pos] = replace(s, cx=s.cx + dx, cy=s.cy + dy)
        elif mut == "swap":
            alt = spec["swap"].get(s.ch)
            if alt:
                variant[pos] = replace(s, ch=alt)
            else:
                variant[pos] = replace(s, hue=120)
        diffs.append((s.cx, s.cy))

    return variant, diffs


# --------------------------------------------------------------------------- #
# Rendu d'un panneau
# --------------------------------------------------------------------------- #
def _background(spec: dict, w: int, h: int) -> Image.Image:
    """Fond du panneau selon le style du thème (extérieur ou intérieur)."""
    from PIL import ImageFilter

    img = Image.new("RGB", (w, h))
    px = img.load()
    top, bot = spec["bg_top"], spec["bg_bottom"]

    if spec.get("bg_style") == "indoor":
        # dégradé vertical sombre + vignette pour l'ambiance « labo »
        for y in range(h):
            t = y / max(1, h - 1)
            col = tuple(int(top[i] + (bot[i] - top[i]) * t) for i in range(3))
            for x in range(w):
                px[x, y] = col
        vig = Image.new("L", (w, h), 0)
        ImageDraw.Draw(vig).ellipse([-w * 0.2, -h * 0.15, w * 1.2, h * 1.15], fill=255)
        vig = vig.filter(ImageFilter.GaussianBlur(min(w, h) // 5))
        return Image.composite(img, Image.new("RGB", (w, h), (8, 6, 14)), vig)

    # extérieur : ciel dégradé + sol
    gy = int(h * spec.get("ground", 0.62))
    grass = tuple(int(c * 0.9) for c in bot)
    for y in range(h):
        if y < gy:
            t = y / max(1, gy)
            col = tuple(int(top[i] + (bot[i] - top[i]) * t) for i in range(3))
        else:
            col = grass
        for x in range(w):
            px[x, y] = col
    ImageDraw.Draw(img).line([(0, gy), (w, gy)],
                             fill=tuple(int(c * 0.8) for c in bot), width=4)
    return img


def render_panel(sprites: List[Sprite], theme: str, w: int, h: int) -> Image.Image:
    spec = THEMES[theme]
    img = _background(spec, w, h)
    for s in sorted(sprites, key=lambda s: s.cy):   # tri = profondeur
        t = tile_for(s)
        img.paste(t, (s.cx - t.width // 2, s.cy - t.height // 2), t)
    return img
