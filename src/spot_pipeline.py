"""Orchestration du format « Cherche les différences » (style vidéo Gemini).

Deux scènes côte à côte (A à gauche, B à droite), un minuteur circulaire au
centre qui décompte, puis une révélation progressive : des cercles verts
apparaissent un par un sur les différences, avec un « ding ». JSON piloté.

Layouts : ``side`` (paysage 16:9, deux panneaux côte à côte — comme la
référence) ou ``stack`` (vertical, panneaux empilés).
"""

from __future__ import annotations

import json
import os
import tempfile
from dataclasses import dataclass
from typing import List, Tuple

from PIL import Image, ImageDraw, ImageFont

from . import tts
from .game_pipeline import _pad_audio
from .game_sfx import synth_ding, synth_game_music
from .pipeline import _run
from .spot_diff import _base_tile, generate_scene, make_variant, render_panel

TEXT_FONT = "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"
GREEN = (60, 230, 96)
GREEN_SOFT = (150, 255, 170)


@dataclass
class SpotConfig:
    width: int = 1920
    height: int = 1080
    fps: int = 30
    layout: str = "side"          # "side" (paysage) | "stack" (vertical)
    pre_roll: float = 0.5
    reveal_step: float = 0.9      # apparition de chaque cercle (s)
    outro: float = 3.0            # maintien final avec CTA (s)


# --------------------------------------------------------------------------- #
# Géométrie des panneaux + du minuteur central
# --------------------------------------------------------------------------- #
def _geometry(cfg: SpotConfig):
    if cfg.layout == "side":
        pw, ph = cfg.width // 2, cfg.height
        offsets = [(0, 0), (pw, 0)]           # A gauche, B droite
        tcx, tcy = cfg.width // 2, int(cfg.height * 0.40)
    else:                                      # stack
        header, gap, bottom = 150, 14, 40
        ph = (cfg.height - header - gap - bottom) // 2
        pw = cfg.width
        offsets = [(0, header), (0, header + ph + gap)]
        tcx, tcy = cfg.width // 2, header // 2
    radius = int(min(cfg.width, cfg.height) * 0.085)
    return pw, ph, offsets, (tcx, tcy, radius)


def _text(draw, cx, cy, text, size, fill, anchor="mm", outline=None):
    font = ImageFont.truetype(TEXT_FONT, size)
    if outline:
        for dx in (-3, 0, 3):
            for dy in (-3, 0, 3):
                if dx or dy:
                    draw.text((cx + dx, cy + dy), text, font=font, fill=outline, anchor=anchor)
    draw.text((cx, cy), text, font=font, fill=fill, anchor=anchor)


def _glow_circle(draw, cx, cy, r, color, soft):
    for w, col in ((11, color), (5, soft)):
        draw.ellipse([cx - r, cy - r, cx + r, cy + r], outline=col, width=w)


def _timer_ring(draw, tc, center_text=None):
    tcx, tcy, R = tc
    # anneau lumineux
    draw.ellipse([tcx - R, tcy - R, tcx + R, tcy + R], outline=(255, 255, 255), width=10)
    draw.ellipse([tcx - R + 14, tcy - R + 14, tcx + R - 14, tcy + R - 14],
                 outline=(120, 200, 255), width=5)
    if center_text is not None:
        _text(draw, tcx, tcy, center_text, int(R * 0.85), (255, 255, 255),
              outline=(20, 40, 70))


