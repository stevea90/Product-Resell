from app.services.scrapers.hotukdeals import HotUKDealsScraper

SCRAPER_REGISTRY = {
    "hotukdeals": HotUKDealsScraper,
}

__all__ = ["HotUKDealsScraper", "SCRAPER_REGISTRY"]
