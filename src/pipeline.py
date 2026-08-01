"""Orchestration de l'usine à vidéos faceless.

Étapes, à partir d'un JSON décrivant la vidéo :

1. Synthèse vocale de chaque scène (voix off) + récupération de l'image.
2. Placement des scènes sur une timeline (parole + respiration).
3. Génération des sous-titres ASS calés sur la parole.
4. Rendu de chaque scène (image animée façon Ken Burns).
5. Concaténation des scènes.
6. Montage audio : voix off concaténée + musique de fond mixée.
7. Mux final avec sous-titres incrustés.

Le rendu se fait par étapes (fichiers intermédiaires dans un dossier de
travail) pour rester robuste et débogable.
"""

from __future__ import annotations

import json
import os
import subprocess
import tempfile
from dataclasses import dataclass
from typing import List

from . import images, tts
from .make_music import synth_cosmic_dark
from .subtitles import ScenePlan, build_ass


@dataclass
class RenderConfig:
    width: int = 1080
    height: int = 1920
    fps: int = 30
    tail: float = 0.6            # respiration ajoutée après chaque réplique (s)
    lead: float = 0.25           # petit silence en tête de scène (s)
    font: str = "DejaVu Sans"


def _run(cmd: List[str]) -> None:
    """Exécute ffmpeg/ffprobe en remontant proprement stderr en cas d'échec."""
    proc = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    if proc.returncode != 0:
        raise RuntimeError(
            "Échec commande: " + " ".join(cmd[:3]) + " ...\n"
            + proc.stderr.decode(errors="replace")[-1500:]
        )


def _kenburns_filter(cfg: RenderConfig, frames: int, zoom_in: bool) -> str:
    """Filtre vidéo Ken Burns pour une image fixe (léger zoom lent centré)."""
    w, h = cfg.width, cfg.height
    if zoom_in:
        z = f"min(1.0+0.12*on/{frames},1.12)"
    else:
        z = f"max(1.12-0.12*on/{frames},1.0)"
    # sur-échantillonnage x2 avant zoompan pour limiter le tremblement
    return (
        f"scale={w*2}:{h*2},"
        f"zoompan=z='{z}':d={frames}:"
        f"x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)':"
        f"s={w}x{h}:fps={cfg.fps},"
        f"format=yuv420p"
    )


def _render_scene_clip(image_path: str, out_path: str, total_dur: float,
                       cfg: RenderConfig, zoom_in: bool) -> None:
    frames = max(1, round(total_dur * cfg.fps))
    _run([
        "ffmpeg", "-y", "-loglevel", "error",
        "-loop", "1", "-i", image_path,
        "-t", f"{total_dur:.3f}",
        "-vf", _kenburns_filter(cfg, frames, zoom_in),
        "-r", str(cfg.fps),
        "-c:v", "libx264", "-preset", "veryfast", "-crf", "20",
        "-pix_fmt", "yuv420p",
        out_path,
    ])


def _padded_scene_audio(voice_path: str, out_path: str,
                        lead: float, total_dur: float) -> None:
    """Ajoute lead (silence en tête) + pad jusqu'à total_dur (respiration)."""
    _run([
        "ffmpeg", "-y", "-loglevel", "error",
        "-i", voice_path,
        "-af", f"adelay={int(lead*1000)}|{int(lead*1000)},"
               f"apad=whole_dur={total_dur:.3f},aresample=44100",
        "-t", f"{total_dur:.3f}",
        "-ac", "2", "-ar", "44100",
        out_path,
    ])


