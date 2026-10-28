"""Care centres and which one is nearest to a place in Bangladesh.

Static reference data, no DB. Every district maps by hand to the centre a
customer there would actually go to (road and bridge access, not straight-line
distance: Gopalganj goes to Khulna, Kishoreganj to Mymensingh). Dhaka has five
centres, so a Dhaka customer is matched by area (Mirpur, Uttara, Tongi, Savar
...); "Dhaka" alone lists all five.

The same centres, addresses and hours are in the knowledge base
(app/data/kb/stores-and-care-centres.md); tests/test_care_centres.py keeps the
two in step.
"""

from __future__ import annotations

import difflib
import re
import unicodedata
from dataclasses import dataclass

CARE_CENTRE_HOURS = "open every day, 9 am to 7 pm"
EXPERIENCE_CENTRE_HOURS = "open every day, 9 am to 9 pm"


@dataclass(frozen=True)
class CareCentre:
    name: str
    address: str
    district: str
    bn: str  # name and address as the Bangla KB passage words them
    hours: str = CARE_CENTRE_HOURS


CENTRES: dict[str, CareCentre] = {
    "gulshan": CareCentre(
        "telco Experience Centre",
        "Gulshan Avenue, Dhaka 1212",
        "Dhaka",
        "telco এক্সপেরিয়েন্স সেন্টার, গুলশান এভিনিউ, ঢাকা ১২১২",
        EXPERIENCE_CENTRE_HOURS,
    ),
    "dhanmondi": CareCentre(
        "Dhanmondi care centre",
        "Satmasjid Road, near Road 27, Dhaka",
        "Dhaka",
        "ধানমন্ডি কেয়ার সেন্টার, সাতমসজিদ রোড, রোড ২৭-এর কাছে",
    ),
    "uttara": CareCentre(
        "Uttara care centre",
        "Sector 7, near the Uttara Model Town park, Dhaka",
        "Dhaka",
        "উত্তরা কেয়ার সেন্টার, সেক্টর ৭, উত্তরা মডেল টাউন পার্কের কাছে",
    ),
    "mirpur": CareCentre(
        "Mirpur care centre",
        "Mirpur 10 roundabout, Dhaka",
        "Dhaka",
        "মিরপুর কেয়ার সেন্টার, মিরপুর ১০ গোলচত্বর",
    ),
    "motijheel": CareCentre(
        "Motijheel care centre",
        "Dilkusha commercial area, Dhaka",
        "Dhaka",
        "মতিঝিল কেয়ার সেন্টার, দিলকুশা কমার্শিয়াল এরিয়া",
    ),
    "chattogram": CareCentre(
        "GEC Circle care centre",
        "CDA Avenue, Chattogram",
        "Chattogram",
        "জিইসি মোড় কেয়ার সেন্টার, সিডিএ এভিনিউ, চট্টগ্রাম",
    ),
    "sylhet": CareCentre(
        "Zindabazar care centre",
        "Zindabazar main road, Sylhet",
        "Sylhet",
        "জিন্দাবাজার কেয়ার সেন্টার, জিন্দাবাজার মেইন রোড, সিলেট",
    ),
    "rajshahi": CareCentre(
        "Shaheb Bazar care centre",
        "near Zero Point, Rajshahi",
        "Rajshahi",
        "সাহেব বাজার কেয়ার সেন্টার, জিরো পয়েন্টের কাছে, রাজশাহী",
    ),
    "khulna": CareCentre(
        "KDA Avenue care centre",
        "near Shibbari More, Khulna",
        "Khulna",
        "কেডিএ এভিনিউ কেয়ার সেন্টার, শিববাড়ি মোড়ের কাছে, খুলনা",
    ),
    "barishal": CareCentre(
        "Sadar Road care centre",
        "Barishal city",
        "Barishal",
        "সদর রোড কেয়ার সেন্টার, বরিশাল শহর",
    ),
    "rangpur": CareCentre(
        "Jahaj Company More care centre",
        "Station Road, Rangpur",
        "Rangpur",
        "জাহাজ কোম্পানি মোড় কেয়ার সেন্টার, স্টেশন রোড, রংপুর",
    ),
    "mymensingh": CareCentre(
        "Ganginarpar care centre",
        "near the town hall, Mymensingh",
        "Mymensingh",
        "গাঙ্গিনারপাড় কেয়ার সেন্টার, টাউন হলের কাছে, ময়মনসিংহ",
    ),
}

