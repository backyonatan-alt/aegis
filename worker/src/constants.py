"""Shared constants for the Aegis data worker."""

R2_KEY = "data.json"

PIZZA_PLACES = [
    {
        "name": "Domino's Pizza",
        "place_id": "ChIJN1t_tDeuEmsRUsoyG83frY4",
        "address": "Pentagon City",
    },
    {
        "name": "Papa John's",
        "place_id": "ChIJP3Sa8ziYEmsRUKgyFmh9AQM",
        "address": "Near Pentagon",
    },
    {
        "name": "Pizza Hut",
        "place_id": "ChIJrTLr-GyuEmsRBfy61i59si0",
        "address": "Pentagon Area",
    },
]

ALERT_KEYWORDS = [
    "strike",
    "attack",
    "military",
    "bomb",
    "missile",
    "war",
    "imminent",
    "troops",
    "forces",
]

IRAN_KEYWORDS = ["iran", "tehran", "persian gulf", "strait of hormuz"]

STRIKE_KEYWORDS = ["strike", "attack", "bomb", "military action"]

NEGATIVE_KEYWORDS = [" not ", "won't", "will not", "doesn't", "does not"]

TANKER_PREFIXES = [
    # Original fuel/gas station themed
    "IRON",
    "SHELL",
    "TEXAN",
    "ETHYL",
    "PEARL",
    "ARCO",
    "ESSO",
    "MOBIL",
    "GULF",
    "TOPAZ",
    "PACK",
    "DOOM",
    "TREK",
    "REACH",
    # Additional fuel-themed callsigns
    "EXXON",
    "TEXACO",
    "OILER",
    "OPEC",
    "PETRO",
    # KC-10 unit callsigns
    "TOGA",
    "DUCE",
    "FORCE",
    "GUCCI",
    "XTNDR",
    "SPUR",
    "TEAM",
    "QUID",
    # KC-135 unit callsigns
    "BOLT",
    "BROKE",
    "BROOM",
    "BOBBY",
    "BOBBIE",
    "BODE",
    "CONIC",
    "MAINE",
    "BRIG",
    "ARTLY",
    "BANKER",
    "BRUSH",
    # KC-46 unit callsigns
    "ARRIS",
    # Coronet/trans-Atlantic mission callsigns
    "GOLD",
    "BLUE",
    "CLEAN",
    "VINYL",
]

USAF_HEX_START = int("AE0000", 16)
USAF_HEX_END = int("AE7FFF", 16)

RSS_FEEDS = [
    "https://feeds.bbci.co.uk/news/world/middle_east/rss.xml",
    "https://www.aljazeera.com/xml/rss/all.xml",
]

MONTHS = [
    "january", "february", "march", "april", "may", "june",
    "july", "august", "september", "october", "november", "december",
]

# Cloudflare Radar API configuration
CLOUDFLARE_RADAR_BASE_URL = "https://api.cloudflare.com/client/v4/radar"
CLOUDFLARE_RADAR_LOCATION = "IR"  # Iran
