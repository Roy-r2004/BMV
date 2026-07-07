"""Scrapes basic metadata (title/description/h1/snippet/og:image) from a reference URL."""
from urllib.parse import urljoin

import requests
from bs4 import BeautifulSoup


def fix_encoding(text: str) -> str:
    if not text:
        return text
    replacements = {
        "â€™": "'",
        "â€˜": "'",
        "â€œ": '"',
        "â€\u009d": '"',
        "â€”": "—",
        "â€“": "–",
    }
    for bad, good in replacements.items():
        text = text.replace(bad, good)
    try:
        return text.encode("latin-1").decode("utf-8")
    except (UnicodeDecodeError, UnicodeEncodeError):
        return text


def fetch_reference_metadata(url: str) -> dict:
    """Return title, description, h1, visible_text_snippet from a reference URL."""
    result = {
        "title": "",
        "description": "",
        "h1": "",
        "visible_text_snippet": "",
        "og_image": "",
        "fetch_success": False,
    }

    if not url or not url.startswith(("http://", "https://")):
        return result

    try:
        headers = {"User-Agent": "Mozilla/5.0 (compatible; BuildMyVersionBot/1.0)"}
        response = requests.get(url, headers=headers, timeout=15)
        response.raise_for_status()
        response.encoding = response.apparent_encoding or "utf-8"

        soup = BeautifulSoup(response.text, "lxml")

        title_tag = soup.find("title")
        if title_tag:
            result["title"] = fix_encoding(title_tag.get_text(strip=True))

        meta_desc = soup.find("meta", attrs={"name": "description"})
        if meta_desc and meta_desc.get("content"):
            result["description"] = fix_encoding(meta_desc.get("content", "").strip())

        og_desc = soup.find("meta", property="og:description")
        if og_desc and og_desc.get("content") and not result["description"]:
            result["description"] = fix_encoding(og_desc.get("content", "").strip())

        h1_tag = soup.find("h1")
        if h1_tag:
            result["h1"] = fix_encoding(h1_tag.get_text(strip=True))

        # Real hero image from the client's own reference site — used instead of
        # a generic industry stock photo when available, so the preview isn't
        # visually identical to every other business in the same category.
        og_image = soup.find("meta", property="og:image")
        if not og_image:
            og_image = soup.find("meta", attrs={"name": "twitter:image"})
        if og_image and og_image.get("content"):
            candidate = og_image.get("content", "").strip()
            if candidate:
                result["og_image"] = urljoin(url, candidate)

        paragraphs = soup.find_all("p")
        texts = [fix_encoding(p.get_text(strip=True)) for p in paragraphs[:5] if p.get_text(strip=True)]
        result["visible_text_snippet"] = " ".join(texts)[:500]
        result["fetch_success"] = True

    except Exception as e:
        result["error"] = str(e)

    return result
