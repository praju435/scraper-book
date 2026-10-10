
import json
import logging
import re
import time
from pathlib import Path
from urllib.parse import urljoin

import requests
from bs4 import BeautifulSoup
from pydantic import BaseModel, Field, HttpUrl, ValidationError


BASE_URL = "https://books.toscrape.com/"
OUTPUT_DIR = Path("output")
OUTPUT_FILE = OUTPUT_DIR / "books.json"

HEADERS = {
    "User-Agent": (
        "BookLearningScraper/1.0 "
        "(educational project; contact: learner@example.com)"
    )
}

RATING_MAP = {
    "One": 1,
    "Two": 2,
    "Three": 3,
    "Four": 4,
    "Five": 5,
}


class Book(BaseModel):
    title: str = Field(min_length=1)
    price: float = Field(ge=0)
    availability: str = Field(min_length=1)
    rating: int = Field(ge=1, le=5)
    product_url: HttpUrl


logging.basicConfig(
    level=logging.INFO,
    format="%(levelname)s: %(message)s",
)

session = requests.Session()
session.headers.update(HEADERS)


def parse_price(price_text: str) -> float:
    """Convert a price such as '£51.77' to 51.77."""
    cleaned = re.sub(r"[^\d.]", "", price_text)
    return float(cleaned)


def scrape_page(page_number: int) -> list[dict]:
    """Fetch and parse one catalogue page."""
    url = urljoin(
        BASE_URL,
        f"catalogue/page-{page_number}.html"
    )

    response = session.get(url, timeout=15)
    response.raise_for_status()

    soup = BeautifulSoup(response.text, "html.parser")
    book_cards = soup.select("article.product_pod")

    if not book_cards:
        raise ValueError("No book cards found; the HTML may have changed.")

    valid_books = []

    for card in book_cards:
        try:
            title_element = card.select_one("h3 a")
            price_element = card.select_one(".price_color")
            availability_element = card.select_one(
                ".availability"
            )
            rating_element = card.select_one(".star-rating")

            if not all([
                title_element,
                price_element,
                availability_element,
                rating_element,
            ]):
                raise ValueError("A required HTML element is missing.")

            title = title_element.get("title", "").strip()
            price = parse_price(
                price_element.get_text(strip=True)
            )
            availability = availability_element.get_text(
                " ", strip=True
            )

            rating_classes = rating_element.get("class", [])
            rating_word = next(
                (
                    item for item in rating_classes
                    if item in RATING_MAP
                ),
                None,
            )

            if rating_word is None:
                raise ValueError("Unknown book rating.")

            product_url = urljoin(
                url,
                title_element.get("href", "")
            )

            book = Book(
                title=title,
                price=price,
                availability=availability,
                rating=RATING_MAP[rating_word],
                product_url=product_url,
            )

            valid_books.append(
                book.model_dump(mode="json")
            )

        except (ValueError, TypeError, ValidationError) as error:
            logging.warning(
                "Skipping an invalid book on page %s: %s",
                page_number,
                error,
            )

    return valid_books


def main():
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    all_books = []

    for page_number in range(1, 4):
        try:
            books = scrape_page(page_number)
            all_books.extend(books)

            logging.info(
                "Page %s: collected %s valid books",
                page_number,
                len(books),
            )

        except (requests.RequestException, ValueError) as error:
            logging.error(
                "Page %s failed: %s",
                page_number,
                error,
            )

        # Be polite: wait between page requests.
        if page_number < 3:
            time.sleep(2)

    with OUTPUT_FILE.open("w", encoding="utf-8") as file:
        json.dump(
            all_books,
            file,
            indent=2,
            ensure_ascii=False,
        )

    logging.info("Total valid books: %s", len(all_books))
    logging.info("Saved output to %s", OUTPUT_FILE.resolve())


if __name__ == "__main__":
    main()
