"""Domain errors: a catalog code of section 16 of document 2 plus data for the response.

Domain code raises DomainError; the API layer turns it into problem+json (infra.problems).
"""

from typing import Any


class DomainError(Exception):
    def __init__(self, code: str, detail: str = "", data: dict[str, Any] | None = None) -> None:
        super().__init__(detail or code)
        self.code = code
        self.detail = detail
        self.data = data
