"""Pure parsing of PropertyGuru-group search pages (iProperty, PropertyGuru).

Both sites embed the listing cards of a search-results page as JSON in
`<script id="__NEXT_DATA__">`. Kept free of network code (no requests /
tenacity) so the baseline pipeline can re-read the page cache in
data/raw/baseline/_cache/ without being able to fetch anything.
"""
import json
import re
from datetime import datetime, timezone

NEXT_DATA_RE = re.compile(r'<script id="__NEXT_DATA__"[^>]*>(.*?)</script>', re.S)


def extract_next_data(html):
    """The page's __NEXT_DATA__ JSON, or None."""
    m = NEXT_DATA_RE.search(html or "")
    if not m:
        return None
    try:
        return json.loads(m.group(1))
    except json.JSONDecodeError:
        return None


def listings_from_next_data(data):
    """The listingData dicts of a search page, or [] if the shape is unexpected."""
    try:
        entries = data["props"]["pageProps"]["pageData"]["data"]["listingsData"]
    except (KeyError, TypeError):
        return []
    return [entry.get("listingData") or {} for entry in entries or []]


def feature_text(listing_features, automation_id):
    """Text of the card feature with this dataAutomationId, or None."""
    for item in listing_features or []:
        candidates = item if isinstance(item, list) else [item]
        for c in candidates:
            if isinstance(c, dict) and c.get("dataAutomationId") == automation_id:
                return c.get("text")
    return None


def row_from_listing_data(ld, base_url):
    """One raw scraped row from a listing card (normalize.normalize_row cleans it)."""
    raw_url = ld.get("url") or ""
    listing_url = raw_url if raw_url.startswith("http") else (base_url + raw_url if raw_url else "")

    price = (ld.get("price") or {}).get("value")
    additional = ld.get("additionalData") or {}
    prop = ld.get("property") or {}
    features = ld.get("listingFeatures")

    # The numeric `bedrooms` field uses -1 as a sentinel for studios
    # (rather than 0), so it can't be trusted on its own — the card's
    # bed-icon feature text ("Studio" vs "2") is the reliable source.
    bed_text = feature_text(features, "listing-card-v2-bedrooms")
    is_studio = bool(bed_text) and bed_text.strip().lower() == "studio"
    bedrooms = ld.get("bedrooms")
    if is_studio:
        bedrooms = 0
    elif isinstance(bedrooms, (int, float)) and bedrooms < 0:
        bedrooms = None

    return {
        "title": ld.get("localizedTitle"),
        "price_myr": price,
        "area": additional.get("districtText") or ld.get("shortAddress"),
        "state": additional.get("regionText"),
        "bedrooms": bedrooms,
        "is_studio": is_studio,
        "bathrooms": ld.get("bathrooms"),
        "property_type": "studio" if is_studio else prop.get("subTypeText"),
        "property_subtype": prop.get("subTypeText"),
        "size_sqft": ld.get("floorArea"),
        "furnishing": feature_text(features, "listing-card-v2-furnish"),
        # Room rentals carry "Master Room" / "Common Room" and "2 pax" here,
        # with bedrooms 0 and no floor area. Not reading these is how 18 rooms
        # entered the whole-unit baseline as 0-bedroom condos.
        "room_type": feature_text(features, "listing-card-v2-room-type"),
        "tenants": feature_text(features, "listing-card-v2-tenants"),
        "portal_listing_id": str(ld["id"]) if ld.get("id") is not None else None,
        "listing_url": listing_url,
        "scraped_at": datetime.now(timezone.utc).isoformat(),
    }
