"""Migration Scout — identifies programs ready for modernization."""

from mainframe_brain.graph.schema import EdgeType, NodeType
from mainframe_brain.graph.store import GraphStore
from mainframe_brain.triage.risk import combined_risk, risk_score

from . import SkillOutput


class MigrationScout:
    """Ranks programs by modernization readiness: high risk + no recent changes = candidate."""

    agent_id = "migration-scout"
    agent_name = "Migration Scout"
    category = "migration"

    def analyze(self, store: GraphStore) -> list[SkillOutput]:
        programs = [n for n in store.all_nodes() if n.type == NodeType.PROGRAM]
        if not programs:
            return []

        scored = []
        for prog in programs:
            base = risk_score(prog)
            combined = combined_risk(store, prog, base)
            scored.append((prog, combined))

        scored.sort(key=lambda x: x[1], reverse=True)
        top = scored[:10]

        lines = [
            f"---",
            f"name: migration-scout",
            f"description: Top modernization candidates ranked by risk and complexity",
            f"category: migration",
            f"---",
            f"",
            f"# Migration Candidates — Top {len(top)} Programs",
            f"",
            f"Ranked by risk score (complexity + GOTO density + external calls + cascade/trigger depth).",
            f"Higher scores = harder to maintain, higher ROI for modernization.",
            f"",
            f"| Rank | Program | Risk Score | Complexity | GOTO Density | Ext Calls |",
            f"|------|---------|------------|------------|--------------|-----------|",
        ]

        for i, (prog, risk) in enumerate(top, 1):
            p = prog.properties
            comp = p.get("cyclomatic_complexity", 0) or 0
            goto = p.get("goto_density", 0) or 0
            calls = len(p.get("external_calls", []) or [])
            lines.append(f"| {i} | {prog.name} | {risk:.1f} | {comp} | {goto:.2f} | {calls} |")

        lines.extend([
            "",
            "## Recommendations",
            "",
        ])

        for i, (prog, risk) in enumerate(top, 1):
            p = prog.properties
            lines.append(f"### {i}. {prog.name} (risk: {risk:.1f})")
            if p.get("cyclomatic_complexity", 0) > 10:
                lines.append(f"- **High complexity** ({p['cyclomatic_complexity']}): consider extracting sub-procedures")
            if p.get("goto_density", 0) > 0.3:
                lines.append(f"- **GOTO-heavy** ({p['goto_density']:.1%} density): restructure control flow first")
            calls = len(p.get("external_calls", []) or [])
            if calls > 5:
                lines.append(f"- **{calls} external calls**: mock these for testing")
            lines.append(f"- View details: `mainframe-brain query --store-path brain.db \"impact of {prog.name}\"`")
            lines.append("")

        content = "\n".join(lines)
        return [SkillOutput(
            id="migration-top-candidates",
            title=f"Top {len(top)} Modernization Candidates",
            category="migration",
            content=content,
            related_nodes=[p.id for p, _ in top],
        )]
