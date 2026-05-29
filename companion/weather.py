"""Lexa AI — Weather Integration (Open-Meteo — FREE, no API key needed!)
Uses Open-Meteo.com for weather data + geocoding.
No registration, no API key, no credit card. 10,000 calls/day free.
"""

import logging
import time
from typing import Optional
from datetime import datetime

import requests

logger = logging.getLogger("lexa.weather")

# ── Cache (TTL 10 minutes) ──
_cache: dict[str, dict] = {}
_CACHE_TTL = 600  # 10 minutes

# ── WMO Weather Code → Emoji + Description (German) ──
_WMO_CODES = {
    0: ("☀️", "Klar"),
    1: ("🌤️", "Überwiegend klar"),
    2: ("⛅", "Teilweise bewölkt"),
    3: ("☁️", "Bewölkt"),
    45: ("🌫️", "Nebel"),
    48: ("🌫️", "Reifnebel"),
    51: ("🌦️", "Leichter Nieselregen"),
    53: ("🌦️", "Nieselregen"),
    55: ("🌧️", "Starker Nieselregen"),
    56: ("🌧️", "Gefrierender Nieselregen"),
    57: ("🌧️", "Starker gefrierender Nieselregen"),
    61: ("🌦️", "Leichter Regen"),
    63: ("🌧️", "Regen"),
    65: ("🌧️", "Starker Regen"),
    66: ("🌧️", "Gefrierender Regen"),
    67: ("🌧️", "Starker gefrierender Regen"),
    71: ("❄️", "Leichter Schneefall"),
    73: ("❄️", "Schneefall"),
    75: ("❄️", "Starker Schneefall"),
    77: ("❄️", "Schneegriesel"),
    80: ("🌦️", "Leichte Regenschauer"),
    81: ("🌧️", "Regenschauer"),
    82: ("🌧️", "Starke Regenschauer"),
    85: ("🌨️", "Leichte Schneeschauer"),
    86: ("🌨️", "Starke Schneeschauer"),
    95: ("⛈️", "Gewitter"),
    96: ("⛈️", "Gewitter mit leichtem Hagel"),
    99: ("⛈️", "Gewitter mit starkem Hagel"),
}


def _wmo_to_emoji(code: int) -> str:
    return _WMO_CODES.get(code, ("🌤️", "Unbekannt"))[0]


def _wmo_to_description(code: int) -> str:
    return _WMO_CODES.get(code, ("🌤️", "Unbekannt"))[1]


def _cache_get(key: str) -> Optional[dict]:
    entry = _cache.get(key)
    if entry and (time.time() - entry["ts"]) < _CACHE_TTL:
        return entry["data"]
    return None


def _cache_set(key: str, data: dict) -> None:
    _cache[key] = {"data": data, "ts": time.time()}


def _geocode(city: str) -> Optional[dict]:
    """Convert city name to lat/lon using Open-Meteo Geocoding API (free, no key)."""
    cache_key = f"geo:{city.lower()}"
    cached = _cache_get(cache_key)
    if cached:
        return cached

    try:
        resp = requests.get(
            "https://geocoding-api.open-meteo.com/v1/search",
            params={"name": city, "count": 1, "language": "de"},
            timeout=5,
        )
        if resp.status_code == 200:
            data = resp.json()
            results = data.get("results", [])
            if results:
                loc = {
                    "lat": results[0]["latitude"],
                    "lon": results[0]["longitude"],
                    "name": results[0].get("name", city),
                    "country": results[0].get("country", ""),
                }
                _cache_set(cache_key, loc)
                return loc
    except Exception as e:
        logger.warning(f"Geocoding error for '{city}': {e}")
    return None


