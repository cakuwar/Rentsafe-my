"""Shared base class for all site scrapers.

Handles the "etiquette" requirements that every scraper must follow:
robots.txt compliance, randomised rate-limited delays, retry with backoff,
raw HTML caching (so re-runs don't re-hit the site), and rotating UAs.

Subclasses implement `parse_listing_urls(html)` and `parse_listing(html, url)`;
everything else (fetching, caching, politeness) lives here.
"""
import hashlib
import logging
import os
import random
import time
import urllib.robotparser
from urllib.parse import urlparse

import requests
from tenacity import (
    retry,
    retry_if_exception_type,
    stop_after_attempt,
    wait_exponential,
)

from . import config, next_data
from .next_data import NEXT_DATA_RE

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(name)s: %(message)s")


class FetchBlocked(Exception):
    """Raised when a page is disallowed by robots.txt or repeatedly blocked (403/429)."""


class BaseScraper:
    site_name = "base"  # overridden by subclasses

    def __init__(self, out_dir=None, use_playwright=False):
        self.log = logging.getLogger(self.site_name)
        self.session = requests.Session()
        self.out_dir = out_dir or config.DATA_RAW_BASELINE
        self.use_playwright = use_playwright
        self._robots_cache = {}
        self._last_request_at = 0.0
        os.makedirs(self.out_dir, exist_ok=True)

    # -- robots.txt -----------------------------------------------------
    def _robots_for(self, url):
        # NOTE: we deliberately don't use RobotFileParser.read() here — it
        # fetches robots.txt itself with a bare "Python-urllib/x.y" UA, which
        # several of these sites' anti-bot fronts 403 outright. robotparser
        # then (per its own fail-safe) treats a 403 as "disallow everything",
        # which would make every page look blocked even when the actual
        # robots.txt is permissive. So we fetch it ourselves with the same
        # browser-like UA as everything else, and hand the text to parse().
        parsed = urlparse(url)
        origin = f"{parsed.scheme}://{parsed.netloc}"
        if origin not in self._robots_cache:
            rp = urllib.robotparser.RobotFileParser()
            try:
                resp = self.session.get(
                    f"{origin}/robots.txt",
                    headers={"User-Agent": random.choice(config.USER_AGENTS)},
                    timeout=config.REQUEST_TIMEOUT_SECONDS,
                )
                if resp.status_code == 200:
                    rp.parse(resp.text.splitlines())
                elif 400 <= resp.status_code < 500:
                    rp.allow_all = True  # no robots.txt => nothing disallowed
                else:
                    self.log.warning(
                        "robots.txt fetch for %s returned %s; assuming disallowed",
                        origin, resp.status_code,
                    )
                    rp = None
            except requests.RequestException as exc:
                self.log.warning("could not read robots.txt for %s (%s); assuming disallowed", origin, exc)
                rp = None
            self._robots_cache[origin] = rp
        return self._robots_cache[origin]

    def is_allowed(self, url):
        rp = self._robots_for(url)
        if rp is None:
            return False
        ua = random.choice(config.USER_AGENTS)
        try:
            return rp.can_fetch(ua, url)
        except Exception:
            return False

    # -- caching ----------------------------------------------------------
    def _cache_path(self, url):
        h = hashlib.sha256(url.encode("utf-8")).hexdigest()[:24]
        return os.path.join(config.CACHE_DIR, f"{h}.html")

    def _read_cache(self, url):
        path = self._cache_path(url)
        if os.path.exists(path):
            with open(path, encoding="utf-8") as f:
                return f.read()
        return None

    def _write_cache(self, url, html):
        with open(self._cache_path(url), "w", encoding="utf-8") as f:
            f.write(html)

    # -- politeness ---------------------------------------------------------
    def _throttle(self):
        elapsed = time.time() - self._last_request_at
        delay = random.uniform(*config.REQUEST_DELAY_RANGE_SECONDS)
        if elapsed < delay:
            time.sleep(delay - elapsed)
        self._last_request_at = time.time()

    @retry(
        reraise=True,
        stop=stop_after_attempt(config.MAX_RETRIES),
        wait=wait_exponential(multiplier=config.RETRY_BACKOFF_SECONDS),
        retry=retry_if_exception_type(requests.RequestException),
    )
    def _get(self, url):
        headers = {
            "User-Agent": random.choice(config.USER_AGENTS),
            "Accept-Language": "en-MY,en;q=0.9,ms;q=0.8",
        }
        resp = self.session.get(url, headers=headers, timeout=config.REQUEST_TIMEOUT_SECONDS)
        if resp.status_code in (403, 429) or resp.status_code >= 500:
            resp.raise_for_status()
        return resp

    def fetch(self, url, force=False):
        """Fetch a URL as HTML text, respecting robots.txt, cache, and rate limits.

        Returns None (and logs) if the page is disallowed or repeatedly blocked
        rather than raising, so callers can just skip and move on.
        """
        if not force:
            cached = self._read_cache(url)
            if cached is not None:
                self.log.info("cache hit: %s", url)
                return cached

        if not self.is_allowed(url):
            self.log.warning("robots.txt disallows fetching %s — skipping", url)
            return None

        self._throttle()
        try:
            resp = self._get(url)
        except requests.RequestException as exc:
            self.log.error("giving up on %s after retries: %s", url, exc)
            return None

        if resp.status_code != 200:
            self.log.warning("unexpected status %s for %s — skipping", resp.status_code, url)
            return None

        html = resp.text
        self._write_cache(url, html)
        return html

    def fetch_rendered(self, url, wait_selector=None):
        """Fetch a JS-rendered page via Playwright (Chromium), same politeness rules."""
        cached = self._read_cache(url)
        if cached is not None:
            self.log.info("cache hit: %s", url)
            return cached

        if not self.is_allowed(url):
            self.log.warning("robots.txt disallows fetching %s — skipping", url)
            return None

        self._throttle()
        try:
            from playwright.sync_api import sync_playwright
        except ImportError:
            self.log.error("playwright not installed; cannot render %s", url)
            return None

        html = None
        try:
            with sync_playwright() as p:
                browser = p.chromium.launch(executable_path=config.PLAYWRIGHT_EXECUTABLE_PATH)
                try:
                    page = browser.new_page(user_agent=random.choice(config.USER_AGENTS))
                    page.goto(url, timeout=config.REQUEST_TIMEOUT_SECONDS * 1000)
                    if wait_selector:
                        try:
                            page.wait_for_selector(wait_selector, timeout=10000)
                        except Exception:
                            pass
                    html = page.content()
                finally:
                    browser.close()
        except Exception as exc:
            self.log.error("playwright render failed for %s: %s", url, exc)
            return None

        if html:
            self._write_cache(url, html)
        return html

    # -- interface to implement per site -------------------------------------
    def parse_listing_urls(self, html, page_url):
        raise NotImplementedError

    def parse_listing(self, html, url):
        raise NotImplementedError

    def build_search_url(self, page_number):
        raise NotImplementedError

    def scrape(self, max_pages=5):
        """Crawl search-result pages, then each listing page. Returns list of dict rows."""
        rows = []
        seen_urls = set()
        for page_number in range(1, max_pages + 1):
            search_url = self.build_search_url(page_number)
            html = self.fetch(search_url)
            if html is None:
                self.log.info("no more pages / blocked at page %d — stopping", page_number)
                break

            listing_urls = self.parse_listing_urls(html, search_url)
            if not listing_urls:
                self.log.info("no listings found on page %d — stopping", page_number)
                break

            for url in listing_urls:
                if url in seen_urls:
                    continue
                seen_urls.add(url)
                listing_html = self.fetch(url)
                if listing_html is None:
                    continue
                try:
                    row = self.parse_listing(listing_html, url)
                except Exception as exc:
                    self.log.warning("failed to parse %s: %s", url, exc)
                    continue
                if row:
                    row["source"] = self.site_name
                    rows.append(row)

        self.log.info("scraped %d listings across %d page(s)", len(rows), max_pages)
        return rows


