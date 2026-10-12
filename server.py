import re
from urllib.parse import urlparse

import httpx
from fastmcp import FastMCP

from scraper import scrape_product

mcp = FastMCP("amazon-product-scraper")

AMAZON_HOST = re.compile(r"(^|\.)amazon\.[a-z.]+$", re.IGNORECASE)
SHORT_LINK_HOST = re.compile(r"^(amzn\.(to|in|eu|com|asia)|a\.co)$", re.IGNORECASE)
PRODUCT_PATH = re.compile(r"/(dp|gp/product)/[A-Z0-9]{10}", re.IGNORECASE)

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0 Safari/537.36"
    ),
}


def is_amazon_product_url(value: str) -> bool:
    try:
        parsed = urlparse(value)
    except ValueError:
        return False

    if parsed.scheme not in ("http", "https"):
        return False

    host = parsed.hostname or ""
    return bool(AMAZON_HOST.search(host) and PRODUCT_PATH.search(parsed.path))


async def expand_short_link(value: str) -> str:
    """Follow amzn.in / amzn.to / a.co redirects and return the final URL."""
    host = urlparse(value).hostname or ""
    if not SHORT_LINK_HOST.match(host):
        return value

    async with httpx.AsyncClient(
        follow_redirects=True, timeout=10, headers=HEADERS
    ) as client:
        # stream() avoids downloading the page body; we only need the final URL
        async with client.stream("GET", value) as response:
            return str(response.url)


@mcp.tool
async def get_amazon_product_details(url: str) -> dict:
    """
    Scrape an Amazon product page and return its details: title, ASIN, price,
    rating, review count, color and size options, offers, the about section,
    and product/technical details. Accepts full product URLs and short links
    such as amzn.in/d/... or amzn.to/...

    Args:
        url: Amazon product URL or short link
    """
    try:
        final_url = await expand_short_link(url)
    except httpx.HTTPError as err:
        raise ValueError(f"Could not resolve short link: {err}") from err

    if not is_amazon_product_url(final_url):
        raise ValueError(
            "Invalid input: the link did not resolve to an Amazon product page "
            f"(final URL: {final_url}). Please provide a URL containing "
            "/dp/<ASIN> or /gp/product/<ASIN>."
        )

    return await scrape_product(final_url)


if __name__ == "__main__":
    mcp.run()