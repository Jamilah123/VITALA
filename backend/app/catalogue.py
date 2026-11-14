from pathlib import Path

from pydantic import TypeAdapter

from app.schemas import CatalogueMedication


def load_catalogue(path: Path) -> dict[str, CatalogueMedication]:
    """Read medications.json. A missing or malformed file stops the app at startup."""
    # Windows does not default to UTF-8, and the file contains Arabic names.
    text = path.read_text(encoding="utf-8")
    medications = TypeAdapter(list[CatalogueMedication]).validate_json(text)
    catalogue = {medication.id: medication for medication in medications}
    if len(catalogue) != len(medications):
        raise ValueError(f"Duplicate medication ids in {path}")
    for medication in medications:
        archived = medication.status == "archived"
        if archived != (medication.archived_on is not None) or archived != (medication.archive_reason_ar is not None):
            raise ValueError(f"Medication {medication.id}: archived_on and archive_reason_ar are required when archived, and only then")
        if archived == (medication.demo_scope is not None):
            raise ValueError(f"Medication {medication.id}: an active entry needs a demo_scope, an archived one must not have it")
    return catalogue
