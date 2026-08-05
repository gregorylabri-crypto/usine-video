#!/usr/bin/env python3
"""Usine à vidéos — générateur « Cherche les différences ».

Deux scènes côte à côte, minuteur circulaire, révélation en cercles verts.
Format inspiré des vidéos-jeu virales (style « spot the difference »).

Exemple :

    python3 generate_spot.py data/differences-alchimie-60s.json
"""

from __future__ import annotations

import argparse
import sys

from src.spot_pipeline import SpotConfig, generate


def main() -> int:
    p = argparse.ArgumentParser(description="Générateur « Cherche les différences »")
    p.add_argument("config", help="Fichier JSON décrivant la scène")
    p.add_argument("--width", type=int, default=1920)
    p.add_argument("--height", type=int, default=1080)
    p.add_argument("--fps", type=int, default=30)
    p.add_argument("--layout", choices=["side", "stack"], default="side")
    args = p.parse_args()

    cfg = SpotConfig(width=args.width, height=args.height, fps=args.fps,
                     layout=args.layout)
    print(generate(args.config, cfg))
    return 0


if __name__ == "__main__":
    sys.exit(main())
