import random
from datetime import date, timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.data import listing_images as img
from app.data import localities
from app.models.property import ListingType, Property, PropertyType

# Every area below gets the same full spread: apartments for rent AND for sale
# across low/mid/high budget tiers, so search_apartments can find a match at any
# budget, in any location, for either renting or buying. There are no separate
# houses: a customer's বাড়ি / বাসা / house is an apartment.
_AREAS = [
    # city, neighborhood, road, rent(low, mid, high), sale(low, mid, high)
    dict(city="Dhaka", neighborhood="Uttara", road="Sector 7",
         rent=(14000, 28000, 60000), sale=(5500000, 8500000, 16000000)),
    dict(city="Dhaka", neighborhood="Dhanmondi", road="Road 27",
         rent=(20000, 42000, 75000), sale=(7500000, 12000000, 22000000)),
    dict(city="Dhaka", neighborhood="Gulshan", road="Road 90",
         rent=(45000, 95000, 170000), sale=(15000000, 32000000, 55000000)),
    dict(city="Dhaka", neighborhood="Banani", road="Road 11, Block C",
         rent=(35000, 55000, 100000), sale=(12000000, 20000000, 38000000)),
    dict(city="Dhaka", neighborhood="Mirpur", road="Block D, Mirpur 10",
         rent=(11000, 18000, 30000), sale=(4000000, 6500000, 10500000)),
    dict(city="Dhaka", neighborhood="Mohammadpur", road="Asad Avenue",
         rent=(13000, 25000, 38000), sale=(4500000, 7200000, 11500000)),
    dict(city="Dhaka", neighborhood="Bashundhara R/A", road="Block C",
         rent=(22000, 48000, 80000), sale=(8000000, 14500000, 24000000)),
    dict(city="Dhaka", neighborhood="Baridhara", road="Road 4, Baridhara DOHS",
         rent=(50000, 90000, 150000), sale=(18000000, 30000000, 48000000)),
    dict(city="Dhaka", neighborhood="Farmgate", road="Indira Road",
         rent=(10000, 20000, 32000), sale=(3800000, 6000000, 9500000)),
    dict(city="Dhaka", neighborhood="Khilgaon", road="Taltola",
         rent=(11000, 21000, 34000), sale=(4000000, 6200000, 9800000)),
    dict(city="Dhaka", neighborhood="Rampura", road="DIT Road",
         rent=(10000, 20000, 32000), sale=(3800000, 6000000, 9200000)),
    dict(city="Gazipur", neighborhood="Tongi", road="Station Road",
         rent=(8000, 12000, 20000), sale=(2800000, 4000000, 7000000)),
    dict(city="Savar", neighborhood="Savar Bazar", road="Bazar Road",
         rent=(7000, 11000, 18000), sale=(2500000, 3800000, 6500000)),
    dict(city="Narayanganj", neighborhood="Tanbazar", road="Tanbazar Road",
         rent=(8000, 13000, 21000), sale=(2800000, 4200000, 7500000)),
    dict(city="Keraniganj", neighborhood="South Keraniganj", road="South Keraniganj",
         rent=(7000, 12000, 19000), sale=(2600000, 3800000, 6800000)),
]

# Rule of thumb: the higher the price, the more bedrooms/bathrooms/amenities a
# listing has. Each table is a sorted list of (price_ceiling, bedrooms,
# bathrooms, sqft, amenities) -- a price picks the first row whose ceiling it
# doesn't exceed, so specs step up monotonically with price regardless of area.
_APARTMENT_RENT_SPECS = [
    (15000, 1, 1, 900, ["lift"]),
    (25000, 2, 1, 900, ["lift", "generator_backup"]),
    (40000, 2, 2, 1200, ["lift", "generator_backup", "parking"]),
    (70000, 3, 2, 1600, ["lift", "generator_backup", "parking", "gas_line"]),
    (110000, 3, 3, 2000, ["lift", "generator_backup", "parking", "gym", "security_guard"]),
    (float("inf"), 4, 4, 2600, ["lift", "generator_backup", "parking", "gym", "security_guard", "rooftop_access"]),
]

