"""Orchestration du format vidéo « Trouve l'intrus ».

À partir d'un JSON décrivant des manches (« rounds »), produit une vidéo
verticale :

1. Pour chaque manche : une grille d'emojis identiques avec un intrus.
2. Phase recherche : grille + compte à rebours + petite voix d'accroche.
3. Phase reveal : l'intrus est entouré, zoom rapide dessus + « ding ».
4. Musique légère en fond, CTA final.

Réutilise les briques de l'usine (voix off, exécution ffmpeg).
"""

from __future__ import annotations

import json
import os
import tempfile
from dataclasses import dataclass
from typing import List

from . import tts
from .game_grid import render_grid
from .game_sfx import synth_ding, synth_game_music
from .pipeline import _run  # exécuteur ffmpeg partagé

TEXT_FONT = "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"


@dataclass
class GameConfig:
    width: int = 1080
    height: int = 1920
    fps: int = 30
    reveal_dur: float = 2.6      # durée de la phase révélation (s)
    pre_roll: float = 0.4        # court instant avant le décompte (s)


def _scan_clip(image_path: str, out_path: str, scan_dur: float, timer: int,
               cfg: GameConfig) -> None:
    """Grille figée + gros compte à rebours (timer → 1) via drawtext."""
    fs = int(cfg.width * 0.11)
    # Décompte robuste : un drawtext par seconde, chacun visible sur sa fenêtre.
    # La seconde k (de timer à 1) s'affiche pendant [pre_roll+(timer-k), +1].
    draws = []
    for k in range(timer, 0, -1):
        start = cfg.pre_roll + (timer - k)
        end = start + 1
        draws.append(
            f"drawtext=fontfile={TEXT_FONT}:text='{k}':"
            f"fontcolor=white:fontsize={fs}:borderw=8:bordercolor=0xFF4A6E:"
            f"x=(w-text_w)/2:y=h*0.10-text_h/2:"
            f"enable='between(t,{start:.2f},{end:.2f})'"
        )
    vf = ",".join(draws + ["format=yuv420p"])
    _run([
        "ffmpeg", "-y", "-loglevel", "error",
        "-loop", "1", "-i", image_path,
        "-t", f"{scan_dur:.3f}",
        "-vf", vf,
        "-r", str(cfg.fps),
        "-c:v", "libx264", "-preset", "veryfast", "-crf", "20",
        "-pix_fmt", "yuv420p", out_path,
    ])


def _reveal_clip(image_path: str, out_path: str, center, cell: int,
                 cfg: GameConfig) -> None:
    """Image de reveal avec zoom rapide centré sur l'intrus."""
    w, h = cfg.width, cfg.height
    frames = max(1, round(cfg.reveal_dur * cfg.fps))
    cx, cy = center
    # zoom rapide 1.0 -> 1.5 en visant le centre de l'intrus
    z = f"min(1.0+0.5*on/{frames},1.5)"
    x = f"{cx}*2-(iw/zoom/2)"      # *2 car sur-échantillonnage préalable
    y = f"{cy}*2-(ih/zoom/2)"
    _run([
        "ffmpeg", "-y", "-loglevel", "error",
        "-loop", "1", "-i", image_path,
        "-t", f"{cfg.reveal_dur:.3f}",
        "-vf", (f"scale={w*2}:{h*2},"
                f"zoompan=z='{z}':d={frames}:x='{x}':y='{y}':"
                f"s={w}x{h}:fps={cfg.fps},format=yuv420p"),
        "-r", str(cfg.fps),
        "-c:v", "libx264", "-preset", "veryfast", "-crf", "20",
        "-pix_fmt", "yuv420p", out_path,
    ])


def _pad_audio(src: str, out_path: str, delay: float, total: float) -> None:
    _run([
        "ffmpeg", "-y", "-loglevel", "error", "-i", src,
        "-af", f"adelay={int(delay*1000)}|{int(delay*1000)},"
               f"apad=whole_dur={total:.3f},aresample=44100",
        "-t", f"{total:.3f}", "-ac", "2", "-ar", "44100", out_path,
    ])