def generate(config_path: str, cfg: RenderConfig | None = None,
             work_dir: str | None = None) -> str:
    cfg = cfg or RenderConfig()
    with open(config_path, encoding="utf-8") as fh:
        conf = json.load(fh)

    root = os.getcwd()
    voice = conf.get("voice", "fr-FR-DeniseNeural")
    rate = conf.get("rate", "+0%")
    music_path = conf.get("music", "")
    music_volume = float(conf.get("music_volume", 0.12))
    output = conf.get("output", "output/video.mp4")
    scenes = conf["scenes"]

    os.makedirs(os.path.dirname(os.path.abspath(output)) or ".", exist_ok=True)
    tmp = work_dir or tempfile.mkdtemp(prefix="usine_")
    os.makedirs(tmp, exist_ok=True)
    print(f"→ Dossier de travail : {tmp}")

    # --- Étape 1 : voix off + images ------------------------------------- #
    plans: List[ScenePlan] = []
    scene_audio_files: List[str] = []
    scene_image_files: List[str] = []
    cursor = 0.0
    backend_used = None

    for i, scene in enumerate(scenes):
        text = scene["text"].strip()
        query = scene.get("image_query", conf.get("title", "abstract"))
        print(f"  [{i+1}/{len(scenes)}] TTS + image — {query!r}")

        voice_file = os.path.join(tmp, f"voice_{i:02d}.mp3")
        narration, backend_used = tts.synthesize(text, voice, rate, voice_file)

        img_file = os.path.join(tmp, f"img_{i:02d}.png")
        images.fetch_image(query, img_file, cfg.width, cfg.height)

        speech_dur = narration.duration
        total_dur = cfg.lead + speech_dur + cfg.tail

        plans.append(ScenePlan(
            index=i,
            start=cursor + cfg.lead,          # la parole commence après le lead
            speech_dur=speech_dur,
            total_dur=total_dur,
            text=text,
            words=narration.words,
        ))
        scene_audio_files.append(voice_file)
        scene_image_files.append(img_file)
        cursor += total_dur

    total_video = cursor
    print(f"→ Voix : backend « {backend_used} » — durée totale {total_video:.1f}s")

    # --- Étape 2 : sous-titres ASS --------------------------------------- #
    ass_path = os.path.join(tmp, "subs.ass")
    with open(ass_path, "w", encoding="utf-8") as fh:
        fh.write(build_ass(plans, cfg.width, cfg.height, cfg.font))

    # --- Étape 3 : clips de scène (Ken Burns) ---------------------------- #
    clip_files = []
    for i, plan in enumerate(plans):
        clip = os.path.join(tmp, f"clip_{i:02d}.mp4")
        print(f"  Rendu scène {i+1}/{len(plans)} ({plan.total_dur:.1f}s)")
        _render_scene_clip(scene_image_files[i], clip, plan.total_dur, cfg,
                           zoom_in=(i % 2 == 0))
        clip_files.append(clip)

    # --- Étape 4 : concaténation vidéo ----------------------------------- #
    concat_list = os.path.join(tmp, "clips.txt")
    with open(concat_list, "w") as fh:
        for c in clip_files:
            fh.write(f"file '{os.path.abspath(c)}'\n")
    video_silent = os.path.join(tmp, "video_silent.mp4")
    _run(["ffmpeg", "-y", "-loglevel", "error", "-f", "concat", "-safe", "0",
          "-i", concat_list, "-c", "copy", video_silent])

    # --- Étape 5 : voix off concaténée ----------------------------------- #
    padded = []
    for i, plan in enumerate(plans):
        p = os.path.join(tmp, f"vpad_{i:02d}.wav")
        _padded_scene_audio(scene_audio_files[i], p, cfg.lead, plan.total_dur)
        padded.append(p)
    va_list = os.path.join(tmp, "voice.txt")
    with open(va_list, "w") as fh:
        for p in padded:
            fh.write(f"file '{os.path.abspath(p)}'\n")
    voice_track = os.path.join(tmp, "voice_full.wav")
    _run(["ffmpeg", "-y", "-loglevel", "error", "-f", "concat", "-safe", "0",
          "-i", va_list, "-c", "copy", voice_track])

    # --- Étape 6 : musique de fond --------------------------------------- #
    music_abs = os.path.join(root, music_path) if music_path else ""
    if music_path and not os.path.exists(music_abs):
        os.makedirs(os.path.dirname(music_abs) or ".", exist_ok=True)
        print(f"→ Musique absente, synthèse d'un lit d'ambiance : {music_path}")
        synth_cosmic_dark(music_abs)

    # --- Étape 7 : mux final (sous-titres + voix + musique) -------------- #
    print("→ Montage final (sous-titres + voix + musique)")
    ass_esc = ass_path.replace("\\", "/").replace(":", "\\:").replace("'", "\\'")

    if music_path and os.path.exists(music_abs):
        # ducking : la musique baisse quand la voix parle (sidechaincompress)
        filter_complex = (
            f"[0:v]subtitles='{ass_esc}'[v];"
            f"[1:a]asplit=2[voice][key];"
            f"[2:a]volume={music_volume}[mus];"
            f"[mus][key]sidechaincompress=threshold=0.03:ratio=6:attack=20:release=350[duck];"
            f"[voice][duck]amix=inputs=2:normalize=0:duration=first[a]"
        )
        cmd = [
            "ffmpeg", "-y", "-loglevel", "error",
            "-i", video_silent,
            "-i", voice_track,
            "-stream_loop", "-1", "-i", music_abs,
            "-filter_complex", filter_complex,
            "-map", "[v]", "-map", "[a]",
            "-t", f"{total_video:.3f}",
            "-c:v", "libx264", "-preset", "medium", "-crf", "20",
            "-pix_fmt", "yuv420p",
            "-c:a", "aac", "-b:a", "192k",
            os.path.join(root, output),
        ]
    else:
        filter_complex = f"[0:v]subtitles='{ass_esc}'[v]"
        cmd = [
            "ffmpeg", "-y", "-loglevel", "error",
            "-i", video_silent, "-i", voice_track,
            "-filter_complex", filter_complex,
            "-map", "[v]", "-map", "1:a",
            "-t", f"{total_video:.3f}",
            "-c:v", "libx264", "-preset", "medium", "-crf", "20",
            "-pix_fmt", "yuv420p", "-c:a", "aac", "-b:a", "192k",
            os.path.join(root, output),
        ]
    _run(cmd)

    out_abs = os.path.join(root, output)
    print(f"✓ Vidéo générée : {output}")
    return out_abs
