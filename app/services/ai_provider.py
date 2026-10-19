from datetime import date
from typing import Protocol

from pydantic import BaseModel


class AIProvider(Protocol):
    """Provider returns untrusted JSON text; validation is a separate concern."""
    def complete(self, kind: str, text: str, schema: type[BaseModel],
                 reference_date: date | None = None, timezone: str | None = None) -> str: ...
