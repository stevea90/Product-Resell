"""
Shared utilities for all retailer scrapers.

detect_category()  — keyword-based category assignment covering all FBA niches
parse_gbp_price()  — extract a float GBP price from any price string
"""
import re
from typing import Optional

# Order matters: more specific categories checked before general ones.
# Each tuple is (category_name, list_of_keywords).
_CATEGORY_RULES: list[tuple[str, list[str]]] = [
    ("lego", [
        "lego", "lego technic", "lego star wars", "lego city",
        "lego creator", "lego friends", "lego harry potter",
        "lego minecraft", "lego marvel",
    ]),
    ("gaming", [
        "playstation", "ps5", "ps4", "xbox", "nintendo switch",
        "nintendo 3ds", "game ", "gaming", "steam deck", "controller",
        "console", "pokemon", "zelda", "mario", "video game",
        "pc gaming", "graphics card", "gpu", "headset gaming",
    ]),
    ("toys", [
        "toy", "nerf", "barbie", "hot wheels", "action figure",
        "playset", "funko", "plush", "doll", "teddy", "puzzle",
        "board game", "jigsaw", "card game", "magic the gathering",
        "yu-gi-oh", "pokemon card", "trading card",
    ]),
    ("electronics", [
        "laptop", "tablet", "ipad", "iphone", "samsung galaxy",
        "tv", "television", "monitor", "headphone", "earbuds",
        "airpods", "speaker", "camera", "drone", "apple watch",
        "smart watch", "smartwatch", "android", "macbook", "pc",
        "desktop computer", "printer", "router", "smart home",
        "alexa", "google home", "echo dot", "kindle",
        "projector", "dash cam", "dashcam", "power bank", "charger",
        "e-reader", "hard drive", "ssd", "usb hub", "graphics card",
    ]),
    ("home", [
        "sofa", "mattress", "bedding", "duvet", "pillow", "curtain",
        "rug", "lamp", "chair", "table", "shelf", "wardrobe",
        "vacuum", "iron", "kettle", "toaster", "microwave",
        "air fryer", "coffee maker", "coffee machine", "blender",
        "food processor", "dishwasher", "washing machine",
        "fridge", "freezer", "oven", "hob", "cookware",
        "pan", "pot ", "knife", "cutlery", "crockery",
        "storage", "organisation", "candle", "diffuser",
    ]),
    ("beauty", [
        "perfume", "cologne", "aftershave", "skincare", "moisturiser",
        "serum", "foundation", "mascara", "lipstick", "eyeshadow",
        "makeup", "hair dryer", "straightener", "curler",
        "electric toothbrush", "shaver", "razor", "trimmer",
        "nail", "fragrance", "deodorant", "shower gel",
        "shampoo", "conditioner", "face mask", "sunscreen",
    ]),
    ("sports", [
        "trainers", "running shoes", "gym", "dumbbell", "barbell",
        "yoga mat", "treadmill", "bike", "cycling", "football",
        "tennis", "golf", "swimming", "wetsuit", "camping",
        "hiking", "walking boots", "rucksack", "backpack outdoor",
        "kayak", "paddle", "ski", "snowboard", "fitness",
        "protein", "supplement", "whey", "creatine",
    ]),
    ("fashion", [
        "jacket", "coat", "hoodie", "jumper", "sweater",
        "jeans", "trousers", "dress", "skirt", "shirt",
        "trainers", "boots", "sandals", "handbag", "wallet",
        "watch ", "sunglasses", "scarf", "gloves", "hat",
        "underwear", "socks", "leggings", "activewear",
    ]),
    ("garden", [
        "garden", "lawn mower", "lawnmower", "strimmer",
        "pressure washer", "garden furniture", "bbq",
        "barbecue", "plant pot", "compost", "fertiliser",
        "shed", "greenhouse", "patio", "decking", "fence",
        "hedge trimmer", "leaf blower", "spade", "trowel",
    ]),
    ("health", [
        "vitamin", "supplement", "omega 3", "cod liver",
        "blood pressure", "thermometer", "first aid",
        "hearing aid", "mobility", "crutch", "wheelchair",
        "tens machine", "massage", "pain relief",
    ]),
    ("pets", [
        "dog food", "cat food", "pet food", "dog bed",
        "cat bed", "pet carrier", "dog lead", "collar",
        "dog toy", "cat toy", "aquarium", "fish tank",
        "hamster", "rabbit", "bird cage", "litter",
    ]),
    ("books", [
        "book", "novel", "paperback", "hardback", "hardcover",
        "audiobook", "kindle edition", "graphic novel",
        "cookbook", "textbook",
    ]),
]

# Build a flat lookup: keyword → category (longest keyword wins via sorting)
_KEYWORD_TO_CATEGORY: list[tuple[str, str]] = []
for _cat, _kws in _CATEGORY_RULES:
    for _kw in _kws:
        _KEYWORD_TO_CATEGORY.append((_kw, _cat))
# Sort longest first so "samsung galaxy" matches before "samsung"
_KEYWORD_TO_CATEGORY.sort(key=lambda x: -len(x[0]))


def detect_category(title: str) -> str:
    """Return the best-matching category for a product title, or 'other'."""
    lower = title.lower()
    for keyword, category in _KEYWORD_TO_CATEGORY:
        if keyword in lower:
            return category
    return "other"


_PRICE_RE = re.compile(r"£\s*([\d,]+\.?\d*)")


def parse_gbp_price(text: Optional[str]) -> Optional[float]:
    """Extract the first GBP price from a string like '£12.99' or 'Was £24.99'."""
    if not text:
        return None
    match = _PRICE_RE.search(str(text))
    if match:
        try:
            return float(match.group(1).replace(",", ""))
        except ValueError:
            pass
    # Try bare numeric if already a number
    if isinstance(text, (int, float)):
        return float(text)
    return None
