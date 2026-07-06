"""generate-skills command — Layer 7 skill agent pipeline."""
from __future__ import annotations

import click


@click.command(name="generate-skills")
@click.option("--store-path", "store_path", required=True)
@click.option("--output-dir", default=".mainframe-brain/skills")
@click.option("--json", "as_json", is_flag=True, help="Output structured JSON instead of human-readable text.")
def generate_skills(store_path: str, output_dir: str, as_json: bool) -> None:
    """Generate AI-tool-ready skills from the knowledge graph (Layer 7).

    8 specialist agents analyze the graph and produce SKILL.md files
    organized by category: migration, patterns, dependency, copybook,
    workflow, risk, tests, history.
    """
    from mainframe_brain.cli._common import _open
    from mainframe_brain.skills.orchestrator import generate_skills as run_skills

    store = _open(store_path)
    result = run_skills(store, output_dir=output_dir)
    store.close()

    summary = {
        "skills_written": result.skills_written,
        "skills_skipped": result.skills_skipped,
        "output_dir": output_dir,
        "errors": result.errors,
        "manifest": result.manifest,
    }

    if as_json:
        import json

        click.echo(json.dumps({
            "status": "ok" if not result.errors else "partial",
            "command": "generate-skills",
            "summary": f"{result.skills_written} skills written to {output_dir}",
            "data": summary,
            "errors": result.errors,
        }, indent=2))
    else:
        click.echo(f"Skills generated: {result.skills_written}")
        click.echo(f"Output directory: {output_dir}")
        click.echo(f"Agents run: {result.manifest.get('agents_run', 8)}")
        if result.errors:
            click.echo("\nErrors:")
            for err in result.errors:
                click.echo(f"  - {err}")
