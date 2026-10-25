"""Find chat bubbles in a screenshot by looking at the image, not the text.

Why this exists
---------------
Counting messages from OCR text alone failed in both directions on real
screenshots. The text counter chose a strategy by counting lines that ended in
something clock-like; on an iOS conversation OCR rendered the 12-hour clocks as
words ("pate", "nasi", "eyes"), the count landed either side of a threshold, and
the same eight pages came out as 76 messages one way and 7 the other against a
true 34.

The bubbles themselves are visible, and far more reliable than anything read
off them:

* A bubble's interior is a **flat, uniform colour**. The wallpaper behind it is
  not — WhatsApp's doodle pattern, or a photo — so the pixels between two lines
  of text say whether those lines share a bubble.
* **Outgoing bubbles are saturated** (green by default, or a theme colour);
  incoming ones are neutral (white in light mode, dark grey in dark mode). So
  colour tells us who sent each message, which OCR text on its own cannot.
* **Text on a non-flat background is inside an image** — a camera watermark on
  a room photo, a sticker's caption — and is not something anyone typed.

Speaker attribution is the part with the most consequence. On the scam
screenshot in data/samples/, several of the phrases layer 1 flags were typed by
the *victim* repeating back what they had been told. Without attribution the
narrator would report the renter's own words as the scammer's demand.

The screenshot is assumed to come from the renter's phone: outgoing = renter.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field

import numpy as np
import pytesseract
from PIL import Image

# Screen furniture occupies fixed bands on a phone screenshot.
HEADER_FRACTION = 0.105   # status bar + contact bar
FOOTER_FRACTION = 0.085   # message input bar

# Share of a text line's box that must be one colour for the line to sit on a
# bubble. Glyphs take a minority of the box; a photo has no majority at all.
DOMINANT_SHARE = 0.50

# Deciding whether two lines share a bubble. Each value sits mid-way across
# a gap measured on the two real conversations in data/samples.
FILL_TOLERANCE = 8.0     # colour distance still counted as the bubble's fill
MIN_ROW_FILL = 0.50      # same bubble >= 0.66 of a row, different <= 0.01
TIMESTAMP_HEIGHT = 0.66  # clocks 0.47-0.61x median height, text >= 0.73x

# Text on neither of the conversation's two bubble colours is not in a bubble:
# a camera's date-and-place stamp burned into a room photo, a caption inside an
# image. The flatness test above cannot catch it when the stamp sits on a flat
# part of the photo (a floor, a wall). Distance is the mean absolute RGB
# difference from the nearest reference fill. Measured on data/samples: every
# typed line, including quote boxes and link previews, within 11.1; the photo
# watermark in the legitimate chat at 18.3-24.7. Mid-way.
MEDIA_FILL_DISTANCE = 15.0
# A speaker's bubble colour must carry this many times the text of any other
# colour of theirs before lines far from it are dropped (see _reference_fills).
TRUSTED_COLOUR_SHARE = 2.0

# Stitching pages. Short replies ("ok", "boleh") recur for real, so
# only messages long enough to be distinctive are de-duplicated.
MIN_DEDUPE_CHARS = 20
FUZZY_MATCH = 0.85      # OCR reads the same message a little differently

# A clock time at the very end of a line: the bubble ends there.
_INLINE_CLOCK_END = re.compile(
    r"\s(?:\d{1,2}[:.,]\d{2}\s*(?:[ap]\.?m\.?)?|\d{4,5})\s*[a-zA-Z/\\|]{0,2}\s*$",
    re.IGNORECASE,
)

# A bubble fill with at least this chroma (max channel minus min channel) is
# outgoing. Measured on both real conversations in data/samples:
#
#                       fill              chroma
#   Android incoming    white             0
#   Android outgoing    pale green        29 - 39
#   iOS incoming        dark grey         <= 3
#   iOS outgoing        red               ~119
#
# Relative saturation was tried first and failed: on a dark grey a 3-unit
# channel difference reads as 8%, and WhatsApp's pale outgoing green only
# reaches 12-17%, so no single cut separated them. Absolute chroma leaves a gap
# of 3 to 29 across both platforms and themes.
OUTGOING_CHROMA = 15.0

_TICKS_OR_CLOCK = re.compile(
    r"^[\s\W]*(?:\d[\d:.,]{1,6}\s*(?:[ap]\.?\s*m\.?)?|[vVwW/\\|✓✔]{1,3}|"
    r"edited|diedit|forwa\w*|dimajukan|preview\s+pdf|tap\s+to\s+\w+)"
    r"[\s\W]*$",
    re.IGNORECASE,
)

# WhatsApp UI labels printed inside a bubble, above or below the message.
# OCR mangles them ("Forwarctect"), so match on a prefix.
_UI_LABEL = re.compile(
    # "forwa" not "forward": OCR renders it "Forwarctect", "Forwarcled".
    r"^\s*(?:[|@&>/\W]*\s*)?(?:forwa\w*|dimajukan|edited|diedit)\b[\s\W]*",
    re.IGNORECASE,
)

# Quote attribution: a phone number followed by "~Name". Anchored on the
# number so ordinary capitalised words are never taken for a name.
_PHONE_TILDE = re.compile(
    r"[+#]?\s*\d[\d\s-]{7,}\d\s*~?\s*[A-Z][a-zA-Z]+(?:\s+[A-Z][a-zA-Z]+)?,?"
)

# A clock-like token: "17:51", "7.46", "10:25pm", "1808", "17684 W".
_CLOCK_TOKEN = re.compile(
    r"(?<=\s)(\d{1,2}[:.,]\d{2}\s*(?:[ap]\.?m\.?)?|\d{4,5})\s*[a-zA-Z/\\|]{0,2}(?=\s|$)",
    re.IGNORECASE,
)

# A number right after one of these is an amount, not a clock:
# "Total DEPO 1900", "Baki 1400", "Booking 500".
_MONEY_WORD = re.compile(
    r"(?:rm|ringgit|depo|deposit|booking|baki|total|harga|sewa|rental|bayar|"
    r"utiliti|utility|fee|yuran)\s*$",
    re.IGNORECASE,
)


def _strip_clocks(text: str) -> str:
    """Remove clock times and ticks, leaving money amounts alone."""
    padded = f" {text} "

    def replace(match):
        # Index into the same padded string the pattern is running on.
        before = padded[:match.start()].rstrip()
        return match.group(0) if _MONEY_WORD.search(before) else " "

    return _CLOCK_TOKEN.sub(replace, padded).strip()


def _clean(text: str) -> str:
    """Strip UI furniture from a bubble's text, keeping what was typed."""
    text = _UI_LABEL.sub("", text)
    text = _PHONE_TILDE.sub("", text)
    text = re.sub(r"^\s*(?:anda|you)\b[\s:]*", "", text, flags=re.IGNORECASE)
    text = _strip_clocks(text)
    return re.sub(r"\s{2,}", " ", text).strip(" ,.|/\\-")


