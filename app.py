import json
import os
import shutil
import uuid
from datetime import datetime, timezone
from pathlib import Path

from flask import Flask, flash, redirect, render_template, request, session, url_for

app = Flask(__name__)
app.secret_key = os.environ.get("SECRET_KEY", os.urandom(24))

GO_ZERO_TIME = "0001-01-01T00:00:00Z"


def champ_path(store_path, champ_id):
    return Path(store_path) / "championships" / f"{champ_id}.json"


def load_championship(store_path, champ_id):
    with open(champ_path(store_path, champ_id)) as f:
        return json.load(f)


def save_championship(store_path, champ_id, data):
    path = champ_path(store_path, champ_id)
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    shutil.copy2(path, path.with_suffix(f".json.bak.{ts}"))
    with open(path, "w") as f:
        json.dump(data, f, indent=2)


def list_championships(store_path):
    champs_dir = Path(store_path) / "championships"
    championships = []
    for f in sorted(champs_dir.glob("*.json")):
        if ".bak." in f.name:
            continue
        try:
            with open(f) as fh:
                data = json.load(fh)
            championships.append(
                {
                    "id": data["ID"],
                    "name": data["Name"],
                    "event_count": len(data.get("Events", [])),
                }
            )
        except Exception:
            pass
    return championships


def find_car_model(champ_data):
    """Return (CarModelID, CarModel) from the first result found in the championship."""
    for event in champ_data.get("Events", []):
        for sess in event.get("Sessions", []):
            results = sess.get("Results")
            if results and results.get("Places"):
                p = results["Places"][0]
                return p.get("CarModelID", ""), p.get("CarModel", "")
    return "", ""


def find_track_id(champ_data):
    """Return TrackID from the first result found in the championship."""
    for event in champ_data.get("Events", []):
        for sess in event.get("Sessions", []):
            results = sess.get("Results")
            if results and results.get("TrackID"):
                return results["TrackID"]
    return ""


def find_driver_info(champ_data, name):
    """Return (GUID, DriverID) for a driver name from existing results."""
    for event in champ_data.get("Events", []):
        for sess in event.get("Sessions", []):
            results = sess.get("Results")
            if not results:
                continue
            for place in results.get("Places", []):
                for driver in place.get("Drivers", []):
                    if driver.get("Name") == name:
                        return driver.get("GUID", ""), driver.get("DriverID", 0)
    return "", 0


def known_drivers(champ_data):
    """Return a sorted list of unique driver names seen in the championship."""
    seen = set()
    for event in champ_data.get("Events", []):
        for sess in event.get("Sessions", []):
            results = sess.get("Results")
            if not results:
                continue
            for place in results.get("Places", []):
                for driver in place.get("Drivers", []):
                    name = driver.get("Name", "").strip()
                    if name:
                        seen.add(name)
    return sorted(seen)


def parse_finishers(raw):
    """Parse textarea input: one driver per line, optional GUID after comma or tab."""
    finishers = []
    for line in raw.splitlines():
        line = line.strip()
        if not line:
            continue
        if "\t" in line:
            name, _, guid = line.partition("\t")
        elif "," in line:
            name, _, guid = line.partition(",")
        else:
            name, guid = line, ""
        name = name.strip()
        guid = guid.strip()
        if name:
            finishers.append({"name": name, "guid": guid})
    return finishers


def format_dt_rfc3339(dt_local_str):
    """Convert datetime-local input ('YYYY-MM-DDTHH:MM') to RFC3339 UTC string."""
    # datetime-local has no timezone; treat as UTC
    return dt_local_str + ":00Z"


def format_dt_for_filename(rfc3339):
    return rfc3339.replace(":", "-").replace("T", "_").rstrip("Z").split("+")[0]


# ─── Routes ──────────────────────────────────────────────────────────────────


@app.route("/", methods=["GET", "POST"])
def index():
    if request.method == "POST":
        store_path = request.form.get("store_path", "").strip()
        champs_dir = Path(store_path) / "championships"
        if not champs_dir.is_dir():
            flash(f"championships/ directory not found inside: {store_path}", "error")
            return render_template("index.html", store_path=store_path)
        session["store_path"] = store_path
        return redirect(url_for("select_championship"))
    return render_template("index.html", store_path=session.get("store_path", ""))


@app.route("/championships")
def select_championship():
    store_path = session.get("store_path")
    if not store_path:
        return redirect(url_for("index"))
    championships = list_championships(store_path)
    return render_template("championships.html", championships=championships, store_path=store_path)


