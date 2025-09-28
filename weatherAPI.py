"""
Flask Weather API Service
- Aggregates multiple providers (OpenWeatherMap, WeatherAPI) for current & forecast
- Endpoints:
    GET /weather/current?location={city}
    GET /weather/forecast?location={city}&days={n}
    GET /locations/search?q={query}
    GET /health
- Caching: TTL cache to reduce external API calls
- Rate limiting: Flask-Limiter
- Logging + error handling
- Swagger UI (flasgger) for API docs and example requests/responses

# python -m venv myenv
# myenv\Scripts\activate
http://192.168.29.207:5000/apidocs/

http://192.168.29.207:5000/apidocs/#/default/get_weather_current
http://192.168.29.207:5000/
http://192.168.29.207:5000/health
http://127.0.0.1:5000/weather/current?location=london
http://192.168.29.207:5000/locations/search?q=Chennai
http://192.168.29.207:5000/weather/forecast?location=Hyderabad&days=3


"""

import os
import time
import logging
from typing import Dict, Any, List, Optional
from functools import wraps

import requests
from flask import Flask, request, jsonify
from cachetools import TTLCache, cached
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address
from flasgger import Swagger, swag_from

from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()

# Config
OPENWEATHER_API_KEY = os.getenv("OPENWEATHER_API_KEY", "")
WEATHERAPI_KEY = os.getenv("WEATHERAPI_KEY", "")
CACHE_TTL_SECONDS = int(os.getenv("CACHE_TTL_SECONDS", "300"))  # 5 minutes default
CACHE_MAXSIZE = int(os.getenv("CACHE_MAXSIZE", "1000"))
DEFAULT_FORECAST_DAYS = 3
MAX_FORECAST_DAYS = 7  # limit for provider compatibility

# Initialize
app = Flask(__name__)
app.config["SWAGGER"] = {
    "title": "Weather Aggregator API",
    "uiversion": 3,
}
Swagger(app)

# Rate limiter: e.g., 60 requests per minute per IP (adjust as needed)
# limiter = Limiter(app, key_func=get_remote_address, default_limits=["60/minute"])
limiter = Limiter(
    key_func=get_remote_address,
    default_limits=["60 per minute"]
)
limiter.init_app(app)

# Logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("weather_api")

# Simple TTL cache
cache = TTLCache(maxsize=CACHE_MAXSIZE, ttl=CACHE_TTL_SECONDS)


# ---------- Utilities ----------
def safe_request(url: str, params: Dict[str, Any], timeout: float = 5.0) -> Dict[str, Any]:
    """
    Make a GET request and return JSON with basic error handling.
    Retries once on network error.
    """
    try:
        resp = requests.get(url, params=params, timeout=timeout)
        resp.raise_for_status()
        return resp.json()
    except requests.RequestException as e:
        logger.warning("Request failed: %s %s %s", url, params, e)
        # try once more
        try:
            time.sleep(0.3)
            resp = requests.get(url, params=params, timeout=timeout)
            resp.raise_for_status()
            return resp.json()
        except Exception as e2:
            logger.error("Retry failed for %s: %s", url, e2)
            raise


