.PHONY: install uninstall purge sync status reset eval eval-natural eval-no-match eval-personal eval-codex install-smoke test check build benchmark-docker benchmark-natural-docker

install:
	uv sync
	SKILL_RAG_LOCAL_FILES_ONLY=0 uv run skill-rag install

uninstall:
	uv run skill-rag uninstall

purge:
	uv run skill-rag uninstall --purge

sync:
	uv run skill-rag sync

status:
	uv run skill-rag status

reset:
	uv run skill-rag reset

eval:
	uv run skill-rag eval

eval-natural:
	uv run skill-rag eval --dataset eval/fixtures/natural-queries.jsonl --corpus eval/fixtures/skills --k 1

eval-no-match:
	uv run skill-rag eval --dataset eval/fixtures/no-match-queries.jsonl --corpus eval/fixtures/skills --k 5

eval-personal:
	uv run skill-rag eval --dataset "$${SKILL_RAG_EVAL_DATASET:-eval/queries.jsonl}" --corpus "$${SKILL_RAG_EVAL_CORPUS:-$$HOME/.skills}" --k 5

eval-codex:
	uv run skill-rag eval --dataset eval/queries.jsonl --corpus "$$HOME/.codex/skills/.system" --k 5

install-smoke:
	@tmp=$$(mktemp -d); \
	trap 'rm -rf "$$tmp"' EXIT; \
	HOME="$$tmp" SKILL_RAG_CORPUS_PATH="$$tmp/.skills" \
	SKILL_RAG_INDEX_PATH="$$tmp/index.lance" SKILL_RAG_LOCAL_FILES_ONLY=1 \
	uv run skill-rag install --dry-run --json

test:
	uv run pytest -q

check:
	uv lock --check
	uv run pytest -q
	uv build
	$(MAKE) install-smoke

build:
	uv build

benchmark-docker:
	uv run python bench/run_matrix.py intfloat/multilingual-e5-base BAAI/bge-m3

benchmark-natural-docker:
	uv run python bench/run_matrix.py --dataset eval/fixtures/natural-queries.jsonl --corpus eval/fixtures/skills --k 1 intfloat/multilingual-e5-base BAAI/bge-m3
