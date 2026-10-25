"""PropertyGuru.com.my scraper.

robots.txt (checked 2026-08-27) disallows a long list of ajax/utility/print
paths plus /l/* and query strings with `&sort=`, but does not disallow
/property-for-rent or its numbered pagination (e.g. /property-for-rent/2),
which is what this scraper uses.

See base.NextDataScraper for the shared parsing logic (both PropertyGuru and
iProperty are the same underlying platform and embed identical
`__NEXT_DATA__` JSON on their search-results pages). One difference handled
there: PropertyGuru's listing `url` field is already absolute, whereas
iProperty's is relative.
"""
from .base import NextDataScraper


class PropertyGuruScraper(NextDataScraper):
    site_name = "propertyguru"
    site_key = "propertyguru"
    search_folder = "/property-for-rent"
