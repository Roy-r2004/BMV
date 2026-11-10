"""GCC outreach: find businesses, read what is public, write each a report and a
DM Roy sends by hand (docs/superpowers/specs/2026-11-10-gcc-outreach-design.md)."""
import secrets


def new_token() -> str:
    """A report's address: 22 characters nobody can guess."""
    return secrets.token_urlsafe(16)
