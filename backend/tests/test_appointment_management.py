from datetime import datetime, timedelta, timezone

import pytest
from sqlmodel import Session, select

from app.models import Appointment, AppointmentStatus, Clinic, ClinicPatient, Doctor, Patient
from app.seed import seed_demo_clinic

RIYADH = timezone(timedelta(hours=3))
# Far enough ahead to stay clear of the seeded demo appointments.
BASE = (datetime.now(RIYADH) + timedelta(days=30)).replace(hour=9, minute=0, second=0, microsecond=0)


def at(minutes: int = 0) -> str:
    return (BASE + timedelta(minutes=minutes)).isoformat()


def error_fields(response) -> list[str]:
    assert response.status_code == 422, response.text
    return [error["loc"][-1] for error in response.json()["detail"]]


@pytest.fixture
def demo(client) -> dict:
    with Session(client.app.state.engine) as session:
        clinic, _ = seed_demo_clinic(session)
        doctors = session.exec(select(Doctor).where(Doctor.clinic_id == clinic.id).order_by(Doctor.id)).all()
        links = session.exec(select(ClinicPatient).where(ClinicPatient.clinic_id == clinic.id).order_by(ClinicPatient.id)).all()
        return {"id": clinic.id, "doctors": [doctor.id for doctor in doctors], "links": [link.id for link in links]}


@pytest.fixture
def other(client, demo) -> dict:
    with Session(client.app.state.engine) as session:
        clinic = Clinic(name_ar="عيادة اختبار أخرى")
        patient = Patient(sex="male")
        session.add_all([clinic, patient])
        session.flush()
        doctor = Doctor(clinic_id=clinic.id, name_ar="د. اختبار")
        link = ClinicPatient(clinic_id=clinic.id, patient_id=patient.id, display_name_ar="مريض اختبار")
        session.add_all([doctor, link])
        session.flush()
        appointment = Appointment(clinic_id=clinic.id, doctor_id=doctor.id, clinic_patient_id=link.id, scheduled_at=BASE + timedelta(days=1))
        session.add(appointment)
        session.commit()
        return {"id": clinic.id, "doctor": doctor.id, "link": link.id, "appointment": appointment.id}


@pytest.fixture
def url(demo) -> str:
    return f"/clinics/{demo['id']}/appointments"


def create(client, url, demo, minutes=0, doctor=0, link=0, **extra):
    body = {"clinic_patient_id": demo["links"][link], "doctor_id": demo["doctors"][doctor], "scheduled_at": at(minutes), **extra}
    return client.post(url, json=body)


@pytest.fixture
def booked(client, url, demo) -> dict:
    response = create(client, url, demo, visit_reason_ar="متابعة")
    assert response.status_code == 201, response.text
    return response.json()


def set_past(client, appointment_id: int) -> None:
    with Session(client.app.state.engine) as session:
        row = session.get(Appointment, appointment_id)
        row.scheduled_at = datetime.now(timezone.utc) - timedelta(hours=2)
        session.add(row)
        session.commit()


# 1. Creating


def test_create_books_a_scheduled_clinic_appointment(client, url, demo, booked):
    assert booked["status"] == "scheduled"
    assert booked["booking_source"] == "clinic"
    assert booked["clinic_id"] == demo["id"]
    assert booked["visit_reason_ar"] == "متابعة"
    assert booked in client.get(url).json()


@pytest.mark.parametrize("field", ["status", "booking_source", "clinic_id"])
def test_create_cannot_set_server_controlled_fields(client, url, demo, field):
    assert error_fields(create(client, url, demo, **{field: "completed" if field == "status" else "vitala" if field == "booking_source" else 2})) == [field]


@pytest.mark.parametrize("missing", ["clinic_patient_id", "doctor_id", "scheduled_at"])
def test_create_requires_patient_doctor_and_time(client, url, demo, missing):
    body = {"clinic_patient_id": demo["links"][0], "doctor_id": demo["doctors"][0], "scheduled_at": at()}
    del body[missing]

    assert error_fields(client.post(url, json=body)) == [missing]


def test_visit_reason_is_trimmed_and_limited(client, url, demo):
    assert create(client, url, demo, visit_reason_ar="  زيارة أولى ").json()["visit_reason_ar"] == "زيارة أولى"
    assert error_fields(create(client, url, demo, minutes=60, visit_reason_ar="x" * 201)) == ["visit_reason_ar"]
    assert error_fields(create(client, url, demo, minutes=120, visit_reason_ar="   ")) == ["visit_reason_ar"]


# 2. Editing


def test_reschedule_and_change_doctor(client, url, demo, booked):
    response = client.patch(f"{url}/{booked['id']}", json={"scheduled_at": at(90), "doctor_id": demo["doctors"][1]})

    assert response.status_code == 200
    body = response.json()
    assert body["doctor_id"] == demo["doctors"][1]
    assert datetime.fromisoformat(body["scheduled_at"]) == BASE + timedelta(minutes=90)
    assert body["clinic_patient_id"] == booked["clinic_patient_id"]
    assert body["visit_reason_ar"] == "متابعة"


