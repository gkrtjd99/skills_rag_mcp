# skill_rag

**한국어** | [English](README.en.md)

`~/.skills/` 에 모아둔 스킬들을 자연어로 검색해서 필요한 것만 에이전트 컨텍스트에 올리는 로컬 RAG.

skill-rag는 세션 시작 시 메타-스킬 1개만 자동 로드하고, 나머지 N개는 새 작업마다
MCP로 검색해서 적합한 본문만 가져옴. 따라서 skill-rag 자체가 처음부터 모든 스킬을
읽지는 않음. Claude/Codex의 native skill loader 설정은 별도로 동작할 수 있으며,
현재는 fallback을 위해 끄지 않음.

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

- 임베딩: `intfloat/multilingual-e5-base` 로컬 모델 (외부 API 호출 없음). 강력한 교차언어 검색 —
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
4. `skill-rag sync` — 첫 실행 시 임베딩·번역 모델 다운로드 후 인덱스 빌드
5. MCP 서버 등록 (Claude Code는 `claude mcp add`; Codex는
   `~/.codex/config.toml`)

이후 하네스를 재시작.

> 한↔영 번역 도입 이전 버전에서 올린 경우, `uv run skill-rag reset && uv run skill-rag sync`를
> 한 번 실행해 번역 포함 인덱스로 재빌드하세요. 스키마 변경은 자동으로 캐시를 재생성하지만,
> `embed_text()` 내용만 바뀐 경우에는 이 명령이 필요합니다.

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
| `make eval-natural` | 영어·한국어 자연어 fixture를 top-1로 평가 |
| `make eval-no-match` | 관련 스킬이 없는 질의의 no-match 정확도 평가 |
| `make eval-codex` | Codex 기본 시스템 스킬 5개를 고정 gold set으로 평가 |
| `make eval-personal` | 지정한 개인 corpus와 대응 gold set 평가 (`SKILL_RAG_EVAL_CORPUS`, `SKILL_RAG_EVAL_DATASET`) |
| `uv run skill-rag reset` | 인덱스 초기화 |
| `uv run skill-rag mcp` | MCP 서버 실행 |
| `uv run skill-rag install [--refresh-bootstrap]` | 부트스트랩 설치 + collect/인덱싱 + MCP 등록 (`make install` 권장). `--refresh-bootstrap`는 기존 메타-스킬을 템플릿으로 덮어씀 |
| `uv run skill-rag uninstall [--purge] [--dry-run] [-y]` | install 역순; `--purge`는 `~/.skills` 통째 비움 |

## 환경 변수

| 변수 | 기본 | 설명 |
| --- | --- | --- |
| `SKILL_RAG_CORPUS_PATH` | `~/.skills` | corpus 경로 |
| `SKILL_RAG_INDEX_PATH` | `./var/index.lance` | LanceDB 경로 |
| `SKILL_RAG_MODEL` | `intfloat/multilingual-e5-base` | 임베딩 모델 |
| `SKILL_RAG_LOCAL_FILES_ONLY` | `1` | 로컬 캐시에서만 임베딩·번역 모델 로드 |
| `SKILL_RAG_MAX_SEQ_LENGTH` | `512` | 임베딩 입력 토큰 상한 |
| `SKILL_RAG_SCORE_THRESHOLD` | `0.45` | dense 매칭 임계값 (E5 동적 테스트 기준) |
| `SKILL_RAG_BM25_THRESHOLD` | `0.30` | BM25 normalized score 임계값 |
| `SKILL_RAG_RRF_K` | `60` | dense/BM25 reciprocal-rank-fusion 상수 |
| `SKILL_RAG_TRANSLATE` | `1` | 인덱스 시 description 한↔영 자동 번역 (`0`이면 끔) |
| `SKILL_RAG_SYNC_TTL` | `30` | sync 캐시 TTL (초) |

`skill-rag eval`은 기본적으로 `eval/fixtures/` 아래의 공개 fixture를 사용하므로
GitHub에서 받은 사용자도 같은 기준으로 검증할 수 있음. Codex 기본 스킬 gold set은
현재 머신의 `~/.codex/skills/.system`을 대상으로 다음처럼 실행:

```bash
make eval-codex
```

임의의 개인 코퍼스를 점검할 때는 그 코퍼스에 실제 존재하는 스킬 이름으로 별도
gold set을 만들고 경로를 명시:

```bash
SKILL_RAG_EVAL_CORPUS=~/.skills \
SKILL_RAG_EVAL_DATASET=eval/my-corpus-queries.jsonl \
make eval-personal
```

Docker에서 모델을 비교하려면 `make benchmark-docker`를 사용하고, 더 엄격한
영어·한국어 자연어 비교는 `make benchmark-natural-docker`를 사용함.

## 문서

- `AGENTS.md` — 에이전트가 첫 작업 전 읽을 순서
- `ARCHITECTURE.md` — 모듈 구조
- `docs/product-specs/skill-rag.md` — 무엇을, 왜
- `docs/design-docs/` — 설계 결정 로그
- `docs/design-docs/implementation-history.md` — 완료된 과거 specs/plans 요약
- `docs/superpowers/` — 진행 중인 기능 spec/plan이 있을 때만 사용
