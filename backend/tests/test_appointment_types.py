"""In-person and virtual appointments. Video itself is not implemented."""

from datetime import datetime, timedelta, timezone

import pytest

from tests.conftest import seed_all


@pytest.fixture
def demo(client) -> dict:
    ids = seed_all(client)
    clinic_id = ids["clinic_id"]
    return {
        "clinic_id": clinic_id,
        "doctor_id": client.get(f"/clinics/{clinic_id}/doctors").json()[0]["id"],
        "link_id": client.get(f"/clinics/{clinic_id}/patients").json()[0]["id"],
    }


def future(days: int) -> str:
    return (datetime.now(timezone.utc) + timedelta(days=days)).replace(microsecond=0).isoformat()


def book(client, demo, **extra):
    body = {"clinic_patient_id": demo["link_id"], "doctor_id": demo["doctor_id"], "scheduled_at": future(5)} | extra
    return client.post(f"/clinics/{demo['clinic_id']}/appointments", json=body)


def test_booking_defaults_to_in_person(client, demo):
    created = book(client, demo)
    assert created.status_code == 201
    assert created.json()["appointment_type"] == "in_person" and created.json()["virtual_session_status"] == "not_applicable"


def test_a_virtual_appointment_is_stored_but_has_no_video(client, demo):
    created = book(client, demo, appointment_type="virtual").json()
    assert created["appointment_type"] == "virtual" and created["virtual_session_status"] == "not_available"
    session = client.get(f"/clinics/{demo['clinic_id']}/appointments/{created['id']}/virtual-session")
    assert session.status_code == 501 and session.json()["detail"]["code"] == "virtual_care_not_implemented"


def test_in_person_has_no_virtual_session(client, demo):
    created = book(client, demo).json()
    assert client.get(f"/clinics/{demo['clinic_id']}/appointments/{created['id']}/virtual-session").status_code == 409


def test_the_type_can_be_changed_and_is_validated(client, demo):
    created = book(client, demo).json()
    url = f"/clinics/{demo['clinic_id']}/appointments/{created['id']}"
    assert client.patch(url, json={"appointment_type": "virtual"}).json()["appointment_type"] == "virtual"
    assert client.patch(url, json={"appointment_type": "video"}).status_code == 422
    assert client.patch(url, json={"appointment_type": None}).status_code == 422
    assert book(client, demo, appointment_type="telephone", scheduled_at=future(9)).status_code == 422


def test_seeded_appointments_keep_their_types(client, demo):
    types = [a["appointment_type"] for a in client.get(f"/clinics/{demo['clinic_id']}/appointments").json()]
    assert types.count("virtual") == 1 and types.count("in_person") == len(types) - 1


def test_other_clinics_appointments_are_not_found(client, demo):
    created = book(client, demo, appointment_type="virtual").json()
    assert client.get(f"/clinics/999/appointments/{created['id']}/virtual-session").status_code == 404
