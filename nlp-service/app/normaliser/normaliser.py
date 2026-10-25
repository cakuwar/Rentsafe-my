"""Shortform normalisation pipeline.

normalise(text) should:
  1. lowercase + whitespace cleanup
  2. expand ditto-mark reduplication (e.g. tiba""tiba -> tiba-tiba)
  3. token-level expansion, stripping/reattaching surrounding punctuation
     (e.g. "xleh?" -> "tak boleh?") so real chat punctuation doesn't block
     a match, in priority order:
     a. SHORTFORM_DICT exact match (curated Manglish -> standard)
     b. digit leetspeak whole-token match (e.g. "gr8" -> "great")
     c. digit prefix rule (e.g. "xnak" -> "tak nak")
     d. digit reduplication suffix (e.g. "jalan2" -> "jalan-jalan")
Returns the normalised string, ready for Layer 1 + Layer 2.
"""
import re
from app.normaliser.dictionary import SHORTFORM_DICT, DIGIT_RULES

# Bases that are never Malay reduplication even when they end in a
# reduplication-suffix digit — e.g. "rm2" is a currency amount, not "rm-rm".
# Rental listings are full of these, so the suffix rule must not touch them.
_NON_REDUPLICATING_BASES = {"rm", "usd", "sgd", "no"}

# Splits a token into (leading punctuation, word/number core, trailing
# punctuation) so real chat punctuation ("xleh?", "(nego)", "call skrg!!")
# doesn't block a dictionary/digit-rule match. A token with punctuation
# embedded in the middle (a hyphenated phone number, "can't") won't match
# and is left untouched rather than mangled.
_TOKEN_PATTERN = re.compile(r"^(\W*)(\w+)(\W*)$")

_DITTO_PATTERN = (
    re.compile(r"(\w+)(?:" + "|".join(re.escape(m) for m in DIGIT_RULES.ditto_markers) + r")(\w*)")
    if DIGIT_RULES.ditto_markers
    else None
)

_PREFIX_PATTERN = (
    re.compile(r"^(" + "|".join(re.escape(p) for p in DIGIT_RULES.prefixes) + r")([a-z]+)$")
    if DIGIT_RULES.prefixes
    else None
)

_REDUP_SUFFIX_PATTERN = (
    re.compile(r"^([a-z]+)(?:" + "|".join(re.escape(s) for s in DIGIT_RULES.reduplication_suffixes) + r")$")
    if DIGIT_RULES.reduplication_suffixes
    else None
)


def _expand_ditto(text: str) -> str:
    """Expand ditto-mark reduplication, e.g. 'tiba""tiba' -> 'tiba-tiba'."""
    if _DITTO_PATTERN is None:
        return text

    def _replace(match: re.Match) -> str:
        base, trailing = match.group(1), match.group(2)
        if trailing and trailing != base:
            return f"{base}-{base} {trailing}"
        return f"{base}-{base}"

    return _DITTO_PATTERN.sub(_replace, text)


def _expand_word(word: str) -> str:
    """Expand a bare word/number core (no surrounding punctuation)."""
    if word in SHORTFORM_DICT:
        return SHORTFORM_DICT[word]

    if word in DIGIT_RULES.leet_tokens:
        return DIGIT_RULES.leet_tokens[word]

    if _PREFIX_PATTERN is not None:
        match = _PREFIX_PATTERN.match(word)
        if match:
            prefix, base = match.group(1), match.group(2)
            return f"{DIGIT_RULES.prefixes[prefix]} {SHORTFORM_DICT.get(base, base)}"

    if _REDUP_SUFFIX_PATTERN is not None:
        match = _REDUP_SUFFIX_PATTERN.match(word)
        if match and match.group(1) not in _NON_REDUPLICATING_BASES:
            base = SHORTFORM_DICT.get(match.group(1), match.group(1))
            return f"{base}-{base}"

    return word


def _expand_token(token: str) -> str:
    """Expand one whitespace-delimited token, preserving its punctuation."""
    match = _TOKEN_PATTERN.match(token)
    if not match:
        return token

    prefix, word, suffix = match.groups()
    return f"{prefix}{_expand_word(word)}{suffix}"


# Links are left exactly as written. A slang dictionary applied inside
# "go.ibilik.com" or "bit.ly/abc" would corrupt the address. Tokens with dots
# inside already escaped expansion by accident (_TOKEN_PATTERN needs a single
# word core); this makes it a rule with tests of its own.
_LINK_TOKEN = re.compile(
    r"^\W*(?:(?:https?://|www\.)\S+|\S+@\S+\.\S+|[\w-]+(?:\.[\w-]+)+(?:/\S*)?)\W*$",
    re.IGNORECASE,
)

# A token right after a link cue is a link even when OCR has mangled it. In a
# real iBilik chat "Go to: go.ibilik.com" was read as "Goto: cm", and "cm" -
# ordinary Malay chat slang for "macam" - was expanded, turning the platform's
# address into a word. The dictionary entry is right in general; the position
# is what says this "cm" is not slang.
_LINK_CUES = {"goto:", "link:", "links:", "url:", "website:", "web:", "site:", "visit:"}


def _is_link(tokens: list[str], index: int) -> bool:
    if _LINK_TOKEN.match(tokens[index]):
        return True
    previous = tokens[index - 1] if index else ""
    return previous in _LINK_CUES or (
        previous == "to:" and index >= 2 and tokens[index - 2] == "go"
    )


def normalise(text: str) -> str:
    text = text.lower()
    text = re.sub(r"\s+", " ", text).strip()
    text = _expand_ditto(text)

    tokens = text.split()
    expanded_tokens = [
        token if _is_link(tokens, index) else _expand_token(token)
        for index, token in enumerate(tokens)
    ]
    text = " ".join(expanded_tokens)

    if not text:
        raise ValueError("normalise() received an empty string.")
    return text