def aggregated_current_from_providers(city: str) -> Dict[str, Any]:
    """
    Call multiple providers and aggregate results.
    Returns unified format:
    {
      "location": {"name": "City, Country", "lat": 12.34, "lon": 56.78},
      "temperature_c": 27.5,
      "feels_like_c": 27.0,
      "humidity": 78,
      "condition": "Partly cloudy",
      "sources": { "openweathermap": {...}, "weatherapi": {...} }
    }
    """
    results = {}
    sources = {}

    # Provider A: OpenWeatherMap (current)
    if OPENWEATHER_API_KEY:
        try:
            ow = safe_request(
                "https://api.openweathermap.org/data/2.5/weather",
                {"q": city, "appid": OPENWEATHER_API_KEY, "units": "metric"},
            )
            sources["openweathermap"] = ow
            results.setdefault("temps", []).append(float(ow["main"]["temp"]))
            results.setdefault("feels", []).append(float(ow["main"].get("feels_like", ow["main"]["temp"])))
            results.setdefault("humidities", []).append(int(ow["main"]["humidity"]))
            cond = ow.get("weather", [{}])[0].get("description", "")
            results.setdefault("conds", []).append(cond)
            location = {"name": f"{ow.get('name','')}, {ow.get('sys',{}).get('country','')}",
                        "lat": ow.get("coord", {}).get("lat"), "lon": ow.get("coord", {}).get("lon")}
        except Exception as e:
            logger.exception("OpenWeather failed: %s", e)

    # Provider B: WeatherAPI.com (current)
    if WEATHERAPI_KEY:
        try:
            wa = safe_request(
                "http://api.weatherapi.com/v1/current.json",
                {"key": WEATHERAPI_KEY, "q": city},
            )
            sources["weatherapi"] = wa
            cur = wa.get("current", {})
            results.setdefault("temps", []).append(float(cur["temp_c"]))
            results.setdefault("feels", []).append(float(cur.get("feelslike_c", cur.get("temp_c"))))
            results.setdefault("humidities", []).append(int(cur.get("humidity", 0)))
            results.setdefault("conds", []).append(cur.get("condition", {}).get("text", ""))
            loc = wa.get("location", {})
            location = {"name": f"{loc.get('name','')}, {loc.get('country','')}", "lat": loc.get("lat"), "lon": loc.get("lon")}
        except Exception as e:
            logger.exception("WeatherAPI failed: %s", e)

    if not results:
        raise RuntimeError("All external providers failed or no provider configured.")

    # Aggregate: mean for numeric; most-common for condition
    def mean(lst: List[float]) -> float:
        return sum(lst) / len(lst)

    temperature_c = round(mean(results["temps"]), 2)
    feels_like_c = round(mean(results["feels"]), 2)
    humidity = int(mean(results["humidities"]))
    # choose most common condition (or first)
    condition = max(results["conds"], key=lambda x: results["conds"].count(x)) if results["conds"] else ""

    return {
        "location": location,
        "temperature_c": temperature_c,
        "feels_like_c": feels_like_c,
        "humidity": humidity,
        "condition": condition,
        "sources": sources,
    }