class NextDataScraper(BaseScraper):
    """Shared logic for PropertyGuru-Group sites (iProperty, PropertyGuru).

    Both sites are server-rendered Next.js apps that embed the full listing
    payload for a search-results page in a `<script id="__NEXT_DATA__">` JSON
    blob — the same data their listing cards render from. That means a single
    search-page fetch yields ~20 fully-populated rows with no need to open
    individual listing detail pages, which keeps request volume low.

    Subclasses just set `site_name`, `site_key` (key into
    config.SITE_BASE_URLS), and `search_folder`.
    """

    site_key = None
    search_folder = "/property-for-rent"

    def build_search_url(self, page_number):
        base = config.SITE_BASE_URLS[self.site_key]
        if page_number <= 1:
            return f"{base}{self.search_folder}"
        return f"{base}{self.search_folder}/{page_number}"

    def _extract_next_data(self, html):
        data = next_data.extract_next_data(html)
        if data is None and NEXT_DATA_RE.search(html or ""):
            self.log.warning("failed to decode __NEXT_DATA__ JSON")
        return data

    # Card parsing lives in next_data.py so the baseline pipeline can re-read
    # the page cache without importing any network code.
    def _row_from_listing_data(self, ld):
        return next_data.row_from_listing_data(ld, config.SITE_BASE_URLS[self.site_key])

    def parse_listing_urls(self, html, page_url):
        # Unused — see scrape() override: full rows come straight from the
        # search page's embedded JSON, so there's no second fetch per listing.
        return []

    def parse_listing(self, html, url):
        raise NotImplementedError("rows come from search-page __NEXT_DATA__; see scrape()")

    def scrape(self, max_pages=5):
        rows = []
        seen_urls = set()
        for page_number in range(1, max_pages + 1):
            search_url = self.build_search_url(page_number)
            html = self.fetch(search_url)
            if html is None:
                self.log.info("no more pages / blocked at page %d — stopping", page_number)
                break

            data = self._extract_next_data(html)
            if not data:
                self.log.info("no __NEXT_DATA__ found on page %d — stopping", page_number)
                break

            try:
                listings = data["props"]["pageProps"]["pageData"]["data"]["listingsData"]
            except (KeyError, TypeError):
                self.log.info("unexpected page shape on page %d — stopping", page_number)
                break

            if not listings:
                self.log.info("no listings on page %d — stopping", page_number)
                break

            for entry in listings:
                ld = entry.get("listingData") or {}
                raw_row = self._row_from_listing_data(ld)
                if not raw_row.get("listing_url") or raw_row["listing_url"] in seen_urls:
                    continue
                seen_urls.add(raw_row["listing_url"])
                raw_row["source"] = self.site_name
                rows.append(raw_row)

        self.log.info("scraped %d raw listings across up to %d page(s)", len(rows), max_pages)
        return rows
