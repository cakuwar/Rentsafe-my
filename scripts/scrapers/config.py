"""Shared configuration for the RentSafe MY price-baseline scrapers.

Kept deliberately small and declarative so mudah.py / iproperty.py /
propertyguru.py and normalize.py all agree on the same canonical lists.
"""
import os

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
DATA_RAW_BASELINE = os.path.join(ROOT, "data", "raw", "baseline")
DATA_PROCESSED = os.path.join(ROOT, "data", "processed")
DATABASE_SEEDS = os.path.join(ROOT, "database", "seeds")
CACHE_DIR = os.path.join(DATA_RAW_BASELINE, "_cache")

# Canonical KL / Selangor areas -> state. Must match
# backend/src/services/metadata.service.js once the price module mirrors it.
#
# DECISION (author, 2026-10-15) — sub-areas are kept separate wherever a source
# distinguishes them, instead of collapsing onto a district. Measured on the
# Aug 2026 scrape: Pavilion Damansara Heights (RM5-8k) was 13 of 18
# "Damansara 1BR" rows, so legitimate Damansara Perdana listings at RM1,400
# read as 76% below market. The old 18-area list folded Damansara Heights /
# Perdana / Kota Damansara into "Damansara", Bandar Sunway / USJ into "Subang"
# and Bangsar South into "Bangsar"; each is its own area now. "Subang" is
# renamed "Subang Jaya".
#
# A name used in both states (Mudah lists "Kuala Lumpur - Cheras" and
# "Selangor - Cheras") is split with a state suffix: in the Kaggle data Cheras
# 3BR condos are RM1,500 (KL) vs RM1,300 (Selangor) and apartments RM1,100 vs
# RM899. The plain name resolves only when the state is known (DUAL_STATE_AREAS).
CANONICAL_AREAS = {
    # Kuala Lumpur
    "Ampang (KL)": "Kuala Lumpur", "Ampang Hilir": "Kuala Lumpur",
    "Bandar Damai Perdana": "Kuala Lumpur", "Bandar Menjalara": "Kuala Lumpur",
    "Bandar Tasik Selatan": "Kuala Lumpur", "Bangsar": "Kuala Lumpur",
    "Bangsar South": "Kuala Lumpur", "Brickfields": "Kuala Lumpur",
    "Bukit Bintang": "Kuala Lumpur", "Bukit Jalil": "Kuala Lumpur",
    "Bukit Tunku": "Kuala Lumpur", "Chan Sow Lin": "Kuala Lumpur",
    "Cheras (KL)": "Kuala Lumpur", "Damansara": "Kuala Lumpur",
    "Damansara Heights": "Kuala Lumpur", "Desa Pandan": "Kuala Lumpur",
    "Desa ParkCity": "Kuala Lumpur", "Desa Petaling": "Kuala Lumpur",
    "Dutamas": "Kuala Lumpur", "Gombak (KL)": "Kuala Lumpur",
    "Jalan Ipoh": "Kuala Lumpur", "Jalan Kuching": "Kuala Lumpur",
    "Jalan Sultan Ismail": "Kuala Lumpur", "Jinjang": "Kuala Lumpur",
    "Kepong": "Kuala Lumpur", "Keramat": "Kuala Lumpur",
    "KL City Centre": "Kuala Lumpur", "KL Eco City": "Kuala Lumpur",
    "KL Sentral": "Kuala Lumpur", "KLCC": "Kuala Lumpur",
    "Kuchai Lama": "Kuala Lumpur", "Mid Valley City": "Kuala Lumpur",
    "Mont Kiara": "Kuala Lumpur", "Old Klang Road": "Kuala Lumpur",
    "OUG": "Kuala Lumpur", "Pandan Indah": "Kuala Lumpur",
    "Pandan Jaya": "Kuala Lumpur", "Pandan Perdana": "Kuala Lumpur",
    "Pantai": "Kuala Lumpur", "Puchong (KL)": "Kuala Lumpur",
    "Pudu": "Kuala Lumpur", "Salak Selatan": "Kuala Lumpur",
    "Segambut": "Kuala Lumpur", "Sentul": "Kuala Lumpur",
    "Seputeh": "Kuala Lumpur", "Serdang (KL)": "Kuala Lumpur",
    "Setapak": "Kuala Lumpur", "Setiawangsa": "Kuala Lumpur",
    "Sri Damansara": "Kuala Lumpur", "Sri Hartamas": "Kuala Lumpur",
    "Sri Petaling": "Kuala Lumpur", "Sungai Besi": "Kuala Lumpur",
    "Sungai Penchala": "Kuala Lumpur", "Taman Desa": "Kuala Lumpur",
    "Taman Melawati": "Kuala Lumpur", "Taman Tun Dr Ismail": "Kuala Lumpur",
    "Titiwangsa": "Kuala Lumpur", "Wangsa Maju": "Kuala Lumpur",
    # Selangor
    "Alam Impian": "Selangor", "Ampang (Selangor)": "Selangor",
    "Ara Damansara": "Selangor", "Balakong": "Selangor",
    "Bandar Bukit Raja": "Selangor", "Bandar Bukit Tinggi": "Selangor",
    "Bandar Botanic": "Selangor", "Bandar Kinrara": "Selangor",
    "Bandar Mahkota Cheras": "Selangor", "Bandar Saujana Putra": "Selangor",
    "Bandar Sri Damansara": "Selangor", "Bandar Sungai Long": "Selangor",
    "Bandar Sunway": "Selangor", "Bandar Utama": "Selangor",
    "Bangi": "Selangor", "Banting": "Selangor", "Batu Caves": "Selangor",
    "Beranang": "Selangor", "Bukit Beruntung": "Selangor",
    "Bukit Jelutong": "Selangor", "Bukit Subang": "Selangor",
    "Cheras (Selangor)": "Selangor", "Cyberjaya": "Selangor",
    "Damansara Damai": "Selangor", "Damansara Jaya": "Selangor",
    "Damansara Perdana": "Selangor", "Damansara Utama": "Selangor",
    "Dengkil": "Selangor", "Glenmarie": "Selangor",
    "Gombak (Selangor)": "Selangor", "Hulu Langat": "Selangor",
    "I-City": "Selangor", "Jenjarom": "Selangor", "Kajang": "Selangor",
    "Kapar": "Selangor", "Kelana Jaya": "Selangor", "Klang": "Selangor",
    "Kota Damansara": "Selangor", "Kota Kemuning": "Selangor",
    "Kuala Langat": "Selangor", "Kuala Selangor": "Selangor",
    "Mutiara Damansara": "Selangor", "Petaling Jaya": "Selangor",
    "Port Klang": "Selangor", "Puchong (Selangor)": "Selangor",
    "Puchong South": "Selangor", "Pulau Indah": "Selangor",
    "Puncak Alam": "Selangor", "Puncak Jalil": "Selangor",
    "Putra Heights": "Selangor", "Rawang": "Selangor",
    "Salak Tinggi": "Selangor", "Saujana Utama": "Selangor",
    "Selayang": "Selangor", "Semenyih": "Selangor", "Sepang": "Selangor",
    "Serdang (Selangor)": "Selangor", "Serendah": "Selangor",
    "Seri Kembangan": "Selangor", "Setia Alam": "Selangor",
    "Shah Alam": "Selangor", "Subang Bestari": "Selangor",
    "Subang Jaya": "Selangor", "Sungai Buloh": "Selangor",
    "Telok Panglima Garang": "Selangor", "Ulu Klang": "Selangor",
    "USJ": "Selangor",
}

