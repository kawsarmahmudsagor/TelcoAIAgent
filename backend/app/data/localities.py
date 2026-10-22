"""Sub-areas (sectors, sections, well-known pockets) inside the big Dhaka areas,
and which ones are next to which.

A customer asking for "Mirpur 12" means that sector, not every Mirpur listing
-- and if it's thin, the next best is Mirpur 11 or Pallabi next door, not
whatever Mirpur flat is cheapest. Listings keep the parent area in
`neighborhood` (the public browse filter and its facets depend on that) and
name the sub-area in `address_line`, so a sub-area is matched as: the row is in
the parent area AND its address matches the sub-area's pattern.

Patterns are Postgres regular expressions, matched case-insensitively against
address_line; \\m and \\M are its word boundaries, so "Mirpur 1" never matches
"Mirpur 10". Pure data plus helpers -- no DB access.
"""

import re
from dataclasses import dataclass

_TO_ASCII_DIGITS = str.maketrans("০১২৩৪৫৬৭৮৯", "0123456789")


@dataclass(frozen=True)
class SubArea:
    name: str
    parent: str
    # Postgres regex for address_line; the row must also be in `parent`.
    pattern: str
    # Closest first. May name parent-level areas too ("Banani"), which are
    # searched as plain areas.
    near: tuple[str, ...]
    # For the seed: how the sub-area is written in an address, and how its
    # prices compare to the parent area's.
    address: str
    price_factor: float = 1.0


def _mirpur(n: int, near: tuple[str, ...], price_factor: float = 1.0) -> SubArea:
    return SubArea(
        name=f"Mirpur {n}",
        parent="Mirpur",
        pattern=rf"\mmirpur[\s-]*{n}\M|\msection[\s-]*{n}\M",
        near=near,
        address=f"Section {n}, Mirpur",
        price_factor=price_factor,
    )


def _uttara(n: int, near: tuple[str, ...], price_factor: float = 1.0) -> SubArea:
    return SubArea(
        name=f"Uttara Sector {n}",
        parent="Uttara",
        pattern=rf"\muttara[\s-]*(sector[\s-]*)?{n}\M|\msector[\s-]*{n}\M",
        near=near,
        address=f"Sector {n}, Uttara",
        price_factor=price_factor,
    )


def _named(
    name: str, parent: str, words: str, near: tuple[str, ...], price_factor: float = 1.0,
    address: str | None = None,
) -> SubArea:  # fmt: skip
    return SubArea(
        name=name,
        parent=parent,
        pattern=rf"\m({words})\M",
        near=near,
        address=address or f"{name}, {parent}",
        price_factor=price_factor,
    )


def _dhanmondi_road(n: int, near: tuple[str, ...], price_factor: float = 1.0) -> SubArea:
    # Old road numbers, the ones people still say ("Dhanmondi 27", "32").
    return SubArea(
        name=f"Dhanmondi {n}",
        parent="Dhanmondi",
        pattern=rf"\mdhanmondi[\s-]*{n}a?\M|\mroad[\s-]*{n}a?\M",
        near=near,
        address=f"Road {n}, Dhanmondi",
        price_factor=price_factor,
    )


