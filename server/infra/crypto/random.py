"""Random secrets of the server (license keys): the OS CSPRNG only (AGENTS.md, rule 12)."""

import secrets


def random_text(alphabet: str, length: int) -> str:
    return "".join(secrets.choice(alphabet) for _ in range(length))