@app.route("/events/<champ_id>")
def select_event(champ_id):
    store_path = session.get("store_path")
    if not store_path:
        return redirect(url_for("index"))
    champ = load_championship(store_path, champ_id)
    events = []
    for i, event in enumerate(champ.get("Events", [])):
        race_sessions = [s for s in event.get("Sessions", []) if s.get("Type") == 2]
        has_result = any(s.get("Results") is not None for s in race_sessions)
        completed = event.get("CompletedTime", GO_ZERO_TIME)
        events.append(
            {
                "index": i + 1,
                "id": event["ID"],
                "created": event.get("Created", ""),
                "completed": completed,
                "completed_is_zero": completed == GO_ZERO_TIME,
                "race_count": len(race_sessions),
                "has_result": has_result,
            }
        )
    return render_template("events.html", champ=champ, events=events)


@app.route("/finishers/<champ_id>/<event_id>")
def enter_finishers(champ_id, event_id):
    store_path = session.get("store_path")
    if not store_path:
        return redirect(url_for("index"))
    champ = load_championship(store_path, champ_id)
    event = next((e for e in champ.get("Events", []) if e["ID"] == event_id), None)
    if not event:
        flash("Event not found.", "error")
        return redirect(url_for("select_event", champ_id=champ_id))

    car_model_id, car_model = find_car_model(champ)
    track_id = find_track_id(champ)
    drivers = known_drivers(champ)

    # Default race time: event CompletedTime if set, else now
    completed = event.get("CompletedTime", GO_ZERO_TIME)
    if completed == GO_ZERO_TIME:
        completed = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    # Strip seconds+Z for datetime-local input
    race_datetime_local = completed[:16]

    race_sessions = [s for s in event.get("Sessions", []) if s.get("Type") == 2]

    return render_template(
        "finishers.html",
        champ=champ,
        event=event,
        race_sessions=race_sessions,
        car_model_id=car_model_id,
        car_model=car_model,
        track_id=track_id,
        race_datetime_local=race_datetime_local,
        drivers=drivers,
    )


@app.route("/submit", methods=["POST"])
def submit():
    store_path = session.get("store_path")
    if not store_path:
        return redirect(url_for("index"))

    champ_id = request.form["champ_id"]
    event_id = request.form["event_id"]
    session_index = int(request.form.get("session_index", 0))
    race_datetime_local = request.form["race_datetime"]
    car_model_id = request.form["car_model_id"].strip()
    car_model = request.form["car_model"].strip()
    track_id = request.form.get("track_id", "").strip()

    race_datetime = format_dt_rfc3339(race_datetime_local)

    finishers = parse_finishers(request.form.get("finishers", ""))
    if not finishers:
        flash("Please enter at least one finisher.", "error")
        return redirect(url_for("enter_finishers", champ_id=champ_id, event_id=event_id))

    champ = load_championship(store_path, champ_id)
    event = next((e for e in champ.get("Events", []) if e["ID"] == event_id), None)
    if not event:
        flash("Event not found.", "error")
        return redirect(url_for("select_event", champ_id=champ_id))

    multi_class = champ.get("Points", {}).get("MultiClass", False)

    places = []
    for i, f in enumerate(finishers):
        guid, driver_id = find_driver_info(champ, f["name"])
        if f["guid"]:
            guid = f["guid"]
        places.append(
            {
                "ID": str(uuid.uuid4()),
                "Team": "",
                "CarModelID": car_model_id,
                "CarModel": car_model,
                "Class": "" if not multi_class else car_model,
                "CupCategory": -1,
                "RaceNumber": 0,
                "Position": i + 1,
                "TotalRaceTime": 0,
                "TimePenalty": 0,
                "Disqualified": False,
                "Ballast": 0,
                "Drivers": [
                    {
                        "GUID": guid,
                        "IsPlayer": True,
                        "Name": f["name"],
                        "DriverID": driver_id,
                        "Penalties": None,
                    }
                ],
                "Laps": [],
                "DriverGUID": "",
                "DriverName": "",
                "IsPlayer": False,
            }
        )

    result = {
        "Type": 2,
        "Date": race_datetime,
        "ServerID": 0,
        "TrackID": track_id,
        "TrackLayoutID": "",
        "PresetID": event_id,
        "ChampionshipID": champ_id,
        "OriginalFileName": f"{format_dt_for_filename(race_datetime)}_RACE_MANUAL.json",
        "FullURL": "",
        "Places": places,
        "Collisions": [],
        "IsWetSession": False,
    }

    # Find the target race session by session_index among Type==2 sessions
    race_sessions = [s for s in event.get("Sessions", []) if s.get("Type") == 2]
    if session_index >= len(race_sessions):
        flash("Selected race session not found.", "error")
        return redirect(url_for("enter_finishers", champ_id=champ_id, event_id=event_id))

    target_session = race_sessions[session_index]
    target_session["Results"] = result
    target_session["CompletedTime"] = race_datetime

    save_championship(store_path, champ_id, champ)

    return render_template(
        "confirm.html",
        champ=champ,
        event=event,
        finishers=finishers,
        race_datetime=race_datetime,
        result=result,
        session_name=target_session.get("Name", "Race"),
    )


if __name__ == "__main__":
    app.run(debug=True, host="0.0.0.0", port=5000)
