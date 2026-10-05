"""The tools the harness can run, and the JSON that describes them to the model."""

import json
import logging
from inspect import signature
import math
import os
import re
from collections import Counter
from pathlib import Path
from urllib.parse import urlparse

import requests

CATEGORIES = ('tops', 'bottoms', 'dresses', 'outerwear', 'shoes', 'bags', 'accessories', 'jewelry')
SEASONS = ('spring', 'summer', 'fall', 'winter')

logger = logging.getLogger(__name__)
GEOCODE_URL = "https://geocoding-api.open-meteo.com/v1/search"
FORECAST_URL = "https://api.open-meteo.com/v1/forecast"
CLOSET_PATH = Path(__file__).parent / "data" / "closet.json"


def _text(value, n=200, default=""):
    return value[:n] if isinstance(value, str) else default


def _load_closet():
    try:
        closet = json.loads(CLOSET_PATH.read_text())
        if not isinstance(closet, list) or any(
            not isinstance(item, dict) or type(item.get("id")) is not int or item["id"] < 1
            or any(not isinstance(item.get(k, ""), str) for k in ("name", "category", "color"))
            or any(not isinstance(item.get(k, []), list)
                   or any(not isinstance(v, str) for v in item.get(k, [])) for k in ("season", "tags"))
            for item in closet
        ) or len({item["id"] for item in closet}) != len(closet):
            raise ValueError("Invalid or duplicate closet records")
        return closet, None
    except (OSError, ValueError):
        logger.exception("Could not load closet")
        return None, json.dumps({"error": "Could not read the closet; check data/closet.json for valid item records and unique IDs."})


def _safe_url(value):
    if not isinstance(value, str):
        return None
    try:
        parsed = urlparse(value)
        if parsed.scheme in ("http", "https") and parsed.hostname and not parsed.username and not parsed.password:
            return parsed._replace(fragment="").geturl()
    except ValueError:
        pass
    return None


def _search_error(code, message):
    return json.dumps({"status": "error", "error": {"code": code, "message": message}})


def _search_api(engine, query):
    """Shared SearchApi.io request; never return credentials or raw provider errors."""
    key = os.environ.get("SEARCHAPI_API_KEY", "").strip()
    if not key:
        return None, _search_error("missing_api_key", "Configure SEARCHAPI_API_KEY in the server environment; do not send keys in chat.")
    try:
        response = requests.get(
            "https://www.searchapi.io/api/v1/search",
            params={"engine": engine, "q": query, "gl": "us", "hl": "en"},
            headers={"Authorization": f"Bearer {key}", "Accept": "application/json"},
            timeout=(5, 20),
        )
        if response.status_code in (401, 403):
            return None, _search_error("authentication_failed", "Check the server's SearchApi.io API key and access.")
        if response.status_code == 429:
            return None, _search_error("rate_limited", "SearchApi.io rate or usage limit reached. Try later or check the account limits.")
        response.raise_for_status()
        data = response.json()
    except requests.Timeout:
        return None, _search_error("timeout", "Search timed out. Try again later.")
    except (requests.RequestException, ValueError):
        # Never expose request details or provider bodies that may contain credentials.
        return None, _search_error("search_failed", "SearchApi.io could not return valid search data. Try again later.")
    if not isinstance(data, dict) or data.get("error"):
        return None, _search_error("provider_error", "SearchApi.io could not complete the search. Try a broader query or check the account.")
    return data, None


def search_products(query: str, max_price: float | None = None, max_results: int = 5) -> str:
    """Search US Google Shopping listings; optionally filter listed USD item prices."""
    if not isinstance(query, str) or not query.strip() or len(query) > 500:
        return _search_error("invalid_query", "Provide a clothing or accessory description of 1–500 characters.")
    if type(max_results) is not int or not 1 <= max_results <= 10:
        return _search_error("invalid_limit", "max_results must be an integer from 1 to 10.")
    if max_price is not None and (
        type(max_price) not in (int, float) or not math.isfinite(max_price) or max_price <= 0
    ):
        return _search_error("invalid_budget", "max_price must be a positive finite amount in USD.")

    data, failure = _search_api("google_shopping", query.strip())
    if failure:
        return failure
    rows = data.get("shopping_results", [])
    if not isinstance(rows, list):
        return _search_error("invalid_response", "SearchApi.io returned an unexpected shopping response.")

    results, seen = [], set()
    for row in rows:
        if not isinstance(row, dict):
            continue
        url = _safe_url(row.get("product_link")) or _safe_url(row.get("link"))
        if not url or url in seen:
            continue
        price = row.get("extracted_price")
        if type(price) not in (int, float) or not math.isfinite(price) or price < 0:
            price = None
        label = _text(row.get("price"), n=None, default=None)
        # A plain dollar price is interpreted as USD only in this US-localized search.
        # Reject ranges, installment labels and other currencies for budget filtering.
        usd = bool(label and re.fullmatch(r"(?:US\$|USD\s*|\$)\s*\d[\d,]*(?:\.\d{1,2})?(?:\s*USD)?", label.strip()))
        currency = "USD" if usd else None
        if max_price is not None and (price is None or currency != "USD" or price > max_price):
            continue
        seen.add(url)
        results.append({
            "title": _text(row.get("title")),
            "url": url,
            "retailer": _text(row.get("seller")),
            "price": price,
            "price_display": _text(label, default=None),
            "currency": currency,
            "image_url": _safe_url(row.get("thumbnail")),
        })
        if len(results) >= max_results:
            break
    return json.dumps({
        "status": "ok" if results else "no_results",
        "query": query.strip(),
        "max_price_usd": max_price,
        "results": results,
        "notes": "USD listing prices exclude shipping/tax; verify price, stock, size and similarity on the linked page.",
    })