def _get_default_city() -> Optional[str]:
    """Get default city from user profile, fallback to IP geolocation."""
    try:
        from backend.memory import _get_db
        db = _get_db()
        row = db.execute(
            "SELECT value FROM user_profile WHERE key = 'city'",
        ).fetchone()
        if row and row["value"]:
            return row["value"]
    except Exception:
        pass

    try:
        resp = requests.get("http://ip-api.com/json/?fields=city", timeout=3)
        if resp.status_code == 200:
            city = resp.json().get("city")
            if city:
                return city
    except Exception:
        pass
    return None


# ══════════════════════════════════════════════════
#  PUBLIC API
# ══════════════════════════════════════════════════

def weather_current(city: str = "") -> dict:
    """Current weather via Open-Meteo (FREE, no API key needed).
    Returns: city, temp, feels_like, description, humidity, wind_speed, icon."""
    city = city.strip() if city else None
    if not city:
        city = _get_default_city()
    if not city:
        return {"error": "Keine Stadt angegeben. Sag z.B. 'Wetter in Hamburg'."}

    # Check cache
    cache_key = f"current:{city.lower()}"
    cached = _cache_get(cache_key)
    if cached:
        return cached

    # Geocode city to lat/lon
    loc = _geocode(city)
    if not loc:
        return {"error": f"Stadt '{city}' nicht gefunden."}

    try:
        resp = requests.get(
            "https://api.open-meteo.com/v1/forecast",
            params={
                "latitude": loc["lat"],
                "longitude": loc["lon"],
                "current": "temperature_2m,relative_humidity_2m,apparent_temperature,weather_code,wind_speed_10m,wind_direction_10m",
                "timezone": "Europe/Berlin",
            },
            timeout=10,
        )
        resp.raise_for_status()
        data = resp.json()
    except requests.RequestException as e:
        logger.warning(f"Open-Meteo API error: {e}")
        return {"error": f"Wetter-API Fehler: {e}"}

    current = data.get("current", {})
    wmo_code = current.get("weather_code", 0)

    result = {
        "city": loc["name"],
        "temp": current.get("temperature_2m", 0),
        "feels_like": current.get("apparent_temperature", 0),
        "description": _wmo_to_description(wmo_code),
        "humidity": current.get("relative_humidity_2m", 0),
        "wind_speed": current.get("wind_speed_10m", 0),
        "icon": _wmo_to_emoji(wmo_code),
        "summary": f"{_wmo_to_emoji(wmo_code)} {loc['name']}: {current.get('temperature_2m', 0)}°C, {_wmo_to_description(wmo_code)}. Gefühlt {current.get('apparent_temperature', 0)}°C. Luftfeuchtigkeit {current.get('relative_humidity_2m', 0)}%, Wind {current.get('wind_speed_10m', 0)} km/h.",
    }

    _cache_set(cache_key, result)
    return result


