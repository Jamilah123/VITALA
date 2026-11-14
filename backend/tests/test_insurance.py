"""Insurance details: encrypted identifiers, masking, validation, and no leaks."""

from sqlmodel import Session

from app.models import PatientInsurance

# Synthetic, format-valid values only.
NATIONAL_ID = "1000000008"
MEMBER = "SYN-778899"
INSURED = {"coverage_status": "insured", "national_id": NATIONAL_ID, "insurer_name": "Synthetic Insurer", "member_number": MEMBER, "insurance_class": "B"}


def new_patient(client) -> int:
    return client.post("/patients", json={"sex": "female"}).json()["id"]


def test_nothing_stored_reads_as_unknown(client):
    patient_id = new_patient(client)
    body = client.get(f"/patients/{patient_id}/insurance").json()
    assert body["stored"] is False and body["coverage_status"] == "unknown" and body["national_id_masked"] is None
    assert (body["eligibility_verified"], body["insurer_integration_available"], body["online_payment_available"]) == (False, False, False)


def test_identifiers_are_encrypted_and_only_returned_masked(key_client, key_settings):
    patient_id = new_patient(key_client)
    response = key_client.put(f"/patients/{patient_id}/insurance", json=INSURED)
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["national_id_masked"] == "******0008"
    assert body["member_number_masked"] == "****8899"
    assert NATIONAL_ID not in response.text and MEMBER not in response.text
    assert NATIONAL_ID not in key_client.get(f"/patients/{patient_id}/insurance").text

    with Session(key_client.app.state.engine) as session:
        stored = session.get(PatientInsurance, patient_id)
        assert stored.national_id_ciphertext and NATIONAL_ID not in stored.national_id_ciphertext
        assert key_client.app.state.field_cipher.decrypt(stored.national_id_ciphertext) == NATIONAL_ID
    # The plain value appears nowhere in the database file.
    key_client.app.state.engine.dispose()
    raw = key_settings.database_path.read_bytes()
    assert NATIONAL_ID.encode() not in raw and MEMBER.encode() not in raw


def test_without_a_key_identifiers_are_refused_but_the_rest_works(client):
    patient_id = new_patient(client)
    refused = client.put(f"/patients/{patient_id}/insurance", json=INSURED)
    assert refused.status_code == 503 and refused.json()["detail"]["code"] == "encryption_not_configured"
    assert client.get(f"/patients/{patient_id}/insurance").json()["stored"] is False
    ok = client.put(f"/patients/{patient_id}/insurance", json={"coverage_status": "insured", "insurer_name": "Synthetic Insurer", "insurance_class": "A"})
    assert ok.status_code == 200 and ok.json()["insurer_name"] == "Synthetic Insurer"


def test_details_only_for_insured_patients(key_client):
    patient_id = new_patient(key_client)
    response = key_client.put(f"/patients/{patient_id}/insurance", json={"coverage_status": "uninsured", "insurer_name": "X"})
    assert response.status_code == 422
    assert key_client.put(f"/patients/{patient_id}/insurance", json={"coverage_status": "uninsured"}).json()["coverage_status"] == "uninsured"


def test_invalid_identifiers_are_rejected_without_echoing_them(key_client):
    patient_id = new_patient(key_client)
    for bad in ("3000000001", "12345", "10000000081"):
        response = key_client.put(f"/patients/{patient_id}/insurance", json=INSURED | {"national_id": bad})
        assert response.status_code == 422
        assert bad not in response.text
        assert MEMBER not in response.text
    missing_status = key_client.put(f"/patients/{patient_id}/insurance", json={"national_id": NATIONAL_ID})
    assert missing_status.status_code == 422 and NATIONAL_ID not in missing_status.text


def test_the_same_national_id_cannot_belong_to_two_patients(key_client):
    first, second = new_patient(key_client), new_patient(key_client)
    key_client.put(f"/patients/{first}/insurance", json=INSURED)
    response = key_client.put(f"/patients/{second}/insurance", json=INSURED | {"member_number": "SYN-000001"})
    assert response.status_code == 409 and str(first) not in response.json()["detail"]["message"]


def test_put_replaces_and_clears_omitted_fields(key_client):
    patient_id = new_patient(key_client)
    key_client.put(f"/patients/{patient_id}/insurance", json=INSURED)
    body = key_client.put(f"/patients/{patient_id}/insurance", json={"coverage_status": "insured", "insurer_name": "Other Synthetic"}).json()
    assert (body["national_id_masked"], body["member_number_masked"], body["insurance_class"]) == (None, None, None)
    with Session(key_client.app.state.engine) as session:
        stored = session.get(PatientInsurance, patient_id)
        assert stored.national_id_ciphertext is None and stored.national_id_hash is None
    assert key_client.delete(f"/patients/{patient_id}/insurance").status_code == 204
    assert key_client.get(f"/patients/{patient_id}/insurance").json()["stored"] is False


def test_missing_patient(key_client):
    assert key_client.put("/patients/999/insurance", json={"coverage_status": "unknown"}).status_code == 404