def search_pinterest_pins(query: str, max_results: int = 5) -> str:
    """Find publicly indexed Pinterest pins through Google Images, not private boards."""
    if not isinstance(query, str) or not query.strip() or len(query) > 500:
        return _search_error("invalid_query", "Provide outfit or style keywords of 1–500 characters.")
    if type(max_results) is not int or not 1 <= max_results <= 10:
        return _search_error("invalid_limit", "max_results must be an integer from 1 to 10.")
    data, failure = _search_api("google_images", f"{query.strip()} outfit inspiration site:pinterest.com/pin/")
    if failure:
        return failure
    rows = data.get("images", [])
    if not isinstance(rows, list):
        return _search_error("invalid_response", "SearchApi.io returned an unexpected image response.")
    results, seen = [], set()
    for row in rows:
        if not isinstance(row, dict):
            continue
        source = row.get("source")
        url = _safe_url(source.get("link")) if isinstance(source, dict) else None
        if not url:
            continue
        parsed = urlparse(url)
        host = parsed.hostname
        if host != "pinterest.com" and not host.endswith(".pinterest.com"):
            continue
        # Keep pin pages only, rejecting boards, profiles and lookalike domains.
        pin = re.fullmatch(r"/pin/(?:[^/]+--)?([0-9]+)/?", parsed.path)
        if not pin:
            continue
        pin_id = pin.group(1)
        if pin_id in seen:
            continue
        seen.add(pin_id)
        original = row.get("original")
        image_url = _safe_url(original.get("link")) if isinstance(original, dict) else None
        thumbnail = _safe_url(row.get("thumbnail"))
        results.append({
            "title": _text(row.get("title"), default="Pinterest inspiration"),
            "url": f"https://www.pinterest.com/pin/{pin_id}/",
            "source": "Pinterest",
            "image_url": image_url or thumbnail,
            "thumbnail_url": thumbnail,
        })
        if len(results) >= max_results:
            break
    return json.dumps({
        "status": "ok" if results else "no_results",
        "query": query.strip(),
        "results": results,
        "notes": "Public pins only; images are displayed but not visually analyzed by the model, and empty results may reflect limited indexing.",
    })


def search_closet(category=None, color=None, season=None, tag=None, query=None) -> str:
    """Filter owned items; omitted filters return the whole closet."""
    filters = {"category": category, "color": color, "season": season, "tag": tag, "query": query}
    if any(v is not None and (not isinstance(v, str) or not v.strip()) for v in filters.values()):
        return json.dumps({"error": "Filters must be nonempty strings, or omitted."})
    filters = {k: v.strip().lower() for k, v in filters.items() if v is not None}
    if filters.get("category", CATEGORIES[0]) not in CATEGORIES or filters.get("season", SEASONS[0]) not in SEASONS:
        return json.dumps({"error": "Choose a category and season from the tool schema."})
    closet, error = _load_closet()
    if error:
        return error
    filtered = []
    for item in closet:
        fields = {"category": item.get("category", "").lower(), "color": item.get("color", "").lower(),
                  "season": [v.lower() for v in item.get("season", [])],
                  "tag": [v.lower() for v in item.get("tags", [])], "query": item.get("name", "").lower()}
        if all(any(value in t for t in fields[key]) if key == "tag" else value in fields[key]
               for key, value in filters.items()):
            filtered.append(item)
    result = {"count": len(filtered), "clothing": filtered}
    if not filtered:
        result["note"] = "No items matched; try fewer filters."
    return json.dumps(result)


