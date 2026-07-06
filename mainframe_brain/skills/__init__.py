"""Skill agents — Layer 7, post-enrichment analysis that produces AI-tool-ready skills.

Each agent is a deterministic graph analyzer (no LLM tokens). It reads the knowledge
graph and produces a SKILL.md artifact — a markdown file structured for AI coding tools
(Kiro, Claude Code, Cursor, Copilot, etc.) to consume as context.

Skills are written to .mainframe-brain/skills/ and compound: re-running after a change
updates only the skills whose source data changed (via content-hash diffing).
"""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Protocol

from mainframe_brain.graph.schema import Node
from mainframe_brain.graph.store import GraphStore


@dataclass
class SkillOutput:
    """One skill produced by a skill agent."""
    id: str                          # machine-readable slug (e.g. "migration-PAYROLL01")
    title: str                       # human-readable title
    category: str                    # "migration", "patterns", "dependency", "copybook", "workflow", "risk", "tests", "history"
    content: str                     # full SKILL.md markdown body
    related_nodes: list[str] = field(default_factory=list)  # node IDs this skill covers
    content_hash: str = ""           # hash for incremental update detection


class SkillAgent(Protocol):
    """A deterministic analyzer that produces skill artifacts from the graph."""

    agent_id: str
    agent_name: str
    category: str

    def analyze(self, store: GraphStore) -> list[SkillOutput]:
        """Read the knowledge graph and produce 0+ skills."""
        ...


__all__ = ["SkillAgent", "SkillOutput"]
