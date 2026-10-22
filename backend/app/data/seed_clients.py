from datetime import date, timedelta

from sqlalchemy.orm import Session

from app.models.client import Client, LeadStatus, RentOrBuy
from app.services.phone_numbers import normalize_bd_mobile

SAMPLE_CLIENTS = [
    dict(
        full_name="Tanvir Ahmed",
        phone="+880-1711-234567",
        email="tanvir.ahmed@example.com",
        lead_source="web_form",
        lead_status=LeadStatus.new,
        budget_min=25000,
        budget_max=35000,
        preferred_location="Uttara",
        preferred_property_type="apartment",
        bedrooms_wanted=2,
        bathrooms_wanted=2,
        move_in_date=date.today() + timedelta(days=14),
        rent_or_buy=RentOrBuy.rent,
        notes="Prefers a flat with a lift and generator backup.",
    ),
    dict(
        full_name="Farzana Rahman",
        phone="+880-1912-345678",
        email="farzana.rahman@example.com",
        lead_source="referral",
        lead_status=LeadStatus.contacted,
        budget_min=8000000,
        budget_max=12000000,
        preferred_location="Dhanmondi",
        preferred_property_type="apartment",
        bedrooms_wanted=3,
        bathrooms_wanted=3,
        move_in_date=None,
        rent_or_buy=RentOrBuy.buy,
        notes="Relocating from Chattogram for work, flexible on move-in timing.",
    ),
    dict(
        full_name="Rakibul Islam",
        phone="+880-1611-456789",
        email="rakibul.islam@example.com",
        lead_source="cold_import",
        lead_status=LeadStatus.new,
        budget_min=12000,
        budget_max=18000,
        preferred_location="Mirpur",
        preferred_property_type="apartment",
        bedrooms_wanted=2,
        bathrooms_wanted=1,
        move_in_date=date.today() + timedelta(days=30),
        rent_or_buy=RentOrBuy.rent,
        notes="First-time renter, price sensitive.",
    ),
    dict(
        full_name="Nusrat Jahan",
        phone="+880-1755-112233",
        email="nusrat.jahan@example.com",
        lead_source="web_form",
        lead_status=LeadStatus.qualified,
        budget_min=45000,
        budget_max=100000,
        preferred_location="Gulshan",
        preferred_property_type="apartment",
        bedrooms_wanted=3,
        bathrooms_wanted=3,
        move_in_date=date.today() + timedelta(days=21),
        rent_or_buy=RentOrBuy.rent,
        notes="Wants a serviced flat close to her office in the diplomatic zone.",
    ),
    dict(
        full_name="Shafiqul Alam",
        phone="+880-1811-223344",
        email="shafiqul.alam@example.com",
        lead_source="referral",
        lead_status=LeadStatus.qualified,
        budget_min=30000000,
        budget_max=50000000,
        preferred_location="Banani",
        preferred_property_type="apartment",
        bedrooms_wanted=5,
        bathrooms_wanted=5,
        move_in_date=None,
        rent_or_buy=RentOrBuy.buy,
        notes="Interested in the Banani DOHS house listing; wants to see it before deciding.",
    ),
    dict(
        full_name="Sabrina Kabir",
        phone="+880-1922-334455",
        email="sabrina.kabir@example.com",
        lead_source="cold_import",
        lead_status=LeadStatus.contacted,
        budget_min=18000,
        budget_max=32000,
        preferred_location="Mohammadpur",
        preferred_property_type="apartment",
        bedrooms_wanted=2,
        bathrooms_wanted=2,
        move_in_date=date.today() + timedelta(days=10),
        rent_or_buy=RentOrBuy.rent,
        notes="Young couple, wants pet-friendly building.",
    ),
    dict(
        full_name="Imran Hossain",
        phone="+880-1611-556677",
        email="imran.hossain@example.com",
        lead_source="web_form",
        lead_status=LeadStatus.new,
        budget_min=6000000,
        budget_max=9500000,
        preferred_location="Farmgate",
        preferred_property_type="apartment",
        bedrooms_wanted=3,
        bathrooms_wanted=2,
        move_in_date=None,
        rent_or_buy=RentOrBuy.buy,
        notes="Looking to buy close to workplace, open on exact neighborhood nearby.",
    ),
    dict(
        full_name="Tahmina Akter",
        phone="+880-1711-667788",
        email="tahmina.akter@example.com",
        lead_source="referral",
        lead_status=LeadStatus.new,
        budget_min=20000,
        budget_max=48000,
        preferred_location="Bashundhara R/A",
        preferred_property_type="apartment",
        bedrooms_wanted=3,
        bathrooms_wanted=3,
        move_in_date=date.today() + timedelta(days=45),
        rent_or_buy=RentOrBuy.rent,
        notes="Relocating for a new job at a nearby university.",
    ),
    dict(
        full_name="Kamrul Hasan",
        phone="+880-1911-778899",
        email="kamrul.hasan@example.com",
        lead_source="cold_import",
        lead_status=LeadStatus.lost,
        budget_min=30000000,
        budget_max=40000000,
        preferred_location="Baridhara",
        preferred_property_type="apartment",
        bedrooms_wanted=4,
        bathrooms_wanted=3,
        move_in_date=None,
        rent_or_buy=RentOrBuy.buy,
        notes="Went with a competing agency; keep for a future re-engagement campaign.",
    ),
    dict(
        full_name="Ruma Begum",
        phone="+880-1811-889900",
        email="ruma.begum@example.com",
        lead_source="web_form",
        lead_status=LeadStatus.contacted,
        budget_min=8000,
        budget_max=13000,
        preferred_location="Tongi",
        preferred_property_type="apartment",
        bedrooms_wanted=1,
        bathrooms_wanted=1,
        move_in_date=date.today() + timedelta(days=5),
        rent_or_buy=RentOrBuy.rent,
        notes="Single tenant, needs something available immediately.",
    ),
    dict(
        full_name="Arif Chowdhury",
        phone="+880-1711-990011",
        email="arif.chowdhury@example.com",
        lead_source="referral",
        lead_status=LeadStatus.qualified,
        budget_min=10000000,
        budget_max=17000000,
        preferred_location="Dhanmondi",
        preferred_property_type="apartment",
        bedrooms_wanted=3,
        bathrooms_wanted=3,
        move_in_date=None,
        rent_or_buy=RentOrBuy.buy,
        notes="Comparing a few Dhanmondi blocks before deciding.",
    ),
    dict(
        full_name="Mehnaz Sultana",
        phone="+880-1611-001122",
        email="mehnaz.sultana@example.com",
        lead_source="cold_import",
        lead_status=LeadStatus.new,
        budget_min=10000,
        budget_max=18000,
        preferred_location="Savar Bazar",
        preferred_property_type="apartment",
        bedrooms_wanted=2,
        bathrooms_wanted=1,
        move_in_date=date.today() + timedelta(days=20),
        rent_or_buy=RentOrBuy.rent,
        notes="Works near Savar, wants to cut down commute time.",
    ),
    dict(
        full_name="Zahidul Karim",
        phone="+880-1911-112200",
        email="zahidul.karim@example.com",
        lead_source="web_form",
        lead_status=LeadStatus.contacted,
        budget_min=8000000,
        budget_max=8600000,
        preferred_location="Narayanganj",
        preferred_property_type="duplex",
        bedrooms_wanted=4,
        bathrooms_wanted=3,
        move_in_date=None,
        rent_or_buy=RentOrBuy.buy,
        notes="Considering the Chashara duplex for a joint family; wants to visit with his parents.",
    ),
    dict(
        full_name="Farhana Yasmin",
        phone="+880-1755-223311",
        email="farhana.yasmin@example.com",
        lead_source="referral",
        lead_status=LeadStatus.new,
        budget_min=None,
        budget_max=None,
        preferred_location="Khilgaon",
        preferred_property_type="apartment",
        bedrooms_wanted=None,
        bathrooms_wanted=None,
        move_in_date=None,
        rent_or_buy=RentOrBuy.undecided,
        notes="Early inquiry, hasn't settled on budget or bedroom count yet.",
    ),
]


