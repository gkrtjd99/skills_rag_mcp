# skill_rag

**한국어** | [English](README.en.md)

`~/.skills/` 에 모아둔 스킬들을 자연어로 검색해서 필요한 것만 에이전트 컨텍스트에 올리는 로컬 RAG.

세션 시작 시 메타-스킬 1개만 자동 로드되고, 나머지 N개는 매 사용자 메시지마다
MCP로 검색해서 적합한 본문만 가져옴. 따라서 처음부터 모든 스킬을 읽느라 컨텍스트
소모하지 않음.

## 핵심 동작

```
사용자 메시지
   │
   ▼
에이전트 → search_skills(query)  ─→ top-k 메타 (name, desc, score)
                                       │
                                       ▼ 적합한 것만
                                  get_skill(name) ─→ SKILL.md 본문
```

- 임베딩: `BAAI/bge-m3` 로컬 모델 (외부 API 호출 없음). 강력한 교차언어 검색 —
  한국어 쿼리가 영어 스킬 설명과도 매칭됨.
- 벡터 DB: LanceDB
- 인덱스: `search_skills` 호출 시 TTL 30s 캐시로 자동 sync

## 설치

```bash
git clone <repo-url>
cd skill_rag
make install
```

`make install`은 idempotent하며 다음 순서로 동작:

1. `uv sync`
2. 부트스트랩 메타-스킬 `~/.skills/using-skill-rag/` 설치 후
   `~/.claude/skills/`, `~/.codex/skills/`에 심볼릭 링크
3. `skill-rag collect` — 발견된 하네스 스킬을 `~/.skills/`에 심볼릭으로 모음
4. `skill-rag sync` — 첫 실행 시 임베딩 모델 다운로드 후 인덱스 빌드
5. MCP 서버 등록 (Claude Code는 `claude mcp add`; Codex는
   `~/.codex/config.toml`)

이후 하네스를 재시작.

### 동작 확인

하네스를 재시작한 뒤 새 세션에서:

- 시작 시 `using-skill-rag` 메타-스킬이 자동 로드되는지 확인
- 아무 메시지에서나 `mcp__skill-rag__search_skills` 도구가 보이는지 확인
- 직접 호출해 보기: `search_skills(query="...", k=5)` → `{status: "ok"|"no_match", hits, ...}`

CLI에서도 같은 검색이 동작하는지 빠르게 확인:

```bash
uv run skill-rag query "deploy to vercel"
```

### 기타 MCP 호환 클라이언트 (Cursor, Windsurf 등)

`make install`은 Claude Code와 Codex만 자동 등록. 다른 클라이언트는
아래 커맨드로 수동 등록:

```
uv --directory <repo> run skill-rag mcp
```

## 제거

```bash
make uninstall   # skill-rag 설치 내용 제거; 직접 둔 스킬은 보존
make purge       # ~/.skills 전체도 비움
```

`uninstall`은 install을 역순으로 실행: MCP 서버 등록 해제, 하네스 부트스트랩
심볼릭 링크 및 인덱스 제거, 수집된 심볼릭 링크 및 부트스트랩 스킬 제거.
`~/.skills` 아래 직접 둔 실제 스킬 디렉터리는 `purge`를 쓰지 않는 한 보존됨.

## 스킬 추가

`~/.skills/<name>/SKILL.md` 형식으로 파일 작성:

```markdown
---
name: my-skill
description: 한 줄 설명. 검색 정확도가 여기 품질에 좌우됨.
---

# 본문
스킬 사용법을 자세히 적음.
```

다음 `search_skills` 호출 시 30초 이내에 자동 인덱싱됨.

## CLI

| 명령 | 설명 |
| --- | --- |
| `uv run skill-rag status` | 코퍼스 경로/모델/인덱스 수/임계값 한눈에 |
| `uv run skill-rag collect [--dry-run]` | 하네스 스킬을 `~/.skills/`로 심볼릭 수집 |
| `uv run skill-rag sync` | 인덱스 수동 동기화 |
| `uv run skill-rag query "<text>"` | 검색 결과 확인 |
| `uv run skill-rag list-skills` | 인덱스된 스킬 목록 |
| `uv run skill-rag eval` | 공개 fixture 평가셋으로 recall@5 측정 |
| `uv run skill-rag reset` | 인덱스 초기화 |
| `uv run skill-rag mcp` | MCP 서버 실행 |
| `uv run skill-rag install` | 부트스트랩 설치 + collect/인덱싱 + MCP 등록 (`make install` 권장) |
| `uv run skill-rag uninstall [--purge] [--dry-run] [-y]` | install 역순; `--purge`는 `~/.skills` 통째 비움 |

## 환경 변수

| 변수 | 기본 | 설명 |
| --- | --- | --- |
| `SKILL_RAG_CORPUS_PATH` | `~/.skills` | corpus 경로 |
| `SKILL_RAG_INDEX_PATH` | `./var/index.lance` | LanceDB 경로 |
| `SKILL_RAG_MODEL` | `BAAI/bge-m3` | 임베딩 모델 |
| `SKILL_RAG_LOCAL_FILES_ONLY` | `1` | 로컬 캐시에서만 임베딩 모델 로드 |
| `SKILL_RAG_SCORE_THRESHOLD` | `0.45` | dense 매칭 임계값 (bge-m3 기준 calibration) |
| `SKILL_RAG_SYNC_TTL` | `30` | sync 캐시 TTL (초) |

`skill-rag eval`은 기본적으로 `eval/fixtures/` 아래의 공개 fixture를 사용하므로
GitHub에서 받은 사용자도 같은 기준으로 검증할 수 있음. 개인 코퍼스를 점검하려면
경로를 명시:

```bash
uv run skill-rag eval --corpus ~/.skills --dataset eval/queries.jsonl
```

## 문서

- `AGENTS.md` — 에이전트가 첫 작업 전 읽을 순서
- `ARCHITECTURE.md` — 모듈 구조
- `docs/product-specs/skill-rag.md` — 무엇을, 왜
- `docs/design-docs/` — 설계 결정 로그
- `docs/superpowers/specs/` — 기능별 설계 스펙
```
