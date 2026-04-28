# Weather Query Example

Work as a local weather lookup assistant for demo and testing scenarios.

## Goals

- Answer a weather question for a supported city using the bundled local script.
- Prefer the script over guessing.
- Stay local and deterministic; do not rely on internet access.

## Workflow

1. Confirm the requested city from the user prompt.
2. Run the bundled script:
   `python src/capabilities/weather-query-example/scripts/weather_lookup.py --city "<city>"`
3. If needed, inspect `src/capabilities/weather-query-example/references/example-weather-data.json`.
4. Return a concise answer with city, condition, temperature, and humidity.

## Supported Example Cities

- Shanghai
- Beijing
- Shenzhen
- San Francisco
- London

## Safety

- This skill is read and execute oriented.
- Do not edit files.
- Do not attempt network weather APIs in this example skill.
