import sys
import time

from playwright.async_api import async_playwright, TimeoutError as PlaywrightTimeoutError

BLOCKED_RESOURCE_TYPES = {"image", "font", "media", "stylesheet"}

BLOCKED_DOMAINS = [
    "google-analytics",
    "googletagmanager",
    "doubleclick",
    "facebook.net",
    "amazon-adsystem",
    "advertising",
    "adservice",
    "scorecardresearch",
    "hotjar",
    "clarity.ms",
]

# Runs in the browser. Same selectors and logic as the original JS scraper.
EXTRACT_JS = """() => {
  const clean = (s) => s?.replace(/\\s+/g, " ").trim() || null;
  const text = (sel) => clean(document.querySelector(sel)?.innerText);
  const attr = (sel, name) => document.querySelector(sel)?.getAttribute(name) || null;

  const offers = Array.from(
    document.querySelectorAll(".vsx__offers .offers-items")
  ).map((offer) => ({
    type: clean(offer.querySelector(".offers-items-title")?.innerText),
    description: clean(offer.querySelector(".a-truncate-full")?.innerText),
    count: clean(offer.querySelector(".vsx-offers-count")?.innerText),
  }));

  const productDetails = {};
  document.querySelectorAll("#prodDetails tr").forEach((row) => {
    const key = clean(row.querySelector("th")?.innerText);
    const value = clean(row.querySelector("td")?.innerText);
    if (key && value && key !== "Customer Reviews") {
      productDetails[key] = value;
    }
  });

  const techDetails = {};
  document.querySelectorAll("#tech table tr").forEach((row) => {
    const cells = row.querySelectorAll("td");
    if (cells.length < 2) return;
    const key = clean(cells[0].innerText);
    const value = clean(cells[1].innerText);
    if (key && value) {
      techDetails[key] = value;
    }
  });

  return {
    title: text("#productTitle"),
    asin: productDetails["ASIN"] || null,
    rating: attr("#acrPopover", "title"),
    reviewCount: text("#acrCustomerReviewText"),
    boughtLastMonth: text("#social-proofing-faceout-title-tk_bought"),
    price: text(".a-price .a-offscreen"),
    color: text("#inline-twister-expanded-dimension-text-color_name"),
    size: text("#inline-twister-expanded-dimension-text-size_name"),
    offers,
    about: text("#feature-bullets"),
    productDetails,
    techDetails,
    reviewSummary: text('[data-testid="overall-summary"]'),
  };
}"""


async def _route_handler(route):
    request = route.request

    # Block resources not required for text scraping
    if request.resource_type in BLOCKED_RESOURCE_TYPES:
        await route.abort()
        return

    # Block tracking / analytics / ads
    if any(domain in request.url for domain in BLOCKED_DOMAINS):
        await route.abort()
        return

    await route.continue_()


async def scrape_product(url: str) -> dict:
    start = time.monotonic()

    async with async_playwright() as p:
        browser = await p.chromium.launch(
            headless=True,
            args=["--disable-gpu", "--disable-dev-shm-usage", "--no-sandbox"],
        )

        try:
            context = await browser.new_context(
                viewport={"width": 1280, "height": 800},
                service_workers="block",
            )
            page = await context.new_page()

            await page.route("**/*", _route_handler)

            await page.goto(url, wait_until="domcontentloaded", timeout=20000)

            try:
                await page.wait_for_selector(
                    "#productTitle", state="attached", timeout=5000
                )
            except PlaywrightTimeoutError:
                # stderr, not stdout: stdout carries the MCP protocol
                print(f"Product title not found: {url}", file=sys.stderr)

            product = await page.evaluate(EXTRACT_JS)

            elapsed_ms = int((time.monotonic() - start) * 1000)
            print(f"Scraped {url} in {elapsed_ms}ms", file=sys.stderr)

            return product
        finally:
            await browser.close()