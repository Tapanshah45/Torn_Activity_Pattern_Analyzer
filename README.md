# Torn City Inactivity & Sleep Pattern Analysis Engine

A high-performance Python utility that ingests Torn City faction campaign snapshots to reconstruct player routines, distinguish sleep cycles from AFK/work periods, infer timezones, and output structured reports via CLI and JSON.

## Features

- **Streaming ingestion** via `ijson` — handles hundreds of MB without loading everything into memory
- **Flight vs. sleep disambiguation** — passive travel is separated from genuine offline periods
- **Circular mean math** — correctly averages sleep times that cross midnight UTC
- **Timezone inference** — estimates each player's UTC offset from their sleep midpoint
- **Rich CLI table** output + optional JSON export
- **Standalone binary** packaging via PyInstaller

## Quick Start

```sh
# 1. Create and activate virtual environment
python -m venv .venv
.venv\Scripts\activate        # Windows
# source .venv/bin/activate   # Linux / macOS

# 2. Install dependencies
pip install -r requirements.txt

# 3. Run analysis
python src/cli.py --file campaign_21.json --json-out report.json

# 4. Run tests
pytest tests/ -v

# 5. Build standalone .exe (Windows)
python build.py
```

## CLI Options

| Flag | Short | Description |
|------|-------|-------------|
| `--file` | `-f` | Path to campaign JSON file (required) |
| `--min-sleep` | | Minimum inactivity gap in hours (default: 4.0) |
| `--json-out` | `-j` | Path to write JSON export |
| `--quiet` | `-q` | Suppress table output |

## Output JSON Schema

Each player entry in the JSON export contains:

```json
{
  "player_id": 3495155,
  "name": "Rustirc",
  "total_snapshots": 250,
  "estimated_sleep_window_utc": "22:30 - 06:30",
  "avg_sleep_duration_hours": 8.0,
  "inferred_timezone": "UTC+5",
  "peak_active_hours_utc": [14, 15, 16, 17],
  "primary_sleep_cycles": [...],
  "secondary_afk_blocks": [...]
}
```

## Project Structure

```
torn_analyzer/
├── pyproject.toml
├── requirements.txt
├── README.md
├── build.py
├── src/
│   ├── __init__.py
│   ├── models.py        — Pydantic data models
│   ├── streamer.py      — ijson streaming ingestion
│   ├── classifier.py    — gap detection, classification logic
│   ├── stats.py         — circular mean math, timezone inference
│   ├── engine.py        — orchestration layer
│   └── cli.py           — Rich CLI entry point
└── tests/
    ├── __init__.py
    ├── test_circular_math.py
    ├── test_flight_logic.py
    └── test_classification.py
```

The Python libraries used across the project are categorized into external dependencies and standard library modules:

### 1. External Third-Party Libraries (from `requirements.txt`)

* **`ijson`**: Used for memory-efficient, chunked streaming parsing of large JSON files without loading entire multi-megabyte/gigabyte arrays into RAM.
* **`pydantic`**: Used for schema modeling, data type validation, and serialization of snapshots and player profile models.
* **`rich`**: Used to build and render the interactive CLI interface and formatted terminal tables.
* **`pytest`**: Used to run automated unit tests for circular mathematics, flight filtering, and activity classification.
* **`pyinstaller`**: Used to compile the Python source code into a standalone, single-file binary executable (`.exe`).

---

### 2. Python Built-in Standard Libraries

* **`datetime`** (`datetime`, `timezone`, `timedelta`): Handles ISO 8601 parsing, UTC time manipulation, and timestamp comparisons.
* **`collections`** (`defaultdict`): Aggregates hourly activity counters and partitions daily 24-hour gap buckets.
* **`typing`** (`List`, `Dict`, `Any`, `Optional`, `Tuple`, `Generator`): Provides static type hinting across functions and classes.
* **`math`**: Used for trigonometry functions (`sin`, `cos`, `atan2`, `pi`) to calculate circular means across UTC midnight.
* **`json`**: Serializes exported player activity reports to disk.
* **`argparse`**: Handles command-line arguments and flags (`--file`, `--min-sleep`, `--json-out`, etc.).
* **`sys`**: Manages command-line arguments and handles system exit calls on file read errors.
* **`platform`**: Inspects the host operating system to determine file extensions (`.exe` on Windows) during build generation.