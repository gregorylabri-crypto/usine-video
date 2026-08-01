#!/usr/bin/env python3
"""Usine à vidéos faceless — point d'entrée en ligne de commande.

Génère une vidéo verticale (format short/Reels/TikTok) à partir d'un fichier
JSON décrivant le titre, la voix, la musique et les scènes.

Exemple :

    python3 generate_video.py data/10-faits-terre.json

Options utiles :

    --width / --height / --fps      dimensions et cadence (défaut 1080x1920@30)
    --keep-workdir                  conserve les fichiers intermédiaires

Variables d'environnement :

    TTS_BACKEND        auto (défaut) | edge | espeak
    PEXELS_API_KEY     active les vraies photos Pexels (sinon fond procédural)
    PIXABAY_API_KEY    idem via Pixabay
    UNSPLASH_ACCESS_KEY idem via Unsplash
"""

from __future__ import annotations

import argparse
import sys

from src.pipeline import RenderConfig, generate


def main() -> int:
    parser = argparse.ArgumentParser(description="Usine à vidéos faceless")
    parser.add_argument("config", help="Fichier JSON décrivant la vidéo")
    parser.add_argument("--width", type=int, default=1080)
    parser.add_argument("--height", type=int, default=1920)
    parser.add_argument("--fps", type=int, default=30)
    parser.add_argument("--keep-workdir", action="store_true",
                        help="Ne pas supprimer le dossier de travail")
    args = parser.parse_args()

    cfg = RenderConfig(width=args.width, height=args.height, fps=args.fps)
    out = generate(args.config, cfg)
    print(out)
    return 0


if __name__ == "__main__":
    sys.exit(main())