def aggregated_forecast_from_providers(city: str, days: int) -> Dict[str, Any]:
    """
    Get aggregated forecast for `days` days. Returns list of daily summaries.
    Unified format:
    {
      "location": {...},
      "forecast": [
        {"date": "2025-09-26", "min_c": x, "max_c": y, "avg_c": z, "condition": "..."},
        ...
      ],
      "sources": {...}
    }
    """
    days = min(days, MAX_FORECAST_DAYS)
    sources = {}
    daily_aggregate = {}  # date -> list of temps, conditions, min, max

    # WeatherAPI forecast endpoint (often supports up to X days)
    if WEATHERAPI_KEY:
        try:
            wa = safe_request(
                "http://api.weatherapi.com/v1/forecast.json",
                {"key": WEATHERAPI_KEY, "q": city, "days": days},
            )
            sources["weatherapi"] = wa
            loc = wa.get("location", {})
            location = {"name": f"{loc.get('name','')}, {loc.get('country','')}", "lat": loc.get("lat"), "lon": loc.get("lon")}
            for day in wa.get("forecast", {}).get("forecastday", []):
                date = day.get("date")
                dayinfo = day.get("day", {})
                daily_aggregate.setdefault(date, {"temps": [], "mins": [], "maxs": [], "conds": []})
                daily_aggregate[date]["temps"].append(dayinfo.get("avgtemp_c"))
                daily_aggregate[date]["mins"].append(dayinfo.get("mintemp_c"))
                daily_aggregate[date]["maxs"].append(dayinfo.get("maxtemp_c"))
                daily_aggregate[date]["conds"].append(dayinfo.get("condition", {}).get("text", ""))
        except Exception as e:
            logger.exception("WeatherAPI forecast failed: %s", e)

    # OpenWeather 7-day One Call (requires lat/lon). We'll attempt quick geocoding then call OneCall
    if OPENWEATHER_API_KEY:
        try:
            # geocode
            ge = safe_request("http://api.openweathermap.org/geo/1.0/direct", {"q": city, "limit": 1, "appid": OPENWEATHER_API_KEY})
            if ge:
                lat = ge[0]["lat"]
                lon = ge[0]["lon"]
                oc = safe_request("https://api.openweathermap.org/data/2.5/onecall",
                                  {"lat": lat, "lon": lon, "appid": OPENWEATHER_API_KEY, "units": "metric", "exclude": "minutely,hourly,alerts"})
                sources["openweathermap"] = oc
                for day in oc.get("daily", [])[:days]:
                    date = time.strftime("%Y-%m-%d", time.gmtime(day.get("dt")))
                    daily_aggregate.setdefault(date, {"temps": [], "mins": [], "maxs": [], "conds": []})
                    # take day temp average from 'temp' object
                    temp_avg = day.get("temp", {}).get("day")
                    if temp_avg is not None:
                        daily_aggregate[date]["temps"].append(temp_avg)
                    daily_aggregate[date]["mins"].append(day.get("temp", {}).get("min"))
                    daily_aggregate[date]["maxs"].append(day.get("temp", {}).get("max"))
                    daily_aggregate[date]["conds"].append(day.get("weather", [{}])[0].get("description", ""))
                    location = {"name": city, "lat": lat, "lon": lon}
        except Exception as e:
            logger.exception("OpenWeather forecast failed: %s", e)

    if not daily_aggregate:
        raise RuntimeError("No forecast data available from configured providers.")

    forecast = []
    for date, data in sorted(daily_aggregate.items())[:days]:
        temps = [t for t in data["temps"] if t is not None]
        mins = [m for m in data["mins"] if m is not None]
        maxs = [M for M in data["maxs"] if M is not None]
        avg_c = round(sum(temps) / len(temps), 2) if temps else None
        day_min = round(min(mins), 2) if mins else None
        day_max = round(max(maxs), 2) if maxs else None
        condition = max(data["conds"], key=lambda x: data["conds"].count(x)) if data["conds"] else ""
        forecast.append({"date": date, "min_c": day_min, "max_c": day_max, "avg_c": avg_c, "condition": condition})

    return {"location": location, "forecast": forecast, "sources": sources}


# Cache wrappers
@cached(cache)
def cached_current(city: str) -> Dict[str, Any]:
    logger.info("Cache miss for current: %s", city)
    return aggregated_current_from_providers(city)


@cached(cache)
def cached_forecast(city: str, days: int) -> Dict[str, Any]:
    logger.info("Cache miss for forecast: %s days=%d", city, days)
    return aggregated_forecast_from_providers(city, days)


# ---------- Routes ----------
@app.route("/health", methods=["GET"])
@swag_from({
    "responses": {
        200: {
            "description": "Health check OK",
            "examples": {
                "application/json": {"status": "ok", "uptime_seconds": 12345}
            }
        }
    }
})
def health():
    """Health check endpoint"""
    return jsonify({"status": "ok", "uptime_seconds": int(time.time() - app.start_time)}), 200


@app.route("/locations/search", methods=["GET"])
@limiter.limit("30/minute")
@swag_from({
    "parameters": [
        {"name": "q", "in": "query", "type": "string", "required": True, "description": "Query (city or partial)"},
    ],
    "responses": {
        200: {
            "description": "List of matching locations",
            "examples": {
                "application/json": {"results": [{"name": "Paris, FR", "lat": 48.8566, "lon": 2.3522}]}
            }
        }
    }
})
def locations_search():
    q = request.args.get("q", "").strip()
    if not q:
        return jsonify({"error": "q query parameter required"}), 400

    # Try OpenWeather geocoding first if API key present; otherwise attempt WeatherAPI location search
    try:
        if OPENWEATHER_API_KEY:
            ge = safe_request("http://api.openweathermap.org/geo/1.0/direct", {"q": q, "limit": 10, "appid": OPENWEATHER_API_KEY})
            results = [{"name": f"{g.get('name')}, {g.get('country')}", "lat": g.get("lat"), "lon": g.get("lon")} for g in ge]
            return jsonify({"results": results[:10]})
        elif WEATHERAPI_KEY:
            wa = safe_request("http://api.weatherapi.com/v1/search.json", {"key": WEATHERAPI_KEY, "q": q})
            results = [{"name": f"{r.get('name')}, {r.get('country')}", "lat": r.get("lat"), "lon": r.get("lon")} for r in wa]
            return jsonify({"results": results})
        else:
            return jsonify({"error": "No geocoding provider configured (set OPENWEATHER_API_KEY or WEATHERAPI_KEY)."}), 500
    except Exception as e:
        logger.exception("locations_search error: %s", e)
        return jsonify({"error": "Failed to search locations", "details": str(e)}), 502


