from __future__ import annotations

import re

US_STATE_ABBREVS = frozenset({
    "AL", "AK", "AZ", "AR", "CA", "CO", "CT", "DE", "FL", "GA", "HI", "ID",
    "IL", "IN", "IA", "KS", "KY", "LA", "ME", "MD", "MA", "MI", "MN", "MS",
    "MO", "MT", "NE", "NV", "NH", "NJ", "NM", "NY", "NC", "ND", "OH", "OK",
    "OR", "PA", "RI", "SC", "SD", "TN", "TX", "UT", "VT", "VA", "WA", "WV",
    "WI", "WY", "DC",
})

US_STATE_NAMES = frozenset({
    "alabama", "alaska", "arizona", "arkansas", "california", "colorado",
    "connecticut", "delaware", "florida", "georgia", "hawaii", "idaho",
    "illinois", "indiana", "iowa", "kansas", "kentucky", "louisiana", "maine",
    "maryland", "massachusetts", "michigan", "minnesota", "mississippi",
    "missouri", "montana", "nebraska", "nevada", "new hampshire", "new jersey",
    "new mexico", "new york", "north carolina", "north dakota", "ohio",
    "oklahoma", "oregon", "pennsylvania", "rhode island", "south carolina",
    "south dakota", "tennessee", "texas", "utah", "vermont", "virginia",
    "washington", "west virginia", "wisconsin", "wyoming",
    "district of columbia",
})

# Common non-US country/region tokens that appear in Muse-style location strings.
# A job whose only specific tags are these (with no US-state tag) is treated as
# non-US even if also marked Remote.
NON_US_TOKENS = frozenset({
    "india", "ireland", "germany", "france", "spain", "italy", "netherlands",
    "belgium", "switzerland", "austria", "poland", "portugal", "uk",
    "united kingdom", "great britain", "scotland", "wales", "england",
    "canada", "mexico", "brazil", "argentina", "chile", "colombia",
    "australia", "new zealand", "singapore", "japan", "china", "hong kong",
    "south korea", "philippines", "vietnam", "thailand", "indonesia",
    "malaysia", "south africa", "kenya", "nigeria", "egypt", "israel",
    "uae", "united arab emirates", "saudi arabia", "turkey", "norway",
    "sweden", "finland", "denmark", "czech republic", "romania", "ukraine",
    "greece", "hungary", "slovakia", "bulgaria", "estonia", "lithuania",
    "latvia", "croatia", "slovenia", "serbia",
})

_STATE_SUFFIX_RE = re.compile(r",\s*([A-Z]{2})\b")


def _location_is_us(name: str) -> bool:
    """Return True if a single location string looks like a US-based location."""
    if not name:
        return False
    n = name.strip()
    n_lower = n.lower()
    if "united states" in n_lower or n_lower.endswith(", usa"):
        return True
    # Bare country/state markers (post-comma-split).
    if n.upper() in {"US", "USA"} or n.upper() in US_STATE_ABBREVS:
        return True
    if n_lower in US_STATE_NAMES:
        return True
    for m in _STATE_SUFFIX_RE.finditer(n):
        if m.group(1) in US_STATE_ABBREVS:
            return True
    return False


def _location_is_remote(name: str) -> bool:
    return "remote" in name.lower() or "flexible" in name.lower()


def _location_is_non_us(name: str) -> bool:
    n_lower = name.lower()
    if _location_is_us(name):
        return False
    return any(tok in n_lower for tok in NON_US_TOKENS)


def location_is_us_or_remote(location_str: str) -> bool:
    """Return True if a job's location string indicates US or US-friendly remote.

    Handles The Muse's multi-location strings like
    "Flexible / Remote, Boston, MA" or "Hinganghāt, India, Flexible / Remote".

    Rules:
    - Any US-tagged location (state abbrev, "United States", "USA") → True
    - Remote with no specific non-US country anywhere in the string → True
    - Otherwise → False
    """
    if not location_str:
        return False
    # Split on commas and slashes to inspect each location/segment.
    segments = [s.strip() for s in re.split(r"[,/]", location_str) if s.strip()]

    has_us = any(_location_is_us(seg) for seg in segments)
    if has_us:
        return True

    # Check if remote is mentioned and no foreign country is mentioned.
    full_lower = location_str.lower()
    has_remote = "remote" in full_lower or "flexible" in full_lower
    has_non_us = any(tok in full_lower for tok in NON_US_TOKENS)
    return has_remote and not has_non_us
