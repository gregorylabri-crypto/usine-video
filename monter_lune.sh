#!/bin/bash
# monter_lune.sh — TikTok vertical "Et si la Lune disparaissait ?"
# Étapes : garde clips/ -> voix off + sous-titres -> montage ffmpeg -> ffprobe.
#
# Prérequis : clips/1.mp4, clips/2.mp4, clips/3.mp4 (9:16, ~5 s chacun).
# Optionnel : ./musique.mp3 (ajouté en boucle, ducké sous la voix).
set -euo pipefail
cd "$(dirname "$0")"

NARRATION="Si la Lune disparaissait maintenant, voici ce qui arriverait en 24 heures. Le ciel d'abord : nos nuits deviennent totalement noires, éclairées par les seules étoiles. Les océans ensuite : sans son attraction, les marées s'effondrent, et les courants qui règlent le climat se dérèglent. Et surtout, la Terre perd son stabilisateur. Son axe se met à osciller : saisons chaotiques, climat déréglé. Sans la Lune, la vie telle qu'on la connaît n'aurait jamais existé."

# ---- 1) Garde : les 3 clips doivent être présents -------------------- #
mkdir -p clips
missing=0
for f in 1.mp4 2.mp4 3.mp4; do
  [ -f "clips/$f" ] || { echo "✗ clips/$f manquant"; missing=1; }
done
if [ "$missing" -ne 0 ]; then
  echo "⛔ Dépose 1.mp4, 2.mp4, 3.mp4 dans clips/ puis relance."
  exit 1
fi

# ---- 2) Voix off + sous-titres --------------------------------------- #
# On tente la commande edge-tts exacte ; si le réseau la bloque, repli eSpeak.
tts_ok=0
if command -v edge-tts >/dev/null 2>&1; then
  echo "→ Voix off via edge-tts (fr-FR-RemyNeural)…"
  if edge-tts --voice fr-FR-RemyNeural --rate=+8% \
       --text "$NARRATION" \
       --write-media voix.mp3 --write-subtitles voix.vtt 2>/tmp/edge.err \
     && [ -s voix.mp3 ]; then
    tts_ok=1
  else
    echo "  ⚠ edge-tts indisponible ($(tail -1 /tmp/edge.err 2>/dev/null)) — repli eSpeak NG."
  fi
fi

if [ "$tts_ok" -ne 1 ]; then
  echo "→ Voix off hors-ligne via eSpeak NG…"
  espeak-ng -v fr -s 178 -w voix.wav "$NARRATION"
  ffmpeg -y -loglevel error -i voix.wav -codec:a libmp3lame -qscale:a 3 voix.mp3
  rm -f voix.wav
  # Génère un VTT synchronisé (répartition proportionnelle sur la durée réelle).
  DUR=$(ffprobe -v error -show_entries format=duration -of default=nk=1:nw=1 voix.mp3)
  python3 - "$DUR" <<'PY'
import re, sys
dur = float(sys.argv[1])
text = ("Si la Lune disparaissait maintenant, voici ce qui arriverait en 24 heures. "
        "Le ciel d'abord : nos nuits deviennent totalement noires, éclairées par les seules étoiles. "
        "Les océans ensuite : sans son attraction, les marées s'effondrent, et les courants qui règlent le climat se dérèglent. "
        "Et surtout, la Terre perd son stabilisateur. "
        "Son axe se met à osciller : saisons chaotiques, climat déréglé. "
        "Sans la Lune, la vie telle qu'on la connaît n'aurait jamais existé.")
words = text.split()
# Regroupe en légendes courtes (~7 mots, coupe aux ponctuations).
chunks, cur = [], []
for w in words:
    cur.append(w)
    if len(cur) >= 7 or w.endswith((".", ":", "!", "?")):
        chunks.append(" ".join(cur)); cur = []
if cur: chunks.append(" ".join(cur))
total = sum(len(c) for c in chunks) or 1

def ts(t):
    h = int(t//3600); m = int(t%3600//60); s = t%60
    return f"{h:02d}:{m:02d}:{s:06.3f}"

lines = ["WEBVTT", ""]
cursor = 0.0
for c in chunks:
    d = dur * len(c) / total
    lines += [f"{ts(cursor)} --> {ts(cursor+d)}", c, ""]
    cursor += d
open("voix.vtt", "w", encoding="utf-8").write("\n".join(lines))
print("  voix.vtt généré:", len(chunks), "légendes")
PY
fi

# ---- 3) Montage ffmpeg ----------------------------------------------- #
FORCE_STYLE="FontName=Arial,Fontsize=18,Bold=1,PrimaryColour=&H00FFFFFF,OutlineColour=&H00000000,BorderStyle=1,Outline=3,Shadow=1,Alignment=2,MarginV=260"

# Chaîne vidéo : ralenti 1.87x, cadrage 1080x1920, 30 fps, sar 1, concat, sous-titres.
VCHAIN=""
for i in 0 1 2; do
  VCHAIN+="[${i}:v]setpts=1.87*PTS,scale=1080:1920:force_original_aspect_ratio=increase,crop=1080:1920,fps=30,setsar=1[v${i}];"
done
VCHAIN+="[v0][v1][v2]concat=n=3:v=1:a=0[vc];[vc]subtitles=voix.vtt:force_style='${FORCE_STYLE}'[vout]"

if [ -f musique.mp3 ]; then
  echo "→ Montage avec musique (duck sous la voix)…"
  ffmpeg -y -loglevel error \
    -i clips/1.mp4 -i clips/2.mp4 -i clips/3.mp4 \
    -i voix.mp3 -stream_loop -1 -i musique.mp3 \
    -filter_complex "${VCHAIN};\
[3:a]dynaudnorm,asplit=2[vk][va];\
[4:a]volume=0.18[mus];\
[mus][vk]sidechaincompress=threshold=0.05:ratio=8:attack=20:release=300[duck];\
[va][duck]amix=inputs=2:normalize=0[aout]" \
    -map "[vout]" -map "[aout]" \
    -c:v libx264 -crf 20 -preset medium -pix_fmt yuv420p -r 30 \
    -c:a aac -b:a 192k -movflags +faststart -shortest lune_tiktok.mp4
else
  echo "→ Montage sans musique (voix seule)…"
  ffmpeg -y -loglevel error \
    -i clips/1.mp4 -i clips/2.mp4 -i clips/3.mp4 -i voix.mp3 \
    -filter_complex "${VCHAIN};[3:a]dynaudnorm[aout]" \
    -map "[vout]" -map "[aout]" \
    -c:v libx264 -crf 20 -preset medium -pix_fmt yuv420p -r 30 \
    -c:a aac -b:a 192k -movflags +faststart -shortest lune_tiktok.mp4
fi

# ---- 4) Vérification ------------------------------------------------- #
echo "✓ Fichier final : lune_tiktok.mp4"
ffprobe -v error -select_streams v:0 \
  -show_entries stream=width,height:format=duration \
  -of default=noprint_wrappers=1 lune_tiktok.mp4
