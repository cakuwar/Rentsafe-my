"""Normalisation helpers shared by every scraper.

Maps free-text area strings onto the canonical KL_SEL_AREAS list (must stay in
sync with backend/src/services/metadata.service.js), infers property_type from
listing text, and applies the price sanity filter.
"""
import re

from . import config

_PROPERTY_TYPE_PATTERNS = (
    (re.compile(r"studio", re.I), "studio"),
    (re.compile(r"condo|condominium|service[d]?\s*resid", re.I), "condo"),
    # Before apartment: "Pangsapuri" contains "pangsa", so flats match whole
    # words only ("rumah pangsa", "PPR", "flat").
    (re.compile(r"\bflats?\b|\bppr\b|\brumah\s+pangsa\b", re.I), "flat"),
    (re.compile(r"apartment|pangsapuri", re.I), "apartment"),
    (re.compile(r"terrace|landed|semi-?d|bungalow|townhouse|villa", re.I), "landed"),
    (re.compile(r"room|bilik|sewa\s*bilik", re.I), "room"),
)

# Sorted longest-first so "Bangsar South" matches before "Bangsar". Each entry
# is matched as a whole word: a bare substring test let "pj" hit inside other
# words. A dict target is a name used in both states, resolved by state.
_AREA_LOOKUP = sorted(
    [(a.lower(), a) for a in config.KL_SEL_AREAS]
    + list(config.DUAL_STATE_AREAS.items())
    + list(config.AREA_ALIASES.items()),
    key=lambda kv: -len(kv[0]),
)
_AREA_PATTERNS = [
    (re.compile(rf"(?<![a-z0-9]){re.escape(alias)}(?![a-z0-9])"), target)
    for alias, target in _AREA_LOOKUP
]


def normalize_area(raw_area, state=None):
    """Map a free-text area/district string to a canonical KL_SEL_AREAS value.

    Returns (canonical_area_or_none, needs_review: bool). needs_review is True
    when we could not confidently map the raw string, so the raw value should
    be kept alongside a flag rather than silently dropped. `state` resolves a
    name used in both states ("Cheras" -> "Cheras (KL)" / "Cheras (Selangor)");
    without it such a name needs review.
    """
    if not raw_area:
        return None, True
    text = raw_area.strip().lower()
    for pattern, target in _AREA_PATTERNS:
        if not pattern.search(text):
            continue
        if target is None:
            continue
        if isinstance(target, dict):
            if state in target:
                return target[state], False
            return raw_area.strip(), True
        return target, False
    return raw_area.strip(), True


def normalize_room_type(raw):
    """"Master Room" -> "master"; common / middle / single / small room -> "common".

    Returns None when the text names no room type — a bare "room" is not
    guessed, since pooling master rooms into "common" would widen it.
    """
    text = (raw or "").strip().lower()
    if not text:
        return None
    if "master" in text:
        return "master"
    if re.search(r"common|middle|medium|single|small", text):
        return "common"
    return None


def normalize_tenants(raw):
    """"2 pax (female)" -> (2, "female"); "1 pax" -> (1, None); "" -> (None, None)."""
    text = (raw or "").strip().lower()
    count = re.search(r"(\d+)\s*pax", text)
    gender = re.search(r"\b(female|male)\b", text)
    return (int(count.group(1)) if count else None, gender.group(1) if gender else None)


def normalize_property_type(*text_fields):
    """Infer property_type from one or more free-text fields (title, listing type, etc)."""
    joined = " ".join(t for t in text_fields if t)
    for pattern, ptype in _PROPERTY_TYPE_PATTERNS:
        if pattern.search(joined):
            return ptype
    return None


def is_price_valid(price_myr):
    if price_myr is None:
        return False
    try:
        price = float(price_myr)
    except (TypeError, ValueError):
        return False
    return config.MIN_PRICE_MYR <= price <= config.MAX_PRICE_MYR


def normalize_bedrooms(raw_bedrooms, property_type=None):
    """Coerce bedroom count to int; studios are 0 bedrooms with is_studio=True."""
    if property_type == "studio":
        return 0, True
    if raw_bedrooms in (None, ""):
        return None, False
    try:
        return int(raw_bedrooms), False
    except (TypeError, ValueError):
        match = re.search(r"\d+", str(raw_bedrooms))
        return (int(match.group()), False) if match else (None, False)


def normalize_row(row):
    """Apply all normalisation steps to a raw scraped row dict in place.

    Returns the row with area/property_type/bedrooms normalised and an
    `area_needs_review` flag added, or None if the row fails the price filter
    or isn't KL/Selangor.
    """
    if not is_price_valid(row.get("price_myr")):
        return None

    state = (row.get("state") or "").strip()
    if state and state not in config.VALID_STATES:
        return None

    area, needs_review = normalize_area(row.get("area"), state or None)
    if area is None:
        return None
    row["area"] = area
    row["area_needs_review"] = needs_review

    # A room rental is a room, whatever the unit it sits in. Before this the
    # card's room type was not read and rooms became "0-bedroom condos".
    room_type = normalize_room_type(row.get("room_type"))
    if room_type:
        row["property_type"] = "room"
        row["room_type"] = room_type
        row["max_tenants"], row["tenant_gender"] = normalize_tenants(row.get("tenants"))
        row["bedrooms"] = None
        row["is_studio"] = False
        return row

    property_type = row.get("property_type")
    if property_type not in config.PROPERTY_TYPES:
        property_type = normalize_property_type(row.get("title"), property_type)
    row["property_type"] = property_type

    bedrooms, is_studio = normalize_bedrooms(row.get("bedrooms"), property_type)
    row["bedrooms"] = bedrooms
    row["is_studio"] = is_studio or bool(row.get("is_studio"))

    return row
