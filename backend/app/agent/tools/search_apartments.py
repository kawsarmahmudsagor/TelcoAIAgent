import json
import logging
import re
import uuid
from dataclasses import dataclass, field

from livekit.agents import RunContext, function_tool
from livekit.agents.llm import ToolError

from app.agent.userdata import SessionUserdata
from app.data import localities
from app.db.session import SessionLocal
from app.models.property import ListingType, Property, PropertyType
from app.repositories import offer_repo, property_repo
from app.services.taka import format_taka

_SHORTLIST_TOPIC = "apartment-shortlist"
_NEAREST_MATCH_COUNT = 3
_log = logging.getLogger(__name__)
_RESULT_LIMIT = 5
# A budget also takes homes this far past it ("15000 er moddhe" is about 15,000).
_BUDGET_STRETCH = 0.10
_POOL_LIMIT = 200
_TYPE_WORDS = {ListingType.rent: "for rent", ListingType.sale: "for sale"}
_TO_ASCII_DIGITS = str.maketrans("০১২৩৪৫৬৭৮৯", "0123456789")
_BANGLA_SCRIPT = re.compile(r"[ঀ-৿]")

# Everyday words the LLM passes through from the customer -> the stored value.
_AMENITY_SYNONYMS = {
    "generator": "generator_backup",
    "backup_generator": "generator_backup",
    "elevator": "lift",
    "security": "security_guard",
    "guard": "security_guard",
    "rooftop": "rooftop_access",
    "roof": "rooftop_access",
    "gas": "gas_line",
    "car_parking": "parking",
    "garage": "parking",
}


# Everyday words for a kind of property -> the stored PropertyType value.
_PROPERTY_TYPE_SYNONYMS = {
    "flat": "apartment",
    "flats": "apartment",
    "apartments": "apartment",
    # Every home is a flat; a villa, penthouse or townhouse is a duplex.
    "house": "apartment",
    "home": "apartment",
    "villa": "duplex",
    "penthouse": "duplex",
    "townhouse": "duplex",
    "shop": "commercial",
    "office": "commercial",
    "office_space": "commercial",
    "showroom": "commercial",
    "land": "plot",
    "lot": "plot",
}


def _parse_property_type(raw: str) -> PropertyType:
    key = raw.strip().lower().replace("-", "_").replace(" ", "_")
    return PropertyType(_PROPERTY_TYPE_SYNONYMS.get(key, key))


def _normalize_amenity(raw: str) -> str:
    key = raw.strip().lower().replace("-", "_").replace(" ", "_")
    return _AMENITY_SYNONYMS.get(key, key)


def listing_card(p: Property) -> dict:
    """A listing as the chat's shortlist card shows it, and as shown_listings
    stores it."""
    return {
        "id": str(p.id),
        "title": p.title,
        "address_line": p.address_line,
        "city": p.city,
        "neighborhood": p.neighborhood,
        "price": float(p.price),
        "listing_type": p.listing_type.value,
        "property_type": p.property_type.value,
        "bedrooms": p.bedrooms,
        "bathrooms": float(p.bathrooms),
        "sqft": p.sqft,
        "amenities": p.amenities,
        "image_url": p.image_url,
        "images": p.images,
    }


async def _send_cards(userdata: SessionUserdata, payload: str, clear_focus: bool) -> None:
    await userdata.room.local_participant.send_text(payload, topic=_SHORTLIST_TOPIC)
    if clear_focus:
        userdata.focused_listing = None


async def send_shortlist(userdata: SessionUserdata, payload: str, clear_focus: bool) -> None:
    """Puts the shortlist cards (JSON) on the customer's screen. With
    userdata.defer_cards the latest search waits for flush_shortlist instead."""
    if userdata.defer_cards:
        userdata.pending_cards = payload
        userdata.pending_cards_clear_focus = clear_focus
        return
    await _send_cards(userdata, payload, clear_focus)


