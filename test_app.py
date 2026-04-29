"""Smoke tests for core logic in app.py."""
import json
import os
import tempfile
import uuid
from pathlib import Path

import pytest

import app as the_app


@pytest.fixture
def store(tmp_path):
    champs_dir = tmp_path / "championships"
    champs_dir.mkdir()

    champ_id = str(uuid.uuid4())
    event_id = str(uuid.uuid4())
    event2_id = str(uuid.uuid4())

    champ = {
        "ID": champ_id,
        "Name": "Test Championship",
        "Points": {"MultiClass": False, "ClassType": 0, "Places": [25, 18, 15]},
        "Events": [
            {
                "ID": event_id,
                "Created": "2026-04-01T10:00:00Z",
                "StartedTime": "2026-04-01T20:00:00Z",
                "CompletedTime": "2026-04-01T21:30:00Z",
                "Sessions": [
                    {
                        "ID": 0,
                        "Type": 0,
                        "Index": 0,
                        "Name": "Practice",
                        "Results": None,
                        "CompletedTime": "0001-01-01T00:00:00Z",
                    },
                    {
                        "ID": 2,
                        "Type": 2,
                        "Index": 0,
                        "Name": "Race",
                        "Results": None,
                        "CompletedTime": "0001-01-01T00:00:00Z",
                    },
                ],
            },
            {
                "ID": event2_id,
                "Created": "2026-04-08T10:00:00Z",
                "StartedTime": "2026-04-08T20:00:00Z",
                "CompletedTime": "2026-04-08T21:45:00Z",
                "Sessions": [
                    {
                        "ID": 2,
                        "Type": 2,
                        "Index": 0,
                        "Name": "Race",
                        "CompletedTime": "2026-04-08T21:45:00Z",
                        "Results": {
                            "Type": 2,
                            "Date": "2026-04-08T21:45:00Z",
                            "ServerID": 0,
                            "TrackID": "-916478809",
                            "TrackLayoutID": "",
                            "PresetID": event2_id,
                            "ChampionshipID": champ_id,
                            "OriginalFileName": "2026-04-08_21-45-00_RACE.json",
                            "FullURL": "",
                            "Collisions": [],
                            "IsWetSession": False,
                            "Places": [
                                {
                                    "ID": str(uuid.uuid4()),
                                    "Team": "",
                                    "CarModelID": "-1404228714",
                                    "CarModel": "Sprint Race",
                                    "Class": "",
                                    "CupCategory": -1,
                                    "RaceNumber": 0,
                                    "Position": 1,
                                    "TotalRaceTime": 0,
                                    "TimePenalty": 0,
                                    "Disqualified": False,
                                    "Ballast": 0,
                                    "Drivers": [
                                        {
                                            "GUID": "76561198000000001",
                                            "IsPlayer": True,
                                            "Name": "Chiefyk",
                                            "DriverID": 42,
                                            "Penalties": None,
                                        }
                                    ],
                                    "Laps": [],
                                    "DriverGUID": "",
                                    "DriverName": "",
                                    "IsPlayer": False,
                                }
                            ],
                        },
                    }
                ],
            },
        ],
        "EntryList": {},
    }

    champ_file = champs_dir / f"{champ_id}.json"
    champ_file.write_text(json.dumps(champ))

    return {"path": str(tmp_path), "champ_id": champ_id, "event_id": event_id, "event2_id": event2_id, "champ": champ}


def test_list_championships(store):
    champs = the_app.list_championships(store["path"])
    assert len(champs) == 1
    assert champs[0]["name"] == "Test Championship"
    assert champs[0]["id"] == store["champ_id"]


def test_find_car_model(store):
    champ = the_app.load_championship(store["path"], store["champ_id"])
    car_model_id, car_model = the_app.find_car_model(champ)
    assert car_model_id == "-1404228714"
    assert car_model == "Sprint Race"


def test_find_track_id(store):
    champ = the_app.load_championship(store["path"], store["champ_id"])
    assert the_app.find_track_id(champ) == "-916478809"


def test_find_driver_info(store):
    champ = the_app.load_championship(store["path"], store["champ_id"])
    guid, driver_id = the_app.find_driver_info(champ, "Chiefyk")
    assert guid == "76561198000000001"
    assert driver_id == 42


