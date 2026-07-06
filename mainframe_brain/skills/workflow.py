"""JCL Workflow Narrator — explains job streams in plain English."""

from mainframe_brain.graph.schema import EdgeType, NodeType
from mainframe_brain.graph.store import GraphStore

from . import SkillOutput


class JCLWorkflowNarrator:
    """Per-JCL-job skill: what runs when, in what order, with what dependencies."""

    agent_id = "workflow-narrator"
    agent_name = "JCL Workflow Narrator"
    category = "workflow"

    def analyze(self, store: GraphStore) -> list[SkillOutput]:
        jobs = [n for n in store.all_nodes() if n.type == NodeType.JCL_JOB]
        if not jobs:
            return []

        outputs: list[SkillOutput] = []

        for job in jobs:
            steps = sorted(
                [n for n in store.neighbors(job.id) if n.type == NodeType.JCL_STEP],
                key=lambda s: int(s.properties.get("step_number", 0)),
            )

            lines = [
                "---",
                f"name: workflow-{_slug(job.name)}",
                f"description: Job stream walkthrough for {job.name}",
                "category: workflow",
                "---",
                "",
                f"# Job Stream: {job.name}",
                "",
                f"**Total steps:** {len(steps)}",
                "",
            ]

            if steps:
                lines.append("## Step Sequence")
                lines.append("")
                lines.append("| Step | Program | Dataset | Condition |")
                lines.append("|------|---------|---------|-----------|")

                for step in steps:
                    p = step.properties
                    prog = p.get("program", p.get("utility", "—"))
                    dataset = p.get("dataset", "—")
                    cond = p.get("condition", "—")
                    s_num = p.get("step_number", "?")
                    lines.append(f"| {s_num} | {prog} | {dataset} | {cond} |")

                lines.append("")

            # Programs executed by steps
            for step in steps:
                exec_neighbors = [n for n in store.neighbors(step.id, EdgeType.EXECUTES.value)
                                  if n.type == NodeType.PROGRAM]
                if exec_neighbors:
                    for prog in exec_neighbors:
                        lines.append(f"- Step `{step.name}` executes **{prog.name}**")

            if not steps:
                lines.append("_No steps found — JCL may not have been fully extracted._")

            lines.extend([
                "",
                "## AI Tool Usage",
                "",
                f"When analyzing or modifying the `{job.name}` job stream, load this skill.",
                "It maps the step-by-step execution order and program-to-step assignments.",
            ])

            outputs.append(SkillOutput(
                id=f"workflow-{_slug(job.name)}",
                title=f"Job Stream: {job.name}",
                category="workflow",
                content="\n".join(lines),
                related_nodes=[job.id],
            ))

        return outputs


def _slug(name: str) -> str:
    return name.lower().replace(" ", "-").replace("_", "-")
