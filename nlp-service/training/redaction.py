"""Strip personal data from text derived from the real screenshots.

Names and addresses are read from data/samples/redact.txt, which is gitignored
with the screenshots themselves. An earlier version hardcoded the names in the regexes
that removed them — which leaked them into source code just the same.

Phone, IC and account numbers are removed by pattern, so they need no list:
nine or more digits joined by at most one space or hyphen at a time. That
catches "+60 1x-xxx xxxx", "yymmdd-xx-xxxx" and bank account numbers, but not a
date range such as "10 Aug 2026 - 31 Aug 2026" — an earlier, looser pattern
redacted that as a phone number.
"""
import os
import re

HERE = os.path.dirname(os.path.abspath(__file__))
LIST = os.path.join(HERE, "..", "..", "data", "samples", "redact.txt")

_PHONE = re.compile(r"\+?\d(?:[\s-]?\d){8,}")


def _entries() -> list[tuple[str, str]]:
    """(text, replacement) pairs. A line may start with a tag such as
    "[address]" to replace with that instead of "[name]"."""
    if not os.path.exists(LIST):
        return []
    entries = []
    with open(LIST, encoding="utf-8") as handle:
        for line in handle:
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            tag = "[name]"
            match = re.match(r"(\[[\w-]+\])\s+(.+)", line)
            if match:
                tag, line = match.groups()
            entries.append((line, tag))
    # Longest first, so a full name is removed before its first name alone.
    return sorted(entries, key=lambda entry: len(entry[0]), reverse=True)


def names() -> list[str]:
    return [text for text, _ in _entries()]


def _pattern(name: str) -> str:
    # No word boundaries: OCR glues words together ("En<name>RumahSe..."), and
    # a boundary would let the name through.
    return r"\s*".join(map(re.escape, name.split()))


def redact(text: str) -> str:
    for entry, tag in _entries():
        text = re.sub(_pattern(entry), tag, text, flags=re.IGNORECASE)
    return _PHONE.sub("[phone]", text)


def leaks(text: str) -> list[str]:
    """Listed names, and any phone-like number, still present in `text`."""
    found = [n for n in names() if re.search(_pattern(n), text, re.IGNORECASE)]
    return found + ["[phone-like number]"] * bool(_PHONE.search(text))


def redact_tree(value):
    """redact() every string inside a JSON-like structure, for eval reports."""
    if isinstance(value, str):
        return redact(value)
    if isinstance(value, dict):
        return {key: redact_tree(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [redact_tree(item) for item in value]
    return value