_APARTMENT_SALE_SPECS = [
    (5000000, 2, 1, 900, ["lift"]),
    (9000000, 2, 2, 1200, ["lift", "generator_backup"]),
    (15000000, 3, 2, 1500, ["lift", "generator_backup", "parking"]),
    (25000000, 3, 3, 1900, ["lift", "generator_backup", "parking", "gas_line"]),
    (40000000, 4, 4, 2400, ["lift", "generator_backup", "parking", "gym", "security_guard"]),
    (float("inf"), 5, 5, 3200, ["lift", "generator_backup", "parking", "gym", "security_guard", "rooftop_access", "furnished"]),
]

_TIER_LABELS = ("Budget", "Mid-range", "Premium")
_TIER_DAYS_OUT = (3, 10, 25)


def _specs_for_price(price: float, table: list[tuple]) -> tuple[int, int, int, list[str]]:
    for ceiling, bedrooms, bathrooms, sqft, amenities in table:
        if price <= ceiling:
            return bedrooms, bathrooms, sqft, amenities
    return table[-1][1:]


def _apartment(city: str, neighborhood: str, road: str, listing_type: ListingType, tier: int, price: float) -> dict:
    label = _TIER_LABELS[tier]
    for_sale = listing_type == ListingType.sale
    table = _APARTMENT_SALE_SPECS if for_sale else _APARTMENT_RENT_SPECS
    bedrooms, bathrooms, sqft, amenities = _specs_for_price(price, table)
    if not for_sale and sqft == 900 and bedrooms == 1:
        # Rent flats start at 900 sqft (was 600); price scales with the area.
        price = round(price * 1.5 / 500) * 500
    if not for_sale and sqft == 900:
        # Entry-level rent flats vary between 900 and 1,200 sqft (stable per
        # listing), with the rent following the area.
        sqft = 900 + 50 * random.Random(f"{neighborhood}|{road}|{tier}|{price}").randint(0, 6)
        price = round(price * sqft / 900 / 500) * 500
    return dict(
        title=f"{label} {bedrooms}BR Apartment {'for Sale in' if for_sale else 'in'} {neighborhood}",
        address_line=f"{road}, {neighborhood}",
        city=city,
        neighborhood=neighborhood,
        property_type=PropertyType.apartment,
        listing_type=listing_type,
        price=price,
        bedrooms=bedrooms,
        bathrooms=bathrooms,
        sqft=sqft,
        amenities=amenities,
        available_from=date.today() + timedelta(days=_TIER_DAYS_OUT[tier]),
        description=(
            f"{label}-tier flat in {neighborhood}, "
            f"{'priced for a straightforward sale' if for_sale else 'ready to move in'}."
        ),
    )


SAMPLE_PROPERTIES: list[dict] = []
for _area in _AREAS:
    for _tier, _price in enumerate(_area["rent"]):
        SAMPLE_PROPERTIES.append(
            _apartment(_area["city"], _area["neighborhood"], _area["road"], ListingType.rent, _tier, _price)
        )
    for _tier, _price in enumerate(_area["sale"]):
        SAMPLE_PROPERTIES.append(
            _apartment(_area["city"], _area["neighborhood"], _area["road"], ListingType.sale, _tier, _price)
        )

# Sector-level listings: every sub-area (Mirpur 12, Uttara Sector 7, Lalmatia...)
# gets a budget and a mid-range flat for rent and for sale, priced off its
# parent area, so "near Mirpur 12" has real sector matches and neighbours to
# fall back on. neighborhood stays the parent area; the sub-area is in the
# address (see app.data.localities).
_AREA_PRICES = {area["neighborhood"]: area for area in _AREAS}


