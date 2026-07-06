"""Mainframe Brain command-line interface."""
from __future__ import annotations

import click

from mainframe_brain.cli._common import get_extractors as get_extractors  # noqa: F401
from mainframe_brain.cli.commands.build_graph import build_graph
from mainframe_brain.cli.commands.enrich import enrich
from mainframe_brain.cli.commands.explore import explore
from mainframe_brain.cli.commands.extract import extract
from mainframe_brain.cli.commands.list_nodes import list_nodes
from mainframe_brain.cli.commands.query import query
from mainframe_brain.cli.commands.triage import triage
from mainframe_brain.cli.commands.verify import edit_rule, flag_rule, verify
from mainframe_brain.cli.commands.generate_skills import generate_skills


@click.group()
@click.version_option(version="0.1.0", prog_name="mainframe-brain")
def cli() -> None:
    """Mainframe Brain — deterministic extraction + selective LLM enrichment."""


cli.add_command(extract)
cli.add_command(enrich)
cli.add_command(triage)
cli.add_command(query)
cli.add_command(verify)
cli.add_command(flag_rule)
cli.add_command(edit_rule)
cli.add_command(explore)
cli.add_command(list_nodes)
cli.add_command(build_graph)
cli.add_command(generate_skills)