_DHAKA_CENTRES = ("gulshan", "dhanmondi", "uttara", "mirpur", "motijheel")

# district -> (Bangla name, centre key or None for Dhaka, other spellings).
DISTRICTS: dict[str, tuple[str, str | None, tuple[str, ...]]] = {
    # Dhaka division
    "Dhaka": ("ঢাকা", None, ("dacca",)),
    "Gazipur": ("গাজীপুর", "uttara", ("gajipur",)),
    "Narayanganj": ("নারায়ণগঞ্জ", "motijheel", ("narayangonj", "narayanganj city")),
    "Narsingdi": ("নরসিংদী", "motijheel", ("narshingdi", "narsingdhi")),
    "Manikganj": ("মানিকগঞ্জ", "mirpur", ("manikgonj",)),
    "Munshiganj": ("মুন্সীগঞ্জ", "motijheel", ("munshigonj", "bikrampur")),
    "Tangail": ("টাঙ্গাইল", "uttara", ("tangail",)),
    "Kishoreganj": ("কিশোরগঞ্জ", "mymensingh", ("kishorgonj", "kishoregonj")),
    "Faridpur": ("ফরিদপুর", "motijheel", ()),
    "Gopalganj": ("গোপালগঞ্জ", "khulna", ("gopalgonj",)),
    "Madaripur": ("মাদারীপুর", "motijheel", ()),
    "Rajbari": ("রাজবাড়ী", "motijheel", ()),
    "Shariatpur": ("শরীয়তপুর", "motijheel", ("shoriatpur",)),
    # Chattogram division
    "Chattogram": ("চট্টগ্রাম", "chattogram", ("chittagong", "ctg", "chottogram")),
    "Cox's Bazar": ("কক্সবাজার", "chattogram", ("coxs bazar", "cox bazar", "coxsbazar")),
    "Rangamati": ("রাঙ্গামাটি", "chattogram", ("rangamati",)),
    "Bandarban": ("বান্দরবান", "chattogram", ()),
    "Khagrachhari": ("খাগড়াছড়ি", "chattogram", ("khagrachari",)),
    "Feni": ("ফেনী", "chattogram", ()),
    "Noakhali": ("নোয়াখালী", "chattogram", ("maijdee",)),
    "Lakshmipur": ("লক্ষ্মীপুর", "chattogram", ("laxmipur", "lakshipur")),
    "Chandpur": ("চাঁদপুর", "motijheel", ()),
    "Cumilla": ("কুমিল্লা", "motijheel", ("comilla",)),
    "Brahmanbaria": ("ব্রাহ্মণবাড়িয়া", "motijheel", ("b baria", "bbaria")),
    # Sylhet division
    "Sylhet": ("সিলেট", "sylhet", ()),
    "Moulvibazar": ("মৌলভীবাজার", "sylhet", ("maulvibazar", "srimangal")),
    "Habiganj": ("হবিগঞ্জ", "sylhet", ("hobiganj", "habigonj")),
    "Sunamganj": ("সুনামগঞ্জ", "sylhet", ("sunamgonj",)),
    # Rajshahi division
    "Rajshahi": ("রাজশাহী", "rajshahi", ()),
    "Natore": ("নাটোর", "rajshahi", ()),
    "Naogaon": ("নওগাঁ", "rajshahi", ("naogaon", "nowgaon")),
    "Chapainawabganj": ("চাঁপাইনবাবগঞ্জ", "rajshahi", ("chapai nawabganj", "chapai")),
    "Pabna": ("পাবনা", "rajshahi", ("ishwardi",)),
    "Sirajganj": ("সিরাজগঞ্জ", "rajshahi", ("sirajgonj", "shirajganj")),
    "Bogura": ("বগুড়া", "rajshahi", ("bogra",)),
    "Joypurhat": ("জয়পুরহাট", "rajshahi", ("jaipurhat",)),
    # Khulna division (Kushtia is nearer Rajshahi over the Lalon Shah bridge)
    "Khulna": ("খুলনা", "khulna", ()),
    "Bagerhat": ("বাগেরহাট", "khulna", ("mongla",)),
    "Satkhira": ("সাতক্ষীরা", "khulna", ()),
    "Jashore": ("যশোর", "khulna", ("jessore", "benapole")),
    "Jhenaidah": ("ঝিনাইদহ", "khulna", ("jhenaidaha",)),
    "Magura": ("মাগুরা", "khulna", ()),
    "Narail": ("নড়াইল", "khulna", ()),
    "Kushtia": ("কুষ্টিয়া", "rajshahi", ()),
    "Chuadanga": ("চুয়াডাঙ্গা", "khulna", ()),
    "Meherpur": ("মেহেরপুর", "khulna", ()),
    # Barishal division
    "Barishal": ("বরিশাল", "barishal", ("barisal",)),
    "Bhola": ("ভোলা", "barishal", ()),
    "Patuakhali": ("পটুয়াখালী", "barishal", ("kuakata",)),
    "Pirojpur": ("পিরোজপুর", "barishal", ()),
    "Jhalokathi": ("ঝালকাঠি", "barishal", ("jhalakathi", "jhalokati")),
    "Barguna": ("বরগুনা", "barishal", ()),
    # Rangpur division
    "Rangpur": ("রংপুর", "rangpur", ()),
    "Dinajpur": ("দিনাজপুর", "rangpur", ()),
    "Thakurgaon": ("ঠাকুরগাঁও", "rangpur", ()),
    "Panchagarh": ("পঞ্চগড়", "rangpur", ("panchagar",)),
    "Nilphamari": ("নীলফামারী", "rangpur", ("saidpur",)),
    "Lalmonirhat": ("লালমনিরহাট", "rangpur", ()),
    "Kurigram": ("কুড়িগ্রাম", "rangpur", ()),
    "Gaibandha": ("গাইবান্ধা", "rangpur", ()),
    # Mymensingh division
    "Mymensingh": ("ময়মনসিংহ", "mymensingh", ("mymensing", "moymonsingh")),
    "Jamalpur": ("জামালপুর", "mymensingh", ()),
    "Sherpur": ("শেরপুর", "mymensingh", ()),
    "Netrokona": ("নেত্রকোনা", "mymensingh", ("netrakona",)),
}

