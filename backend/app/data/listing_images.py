"""Curated Unsplash photos for the seeded listings.

Fixed photo IDs (every URL was checked to return HTTP 200 when added). Each
listing stores `image_url` as its cover and `images` as its ordered gallery,
cover first.
"""


def unsplash(photo_id: str) -> str:
    return f"https://images.unsplash.com/photo-{photo_id}?auto=format&fit=crop&w=1200&q=80"


BUILDINGS = [unsplash(i) for i in (
    "1545324418-cc1a3fa10c00",
    "1460317442991-0ec209397118",
    "1515263487990-61b07816b324",
    "1551361415-69c87624334f",
    "1574362848149-11496d93a7c7",
    "1594484208280-efa00f96fc21",
    "1580041065738-e72023775cdc",
)]

LIVING_ROOMS = [unsplash(i) for i in (
    "1502672260266-1c1ef2d93688",
    "1522708323590-d24dbb6b0267",
    "1493809842364-78817add7ffb",
    "1560448204-e02f11c3d0e2",
    "1484101403633-562f891dc89a",
    "1501183638710-841dd1904471",
    "1505691938895-1758d7feb511",
    "1536376072261-38c75010e6c9",
    "1554995207-c18c203602cb",
    "1560185007-cde436f6a4d0",
    "1586023492125-27b2c045efd7",
    "1600210492486-724fe5c67fb0",
    "1600607687939-ce8a6c25118c",
)]

# Double-height rooms and open staircases: duplexes.
SPLIT_LEVEL = [unsplash(i) for i in (
    "1502005229762-cf1b2da7c5d6",
    "1600566753086-00f18fb6b3ea",
    "1600573472550-8090b5e0745e",
    "1505873242700-f289a29e1e0f",
    "1503174971373-b1f69850bded",
)]

KITCHENS = [unsplash(i) for i in (
    "1484154218962-a197022b5858",
    "1507089947368-19c1da9775ae",
    "1588854337236-6889d631faa8",
)]

BEDROOMS = [unsplash(i) for i in (
    "1540518614846-7eded433c457",
    "1512918728675-ed5a9ecdebfd",
    "1560185893-a55cbc8c57e8",
    "1595526114035-0d45ed16cfbf",
    "1600607687644-c7171b42498f",
    "1616594039964-ae9021a400a0",
    "1631049307264-da0ec9d70304",
)]

BATHROOMS = [unsplash(i) for i in (
    "1552321554-5fefe8c9ef14",
    "1600566752355-35792bedcfea",
    "1620626011761-996317b8d101",
)]

DINING = [unsplash("1617806118233-18e1de247200")]

OFFICES = [unsplash(i) for i in (
    "1497366216548-37526070297c",
    "1497366811353-6870744d04b2",
    "1524758631624-e2822e304c36",
    "1497215842964-222b430dc094",
)]

OFFICE_TOWERS = [unsplash(i) for i in (
    "1486406146926-c627a92ad1ab",
    "1554469384-e58fac16e23a",
)]

SHOPS = [unsplash("1441986300917-64674bd600d8")]

LAND = [unsplash(i) for i in (
    "1500382017468-9049fed747ef",
    "1592595896551-12b371d546d5",
    "1465146344425-f00d5f5c8f07",
)]

HOUSES = [unsplash(i) for i in (
    "1600596542815-ffad4c1539a9",
    "1600585154340-be6161a56a0c",
    "1512917774080-9991f1c4c750",
    "1580587771525-78b9dba3b914",
    "1600047509807-ba8f99d2cdde",
    "1600566753190-17f0baa2a6c3",
    "1600585154526-990dced4db0d",
    "1600607688969-a5bfcd646154",
    "1613490493576-7fde63acd811",
    "1613977257363-707ba9348227",
    "1591474200742-8e512e6f98f8",
    "1494526585095-c41746248156",
    "1523217582562-09d0def993a6",
    "1568605114967-8130f3a36994",
    "1570129477492-45c003edd2be",
    "1583608205776-bfd35f0d9f83",
    "1605276374104-dee2a0ed3cd6",
    "1625602812206-5ec545ca1231",
    "1505843513577-22bb7d21e455",
)]

TOWNHOUSES = [unsplash("1567496898669-ee935f5f647a")]

# Cover pool for the generated apartment rows: building exteriors and living rooms.
APARTMENT_COVERS = BUILDINGS + LIVING_ROOMS


def all_urls() -> set[str]:
    return set(
        BUILDINGS + LIVING_ROOMS + SPLIT_LEVEL + KITCHENS + BEDROOMS + BATHROOMS + DINING
        + OFFICES + OFFICE_TOWERS + SHOPS + LAND + HOUSES + TOWNHOUSES
    )
