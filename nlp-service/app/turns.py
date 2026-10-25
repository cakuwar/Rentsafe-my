"""Counting how much conversation is actually visible in a piece of text.

Layer 2's short-input guard is driven by this number, so it has to mean the same
thing everywhere: in the truncation sweep that sets the thresholds, in the guard
itself, and in the docs.

The unit is a **message** — one chat bubble — not a line. OCR of a WhatsApp
screenshot emits one line per *visual* line, so a long message wraps across
several, and the phone's own furniture lands in the text too. Real output from a
scam screenshot in this project looked like:

    10:34 a fd @
    rumah sewa threads
    rm800 imonth rental
    rm800 imonth deposit rm100 air api
    total rm1700 10:25 pm
    @ mesej cn ¢ |

Counting non-blank lines gives six for what is really one message. The inflation
was not theoretical: two real screenshot sets reported 146 and 103 "turns" for
conversations holding perhaps twenty messages, sailing past a guard meant to
catch thin input.

Boundaries are found in whichever of three ways the text supports:

1. **Speaker labels** ("Renter:", "Owner:") mark messages exactly. Used first
   when present, which is the case for the CSV corpus.
2. **Trailing timestamps.** WhatsApp prints a clock time at the end of every
   bubble, so in screenshot OCR a line ending in a time closes a message. This
   is the only reliable boundary in real screenshots.
3. **Line breaks**, once furniture is stripped — the fallback for plain text.

Note what is deliberately *not* used: "line starts with a lowercase letter, so it
continues the previous one". In Malay chat most messages open lowercase
("lupa nak tnya", "tak kenapa ye"), so that rule collapses whole conversations
into a single message.
"""
import re

_SPEAKER = re.compile(
    r"^\s*(?:renter|owner|pemilik|penyewa|tenant|agent|ejen)\s*:",
    re.IGNORECASE,
)

# Clock times as OCR renders them. Real screenshots mangle these badly: one
# conversation produced "5.95", "1808", "7.46", "17684 W", "46.9,", "57.37 w",
# "1745" and "45.45" for what were all ordinary timestamps. Matching only
# HH:MM missed most of them, so bubble boundaries were missed with them.
_TIME_CORE = r"\d{1,2}\s*[:.,]{0,2}\s*\d{2}\s*(?:[ap]\s*\.?\s*m\.?)?"
_TIMESTAMP = re.compile(rf"(?:^|\s){_TIME_CORE}(?:\s|$)", re.IGNORECASE)

# Positional rule: a short mostly-numeric token at the very end of a line, with
# up to two stray letters after it (OCR reads the delivery ticks as "W", "A",
# "WM", "/"). Position carries the meaning — WhatsApp puts the clock at the end
# of the bubble — so this does not depend on the digits parsing as a real time.
_TRAILING_TIMESTAMP = re.compile(
    # (?:^|\s) rather than \s+ : WhatsApp often puts the clock on a line of its
    # own, and OCR reads it as "1746 WM" or "17:51 A". Requiring whitespace
    # before the digits meant those lines closed nothing, so the message above
    # and the message below were joined into one.
    r"(?:^|\s)\d[\d:.,]{2,6}\s*[a-zA-Z/\\|]{0,2}\s*[\W_]*$",
)

# ...but a number at the end of a line is often money in this domain
# ("Total DEPO 1900", "Booking 500"). When the line talks about money, the
# trailing number is not treated as a clock.
_MONEY_CONTEXT = re.compile(
    r"\b(?:rm|ringgit|depo|deposit|booking|baki|total|harga|sewa|rental|"
    r"bayar|utiliti|utility)\b",
    re.IGNORECASE,
)

# WhatsApp chrome and OCR's rendering of icons and status text.
_UI_WORDS = re.compile(
    r"\b(?:mesej|message|dalam\s+talian|online|typing|menaip|diedit|edited|"
    r"dimajukan|forwarded|unread\s+messages?|photos?|gambar|video|"
    r"voice\s+message|tap\s+to\s+load|klik\s+untuk|delivered|whatsapp|"
    r"national\s+qr)\b",
    re.IGNORECASE,
)

# "Anda" / "You" alone on a line is the header of a quoted reply, not a message.
_QUOTE_HEADER = re.compile(r"^\s*(?:anda|you|awak)\s*[:.]?\s*$", re.IGNORECASE)

# The status bar OCR reads off the top of every screenshot: a clock, then signal
# and battery glyphs as short nonsense tokens.
_STATUS_BAR = re.compile(
    r"^\s*\d{1,2}[:.]\d{2}\s+(?:[A-Za-z0-9%€£]{1,6}\s*){1,5}$",
)

_SENTENCE_END = (".", "!", "?", ":", "…")


def _letters(text: str) -> int:
    return sum(1 for character in text if character.isalpha())


def _has_real_word(text: str) -> bool:
    """At least one token of three or more letters.

    OCR noise is short fragments — "a fd @", "45. ng + (2 g", "v fl i + (2 g".
    Anything carrying meaning has a proper word in it.
    """
    return any(len(token) >= 3 for token in re.findall(r"[^\W\d_]+", text))


