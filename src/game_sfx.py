"""Effets sonores et musique pour le format « Trouve l'intrus ».

Tout est synthétisé avec ffmpeg (libre de droits, autonome) :

* ``synth_ding``       — cloche courte et satisfaisante jouée au reveal ;
* ``synth_game_music`` — nappe légère et enjouée (accord majeur) en fond.
"""

from __future__ import annotations

import subprocess


def synth_ding(out_path: str) -> str:
    """Petite cloche brillante (~0,7 s) pour la révélation."""
    subprocess.run(
        ["ffmpeg", "-y", "-loglevel", "error",
         "-f", "lavfi", "-i", "sine=frequency=988:duration=0.7",
         "-f", "lavfi", "-i", "sine=frequency=1319:duration=0.7",
         "-filter_complex",
         "[0:a][1:a]amix=inputs=2:normalize=0,"
         "aecho=0.8:0.85:60:0.3,"
         "afade=t=out:st=0.08:d=0.6,volume=1.4[out]",
         "-map", "[out]", "-ac", "2", "-ar", "44100", out_path],
        check=True,
    )
    return out_path


def synth_game_music(out_path: str, duration: int = 60) -> str:
    """Nappe légère en Do majeur (Do Mi Sol Si), trémolo doux, écho court."""
    freqs = [261.63, 329.63, 392.00, 493.88]
    inputs = []
    for f in freqs:
        inputs += ["-f", "lavfi", "-i", f"sine=frequency={f}:duration={duration}"]
    n = len(freqs)
    mix = "".join(f"[{i}:a]" for i in range(n))
    fg = (
        f"{mix}amix=inputs={n}:normalize=0[raw];"
        "[raw]tremolo=f=2.2:d=0.5,lowpass=f=2200,highpass=f=180,"
        "aecho=0.7:0.7:200|400:0.3|0.2,"
        f"volume=0.8,afade=t=in:st=0:d=2,afade=t=out:st={duration-2}:d=2[out]"
    )
    subprocess.run(
        ["ffmpeg", "-y", "-loglevel", "error", *inputs,
         "-filter_complex", fg, "-map", "[out]",
         "-codec:a", "libmp3lame", "-qscale:a", "4", out_path],
        check=True,
    )
    return out_path


if __name__ == "__main__":
    synth_ding("assets/sfx/ding.wav")
    synth_game_music("assets/music/game_light.mp3")
