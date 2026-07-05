"""COPY...REPLACING expansion helpers.

Shared by the COBOL and copybook extractors so the post-expansion hash is the
single source of truth (architecture 5.5). Two programs importing the same
copybook with different REPLACING pairs must hash differently.
"""
from __future__ import annotations

import re

from mainframe_brain.extractors.base import content_hash

_PLACEHOLDER = re.compile(r"==([A-Za-z0-9-]+)==")


def expand_copybook(copybook_source: str, replacing: list[tuple[str, str]]) -> str:
    """Apply `==X== BY ==Y==` token substitution to copybook text.

    `replacing` is a list of (pseudo_text, replacement) pairs as captured from a
    COPY statement's REPLACING clause. The leading/trailing `==` are stripped
    from the pair on input; we substitute any `==X==` occurrence with `Y`.
    """
    if not replacing:
        return copybook_source
    out = copybook_source
    for pseudo, repl in replacing:
        out = out.replace(f"=={pseudo}==", repl)
    return out


def post_expansion_source(paragraph_source: str, replacing: list[tuple[str, str]]) -> str:
    """Return post-expansion text for a logical unit.

    Phase 1 implementation: substitute `==X==` placeholders that appear inside
    paragraph source (e.g. from an inlined COPY) using the REPLACING pairs
    captured on the COPY statement. Hashing the raw (pre-expansion) text would
    cache narrations against the wrong field names (gap #2 fix).
    """
    return expand_copybook(paragraph_source, replacing)


def post_expansion_hash(text: str, replacing: list[tuple[str, str]]) -> str:
    return content_hash(post_expansion_source(text, replacing))


__all__ = ["expand_copybook", "post_expansion_source", "post_expansion_hash"]