def test_patch_leaves_omitted_fields_and_null_clears_the_reason(client, url, booked):
    body = client.patch(f"{url}/{booked['id']}", json={"visit_reason_ar": None}).json()

    assert body == booked | {"visit_reason_ar": None}


@pytest.mark.parametrize("field", ["clinic_patient_id", "clinic_id", "status", "booking_source"])
def test_patch_cannot_move_the_appointment_to_another_patient_or_clinic(client, url, booked, field):
    assert error_fields(client.patch(f"{url}/{booked['id']}", json={field: 1})) == [field]


@pytest.mark.parametrize("field", ["doctor_id", "scheduled_at"])
def test_patch_rejects_null_for_required_fields(client, url, booked, field):
    assert error_fields(client.patch(f"{url}/{booked['id']}", json={field: None})) == [field]


# 3. Cancelling


def test_cancel_keeps_the_appointment_in_history(client, url, demo, booked):
    response = client.post(f"{url}/{booked['id']}/status", json={"status": "cancelled"})

    assert response.status_code == 200
    assert response.json()["status"] == "cancelled"
    listed = next(item for item in client.get(url).json() if item["id"] == booked["id"])
    assert listed["status"] == "cancelled"
    assert client.get(f"{url}/{booked['id']}").status_code == 200
    assert client.delete(f"{url}/{booked['id']}").status_code == 405


def test_a_cancelled_slot_can_be_booked_again(client, url, demo, booked):
    client.post(f"{url}/{booked['id']}/status", json={"status": "cancelled"})

    assert create(client, url, demo, link=1).status_code == 201


# 4. Doctor and patient ownership


def test_create_rejects_a_doctor_or_patient_from_another_clinic(client, url, demo, other):
    response = client.post(url, json={"clinic_patient_id": other["link"], "doctor_id": other["doctor"], "scheduled_at": at()})

    assert sorted(error_fields(response)) == ["clinic_patient_id", "doctor_id"]


@pytest.mark.parametrize(("field", "value"), [("clinic_patient_id", 9999), ("doctor_id", 9999), ("doctor_id", "1"), ("clinic_patient_id", True)])
def test_create_rejects_unknown_or_loosely_typed_ids(client, url, demo, field, value):
    body = {"clinic_patient_id": demo["links"][0], "doctor_id": demo["doctors"][0], "scheduled_at": at(), field: value}

    assert error_fields(client.post(url, json=body)) == [field]


def test_reassigning_to_another_clinics_doctor_is_rejected(client, url, other, booked):
    assert error_fields(client.patch(f"{url}/{booked['id']}", json={"doctor_id": other["doctor"]})) == ["doctor_id"]
    assert client.get(f"{url}/{booked['id']}").json()["appointment"] == booked


def test_create_in_an_unknown_clinic_returns_404(client, demo):
    body = {"clinic_patient_id": demo["links"][0], "doctor_id": demo["doctors"][0], "scheduled_at": at()}

    assert client.post("/clinics/9999/appointments", json=body).status_code == 404


# 5. Cross-clinic updates


@pytest.mark.parametrize(
    ("method", "suffix", "body"),
    [("patch", "", {"visit_reason_ar": "تعديل"}), ("post", "/status", {"status": "cancelled"})],
)
def test_another_clinics_appointment_cannot_be_changed(client, url, other, method, suffix, body):
    response = client.request(method, f"{url}/{other['appointment']}{suffix}", json=body)

    assert response.status_code == 404
    with Session(client.app.state.engine) as session:
        row = session.get(Appointment, other["appointment"])
        assert row.status == AppointmentStatus.scheduled
        assert row.visit_reason_ar is None


# 6. Conflicts


def test_a_doctor_cannot_be_double_booked_within_the_slot(client, url, demo, booked):
    assert error_fields(create(client, url, demo, minutes=29, link=1)) == ["scheduled_at"]
    assert error_fields(create(client, url, demo, minutes=-29, link=1)) == ["scheduled_at"]
    assert create(client, url, demo, minutes=30, link=1).status_code == 201
    assert create(client, url, demo, minutes=0, doctor=1, link=2).status_code == 201


def test_rescheduling_checks_conflicts_but_not_against_itself(client, url, demo, booked):
    second = create(client, url, demo, minutes=60, link=1).json()

    assert client.patch(f"{url}/{booked['id']}", json={"scheduled_at": at(10)}).status_code == 200
    assert error_fields(client.patch(f"{url}/{booked['id']}", json={"scheduled_at": at(70)})) == ["scheduled_at"]
    assert error_fields(client.patch(f"{url}/{second['id']}", json={"scheduled_at": at(20)})) == ["scheduled_at"]


