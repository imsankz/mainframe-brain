"""Dependency Mapper — program-to-data and program-to-program impact analysis."""

from collections import defaultdict

from mainframe_brain.graph.schema import EdgeType, NodeType
from mainframe_brain.graph.store import GraphStore

from . import SkillOutput


class DependencyMapper:
    """Per-program skill: what it reads/writes/calls, what depends on it."""

    agent_id = "dependency-mapper"
    agent_name = "Dependency Mapper"
    category = "dependency"

    def analyze(self, store: GraphStore) -> list[SkillOutput]:
        programs = [n for n in store.all_nodes() if n.type == NodeType.PROGRAM]
        if not programs:
            return []

        # Build reverse index: what calls/reads/writes this?
        callers: dict[str, list[str]] = defaultdict(list)
        readers: dict[str, list[str]] = defaultdict(list)
        writers: dict[str, list[str]] = defaultdict(list)
        caller_names: dict[str, str] = {}

        for n in store.all_nodes():
            caller_names[n.id] = n.name

        for e in store.all_edges():
            if e.type == EdgeType.CALLS:
                callers[e.dst].append(e.src)
            elif e.type == EdgeType.READS:
                readers[e.dst].append(e.src)
            elif e.type == EdgeType.WRITES:
                writers[e.dst].append(e.src)

        outputs: list[SkillOutput] = []

        for prog in programs:
            # What does this program call/read/write?
            callees = [store.get_node(n.id) for n in store.neighbors(prog.id, EdgeType.CALLS.value)]
            callees = [n for n in callees if n is not None]
            reads = [store.get_node(n.id) for n in store.neighbors(prog.id, EdgeType.READS.value)]
            reads = [n for n in reads if n is not None]
            writes = [store.get_node(n.id) for n in store.neighbors(prog.id, EdgeType.WRITES.value)]
            writes = [n for n in writes if n is not None]

            called_by = [caller_names.get(c, c) for c in callers.get(prog.id, [])]
            read_by = [caller_names.get(r, r) for r in readers.get(prog.id, [])]
            written_by = [caller_names.get(w, w) for w in writers.get(prog.id, [])]

            lines = [
                "---",
                f"name: dependency-{_slug(prog.name)}",
                f"description: Dependency map for program {prog.name}",
                "category: dependency",
                "---",
                "",
                f"# Dependency Map: {prog.name}",
                "",
                f"**Node ID:** `{prog.id}`",
                "",
            ]

            if callees:
                lines.append("## Calls")
                lines.append("")
                for c in callees:
                    lines.append(f"- **{c.name}** ({c.type.value})")
                lines.append("")

            if reads:
                lines.append("## Reads")
                lines.append("")
                for r in reads:
                    lines.append(f"- **{r.name}** ({r.type.value})")
                lines.append("")

            if writes:
                lines.append("## Writes")
                lines.append("")
                for w in writes:
                    lines.append(f"- **{w.name}** ({w.type.value})")
                lines.append("")

            if called_by:
                lines.append("## Called By")
                for c in sorted(called_by):
                    lines.append(f"- {c}")
                lines.append("")

            if read_by:
                lines.append("## Read By")
                for r in sorted(read_by):
                    lines.append(f"- {r}")
                lines.append("")

            if written_by:
                lines.append("## Written By")
                for w in sorted(written_by):
                    lines.append(f"- {w}")
                lines.append("")

            lines.extend([
                "## Impact Analysis Questions",
                "",
                f"1. If I change `{prog.name}`, what breaks? → Check **Called By** above",
                f"2. If I change a data source, does `{prog.name}` need updates? → Check **Reads/Writes** above",
                f"3. What's the blast radius? → {len(called_by)} upstream, {len(callees)} downstream",
            ])

            outputs.append(SkillOutput(
                id=f"dependency-{_slug(prog.name)}",
                title=f"Dependency Map: {prog.name}",
                category="dependency",
                content="\n".join(lines),
                related_nodes=[prog.id],
            ))

        return outputs


def _slug(name: str) -> str:
    return name.lower().replace(" ", "-").replace("_", "-")
