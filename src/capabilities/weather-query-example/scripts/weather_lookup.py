from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys


DATA_FILE = (
    Path(__file__).resolve().parent.parent / "references" / "example-weather-data.json"
)


def load_weather_data() -> dict[str, dict[str, object]]:
    return json.loads(DATA_FILE.read_text(encoding="utf-8"))


def normalize_city(city: str, weather_data: dict[str, dict[str, object]]) -> str | None:
    requested = city.strip().lower()
    for known_city in weather_data:
        if known_city.lower() == requested:
            return known_city
    return None


def build_output(city: str) -> str:
    weather_data = load_weather_data()
    normalized_city = normalize_city(city, weather_data)
    if normalized_city is None:
        supported = ", ".join(sorted(weather_data))
        return f"Unsupported city: {city}. Supported example cities: {supported}"

    record = weather_data[normalized_city]
    return (
        f"{normalized_city}: {record['temperature_c']}C, {record['condition']}, "
        f"humidity {record['humidity_pct']}%"
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Local example weather lookup.")
    parser.add_argument("--city", required=True, help="City name to query.")
    args = parser.parse_args(argv)
    print(build_output(args.city))
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
