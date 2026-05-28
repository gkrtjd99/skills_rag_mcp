from __future__ import annotations

import json

import typer

from . import index as index_mod
from . import retrieve
from . import sync as sync_mod

app = typer.Typer(no_args_is_help=True, help="skill_rag — local RAG over ~/.skills.")


@app.command()
def sync(json_out: bool = typer.Option(False, "--json")):
    """Reconcile the index against ~/.skills."""
    report = sync_mod.run_sync()
    if json_out:
        typer.echo(json.dumps(report, ensure_ascii=False, indent=2))
        return
    typer.echo(f"added:     {len(report['added'])}")
    for n in report["added"]:
        typer.echo(f"  + {n}")
    typer.echo(f"updated:   {len(report['updated'])}")
    for n in report["updated"]:
        typer.echo(f"  ~ {n}")
    typer.echo(f"removed:   {len(report['removed'])}")
    for n in report["removed"]:
        typer.echo(f"  - {n}")
    typer.echo(f"unchanged: {report['unchanged']}")


@app.command()
def query(
    text: str = typer.Argument(..., help="Natural-language query."),
    k: int = typer.Option(5, "--k", "-k", min=1, max=50),
    json_out: bool = typer.Option(False, "--json"),
):
    """Return top-k skills for the query."""
    res = retrieve.search(text, k=k)
    if json_out:
        typer.echo(json.dumps(res, ensure_ascii=False, indent=2))
        return
    if res["status"] == "no_match":
        typer.echo(f"(no match — {res['message']})")
        return
    for rank, h in enumerate(res["hits"], start=1):
        typer.echo(f"{rank}. [{h['score']:.3f}] {h['name']}")
        typer.echo(f"   {h['description'][:140]}")


@app.command(name="list-skills")
def list_skills(json_out: bool = typer.Option(False, "--json")):
    """List skills currently indexed."""
    rows = index_mod.list_indexed()
    if json_out:
        typer.echo(json.dumps(rows, ensure_ascii=False, indent=2))
        return
    if not rows:
        typer.echo("(index is empty)")
        return
    for r in rows:
        typer.echo(f"- {r['name']}  ({r['path']})")


@app.command()
def reset():
    """Drop the index entirely. Next `sync` will rebuild it."""
    index_mod.reset()
    sync_mod.reset_cache()
    typer.echo("index dropped.")


@app.command()
def mcp():
    """Start the MCP server over stdio."""
    from .mcp_server import run

    run()


from pathlib import Path as _Path


@app.command()
def eval(
    dataset: _Path = typer.Option(_Path("eval/queries.jsonl"), "--dataset", "-d"),
    k: int = typer.Option(5, "--k", "-k"),
    json_out: bool = typer.Option(False, "--json"),
):
    """Run the evaluation harness."""
    from .evaluator import evaluate as _eval, load_cases

    cases = load_cases(dataset)
    report = _eval(cases, k=k)
    if json_out:
        typer.echo(json.dumps(report.to_dict(), ensure_ascii=False, indent=2))
        return
    typer.echo(f"n            = {report.n}")
    typer.echo(f"recall@{report.k:<5} = {report.recall_at_k:.3f}")
    typer.echo(f"mrr          = {report.mrr:.3f}")
    typer.echo(f"latency p50  = {report.p50_ms:.1f} ms")
    typer.echo(f"latency p95  = {report.p95_ms:.1f} ms")
    if report.misses:
        typer.echo(f"\nmisses ({len(report.misses)}):")
        for m in report.misses:
            typer.echo(f"  q={m['query']!r}")
            typer.echo(f"    expected={m['expected']}")
            typer.echo(f"    got={m['got']}")


if __name__ == "__main__":
    app()
