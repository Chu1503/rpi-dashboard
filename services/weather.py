"""Open-Meteo current weather service (no API key required)."""

from __future__ import annotations

import requests

from config import Settings
from services.cache import CachedService


WEATHER_CODES = {
    0: "Clear sky", 1: "Mostly clear", 2: "Partly cloudy", 3: "Overcast",
    45: "Fog", 48: "Rime fog", 51: "Light drizzle", 53: "Drizzle", 55: "Heavy drizzle",
    56: "Freezing drizzle", 57: "Heavy freezing drizzle", 61: "Light rain", 63: "Rain",
    65: "Heavy rain", 66: "Freezing rain", 67: "Heavy freezing rain", 71: "Light snow",
    73: "Snow", 75: "Heavy snow", 77: "Snow grains", 80: "Light showers",
    81: "Showers", 82: "Heavy showers", 85: "Snow showers", 86: "Heavy snow showers",
    95: "Thunderstorm", 96: "Thunderstorm with hail", 99: "Heavy hail storm",
}


class WeatherService:
    def __init__(self, settings: Settings):
        self.settings = settings
        self.cache = CachedService("weather", settings.cache_dir, settings.weather_ttl)

    def get(self, force: bool = False, allow_stale: bool = False) -> dict:
        return self.cache.get(
            self._fetch,
            {"temperature_c": None, "condition": None},
            force=force,
            allow_stale=allow_stale,
            persist_success=not self.settings.demo_mode,
        )

    def _fetch(self) -> dict:
        if self.settings.demo_mode:
            return {"temperature_c": 21.0, "condition": "Partly cloudy"}
        if self.settings.weather_lat is None or self.settings.weather_lon is None:
            raise RuntimeError("WEATHER_LAT and WEATHER_LON are not configured")
        response = requests.get(
            "https://api.open-meteo.com/v1/forecast",
            params={
                "latitude": self.settings.weather_lat,
                "longitude": self.settings.weather_lon,
                "current": "temperature_2m,weather_code",
                "temperature_unit": "celsius",
                "timezone": "auto",
            },
            timeout=self.settings.request_timeout,
        )
        response.raise_for_status()
        current = response.json()["current"]
        code = int(current["weather_code"])
        return {
            "temperature_c": round(float(current["temperature_2m"]), 1),
            "condition": WEATHER_CODES.get(code, "Unknown conditions"),
        }
