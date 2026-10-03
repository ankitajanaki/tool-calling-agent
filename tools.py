"""The tools the harness can run, and the JSON that describes them to the model."""

import json
from pathlib import Path

import requests

# Open-Meteo is free and needs no API key.
GEOCODE_URL = "https://geocoding-api.open-meteo.com/v1/search"
FORECAST_URL = "https://api.open-meteo.com/v1/forecast"
CLOSET_PATH = Path(__file__).parent / "data" / "closet.json"

def search_closet(category = None, color = None, season = None, tag = None, query = None) -> str:
    """
    Looks through items already in the user's closet.
    Attempts to apply filters based on provided details and occassion.
    A call with no filters should list all items in the closet.
    """
    
    try:
        with open(CLOSET_PATH) as f:
            closet = json.load(f)
    except (FileNotFoundError, json.JSONDecodeError) as e:
        return json.dumps({"error": f"Could not read closet: {e}"})

    filtered = []
    for item in closet:
        if (category is not None) and (category.lower() not in item["category"].lower()):
            continue
        if (color is not None) and (item["color"].lower() not in color.lower()):
            continue
        if (season is not None) and (season.lower() not in item["season"]):
            continue
        if (tag is not None) and not any(tag.lower() in t for t in item["tags"]):
            continue
        if (query is not None) and (query.lower() not in item["name"].lower()):
            continue
        filtered.append(item)

    if len(filtered) == 0:
        return json.dumps({"count": len(filtered), "clothing": filtered, "note": "No clothing items matched these filters."})
    
    return json.dumps({"count": len(filtered), "clothing": filtered})

def get_weather(location: str) -> str:
    """Get the current weather for a location."""
    try:
        places = requests.get(GEOCODE_URL, params={"name": location, "count": 1}, timeout=10).json()
        if not places.get("results"):
            return json.dumps({"error": f"City '{location}' was not found."})
        place = places["results"][0]

        current = requests.get(
            FORECAST_URL,
            params={
                "latitude": place["latitude"],
                "longitude": place["longitude"],
                "current": "temperature_2m,relative_humidity_2m,wind_speed_10m",
                "temperature_unit": "fahrenheit",
                "wind_speed_unit": "mph",
            },
            timeout=10,
        ).json()["current"]
    except requests.RequestException as e:
        # The model cannot see an exception. Return something it can reason about.
        return json.dumps({"error": f"Weather service failed: {e}"})

    return json.dumps({
        "location": place["name"],
        "temp_f": current["temperature_2m"],
        "humidity": current["relative_humidity_2m"],
        "wind_mph": current["wind_speed_10m"],
    })


# What the model sees: the "set notes" in the screenplay.
TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "get_weather",
            "description": "Get the current weather (temperature, humidity, wind) for a city.",
            "parameters": {
                "type": "object",
                "properties": {
                    "location": {"type": "string", "description": "City name, e.g. 'New York'"},
                },
                "required": ["location"],
            },
        },
    },
    {
            "type": "function",
            "function": {
                "name": "search_closet",
                "description": "Searches through your closet to find items that match what you are looking for.",
                "parameters": {
                    "type": "object",
                        "properties": {
                            "category": {"type": "string", "enum": ["tops", "bottoms", "dresses", "outerwear",
                                                    "shoes", "bags", "accessories", "jewelry"]},
                            "color":    {"type": "string", "description": "Single color word, e.g. 'black'"},
                            "season":   {"type": "string", "enum": ["spring", "summer", "fall", "winter"]},
                            "tag":      {"type": "string", "description": "Occasion or style, e.g. 'work', 'evening', 'vacation'"},
                            "query":    {"type": "string", "description": "Free-text words to match in item names, e.g. 'silk' or 'blazer'"},
                        },
                "required": [],
                },
            },
        },
]

# What the harness runs: tool name -> Python function.
TOOL_MAP = {"get_weather": get_weather, "search_closet": search_closet}


def run_tool(name: str, args: dict) -> str:
    """Run one tool call. Models invent tool names and arguments; never let that crash the loop."""
    if name not in TOOL_MAP:
        return json.dumps({"error": f"Unknown tool '{name}'. Available: {list(TOOL_MAP)}"})
    try:
        return TOOL_MAP[name](**args)
    except TypeError as e:
        return json.dumps({"error": f"Bad arguments for {name}: {e}"})