# Areas of Dhaka and the towns next to it -> nearest of the five Dhaka centres.
DHAKA_AREAS: dict[str, tuple[str, str]] = {
    # area: (Bangla name, centre key)
    "Gulshan": ("গুলশান", "gulshan"),
    "Banani": ("বনানী", "gulshan"),
    "Baridhara": ("বারিধারা", "gulshan"),
    "Bashundhara": ("বসুন্ধরা", "gulshan"),
    "Badda": ("বাড্ডা", "gulshan"),
    "Rampura": ("রামপুরা", "gulshan"),
    "Banasree": ("বনশ্রী", "gulshan"),
    "Aftabnagar": ("আফতাবনগর", "gulshan"),
    "Mohakhali": ("মহাখালী", "gulshan"),
    "Niketan": ("নিকেতন", "gulshan"),
    "Tejgaon": ("তেজগাঁও", "gulshan"),
    "Khilkhet": ("খিলক্ষেত", "gulshan"),
    "Kuril": ("কুড়িল", "gulshan"),
    "Vatara": ("ভাটারা", "gulshan"),
    "Uttara": ("উত্তরা", "uttara"),
    "Airport": ("এয়ারপোর্ট", "uttara"),
    "Dakshinkhan": ("দক্ষিণখান", "uttara"),
    "Uttarkhan": ("উত্তরখান", "uttara"),
    "Abdullahpur": ("আব্দুল্লাহপুর", "uttara"),
    "Tongi": ("টঙ্গী", "uttara"),
    "Turag": ("তুরাগ", "uttara"),
    "Ashkona": ("আশকোনা", "uttara"),
    "Mirpur": ("মিরপুর", "mirpur"),
    "Pallabi": ("পল্লবী", "mirpur"),
    "Kafrul": ("কাফরুল", "mirpur"),
    "Kazipara": ("কাজীপাড়া", "mirpur"),
    "Shewrapara": ("শেওড়াপাড়া", "mirpur"),
    "Agargaon": ("আগারগাঁও", "mirpur"),
    "Shyamoli": ("শ্যামলী", "mirpur"),
    "Adabor": ("আদাবর", "mirpur"),
    "Gabtoli": ("গাবতলী", "mirpur"),
    "Cantonment": ("ক্যান্টনমেন্ট", "mirpur"),
    "Savar": ("সাভার", "mirpur"),
    "Ashulia": ("আশুলিয়া", "mirpur"),
    "Hemayetpur": ("হেমায়েতপুর", "mirpur"),
    "Aminbazar": ("আমিনবাজার", "mirpur"),
    "Dhanmondi": ("ধানমন্ডি", "dhanmondi"),
    "Mohammadpur": ("মোহাম্মদপুর", "dhanmondi"),
    "Lalmatia": ("লালমাটিয়া", "dhanmondi"),
    "Kalabagan": ("কলাবাগান", "dhanmondi"),
    "Jigatola": ("জিগাতলা", "dhanmondi"),
    "Hazaribagh": ("হাজারীবাগ", "dhanmondi"),
    "Rayer Bazar": ("রায়েরবাজার", "dhanmondi"),
    "Farmgate": ("ফার্মগেট", "dhanmondi"),
    "Karwan Bazar": ("কারওয়ান বাজার", "dhanmondi"),
    "Panthapath": ("পান্থপথ", "dhanmondi"),
    "Green Road": ("গ্রিন রোড", "dhanmondi"),
    "New Market": ("নিউ মার্কেট", "dhanmondi"),
    "Elephant Road": ("এলিফ্যান্ট রোড", "dhanmondi"),
    "Science Lab": ("সায়েন্স ল্যাব", "dhanmondi"),
    "Azimpur": ("আজিমপুর", "dhanmondi"),
    "Lalbagh": ("লালবাগ", "dhanmondi"),
    "Kamrangirchar": ("কামরাঙ্গীরচর", "dhanmondi"),
    "Keraniganj": ("কেরানীগঞ্জ", "dhanmondi"),
    "Motijheel": ("মতিঝিল", "motijheel"),
    "Dilkusha": ("দিলকুশা", "motijheel"),
    "Paltan": ("পল্টন", "motijheel"),
    "Ramna": ("রমনা", "motijheel"),
    "Shahbagh": ("শাহবাগ", "motijheel"),
    "Segunbagicha": ("সেগুনবাগিচা", "motijheel"),
    "Kakrail": ("কাকরাইল", "motijheel"),
    "Shantinagar": ("শান্তিনগর", "motijheel"),
    "Malibagh": ("মালিবাগ", "motijheel"),
    "Moghbazar": ("মগবাজার", "motijheel"),
    "Khilgaon": ("খিলগাঁও", "motijheel"),
    "Basabo": ("বাসাবো", "motijheel"),
    "Sabujbagh": ("সবুজবাগ", "motijheel"),
    "Mugda": ("মুগদা", "motijheel"),
    "Jatrabari": ("যাত্রাবাড়ী", "motijheel"),
    "Sayedabad": ("সায়েদাবাদ", "motijheel"),
    "Demra": ("ডেমরা", "motijheel"),
    "Gulistan": ("গুলিস্তান", "motijheel"),
    "Wari": ("ওয়ারী", "motijheel"),
    "Old Dhaka": ("পুরান ঢাকা", "motijheel"),
    "Sadarghat": ("সদরঘাট", "motijheel"),
    "Sutrapur": ("সূত্রাপুর", "motijheel"),
    "Chawkbazar": ("চকবাজার", "motijheel"),
    "Fatullah": ("ফতুল্লা", "motijheel"),
    "Siddhirganj": ("সিদ্ধিরগঞ্জ", "motijheel"),
}

