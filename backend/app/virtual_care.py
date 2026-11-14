"""Extension point for in-app video consultations. NOT IMPLEMENTED.

No video provider is integrated. A virtual appointment is only a booking type;
nobody can join a call through VITALA yet. To add video later, implement
VirtualCareProvider against a vetted provider (authentication, consent, end-to-end
encryption, recording policy) and set it on app.state.virtual_care.
"""

from dataclasses import dataclass
from typing import Protocol


@dataclass(frozen=True)
class VirtualSession:
    appointment_id: int
    join_url: str
    expires_at: str


class VirtualCareProvider(Protocol):
    name: str

    def create_session(self, appointment_id: int) -> VirtualSession: ...


class VirtualCareNotConfigured(RuntimeError):
    pass


class NoVirtualCareProvider:
    """The only provider today: it always refuses."""

    name = "none"

    def create_session(self, appointment_id: int) -> VirtualSession:
        raise VirtualCareNotConfigured("In-app video consultations are not implemented")