async def flush_shortlist(userdata: SessionUserdata) -> bool:
    """Sends the cards send_shortlist held back. False when there were none."""
    payload = userdata.pending_cards
    if payload is None:
        return False
    userdata.pending_cards = None
    try:
        await _send_cards(userdata, payload, userdata.pending_cards_clear_focus)
    except Exception:
        _log.exception("could not send the shortlist cards")
        return False
    return True


def _assign_listing_numbers(shown: dict[int, dict], cards: list[dict]) -> list[int]:
    """A listing keeps the #number it was first shown under for the whole
    session, so "the Uttara one from before" still books the right property
    after a newer search."""
    by_id = {card["id"]: number for number, card in shown.items()}
    numbers = []
    for card in cards:
        number = by_id.get(card["id"])
        if number is None:
            number = len(shown) + 1
            by_id[card["id"]] = number
        shown[number] = card
        numbers.append(number)
    return numbers


@dataclass(frozen=True)
class _Budget:
    """The customer's budget, and the band searched around it. "15000 er
    moddhe" means about 15,000: homes up to 10% past a bound count too, unless
    the customer made it a hard minimum or maximum."""

    min: float | None
    max: float | None
    min_strict: bool = False
    max_strict: bool = False

    @property
    def given(self) -> bool:
        return self.min is not None or self.max is not None

    @property
    def lo(self) -> float | None:
        if self.min is None:
            return None
        return self.min if self.min_strict else self.min * (1 - _BUDGET_STRETCH)

    @property
    def hi(self) -> float | None:
        if self.max is None:
            return None
        return self.max if self.max_strict else self.max * (1 + _BUDGET_STRETCH)

    @property
    def ref(self) -> float | None:
        """The price results are ranked around: closest first."""
        return self.max if self.max is not None else self.min

    def within(self, price) -> bool:
        price = float(price)
        return (self.min is None or price >= self.min) and (
            self.max is None or price <= self.max
        )

    def allows(self, price) -> bool:
        """Inside every hard bound -- the only limit a fallback may not cross."""
        price = float(price)
        return not (self.min_strict and self.min is not None and price < self.min) and not (
            self.max_strict and self.max is not None and price > self.max
        )

    def phrase(self) -> str:
        # Prices say "taka", not "৳": the LLM copies the form it's given.
        if self.min is not None and self.max is not None:
            return f"{format_taka(self.min)}–{format_taka(self.max)}"
        if self.max is not None:
            return f"under {format_taka(self.max)}"
        return f"above {format_taka(self.min or 0)}"

    def closeness(self, prop: Property) -> tuple[float, float]:
        """Closest to the budget first; cheapest first with no budget."""
        if self.ref is None:
            return (float(prop.price), 0.0)
        return (abs(float(prop.price) - self.ref), float(prop.price))


@dataclass
class _Pool:
    """One area's matches: inside the stated budget, and in the stretch band
    just past it, each closest to the budget first."""

    in_budget: list[Property] = field(default_factory=list)
    stretch: list[Property] = field(default_factory=list)
    # listing id -> the sector next door it came from (sector searches only).
    nearby_area: dict[str, str] = field(default_factory=dict)
    notes: list[str] = field(default_factory=list)
    # The filters these came from, after any the area search relaxed.
    filters: dict = field(default_factory=dict)