# The few areas above that lie outside Dhaka district.
_AREA_DISTRICT = {"Tongi": "Gazipur", "Fatullah": "Narayanganj", "Siddhirganj": "Narayanganj"}

# Words around a place name that don't change the place ("Gazipur district",
# "সাভার এলাকা").
_FILLER_WORDS = {
    "district", "zila", "zilla", "sadar", "city", "town", "area", "thana", "upazila",
    "division", "জেলা", "সদর", "শহর", "থানা", "উপজেলা", "এলাকা", "বিভাগ",
}


@dataclass(frozen=True)
class Match:
    """Where `place` resolved to: a district or a Dhaka area, and its centre
    (None for "Dhaka" alone, which has five)."""

    place: str  # canonical English name
    district: str
    centre: CareCentre | None


def _key(text: str) -> str:
    text = unicodedata.normalize("NFC", text).lower()
    text = re.sub(r"['’`]", "", text)  # "Cox's" -> "coxs"
    text = re.sub(r"[^\w\s]", " ", text)
    text = re.sub(r"\d+", " ", text)  # "Mirpur 10", "Sector 7"
    return " ".join(w for w in text.split() if w not in _FILLER_WORDS)


def _build_index() -> dict[str, Match]:
    index: dict[str, Match] = {}
    for name, (bn, centre_key, aliases) in DISTRICTS.items():
        match = Match(name, name, CENTRES[centre_key] if centre_key else None)
        for spelling in (name, bn, *aliases):
            index[_key(spelling)] = match
    for name, (bn, centre_key) in DHAKA_AREAS.items():
        match = Match(name, _AREA_DISTRICT.get(name, "Dhaka"), CENTRES[centre_key])
        for spelling in (name, bn):
            index.setdefault(_key(spelling), match)
    return index


