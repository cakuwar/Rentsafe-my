"""iProperty.com.my scraper.

robots.txt (checked 2026-08-27) disallows /cdn-cgi/, /international,
/useracc, /l/*, /*/schema.json and the literal pagination placeholder
"/*/{{page}}" — it does not disallow /property-for-rent or its numbered
pagination (e.g. /property-for-rent/2), which is what this scraper uses.

See base.NextDataScraper for the shared parsing logic (both iProperty and
PropertyGuru are the same underlying platform and embed identical
`__NEXT_DATA__` JSON on their search-results pages).
"""
from .base import NextDataScraper


class IPropertyScraper(NextDataScraper):
    site_name = "iproperty"
    site_key = "iproperty"
    search_folder = "/property-for-rent"