def weather_forecast(city: str = "", days: int = 3) -> dict:
    """3-day forecast via Open-Meteo (FREE)."""
    city = city.strip() if city else None
    if not city:
        city = _get_default_city()
    if not city:
        return {"error": "Keine Stadt angegeben."}

    days = max(1, min(7, int(days)))

    cache_key = f"forecast:{city.lower()}:{days}"
    cached = _cache_get(cache_key)
    if cached:
        return cached

    loc = _geocode(city)
    if not loc:
        return {"error": f"Stadt '{city}' nicht gefunden."}

    try:
        resp = requests.get(
            "https://api.open-meteo.com/v1/forecast",
            params={
                "latitude": loc["lat"],
                "longitude": loc["lon"],
                "daily": "temperature_2m_max,temperature_2m_min,weather_code,precipitation_probability_max,wind_speed_10m_max",
                "timezone": "Europe/Berlin",
                "forecast_days": days,
            },
            timeout=10,
        )
        resp.raise_for_status()
        data = resp.json()
    except requests.RequestException as e:
        logger.warning(f"Open-Meteo forecast error: {e}")
        return {"error": f"Wetter-API Fehler: {e}"}

    daily = data.get("daily", {})
    dates = daily.get("time", [])
    temp_max = daily.get("temperature_2m_max", [])
    temp_min = daily.get("temperature_2m_min", [])
    codes = daily.get("weather_code", [])
    rain_prob = daily.get("precipitation_probability_max", [])

    forecast_days = []
    for i in range(min(days, len(dates))):
        try:
            dt = datetime.strptime(dates[i], "%Y-%m-%d")
            label = dt.strftime("%A, %d.%m.")
        except (ValueError, IndexError):
            label = dates[i] if i < len(dates) else f"Tag {i + 1}"

        wmo = codes[i] if i < len(codes) else 0
        forecast_days.append({
            "date": dates[i] if i < len(dates) else "",
            "label": label,
            "temp_min": temp_min[i] if i < len(temp_min) else 0,
            "temp_max": temp_max[i] if i < len(temp_max) else 0,
            "description": _wmo_to_description(wmo),
            "icon": _wmo_to_emoji(wmo),
            "rain_probability": rain_prob[i] if i < len(rain_prob) else 0,
        })

    result = {
        "city": loc["name"],
        "days": forecast_days,
        "summary": f"Vorhersage {loc['name']}: " + " | ".join(
            f"{d['label']}: {d['icon']} {d['temp_min']}-{d['temp_max']}°C"
            for d in forecast_days
        ),
    }

    _cache_set(cache_key, result)
    return result


def weather_will_it_rain(city: str = "") -> dict:
    """Rain check for next 24h via Open-Meteo (FREE)."""
    city = city.strip() if city else None
    if not city:
        city = _get_default_city()
    if not city:
        return {"error": "Keine Stadt angegeben."}

    loc = _geocode(city)
    if not loc:
        return {"error": f"Stadt '{city}' nicht gefunden."}

    cache_key = f"rain:{city.lower()}"
    cached = _cache_get(cache_key)
    if cached:
        return cached

    try:
        resp = requests.get(
            "https://api.open-meteo.com/v1/forecast",
            params={
                "latitude": loc["lat"],
                "longitude": loc["lon"],
                "hourly": "precipitation_probability,precipitation",
                "timezone": "Europe/Berlin",
                "forecast_days": 1,
            },
            timeout=10,
        )
        resp.raise_for_status()
        data = resp.json()
    except requests.RequestException as e:
        return {"error": f"Wetter-API Fehler: {e}"}

    hourly = data.get("hourly", {})
    times = hourly.get("time", [])
    probs = hourly.get("precipitation_probability", [])
    amounts = hourly.get("precipitation", [])

    rain_entries = []
    for i in range(len(times)):
        prob = probs[i] if i < len(probs) else 0
        amount = amounts[i] if i < len(amounts) else 0
        if prob > 30 or amount > 0:
            try:
                dt = datetime.strptime(times[i], "%Y-%m-%dT%H:%M")
                time_str = dt.strftime("%H:%M")
            except (ValueError, IndexError):
                time_str = times[i]
            rain_entries.append({
                "time": time_str,
                "probability": prob,
                "amount_mm": round(amount, 1),
            })

    if rain_entries:
        first = rain_entries[0]
        result = {
            "city": loc["name"],
            "will_rain": True,
            "probability": first["probability"],
            "expected_time": first["time"],
            "message": f"Ja, es wird wahrscheinlich regnen in {loc['name']}. Ab ca. {first['time']} Uhr ({first['probability']}% Wahrscheinlichkeit).",
            "details": rain_entries[:8],
        }
    else:
        result = {
            "city": loc["name"],
            "will_rain": False,
            "probability": 0,
            "message": f"Nein, kein Regen in den nächsten 24 Stunden in {loc['name']}.",
        }

    _cache_set(cache_key, result)
    return result


def get_weather_status() -> dict:
    """Weather API status — Open-Meteo needs no key!"""
    return {
        "configured": True,  # Always available — no API key needed!
        "service": "Open-Meteo (FREE)",
    }