_ALL: list[SubArea] = [
    # --- Mirpur: numbered sections plus the pockets around them ---------------
    _mirpur(1, ("Mirpur 2", "Mirpur 6", "Mirpur 10", "Shyamoli")),
    _mirpur(2, ("Mirpur 6", "Mirpur 10", "Mirpur 1", "Mirpur 7")),
    _mirpur(6, ("Mirpur 7", "Mirpur 2", "Mirpur 10", "Mirpur 11")),
    _mirpur(7, ("Mirpur 6", "Mirpur 11", "Pallabi", "Mirpur 2")),
    _mirpur(10, ("Mirpur 11", "Mirpur 2", "Kazipara", "Mirpur 13", "Mirpur 6"), 1.1),
    _mirpur(11, ("Mirpur 10", "Mirpur 12", "Pallabi", "Mirpur 7")),
    _mirpur(12, ("Mirpur 11", "Pallabi", "Mirpur DOHS", "Mirpur 10")),
    _mirpur(13, ("Mirpur 14", "Mirpur 10", "Kazipara", "Mirpur 11")),
    _mirpur(14, ("Mirpur 13", "Mirpur 10", "Kazipara")),
    _named("Pallabi", "Mirpur", "pallabi", ("Mirpur 12", "Mirpur 11", "Mirpur 7", "Mirpur DOHS")),
    _named("Kazipara", "Mirpur", "kazipara", ("Mirpur 10", "Mirpur 13", "Mirpur 14", "Mirpur 1"), 0.9),
    _named(
        "Mirpur DOHS", "Mirpur", r"mirpur[\s-]*dohs",
        ("Mirpur 12", "Pallabi", "Mirpur 11", "Mirpur 13"), 1.5, address="Mirpur DOHS",
    ),  # fmt: skip
    # --- Uttara: sectors (15-18 are the 3rd Phase) ----------------------------
    _uttara(1, ("Uttara Sector 3", "Uttara Sector 4", "Uttara Sector 7")),
    _uttara(3, ("Uttara Sector 1", "Uttara Sector 7", "Uttara Sector 4", "Uttara Sector 6"), 1.1),
    _uttara(4, ("Uttara Sector 1", "Uttara Sector 6", "Uttara Sector 5", "Uttara Sector 3")),
    _uttara(5, ("Uttara Sector 4", "Uttara Sector 6", "Uttara Sector 9")),
    _uttara(6, ("Uttara Sector 7", "Uttara Sector 4", "Uttara Sector 5", "Uttara Sector 3")),
    _uttara(7, ("Uttara Sector 6", "Uttara Sector 3", "Uttara Sector 9", "Uttara Sector 11"), 1.1),
    _uttara(9, ("Uttara Sector 7", "Uttara Sector 10", "Uttara Sector 6", "Uttara Sector 11")),
    _uttara(10, ("Uttara Sector 9", "Uttara Sector 11", "Uttara Sector 12")),
    _uttara(11, ("Uttara Sector 10", "Uttara Sector 12", "Uttara Sector 13", "Uttara Sector 7")),
    _uttara(12, ("Uttara Sector 11", "Uttara Sector 13", "Uttara Sector 10")),
    _uttara(13, ("Uttara Sector 14", "Uttara Sector 12", "Uttara Sector 11")),
    _uttara(14, ("Uttara Sector 13", "Uttara Sector 12", "Uttara Sector 15")),
    _uttara(15, ("Uttara Sector 16", "Uttara Sector 14", "Uttara Sector 13"), 0.85),
    _uttara(16, ("Uttara Sector 15", "Uttara Sector 17", "Uttara Sector 18"), 0.85),
    _uttara(17, ("Uttara Sector 16", "Uttara Sector 18", "Uttara Sector 15"), 0.8),
    _uttara(18, ("Uttara Sector 17", "Uttara Sector 16", "Uttara Sector 15"), 0.8),
    # --- Gulshan --------------------------------------------------------------
    SubArea(
        name="Gulshan 1", parent="Gulshan", pattern=r"\mgulshan[\s-]*1\M",
        near=("Gulshan 2", "Niketan", "Banani"), address="Gulshan 1",
    ),  # fmt: skip
    SubArea(
        name="Gulshan 2", parent="Gulshan", pattern=r"\mgulshan[\s-]*2\M",
        near=("Gulshan 1", "Baridhara", "Banani"), address="Gulshan 2", price_factor=1.15,
    ),  # fmt: skip
    _named("Niketan", "Gulshan", "niketan", ("Gulshan 1", "Gulshan 2", "Banani"), 0.75),
    # --- Dhanmondi ------------------------------------------------------------
    _dhanmondi_road(27, ("Dhanmondi 32", "Lalmatia", "Dhanmondi 15", "Jigatola"), 1.1),
    _dhanmondi_road(32, ("Dhanmondi 27", "Science Lab", "Dhanmondi 15"), 1.1),
    _dhanmondi_road(15, ("Jigatola", "Dhanmondi 27", "Dhanmondi 32")),
    _named("Jigatola", "Dhanmondi", "jigatola", ("Dhanmondi 15", "Science Lab", "Dhanmondi 27"), 0.85),
    _named(
        "Science Lab", "Dhanmondi", r"science[\s-]*lab", ("Dhanmondi 32", "Jigatola", "Dhanmondi 15"),
        0.9,
    ),  # fmt: skip
    # --- Mohammadpur ----------------------------------------------------------
    _named("Lalmatia", "Mohammadpur", "lalmatia", ("Dhanmondi 27", "Iqbal Road", "Tajmahal Road"), 1.2),
    _named(
        "Iqbal Road", "Mohammadpur", r"iqbal[\s-]*road", ("Lalmatia", "Tajmahal Road", "Shyamoli"),
    ),  # fmt: skip
    _named(
        "Tajmahal Road", "Mohammadpur", r"taj[\s-]*mahal[\s-]*road",
        ("Iqbal Road", "Japan Garden City", "Shyamoli"),
    ),  # fmt: skip
    _named("Shyamoli", "Mohammadpur", "shyamoli|shamoli", ("Japan Garden City", "Iqbal Road", "Mirpur 1")),
    _named(
        "Japan Garden City", "Mohammadpur", r"japan[\s-]*garden[\s-]*city",
        ("Shyamoli", "Tajmahal Road", "Bosila"), 1.1,
    ),  # fmt: skip
    _named("Bosila", "Mohammadpur", "bosila|basila", ("Japan Garden City", "Tajmahal Road"), 0.75),
]

