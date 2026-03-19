"""Geocoding utility using Nominatim (OpenStreetMap)."""

import logging
import time
from functools import lru_cache
from typing import NamedTuple

from geopy.geocoders import Nominatim
from geopy.exc import GeocoderTimedOut, GeocoderServiceError

logger = logging.getLogger(__name__)

_geolocator: Nominatim | None = None


def _get_geolocator() -> Nominatim:
    global _geolocator
    if _geolocator is None:
        _geolocator = Nominatim(user_agent="triangulate-investigation-toolkit")
    return _geolocator


class GeoResult(NamedTuple):
    country_code: str
    lat: float
    lon: float


@lru_cache(maxsize=1000)
def geocode_location(location_text: str) -> GeoResult | None:
    if not location_text or not location_text.strip():
        return None

    location_text = location_text.strip()
    geolocator = _get_geolocator()

    try:
        location = geolocator.geocode(location_text, language="en", timeout=10)
        if location:
            address = location.raw.get("address", {})
            country_code = address.get("country_code", "").upper()
            if not country_code:
                country_code = _infer_country_code(address, location_text)
            return GeoResult(
                country_code=country_code,
                lat=location.latitude,
                lon=location.longitude,
            )
    except GeocoderTimedOut:
        logger.warning(f"Geocoding timeout for: {location_text}")
    except GeocoderServiceError as e:
        logger.warning(f"Geocoding service error for '{location_text}': {e}")
    except Exception as e:
        logger.warning(f"Geocoding failed for '{location_text}': {e}")

    return None


def geocode_with_retry(location_text: str, retries: int = 2, delay: float = 1.5) -> GeoResult | None:
    for attempt in range(retries):
        result = geocode_location(location_text)
        if result:
            return result
        if attempt < retries - 1:
            time.sleep(delay)
    return None


def _infer_country_code(address: dict, location_text: str = "") -> str:
    country = address.get("country", "")
    country_code = address.get("country_code", "").upper()
    if country_code:
        return country_code
    location_text_lower = location_text.lower()
    country_to_code = {
        "gaza": "PS",
        "palestine": "PS",
        "palestinian": "PS",
        "israel": "IL",
        "jerusalem": "IL",
        "tel aviv": "IL",
        "ukraine": "UA",
        "kyiv": "UA",
        "kiev": "UA",
        "russia": "RU",
        "moscow": "RU",
        "united states": "US",
        "usa": "US",
        "washington": "US",
        "united kingdom": "GB",
        "uk": "GB",
        "britain": "GB",
        "london": "GB",
        "germany": "DE",
        "berlin": "DE",
        "france": "FR",
        "paris": "FR",
        "iran": "IR",
        "tehran": "IR",
        "iraq": "IQ",
        "syria": "SY",
        "damascus": "SY",
        "lebanon": "LB",
        "beirut": "LB",
        "jordan": "JO",
        "amman": "JO",
        "egypt": "EG",
        "cairo": "EG",
        "saudi": "SA",
        "uae": "AE",
        "qatar": "QA",
        "doha": "QA",
    }
    for key, code in country_to_code.items():
        if key in location_text_lower:
            return code
    return country_to_code.get(country, "").upper()
