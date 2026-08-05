#!/bin/bash
# monter_petitche.sh — transforme une photo en TikTok vertical (muet, sous-titré).
#
# Étapes : amélioration de l'image (lumière/contraste/chaleur/netteté/vignette),
# léger zoom Ken Burns vers le sujet, incrustation des sous-titres, sortie 9:16
# SANS audio (pour ajouter un son tendance directement dans TikTok).
#
# Usage :
#   ./monter_petitche.sh [image_source] [sortie.mp4]
# Défauts : scratch_cat/source.jpg  ->  output/mon-chat-tiktok.mp4
set -euo pipefail

SRC="${1:-scratch_cat/source.jpg}"
OUT="${2:-output/mon-chat-tiktok.mp4}"
WORK="scratch_cat"
ENHANCED="$WORK/enhanced.png"
SUBS="$WORK/subs.ass"
DUR=11.5
FRAMES=345          # DUR * 30 fps
FONT="/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"

mkdir -p "$WORK" "$(dirname "$OUT")"

if [ ! -f "$SRC" ]; then
  echo "❌ Image source introuvable : $SRC" >&2
  exit 1
fi

echo "→ Amélioration de l'image…"
python3 - "$SRC" "$ENHANCED" <<'PY'
import sys
from PIL import Image, ImageEnhance, ImageFilter, ImageDraw
src, out = sys.argv[1], sys.argv[2]
img = Image.open(src).convert("RGB").resize((1080, 1920), Image.LANCZOS)
e = img
e = ImageEnhance.Brightness(e).enhance(1.08)
e = ImageEnhance.Contrast(e).enhance(1.13)
e = ImageEnhance.Color(e).enhance(1.20)
e = ImageEnhance.Sharpness(e).enhance(1.45)
r, g, b = e.split()                      # réchauffement subtil
r = r.point(lambda p: min(255, int(p * 1.03)))
b = b.point(lambda p: int(p * 0.975))
e = Image.merge("RGB", (r, g, b))
vig = Image.new("L", e.size, 0)          # vignette pour détacher le sujet
ImageDraw.Draw(vig).ellipse([-e.width*0.30, -e.height*0.14,
                             e.width*1.30, e.height*1.14], fill=255)
vig = vig.filter(ImageFilter.GaussianBlur(240))
e = Image.composite(e, Image.new("RGB", e.size, (0, 0, 0)), vig)
e.save(out)
print("   image améliorée:", out)
PY

echo "→ Écriture des sous-titres…"
cat > "$SUBS" <<'ASS'
[Script Info]
ScriptType: v4.00+
PlayResX: 1080
PlayResY: 1920
WrapStyle: 2
ScaledBorderAndShadow: yes

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: Cap,DejaVu Sans,80,&H00FFFFFF,&H00FFFFFF,&H00101820,&H64000000,-1,0,0,0,100,100,0,0,1,7,4,2,64,64,300,1

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
Dialogue: 0,0:00:00.15,0:00:02.30,Cap,,0,0,0,,{\fad(150,120)}Mode pain : activé
Dialogue: 0,0:00:02.30,0:00:04.60,Cap,,0,0,0,,{\fad(120,120)}Ne pas déranger.
Dialogue: 0,0:00:04.60,0:00:07.20,Cap,,0,0,0,,{\fad(120,120)}Je digère 14 h de sieste...
Dialogue: 0,0:00:07.20,0:00:09.60,Cap,,0,0,0,,{\fad(120,120)}...et je prépare la suivante.
Dialogue: 0,0:00:09.60,0:00:11.50,Cap,,0,0,0,,{\fad(120,0)}Like si ton chat fait pareil
ASS

echo "→ Montage (zoom + sous-titres, muet)…"
ffmpeg -y -loglevel error -loop 1 -i "$ENHANCED" -t "$DUR" \
  -vf "scale=2160:3840,zoompan=z='min(1.0+0.10*on/${FRAMES},1.10)':d=${FRAMES}:x='iw*0.36-(iw/zoom/2)':y='ih*0.34-(ih/zoom/2)':s=1080x1920:fps=30,subtitles=${SUBS},format=yuv420p" \
  -r 30 -an -c:v libx264 -preset medium -crf 19 -pix_fmt yuv420p "$OUT"

echo "✓ Vidéo prête : $OUT (muette — ajoute un son tendance dans TikTok)"