SUBAREAS: dict[str, SubArea] = {area.name: area for area in _ALL}

# Numbered sectors that aren't curated still resolve, and get their neighbours
# by number: x-1 and x+1 first, then the next ones that exist.
_NUMBERED_RANGE = {"Mirpur": range(1, 15), "Uttara": range(1, 19)}

# Filler around a place name: "near Mirpur 12", "Mirpur 12 er kache", "Uttara area".
_FILLER_RE = re.compile(
    r"\b(near(by)?|around|close to|beside|er|kache|kachakachi|pashe|area|এলাকা|এর|কাছে)\b"
)
_TRAILING_CITY_RE = re.compile(r",?\s*\b(dhaka|bangladesh)\b\s*$")


def _normalize(location: str) -> str:
    text = location.translate(_TO_ASCII_DIGITS).lower()
    text = _FILLER_RE.sub(" ", text)
    text = _TRAILING_CITY_RE.sub("", text)
    return re.sub(r"\s+", " ", text).strip(" ,-/")


_NUMBERED_PATTERNS = [
    # "mirpur 12", "mirpur-12", "mirpur section 12", "section 12, mirpur"
    ("Mirpur", re.compile(r"^mirpur\s*-?\s*(?:sec(?:tion)?\.?\s*)?(\d{1,2})$")),
    ("Mirpur", re.compile(r"^sec(?:tion)?\.?\s*(\d{1,2})\s*,?\s*mirpur$")),
    # "uttara 7", "uttara sector 7", "sector 7, uttara", "uttara sec-7"
    ("Uttara", re.compile(r"^uttara\s*-?\s*(?:sec(?:tor)?\.?\s*-?\s*)?(\d{1,2})$")),
    ("Uttara", re.compile(r"^sec(?:tor)?\.?\s*-?\s*(\d{1,2})\s*,?\s*uttara$")),
    ("Gulshan", re.compile(r"^gulshan\s*-?\s*([12])$")),
    ("Dhanmondi", re.compile(r"^dhanmondi\s*-?\s*(?:road\s*)?(\d{1,2})a?$")),
    ("Dhanmondi", re.compile(r"^road\s*(\d{1,2})a?\s*,?\s*dhanmondi$")),
]


def _numbered_name(parent: str, n: int) -> str:
    if parent == "Uttara":
        return f"Uttara Sector {n}"
    return f"{parent} {n}"


def resolve_subarea(location: str | None) -> str | None:
    """The sub-area a location names, or None for a whole area ("Mirpur") or
    anything unrecognised -- those keep the broad area search. An uncurated
    Mirpur/Uttara number ("Mirpur 3") still resolves, so it gets numeric
    neighbours."""
    if not location:
        return None
    text = _normalize(location)
    for parent, pattern in _NUMBERED_PATTERNS:
        if match := pattern.match(text):
            name = _numbered_name(parent, int(match.group(1)))
            if name in SUBAREAS:
                return name
            numbered = _NUMBERED_RANGE.get(parent)
            return name if numbered and int(match.group(1)) in numbered else None
    # A named pocket, alone or with its parent: "lalmatia", "lalmatia, mohammadpur".
    for area in _ALL:
        if area.name in _NUMBERED_SUBAREA_NAMES:
            continue
        words = area.pattern.replace(r"\m", r"\b").replace(r"\M", r"\b")
        rest = re.sub(words, " ", text, count=1)
        if rest != text and not re.sub(rf"\b{area.parent.lower()}\b|[\s,/-]", "", rest):
            return area.name
    return None


_NUMBERED_SUBAREA_NAMES = frozenset(
    name for name, area in SUBAREAS.items() if re.search(r"\d$", name)
)


def get(name: str) -> SubArea | None:
    """The sub-area, including an uncurated Mirpur/Uttara number resolve_subarea
    returned (built on the fly, with numeric neighbours)."""
    if area := SUBAREAS.get(name):
        return area
    match = re.fullmatch(r"(Mirpur|Uttara Sector) (\d{1,2})", name)
    if not match:
        return None
    n = int(match.group(2))
    if match.group(1) == "Mirpur":
        return _mirpur(n, _numeric_near("Mirpur", n))
    return _uttara(n, _numeric_near("Uttara", n))


def _numeric_near(parent: str, n: int, limit: int = 4) -> tuple[str, ...]:
    known = [
        int(area.name.rsplit(" ", 1)[1])
        for area in _ALL
        if area.parent == parent and area.name in _NUMBERED_SUBAREA_NAMES
    ]
    ordered = sorted((k for k in known if k != n), key=lambda k: (abs(k - n), k))
    return tuple(_numbered_name(parent, k) for k in ordered[:limit])


def nearby(name: str) -> list[str]:
    """Places next to a sub-area, closest first."""
    area = get(name)
    return list(area.near) if area else []