# Earlier seed values that left a lead with nothing to offer on a call (no
# listing in their area fits the budget/type) or with a file contradicting
# itself. Applied to a seeded row only while it still holds exactly the old
# values, so an admin's edits are never overwritten.
_CORRECTIONS: list[tuple[str, dict, dict]] = [
    (
        "+880-1811-223344",  # Shafiqul Alam: a 5-bed Banani house costs crores, not lakhs
        dict(budget_min=3000000, budget_max=5000000),
        dict(budget_min=30000000, budget_max=50000000),
    ),
    (
        "+880-1911-778899",  # Kamrul Hasan: no 4-bed Baridhara house under 2 crore
        dict(budget_min=15000000, budget_max=20000000),
        dict(budget_min=30000000, budget_max=40000000),
    ),
    (
        "+880-1611-001122",  # Mehnaz Sultana: no 2-bed Savar flat under 12k
        dict(budget_min=7000, budget_max=12000),
        dict(budget_min=10000, budget_max=18000),
    ),
    (
        "+880-1811-223344",  # Shafiqul Alam: "booked" with no booking on file
        dict(lead_status=LeadStatus.booked, notes="Viewing booked for the Banani DOHS house listing."),
        dict(
            lead_status=LeadStatus.qualified,
            notes="Interested in the Banani DOHS house listing; wants to see it before deciding.",
        ),
    ),
    (
        "+880-1911-112200",  # Zahidul Karim: "closed" on the duplex a call would pitch
        dict(lead_status=LeadStatus.closed, notes="Closed on the Chashara duplex."),
        dict(
            lead_status=LeadStatus.contacted,
            notes="Considering the Chashara duplex for a joint family; wants to visit with his parents.",
        ),
    ),
]


def _matches(client: Client, values: dict) -> bool:
    for field, value in values.items():
        current = getattr(client, field)
        if isinstance(value, (int, float)) and current is not None:
            current = float(current)
        if current != value:
            return False
    return True


def _phone_key(phone: str) -> str:
    try:
        return normalize_bd_mobile(phone)
    except ValueError:
        return phone


def seed(db: Session) -> int:
    """Non-destructive upsert, safe to run on every launch (run-local.bat does).

    Inserts sample leads whose phone number isn't in the table yet, and applies
    _CORRECTIONS to seeded rows that still hold the old values. Returns the
    number of rows inserted."""
    by_phone = {
        _phone_key(c.phone): c for c in db.query(Client).filter(Client.phone.is_not(None))
    }
    inserted = 0
    for data in SAMPLE_CLIENTS:
        if _phone_key(data["phone"]) not in by_phone:
            db.add(Client(**data))
            inserted += 1
    for phone, old, new in _CORRECTIONS:
        client = by_phone.get(_phone_key(phone))
        if client is not None and _matches(client, old):
            for field, value in new.items():
                setattr(client, field, value)
    db.commit()
    return inserted