def _is_noise(line: str) -> bool:
    """True when the line is phone furniture rather than conversation."""
    stripped = line.strip()
    if not stripped or not _has_real_word(stripped):
        return True

    # "Anda" / "You" heads a quoted reply; the status bar heads every page.
    if _QUOTE_HEADER.match(stripped) or _STATUS_BAR.match(stripped):
        return True

    # Mostly punctuation, which is what OCR makes of icon rows.
    non_alnum = sum(
        1 for character in stripped
        if not character.isalnum() and not character.isspace()
    )
    if non_alnum > len(stripped) * 0.4:
        return True

    # What survives once timestamps and UI words are removed.
    residue = _UI_WORDS.sub(" ", _TIMESTAMP.sub(" ", f" {stripped} "))
    if not _has_real_word(residue):
        return True

    # Mostly status furniture, e.g. "€ es dalam talian o tak a .".
    return _letters(residue) < _letters(stripped) * 0.5


def _strip_trailing_timestamp(line: str) -> str:
    return _TRAILING_TIMESTAMP.sub("", line).strip(" .-|·_")


def _ends_with_timestamp(line: str) -> bool:
    """Does this line close a bubble?

    A trailing number only counts as the clock when the line is not talking
    about money: "Total DEPO 1900" ends a sentence about a deposit, not a
    message at 19:00.
    """
    stripped = line.strip()
    if not _TRAILING_TIMESTAMP.search(stripped):
        return False
    if _MONEY_CONTEXT.search(stripped):
        # An explicit HH:MM still wins over the money heuristic.
        return bool(
            re.search(
                r"\d{1,2}[:.]\d{2}\s*(?:[ap]\.?m\.?)?\s*[a-zA-Z/\|]{0,2}\s*[\W_]*$",
                stripped,
                re.IGNORECASE,
            )
        )
    return True


def _by_speaker_label(lines: list[str]) -> list[str]:
    messages: list[str] = []
    for line in lines:
        if _SPEAKER.match(line):
            messages.append(line)
        elif messages and not _is_noise(line):
            messages[-1] = f"{messages[-1]} {line}".strip()
    return messages


def _by_timestamp(lines: list[str]) -> list[str]:
    """Group lines into bubbles, each closed by its trailing timestamp."""
    messages: list[str] = []
    buffer: list[str] = []
    for line in lines:
        if _is_noise(line):
            # Furniture can still close a bubble if it carries the clock.
            if _ends_with_timestamp(line) and buffer:
                messages.append(" ".join(buffer))
                buffer = []
            continue
        buffer.append(line)
        if _ends_with_timestamp(line):
            messages.append(" ".join(buffer))
            buffer = []
    if buffer:
        messages.append(" ".join(buffer))
    return messages


def _by_line(lines: list[str]) -> list[str]:
    """Plain text: one message per line.

    Nothing is merged here. A line break in typed or pasted text is the author's
    own message boundary, so joining lines would undercount. Visual wrapping is
    an OCR artefact and is handled by the timestamp path above, which has a real
    end-of-bubble signal to work with.
    """
    return [line for line in lines if not _is_noise(line)]


def _fingerprint(message: str) -> str:
    """Comparison key: letters and digits only, lowercased."""
    return re.sub(r"[^a-z0-9]+", "", message.lower())


def _deduplicate(messages: list[str]) -> list[str]:
    """Drop repeats of text that has already appeared.

    Two things in real screenshots produce the same artefact. A **quoted reply**
    renders the message being replied to above the reply itself, so OCR reads it
    twice. And **page seams** overlap: consecutive scrolling captures share a
    message or two, so stitching repeats them.

    Both are the same conversation content appearing twice, and a person reading
    the chat counts it once. Matching on content handles both without needing to
    know where the pages were joined or how WhatsApp draws a quote.

    Short messages are exempt. "ok", "boleh" and "yes" are genuinely said more
    than once in a conversation, and collapsing them would undercount.
    """
    MIN_LENGTH_TO_DEDUPE = 25

    seen: list[tuple[str, int]] = []   # (fingerprint, word count)
    kept: list[str] = []

    for message in messages:
        words = message.split()

        # A quoted reply runs straight into the reply itself with no separator,
        # so the repeat is a *prefix* rather than the whole message. Trim it and
        # keep what the person actually wrote.
        for fingerprint, length in seen:
            if length >= len(words):
                continue
            prefix = _fingerprint(" ".join(words[:length]))
            if prefix == fingerprint:
                words = words[length:]
                break

        trimmed = " ".join(words)
        if not _has_real_word(trimmed):
            continue

        key = _fingerprint(trimmed)
        if len(key) >= MIN_LENGTH_TO_DEDUPE:
            if any(key == fingerprint for fingerprint, _ in seen):
                continue
            seen.append((key, len(words)))
        kept.append(trimmed)

    return kept


def split_messages(text: str) -> list[str]:
    """The conversation as a list of messages, furniture removed."""
    if not text:
        return []

    lines = [line.strip() for line in text.splitlines()]
    lines = [line for line in lines if line]
    if not lines:
        return []

    # One label is enough: a transcript either uses them throughout or not at
    # all, so a single "Owner:" means the unlabelled lines under it are that
    # message wrapping, not separate bubbles.
    if any(_SPEAKER.match(line) for line in lines):
        messages = _by_speaker_label(lines)
    elif sum(1 for line in lines if _ends_with_timestamp(line)) >= 2:
        messages = _by_timestamp(lines)
    else:
        messages = _by_line(lines)

    cleaned = [_strip_trailing_timestamp(message) for message in messages]
    return _deduplicate([m for m in cleaned if _has_real_word(m)])


def count_messages(text: str) -> int:
    """How many messages of conversation are visible."""
    return len(split_messages(text))
