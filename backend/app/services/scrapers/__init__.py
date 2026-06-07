from app.services.scrapers.hotukdeals import HotUKDealsScraper
from app.services.scrapers.argos import ArgosScraper
from app.services.scrapers.currys import CurrysScraper
from app.services.scrapers.smyths import SmythsScraper
from app.services.scrapers.very import VeryScraper
from app.services.scrapers.lego import LegoScraper
from app.services.scrapers.box import BoxScraper
from app.services.scrapers.ebuyer import EbuyerScraper
from app.services.scrapers.boots import BootsScraper
from app.services.scrapers.costco import CostcoScraper
from app.services.scrapers.tkmaxx import TKMaxxScraper
from app.services.scrapers.bm import BMScraper
from app.services.scrapers.homebargains import HomeBargainsScraper

SCRAPER_REGISTRY = {
    "hotukdeals": HotUKDealsScraper,
    "argos": ArgosScraper,
    "currys": CurrysScraper,
    "smyths": SmythsScraper,
    "very": VeryScraper,
    "lego_shop": LegoScraper,
    "box": BoxScraper,
    "ebuyer": EbuyerScraper,
    "boots": BootsScraper,
    "costco": CostcoScraper,
    "tkmaxx": TKMaxxScraper,
    "bm": BMScraper,
    "homebargains": HomeBargainsScraper,
}

__all__ = [
    "HotUKDealsScraper",
    "ArgosScraper",
    "CurrysScraper",
    "SmythsScraper",
    "VeryScraper",
    "LegoScraper",
    "BoxScraper",
    "EbuyerScraper",
    "BootsScraper",
    "CostcoScraper",
    "TKMaxxScraper",
    "BMScraper",
    "HomeBargainsScraper",
    "SCRAPER_REGISTRY",
]
