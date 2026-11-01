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
    return catalogue