def _compose(panelA, panelB, cfg, title, tc_text=None, circles=None, cta=None):
    pw, ph, offsets, tc = _geometry(cfg)
    img = Image.new("RGB", (cfg.width, cfg.height), (16, 14, 24))
    img.paste(panelA, offsets[0])
    img.paste(panelB, offsets[1])
    draw = ImageDraw.Draw(img)

    # séparation centrale + cadres
    if cfg.layout == "side":
        draw.line([(pw, 0), (pw, cfg.height)], fill=(255, 255, 255), width=4)
    for ox, oy in offsets:
        draw.rectangle([ox + 1, oy + 1, ox + pw - 2, oy + ph - 2],
                       outline=(255, 255, 255), width=3)

    # bandeau titre (haut-centre)
    tw = int(cfg.width * 0.46)
    draw.rounded_rectangle([(cfg.width - tw) // 2, 18, (cfg.width + tw) // 2, 92],
                           radius=34, fill=(20, 16, 30))
    _text(draw, cfg.width // 2, 55, title, int(cfg.height * 0.036), (255, 255, 255))

    # cercles de révélation sur LES DEUX panneaux (coordonnées locales)
    r = int(min(pw, ph) * 0.075)
    for (x, y) in (circles or []):
        for ox, oy in offsets:
            _glow_circle(draw, ox + x, oy + y, r, GREEN, GREEN_SOFT)

    # minuteur circulaire (texte central baké pour la phase reveal)
    _timer_ring(draw, tc, center_text=tc_text)

    if cta:
        cw = int(cfg.width * 0.56)
        y0, y1 = cfg.height - 88, cfg.height - 16
        cyb = (y0 + y1) // 2
        draw.rounded_rectangle([(cfg.width - cw) // 2, y0, (cfg.width + cw) // 2, y1],
                               radius=32, fill=GREEN)
        # pouce 👍 « like » à gauche du texte
        like_sz = int((y1 - y0) * 0.78)
        tile = _base_tile("👍", like_sz)
        font = ImageFont.truetype(TEXT_FONT, int(cfg.height * 0.030))
        tb = draw.textbbox((0, 0), cta, font=font)
        text_w = tb[2] - tb[0]
        group_w = tile.width + 18 + text_w
        gx = (cfg.width - group_w) // 2
        img.paste(tile, (gx, cyb - tile.height // 2), tile)
        _text(draw, gx + tile.width + 18 + text_w // 2, cyb, cta,
              int(cfg.height * 0.030), (12, 40, 20))
    return img


def _still_clip(image_path, out_path, dur, cfg, countdown=None):
    """Image fixe ; countdown=(timer, pre_roll) dessine le décompte au centre."""
    _, _, _, (tcx, tcy, R) = _geometry(cfg)
    vf = []
    if countdown:
        timer, pre = countdown
        fs = int(R * 0.85)
        for k in range(timer, 0, -1):
            start = pre + (timer - k)
            vf.append(
                f"drawtext=fontfile={TEXT_FONT}:text='{k}':fontcolor=white:"
                f"fontsize={fs}:borderw=6:bordercolor=0x284670:"
                f"x={tcx}-text_w/2:y={tcy}-text_h/2:"
                f"enable='between(t,{start:.2f},{start+1:.2f})'"
            )
    vf_str = ",".join(vf + ["format=yuv420p"])
    _run([
        "ffmpeg", "-y", "-loglevel", "error", "-loop", "1", "-i", image_path,
        "-t", f"{dur:.3f}", "-vf", vf_str, "-r", str(cfg.fps),
        "-c:v", "libx264", "-preset", "veryfast", "-crf", "20",
        "-pix_fmt", "yuv420p", out_path,
    ])


def generate(config_path, cfg=None, work_dir=None):
    cfg = cfg or SpotConfig()
    with open(config_path, encoding="utf-8") as fh:
        conf = json.load(fh)

    root = os.getcwd()
    voice = conf.get("voice", "fr-FR-DeniseNeural")
    rate = conf.get("rate", "+0%")
    music_path = conf.get("music", "")
    music_volume = float(conf.get("music_volume", 0.16))
    output = conf.get("output", "output/differences.mp4")
    theme = conf.get("theme", "alchimie")
    seed = int(conf.get("seed", 7))
    n = int(conf.get("num_differences", 8))
    timer = int(conf.get("timer", 50))
    title = conf.get("title", f"Trouve les {n} différences")
    hook = conf.get("hook", f"Trouve les {n} différences. Tu as {timer} secondes.")
    reveal_line = conf.get("reveal_line", "Les voilà !")
    cta = conf.get("cta", "T'en as trouvé combien ? Commente")
    if "layout" in conf:
        cfg.layout = conf["layout"]

    os.makedirs(os.path.dirname(os.path.abspath(output)) or ".", exist_ok=True)
    tmp = work_dir or tempfile.mkdtemp(prefix="spot_")
    os.makedirs(tmp, exist_ok=True)
    print(f"→ Dossier de travail : {tmp}  (layout {cfg.layout})")

    pw, ph, offsets, tc = _geometry(cfg)
    print(f"  Scène « {theme} » (seed {seed}) — panneaux {pw}x{ph}")
    scene = generate_scene(theme, seed, pw, ph)
    variant, diffs = make_variant(scene, theme, seed, n, pw, ph)
    print(f"  {len(scene)} éléments, {len(diffs)} différences")
    panelA = render_panel(scene, theme, pw, ph)
    panelB = render_panel(variant, theme, pw, ph)

    # images composées
    scan_png = os.path.join(tmp, "scan.png")
    _compose(panelA, panelB, cfg, title).save(scan_png)
    reveal_pngs = []
    for k in range(1, n + 1):
        p = os.path.join(tmp, f"rev_{k:02d}.png")
        _compose(panelA, panelB, cfg, title, tc_text=f"{k}/{n}",
                 circles=diffs[:k], cta=(cta if k == n else None)).save(p)
        reveal_pngs.append(p)

    # clips
    clips = []
    scan_dur = cfg.pre_roll + timer
    scan_clip = os.path.join(tmp, "scan.mp4")
    _still_clip(scan_png, scan_clip, scan_dur, cfg, countdown=(timer, cfg.pre_roll))
    clips.append(scan_clip)

    reveal_times, cursor = [], scan_dur
    for k, p in enumerate(reveal_pngs):
        dur = cfg.reveal_step + (cfg.outro if k == n - 1 else 0.0)
        c = os.path.join(tmp, f"rev_{k:02d}.mp4")
        _still_clip(p, c, dur, cfg)
        clips.append(c)
        reveal_times.append(cursor)
        cursor += dur
    total = cursor

    # voix
    backend = None
    hook_v = os.path.join(tmp, "hook.mp3")
    rev_v = os.path.join(tmp, "rev.mp3")
    cta_v = os.path.join(tmp, "cta.mp3")
    (_, backend) = tts.synthesize(hook, voice, rate, hook_v)
    tts.synthesize(reveal_line, voice, rate, rev_v)
    tts.synthesize(cta, voice, rate, cta_v)
    hook_pad = os.path.join(tmp, "hp.wav")
    rev_pad = os.path.join(tmp, "rp.wav")
    cta_pad = os.path.join(tmp, "cp.wav")
    _pad_audio(hook_v, hook_pad, cfg.pre_roll, scan_dur)
    _pad_audio(rev_v, rev_pad, 0.1, cfg.reveal_step * n)
    _pad_audio(cta_v, cta_pad, 0.2, cfg.outro)
    vlist = os.path.join(tmp, "voice.txt")
    with open(vlist, "w") as fh:
        for p in (hook_pad, rev_pad, cta_pad):
            fh.write(f"file '{os.path.abspath(p)}'\n")
    voice_track = os.path.join(tmp, "voice.wav")
    _run(["ffmpeg", "-y", "-loglevel", "error", "-f", "concat", "-safe", "0",
          "-i", vlist, "-c", "copy", voice_track])
    print(f"→ Voix : backend « {backend} » — durée totale {total:.1f}s")

    # concat vidéo
    clist = os.path.join(tmp, "clips.txt")
    with open(clist, "w") as fh:
        for c in clips:
            fh.write(f"file '{os.path.abspath(c)}'\n")
    video = os.path.join(tmp, "video.mp4")
    _run(["ffmpeg", "-y", "-loglevel", "error", "-f", "concat", "-safe", "0",
          "-i", clist, "-c", "copy", video])

    # sfx + musique
    ding = os.path.join(tmp, "ding.wav")
    synth_ding(ding)
    music_abs = os.path.join(root, music_path) if music_path else ""
    if music_path and not os.path.exists(music_abs):
        os.makedirs(os.path.dirname(music_abs) or ".", exist_ok=True)
        print(f"→ Musique absente, synthèse : {music_path}")
        synth_game_music(music_abs, duration=max(30, int(total) + 4))

    print("→ Montage final (voix + musique + dings)")
    inputs = ["-i", video, "-i", voice_track]
    idx = 2
    has_music = bool(music_path and os.path.exists(music_abs))
    if has_music:
        inputs += ["-stream_loop", "-1", "-i", music_abs]
        music_idx = idx
        idx += 1
    ding_base = idx
    for _ in reveal_times:
        inputs += ["-i", ding]

    parts, labels = [], ["[1:a]"]
    if has_music:
        parts.append(f"[{music_idx}:a]volume={music_volume}[mus]")
        labels.append("[mus]")
    for k, t in enumerate(reveal_times):
        parts.append(f"[{ding_base+k}:a]adelay={int(t*1000)}|{int(t*1000)},volume=0.85[d{k}]")
        labels.append(f"[d{k}]")
    parts.append("".join(labels) +
                 f"amix=inputs={len(labels)}:normalize=0:duration=longest[a]")

    out_abs = os.path.join(root, output)
    _run([
        "ffmpeg", "-y", "-loglevel", "error", *inputs,
        "-filter_complex", ";".join(parts),
        "-map", "0:v", "-map", "[a]", "-t", f"{total:.3f}",
        "-c:v", "libx264", "-preset", "medium", "-crf", "20",
        "-pix_fmt", "yuv420p", "-c:a", "aac", "-b:a", "192k", out_abs,
    ])
    print(f"✓ Vidéo générée : {output} ({total:.0f}s)")
    return out_abs
