"""Versioned business-rule narration prompt — structured JSON output only."""
from __future__ import annotations

PROMPT_VERSION = "business_rule.v1"


SYSTEM = (
    "You narrate undocumented business rules in legacy mainframe code. "
    "Return ONLY JSON with keys: rule (plain language), confidence (0..1 float), "
    "line_range ([start, end] 1-indexed in the supplied source), "
    "edge_cases (list of strings). Never invent line numbers. "
    "Never invent business facts not present in the source. "
    "If you cannot confidently identify a rule, set confidence <= 0.3 and rule to a minimal description. "
    "Do not wrap the JSON in markdown fences."
)


def render_prompt(source_text: str, artifact_type: str, unit_name: str) -> str:
    return (
        f"Artifact type: {artifact_type}\n"
        f"Unit name: {unit_name}\n\n"
        f"Source:\n{source_text}\n\n"
        "Describe the business rule this code encodes as JSON. "
        "rule = the business decision (not just 'what does this code do'); "
        "confidence = how sure you are (0..1); line_range = [1-based start, end] "
        "of the lines encoding this rule; edge_cases = list of edge cases or hazards "
        "a reviewer should manually verify."
    )


__all__ = ["SYSTEM", "render_prompt", "PROMPT_VERSION"]