def test_changing_doctor_checks_the_new_doctors_schedule(client, url, demo, booked):
    create(client, url, demo, minutes=15, doctor=1, link=1)

    assert error_fields(client.patch(f"{url}/{booked['id']}", json={"doctor_id": demo["doctors"][1]})) == ["scheduled_at"]


# 7. Time zones and dates


def test_riyadh_time_is_stored_and_returned_in_utc(client, url, demo):
    local = BASE.replace(hour=9, minute=0)
    body = client.post(url, json={"clinic_patient_id": demo["links"][0], "doctor_id": demo["doctors"][2], "scheduled_at": local.isoformat()}).json()

    assert body["scheduled_at"] == local.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    assert body["scheduled_at"].endswith("T06:00:00Z")


def test_a_utc_timestamp_is_accepted(client, url, demo):
    utc = (BASE + timedelta(hours=5)).astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

    assert client.post(url, json={"clinic_patient_id": demo["links"][0], "doctor_id": demo["doctors"][0], "scheduled_at": utc}).status_code == 201


@pytest.mark.parametrize(
    "value",
    [
        BASE.replace(tzinfo=None).isoformat(),
        BASE.date().isoformat(),
        int(BASE.timestamp()),
        "next tuesday",
        (datetime.now(RIYADH) - timedelta(hours=1)).isoformat(),
        (datetime.now(RIYADH) + timedelta(days=366)).isoformat(),
    ],
)
def test_naive_vague_past_or_distant_times_are_rejected(client, url, demo, value):
    body = {"clinic_patient_id": demo["links"][0], "doctor_id": demo["doctors"][0], "scheduled_at": value}

    assert error_fields(client.post(url, json=body)) == ["scheduled_at"]


def test_rescheduling_into_the_past_is_rejected(client, url, booked):
    past = (datetime.now(RIYADH) - timedelta(days=1)).isoformat()

    assert error_fields(client.patch(f"{url}/{booked['id']}", json={"scheduled_at": past})) == ["scheduled_at"]


# 8. Status transitions


def test_a_future_appointment_cannot_be_completed_or_missed(client, url, booked):
    for status in ("completed", "no_show"):
        assert error_fields(client.post(f"{url}/{booked['id']}/status", json={"status": status})) == ["status"]


@pytest.mark.parametrize("outcome", ["completed", "no_show"])
def test_a_past_scheduled_appointment_can_be_completed_or_missed(client, url, booked, outcome):
    set_past(client, booked["id"])

    assert client.post(f"{url}/{booked['id']}/status", json={"status": outcome}).json()["status"] == outcome


@pytest.mark.parametrize("final", ["cancelled", "completed", "no_show"])
def test_final_statuses_cannot_change_or_be_edited(client, url, booked, final):
    set_past(client, booked["id"]) if final != "cancelled" else None
    client.post(f"{url}/{booked['id']}/status", json={"status": final})

    for status in ("completed", "cancelled", "no_show"):
        assert error_fields(client.post(f"{url}/{booked['id']}/status", json={"status": status})) == ["status"]
    assert error_fields(client.patch(f"{url}/{booked['id']}", json={"visit_reason_ar": "تعديل"})) == ["status"]


@pytest.mark.parametrize("status", ["scheduled", "deleted", ""])
def test_unknown_or_backward_status_values_are_rejected(client, url, booked, status):
    assert error_fields(client.post(f"{url}/{booked['id']}/status", json={"status": status})) == ["status"]


# 9. Summary access


def test_summary_stays_available_after_create_edit_and_cancel(client, url, demo, booked):
    summary = f"{url}/{booked['id']}/summary"
    assert client.get(summary).status_code == 200

    client.patch(f"{url}/{booked['id']}", json={"doctor_id": demo["doctors"][1]})
    after_edit = client.get(summary).json()
    assert after_edit["visit"]["doctor"]["id"] == demo["doctors"][1]

    client.post(f"{url}/{booked['id']}/status", json={"status": "cancelled"})
    after_cancel = client.get(summary).json()
    assert after_cancel["visit"]["appointment"]["status"] == "cancelled"
    assert after_cancel["visit"]["patient"]["id"] == booked["clinic_patient_id"]


# 10. Original patients


def test_appointment_writes_never_touch_or_expose_existing_patients(client, url, demo, patient):
    before = client.get(f"/patients/{patient['id']}").json()
    preview_before = client.get(f"/patients/{patient['id']}/screening-preview").json()

    booked = create(client, url, demo).json()
    client.patch(f"{url}/{booked['id']}", json={"scheduled_at": at(45)})
    client.post(f"{url}/{booked['id']}/status", json={"status": "cancelled"})

    assert client.get(f"/patients/{patient['id']}").json() == before
    assert client.get(f"/patients/{patient['id']}/screening-preview").json() == preview_before
    linked = {item["patient"]["id"] for item in client.get(f"/clinics/{demo['id']}/patients").json()}
    assert patient["id"] not in linked
