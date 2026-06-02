.PHONY: install uninstall purge sync status reset eval test

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

test:
	uv run pytest -q
