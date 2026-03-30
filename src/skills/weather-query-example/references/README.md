# Weather Query Example References

This skill is intentionally local and deterministic.

The bundled script reads `example-weather-data.json` and returns a formatted weather summary for a supported city.

Example command:

```bash
python src/skills/weather-query-example/scripts/weather_lookup.py --city "Shanghai"
```

Expected example output:

```text
Shanghai: 22C, Sunny, humidity 48%
```