def generate(config_path: str, cfg: GameConfig | None = None,
             work_dir: str | None = None) -> str:
    cfg = cfg or GameConfig()
    with open(config_path, encoding="utf-8") as fh:
        conf = json.load(fh)

    root = os.getcwd()
    voice = conf.get("voice", "fr-FR-DeniseNeural")
    rate = conf.get("rate", "+0%")
    music_path = conf.get("music", "")
    music_volume = float(conf.get("music_volume", 0.18))
    output = conf.get("output", "output/jeu.mp4")
    cta = conf.get("cta")
    rounds = conf["rounds"]

    os.makedirs(os.path.dirname(os.path.abspath(output)) or ".", exist_ok=True)
    tmp = work_dir or tempfile.mkdtemp(prefix="jeu_")
    os.makedirs(tmp, exist_ok=True)
    print(f"→ Dossier de travail : {tmp}")

    clip_files: List[str] = []
    voice_pads: List[str] = []
    reveal_times: List[float] = []
    cursor = 0.0
    backend = None

    for i, rnd in enumerate(rounds):
        base, intr = rnd["base"], rnd["intruder"]
        cols, rows = int(rnd.get("cols", 6)), int(rnd.get("rows", 8))
        timer = int(rnd.get("timer", 8))
        hook = rnd.get("hook", "Trouve l'intrus")
        reveal_text = rnd.get("reveal_text", "Le voilà !")
        seed = int(rnd.get("seed", 1000 + i))
        last = (i == len(rounds) - 1)
        print(f"  Manche {i+1}/{len(rounds)} — {base} vs {intr} "
              f"({cols}x{rows}, {timer}s)")

        # Images (recherche + reveal), l'intrus est au même endroit (même seed).
        plain = os.path.join(tmp, f"grid_{i:02d}.png")
        rev = os.path.join(tmp, f"reveal_{i:02d}.png")
        img_p, center, cell = render_grid(base, intr, cols, rows, seed,
                                          cfg.width, cfg.height, reveal=False,
                                          title=hook)
        img_p.save(plain)
        img_r, center, cell = render_grid(base, intr, cols, rows, seed,
                                          cfg.width, cfg.height, reveal=True,
                                          title=hook, banner=reveal_text,
                                          cta=cta if last else None)
        img_r.save(rev)

        # Clips vidéo de la manche.
        scan_dur = cfg.pre_roll + timer
        scan = os.path.join(tmp, f"scan_{i:02d}.mp4")
        reveal = os.path.join(tmp, f"rev_{i:02d}.mp4")
        _scan_clip(plain, scan, scan_dur, timer, cfg)
        _reveal_clip(rev, reveal, center, cell, cfg)
        clip_files += [scan, reveal]

        # Voix : accroche au début de la recherche, réponse au reveal.
        hook_voice = os.path.join(tmp, f"vh_{i:02d}.mp3")
        rev_voice = os.path.join(tmp, f"vr_{i:02d}.mp3")
        (nh, backend) = tts.synthesize(hook, voice, rate, hook_voice)
        (nr, backend) = tts.synthesize(reveal_text, voice, rate, rev_voice)

        # Pistes audio calées sur les phases.
        vh_pad = os.path.join(tmp, f"vhp_{i:02d}.wav")
        vr_pad = os.path.join(tmp, f"vrp_{i:02d}.wav")
        _pad_audio(hook_voice, vh_pad, cfg.pre_roll, scan_dur)
        _pad_audio(rev_voice, vr_pad, 0.15, cfg.reveal_dur)
        voice_pads += [vh_pad, vr_pad]

        reveal_times.append(cursor + scan_dur)   # instant du « ding »
        cursor += scan_dur + cfg.reveal_dur

    total = cursor
    print(f"→ Voix : backend « {backend} » — durée totale {total:.1f}s")

    # Concat vidéo.
    vlist = os.path.join(tmp, "clips.txt")
    with open(vlist, "w") as fh:
        for c in clip_files:
            fh.write(f"file '{os.path.abspath(c)}'\n")
    video = os.path.join(tmp, "video.mp4")
    _run(["ffmpeg", "-y", "-loglevel", "error", "-f", "concat", "-safe", "0",
          "-i", vlist, "-c", "copy", video])

    # Concat voix.
    alist = os.path.join(tmp, "voice.txt")
    with open(alist, "w") as fh:
        for p in voice_pads:
            fh.write(f"file '{os.path.abspath(p)}'\n")
    voice_track = os.path.join(tmp, "voice.wav")
    _run(["ffmpeg", "-y", "-loglevel", "error", "-f", "concat", "-safe", "0",
          "-i", alist, "-c", "copy", voice_track])

    # SFX ding + musique.
    ding = os.path.join(tmp, "ding.wav")
    synth_ding(ding)
    music_abs = os.path.join(root, music_path) if music_path else ""
    if music_path and not os.path.exists(music_abs):
        os.makedirs(os.path.dirname(music_abs) or ".", exist_ok=True)
        print(f"→ Musique absente, synthèse d'un fond enjoué : {music_path}")
        synth_game_music(music_abs, duration=max(30, int(total) + 4))

    # Montage audio final : voix + musique + dings placés aux reveals.
    # Ordre des entrées ffmpeg : 0=vidéo, 1=voix, [2=musique], puis les dings.
    print("→ Montage final (voix + musique + dings)")
    inputs = ["-i", video, "-i", voice_track]
    next_idx = 2
    has_music = bool(music_path and os.path.exists(music_abs))
    if has_music:
        inputs += ["-stream_loop", "-1", "-i", music_abs]
        music_idx = next_idx
        next_idx += 1
    ding_base = next_idx
    for _ in reveal_times:
        inputs += ["-i", ding]

    parts = []
    mix_labels = ["[1:a]"]                     # voix = entrée 1
    if has_music:
        parts.append(f"[{music_idx}:a]volume={music_volume}[mus]")
        mix_labels.append("[mus]")
    for k, t in enumerate(reveal_times):
        src = ding_base + k
        parts.append(f"[{src}:a]adelay={int(t*1000)}|{int(t*1000)},volume=0.9[d{k}]")
        mix_labels.append(f"[d{k}]")
    parts.append("".join(mix_labels) +
                 f"amix=inputs={len(mix_labels)}:normalize=0:duration=longest[a]")
    filter_complex = ";".join(parts)

    out_abs = os.path.join(root, output)
    _run([
        "ffmpeg", "-y", "-loglevel", "error",
        *inputs,
        "-filter_complex", filter_complex,
        "-map", "0:v", "-map", "[a]",
        "-t", f"{total:.3f}",
        "-c:v", "libx264", "-preset", "medium", "-crf", "20",
        "-pix_fmt", "yuv420p", "-c:a", "aac", "-b:a", "192k",
        out_abs,
    ])
    print(f"✓ Vidéo générée : {output}")
    return out_abs
