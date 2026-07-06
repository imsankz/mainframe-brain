"""Rule Historian — tracks business rule changes over time via node_history."""

from collections import defaultdict

from mainframe_brain.graph.schema import NodeType
from mainframe_brain.graph.store import GraphStore

from . import SkillOutput


class RuleHistorian:
    """Tracks which business rules changed, when, and what they were before."""

    agent_id = "rule-historian"
    agent_name = "Rule Historian"
    category = "history"

    def analyze(self, store: GraphStore) -> list[SkillOutput]:
        rules = [n for n in store.all_nodes() if n.type == NodeType.BUSINESS_RULE]

        # Group history entries by rule ID
        history: dict[str, list[dict]] = defaultdict(list)
        try:
            if hasattr(store, '_conn'):
                rows = store._conn.execute(  # type: ignore[attr-defined]
                "SELECT id, content_hash, last_verified, op, ts FROM node_history "
                "WHERE type = ? ORDER BY ts DESC",
                (NodeType.BUSINESS_RULE.value,)
            ).fetchall()
            for row in rows:
                history[row["id"]].append({
                    "content_hash": row["content_hash"],
                    "last_verified": row["last_verified"],
                    "op": row["op"],
                    "ts": row["ts"],
                })
        except Exception:
            pass

        if not rules:
            return []

        lines = [
            "---",
            "name: rule-history",
            "description: Business rule change log over time",
            "category: history",
            "---",
            "",
            "# Business Rule History",
            "",
            f"**Total rules:** {len(rules)}",
            f"**Verified rules:** {sum(1 for r in rules if r.properties.get('human_verified'))}",
            f"**Unverified rules:** {sum(1 for r in rules if not r.properties.get('human_verified'))}",
            "",
        ]

        # Rules with history (changed over time)
        changed = {rid: entries for rid, entries in history.items() if len(entries) > 1}
        if changed:
            lines.append("## Rules With History")
            lines.append("")
            lines.append("| Rule | Changes | Last Updated |")
            lines.append("|------|---------|-------------|")

            for rid, entries in sorted(changed.items()):
                rule = store.get_node(rid)
                name = rule.name if rule else rid.split(":")[-1][:40]
                lines.append(f"| {name} | {len(entries)} | {entries[0]['ts'][:19]} |")
            lines.append("")

        # Rules never updated (first-time enrichment only)
        first_time = [r for r in rules if r.id not in changed and r.properties.get("human_verified")]
        if first_time:
            lines.append(f"## Stable Rules ({len(first_time)})")
            lines.append("")
            lines.append("These rules have not changed since first enrichment:")
            lines.append("")
            for r in sorted(first_time, key=lambda x: x.name)[:20]:
                lines.append(f"- {r.name}")
            if len(first_time) > 20:
                lines.append(f"- ... and {len(first_time) - 20} more")
            lines.append("")

        # Unverified rules
        unverified = [r for r in rules if not r.properties.get("human_verified")]
        if unverified:
            lines.append(f"## Unverified Rules ({len(unverified)})")
            lines.append("")
            lines.append("These rules need human review:")
            lines.append("")
            for r in sorted(unverified, key=lambda x: x.name)[:20]:
                lines.append(f"- [ ] `{r.name}` — verify: `mainframe-brain verify --store-path brain.db \"{r.id}\"`")
            lines.append("")

        return [SkillOutput(
            id="rule-history",
            title="Business Rule History",
            category="history",
            content="\n".join(lines),
            related_nodes=[r.id for r in rules],
        )]
