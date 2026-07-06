"""Pattern Detective — finds anti-patterns and code smells."""

from collections import defaultdict

from mainframe_brain.graph.schema import EdgeType, NodeType
from mainframe_brain.graph.store import GraphStore

from . import SkillOutput


class PatternDetective:
    """Finds code smells: unreachable paragraphs, GOTO chains, orphan nodes."""

    agent_id = "pattern-detective"
    agent_name = "Pattern Detective"
    category = "patterns"

    def analyze(self, store: GraphStore) -> list[SkillOutput]:
        paragraphs = [n for n in store.all_nodes() if n.type == NodeType.PARAGRAPH]
        programs = [n for n in store.all_nodes() if n.type == NodeType.PROGRAM]

        findings: list[str] = []
        related: list[str] = []

        # 1. Unreachable paragraphs: any paragraph with zero incoming PERFORMS edges
        performed_from: dict[str, set[str]] = defaultdict(set)
        for e in store.all_edges():
            if e.type == EdgeType.PERFORMS:
                performed_from[e.dst].add(e.src)

        unreachable = [p for p in paragraphs if not performed_from.get(p.id)]
        if unreachable:
            findings.append("## Unreachable Paragraphs\n")
            findings.append("These paragraphs have no PERFORMS edge pointing to them — they may be dead code.\n")
            findings.append("| Paragraph | Program |")
            findings.append("|-----------|---------|")
            for p in unreachable:
                prog_name = _program_for(store, p.id)
                findings.append(f"| {p.name} | {prog_name} |")
                related.append(p.id)
            findings.append("")

        # 2. GOTO chains: paragraphs where GOTO count > 3
        goto_heavy = [p for p in paragraphs if (p.properties.get("goto_density", 0) or 0) > 0.5]
        if goto_heavy:
            findings.append("## GOTO-Heavy Paragraphs\n")
            findings.append("GOTO density > 0.5 indicates unstructured control flow.\n")
            findings.append("| Paragraph | GOTO Density | Program |")
            findings.append("|-----------|-------------|---------|")
            for p in goto_heavy:
                prog_name = _program_for(store, p.id)
                density = p.properties.get("goto_density", 0) or 0
                findings.append(f"| {p.name} | {density:.2f} | {prog_name} |")
                related.append(p.id)
            findings.append("")

        # 3. Programs with no CALL edges (monoliths)
        called_progs: set[str] = set()
        for e in store.all_edges():
            if e.type == EdgeType.CALLS:
                called_progs.add(e.dst)

        if programs:
            standalone = [p for p in programs if p.id not in called_progs and not _has_incoming_call(store, p.id)]
            if standalone:
                findings.append("## Standalone Programs\n")
                findings.append("These programs are not called by any other program.\n")
                findings.append("| Program | Complexity | Risk |")
                findings.append("|---------|------------|------|")
                for p in standalone:
                    comp = p.properties.get("cyclomatic_complexity", 0) or 0
                    findings.append(f"| {p.name} | {comp} | trivial |")
                    related.append(p.id)
                findings.append("")

        if not findings:
            return []

        content = "\n".join([
            "---",
            "name: pattern-detective",
            "description: Anti-patterns and code smell findings",
            "category: patterns",
            "---",
            "",
            "# Code Pattern Analysis",
            "",
        ] + findings + [
            "## Recommended Actions",
            "",
            "1. Investigate unreachable paragraphs — confirm they're dead before removing",
            "2. Refactor GOTO-heavy paragraphs into structured control flow (EVALUATE/PERFORM)",
            "3. Consider decomposing standalone programs with high complexity into subprograms",
        ])

        return [SkillOutput(
            id="pattern-detective-report",
            title="Code Pattern Analysis",
            category="patterns",
            content=content,
            related_nodes=related,
        )]


def _program_for(store: GraphStore, para_id: str) -> str:
    for e in store.all_edges():
        if e.type == EdgeType.PERFORMS and e.src == para_id:
            try:
                node = store.get_node(e.dst)
                if node:
                    return node.name
            except Exception:
                pass
    # Fallback: check if there's an EXECUTES edge pointing to a program
    for e in store.all_edges():
        if e.type in (EdgeType.EXECUTES,):
            pass
    return "unknown"


def _has_incoming_call(store: GraphStore, prog_id: str) -> bool:
    for e in store.all_edges():
        if e.type == EdgeType.CALLS and e.dst == prog_id:
            return True
    return False
