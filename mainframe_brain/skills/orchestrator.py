"""Skill orchestrator — runs all skill agents and writes output to .mainframe-brain/skills/."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path

from mainframe_brain.graph.store import GraphStore

from . import SkillOutput
from .copybook import CopybookCataloger
from .dependency import DependencyMapper
from .historian import RuleHistorian
from .migration import MigrationScout
from .patterns import PatternDetective
from .risk_report import RiskReporter
from .test_suggest import TestSuggester
from .workflow import JCLWorkflowNarrator


@dataclass
class SkillRunResult:
    output_dir: str
    skills_written: int
    skills_skipped: int
    errors: list[str] = field(default_factory=list)
    manifest: dict = field(default_factory=dict)

    def to_dict(self) -> dict:
        return {
            "output_dir": self.output_dir,
            "skills_written": self.skills_written,
            "skills_skipped": self.skills_skipped,
            "errors": self.errors,
            "manifest": self.manifest,
            "timestamp": _now(),
        }


_ALL_AGENTS = [
    MigrationScout(),
    PatternDetective(),
    DependencyMapper(),
    CopybookCataloger(),
    JCLWorkflowNarrator(),
    RiskReporter(),
    TestSuggester(),
    RuleHistorian(),
]


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def generate_skills(store: GraphStore, output_dir: str = ".mainframe-brain/skills") -> SkillRunResult:
    """Run all skill agents against the graph store and write SKILL.md files.

    Each agent produces 0+ skills. Skills are written as {id}.md in output_dir,
    organized by category subdirectory. A manifest.json lists all generated skills.
    """
    out = Path(output_dir)
    result = SkillRunResult(output_dir=str(out), skills_written=0, skills_skipped=0)

    written_ids: list[str] = []

    for agent in _ALL_AGENTS:
        try:
            skills = agent.analyze(store)
        except Exception as e:
            result.errors.append(f"{agent.agent_name}: {e}")
            continue

        for skill in skills:
            try:
                cat_dir = out / skill.category
                cat_dir.mkdir(parents=True, exist_ok=True)

                filepath = cat_dir / f"{skill.id}.md"
                filepath.write_text(skill.content, encoding="utf-8")

                written_ids.append(skill.id)
                result.skills_written += 1
            except Exception as e:
                result.errors.append(f"{agent.agent_name}/{skill.id}: {e}")

    # Write manifest
    result.manifest = {
        "generated_at": _now(),
        "total_skills": result.skills_written,
        "agents_run": len(_ALL_AGENTS),
        "agents_with_errors": len([e for e in result.errors if e]),
        "skill_ids": written_ids,
        "output_dir": str(out),
    }
    (out / "manifest.json").write_text(json.dumps(result.manifest, indent=2))

    return result


__all__ = ["SkillRunResult", "generate_skills", "_ALL_AGENTS"]
