"""Add one synthetic patient to the development database.

Run from the backend folder: .\\.venv\\Scripts\\python.exe -m app.seed
Running it again changes nothing.
"""

from datetime import date

from sqlmodel import Session, select

from app.config import Settings
from app.database import build_engine, init_db
from app.models import ConditionStatus, DiabetesType, Patient, Sex

SEED_KEY = "synthetic-patient-1"


def seed_synthetic_patient(session: Session) -> tuple[Patient, bool]:
    """Return the synthetic patient, and whether this call created it."""
    existing = session.exec(select(Patient).where(Patient.seed_key == SEED_KEY)).first()
    if existing:
        return existing, False

    # Invented test values, not a real person. Hypertension stays unknown on
    # purpose, to show missing information rather than a negative finding.
    patient = Patient(
        seed_key=SEED_KEY,
        date_of_birth=date(1985, 3, 15),
        sex=Sex.female,
        diabetes_status=ConditionStatus.diagnosed,
        diabetes_type=DiabetesType.type_2,
        diabetes_diagnosis_date=date(2020, 6, 1),
    )
    session.add(patient)
    session.commit()
    session.refresh(patient)
    return patient, True


def main() -> None:
    settings = Settings()
    engine = build_engine(settings.database_path)
    init_db(engine, settings.database_path)
    with Session(engine) as session:
        patient, created = seed_synthetic_patient(session)
        outcome = "Created" if created else "Already exists, nothing changed:"
        print(f"{outcome} synthetic patient id={patient.id} in {settings.database_path}")
    engine.dispose()


if __name__ == "__main__":
    main()