KL_SEL_AREAS = list(CANONICAL_AREAS)

# Plain names that exist in both states; resolved by the listing's state.
DUAL_STATE_AREAS = {
    name.lower(): {"Kuala Lumpur": f"{name} (KL)", "Selangor": f"{name} (Selangor)"}
    for name in ("Cheras", "Ampang", "Gombak", "Puchong", "Serdang")
}

# Other spellings -> canonical name. Left-hand side is matched
# case-insensitively, as a whole word; None means "too generic to count, keep
# looking". Every canonical name matches itself and needs no entry here.
AREA_ALIASES = {
    "kl": None,
    "kuala lumpur": None,
    "selangor": None,
    "others": None,
    "pj": "Petaling Jaya",
    "pjs": "Petaling Jaya",
    "ss2": "Petaling Jaya",
    "subang": "Subang Jaya",
    "sunway": "Bandar Sunway",
    "usj subang jaya": "USJ",
    "ampang jaya": "Ampang (Selangor)",
    "kl city": "KL City Centre",
    "city centre": "KL City Centre",
    "jalan klang lama": "Old Klang Road",
    "solaris dutamas": "Dutamas",
    "salak south": "Salak Selatan",
    "ttdi": "Taman Tun Dr Ismail",
    "bandar baru bangi": "Bangi",
}

