"""Copybook Cataloger — documents copybook fields, types, and cross-program usage."""

from collections import defaultdict

from mainframe_brain.graph.schema import EdgeType, NodeType
from mainframe_brain.graph.store import GraphStore

from . import SkillOutput


class CopybookCataloger:
    """Per-copybook skill: field listing, data types, and programs that include it."""

    agent_id = "copybook-cataloger"
    agent_name = "Copybook Cataloger"
    category = "copybook"

    def analyze(self, store: GraphStore) -> list[SkillOutput]:
        copybooks = [n for n in store.all_nodes() if n.type == NodeType.COPYBOOK]
        fields = [n for n in store.all_nodes() if n.type == NodeType.FIELD]

        # Map: field ID → copybook name (parent)
        field_parent: dict[str, str] = {}
        for e in store.all_edges():
            if e.type == EdgeType.DERIVED_FROM:
                field_parent[e.src] = e.dst

        # Map: copybook ID → programs that INCLUDE it
        includers: dict[str, list[str]] = defaultdict(list)
        for e in store.all_edges():
            if e.type == EdgeType.INCLUDES:
                src = store.get_node(e.src)
                if src:
                    includers[e.dst].append(src.name)

        outputs: list[SkillOutput] = []

        for cb in copybooks:
            cb_fields = [f for f in fields if field_parent.get(f.id) == cb.id]

            lines = [
                "---",
                f"name: copybook-{_safe_slug(cb.name)}",
                f"description: Fields, types, and usage of copybook {cb.name}",
                "category: copybook",
                "---",
                "",
                f"# Copybook: {cb.name}",
                "",
                f"**Node ID:** `{cb.id}`",
                f"**Programs using it:** {len(includers.get(cb.id, []))}",
                "",
            ]

            if includers.get(cb.id):
                lines.append("## Used By")
                lines.append("")
                for prog in sorted(includers[cb.id]):
                    lines.append(f"- {prog}")
                lines.append("")

            if cb_fields:
                lines.append("## Fields")
                lines.append("")
                lines.append("| Field | Level | Type | Length | Occurs | Redefines |")
                lines.append("|-------|-------|------|--------|--------|-----------|")
                for f in sorted(cb_fields, key=lambda x: x.name):
                    p = f.properties
                    level = p.get("level", "")
                    pic = p.get("pic", "")
                    occurs = p.get("occurs", "")
                    redef = p.get("redefines", "")
                    lines.append(f"| {f.name} | {level} | {pic} | | {occurs} | {redef} |")
                lines.append("")

            lines.extend([
                "## AI Tool Usage",
                "",
                f"When modifying code that uses `{cb.name}`, load this skill first.",
                f"Reference: `skill_view(name='copybook-{_safe_slug(cb.name)}')`",
                "",
                "### Key facts for agents",
                f"- Copybook contains {len(cb_fields)} fields",
                f"- Used by {len(includers.get(cb.id, []))} programs",
                "- Check FIELD nodes for field-level details (PIC, OCCURS, REDEFINES)",
            ])

            outputs.append(SkillOutput(
                id=f"copybook-{_safe_slug(cb.name)}",
                title=f"Copybook: {cb.name}",
                category="copybook",
                content="\n".join(lines),
                related_nodes=[cb.id] + [f.id for f in cb_fields],
            ))

        # Summary skill
        summary_lines = [
            "---",
            "name: copybook-overview",
            "description: Overview of all copybooks in the codebase",
            "category: copybook",
            "---",
            "",
            "# Copybook Overview",
            "",
            f"**Total copybooks:** {len(copybooks)}",
            f"**Total fields:** {len(fields)}",
            "",
            "| Copybook | Fields | Used By |",
            "|----------|--------|---------|",
        ]
        for cb in sorted(copybooks, key=lambda x: x.name):
            n_fields = sum(1 for f in fields if field_parent.get(f.id) == cb.id)
            n_users = len(includers.get(cb.id, []))
            summary_lines.append(f"| {cb.name} | {n_fields} | {n_users} |")

        outputs.append(SkillOutput(
            id="copybook-overview",
            title="Copybook Overview",
            category="copybook",
            content="\n".join(summary_lines),
            related_nodes=[cb.id for cb in copybooks],
        ))

        return outputs


def _safe_slug(name: str) -> str:
    return name.lower().replace(" ", "-").replace("_", "-")
