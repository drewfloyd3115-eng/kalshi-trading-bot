"""Safe team normalization for coverage diagnostics; no fuzzy automatic trades."""
import re

ALIASES = {
    "lsu": "louisiana state", "usc": "southern california",
    "uab": "alabama birmingham", "unlv": "nevada las vegas",
    "utep": "texas el paso", "utsa": "texas san antonio",
    "byu": "brigham young", "smu": "southern methodist",
    "tcu": "texas christian", "ucf": "central florida",
    "uconn": "connecticut", "ole miss": "mississippi",
    "pitt": "pittsburgh", "unc": "north carolina",
    "penn st": "penn state", "jacksonville st": "jacksonville state",
    "florida international": "florida international", "fiu": "florida international",
    "hawai i": "hawaii", "hawaii": "hawaii",
    "boise st": "boise state", "fresno st": "fresno state",
    "middle tennessee st": "middle tennessee",
    "colorado st": "colorado state", "texas st": "texas state",
}
MASCOT_SUFFIXES = (
    "rainbow warriors", "sun devils", "broncos", "bulldogs", "dukes",
    "eagles", "tigers", "wildcats", "ragin cajuns", "chanticleers",
    "thundering herd", "blazers", "aztecs", "beavers", "trojans",
    "nittany lions", "golden gophers", "boilermakers", "bison",
    "rebels", "wolf pack", "miners", "orange", "cavaliers",
    "crimson tide", "fighting irish", "golden flashes", "redhawks",
    "golden eagles", "mountaineers", "hurricanes", "seminoles",
    "spartans", "buckeyes", "wolverines", "cougars", "cardinals",
    "knights", "owls", "aggies", "huskies", "panthers", "falcons",
    "longhorns", "sooners", "volunteers", "commodores", "gators",
    "pirates", "yellow jackets", "tar heels", "wolfpack",
    "blue devils", "cyclones", "mustangs", "rockets", "rams",
    "raiders", "bears", "ducks", "lions", "hawks", "red wolves",
    "warhawks", "green wave", "mean green", "red raiders", "gamecocks", "blue hens", "bobcats", "utes", "jayhawks",
)
def normalized(name):
    value = re.sub(r"[^a-z0-9 ]+", " ", str(name or "").lower()).strip()
    value = re.sub(r" +", " ", value)
    for suffix in sorted(MASCOT_SUFFIXES, key=len, reverse=True):
        if value.endswith(" " + suffix):
            value = value[:-(len(suffix)+1)]
            break
    return ALIASES.get(value, value)

def contains_team(text, team):
    normalized_text = re.sub(r"[^a-z0-9 ]+", " ", str(text or "").lower())
    normalized_text = " " + re.sub(r" +", " ", normalized_text).strip() + " "
    key = normalized(team)
    return bool(key) and (" " + key + " ") in normalized_text
