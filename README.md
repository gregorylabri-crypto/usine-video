# Usine à vidéos faceless

Génère des vidéos verticales (format short / Reels / TikTok, 1080×1920) prêtes
à publier à partir d'un simple fichier **JSON**. Chaque scène combine une voix
off, un visuel de fond animé (effet Ken Burns), des sous-titres incrustés calés
sur la parole, et une musique d'ambiance mixée par-dessus — le tout monté avec
`ffmpeg`.

## Démarrage rapide

```bash
# 1. Dépendances système
sudo apt-get install -y ffmpeg espeak-ng

# 2. Dépendances Python
pip install -r requirements.txt

# 3. Génération
python3 generate_video.py data/10-faits-terre.json
# → output/10-faits-terre.mp4
```

## Format du JSON

```jsonc
{
  "title": "10 faits surprenants sur la Terre",
  "voice": "fr-FR-DeniseNeural",        // voix Edge TTS
  "rate": "+15%",                        // vitesse de parole
  "music": "assets/music/cosmic_dark.mp3",
  "music_volume": 0.12,                  // volume musique (0–1)
  "output": "output/10-faits-terre.mp4",
  "scenes": [
    {
      "image_query": "planet earth from space blue",  // recherche du visuel
      "text": "10 faits surprenants sur la Terre..."  // narration + sous-titres
    }
    // ... une entrée par scène
  ]
}
```

La durée de chaque scène est déterminée automatiquement par la longueur de la
voix off (plus une courte respiration). Aucune durée n'est à renseigner.

## Voix off (TTS)

Sélection via la variable d'environnement `TTS_BACKEND` :

| Valeur    | Moteur          | Qualité   | Réseau requis | Sous-titres |
|-----------|-----------------|-----------|---------------|-------------|
| `auto` ⭐ | Edge → eSpeak   | —         | tente Edge    | mot à mot / proportionnel |
| `edge`    | Microsoft Edge  | naturelle | oui           | **calés mot à mot** |
| `espeak`  | eSpeak NG       | robotique | non           | proportionnels |

En mode `auto` (défaut), l'usine tente d'abord les voix neuronales Edge TTS
(celles indiquées dans le JSON) et retombe automatiquement sur eSpeak NG,
100 % hors-ligne, si le réseau est indisponible ou bloqué.

## Visuels de fond

L'usine cherche une photo correspondant à `image_query` via, dans l'ordre, la
première API dont la clé est présente dans l'environnement :

```bash
export PEXELS_API_KEY=...      # https://www.pexels.com/api/   (gratuit)
export PIXABAY_API_KEY=...     # https://pixabay.com/api/docs/ (gratuit)
export UNSPLASH_ACCESS_KEY=... # https://unsplash.com/developers
```

**Sans clé d'API**, un fond « cosmique » procédural est généré (dégradé sombre
déterministe, halo, champ d'étoiles, vignette) — l'usine reste donc pleinement
fonctionnelle hors-ligne. Les photos sont automatiquement assombries pour
garantir la lisibilité des sous-titres blancs.

## Musique

Si le fichier référencé par `music` est absent, un lit d'ambiance « cosmic
dark » libre de droits est synthétisé automatiquement (nappes graves, trémolo
lent, écho). La musique est mixée sous la voix avec un léger *ducking*
(sidechain compression) pour que la narration reste au premier plan.

## Options

```bash
python3 generate_video.py data/10-faits-terre.json \
    --width 1080 --height 1920 --fps 30 \
    --keep-workdir            # conserve les fichiers intermédiaires
```

## Architecture

```
generate_video.py      Entrée CLI
src/pipeline.py        Orchestration (TTS → images → clips → montage final)
src/tts.py             Voix off (Edge TTS + repli eSpeak NG, timings mots)
src/images.py          Visuels (Pexels/Pixabay/Unsplash + fond procédural)
src/subtitles.py       Sous-titres ASS calés sur la parole
src/make_music.py      Synthèse du lit musical d'ambiance
data/                  Exemples de fichiers JSON
```

## Exemple inclus

`data/10-faits-terre.json` produit une vidéo de ~64 s : `output/10-faits-terre.mp4`.