@function_tool()
async def search_apartments(
    ctx: RunContext[SessionUserdata],
    budget_min: float | None = None,
    budget_max: float | None = None,
    budget_min_strict: bool = False,
    budget_max_strict: bool = False,
    location: str | None = None,
    locations: list[str] | None = None,
    location_mode: str | None = None,
    property_type: str | None = None,
    listing_type: str | None = None,
    bedrooms: int | None = None,
    bathrooms: float | None = None,
    amenities: list[str] | None = None,
    more: bool = False,
) -> str:
    """Search property listings using only the criteria the customer has stated
    or confirmed *in this conversation* (asking for "the same as last time" confirms
    the previous conversation's search).

    Leave every other argument as None, including numbers or types from on-file
    notes or earlier conversations they haven't confirmed in this one. Never hold a
    search back for missing fields: a location alone searches that whole area at any
    price, a budget alone searches every location, a property type alone searches
    that type everywhere. Ask a clarifying question first only if they've given
    nothing to search on. Rent and sale budgets differ in scale (thousands vs.
    lakhs/crores): reset budget_min and budget_max to None as soon as the customer
    switches between renting and buying.

    Args:
        budget_min: Minimum price/rent the customer will consider, if stated.
        budget_max: Maximum price/rent the customer will consider, if stated. A budget
            means "about this much": the search also includes homes slightly past it.
        budget_min_strict: True only if they made budget_min a hard floor ("minimum",
            "at least", "কমপক্ষে", "er kom na").
        budget_max_strict: True only if they made budget_max a hard ceiling ("maximum",
            "at most", "সর্বোচ্চ", "er beshi na"). "15000 er moddhe" alone is not strict.
        location: One city or neighborhood the customer wants, if stated, always in
            English spelling (e.g. "Mohammadpur" for মোহাম্মদপুর) whatever language
            the customer used. Keep a sector or section number they give ("Mirpur 12",
            "Uttara Sector 7", "Gulshan 2"; "মিরপুর ১২" -> "Mirpur 12") and drop words
            like "near" or "area": results start in that sector, then add the ones
            next to it.
        locations: Two or more separate areas, each spelled as for location, instead of
            location ("Dhanmondi ba Mirpur" -> ["Dhanmondi", "Mirpur"]).
        location_mode: With locations: "all" when they want to see each area ("A ebong
            B", "A and B", "A o B"); "any" when either will do ("A ba B", "A or B",
            "ei duitar moddhe", "je kono ekta").
        property_type: One of apartment (a flat), studio, duplex,
            commercial (shop/office space) or plot (land), if stated.
            বাসা, বাড়ি, বাড়ি ভাড়া, পুরো বাড়ি, ঘর, basa, bari, basha, "house" or "a home"
            all mean a flat: leave it None. We have no separate houses. villa means duplex.
            Studios, duplexes, commercial space and plots are only returned when asked for.
        listing_type: "rent" or "sale" (sale covers buying), if stated.
        bedrooms: Minimum number of bedrooms wanted, if stated.
        bathrooms: Minimum number of bathrooms wanted, if stated.
        amenities: Amenities the customer cares about, e.g. ["parking", "lift"]. Listings
            record: lift, generator_backup, parking, gas_line, gym, security_guard,
            rooftop_access, furnished.
        more: True when they ask for more or other options with the same criteria
            ("aro dekhao", "show me more"): returns homes not shown yet.
    """
    return await run_search(
        ctx.userdata,
        budget_min=budget_min,
        budget_max=budget_max,
        budget_min_strict=budget_min_strict,
        budget_max_strict=budget_max_strict,
        location=location,
        locations=locations,
        location_mode=location_mode,
        property_type=property_type,
        listing_type=listing_type,
        bedrooms=bedrooms,
        bathrooms=bathrooms,
        amenities=amenities,
        more=more,
    )


def _english_location(location: str) -> str:
    # Listings store areas in English, so a Bangla-script location matches
    # nothing and the LLM would tell the customer the area is empty. Bengali
    # digits are fine: "Mirpur ১২" is Mirpur 12.
    location = location.translate(_TO_ASCII_DIGITS).strip()
    if _BANGLA_SCRIPT.search(location):
        raise ToolError(
            "location must be in English spelling, e.g. 'Mohammadpur' for মোহাম্মদপুর. "
            "Call search_apartments again with the English spelling."
        )
    return location


