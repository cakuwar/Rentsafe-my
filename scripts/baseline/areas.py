"""Area resolution on top of scripts/scrapers/config.py's canonical list."""
import re

from scripts.scrapers import config
from scripts.scrapers.normalize import normalize_area

_IPROPERTY_DISTRICT = re.compile(r"iproperty\.com\.my/property/([^/]+)/")


def resolve(raw, state=None):
    """Canonical area for `raw`, or None when it does not map confidently."""
    area, needs_review = normalize_area(raw if isinstance(raw, str) else "", state)
    return None if needs_review else area


def refine_scraped_area(title, url, area, state):
    """The most specific canonical area a scraped listing supports.

    Portals file sub-areas under a district ("Mossaz @ Empire City, Damansara
    Perdana" under "Damansara"; "Skyline KL, Pudu, KL City Centre" under
    "KL City Centre"). The title's locality segments and iProperty's URL slug
    name the sub-area; a candidate wins over the district it belongs to
    (config.PARENT_AREAS). The building name is trusted only to refine within
    the chosen district: "Pavilion Damansara Heights" under "Damansara" is
    Damansara Heights, but "Sunway Avila Residences" in Wangsa Maju is not
    Bandar Sunway.
    """
    district = resolve(area, state)
    segments = [s.strip() for s in (title or "").split(",") if s.strip()]
    building, localities = (segments[0], segments[1:]) if segments else ("", [])

    candidates = [resolve(seg, state) for seg in localities]
    slug = _IPROPERTY_DISTRICT.search(url or "")
    if slug:
        candidates.append(resolve(slug.group(1).replace("-", " "), state))
    candidates = [c for c in candidates if c]
    if district:
        candidates.append(district)

    for candidate in candidates:
        if config.PARENT_AREAS.get(candidate) in candidates:
            return candidate
    chosen = district or (candidates[-1] if candidates else None)

    named = resolve(building, state)
    if named and chosen and config.PARENT_AREAS.get(named) == chosen:
        return named
    return chosen