@dataclass
class Line:
    text: str
    left: int
    top: int
    right: int
    bottom: int
    fill: np.ndarray | None = None
    flat: bool = False


@dataclass
class Bubble:
    speaker: str                      # "renter" or "owner"
    lines: list[Line] = field(default_factory=list)

    @property
    def raw_text(self) -> str:
        return " ".join(line.text for line in self.lines).strip()

    @property
    def text(self) -> str:
        return _clean(self.raw_text)

    @property
    def top(self) -> int:
        return self.lines[0].top

    @property
    def bottom(self) -> int:
        return self.lines[-1].bottom


def _ocr_lines(image: Image.Image, preprocess) -> list[Line]:
    """Text lines with bounding boxes, from Tesseract's layout analysis."""
    data = pytesseract.image_to_data(
        preprocess(image), lang="eng+msa", config="--psm 3",
        output_type=pytesseract.Output.DICT,
    )
    grouped: dict[tuple, dict] = {}
    for index, word in enumerate(data["text"]):
        if not word.strip():
            continue
        try:
            if float(data["conf"][index]) < 0:
                continue
        except (TypeError, ValueError):
            continue
        key = (data["block_num"][index], data["par_num"][index],
               data["line_num"][index])
        entry = grouped.setdefault(key, {
            "words": [], "left": 10**9, "top": 10**9, "right": 0, "bottom": 0,
        })
        entry["words"].append(word)
        entry["left"] = min(entry["left"], data["left"][index])
        entry["top"] = min(entry["top"], data["top"][index])
        entry["right"] = max(entry["right"],
                             data["left"][index] + data["width"][index])
        entry["bottom"] = max(entry["bottom"],
                              data["top"][index] + data["height"][index])

    lines = [
        Line(" ".join(e["words"]), e["left"], e["top"], e["right"], e["bottom"])
        for e in grouped.values()
    ]
    return sorted(lines, key=lambda line: (line.top, line.left))


