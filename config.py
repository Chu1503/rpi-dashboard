"""Application configuration loaded from environment variables."""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv


BASE_DIR = Path(__file__).resolve().parent
load_dotenv(BASE_DIR / ".env")


def _int(name: str, default: int) -> int:
    try:
        return int(os.getenv(name, str(default)))
    except ValueError:
        return default


def _float_or_none(name: str) -> float | None:
    value = os.getenv(name, "").strip()
    if not value:
        return None
    try:
        return float(value)
    except ValueError:
        return None


def _bool(name: str, default: bool = False) -> bool:
    return os.getenv(name, str(default)).strip().lower() in {"1", "true", "yes", "on"}


@dataclass(frozen=True)
class Settings:
    base_dir: Path = BASE_DIR
    display_name: str = os.getenv("DISPLAY_NAME", "Chu").strip() or "Chu"
    host: str = os.getenv("ALFRED_HOST", "127.0.0.1")
    port: int = _int("ALFRED_PORT", 8080)
    dashboard_time_zone: str = os.getenv("DASHBOARD_TIME_ZONE", "").strip()
    weather_lat: float | None = _float_or_none("WEATHER_LAT")
    weather_lon: float | None = _float_or_none("WEATHER_LON")
    calendar_id: str = os.getenv("GOOGLE_CALENDAR_ID", "primary").strip() or "primary"
    calendar_days: int = _int("CALENDAR_DAYS", 14)
    max_tasks: int = min(14, max(1, _int("MAX_TASKS", 14)))
    max_events: int = min(8, max(1, _int("MAX_EVENTS", 8)))
    calendar_ttl: int = _int("CALENDAR_CACHE_SECONDS", 60)
    tasks_ttl: int = _int("TASKS_CACHE_SECONDS", 60)
    weather_ttl: int = _int("WEATHER_CACHE_SECONDS", 600)
    health_ttl: int = _int("HEALTH_CACHE_SECONDS", 600)
    steps_ttl: int = _int("STEPS_CACHE_SECONDS", 120)
    heart_rate_ttl: int = _int("HEART_RATE_CACHE_SECONDS", 120)
    request_timeout: int = _int("EXTERNAL_REQUEST_TIMEOUT_SECONDS", 12)
    demo_mode: bool = _bool("ALFRED_DEMO_MODE")
    tv_remote_token: str = os.getenv("TV_REMOTE_TOKEN", "").strip()
    tv_bridge_socket: str = os.getenv(
        "TV_BRIDGE_SOCKET", "/var/run/arduino-router.sock"
    ).strip() or "/var/run/arduino-router.sock"
    tv_rpc_timeout: float = max(0.25, float(os.getenv("TV_RPC_TIMEOUT_SECONDS", "3")))
    voice_input_enabled: bool = _bool("ALFRED_VOICE_INPUT_ENABLED")
    mic_device: str = os.getenv("ALFRED_MIC_DEVICE", "").strip()
    wake_word: str = os.getenv("ALFRED_WAKE_WORD", "Alfred").strip() or "Alfred"
    wake_words: tuple[str, ...] = tuple(
        part.strip()
        for part in os.getenv("ALFRED_WAKE_WORDS", "Alfred,Computer,Jarvis").split(",")
        if part.strip()
    )
    wake_aliases: tuple[str, ...] = tuple(
        part.strip()
        for part in os.getenv(
            "ALFRED_WAKE_ALIASES",
            "Alfred,Alford,Fred,Computer,Jarvis,Jervis",
        ).split(",")
        if part.strip()
    )
    voice_sample_rate: int = max(8_000, min(48_000, _int("ALFRED_VOICE_SAMPLE_RATE", 16_000)))

    @property
    def secrets_dir(self) -> Path:
        return self.base_dir / "data" / "secrets"

    @property
    def cache_dir(self) -> Path:
        return self.base_dir / "data" / "cache"

    @property
    def voice_model_path(self) -> Path:
        configured = os.getenv(
            "ALFRED_VOSK_MODEL", "data/voices/vosk-model-small-en-us-0.15"
        ).strip()
        path = Path(configured).expanduser()
        return path if path.is_absolute() else self.base_dir / path


settings = Settings()
