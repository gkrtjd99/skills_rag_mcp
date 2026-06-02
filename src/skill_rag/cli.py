from __future__ import annotations

import json
import os
import tempfile
from pathlib import Path as _Path

import typer

from . import collect as collect_mod
from . import corpus as corpus_mod
from . import index as index_mod
from . import lifecycle
from . import retrieve
from . import sync as sync_mod
from . import embed as embed_mod
from . import translate as translate_mod

app = typer.Typer(no_args_is_help=True, help="skill_rag — local RAG over ~/.skills.")
PROJECT_ROOT = _Path(__file__).resolve().parents[2]
DEFAULT_EVAL_CORPUS = PROJECT_ROOT / "eval" / "fixtures" / "skills"
DEFAULT_EVAL_DATASET = PROJECT_ROOT / "eval" / "fixtures" / "queries.jsonl"


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
    duplicates = report.get("duplicate_names", [])
    if duplicates:
        typer.echo(f"duplicate names skipped: {len(duplicates)}")
        for item in duplicates:
            typer.echo(f"  ! {item['name']}")
            typer.echo(f"      kept    {item['kept']}")
            typer.echo(f"      skipped {item['skipped']}")


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
def collect(
    dry_run: bool = typer.Option(
        False, "--dry-run", help="Show what would be linked without writing."
    ),
    json_out: bool = typer.Option(False, "--json"),
):
    """Symlink skills from Claude/Codex installations into ~/.skills/."""
    report = collect_mod.apply(dry_run=dry_run)
    if json_out:
        typer.echo(json.dumps(report.to_dict(), ensure_ascii=False, indent=2))
        return
    typer.echo(f"target       = {corpus_mod.CORPUS_PATH}")
    typer.echo("sources:")
    for s in report.sources_scanned:
        marker = "·" if s.exists() else "✗"
        typer.echo(f"  {marker} {s}")
    verb = "would link" if dry_run else "linked"
    typer.echo(f"{verb}: {len(report.linked)}")
    for n in report.linked:
        typer.echo(f"  + {n}")
    if report.already_present:
        typer.echo(f"already present (skipped): {len(report.already_present)}")
        for n in report.already_present:
            typer.echo(f"  = {n}")
    if report.collisions:
        typer.echo(f"name collisions (kept first): {len(report.collisions)}")
        for name, kept, rejected in report.collisions:
            typer.echo(f"  ! {name}")
            typer.echo(f"      kept     {kept}")
            typer.echo(f"      rejected {rejected}")
    if dry_run:
        typer.echo("\n(dry-run — no symlinks created)")


@app.command()
def status(json_out: bool = typer.Option(False, "--json")):
    """Show corpus, index, model, retrieval, and sync settings."""
    payload = {
        "corpus_path": str(corpus_mod.CORPUS_PATH),
        "corpus_exists": corpus_mod.CORPUS_PATH.exists(),
        "index_path": str(index_mod.index_path()),
        "indexed_count": index_mod.indexed_count(),
        "model": embed_mod.DEFAULT_MODEL,
        "local_files_only": embed_mod.LOCAL_FILES_ONLY,
        "max_seq_length": embed_mod.MAX_SEQ_LENGTH,
        "score_threshold": corpus_mod.SCORE_THRESHOLD,
        "bm25_threshold": corpus_mod.BM25_THRESHOLD,
        "rrf_k": corpus_mod.RRF_K,
        "translation_enabled": translate_mod.TRANSLATE_ENABLED,
        "sync_ttl_seconds": corpus_mod.SYNC_TTL_SECONDS,
    }
    if json_out:
        typer.echo(json.dumps(payload, ensure_ascii=False, indent=2))
        return
    typer.echo(f"corpus path     : {payload['corpus_path']}")
    typer.echo(f"corpus exists   : {payload['corpus_exists']}")
    typer.echo(f"index path      : {payload['index_path']}")
    typer.echo(f"indexed skills  : {payload['indexed_count']}")
    typer.echo(f"embedding model : {payload['model']}")
    typer.echo(f"local files only: {payload['local_files_only']}")
    typer.echo(f"max seq length  : {payload['max_seq_length']}")
    typer.echo(f"dense threshold : {payload['score_threshold']}")
    typer.echo(f"BM25 threshold  : {payload['bm25_threshold']}")
    typer.echo(f"RRF k           : {payload['rrf_k']}")
    typer.echo(f"translation     : {payload['translation_enabled']}")
    typer.echo(f"sync TTL (s)    : {payload['sync_ttl_seconds']}")


