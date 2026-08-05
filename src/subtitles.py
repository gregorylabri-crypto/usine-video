"""Construction des sous-titres incrustés au format ASS (libass).

Style « short vertical » : légendes courtes (quelques mots), centrées bas,
grosse graisse, contour noir marqué pour rester lisibles sur n'importe quel
fond.

Deux sources de timing :

* Si la narration fournit des mots horodatés (backend Edge TTS), les légendes
  sont calées exactement sur la parole.
* Sinon (eSpeak), les mots sont répartis proportionnellement à leur longueur
  sur la durée de parole de la scène.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import List, Sequence

from .tts import Word


@dataclass
class ScenePlan:
    """Une scène telle que placée sur la timeline finale."""

    index: int
    start: float          # début de la scène dans la vidéo globale (s)
    speech_dur: float     # durée réelle de la parole (s)
    total_dur: float      # durée de la scène = parole + respiration (s)
    text: str
    words: List[Word]


def _fmt_time(t: float) -> str:
    """Formate un temps en H:MM:SS.cc (centièmes) pour l'ASS."""
    if t < 0:
        t = 0
    cs = int(round(t * 100))
    h, cs = divmod(cs, 360000)
    m, cs = divmod(cs, 6000)
    s, cs = divmod(cs, 100)
    return f"{h:d}:{m:02d}:{s:02d}.{cs:02d}"


def _chunk_words(words: Sequence[str], max_words: int, max_chars: int) -> List[List[str]]:
    """Regroupe les mots en légendes courtes et lisibles."""
    chunks: List[List[str]] = []
    cur: List[str] = []
    for w in words:
        tentative = cur + [w]
        if cur and (len(tentative) > max_words or len(" ".join(tentative)) > max_chars):
            chunks.append(cur)
            cur = [w]
        else:
            cur = tentative
    if cur:
        chunks.append(cur)
    return chunks


def _caption_lines(plan: ScenePlan, max_words: int, max_chars: int):
    """Renvoie une liste de (start, end, texte) pour une scène."""
    raw_words = plan.text.split()
    if not raw_words:
        return []

    chunks = _chunk_words(raw_words, max_words, max_chars)

    # Cas 1 : timings mot à mot disponibles (Edge TTS).
    if plan.words and len(plan.words) >= len(raw_words) * 0.6:
        lines = []
        wi = 0
        for chunk in chunks:
            n = len(chunk)
            grp = plan.words[wi:wi + n]
            wi += n
            if not grp:
                continue
            start = plan.start + grp[0].start
            end = plan.start + grp[-1].end
            lines.append((start, end, " ".join(chunk)))
        # étire la dernière légende jusqu'au bout de la parole
        if lines:
            s, _, t = lines[-1]
            lines[-1] = (s, plan.start + plan.speech_dur, t)
        return lines

    # Cas 2 : pas de timing -> répartition proportionnelle à la longueur.
    total_chars = sum(len(" ".join(c)) for c in chunks) or 1
    lines = []
    cursor = plan.start
    speech = plan.speech_dur
    for chunk in chunks:
        share = len(" ".join(chunk)) / total_chars
        dur = speech * share
        lines.append((cursor, cursor + dur, " ".join(chunk)))
        cursor += dur
    return lines


def build_ass(
    plans: Sequence[ScenePlan],
    width: int,
    height: int,
    font: str = "DejaVu Sans",
    max_words: int = 4,
    max_chars: int = 22,
) -> str:
    """Construit le contenu d'un fichier ASS pour toutes les scènes."""
    # Taille de police proportionnelle à la largeur du cadre.
    font_size = int(width * 0.072)
    margin_v = int(height * 0.16)
    outline = max(2, int(width * 0.006))
    shadow = max(1, int(width * 0.003))

    header = f"""[Script Info]
ScriptType: v4.00+
PlayResX: {width}
PlayResY: {height}
WrapStyle: 2
ScaledBorderAndShadow: yes

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: Caption,{font},{font_size},&H00FFFFFF,&H00FFFFFF,&H00000000,&H64000000,-1,0,0,0,100,100,0,0,1,{outline},{shadow},2,60,60,{margin_v},1

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
"""

    events = []
    for plan in plans:
        for start, end, text in _caption_lines(plan, max_words, max_chars):
            # \fad = fondu entrée/sortie ; échappe les accolades éventuelles
            safe = text.replace("{", "(").replace("}", ")")
            events.append(
                f"Dialogue: 0,{_fmt_time(start)},{_fmt_time(end)},Caption,,0,0,0,,"
                f"{{\\fad(120,120)}}{safe}"
            )
    return header + "\n".join(events) + "\n"
