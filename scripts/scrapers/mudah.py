"""Mudah.my scraper — DISABLED by design, not just unimplemented.

Mudah.my's robots.txt (checked 2026-08-27) contains an explicit
human-readable policy statement above the machine-parseable rules:

    "It is expressly forbidden to use spiders or other automated methods
    to access mudah.my. Only if mudah.my has given special permit such
    access is allowed."

The `Disallow` rules themselves are narrow (query params, /redir, etc.) and
technically leave the listing search paths (/list, /li) fetchable, but the
site operator has stated a blanket no-automation policy that goes beyond
normal crawl-control. Per RentSafe MY's scraping etiquette requirements
(robots.txt compliance is a hard gate, not just a path-level check), this
scraper does not perform any HTTP requests.

If the project later obtains an explicit written permit from mudah.my, the
`allowed` flag below can be flipped and a real implementation (following the
same NextDataScraper / BaseScraper pattern as iproperty.py / propertyguru.py)
can be added.
"""
from .base import BaseScraper


class MudahScraper(BaseScraper):
    site_name = "mudah"
    allowed = False

    def build_search_url(self, page_number):
        raise NotImplementedError("mudah.py is disabled — see module docstring")

    def parse_listing_urls(self, html, page_url):
        raise NotImplementedError("mudah.py is disabled — see module docstring")

    def parse_listing(self, html, url):
        raise NotImplementedError("mudah.py is disabled — see module docstring")

    def scrape(self, max_pages=5):
        self.log.error(
            "mudah.py is disabled: mudah.my's robots.txt expressly forbids "
            "automated access without a special permit. No requests were made. "
            "See the module docstring for details."
        )
        return []
