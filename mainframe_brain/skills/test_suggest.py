"""Test Suggester — suggests test cases for critical business logic."""

from mainframe_brain.graph.schema import EdgeType, NodeType
from mainframe_brain.graph.store import GraphStore
from mainframe_brain.triage.risk import combined_risk, risk_score

from . import SkillOutput


class TestSuggester:
    """Suggests test scenarios for the highest-risk business rules."""

    agent_id = "test-suggester"
    agent_name = "Test Suggester"
    category = "tests"

    def analyze(self, store: GraphStore) -> list[SkillOutput]:
        paragraphs = [n for n in store.all_nodes() if n.type == NodeType.PARAGRAPH]

        # Find paragraphs with BusinessRule nodes linked via IMPLEMENTS_RULE
        rules: list[tuple] = []
        para_by_rule: dict[str, str] = {}

        for e in store.all_edges():
            if e.type == EdgeType.IMPLEMENTS_RULE:
                rule_node = store.get_node(e.dst)
                para_node = store.get_node(e.src)
                if rule_node and para_node:
                    para_by_rule[rule_node.id] = para_node.name

        for n in store.all_nodes():
            if n.type != NodeType.BUSINESS_RULE:
                continue
            if n.properties.get("human_verified"):
                base = risk_score(n)
                combined = combined_risk(store, n, base)
                rules.append((n, combined))

        rules.sort(key=lambda x: x[1], reverse=True)
        top = rules[:15]

        if not top:
            return []

        lines = [
            "---",
            "name: test-suggestions",
            "description: Suggested test cases for critical business logic",
            "category: tests",
            "---",
            "",
            "# Test Case Suggestions",
            "",
            f"Based on {len(rules)} business rules analyzed. Top {len(top)} by risk:",
            "",
        ]

        for i, (rule, risk) in enumerate(top, 1):
            p = rule.properties
            rule_text = (p.get("rule", "") or "")[:120]
            para_name = para_by_rule.get(rule.id, rule.name)

            lines.append(f"## Test {i}: {rule.name}")
            lines.append("")
            lines.append(f"**Risk score:** {risk:.1f}")
            lines.append(f"**Parent paragraph:** `{para_name}`")
            lines.append(f"**Rule:** {rule_text}")
            lines.append(f"**Verified:** {'✅ human-verified' if p.get('human_verified') else '⚠️ unverified'}")

            if p.get("edge_cases"):
                lines.append("")
                lines.append("### Edge cases to test")
                for ec in p["edge_cases"]:
                    lines.append(f"- [ ] {ec}")

            lines.append("")
            lines.append("### Suggested test scenarios")
            lines.append(f"- [ ] Happy path: normal execution of `{para_name}`")
            lines.append(f"- [ ] Edge case: boundary conditions for date/numeric fields")
            lines.append(f"- [ ] Error case: invalid input to `{para_name}`")
            lines.append(f"- [ ] Integration: verify `{para_name}` in the context of its calling program")
            lines.append("")

        lines.extend([
            "## AI Tool Usage",
            "",
            "Load this skill when tasked with writing tests for the codebase.",
            "Each section above maps to a specific paragraph with documented business rules.",
        ])

        return [SkillOutput(
            id="test-suggestions",
            title="Test Case Suggestions",
            category="tests",
            content="\n".join(lines),
            related_nodes=[r.id for r, _ in top],
        )]
