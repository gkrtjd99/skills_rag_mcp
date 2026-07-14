"""Build and run disposable Docker model benchmarks, then remove containers/cache."""

from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import subprocess
import tempfile
from pathlib import Path


def slug(model: str) -> str:
    return re.sub(r"[^A-Za-z0-9_.-]+", "-", model).strip("-")


def run(cmd: list[str]) -> None:
    subprocess.run(cmd, check=True)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("models", nargs="+", help="Hugging Face model ids")
    parser.add_argument("--output", type=Path, default=Path("var/benchmark-results"))
    parser.add_argument("--image", default="skill-rag-benchmark:local")
    parser.add_argument("--keep-cache", action="store_true")
    parser.add_argument("--cpus", default="4")
    parser.add_argument("--memory", default="8g")
    parser.add_argument("--dataset", default="eval/fixtures/queries.jsonl")
    parser.add_argument("--corpus", default="eval/fixtures/skills")
    parser.add_argument("--k", type=int, default=5)
    args = parser.parse_args()

    repo = Path(__file__).resolve().parents[1]
    args.output.mkdir(parents=True, exist_ok=True)
    dataset = Path(args.dataset)
    corpus = Path(args.corpus)
    if dataset.is_absolute() or corpus.is_absolute():
        raise SystemExit("--dataset and --corpus must be paths inside the repository")
    container_dataset = f"/app/{dataset.as_posix()}"
    container_corpus = f"/app/{corpus.as_posix()}"
    run(["docker", "build", "-f", str(repo / "bench/Dockerfile"), "-t", args.image, str(repo)])
    results: list[dict] = []
    volumes: list[str] = []
    try:
        for model in args.models:
            name = slug(model)
            volume = f"skill-rag-bench-cache-{os.getpid()}-{name}"
            volumes.append(volume)
            run(["docker", "volume", "create", volume])
            # Download/prefetch is a separate network-enabled phase.
            run([
                "docker", "run", "--rm", "-e", "HF_HOME=/cache/hf",
                "-v", f"{volume}:/cache", "--entrypoint", "uv", args.image,
                "run", "--no-sync", "python", "-c",
                "from sentence_transformers import SentenceTransformer; SentenceTransformer(__import__('sys').argv[1], local_files_only=False)", model,
            ])
            output = args.output / f"{name}.json"
            run([
                "docker", "run", "--rm", "--network=none", "--cpus", args.cpus,
                "--memory", args.memory, "-e", "HF_HOME=/cache/hf",
                "-v", f"{volume}:/cache", "-v", f"{args.output.resolve()}:/results",
                args.image, "--model", model,
                "--dataset", container_dataset,
                "--corpus", container_corpus,
                "--k", str(args.k),
                "--output", f"/results/{output.name}",
            ])
            results.append(json.loads(output.read_text(encoding="utf-8")))
            if not args.keep_cache:
                subprocess.run(["docker", "volume", "rm", "-f", volume], check=False)
    finally:
        if not args.keep_cache:
            for volume in volumes:
                subprocess.run(["docker", "volume", "rm", "-f", volume], check=False)
    summary = args.output / "summary.json"
    summary.write_text(json.dumps(results, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    lines = ["# Docker embedding benchmark", "", "| model | recall@5 | MRR | p50 ms | p95 ms | peak RSS MB | cgroup peak MB | HF cache MB |", "|---|---:|---:|---:|---:|---:|---:|---:|"]
    for row in results:
        lines.append(
            f"| {row['model']} | {row['recall_at_k']:.3f} | {row['mrr']:.3f} | "
            f"{row['p50_query_ms']:.2f} | {row['p95_query_ms']:.2f} | "
            f"{row['rss_peak_mb']:.1f} | {row.get('cgroup_memory_peak_mb', 0):.1f} | "
            f"{row.get('hf_cache_bytes', 0) / 1048576:.1f} |"
        )
    (args.output / "summary.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(summary)


if __name__ == "__main__":
    main()