@app.command()
def reset():
    """Drop the index entirely. Next `sync` will rebuild it."""
    index_mod.reset()
    sync_mod.reset_cache()
    typer.echo("index dropped.")


@app.command()
def install(
    dry_run: bool = typer.Option(False, "--dry-run", help="Show actions without writing."),
    json_out: bool = typer.Option(False, "--json"),
):
    """Install the bootstrap skill, collect+index skills, register the MCP server."""
    report = lifecycle.install(dry_run=dry_run)
    if json_out:
        typer.echo(json.dumps(report, ensure_ascii=False, indent=2))
        return
    typer.echo(f"bootstrap installed : {report['bootstrap_installed']}")
    typer.echo(f"harness links       : {len(report['harness_links'])}")
    typer.echo(f"collect ran         : {report['collect_ran']}")
    typer.echo(f"sync ran            : {report['sync_ran']}")
    typer.echo(f"mcp                 : {report['mcp']}")
    if dry_run:
        typer.echo("\n(dry-run — nothing written)")


@app.command()
def uninstall(
    purge: bool = typer.Option(False, "--purge", help="Also delete the entire ~/.skills corpus."),
    yes: bool = typer.Option(False, "--yes", "-y", help="Skip the confirmation prompt."),
    dry_run: bool = typer.Option(False, "--dry-run", help="Show actions without writing."),
    json_out: bool = typer.Option(False, "--json"),
):
    """Reverse `install`: unregister MCP, remove harness links + bootstrap + index.

    Default keeps hand-placed real skill dirs; `--purge` empties ~/.skills.
    """
    if not dry_run and not yes:
        scope = "the ENTIRE ~/.skills corpus" if purge else "skill-rag's footprint"
        typer.echo(f"About to remove {scope}, the index, harness links, and MCP registration.")
        if not typer.confirm("Continue?"):
            typer.echo("aborted.")
            raise typer.Exit(1)
    report = lifecycle.uninstall(purge=purge, dry_run=dry_run)
    if json_out:
        typer.echo(json.dumps(report, ensure_ascii=False, indent=2))
        return
    c = report["corpus"]
    typer.echo(f"mcp                 : {report['mcp']}")
    typer.echo(f"harness links rm    : {len(report['harness_links_removed'])}")
    typer.echo(f"index dropped       : {report['index_dropped']}")
    typer.echo(f"corpus symlinks     : {len(c['removed_links'])}")
    typer.echo(f"corpus dirs removed : {len(c['removed_dirs'])}")
    typer.echo(f"corpus kept         : {len(c['kept'])}")
    if dry_run:
        typer.echo("\n(dry-run — nothing written)")


@app.command()
def mcp():
    """Start the MCP server over stdio."""
    from .mcp_server import run

    run()

@app.command()
def eval(
    dataset: _Path = typer.Option(DEFAULT_EVAL_DATASET, "--dataset", "-d"),
    corpus: _Path = typer.Option(
        DEFAULT_EVAL_CORPUS,
        "--corpus",
        "-c",
        help="Skill corpus to evaluate. Defaults to the repo fixture corpus.",
    ),
    k: int = typer.Option(5, "--k", "-k"),
    json_out: bool = typer.Option(False, "--json"),
):
    """Run the evaluation harness against a corpus and query set."""
    from .evaluator import evaluate as _eval, load_cases
    from .mcp_server import search_skills

    corpus = corpus.expanduser().resolve()
    dataset = dataset.expanduser().resolve()
    cases = load_cases(dataset)

    old_corpus = corpus_mod.CORPUS_PATH
    old_index_env = os.environ.get("SKILL_RAG_INDEX_PATH")
    try:
        with tempfile.TemporaryDirectory(prefix="skill-rag-eval-") as tmp:
            os.environ["SKILL_RAG_INDEX_PATH"] = str(_Path(tmp) / "index.lance")
            corpus_mod.CORPUS_PATH = corpus
            sync_mod.reset_cache()
            report = _eval(cases, k=k, search_fn=search_skills)
            sync_mod.reset_cache()
    finally:
        corpus_mod.CORPUS_PATH = old_corpus
        if old_index_env is None:
            os.environ.pop("SKILL_RAG_INDEX_PATH", None)
        else:
            os.environ["SKILL_RAG_INDEX_PATH"] = old_index_env

    if json_out:
        payload = report.to_dict()
        payload["dataset"] = str(dataset)
        payload["corpus"] = str(corpus)
        typer.echo(json.dumps(payload, ensure_ascii=False, indent=2))
        return
    typer.echo(f"dataset      = {dataset}")
    typer.echo(f"corpus       = {corpus}")
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