def _split_areas(db, parts: list[str]) -> list[str]:
    """The separate areas in what the customer named. A part another part sits
    inside ("Uttara, Dhaka", "Mirpur 10, Mirpur") narrows it rather than being an
    area of its own -- decided from the listings, since "Savar" is both a city
    and an area people pick instead of Mirpur."""
    if len(parts) < 2:
        return parts

    def nests(inner: str, outer: str) -> bool:
        return bool(property_repo.search(db, location=f"{inner}, {outer}", limit=1))

    outers = {o for o in parts if any(i != o and nests(i, o) for i in parts)}
    areas = [p for p in parts if p not in outers]
    if not areas:
        return [", ".join(parts)]
    return [", ".join([a, *(o for o in parts if o in outers and nests(a, o))]) for a in areas]


def _area_pool(
    db, location: str | None, filters: dict, budget: _Budget, exclude: set | None
) -> _Pool:
    """Matches in one area, with the area-level fallbacks that keep the budget:
    the sectors next door, then the amenity nothing here has, then flats when
    no house fits."""
    subarea = localities.resolve_subarea(location)

    def fetch(where: str | None, f: dict) -> tuple[list[Property], list[Property]]:
        homes = property_repo.search(
            db,
            location=where,
            budget_min=budget.lo,
            budget_max=budget.hi,
            near_price=budget.ref,
            exclude_ids=exclude,
            limit=_POOL_LIMIT,
            **f,
        )
        return (
            [p for p in homes if budget.within(p.price)],
            [p for p in homes if not budget.within(p.price)],
        )

    def gather(f: dict) -> _Pool:
        in_budget, stretch = fetch(location, f)
        pool = _Pool(in_budget, stretch)
        # A sector ("Mirpur 12") with nothing in budget: the sectors next door,
        # closest first, with the same budget and filters -- an in-budget flat
        # one sector over beats an out-of-budget one here. A sector that has
        # matches shows only those: the customer asked about it.
        if subarea is not None and not in_budget:
            seen: set = set()
            for near in localities.nearby(subarea):
                if len(pool.in_budget) >= _RESULT_LIMIT:
                    break
                for prop in fetch(near, f)[0]:
                    if prop.id in seen or len(pool.in_budget) >= _RESULT_LIMIT:
                        continue
                    seen.add(prop.id)
                    pool.in_budget.append(prop)
                    pool.nearby_area[str(prop.id)] = near
        return pool

    pool = gather(filters)

    # Amenities nothing here has together: drop them -- the place and price are
    # usually firmer than one feature -- but only when that is what empties the
    # search; a budget or bedroom count no home meets is the fallbacks' job.
    # Drop the rarest one among homes matching everything else, one at a time,
    # so "gym + lift" keeps lift when only gym is the problem.
    if not pool.in_budget and filters["amenities"]:
        without = gather({**filters, "amenities": None})
        candidates = without.in_budget
        if candidates:
            kept = list(filters["amenities"])
            dropped: list[str] = []
            while kept and not [p for p in candidates if set(kept) <= set(p.amenities)]:
                rarest = min(kept, key=lambda a: sum(a in p.amenities for p in candidates))
                kept.remove(rarest)
                dropped.append(rarest)
            filters["amenities"] = kept or None
            pool = gather(filters)
            missing = ", ".join(repr(a) for a in dropped)
            pool.notes.append(
                f"Nothing matched with {missing}, so the search dropped it. Tell the customer "
                f"plainly that none of our homes here have {missing}, then offer these instead."
            )

    pool.filters = filters
    return pool


def _varied(homes: list, limit: int) -> list:
    """`limit` of `homes` (already best-first) with as many different sizes as
    they offer, so a search shows 900, 1,050 and 1,200 sqft flats rather than five
    of the same. Each size's best match goes first, then the rest fill in; the
    result keeps the original order."""
    if len(homes) <= limit:
        return homes
    picked: list[int] = []
    seen_sizes: set = set()
    for i, home in enumerate(homes):
        if home.sqft not in seen_sizes and len(picked) < limit:
            seen_sizes.add(home.sqft)
            picked.append(i)
    for i in range(len(homes)):
        if len(picked) >= limit:
            break
        if i not in picked:
            picked.append(i)
    return [homes[i] for i in sorted(picked)]