def test_find_driver_info_unknown(store):
    champ = the_app.load_championship(store["path"], store["champ_id"])
    guid, driver_id = the_app.find_driver_info(champ, "NoSuchDriver")
    assert guid == ""
    assert driver_id == 0


def test_known_drivers(store):
    champ = the_app.load_championship(store["path"], store["champ_id"])
    drivers = the_app.known_drivers(champ)
    assert "Chiefyk" in drivers


def test_parse_finishers():
    raw = "Chiefyk\nSecondDriver,76561198000000002\nThirdDriver\t76561198000000003"
    result = the_app.parse_finishers(raw)
    assert len(result) == 3
    assert result[0] == {"name": "Chiefyk", "guid": ""}
    assert result[1] == {"name": "SecondDriver", "guid": "76561198000000002"}
    assert result[2] == {"name": "ThirdDriver", "guid": "76561198000000003"}


def test_parse_finishers_blank_lines():
    raw = "\nChiefyk\n\nSecondDriver\n"
    result = the_app.parse_finishers(raw)
    assert len(result) == 2


def test_save_championship_creates_backup(store):
    champ = the_app.load_championship(store["path"], store["champ_id"])
    the_app.save_championship(store["path"], store["champ_id"], champ)
    backups = list(Path(store["path"], "championships").glob(f"{store['champ_id']}.json.bak.*"))
    assert len(backups) == 1


def test_submit_writes_result(store):
    """Integration: submit route writes a result and sets CompletedTime."""
    client = the_app.app.test_client()
    the_app.app.config["TESTING"] = True
    the_app.app.config["SECRET_KEY"] = "test"

    with the_app.app.test_request_context():
        with client.session_transaction() as sess:
            sess["store_path"] = store["path"]

        response = client.post(
            "/submit",
            data={
                "champ_id": store["champ_id"],
                "event_id": store["event_id"],
                "session_index": "0",
                "race_datetime": "2026-04-01T21:30",
                "car_model_id": "-1404228714",
                "car_model": "Sprint Race",
                "track_id": "-916478809",
                "finishers": "Chiefyk\nSecondDriver,76561198000000002",
            },
        )

    assert response.status_code == 200
    assert b"Result written" in response.data or b"Chiefyk" in response.data

    # Verify the file was updated
    champ = the_app.load_championship(store["path"], store["champ_id"])
    event = next(e for e in champ["Events"] if e["ID"] == store["event_id"])
    race_session = next(s for s in event["Sessions"] if s["Type"] == 2)

    assert race_session["Results"] is not None
    assert race_session["CompletedTime"] == "2026-04-01T21:30:00Z"

    places = race_session["Results"]["Places"]
    assert len(places) == 2
    assert places[0]["Position"] == 1
    assert places[0]["Drivers"][0]["Name"] == "Chiefyk"
    assert places[0]["Class"] == ""  # single-class: must be empty
    assert places[1]["Position"] == 2
    assert places[1]["Drivers"][0]["GUID"] == "76561198000000002"

    # PresetID must equal the Event ID
    assert race_session["Results"]["PresetID"] == store["event_id"]
    assert race_session["Results"]["ChampionshipID"] == store["champ_id"]


def test_known_driver_guid_auto_lookup(store):
    """GUIDs and DriverIDs are looked up from existing results when not provided."""
    client = the_app.app.test_client()
    the_app.app.config["TESTING"] = True
    the_app.app.config["SECRET_KEY"] = "test"

    with client.session_transaction() as sess:
        sess["store_path"] = store["path"]

    client.post(
        "/submit",
        data={
            "champ_id": store["champ_id"],
            "event_id": store["event_id"],
            "session_index": "0",
            "race_datetime": "2026-04-01T21:30",
            "car_model_id": "-1404228714",
            "car_model": "Sprint Race",
            "track_id": "-916478809",
            "finishers": "Chiefyk",  # No GUID supplied — should be looked up
        },
    )

    champ = the_app.load_championship(store["path"], store["champ_id"])
    event = next(e for e in champ["Events"] if e["ID"] == store["event_id"])
    race_session = next(s for s in event["Sessions"] if s["Type"] == 2)
    place = race_session["Results"]["Places"][0]

    assert place["Drivers"][0]["GUID"] == "76561198000000001"
    assert place["Drivers"][0]["DriverID"] == 42
