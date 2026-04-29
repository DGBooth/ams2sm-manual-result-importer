# AMS2 Manual Result Importer

A small Flask web app for manually entering race finishing order into an [AMS2 Server Manager](https://github.com/JustaPenguin/assetto-server-manager) championship. Use this when a race session result is missing or corrupted and needs to be reconstructed by hand.

## Requirements

- Python 3.9+
- Flask

## Installation

```bash
git clone https://github.com/dgbooth/ams2sm-manual-result-importer.git
cd ams2sm-manual-result-importer
pip install -r requirements.txt
```

## Running

```bash
python app.py
```

Then open [http://localhost:5000](http://localhost:5000) in your browser.

> The server must be reachable from wherever the `store.json` folder lives. If you're running the importer directly on the race server, `localhost` is fine. If the store is on a remote machine, run the app there (or mount the path).

## Usage

### 1. Connect to the store

Enter the full path to the `store.json` **folder** (the directory with the `.json` extension, not a file inside it). It must contain a `championships/` subdirectory.

```
/home/user/server-manager/store.json
```

### 2. Select a championship

Pick the championship you want to modify from the list.

### 3. Select an event

Events are listed with their creation date and completion status. A badge shows whether a race result already exists — if one does, submitting will **overwrite it** (a timestamped backup is always created first).

### 4. Enter finishers

Fill in the form:

| Field | Description |
|---|---|
| **Race Date & Time** | Pre-filled from the event's completion time. Treated as UTC. Sets `Session.CompletedTime` and `Result.Date`. |
| **Car Model ID / Name** | Auto-filled from existing results in the championship. Edit if wrong. |
| **Track ID** | Auto-filled from existing results. Cosmetic only — does not affect points. |
| **Finishing Order** | One driver per line, 1st to last. |

**Finisher format** — one driver per line:

```
Chiefyk
SecondDriver,76561198012345678
ThirdDriver	76561198087654321
```

Comma or tab separates the driver name from their optional Steam64 GUID. If a GUID is omitted, the app looks it up automatically from the driver's previous results in the same championship.

Known drivers from the championship's history appear as clickable chips below the textarea — click any name to append it to the list.

### 5. Confirm

A summary of what was written is displayed. **Restart the AMS2 Server Manager** for the changes to take effect.

## Backups

Before every write, the original championship file is copied to:

```
store.json/championships/<uuid>.json.bak.<YYYYMMDD_HHMMSS>
```

Backups are not cleaned up automatically. Remove old ones manually if needed.

## Common mistakes

**Points not appearing after import** — Two known causes:

1. `Session.CompletedTime` was left as `0001-01-01T00:00:00Z` (Go's zero time). The server treats sessions with this timestamp as incomplete. This app always sets it to the submitted race datetime.

2. `Place.Class` was set to a non-empty string (e.g. `"Sprint Race"`). This causes the server to create a separate sub-standings category instead of counting results in the main Drivers standings. This app always sets `Class` to `""` for single-class championships.

## Running tests

```bash
pip install pytest
python -m pytest test_app.py -v
```
