#!/usr/bin/env python3
"""Usine à vidéos — générateur de jeu « Trouve l'intrus ».

Produit une vidéo verticale interactive : une grille d'emojis identiques avec
un intrus à repérer, compte à rebours, révélation animée, son et voix off.

Exemple :

    python3 generate_game.py data/trouve-intrus-chats.json

Format « find the odd one out » pensé pour la rétention et les commentaires.
Voir README pour le format du JSON.
"""

from __future__ import annotations

import argparse
import sys

from src.game_pipeline import GameConfig, generate


def main() -> int:
    parser = argparse.ArgumentParser(description="Générateur « Trouve l'intrus »")
    parser.add_argument("config", help="Fichier JSON décrivant les manches")
    parser.add_argument("--width", type=int, default=1080)
    parser.add_argument("--height", type=int, default=1920)
    parser.add_argument("--fps", type=int, default=30)
    parser.add_argument("--reveal-dur", type=float, default=2.6,
                        help="Durée de la phase révélation (s)")
    args = parser.parse_args()

    cfg = GameConfig(width=args.width, height=args.height, fps=args.fps,
                     reveal_dur=args.reveal_dur)
    print(generate(args.config, cfg))
    return 0


if __name__ == "__main__":
    sys.exit(main())
