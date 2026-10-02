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


def object_id_for(domain: str, name: str | None, tag: str | None, is_taken, prefix: str = "proxon") -> str | None:
    """Pick the object id part of an entity_id: ``proxon_<name>``.

    If that is taken, ``proxon_<name>_<register>``; if the entity has no usable
    name at all, just ``proxon_<register>`` (register in the register list's
    notation, e.g. 3x0209). ``is_taken(entity_id)`` says whether an ID is in
    use. Returns None if nothing is free (the caller then lets Home Assistant
    choose).
    """
    slug = slugify(name) if name and slugify(name) != "zone" else ""
    candidates = []
    if slug:
        candidates.append(f"{prefix}_{slug}")
        if tag:
            candidates.append(f"{prefix}_{slug}_{tag}")
    if tag:
        candidates.append(f"{prefix}_{tag}")
    for candidate in candidates:
        if not is_taken(f"{domain}.{candidate}"):
            return candidate
    return None