def _round_price(price: float, listing_type: ListingType) -> float:
    step = 100000 if listing_type == ListingType.sale else 500
    return round(price / step) * step


def _subarea_apartments() -> list[dict]:
    rows = []
    for index, area in enumerate(localities.SUBAREAS.values()):
        prices = _AREA_PRICES[area.parent]
        # Small per-listing spread so sectors of one area don't all cost the same.
        spread = 1 + ((index % 5) - 2) * 0.03
        house, road = 3 + (index * 7) % 40, 1 + (index * 3) % 18
        for listing_type, tiers in ((ListingType.rent, prices["rent"]), (ListingType.sale, prices["sale"])):
            for tier in (0, 1):
                price = _round_price(tiers[tier] * area.price_factor * spread, listing_type)
                row = _apartment(prices["city"], area.parent, "", listing_type, tier, price)
                for_sale = listing_type == ListingType.sale
                row["title"] = (
                    f"{_TIER_LABELS[tier]} {row['bedrooms']}BR Apartment "
                    f"{'for Sale in' if for_sale else 'in'} {area.name}"
                )
                row["address_line"] = f"House {house + tier}, Road {road}, {area.address}"
                row["description"] = (
                    f"{_TIER_LABELS[tier]}-tier flat in {area.name}, {area.parent}, "
                    f"{'priced for a straightforward sale' if for_sale else 'ready to move in'}."
                )
                rows.append(row)
    return rows


SAMPLE_PROPERTIES.extend(_subarea_apartments())

# A few studios and duplexes thrown in for extra variety beyond the apartment matrix.
SAMPLE_PROPERTIES.extend([
    dict(
        title="Studio Apartment in Farmgate",
        address_line="Indira Road, Farmgate",
        city="Dhaka",
        neighborhood="Farmgate",
        property_type=PropertyType.studio,
        listing_type=ListingType.rent,
        price=13000,
        bedrooms=1,
        bathrooms=1,
        sqft=550,
        amenities=["lift", "furnished"],
        available_from=date.today(),
        description="Compact bachelor studio, ideal for a single tenant near Farmgate junction.",
    ),
    dict(
        title="Studio Apartment in Mirpur",
        address_line="Section 2, Mirpur",
        city="Dhaka",
        neighborhood="Mirpur",
        property_type=PropertyType.studio,
        listing_type=ListingType.rent,
        price=10500,
        bedrooms=1,
        bathrooms=1,
        sqft=500,
        amenities=["lift"],
        available_from=date.today() + timedelta(days=5),
        description="Entry-level studio close to Mirpur 2 bus stand and local markets.",
    ),
])


# ---------------------------------------------------------------------------
# Photos for the generated rows above: rotate through the curated pools so
# neighbouring listings don't all share one picture.
# ---------------------------------------------------------------------------


def _rotating(pool: list[str], index: int) -> str:
    return pool[index % len(pool)]


def _generated_photos(data: dict, index: int) -> list[str]:
    kind = data["property_type"]
    if kind == PropertyType.studio:
        cover = _rotating(img.LIVING_ROOMS, index)
        return [cover, _rotating(img.KITCHENS, index), _rotating(img.BATHROOMS, index)]
    cover = _rotating(img.APARTMENT_COVERS, index)
    return [
        cover,
        _rotating(img.LIVING_ROOMS, index + 5),
        _rotating(img.KITCHENS, index),
        _rotating(img.BEDROOMS, index),
    ]


for _index, _data in enumerate(SAMPLE_PROPERTIES):
    _photos = _generated_photos(_data, _index)
    _data["image_url"] = _photos[0]
    _data["images"] = _photos


# ---------------------------------------------------------------------------
# Featured listings: hand-written flats shown on the public landing page.
# ---------------------------------------------------------------------------

_KATHA_SQFT = 720