# Sub-area -> the district a listing portal files it under. Used only to
# refine a scraped row from its title ("Mossaz @ Empire City, Damansara
# Perdana" filed under "Damansara"); never to merge areas.
PARENT_AREAS = {
    **{sub: "Damansara" for sub in (
        "Damansara Heights", "Damansara Perdana", "Damansara Damai",
        "Damansara Jaya", "Damansara Utama", "Kota Damansara", "Ara Damansara",
        "Mutiara Damansara", "Bandar Sri Damansara", "Sri Damansara")},
    **{sub: "Subang Jaya" for sub in ("USJ", "Bandar Sunway", "Bukit Subang")},
    **{sub: "KL City Centre" for sub in (
        "KLCC", "Bukit Bintang", "Pudu", "Jalan Sultan Ismail")},
    **{sub: "Shah Alam" for sub in (
        "Setia Alam", "Kota Kemuning", "Alam Impian", "Bukit Jelutong",
        "Puncak Alam", "I-City", "Subang Bestari")},
    "Bangsar South": "Bangsar",
    "Kelana Jaya": "Petaling Jaya",
    "Puchong South": "Puchong (Selangor)",
    "Bandar Kinrara": "Puchong (Selangor)",
}

# Room rentals: one stratum per room type. A form or source saying "single"
# or "middle" maps to "common" (normalize.normalize_room_type) — the
# PropertyGuru-group portals only label rooms "Master Room" / "Common Room",
# so single and middle cannot be told apart in the data.
ROOM_TYPES = ("master", "common")

# States we accept; anything else gets dropped in normalize.py.
VALID_STATES = {"Kuala Lumpur", "Selangor"}

# DECISION (author, 2026-10-15) — "flat" is its own type, not an apartment.
# In the Kaggle data flats rent a median 23% below apartments in the same area
# and bedroom count (31 strata); pooled, every legitimate flat would read as
# under-priced. Flat / PPR / rumah pangsa -> flat; pangsapuri stays apartment.
PROPERTY_TYPES = ("room", "studio", "apartment", "flat", "condo", "landed")

# Sanity bounds for monthly rent in MYR. Anything outside is dropped.
MIN_PRICE_MYR = 150
MAX_PRICE_MYR = 20000

MIN_SAMPLE_SIZE_FOR_BASELINE = 3

# --- Politeness / etiquette -------------------------------------------------
REQUEST_DELAY_RANGE_SECONDS = (3, 6)
MAX_RETRIES = 3
RETRY_BACKOFF_SECONDS = 2  # exponential: 2, 4, 8...
REQUEST_TIMEOUT_SECONDS = 20

# Contact note is included so any site operator reviewing access logs can see
# this is a rate-limited academic research crawl and reach out if needed.
CONTACT_NOTE = "academic research contact: afiq04aiman10@gmail.com"

USER_AGENTS = [
    f"Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    f"(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36 "
    f"RentSafeMY-ResearchBot/0.1 ({CONTACT_NOTE})",
    f"Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 "
    f"(KHTML, like Gecko) Version/17.0 Safari/605.1.15 "
    f"RentSafeMY-ResearchBot/0.1 ({CONTACT_NOTE})",
    f"Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
    f"(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36 "
    f"RentSafeMY-ResearchBot/0.1 ({CONTACT_NOTE})",
]

PLAYWRIGHT_EXECUTABLE_PATH = "/opt/pw-browsers/chromium"

SITE_BASE_URLS = {
    "mudah": "https://www.mudah.my",
    "iproperty": "https://www.iproperty.com.my",
    "propertyguru": "https://www.propertyguru.com.my",
}

os.makedirs(CACHE_DIR, exist_ok=True)
os.makedirs(DATA_PROCESSED, exist_ok=True)
os.makedirs(DATABASE_SEEDS, exist_ok=True)