def _patch(pixels: np.ndarray, top: int, bottom: int, left: int, right: int):
    height, width = pixels.shape[:2]
    top, bottom = max(0, top), min(height, bottom)
    left, right = max(0, left), min(width, right)
    if bottom - top < 1 or right - left < 1:
        return None
    return pixels[top:bottom, left:right].reshape(-1, 3)


def _fill_of(pixels: np.ndarray, line: Line) -> tuple[np.ndarray | None, bool]:
    """The background colour behind a line of text, and whether it is flat.

    Read from *inside* the line's own box. Glyphs are thin, so the background
    is the majority colour there. An earlier version sampled strips above and
    below the text instead, and on a one-line bubble those strips fell outside
    the bubble onto the wallpaper — the line failed the flatness test and was
    discarded, losing whole messages.

    Flat means a single colour dominates the box. Text printed over a photo has
    no dominant colour, which is how watermarks and sticker captions are told
    apart from typed messages.
    """
    patch = _patch(pixels, line.top, line.bottom, line.left, line.right)
    if patch is None or len(patch) < 12:
        return None, False
    patch = patch.astype(int)

    # Mode colour, on a coarse grid so JPEG noise does not split it.
    quantised = (patch // 12) * 12
    codes = quantised[:, 0] * 65536 + quantised[:, 1] * 256 + quantised[:, 2]
    values, counts = np.unique(codes, return_counts=True)
    mode = values[counts.argmax()]
    mode_colour = np.array([mode // 65536, (mode // 256) % 256, mode % 256])

    close = np.abs(patch - mode_colour).mean(axis=1) < 26
    share = float(close.mean())
    fill = patch[close].mean(axis=0) if close.any() else mode_colour.astype(float)
    return fill, share >= DOMINANT_SHARE


def _chroma(colour: np.ndarray) -> float:
    """How far a colour is from grey: 0 for any neutral, large for a hue."""
    return float(colour.max()) - float(colour.min())


def _wallpaper_between(pixels: np.ndarray, above: Line, below: Line) -> bool:
    """Is there a band of wallpaper between two lines?

    Inside a bubble every row between two lines is mostly the bubble's fill —
    blank-line spacing is pure fill, and an emoji only covers a few columns.
    Between two bubbles at least one row crosses wallpaper. So the test is the
    *least* fill-covered row, not an average that the padding would dominate.

    Measured on both real conversations: same-bubble pairs never fall below
    0.66 of a row in fill; separate bubbles fall to 0.00-0.01 — with one
    exception, two dark bubbles over a dark part of a photo wallpaper, which
    colour cannot separate. Timestamps catch that case (see segment()).
    """
    top, bottom = above.bottom + 1, below.top - 1
    if bottom - top < 2 or above.fill is None:
        return False
    left, right = max(above.left, below.left), min(above.right, below.right)
    if right - left < 6:
        left, right = min(above.left, below.left), max(above.right, below.right)
    band = pixels[max(0, top):bottom, max(0, left):right].astype(float)
    if band.size == 0:
        return False
    close = np.abs(band - above.fill).mean(axis=2) < FILL_TOLERANCE
    return float(close.mean(axis=1).min()) < MIN_ROW_FILL


def _ends_in_clock(text: str) -> bool:
    """Does this line end in a clock time (and so close its bubble)?

    A trailing number after a money word is an amount, not a time: "Total DEPO
    1900" is a deposit, and treating it as 19:00 split that bubble in two.
    """
    match = _INLINE_CLOCK_END.search(text)
    if not match:
        return False
    return not _MONEY_WORD.search(text[:match.start()].rstrip())


def segment(image: Image.Image, preprocess) -> list[Bubble]:
    """Split one screenshot into bubbles, each attributed to a speaker.

    A new bubble starts when any of these holds between two text lines:

    1. **The speaker changes** — fill colour flips between neutral and hued.
    2. **A timestamp sits between them.** Every WhatsApp bubble ends with its
       clock, printed smaller than message text on both platforms (measured
       0.47-0.61x the median line height against >=0.73x for message text).
       Detecting it by size works even when OCR turns the digits into letters,
       which it did for every iOS timestamp in data/samples.
    3. **The line above ends in a clock**, for bubbles where the time is
       printed inline on the last line rather than on its own row.
    4. **There is wallpaper between them.**
    """
    rgb = image.convert("RGB")
    pixels = np.asarray(rgb)
    width, height = rgb.size

    raw = [
        line for line in _ocr_lines(image, preprocess)
        if line.top >= height * HEADER_FRACTION
        and line.bottom <= height * (1 - FOOTER_FRACTION)
    ]
    if not raw:
        return []

    heights = sorted(line.bottom - line.top for line in raw)
    median_height = float(heights[len(heights) // 2])

    # Walk in reading order. Timestamps are not kept as text, but each one
    # marks the end of the bubble above it.
    entries: list[tuple[str, Line]] = []
    for line in raw:
        small = (line.bottom - line.top) <= median_height * TIMESTAMP_HEIGHT
        if _TICKS_OR_CLOCK.match(line.text) or (small and len(line.text) <= 14):
            entries.append(("end", line))
            continue

        line.fill, line.flat = _fill_of(pixels, line)
        # Text on a textured background is inside an image — a watermark on a
        # room photo, a sticker's caption. Nobody typed it.
        if not line.flat or line.fill is None:
            continue
        # A centred, narrow line on neither margin is a system notice: a date
        # separator, the encryption banner.
        centre = (line.left + line.right) / 2
        if (abs(centre - width / 2) < width * 0.08
                and line.left > width * 0.14 and line.right < width * 0.86):
            continue
        entries.append(("text", line))

    bubbles: list[Bubble] = []
    closed = True
    for kind, line in entries:
        if kind == "end":
            closed = True
            continue

        speaker = "renter" if _chroma(line.fill) >= OUTGOING_CHROMA else "owner"
        joins = (
            bubbles
            and not closed
            and bubbles[-1].speaker == speaker
            and not _wallpaper_between(pixels, bubbles[-1].lines[-1], line)
        )
        if joins:
            bubbles[-1].lines.append(line)
        else:
            bubbles.append(Bubble(speaker, [line]))

        # An inline clock at the end of this line closes its bubble.
        closed = _ends_in_clock(line.text)

    # A bubble with nothing left once furniture is stripped was furniture.
    return [bubble for bubble in bubbles if _has_real_word(bubble.text)]


def _reference_fills(pages: list[list[Bubble]]) -> list[np.ndarray]:
    """Colours that count as "inside a bubble", from the whole upload.

    Each speaker's line fills are grouped into colours (within
    MEDIA_FILL_DISTANCE of a group's text-weighted centre). A speaker's main
    colour is trusted only if it carries at least TRUSTED_COLOUR_SHARE times
    the text of any other colour of theirs; then lines far from it may be
    dropped. If not - a speaker with little text, and a photo stamp as long as
    their messages - every colour of that speaker is kept as a reference, so
    nothing of theirs is dropped. Losing a real message is worse than keeping
    a watermark.
    """
    references = []
    for speaker in ("renter", "owner"):
        lines = sorted(
            (line for page in pages for bubble in page if bubble.speaker == speaker
             for line in bubble.lines if line.fill is not None),
            key=lambda line: -len(line.text))
        groups: list[list] = []            # [centre, characters]
        for line in lines:
            weight = max(1, len(line.text))
            for group in groups:
                if float(np.abs(line.fill - group[0]).mean()) <= MEDIA_FILL_DISTANCE:
                    group[0] = (group[0] * group[1] + line.fill * weight) / (group[1] + weight)
                    group[1] += weight
                    break
            else:
                groups.append([np.array(line.fill, dtype=float), weight])
        if not groups:
            continue
        groups.sort(key=lambda group: -group[1])
        trusted = len(groups) == 1 or groups[0][1] >= TRUSTED_COLOUR_SHARE * groups[1][1]
        references += [groups[0][0]] if trusted else [group[0] for group in groups]
    return references


def drop_media_text(pages: list[list[Bubble]]) -> list[list[Bubble]]:
    """Remove lines printed inside images - photo watermarks, captions.

    A line is kept when its background is within MEDIA_FILL_DISTANCE of either
    speaker's bubble colour. Bubbles left with no real word are removed.
    """
    references = _reference_fills(pages)
    if not references:
        return pages

    def in_a_bubble(line: Line) -> bool:
        if line.fill is None:
            return True
        return min(float(np.abs(line.fill - ref).mean()) for ref in references) <= MEDIA_FILL_DISTANCE

    cleaned = []
    for page in pages:
        kept = []
        for bubble in page:
            lines = [line for line in bubble.lines if in_a_bubble(line)]
            if lines and _has_real_word(_clean(" ".join(l.text for l in lines))):
                kept.append(Bubble(bubble.speaker, lines))
        cleaned.append(kept)
    return cleaned


def _has_real_word(text: str) -> bool:
    """At least one token of three or more letters."""
    return any(len(token) >= 3 for token in re.findall(r"[^\W\d_]+", text))


# ---------------------------------------------------------------------------
# Joining pages into one conversation
# ---------------------------------------------------------------------------

def _key(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", "", text.lower())


def _similar(a: str, b: str) -> bool:
    """Same message read twice by OCR, allowing for its misreadings."""
    from difflib import SequenceMatcher

    if not a or not b:
        return False
    return SequenceMatcher(None, a, b).ratio() >= FUZZY_MATCH


def stitch(pages: list[list[Bubble]]) -> list[tuple[str, str]]:
    """Merge per-page bubbles into one conversation of (speaker, text).

    Two things put the same text on screen twice, and a reader counts it once:

    * **Quoted replies** show the earlier message again inside the reply. The
      quote sits in the *other* person's bubble, so matching must ignore the
      speaker — comparing "renter: x" with "owner: x" never matched, and every
      quote was counted as a message of its own.
    * **Page seams** repeat a message at the bottom of one screenshot and the
      top of the next. OCR reads the two copies slightly differently ("ya laqi"
      against "yg lagi"), so matching is fuzzy.

    The first occurrence is kept, with its original speaker. When a repeat is
    only the *start* of a later bubble, the repeat is trimmed and the reply
    after it kept.
    """
    seen: list[str] = []
    result: list[tuple[str, str]] = []

    for bubbles in pages:
        for bubble in bubbles:
            text = bubble.text
            words = text.split()

            # A quote at the head of a reply: drop it, keep the reply.
            for index in range(len(words) - 1, 0, -1):
                head = _key(" ".join(words[:index]))
                if len(head) >= MIN_DEDUPE_CHARS and any(
                    _similar(head, earlier) for earlier in seen
                ):
                    words = words[index:]
                    break

            text = " ".join(words)
            key = _key(text)
            if not _has_real_word(text):
                continue
            if len(key) >= MIN_DEDUPE_CHARS and any(
                _similar(key, earlier) for earlier in seen
            ):
                continue
            seen.append(key)
            result.append((bubble.speaker, text))
    return result