def _featured(
    *,
    title: str,
    address_line: str,
    neighborhood: str,
    property_type: PropertyType,
    listing_type: ListingType,
    price: float,
    bedrooms: int,
    bathrooms: float,
    sqft: int,
    amenities: list[str],
    description: str,
    photos: list[str],
    days_out: int = 7,
    city: str = "Dhaka",
) -> dict:
    return dict(
        title=title,
        address_line=address_line,
        city=city,
        neighborhood=neighborhood,
        property_type=property_type,
        listing_type=listing_type,
        price=price,
        bedrooms=bedrooms,
        bathrooms=bathrooms,
        sqft=sqft,
        amenities=amenities,
        available_from=date.today() + timedelta(days=days_out),
        description=description,
        image_url=photos[0],
        images=photos,
        is_featured=True,
    )


_A, _S = PropertyType.apartment, PropertyType.studio
_DUP = PropertyType.duplex
_COM, _PLOT = PropertyType.commercial, PropertyType.plot
_RENT, _SALE = ListingType.rent, ListingType.sale
_LR, _KT, _BR, _BA = img.LIVING_ROOMS, img.KITCHENS, img.BEDROOMS, img.BATHROOMS
_BLD, _SPL, _OFF, _TWR = img.BUILDINGS, img.SPLIT_LEVEL, img.OFFICES, img.OFFICE_TOWERS
_LAND = img.LAND
_LUX = ["lift", "generator_backup", "parking", "gym", "security_guard", "rooftop_access"]