def _take(pool: _Pool, budget: _Budget, limit: int, more: bool, stretch_slots: int) -> list:
    """The listings to show from a pool: in budget first, closest to it, then at
    most `stretch_slots` just past it. `more` shows the whole band. Within the
    budget the picks vary in size (see _varied)."""
    if not budget.given:
        return _varied(pool.in_budget, limit)
    if more:
        return _varied(sorted(pool.in_budget + pool.stretch, key=budget.closeness), limit)
    stretch = pool.stretch[: min(stretch_slots, limit)]
    return _varied(pool.in_budget, limit - len(stretch)) + stretch


def _even_shares(sizes: list[int], total: int) -> list[int]:
    """`total` slots shared as evenly as the areas allow, the first-named area
    taking the odd one; slots an area can't fill go to the others."""
    shares = [0] * len(sizes)
    while sum(shares) < total:
        grew = False
        for i, size in enumerate(sizes):
            if sum(shares) < total and shares[i] < size:
                shares[i] += 1
                grew = True
        if not grew:
            break
    return shares


async def run_search(
    userdata: SessionUserdata,
    *,
    budget_min: float | None = None,
    budget_max: float | None = None,
    budget_min_strict: bool = False,
    budget_max_strict: bool = False,
    location: str | None = None,
    locations: list[str] | None = None,
    location_mode: str | None = None,
    property_type: str | None = None,
    listing_type: str | None = None,
    bedrooms: int | None = None,
    bathrooms: float | None = None,
    amenities: list[str] | None = None,
    more: bool = False,
) -> str:
    """search_apartments without the tool wrapper, so the turn router can run a
    search before the LLM (see app.agent.turn_router). Same side effects: it
    records last_search, sends the shortlist cards to the room and numbers the
    listings. Raises ToolError on arguments the tool would refuse."""
    named = [_english_location(loc) for loc in (locations or []) if loc and loc.strip()]
    if not named and location and location.strip():
        named = [_english_location(location)]
    try:
        parsed_property_type = _parse_property_type(property_type) if property_type else None
        parsed_listing_type = (
            ListingType(listing_type.lower().replace("buy", "sale")) if listing_type else None
        )
    except ValueError as exc:
        raise ToolError(str(exc)) from exc
    mode = "all" if (location_mode or "").lower() == "all" else "any"
    budget = _Budget(budget_min, budget_max, bool(budget_min_strict), bool(budget_max_strict))
    exclude = (
        {uuid.UUID(card["id"]) for card in userdata.shown_listings.values()} if more else None
    )

    db = SessionLocal()
    try:
        # A sub-area with its parent ("Lalmatia, Mohammadpur") is one place; other
        # lists are split into areas ("Dhanmondi, Mirpur" is two).
        if len(named) == 1 and localities.resolve_subarea(named[0]) is None:
            parts = [t.strip() for t in re.split(r"[,/]", named[0]) if t.strip()]
        else:
            parts = named
        areas: list[str | None] = list(_split_areas(db, parts)) if parts else [None]
        multi = len(areas) > 1

        # No rent/sale given, but a budget only one of them reaches: search that
        # one, or a 15-lakh budget lists 7,000-taka rentals.
        ranges = property_repo.residential_price_ranges(db)
        if parsed_listing_type is None and budget.ref is not None:
            rent, sale = ranges.get(ListingType.rent), ranges.get(ListingType.sale)
            if rent and budget.ref > rent[1]:
                parsed_listing_type = ListingType.sale
            elif sale and budget.ref < sale[0]:
                parsed_listing_type = ListingType.rent

        criteria = {
            "budget_min": budget_min,
            "budget_max": budget_max,
            "budget_min_strict": budget_min_strict or None,
            "budget_max_strict": budget_max_strict or None,
            "location": None if multi else areas[0],
            "locations": areas if multi else None,
            "location_mode": mode if multi else None,
            "property_type": parsed_property_type.value if parsed_property_type else None,
            "listing_type": parsed_listing_type.value if parsed_listing_type else None,
            "bedrooms": bedrooms,
            "bathrooms": bathrooms,
        }
        userdata.last_search = {k: v for k, v in criteria.items() if v is not None}

        # An amenity no listing records can only ever zero out the search (and
        # tempts the LLM to claim a listing "has" it), so search on the ones
        # that exist and tell the LLM plainly about the rest.
        unknown_amenities: list[str] = []
        if amenities:
            known = property_repo.known_amenities(db)
            normalized = [_normalize_amenity(a) for a in amenities]
            unknown_amenities = [a for a in normalized if a not in known]
            amenities = [a for a in normalized if a in known] or None

        filters = dict(
            property_type=parsed_property_type,
            listing_type=parsed_listing_type,
            bedrooms=bedrooms,
            bathrooms=bathrooms,
            amenities=amenities,
        )
        pools = [(area, _area_pool(db, area, dict(filters), budget, exclude)) for area in areas]
        notes = [note for _, pool in pools for note in pool.notes]
        area_label: dict[str, str] = {}
        nearby_area: dict[str, str] = {}
        subarea = None if multi else localities.resolve_subarea(areas[0])
        for area, pool in pools:
            nearby_area.update(pool.nearby_area)
            if multi:
                for prop in pool.in_budget + pool.stretch:
                    area_label.setdefault(str(prop.id), area or "")

        def where_text(names: list) -> str:
            names = [n for n in names if n]
            return f" in {' or '.join(names)}" if names else ""

        # The filters the area search ended on (an amenity dropped, a house
        # widened to any home), so the fallbacks below build on them.
        searched = filters if multi else pools[0][1].filters

        def homes_from(where: list[str | None], **changes) -> list[Property]:
            """In-budget homes with some criteria changed, across the given areas,
            cheapest first."""
            found: dict = {}
            f = {**searched, "budget_min": budget.min, "budget_max": budget.max, **changes}
            for area in where:
                for p in property_repo.search(db, location=area, limit=1000, **f):
                    found[p.id] = p
            return sorted(found.values(), key=lambda p: float(p.price))

        results: list[Property] = []
        price_context = None
        if not multi:
            pool = pools[0][1]
            # Nothing in budget leaves results empty: the price fallback below
            # then shows the closest homes, stretch band included.
            if pool.in_budget or more:
                results = _take(pool, budget, _RESULT_LIMIT, more, 1)
        elif not more and not any(pl.in_budget for _, pl in pools):
            results = []
        elif mode == "any":
            merged = _Pool(
                sorted(
                    {p.id: p for _, pl in pools for p in pl.in_budget}.values(),
                    key=budget.closeness,
                ),
                sorted(
                    {p.id: p for _, pl in pools for p in pl.stretch}.values(),
                    key=budget.closeness,
                ),
            )
            results = _take(merged, budget, _RESULT_LIMIT, more, 1)
        else:
            stretch = []
            if budget.given and not more:
                stretch = sorted(
                    (p for _, pl in pools for p in pl.stretch), key=budget.closeness
                )[:1]
            seen = {p.id for p in stretch}
            area_homes = []
            for _, pl in pools:
                homes = [p for p in (pl.in_budget + pl.stretch if more else pl.in_budget)
                         if p.id not in seen]
                if more and budget.given:
                    homes.sort(key=budget.closeness)
                area_homes.append(homes)
                seen.update(p.id for p in homes)
            shares = _even_shares([len(h) for h in area_homes], _RESULT_LIMIT - len(stretch))
            for homes, share in zip(area_homes, shares):
                results += homes[:share]
            results += stretch

        if multi and results:
            # Each named area answers for itself: one with nothing in budget
            # gets a sentence, not a card.
            shown_areas = {area_label.get(str(p.id)) for p in results}
            for area, pool in pools:
                if area in shown_areas or pool.in_budget:
                    continue
                if budget.given:
                    anywhere = homes_from([area], budget_min=None, budget_max=None)
                    if anywhere:
                        notes.append(
                            f"Nothing in {area} matched the {budget.phrase()} budget; homes "
                            f"there start at {format_taka(anywhere[0].price)}. Say so plainly."
                        )
                        continue
                notes.append(f"Nothing in {area} matched. Say so plainly.")

        # A budget with no matches usually means the customer's number is outside
        # what's actually available (too low or too high), not that nothing at all
        # fits — re-check the same criteria minus budget so we can tell them the
        # real range and show the closest-priced options instead of a dead end.
        if not results and not more and budget.given:
            unfiltered = homes_from(areas, budget_min=None, budget_max=None)
            if unfiltered:
                prices = [float(p.price) for p in unfiltered]
                # The closest, but never past a hard minimum or maximum.
                results = [
                    p for p in sorted(unfiltered, key=budget.closeness) if budget.allows(p.price)
                ][:_NEAREST_MATCH_COUNT]
                where = where_text(areas)
                price_context = (
                    f"Nothing{where} matched the {budget.phrase()} budget. The available "
                    f"range{where} is {format_taka(prices[0])}–{format_taka(prices[-1])}. "
                    + (
                        "Tell the customer this plainly and show them the closest-priced "
                        "options below instead of just saying nothing was found."
                        if results
                        else "Tell the customer this plainly, and ask whether they can go "
                        "past their limit."
                    )
                )
            notes += _wider_notes(
                budget, areas, parsed_listing_type, bool(listing_type), bedrooms, ranges,
                homes_from,
            )

        cards = [listing_card(p) for p in results]
        # Live offers ride along on the card (the chat shows a badge) and in the
        # LLM's text below; rent listings never have any.
        live_offers = offer_repo.live_for_properties(db, [p.id for p in results])
        offer_lines: dict[str, str] = {}
        for p, card in zip(results, cards):
            offers = live_offers.get(p.id, [])
            card["offers"] = [offer_repo.badge(o) for o in offers]
            if offers:
                offer_lines[card["id"]] = "; ".join(offer_repo.describe(o) for o in offers)
    finally:
        db.close()

    is_phone_call = userdata.is_phone_call
    if not is_phone_call:
        # A phone has no screen to show the shortlist on.
        await send_shortlist(userdata, json.dumps(cards), bool(cards))

    amenity_note = ""
    if unknown_amenities:
        amenity_note = (
            f"No listings record {', '.join(repr(a) for a in unknown_amenities)}, so the "
            "search ignored it. Never claim a listing has it, and don't say you can't "
            "confirm it. Tell the customer the listings don't mention it and offer a "
            "viewing where they can confirm it, as WHEN YOU DON'T HAVE A DETAIL says. "
        )
    note_text = "".join(f"{note} " for note in notes)

    if not cards:
        if more:
            return (
                f"{amenity_note}No more homes match these criteria beyond the ones already "
                "shown. Say so, and ask if they'd widen the area, budget or other criteria."
            )
        if price_context:
            return f"{amenity_note}{note_text}{price_context}"
        return (
            amenity_note
            + note_text
            + "No matching listings found — let the customer know and ask if they'd flex on any criteria."
        )

    numbers = _assign_listing_numbers(userdata.shown_listings, cards)

    # The customer can only see the cards on their own screen -- everything you
    # know about them for answering follow-ups (amenities, sqft, exact price,
    # etc.) has to come from here, for every card shown, not just the top pick.
    # Missing a field for a card means you don't actually know it; say so
    # instead of guessing what a listing "probably" has.
    def area_of(card: dict) -> str:
        if card["id"] in nearby_area:
            return f"{nearby_area[card['id']]} (nearby, not {subarea})"
        if card["id"] in area_label:
            return area_label[card["id"]]
        return subarea or card["neighborhood"] or card["city"]

    listing_lines = [
        f"#{n} {c['title']}, area: {area_of(c)} — "
        f"{format_taka(c['price'], sale=c['listing_type'] == 'sale')}, "
        f"{c['bedrooms']}bd/{c['bathrooms']}ba, {c['sqft']} sqft, "
        f"amenities: {', '.join(c['amenities']) if c['amenities'] else 'none listed'}"
        + (f"; has offer: {offer_lines[c['id']]}" if c["id"] in offer_lines else "")
        for n, c in zip(numbers, cards)
    ]
    found = f"Found {len(cards)} matching listings"
    if nearby_area:
        found = (
            f"Found nothing in budget in {subarea} itself, but {len(nearby_area)} in the areas "
            f"next to it. Say plainly there's nothing in {subarea}, then offer these as close "
            "alternatives, naming their area"
        )
    elif multi:
        found += ", naming each one's area when you mention it"
    if is_phone_call:
        summary = (
            f"{found}. This is a phone call: the customer can't "
            "see them, so describe the best two or three aloud, briefly:\n"
            + "\n".join(listing_lines)
            + "\nPass a listing's #number as listing_number to update_booking_form when booking "
            "it. Refer to listings aloud by title or area, never by #number."
        )
    else:
        summary = (
            f"{found}. They're shown on the customer's screen in this order:\n"
            + "\n".join(listing_lines)
            + "\nPass a listing's #number as listing_number to update_booking_form when booking "
            "it. Refer to listings aloud by title, area or position, never by #number — the "
            "customer's cards aren't numbered. When a later reply is about just one of these, "
            "open it with [show:#number] (see SHOWING ONE LISTING)."
        )
    if budget.given and not price_context and any(not budget.within(c["price"]) for c in cards):
        summary += (
            f"\nA listing priced outside {budget.phrase()} is slightly past their budget: "
            "never call it within the budget."
        )
    if offer_lines:
        summary += (
            "\nDon't mention these offers unless the customer has asked about offers, "
            "discounts or payment terms. If they have: name a listing's offer in a few words, "
            "without terms or end date unless they asked for the offer's details (then call "
            "search_offers for them); mention only offers it or this list names, and never "
            "invent or negotiate a discount."
        )
    if price_context:
        return f"{amenity_note}{note_text}{price_context} {summary}"
    return f"{amenity_note}{note_text}{summary}"


