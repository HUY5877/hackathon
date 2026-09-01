"""Evidence-based helpers shared by HTML crawler implementations.

The helpers in this module deliberately reject ambiguous values.  A crawler is
better off leaving a factual field empty for the screening pipeline than
silently assigning an unrelated date or location from elsewhere on the page.
"""

from __future__ import annotations

import json
import re
from typing import Any, Iterable
from urllib.parse import urlparse


_MONTH = (
    r"January|February|March|April|May|June|July|August|September|"
    r"October|November|December|Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec"
)
_DATE_TOKEN_RE = re.compile(
    rf"(?:"
    rf"\d{{4}}(?:年|[-/])\d{{1,2}}(?:月|[-/])\d{{1,2}}日?"
    rf"(?:[T\s]\d{{1,2}}:\d{{2}}(?::\d{{2}})?(?:Z|[+-]\d{{2}}:?\d{{2}})?)?"
    rf"|(?:{_MONTH})\s+\d{{1,2}}(?:st|nd|rd|th)?,?\s+\d{{4}}"
    rf"|\d{{1,2}}(?:st|nd|rd|th)?\s+(?:{_MONTH})\s+\d{{4}}"
    rf")",
    re.IGNORECASE,
)
_RANGE_SEPARATOR_RE = re.compile(
    r"^[\s,;:()\[\]]*(?:to|through|until|[-–—~]|至|到)[\s,;:()\[\]]*$",
    re.IGNORECASE,
)
_SAME_MONTH_RANGE_RE = re.compile(
    rf"\b({_MONTH})\s+(\d{{1,2}})(?:st|nd|rd|th)?\s*[-–—~]\s*"
    rf"(\d{{1,2}})(?:st|nd|rd|th)?,?\s+(\d{{4}})\b",
    re.IGNORECASE,
)
_CROSS_MONTH_RANGE_RE = re.compile(
    rf"\b({_MONTH})\s+(\d{{1,2}})(?:st|nd|rd|th)?,?\s*[-–—~]\s*"
    rf"({_MONTH})\s+(\d{{1,2}})(?:st|nd|rd|th)?,?\s+(\d{{4}})\b",
    re.IGNORECASE,
)
_MONTH_NUMBERS = {
    "jan": 1,
    "feb": 2,
    "mar": 3,
    "apr": 4,
    "may": 5,
    "jun": 6,
    "jul": 7,
    "aug": 8,
    "sep": 9,
    "oct": 10,
    "nov": 11,
    "dec": 12,
}


def _month_number(value: str) -> int:
    return _MONTH_NUMBERS[value[:3].casefold()]


def extract_explicit_date_range(text: str) -> tuple[str | None, str | None]:
    """Extract one date or an explicitly connected start/end pair.

    Two dates are accepted only when the text between them is an unambiguous
    range connector such as ``to`` or ``至``.  Three or more dates are rejected
    instead of taking the first two.
    """
    if not isinstance(text, str):
        return None, None
    value = " ".join(text.split())
    if not value:
        return None, None

    cross_month = _CROSS_MONTH_RANGE_RE.search(value)
    if cross_month:
        outside = value[: cross_month.start()] + " " + value[cross_month.end() :]
        if _DATE_TOKEN_RE.search(outside) or _SAME_MONTH_RANGE_RE.search(outside) or _CROSS_MONTH_RANGE_RE.search(outside):
            return None, None
        month1, day1, month2, day2, year = cross_month.groups()
        return (
            f"{year}-{_month_number(month1):02d}-{int(day1):02d}",
            f"{year}-{_month_number(month2):02d}-{int(day2):02d}",
        )

    same_month = _SAME_MONTH_RANGE_RE.search(value)
    if same_month:
        outside = value[: same_month.start()] + " " + value[same_month.end() :]
        if _DATE_TOKEN_RE.search(outside) or _SAME_MONTH_RANGE_RE.search(outside) or _CROSS_MONTH_RANGE_RE.search(outside):
            return None, None
        month, day1, day2, year = same_month.groups()
        month_number = _month_number(month)
        return (
            f"{year}-{month_number:02d}-{int(day1):02d}",
            f"{year}-{month_number:02d}-{int(day2):02d}",
        )

    matches = list(_DATE_TOKEN_RE.finditer(value))
    if not matches:
        return None, None
    if len(matches) == 1:
        return matches[0].group(0), None
    if len(matches) != 2:
        return None, None

    separator = value[matches[0].end() : matches[1].start()]
    if not _RANGE_SEPARATOR_RE.fullmatch(separator):
        return None, None
    return matches[0].group(0), matches[1].group(0)


def is_standalone_date_expression(
    text: str,
    start: str | None,
    end: str | None = None,
) -> bool:
    """Return whether a fragment contains only the extracted date expression."""
    if not isinstance(text, str) or not start:
        return False
    remainder = text
    for token in (start, end):
        if token:
            remainder = remainder.replace(token, " ", 1)
    remainder = re.sub(r"\b(?:from|to|through|until)\b|[-–—~至到]", " ", remainder, flags=re.IGNORECASE)
    remainder = re.sub(r"[\s,;:().\[\]]+", "", remainder)
    return remainder == ""


