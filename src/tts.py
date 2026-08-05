"""Génération de la voix off (text-to-speech).

Deux moteurs sont supportés, sélectionnés par la variable d'environnement
``TTS_BACKEND`` (``auto`` par défaut) :

* ``edge``   — Microsoft Edge TTS. Voix neuronales très naturelles (celles
               demandées dans le JSON, ex. ``fr-FR-DeniseNeural``). Nécessite
               un accès réseau vers les serveurs de synthèse Microsoft.
               Fournit en prime les *timings mot à mot*, utilisés pour caler
               précisément les sous-titres.
* ``espeak`` — eSpeak NG, 100 % hors-ligne. Voix robotique mais fonctionne
               partout (utilisé comme repli quand ``edge`` est indisponible).

Chaque moteur renvoie un :class:`Narration` : chemin du fichier audio, durée,
et éventuellement les mots horodatés.
"""

from __future__ import annotations

import asyncio
import os
import shutil
import subprocess
from dataclasses import dataclass, field
from typing import List, Optional, Tuple


@dataclass
class Word:
    """Un mot prononcé et sa position temporelle (en secondes)."""

    text: str
    start: float
    end: float


@dataclass
class Narration:
    """Résultat d'une synthèse vocale pour une scène."""

    audio_path: str
    duration: float
    words: List[Word] = field(default_factory=list)


def _ffprobe_duration(path: str) -> float:
    """Durée d'un fichier audio en secondes via ffprobe."""
    out = subprocess.check_output(
        [
            "ffprobe", "-v", "error", "-show_entries", "format=duration",
            "-of", "default=noprint_wrappers=1:nokey=1", path,
        ]
    )
    return float(out.decode().strip())


# --------------------------------------------------------------------------- #
# Backend Edge TTS
# --------------------------------------------------------------------------- #
def _edge_synthesize(text: str, voice: str, rate: str, out_path: str) -> Narration:
    import edge_tts  # import tardif : optionnel

    proxy = os.environ.get("HTTPS_PROXY") or os.environ.get("https_proxy")

    async def _run() -> List[Word]:
        communicate = edge_tts.Communicate(text, voice, rate=rate, proxy=proxy)
        words: List[Word] = []
        with open(out_path, "wb") as fh:
            async for chunk in communicate.stream():
                if chunk["type"] == "audio":
                    fh.write(chunk["data"])
                elif chunk["type"] == "WordBoundary":
                    start = chunk["offset"] / 1e7          # 100-ns -> s
                    dur = chunk["duration"] / 1e7
                    words.append(Word(chunk["text"], start, start + dur))
        return words

    words = asyncio.run(_run())
    if os.path.getsize(out_path) == 0:
        raise RuntimeError("Edge TTS n'a renvoyé aucun audio")
    return Narration(out_path, _ffprobe_duration(out_path), words)


# --------------------------------------------------------------------------- #
# Backend eSpeak NG (hors-ligne)
# --------------------------------------------------------------------------- #
def _espeak_rate_wpm(rate: str) -> int:
    """Convertit un « rate » façon Edge (« +15% ») en mots/minute eSpeak."""
    base = 165
    try:
        pct = int(rate.strip().rstrip("%"))
    except (ValueError, AttributeError):
        pct = 0
    return max(80, int(base * (1 + pct / 100.0)))


def _espeak_synthesize(text: str, voice: str, rate: str, out_path: str) -> Narration:
    # On déduit la langue eSpeak du préfixe de la voix Edge (ex. « fr-FR »).
    lang = "fr"
    if voice and "-" in voice:
        lang = voice.split("-")[0].lower()

    wpm = _espeak_rate_wpm(rate)
    wav_path = out_path.rsplit(".", 1)[0] + ".wav"
    subprocess.run(
        ["espeak-ng", "-v", lang, "-s", str(wpm), "-w", wav_path, text],
        check=True,
    )
    # Transcode en mp3 pour homogénéiser la suite de la chaîne.
    subprocess.run(
        ["ffmpeg", "-y", "-loglevel", "error", "-i", wav_path,
         "-codec:a", "libmp3lame", "-qscale:a", "3", out_path],
        check=True,
    )
    os.remove(wav_path)
    # eSpeak ne fournit pas de timings : on laisse la liste vide, le module
    # de sous-titres répartira les mots proportionnellement.
    return Narration(out_path, _ffprobe_duration(out_path), [])


# --------------------------------------------------------------------------- #
# Point d'entrée
# --------------------------------------------------------------------------- #
def synthesize(text: str, voice: str, rate: str, out_path: str) -> Tuple[Narration, str]:
    """Synthétise ``text`` et renvoie (Narration, nom_du_backend_utilisé).

    Respecte ``TTS_BACKEND`` (``auto`` | ``edge`` | ``espeak``). En mode
    ``auto``, tente Edge puis retombe sur eSpeak.
    """
    backend = os.environ.get("TTS_BACKEND", "auto").lower()

    if backend == "espeak":
        return _espeak_synthesize(text, voice, rate, out_path), "espeak"

    if backend == "edge":
        return _edge_synthesize(text, voice, rate, out_path), "edge"

    # auto
    try:
        return _edge_synthesize(text, voice, rate, out_path), "edge"
    except Exception as exc:  # réseau bloqué, DRM, etc.
        if not shutil.which("espeak-ng"):
            raise
        print(f"    ⚠ Edge TTS indisponible ({type(exc).__name__}), repli sur eSpeak NG")
        return _espeak_synthesize(text, voice, rate, out_path), "espeak"