def _wider_notes(
    budget: _Budget,
    areas: list[str | None],
    listing_type: ListingType | None,
    type_was_stated: bool,
    bedrooms: int | None,
    ranges: dict,
    homes_from,
) -> list[str]:
    """When nothing fits the budget: what would fit if one criterion carried
    over from earlier went, so the LLM can offer it instead of a dead end. Only
    offered, never shown -- the customer may really mean what they said."""
    notes = []
    if listing_type is not None and type_was_stated:
        other = ListingType.rent if listing_type == ListingType.sale else ListingType.sale
        low, high = ranges.get(listing_type, (None, None))
        other_low, other_high = ranges.get(other, (None, None))
        # Only a budget on the other type's scale: 15 lakh isn't a rent.
        ref = budget.ref
        if (
            ref is not None
            and low is not None
            and other_low is not None
            and not (low <= ref <= high)
            and other_low * (1 - _BUDGET_STRETCH) <= ref <= other_high
        ):
            fit = homes_from(areas, listing_type=other)
            if fit:
                notes.append(
                    f"No homes {_TYPE_WORDS[listing_type]} come near "
                    f"{format_taka(ref)}, but {len(fit)} homes {_TYPE_WORDS[other]} fit "
                    f"this budget, from {format_taka(fit[0].price)}. Ask whether they want a "
                    f"home {_TYPE_WORDS[other]} before showing them."
                )
    if any(areas):
        fit = homes_from([None])
        if fit:
            notes.append(
                f"Elsewhere, {len(fit)} homes fit this budget, from {format_taka(fit[0].price)}. "
                "Offer to show them; don't show them unasked."
            )
    if bedrooms:
        fit = homes_from(areas, bedrooms=None)
        if fit:
            notes.append(
                f"With fewer bedrooms, {len(fit)} homes fit this budget, from "
                f"{format_taka(fit[0].price)}. Offer them; don't show them unasked."
            )
    return notes