def compact_text_fragments(
    soup: Any,
    *,
    selectors: Iterable[str] = (),
    max_length: int = 300,
) -> list[str]:
    """Return de-duplicated, bounded text fragments without flattening a page.

    Flattening the entire document destroys the relationship between labels and
    values.  These fragments preserve local DOM context and are therefore safe
    inputs for label-aware extraction.
    """
    fragments: list[str] = []
    seen: set[str] = set()

    def add(raw: Any) -> None:
        if not isinstance(raw, str):
            return
        text = " ".join(raw.split())
        if not text or len(text) > max_length or text in seen:
            return
        seen.add(text)
        fragments.append(text)

    selector_list = tuple(selectors)
    for selector in selector_list:
        for element in soup.select(selector):
            add(element.get_text(" ", strip=True))
    # With explicit selectors, widening the search back to every text node would
    # re-introduce navigation/footer false positives.  The all-text fallback is
    # only for callers that intentionally omit selectors and apply label checks.
    if not selector_list:
        for raw in soup.stripped_strings:
            add(str(raw))
    return fragments


def _walk_json(value: Any):
    if isinstance(value, dict):
        yield value
        for nested in value.values():
            yield from _walk_json(nested)
    elif isinstance(value, list):
        for nested in value:
            yield from _walk_json(nested)


def _is_http_url(value: Any) -> bool:
    if not isinstance(value, str):
        return False
    parsed = urlparse(value)
    return parsed.scheme in {"http", "https"} and bool(parsed.netloc)


def _first_image_url(value: Any) -> str | None:
    candidates = value if isinstance(value, list) else [value]
    for candidate in candidates:
        if isinstance(candidate, dict):
            candidate = candidate.get("url") or candidate.get("contentUrl")
        if _is_http_url(candidate):
            return candidate
    return None


def extract_event_json_ld(soup: Any) -> dict[str, Any]:
    """Extract one schema.org Event object, including values nested in @graph."""
    for script in soup.select('script[type="application/ld+json"]'):
        content = script.string or script.get_text()
        if not content:
            continue
        try:
            parsed = json.loads(content)
        except (json.JSONDecodeError, TypeError, ValueError):
            continue

        for item in _walk_json(parsed):
            item_type = item.get("@type")
            types = item_type if isinstance(item_type, list) else [item_type]
            if "Event" not in types:
                continue

            data: dict[str, Any] = {}
            if isinstance(item.get("name"), str) and item["name"].strip():
                data["title"] = item["name"].strip()
            if isinstance(item.get("description"), str) and item["description"].strip():
                data["description"] = item["description"].strip()[:20_000]
            if isinstance(item.get("startDate"), str):
                data["start_date"] = item["startDate"].strip()
            if isinstance(item.get("endDate"), str):
                data["end_date"] = item["endDate"].strip()

            attendance_mode = str(item.get("eventAttendanceMode") or "").casefold()
            if "mixed" in attendance_mode:
                data["mode"] = "hybrid"
            elif "online" in attendance_mode:
                data["mode"] = "online"
            elif "offline" in attendance_mode:
                data["mode"] = "offline"

            location = item.get("location")
            if isinstance(location, str) and location.strip():
                data["location"] = location.strip()
            elif isinstance(location, dict):
                location_name = location.get("name")
                address = location.get("address")
                if isinstance(location_name, str) and location_name.strip():
                    data["location"] = location_name.strip()
                if isinstance(address, str) and address.strip() and "location" not in data:
                    data["location"] = address.strip()
                elif isinstance(address, dict):
                    city = address.get("addressLocality")
                    country = address.get("addressCountry")
                    if isinstance(city, str) and city.strip():
                        data["city"] = city.strip()
                    if isinstance(country, dict):
                        country = country.get("name")
                    if isinstance(country, str) and country.strip():
                        data["country"] = country.strip()
                    if "location" not in data:
                        parts = [
                            part.strip()
                            for part in (address.get("streetAddress"), city, country)
                            if isinstance(part, str) and part.strip()
                        ]
                        if parts:
                            data["location"] = ", ".join(parts)

            organizer = item.get("organizer")
            if isinstance(organizer, dict):
                organizer = organizer.get("name")
            if isinstance(organizer, str) and organizer.strip():
                data["organizer"] = organizer.strip()

            image_url = _first_image_url(item.get("image"))
            if image_url:
                data["cover_image"] = image_url
                data["image_urls"] = [image_url]

            offers = item.get("offers")
            offers = offers if isinstance(offers, list) else [offers]
            for offer in offers:
                if not isinstance(offer, dict):
                    continue
                price = offer.get("price")
                if isinstance(price, (str, int, float)) and str(price).strip():
                    data.setdefault("price", str(price).strip())
                if _is_http_url(offer.get("url")):
                    data["signup_url"] = offer["url"]
                    break

            return data
    return {}