_INDEX = _build_index()


def resolve(place: str) -> Match | None:
    """The district or Dhaka area `place` names (English, Bangla or a close
    misspelling), or None if it isn't one."""
    key = _key(place)
    if not key:
        return None
    if key in _INDEX:
        return _INDEX[key]
    close = difflib.get_close_matches(key, _INDEX.keys(), n=1, cutoff=0.8)
    return _INDEX[close[0]] if close else None


def describe(centre: CareCentre) -> str:
    return f"{centre.name}, {centre.address} (in Bangla: {centre.bn}), {centre.hours}"


def _dhaka_list() -> str:
    return "; ".join(describe(CENTRES[k]) for k in _DHAKA_CENTRES)


def nearest_text(match: Match) -> str:
    """The tool's answer for a resolved place."""
    if match.centre is None:
        return (
            f"Care centres in Dhaka: {_dhaka_list()}. Ask which area of Dhaka they are in "
            "to give the nearest one."
        )
    text = f"Nearest care centre to {match.place}: {describe(match.centre)}."
    if match.centre.district != match.district:
        text += (
            f" There is no care centre in {match.district} itself; authorised retail points "
            "there sell new SIMs and recharge and can replace a lost SIM."
        )
    return text


def snapshot_line(district: str) -> str | None:
    """The account snapshot's care-centre line for the customer's district on
    file, or None when it isn't a district we know."""
    match = resolve(district)
    if match is None:
        return None
    if match.centre is None:
        names = ", ".join(CENTRES[k].name for k in _DHAKA_CENTRES)
        return (
            f"Care centres in their district ({match.place}): {names}; "
            "for the nearest, ask which area and call find_care_centre."
        )
    return f"Nearest care centre to their district: {describe(match.centre)}."