@app.route("/weather/current", methods=["GET"])
@limiter.limit("60/minute")
@swag_from({
    "parameters": [
        {"name": "location", "in": "query", "type": "string", "required": True},
    ],
    "responses": {
        200: {
            "description": "Aggregated current weather",
            "examples": {
                "application/json": {
                    "location": {"name": "Berlin, DE", "lat": 52.52, "lon": 13.405},
                    "temperature_c": 16.5,
                    "feels_like_c": 15.8,
                    "humidity": 72,
                    "condition": "Light rain",
                    "sources": {"openweathermap": {}, "weatherapi": {}}
                }
            }
        },
        400: {"description": "Bad request"},
        502: {"description": "Provider failure"}
    }
})
def current_weather():
    location = request.args.get("location", "").strip()
    if not location:
        return jsonify({"error": "location query parameter is required"}), 400

    try:
        data = cached_current(location)
        return jsonify(data), 200
    except RuntimeError as e:
        logger.error("All providers failed: %s", e)
        return jsonify({"error": "All providers failed", "details": str(e)}), 502
    except Exception as e:
        logger.exception("Unexpected error in /weather/current: %s", e)
        return jsonify({"error": "Internal server error", "details": str(e)}), 500


@app.route("/weather/forecast", methods=["GET"])
@limiter.limit("60/minute")
@swag_from({
    "parameters": [
        {"name": "location", "in": "query", "type": "string", "required": True},
        {"name": "days", "in": "query", "type": "integer", "required": False, "default": DEFAULT_FORECAST_DAYS}
    ],
    "responses": {
        200: {"description": "Aggregated forecast"},
        400: {"description": "Bad request"},
        502: {"description": "Provider failure"}
    }
})
def forecast_weather():
    location = request.args.get("location", "").strip()
    try:
        days = int(request.args.get("days", DEFAULT_FORECAST_DAYS))
    except ValueError:
        return jsonify({"error": "days must be an integer"}), 400

    if not location:
        return jsonify({"error": "location query parameter is required"}), 400
    if days <= 0 or days > MAX_FORECAST_DAYS:
        return jsonify({"error": f"days must be between 1 and {MAX_FORECAST_DAYS}"}), 400

    try:
        data = cached_forecast(location, days)
        return jsonify(data), 200
    except RuntimeError as e:
        logger.error("All providers failed for forecast: %s", e)
        return jsonify({"error": "All providers failed", "details": str(e)}), 502
    except Exception as e:
        logger.exception("Unexpected error in /weather/forecast: %s", e)
        return jsonify({"error": "Internal server error", "details": str(e)}), 500


# ---------- App start ----------
# @app.before_first_request
# def _record_start_time():
#     app.start_time = time.time()
@app.before_request
def _record_start_time():
    if not hasattr(app, "start_time"):
        app.start_time = time.time()


# Basic root page
@app.route("/", methods=["GET"])
def root():
    return jsonify({
        "message": "Weather Aggregator API. See /apidocs for Swagger UI.",
        "endpoints": ["/weather/current", "/weather/forecast", "/locations/search", "/health"]
    })


# Error handlers
@app.errorhandler(429)
def ratelimit_handler(e):
    return jsonify({"error": "rate limit exceeded", "details": str(e)}), 429


if __name__ == "__main__":
    # For local dev only; use gunicorn/uvicorn + workers in prod.
    app.run(host="0.0.0.0", port=int(os.getenv("PORT", 5000)), debug=(os.getenv("FLASK_DEBUG") == "1"))