FEATURED_PROPERTIES: list[dict] = [
    # --- Gulshan -----------------------------------------------------------
    _featured(
        title="Lakeview 3BR Apartment in Gulshan 2",
        address_line="Road 79, Gulshan 2", neighborhood="Gulshan",
        property_type=_A, listing_type=_RENT, price=165000,
        bedrooms=3, bathrooms=3, sqft=2150, amenities=_LUX + ["gas_line"],
        description=(
            "South-facing 3-bedroom flat overlooking Gulshan Lake, with a wraparound "
            "balcony, servant quarters and two reserved parking bays."
        ),
        photos=[_BLD[3], _LR[0], _KT[1], _BR[0], _BA[0]],
    ),
    _featured(
        title="Furnished Studio near Gulshan 1 Circle",
        address_line="Road 24, Gulshan 1", neighborhood="Gulshan",
        property_type=_S, listing_type=_RENT, price=55000,
        bedrooms=1, bathrooms=1, sqft=720,
        amenities=["lift", "generator_backup", "furnished", "security_guard"],
        description=(
            "Fully furnished serviced studio a short walk from Gulshan 1 Circle, ideal "
            "for expat professionals. Utilities and weekly housekeeping included."
        ),
        photos=[_LR[7], _KT[2], _BR[3]],
        days_out=2,
    ),
    _featured(
        title="Grade-A Office Floor on Gulshan Avenue",
        address_line="Gulshan Avenue, Gulshan 2", neighborhood="Gulshan",
        property_type=_COM, listing_type=_RENT, price=650000,
        bedrooms=0, bathrooms=4, sqft=6500,
        amenities=["lift", "generator_backup", "parking", "security_guard"],
        description=(
            "Full open-plan office floor in a glass-fronted tower with central AC, "
            "full generator backup and 12 car parks. Suits a regional head office."
        ),
        photos=[_TWR[0], _OFF[0], _OFF[1], _OFF[2]],
        days_out=30,
    ),
    _featured(
        title="4BR Duplex with Private Terrace in Gulshan 1",
        address_line="Road 32, Gulshan 1", neighborhood="Gulshan",
        property_type=_DUP, listing_type=_SALE, price=92000000,
        bedrooms=4, bathrooms=4.5, sqft=4300, amenities=_LUX + ["gas_line"],
        description=(
            "Two-level home on the top floors of a boutique building, with an internal "
            "staircase, a family lounge upstairs and a planted private terrace."
        ),
        photos=[_SPL[0], _SPL[1], _LR[12], _BR[4], _KT[0]],
        days_out=60,
    ),
    # --- Banani ------------------------------------------------------------
    _featured(
        title="Banani Road 11 Family Apartment",
        address_line="Road 11, Block E, Banani", neighborhood="Banani",
        property_type=_A, listing_type=_RENT, price=85000,
        bedrooms=3, bathrooms=3, sqft=1950,
        amenities=["lift", "generator_backup", "parking", "gas_line", "security_guard"],
        description=(
            "Bright 3-bedroom flat on Banani's main dining street, with a separate "
            "family living room and a drawing-dining area that seats ten."
        ),
        photos=[_BLD[0], _LR[2], img.DINING[0], _BR[1]],
        days_out=10,
    ),
    _featured(
        title="Lake-Facing 4BR Apartment for Sale in Banani",
        address_line="Road 2, Block A, Banani", neighborhood="Banani",
        property_type=_A, listing_type=_SALE, price=42000000,
        bedrooms=4, bathrooms=4, sqft=2600, amenities=_LUX,
        description=(
            "Ready flat facing Banani Lake with RAJUK-approved plans, two car parks, "
            "and a community hall and gym on the ground floor."
        ),
        photos=[_BLD[4], _LR[3], _KT[1], _BR[2], _BA[1]],
        days_out=20,
    ),
    _featured(
        title="Retail Shop on Kemal Ataturk Avenue, Banani",
        address_line="Kemal Ataturk Avenue, Banani", neighborhood="Banani",
        property_type=_COM, listing_type=_RENT, price=220000,
        bedrooms=0, bathrooms=1, sqft=1400, amenities=["generator_backup", "security_guard"],
        description=(
            "Ground-floor retail unit with 30 feet of glass frontage on one of Dhaka's "
            "busiest shopping streets. Suits a showroom, cafe or boutique."
        ),
        photos=[img.SHOPS[0], _TWR[1], _OFF[3]],
        days_out=14,
    ),
    # --- Dhanmondi ---------------------------------------------------------
    _featured(
        title="Dhanmondi Lake Road 3BR Apartment",
        address_line="Road 8A, Dhanmondi", neighborhood="Dhanmondi",
        property_type=_A, listing_type=_RENT, price=65000,
        bedrooms=3, bathrooms=3, sqft=1750,
        amenities=["lift", "generator_backup", "parking", "gas_line"],
        description=(
            "Lake-side flat a minute from the Dhanmondi Lake walkway, close to schools, "
            "Rabindra Sarobar and the Road 27 restaurants."
        ),
        photos=[_LR[1], _KT[0], _BR[0], _BA[0]],
        days_out=5,
    ),
    _featured(
        title="Satmasjid Road 4BR Duplex",
        address_line="Satmasjid Road, Dhanmondi", neighborhood="Dhanmondi",
        property_type=_DUP, listing_type=_SALE, price=48000000,
        bedrooms=4, bathrooms=4, sqft=3400,
        amenities=["lift", "generator_backup", "parking", "gas_line", "rooftop_access"],
        description=(
            "Duplex on the top two floors with an internal staircase, a family lounge "
            "upstairs and exclusive use of the roof."
        ),
        photos=[_SPL[1], _SPL[0], _LR[4], _BR[2]],
        days_out=40,
    ),
    _featured(
        title="Dhanmondi 2BR Starter Flat for Sale",
        address_line="Road 15A, Dhanmondi", neighborhood="Dhanmondi",
        property_type=_A, listing_type=_SALE, price=11500000,
        bedrooms=2, bathrooms=2, sqft=1150, amenities=["lift", "generator_backup", "gas_line"],
        description=(
            "Compact, well-kept 2-bedroom flat in a 10-year-old building: a sensible "
            "first home or a steady rental investment."
        ),
        photos=[_BLD[1], _LR[5], _KT[2], _BR[1]],
        days_out=15,
    ),
    _featured(
        title="Office Suite on Dhanmondi 27",
        address_line="Road 27 (Old), Dhanmondi", neighborhood="Dhanmondi",
        property_type=_COM, listing_type=_SALE, price=30000000,
        bedrooms=0, bathrooms=2, sqft=2400,
        amenities=["lift", "generator_backup", "parking", "security_guard"],
        description=(
            "Ready office suite on Dhanmondi 27 with a reception, four cabins and an "
            "open workspace for twenty. Two dedicated car parks."
        ),
        photos=[_OFF[2], _OFF[3], _OFF[0]],
        days_out=30,
    ),
    # --- Bashundhara -------------------------------------------------------
    _featured(
        title="Bashundhara Block D Family Flat",
        address_line="Road 7, Block D, Bashundhara R/A", neighborhood="Bashundhara R/A",
        property_type=_A, listing_type=_SALE, price=16500000,
        bedrooms=3, bathrooms=3, sqft=1700,
        amenities=["lift", "generator_backup", "parking", "security_guard"],
        description=(
            "Brand-new 3-bedroom flat in a gated block, close to Apollo Hospital and "
            "the international schools."
        ),
        photos=[_BLD[2], _LR[6], _KT[1], _BR[3]],
        days_out=20,
    ),
    _featured(
        title="3BR Apartment near NSU, Bashundhara",
        address_line="Road 2, Block B, Bashundhara R/A", neighborhood="Bashundhara R/A",
        property_type=_A, listing_type=_RENT, price=38000,
        bedrooms=3, bathrooms=2, sqft=1450, amenities=["lift", "generator_backup", "gas_line"],
        description=(
            "Practical 3-bedroom flat a short walk from North South University and "
            "Jamuna Future Park. Good natural light and cross ventilation."
        ),
        photos=[_LR[8], _KT[2], _BR[4]],
        days_out=3,
    ),
    _featured(
        title="5-Katha Residential Plot in Bashundhara Block I",
        address_line="Road 12, Block I, Bashundhara R/A", neighborhood="Bashundhara R/A",
        property_type=_PLOT, listing_type=_SALE, price=75000000,
        bedrooms=0, bathrooms=0, sqft=5 * _KATHA_SQFT, amenities=[],
        description=(
            "South-facing 5-katha plot on a 30-foot road with clear title and mutation "
            "done. Approved for a 9-storey residential building."
        ),
        photos=[_LAND[0], _LAND[1], _LAND[2]],
        days_out=0,
    ),
    # --- Uttara ------------------------------------------------------------
    _featured(
        title="Uttara Sector 4 Lakeside Apartment",
        address_line="Road 9, Sector 4, Uttara", neighborhood="Uttara",
        property_type=_A, listing_type=_RENT, price=45000,
        bedrooms=3, bathrooms=3, sqft=1600,
        amenities=["lift", "generator_backup", "parking", "gas_line"],
        description=(
            "3-bedroom flat by the Sector 4 lake, ten minutes from the airport and "
            "the Uttara metro stations."
        ),
        photos=[_BLD[5], _LR[10], _KT[1], _BR[6]],
        days_out=7,
    ),
    _featured(
        title="Uttara Sector 11 3BR Apartment for Sale",
        address_line="Road 6, Sector 11, Uttara", neighborhood="Uttara",
        property_type=_A, listing_type=_SALE, price=13500000,
        bedrooms=3, bathrooms=3, sqft=1550, amenities=["lift", "generator_backup", "parking"],
        description=(
            "Ready flat in a well-run building with a residents' association, "
            "near the Sector 11 market."
        ),
        photos=[_BLD[6], _LR[3], _BR[0], _BA[1]],
        days_out=25,
    ),
    _featured(
        title="Uttara Sector 7 Studio for Professionals",
        address_line="Road 18, Sector 7, Uttara", neighborhood="Uttara",
        property_type=_S, listing_type=_RENT, price=22000,
        bedrooms=1, bathrooms=1, sqft=600, amenities=["lift", "generator_backup", "furnished"],
        description=(
            "Furnished studio with a kitchenette and work nook, two minutes from "
            "Uttara Sector 7 park. Suits a single professional."
        ),
        photos=[_LR[12], _KT[2], _BA[0]],
        days_out=1,
    ),
    _featured(
        title="Uttara Sector 15 Duplex Home",
        address_line="Road 2, Sector 15, Uttara", neighborhood="Uttara",
        property_type=_DUP, listing_type=_RENT, price=120000,
        bedrooms=5, bathrooms=5, sqft=3800,
        amenities=["lift", "generator_backup", "parking", "rooftop_access", "security_guard"],
        description=(
            "Spacious 5-bedroom duplex with a double-height living room, a home office "
            "and its own roof terrace. Ideal for a large family."
        ),
        photos=[_SPL[3], _SPL[1], _LR[9], _BR[2]],
        days_out=30,
    ),
    # --- Purbachal ---------------------------------------------------------
    _featured(
        title="3-Katha Plot in Purbachal Sector 22",
        address_line="Road 104, Sector 22, Purbachal", neighborhood="Purbachal",
        property_type=_PLOT, listing_type=_SALE, price=18000000,
        bedrooms=0, bathrooms=0, sqft=3 * _KATHA_SQFT, amenities=[],
        description=(
            "RAJUK-allotted 3-katha residential plot with handover complete, near "
            "the 300-foot road."
        ),
        photos=[_LAND[1], _LAND[2], _LAND[0]],
        days_out=0,
    ),
    _featured(
        title="Purbachal New Town 3BR Apartment",
        address_line="Sector 4, Purbachal", neighborhood="Purbachal",
        property_type=_A, listing_type=_SALE, price=9800000,
        bedrooms=3, bathrooms=2, sqft=1400, amenities=["lift", "generator_backup", "parking"],
        description=(
            "Newly built 3-bedroom flat in Purbachal New Town, with lake views and "
            "quick access to the 300-foot road into the city."
        ),
        photos=[_BLD[3], _LR[11], _KT[0], _BR[1]],
        days_out=35,
    ),
    _featured(
        title="Corner Commercial Plot in Purbachal Sector 1",
        address_line="Sector 1, Purbachal", neighborhood="Purbachal",
        property_type=_PLOT, listing_type=_SALE, price=42000000,
        bedrooms=0, bathrooms=0, sqft=10 * _KATHA_SQFT, amenities=[],
        description=(
            "10-katha corner plot zoned for commercial use, fronting two roads. Suits "
            "a shopping complex, hospital or office building."
        ),
        photos=[_LAND[2], _LAND[0], _LAND[1]],
        days_out=0,
    ),
]

ALL_PROPERTIES: list[dict] = SAMPLE_PROPERTIES + FEATURED_PROPERTIES


def _needs_cover(image_url: str | None) -> bool:
    return not image_url or "placehold.co" in image_url


def seed(db: Session) -> int:
    """Non-destructive upsert, safe to run on every launch (run-local.bat does).

    Inserts only listings whose title isn't in the table yet. On existing rows it
    fills in photos (`images` when null, `image_url` when null or a placeholder)
    and never touches anything an admin may have edited (price, is_active, ...).
    Returns the number of rows inserted.
    """
    existing = {p.title: p for p in db.scalars(select(Property))}
    inserted = 0
    for data in ALL_PROPERTIES:
        prop = existing.get(data["title"])
        if prop is None:
            db.add(Property(**data))
            inserted += 1
            continue
        if prop.images is None:
            prop.images = data["images"]
        if _needs_cover(prop.image_url):
            prop.image_url = data["image_url"]
    db.commit()
    return inserted
