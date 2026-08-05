"""Synthétise un lit sonore d'ambiance « cosmic dark » libre de droits.

Utilisé automatiquement par la pipeline lorsque le fichier musical référencé
dans le JSON est absent, afin que l'usine reste 100 % autonome. Le rendu est
un pad de nappes graves (accord de Mi mineur) avec trémolo lent, écho et
filtrage passe-bas pour une texture spatiale et sombre.
"""

from __future__ import annotations

import subprocess


def synth_cosmic_dark(out_path: str, duration: int = 45) -> str:
    # Accord grave Mi mineur : E1, E2, G2, B2, E3.
    freqs = [41.20, 82.41, 98.00, 123.47, 164.81]
    inputs = []
    for f in freqs:
        inputs += ["-f", "lavfi", "-i", f"sine=frequency={f}:duration={duration}"]

    n = len(freqs)
    mix = "".join(f"[{i}:a]" for i in range(n))
    filtergraph = (
        f"{mix}amix=inputs={n}:normalize=0[raw];"
        # trémolo lent pour la respiration + passe-bas pour retirer le haut du spectre
        "[raw]tremolo=f=0.1:d=0.7,lowpass=f=520,"
        # écho pour la profondeur, puis mise à niveau douce et fondus
        "aecho=0.8:0.9:600|1200:0.4|0.25,"
        "volume=0.9,afade=t=in:st=0:d=3,afade=t=out:st="
        f"{duration - 3}:d=3[out]"
    )

    subprocess.run(
        ["ffmpeg", "-y", "-loglevel", "error", *inputs,
         "-filter_complex", filtergraph, "-map", "[out]",
         "-codec:a", "libmp3lame", "-qscale:a", "4", out_path],
        check=True,
    )
    return out_path


if __name__ == "__main__":
    import sys

    synth_cosmic_dark(sys.argv[1] if len(sys.argv) > 1 else "assets/music/cosmic_dark.mp3")