def add_closet_item(name: str, category: str, color: str, season: list, tags: list) -> str:
    """Save an owned item; its photo can be added through the closet sidebar."""
    closet, error = _load_closet()
    if error:
        return error

    if not isinstance(name, str) or not name.strip() or len(name) > 200:
        return json.dumps({"error": "Provide an item name of 1–200 characters."})
    if not isinstance(category, str) or category.strip().lower() not in CATEGORIES:
        return json.dumps({"error": "Use a category from the add_closet_item schema."})
    if not isinstance(color, str) or not color.strip() or len(color) > 40:
        return json.dumps({"error": "Provide a short color description."})
    if not isinstance(season, list) or not season or any(not isinstance(s, str) or s.strip().lower() not in SEASONS for s in season):
        return json.dumps({"error": "Provide at least one season: spring, summer, fall or winter."})
    if not isinstance(tags, list) or any(not isinstance(t, str) or not t.strip() for t in tags):
        return json.dumps({"error": "Provide tags as a list of nonempty style or occasion words."})
    next_id = max((i["id"] for i in closet), default=0) + 1
    item = {
        "id": next_id,
        "name": name.strip(),
        "category": category.strip().lower(),
        "color": color.strip().lower(),
        "season": list(dict.fromkeys(s.strip().lower() for s in season)),
        "tags": list(dict.fromkeys(t.strip().lower() for t in tags)),
        "image_url": None,
        "image_kind": None,
    }
    closet.append(item)

    with open(CLOSET_PATH, "w") as f:
        json.dump(closet, f, indent=4)

    return json.dumps({"added": item})


def get_closet_stats() -> str:
    """Count wardrobe items by category, color, season and tag."""
    closet, error = _load_closet()
    if error:
        return error
    result = {"total": len(closet)}
    for key in ("category", "color", "season", "tags"):
        values = (v for item in closet for v in (
            item.get(key, []) if key in ("season", "tags") else [item.get(key, "")]))
        result[f"by_{key}"] = dict(Counter(values).most_common())
    return json.dumps(result)


def get_weather(location: str) -> str:
    """Get the current weather for a location."""
    if not isinstance(location, str) or not location.strip():
        return json.dumps({"error": "Provide a city name, for example New York."})
    try:
        geocoding = requests.get(GEOCODE_URL, params={"name": location, "count": 1}, timeout=10)
        geocoding.raise_for_status()
        places = geocoding.json()
        if not places.get("results"):
            return json.dumps({"error": f"City '{location}' was not found."})
        place = places["results"][0]

        weather_response = requests.get(
            FORECAST_URL,
            params={
                "latitude": place["latitude"],
                "longitude": place["longitude"],
                "current": "temperature_2m,relative_humidity_2m,wind_speed_10m",
                "temperature_unit": "fahrenheit",
                "wind_speed_unit": "mph",
            },
            timeout=10,
        )
        weather_response.raise_for_status()
        current = weather_response.json()["current"]
        return json.dumps({
            "location": place["name"],
            "temp_f": current["temperature_2m"],
            "humidity": current["relative_humidity_2m"],
            "wind_mph": current["wind_speed_10m"],
        })
    except (requests.RequestException, ValueError, KeyError, TypeError, AttributeError):
        return json.dumps({"error": "Weather is temporarily unavailable. Try again with a city and country, or ask for general seasonal styling."})


def present_outfits(outfits: list) -> str:
    """Return selected items in display order, with photos when available."""
    if not isinstance(outfits, list) or not 1 <= len(outfits) <= 6:
        return json.dumps({"error": "Provide between 1 and 6 outfits."})
    items, error = _load_closet()
    if error:
        return error
    closet = {item["id"]: item for item in items}
    order = {"tops": 0, "dresses": 0, "outerwear": 1, "bottoms": 2,
             "shoes": 3, "bags": 4, "accessories": 4, "jewelry": 4}
    selected = []
    for outfit in outfits:
        if not isinstance(outfit, dict):
            return json.dumps({"error": "Each outfit needs a title and item_ids."})
        title, ids = outfit.get("title"), outfit.get("item_ids")
        if not isinstance(title, str) or not title.strip() or len(title) > 120:
            return json.dumps({"error": "Each outfit needs a title of 1–120 characters."})
        if not isinstance(ids, list) or not 1 <= len(ids) <= 12 or any(type(i) is not int for i in ids):
            return json.dumps({"error": "item_ids must contain 1–12 integer closet IDs."})
        missing = [i for i in ids if i not in closet]
        if missing:
            return json.dumps({"error": "Unknown closet IDs. Search the closet and retry.", "item_ids": missing})
        clothing = sorted(({"image_url": None, "image_kind": None, **closet[i]} for i in dict.fromkeys(ids)),
                          key=lambda item: order.get(item.get("category"), 5))
        selected.append({"title": title.strip(), "clothing": clothing})
    return json.dumps({"status": "ok", "outfits": selected})


TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "present_outfits",
            "description": "Display outfits selected by closet item IDs in top-to-shoes order, with available photos or a placeholder.",
            "parameters": {
                "type": "object",
                "properties": {"outfits": {
                    "type": "array", "minItems": 1, "maxItems": 6,
                    "items": {
                        "type": "object",
                        "properties": {
                            "title": {"type": "string", "minLength": 1, "maxLength": 120},
                            "item_ids": {"type": "array", "minItems": 1, "maxItems": 12, "items": {"type": "integer"}},
                        },
                        "required": ["title", "item_ids"], "additionalProperties": False,
                    },
                }},
                "required": ["outfits"], "additionalProperties": False,
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "search_pinterest_pins",
            "description": "Find public Pinterest inspiration via Google Images; returns pin links and images, without private-board access or visual analysis.",
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {"type": "string", "minLength": 1, "maxLength": 500, "description": "Style keywords, e.g. brown jacket fall outfits."},
                    "max_results": {"type": "integer", "minimum": 1, "maximum": 10, "description": "Maximum pins; default 5."},
                },
                "required": ["query"], "additionalProperties": False,
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "search_products",
            "description": "Find US clothing listings via SearchApi.io Google Shopping, with prices, retailers, images and links; searches find similar styles, not verified exact matches.",
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {"type": "string", "minLength": 1, "maxLength": 500, "description": "One garment's type, color, cut and material, including details from an attached photo."},
                    "max_price": {"type": "number", "exclusiveMinimum": 0, "description": "USD per item before shipping/tax; excludes unknown and non-USD prices."},
                    "max_results": {"type": "integer", "minimum": 1, "maximum": 10, "description": "Maximum listings; default 5."},
                },
                "required": ["query"], "additionalProperties": False,
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_weather",
            "description": "Get current temperature, humidity and wind for a city.",
            "parameters": {
                "type": "object",
                "properties": {"location": {"type": "string", "minLength": 1, "description": "City name, e.g. New York."}},
                "required": ["location"], "additionalProperties": False,
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "search_closet",
            "description": "Find owned items, IDs and available photos; omitted filters return the full wardrobe, and empty matches can be retried with fewer filters.",
            "parameters": {
                "type": "object",
                "properties": {
                    "category": {"type": "string", "enum": list(CATEGORIES)},
                    "color": {"type": "string", "minLength": 1, "description": "Color substring, e.g. blue matches navy blue."},
                    "season": {"type": "string", "enum": list(SEASONS)},
                    "tag": {"type": "string", "minLength": 1, "description": "Style or occasion tag, e.g. work or vacation."},
                    "query": {"type": "string", "minLength": 1, "description": "Substring of the item name, e.g. silk or blazer."},
                },
                "additionalProperties": False,
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "add_closet_item",
            "description": "Save a new owned item when requested; its photo can be added in My closet.",
            "parameters": {
                "type": "object",
                "properties": {
                    "name": {"type": "string", "minLength": 1, "maxLength": 200, "description": "Item name, e.g. Striped wool sweater."},
                    "category": {"type": "string", "enum": list(CATEGORIES)},
                    "color": {"type": "string", "minLength": 1, "maxLength": 40, "description": "Main color, e.g. black."},
                    "season": {"type": "array", "minItems": 1, "items": {"type": "string", "enum": list(SEASONS)}},
                    "tags": {"type": "array", "items": {"type": "string", "minLength": 1}, "description": "Style or occasion tags, e.g. work or vacation."},
                },
                "required": ["name", "category", "color", "season", "tags"], "additionalProperties": False,
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_closet_stats",
            "description": "Count wardrobe items by category, color, season and tag.",
            "parameters": {"type": "object", "additionalProperties": False},
        },
    },
]

TOOL_MAP = {function.__name__: function for function in (
    present_outfits, search_pinterest_pins, search_products, get_weather,
    search_closet, add_closet_item, get_closet_stats,
)}


def run_tool(name: str, args: dict) -> str:
    """Validate call arguments and keep unexpected failures out of model responses."""
    if not isinstance(name, str) or name not in TOOL_MAP:
        return json.dumps({"error": f"Unknown tool. Available: {list(TOOL_MAP)}"})
    if not isinstance(args, dict):
        return json.dumps({"error": "Tool arguments must be a JSON object."})
    function = TOOL_MAP[name]
    try:
        signature(function).bind(**args)
    except TypeError:
        return json.dumps({"error": f"Bad arguments for {name}; check required names in its schema."})
    try:
        return function(**args)
    except Exception:
        logger.exception("Tool %s failed", name)
        return json.dumps({"error": f"{name} failed unexpectedly; try again, or ask the app owner to check server logs."})
