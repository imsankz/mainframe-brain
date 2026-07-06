"""Risk Reporter — prioritized risk assessment across the entire codebase."""

from mainframe_brain.graph.schema import NodeType
from mainframe_brain.graph.store import GraphStore
from mainframe_brain.triage.risk import combined_risk, risk_score

from . import SkillOutput


class RiskReporter:
    """Codebase-level risk heat map sorted by combined risk."""

    agent_id = "risk-reporter"
    agent_name = "Risk Reporter"
    category = "risk"

    def analyze(self, store: GraphStore) -> list[SkillOutput]:
        paragraphs = [n for n in store.all_nodes() if n.type == NodeType.PARAGRAPH]
        programs = [n for n in store.all_nodes() if n.type == NodeType.PROGRAM]
        tables = [n for n in store.all_nodes() if n.type == NodeType.DB2_TABLE]
        triggers = [n for n in store.all_nodes() if n.type == NodeType.TRIGGER]

        all_risky: list[tuple] = []

        for p in paragraphs:
            base = risk_score(p)
            combined = combined_risk(store, p, base)
            if combined > 0:
                all_risky.append((p, combined, "paragraph"))

        for prog in programs:
            base = risk_score(prog)
            combined = combined_risk(store, prog, base)
            if combined > 0:
                all_risky.append((prog, combined, "program"))

        for tbl in tables:
            combined = combined_risk(store, tbl, 0)
            if combined > 0:
                all_risky.append((tbl, combined, "table"))

        for trg in triggers:
            combined = combined_risk(store, trg, 0)
            if combined > 0:
                all_risky.append((trg, combined, "trigger"))

        all_risky.sort(key=lambda x: x[1], reverse=True)

        lines = [
            "---",
            "name: risk-report",
            "description: Codebase-wide risk heat map",
            "category: risk",
            "---",
            "",
            "# Risk Heat Map",
            "",
            f"**Total entities scored:** {len(all_risky)}",
            "",
            "Top 20 riskiest entities:",
            "",
            "| Rank | Name | Type | Risk Score | Confidence |",
            "|------|------|------|------------|------------|",
        ]

        top = all_risky[:20]
        for i, (node, risk, kind) in enumerate(top, 1):
            conf = node.parse_confidence if node.parse_confidence else 1.0
            conf_str = f"{conf:.0%}" if conf < 1.0 else "✅"
            lines.append(f"| {i} | {node.name} | {kind} | {risk:.1f} | {conf_str} |")

        lines.extend([
            "",
            "## Risk Distribution",
            "",
        ])

        high = sum(1 for _, r, _ in all_risky if r >= 5)
        medium = sum(1 for _, r, _ in all_risky if 2 <= r < 5)
        low = sum(1 for _, r, _ in all_risky if r < 2)

        lines.append(f"- 🔴 High risk (≥5): {high}")
        lines.append(f"- 🟡 Medium risk (2–5): {medium}")
        lines.append(f"- 🟢 Low risk (<2): {low}")
        lines.append("")
        lines.append("Risk formula: complexity×0.5 + GOTO×0.2 + ext_calls×0.15 + literals×0.1 + cascade/trigger depth")
        lines.append("Parse confidence < 0.5 applies a 0.3× penalty to avoid false positives from partial parses.")

        return [SkillOutput(
            id="risk-report",
            title="Risk Heat Map",
            category="risk",
            content="\n".join(lines),
            related_nodes=[n.id for n, _, _ in top],
        )]
