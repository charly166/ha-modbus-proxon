"""Shared helpers for the Proxon integration."""

from __future__ import annotations

import re
import unicodedata

_UMLAUT_MAP = str.maketrans({"ä": "ae", "ö": "oe", "ü": "ue", "Ä": "Ae", "Ö": "Oe", "Ü": "Ue", "ß": "ss"})


def slugify(name: str) -> str:
    """Turn a (German) display name into a safe Python identifier / unique_id fragment.

    Kept in sync with tools/generate_registers.py's copy, which uses the same
    algorithm to derive the legacy unique_ids this must reproduce for a given
    zone name.
    """
    name = name.translate(_UMLAUT_MAP)
    name = unicodedata.normalize("NFKD", name).encode("ascii", "ignore").decode("ascii")
    name = re.sub(r"[^0-9a-zA-Z]+", "_", name).strip("_").lower()
    name = re.sub(r"_+", "_", name)
    if not name:
        name = "zone"
    if name[0].isdigit():
        name = f"z_{name}"
    return name
