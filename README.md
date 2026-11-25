# skill_rag

**한국어** | [English](README.en.md)

에이전트 스킬이 수백 개일 때, 전부 컨텍스트에 올려 두는 대신 요청마다 맞는 스킬만 찾아서
읽게 하는 로컬 검색 서버 (MCP). Claude Code, Codex 및 MCP를 지원하는 클라이언트에서 동작함.

## 목적

Claude Code나 Codex는 설치된 모든 스킬의 이름과 설명을 매 세션 컨텍스트에 올림. 스킬이
많아지면 두 가지 문제가 생김.

- **컨텍스트 비용.** 스킬 350개의 설명만 약 33,750토큰이 항상 차 있음.
- **엉뚱한 스킬을 읽음.** 목록이 길수록 에이전트가 관련 없는 스킬을 집어 듦. 측정에서는 맞는
  스킬이 없는 요청의 54.2%에서 엉뚱한 스킬을 읽었음.

skill-rag는 세션 시작 시 안내용 스킬 1개만 올리고, 나머지는 `~/.skills/`에 모아 두었다가
새 작업마다 `search_skills`로 찾아 `get_skill`로 필요한 본문만 가져옴.

## 써야 하는 상황

아래 기준은 모두 이 저장소의 측정에서 나온 것 ([효과](#효과) 참고).

**쓰는 편이 나은 경우**

- 스킬이 수백 개임. 스킬 하나당 설명이 약 100토큰이므로 350개면 약 33,750토큰이 매 세션 차 있음.
- 판정 모델(`jev`)을 쓸 수 있음. TypeSafe API 키가 있고, 요청 문장과 스킬의 이름·설명이 외부로
  전송되어도 되며, 검색당 약 $0.0009와 0.55초를 감당할 수 있음.
- 에이전트가 관련 없는 스킬을 읽어 작업이 엇나가는 일이 잦음.
- 한국어로 요청하는데 스킬 설명은 영어임 (한국어 요청 89.7%, 영어 92.6%).
- Claude Code와 Codex가 같은 스킬 저장소를 쓰게 하고 싶음.

**쓰지 않는 편이 나은 경우**

- 스킬이 수십 개뿐임. 전체 목록이 2,000토큰 안팎이라 줄일 것이 거의 없음.
- 판정 모델을 쓸 수 없음 (오프라인이거나 외부 전송 불가). 판정 모델 없는 검색은 쓸모 있는 스킬을
  69.6%만 읽었고, 같은 요청에서 전부 올려 두면 93.8%였음.
- 맞는 스킬을 놓치는 것이 엉뚱한 스킬을 읽는 것보다 훨씬 나쁨. 검색은 전부 올려 두는 것보다
  쓸모 있는 스킬을 4~5점 덜 읽음.
- `/스킬이름` 직접 호출에 의존함. `adopt`로 옮긴 스킬은 직접 호출이 안 됨.

**측정하지 않은 경우**

- 스킬 50~200개에서 현재 기본 방식의 효과.
- 스킬 500개 초과. 판정 모델의 전체 스캔이 꺼지고 로컬 순위로 후보를 뽑음.
- 실제 Claude Code, Codex 세션. 측정의 에이전트는 모델로 흉내 낸 것. 설치 후
  `uv run skill-rag usage`로 추천된 스킬 중 실제로 읽힌 비율을 볼 수 있음.

## 기능

- **하이브리드 로컬 검색.** `intfloat/multilingual-e5-base` 임베딩과 BM25를 합침. 로컬에서
  실행되며 한국어 요청이 영어 설명과도 매칭됨.
- **판정 모델 (선택).** `jev`, `openai`, 또는 직접 만든 판정 모델이 전체 스킬을 훑어 후보를
  추리고, 적합 확률 0.5 이상인 후보를 최대 8개 돌려줌. 고르는 것은 에이전트.
- **메타데이터 먼저, 본문은 나중.** 검색은 이름과 짧은 설명만 돌려주고, 본문은 에이전트가
  `get_skill`로 고른 것만 읽음.
- **이름으로 지정한 스킬은 바로 반환.** 요청에 `/이름`, `이름 스킬`처럼 스킬을 지정하면 판정 없이
  그 스킬을 돌려줌.
- **한 번 읽은 스킬은 다시 추천하지 않음.** 같은 세션 안에서 적용됨.
- **스킬 수집과 이동.** `collect`는 하네스의 스킬을 링크로 모으고, `adopt`는 스킬을 저장소로
  옮겨 하네스 목록에서 뺌. `restore`로 되돌림.
- **사용 기록.** 무엇이 추천됐고 무엇이 실제로 읽혔는지 로컬 파일에 남김.
- **자동 인덱싱.** `~/.skills/`에 스킬을 추가하면 30초 안에 검색됨.
- **실패 시 로컬로 동작.** 판정 모델 호출이 실패하면 로컬 검색 결과를 그대로 돌려줌.

## 효과

스킬 350개에서, 에이전트 역할 모델이 실제로 읽기로 한 스킬을 센 결과. 설정을 고른 뒤 처음 보는
테스트셋으로 1회 측정 (맞는 스킬 있는 요청 191, 없는 요청 96):

| | 쓸모 있는 스킬을 읽음 | 맞는 스킬이 없는데 엉뚱한 스킬을 읽음 | 컨텍스트에 올라가는 스킬 메타데이터 |
| --- | ---: | ---: | --- |
| **검색 + `jev` (판정 모델을 켰을 때의 기본)** | 91.1% | 9.4% | 검색당 약 650자 (약 160토큰) |
| 검색 + `jev`, 후보 1개만 (`STYLE=single`) | 74.9% | 0.0% | 검색당 약 90자 |
| 검색 없이 350개 설명을 전부 컨텍스트에 | 94.8% | 54.2% | 항상 약 33,750토큰 |

- `jev`를 켠 검색은 전부 올려 두는 것보다 쓸모 있는 스킬을 3.7점 덜 읽고, 엉뚱한 스킬은
  6분의 1만 읽으며, 컨텍스트는 약 200분의 1을 씀.
- **판정 모델 없이(기본 설치)는 이 수치가 나오지 않음.** 다른 테스트셋에서 판정 모델 없는 검색은
  69.6% / 14.4%였고, 같은 셋에서 전부 올려 두면 93.8% / 34.0%였음.
- 비용: 검색당 `jev` 입력 약 21,000토큰(약 $0.0009)과 약 0.55초. 매 검색마다 질의와 **전체 스킬의
  이름·설명 앞 120자**가 TypeSafe로 전송됨 (본문은 전송 안 함).
- 한계: 에이전트는 빈 컨텍스트의 단발 모델 호출로 흉내 낸 것이며 실제 하네스와 다를 수 있음.
  요청은 모델이 쓴 것. 같은 방식이 개발셋에서는 96.2%였으므로 절대값은 ±5점 정도로 볼 것.
  스킬 350개, `jev` 한 가지 조건만 측정함 (스킬 모음은 아래의 두 가지).
- 자세한 내용: `docs/benchmarks/2026-11-25-candidates-results.md`,
  `docs/benchmarks/2026-11-25-native-baseline-results.md`.

**다른 스킬 모음에서 다시 측정.** 위 설정은 모두 한 스킬 모음 위에서 골랐기 때문에, 저장소가 하나도
겹치지 않는 새 스킬 350개(107개 저장소)로 설정을 바꾸지 않고 1회 더 측정함 (맞는 스킬 있는 요청 196,
없는 요청 96):

| | 쓸모 있는 스킬을 읽음 | 맞는 스킬이 없는데 엉뚱한 스킬을 읽음 |
| --- | ---: | ---: |
| **검색 + `jev`** | 88.8% (첫 모음 91.1%) | 10.4% (첫 모음 9.4%) |
| 검색 + `jev`, 후보 1개만 | 71.4% (74.9%) | 4.2% (0.0%) |
| 검색 없이 350개 설명을 전부 컨텍스트에 | 93.9% (94.8%) | 43.8% (54.2%) |

- 미리 정한 기준(쓸모 있는 스킬 86.1% 이상, 엉뚱한 스킬 13% 이하이면서 전부 올려 둘 때의 절반 미만)을
  모두 만족함. 전부 올려 두는 것과의 차이는 쓸모 있는 스킬 5.1점, 엉뚱한 스킬은 약 4분의 1.
- 엉뚱한 스킬 10.4%는 설정을 고를 때 쓴 한도 10%를 요청 1건 차이로 넘음. 두 모음 모두 한도 근처임.
- 요청을 쓴 모델, 에이전트 역할 모델, 판정 모델은 첫 측정과 같음. 자세한 내용:
  `docs/benchmarks/2026-11-25-second-corpus-results.md`.

## 사용 방법

필요한 것: Python 3.13 이상, [uv](https://docs.astral.sh/uv/).

```bash
git clone https://github.com/gkrtjd99/skills_rag_mcp.git
cd skills_rag_mcp
make install
```

위 표의 수치를 얻으려면 판정 모델을 켬. MCP 서버 프로세스가 아래 환경 변수를 볼 수 있어야 함.

```bash
uv sync --extra rerank
export TYPESAFE_API_KEY=...
export SKILL_RAG_RERANK=jev
```

터미널에서 실행한 Claude Code나 Codex는 그 셸의 환경 변수를 물려받음. 앱으로 실행하는 경우처럼
셸 환경이 전달되지 않으면 MCP 서버 등록에 환경 변수를 직접 넣어야 함 (API 키가 설정 파일에 남는
점에 주의).

설정이 맞는지는 `uv run skill-rag status`의 마지막 `note` 줄로 확인. 판정 모델이 꺼져 있거나,
스킬이 너무 적거나, 설치된 안내 스킬이 예전 버전이면 여기에 표시됨. 같은 내용이 `make install`
끝에도 나옴.

하네스를 재시작하면 그다음부터는 따로 할 일이 없음. 에이전트가 새 작업을 시작할 때
`search_skills`를 부르고, 맞는 스킬이 있으면 `get_skill`로 읽음. 특정 스킬을 쓰게 하려면
요청에 `/스킬이름`이나 `스킬이름 스킬`이라고 적으면 됨.

스킬을 하네스 목록에서 빼서 컨텍스트를 실제로 줄이려면 `adopt`를 실행
([스킬을 저장소에만 두기](#스킬을-저장소에만-두기-adopt) 참고). `collect`만으로는 하네스가 여전히
모든 설명을 올림.

```bash
uv run skill-rag adopt --dry-run
uv run skill-rag adopt
```

### 업그레이드

```bash
git pull
make install
uv sync --extra rerank
uv run skill-rag install --refresh-bootstrap
```

- `make install`은 `uv sync`를 다시 실행해 판정 모델용 추가 패키지를 지우므로, `jev`를 쓰면
  `uv sync --extra rerank`를 다시 실행해야 함.
- `--refresh-bootstrap`은 설치된 안내 스킬(`~/.skills/using-skill-rag`)을 새 버전으로 덮어씀.
  0.4.0에서 검색 응답에 `candidates`, `uncertain` 상태가 추가됐고, 예전 안내 스킬은 이를 다루는 법을
  모름. 그 스킬을 직접 고쳐 썼다면 덮어쓰기 전에 백업할 것.
- 끝나면 하네스를 재시작.

## 동작 방식

```
사용자 메시지
   │
   ▼
에이전트 → search_skills(query)
              │  1. 로컬 하이브리드 검색 (임베딩 + BM25)
              │  2. 판정 모델이 후보별 적합 확률 계산 (켠 경우)
              ▼
           후보 메타데이터 (name, description, score)
              │
              ▼ 에이전트가 맞다고 본 것만
           get_skill(name) ─→ SKILL.md 본문
```

- 임베딩: `intfloat/multilingual-e5-base` 로컬 모델의 `query:`/`passage:` 프롬프트 사용
  (외부 API 호출 없음).
- MCP 프로세스가 LanceDB 메타데이터와 BM25 구조를 재사용하고, 한국어 의도어 보강을
  사용함. 약 50개 스킬 기준 warm 검색은 1초 미만.
- 검색은 메타데이터만 반환하고 hit description을 기본 280자(판정 모델을 거치면 120자)로
  제한함. 전체 본문은 `get_skill`을 호출할 때만 가져옴.
- 벡터 DB: LanceDB
- 인덱스: `search_skills` 호출 시 TTL 30s 캐시로 자동 sync

## 설치 상세

```bash
git clone https://github.com/gkrtjd99/skills_rag_mcp.git
cd skills_rag_mcp
make install
```

`make install`은 idempotent하며 다음 순서로 동작:

1. `uv sync`
2. 부트스트랩 메타-스킬 `~/.skills/using-skill-rag/` 설치 후
   `~/.claude/skills/`, `~/.codex/skills/`에 심볼릭 링크
3. `skill-rag collect` — 발견된 하네스 스킬을 `~/.skills/`에 심볼릭으로 모음
4. `skill-rag sync` — 첫 실행 시 임베딩 모델 다운로드 후 인덱스 빌드. 로컬 설명 번역은
   선택 기능이며 기본으로 꺼져 있음.
5. MCP 서버 등록 (Claude Code는 `claude mcp add`; Codex는
   `~/.codex/config.toml`)

이후 하네스를 재시작.

> 이전의 E5 프롬프트가 없던 인덱스를 사용 중이면 다음 sync에서 schema metadata가
> 감지해 자동 재빌드합니다. 명시적으로 `uv run skill-rag reset && uv run skill-rag sync`를
> 실행해도 됩니다. 로컬 한↔영 설명 보강이 필요할 때만 `SKILL_RAG_TRANSLATE=1`을
> 설정하세요. 인덱스 시 번역 모델 비용이 추가됩니다.

### 동작 확인

하네스를 재시작한 뒤 새 세션에서:

- 시작 시 `using-skill-rag` 메타-스킬이 자동 로드되는지 확인
- 아무 메시지에서나 `mcp__skill-rag__search_skills` 도구가 보이는지 확인
- 직접 호출해 보기: `search_skills(query="...", k=5)` → `{status: "ok"|"candidates"|"uncertain"|"no_match", hits, ...}`

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
| `uv run skill-rag adopt [이름...] [--from 폴더] [--dry-run]` | 스킬을 `~/.skills/`로 **이동** (하네스가 더는 로드하지 않음) |
| `uv run skill-rag restore [이름...] [--dry-run]` | adopt한 스킬을 원래 위치로 되돌림 |
| `uv run skill-rag sync` | 인덱스 수동 동기화 |
| `uv run skill-rag usage [--json]` | 스킬이 추천된 횟수와 추천 뒤 실제로 읽힌 횟수 |
| `uv run skill-rag query "<text>"` | 검색 결과 확인 |
| `uv run skill-rag list-skills` | 인덱스된 스킬 목록 |
| `uv run skill-rag eval` | 공개 fixture 평가셋으로 recall@5 측정 |
| `make eval-natural` | 영어·한국어 자연어 fixture를 top-1로 평가 |
| `make eval-no-match` | 관련 스킬이 없는 질의의 no-match 정확도 평가 |
| `make eval-codex` | Codex 기본 시스템 스킬 5개를 고정 gold set으로 평가 |
| `make eval-personal` | 지정한 개인 corpus와 대응 gold set 평가 (`SKILL_RAG_EVAL_CORPUS`, `SKILL_RAG_EVAL_DATASET`) |
| `uv run skill-rag reset` | 인덱스 초기화 |
| `uv run skill-rag mcp` | MCP 서버 실행 |
| `uv run skill-rag install [--refresh-bootstrap]` | 부트스트랩 설치 + collect/인덱싱 + MCP 등록 (`make install` 권장). `--refresh-bootstrap`는 기존 메타-스킬을 템플릿으로 덮어씀. `--no-collect`는 하네스·플러그인 스킬을 링크하지 않음 (adopt한 스킬만 제공할 때) |
| `uv run skill-rag uninstall [--purge] [--dry-run] [-y]` | install 역순; `--purge`는 `~/.skills` 통째 비움 |

### 스킬을 저장소에만 두기 (adopt)

`collect`는 스킬을 원래 자리에 둔 채 링크만 걸기 때문에, 하네스는 여전히 모든 스킬 설명을
매 세션 컨텍스트에 싣는다. `adopt`는 스킬 폴더를 `~/.skills/`로 옮겨서 하네스에는
부트스트랩 스킬만 남기고, 나머지는 `search_skills` / `get_skill`로만 제공한다.

```bash
uv run skill-rag adopt --dry-run                      # 무엇이 옮겨질지 확인
uv run skill-rag adopt                                # ~/.claude/skills, ~/.codex/skills 에서 이동
uv run skill-rag adopt --from ~/work/app/.claude/skills   # 프로젝트에 설치한 스킬을 전역 저장소로
uv run skill-rag restore                              # 전부 원래 위치로
```

- 직접 하위 폴더만 대상이며 심볼릭 링크, 플러그인 캐시, 중첩 폴더는 건드리지 않음.
- 이동 기록이 남으므로 `restore`와 `uninstall`이 원래 위치로 되돌림. 원래 위치가 다시
  차 있으면 덮어쓰지 않고 저장소에 남김 (`--purge`로도 삭제되지 않음).
- 이동 후 하네스를 재시작해야 목록에서 빠짐. 옮긴 스킬은 `/스킬이름` 직접 호출이 안 됨.
- `get_skill`이 스킬 폴더 `path`를 함께 돌려주므로 스킬에 딸린 스크립트·참고 파일도 사용 가능.

### 사용 기록

`search_skills`가 무엇을 추천했고 그 뒤 에이전트가 `get_skill`로 실제로 읽었는지를 로컬 파일에
남김. 기계 밖으로 나가지 않음. 기본 모드(`stats`)는 스킬 이름과 점수만 남기고 질의 문장은 남기지
않음. 실제 질의로 평가셋을 만들려면 `SKILL_RAG_USAGE_LOG=full`. `uv run skill-rag usage`로 스킬별
추천 횟수와 추천 뒤 읽힌 횟수를 볼 수 있음. 같은 세션(MCP 서버 프로세스 하나)에서 이미 읽은 스킬은
다시 추천하지 않음.

## 환경 변수

| 변수 | 기본 | 설명 |
| --- | --- | --- |
| `SKILL_RAG_CORPUS_PATH` | `~/.skills` | corpus 경로 |
| `SKILL_RAG_INDEX_PATH` | `./var/index.lance` | LanceDB 경로 |
| `SKILL_RAG_MODEL` | `intfloat/multilingual-e5-base` | 임베딩 모델 |
| `SKILL_RAG_LOCAL_FILES_ONLY` | `1` | 로컬 캐시에서만 임베딩·번역 모델 로드 |
| `SKILL_RAG_MAX_SEQ_LENGTH` | `128` | 임베딩 입력 토큰 상한 (질의와 스킬 설명 모두) |
| `SKILL_RAG_DENSE_BODY_CHARS` | `300` | dense 임베딩에 추가할 본문 앞부분 문자 수 (`0`이면 name/description만 사용) |
| `SKILL_RAG_SCORE_THRESHOLD` | `0.78` | 양성·부정 fixture로 보정한 dense 매칭 임계값 |
| `SKILL_RAG_DENSE_ONLY_THRESHOLD` | `0.86` | 의미 있는 lexical 근거가 없을 때 dense 단독 매칭에 필요한 높은 confidence |
| `SKILL_RAG_DENSE_ONLY_MARGIN_THRESHOLD` | `0.05` | 작은 corpus에서 강한 dense 매칭으로 인정할 top-2 cosine 차이 |
| `SKILL_RAG_BM25_THRESHOLD` | `0.30` | BM25 normalized score 임계값 |
| `SKILL_RAG_BM25_MIN_QUERY_COVERAGE` | `0.50` | lexical rescue에 필요한 의미어 커버리지 |
| `SKILL_RAG_RRF_K` | `60` | dense/BM25 reciprocal-rank-fusion 상수 |
| `SKILL_RAG_DENSE_CANDIDATE_MULTIPLIER` | `4` | 요청 k 대비 dense 후보 배수 |
| `SKILL_RAG_MIN_DENSE_CANDIDATES` | `20` | dense 후보 최소 개수 |
| `SKILL_RAG_MAX_HIT_DESCRIPTION_CHARS` | `280` | MCP 메타데이터 description 상한 (`0`이면 해제) |
| `SKILL_RAG_TRANSLATE` | `0` | 인덱스 시 로컬 description 번역 (`1`이면 켬) |
| `SKILL_RAG_SYNC_TTL` | `30` | sync 캐시 TTL (초) |
| `SKILL_RAG_USAGE_LOG` | `stats` | 로컬 사용 기록: `stats`(스킬 이름·점수만), `full`(질의 문장 포함), `off` |
| `SKILL_RAG_USAGE_PATH` | `./var/usage.jsonl` | 사용 기록 파일 경로 |
| `SKILL_RAG_EXCLUDE_LOADED` | `1` | 이번 세션에서 이미 읽은 스킬을 추천에서 제외 (`0`이면 끔) |
| `SKILL_RAG_EXPLICIT` | `1` | 요청이 스킬을 이름으로 지정하면(`/이름`, `이름 스킬`) 판정 없이 그 스킬을 반환 (`0`이면 끔) |
| `SKILL_RAG_RERANK` | (꺼짐) | 2단계 적합성 판정 모델: `jev`, `openai`, 또는 직접 만든 `패키지.모듈:팩토리` (클라우드 호출, 아래 참고) |
| `SKILL_RAG_RERANK_CANDIDATES` | `16` | 판정 모델에게 보여줄 후보 스킬 수 |
| `SKILL_RAG_RERANK_STYLE` | `candidates` | `candidates`: 적합 확률이 하한 이상인 후보 여러 개를 돌려주고 에이전트가 고름. `single`: 확실한 1개만 (아래 임계값 사용) |
| `SKILL_RAG_RERANK_FLOOR` | `0.5` | `candidates` 방식에서 후보로 보여 줄 최소 적합 확률 |
| `SKILL_RAG_RERANK_SHOWN` | `8` | `candidates` 방식에서 보여 줄 최대 후보 수 |
| `SKILL_RAG_RERANK_SCAN_MAX` | `500` | 판정 모델이 전체 스킬을 훑어 후보를 뽑을 최대 코퍼스 크기 (`0`이면 끔, 로컬 순위로 후보 선정) |
| `SKILL_RAG_RERANK_THRESHOLD` | `0.9` | `single` 방식: 스킬을 반환하는 최소 적합 확률 (`jev` 기준으로 고른 값) |
| `SKILL_RAG_RERANK_MAX_HITS` | `1` | `single` 방식: 검색당 반환할 최대 스킬 수 (`0`이면 `k`까지) |
| `SKILL_RAG_RERANK_MODEL` | (제공사 기본) | 판정 모델 ID 고정 (예: `jev-1.14.0`, `gpt-6-luna`) |
| `SKILL_RAG_RERANK_TIMEOUT` | `5` | 판정 요청 타임아웃 (초) |
| `SKILL_RAG_RERANK_COOLDOWN` | `60` | 판정 호출 실패 후 로컬 판정만 쓰는 시간 (초) |
| `SKILL_RAG_RERANK_DESCRIPTION_CHARS` | `120` | 판정을 거친 hit의 description 상한 (`0`이면 해제) |
| `SKILL_RAG_RERANK_UNCERTAIN_FROM` | `0.7` | `single` 방식: 임계값에 못 미친 스킬 중 이 확률 이상인 최상위 1개를 `uncertain` 후보로 반환 (임계값 이상으로 두면 끔) |
| `SKILL_RAG_LOCAL_CANDIDATES` | `0` | 판정 모델 없이 로컬 순위 상위 N개를 `uncertain` 후보로 반환 (`0`이면 기본 게이트) |

### 선택 기능: 판정 모델 재순위 (기본 꺼짐)

기본 임계값은 공개 fixture에 맞춰져 있어 다른 코퍼스에서는 정확도가 떨어짐.
켜면 판정 모델이 전체 스킬을 훑어 후보 16개를 뽑고, 후보마다 "이 질의에 맞는 스킬인가"의 확률을
돌려줌. 기본 방식(`candidates`)은 확률 0.5 이상인 후보를 점수순으로 최대 8개, 120자 설명과 함께
`status: "candidates"`로 돌려주고 **고르는 것은 에이전트**가 함. 후보가 눈앞에 있으면 에이전트가 판정
모델보다 잘 고르기 때문. 결과는 [효과](#효과)의 표 참고.

아래는 이전 기본값이었던 `single` 방식(확률 0.9 이상인 스킬 하나만 반환)의 측정 기록.
엉뚱한 스킬을 거의 주지 않는 대신 쓸모 있는 스킬을 훨씬 덜 줌. `SKILL_RAG_RERANK_STYLE=single`로 사용.

**벤치마크 (규칙과 설정을 먼저 커밋한 뒤, 처음 보는 테스트셋으로 1회 측정).** skills.sh에서 받은
스킬 350개 코퍼스, 다른 모델이 스킬 본문만 보고 쓴 질의 293개 (맞는 스킬 있음 196, 없음 97, 한·영).
"엉뚱한 스킬"은 첫 번째로 반환한 스킬이 실제로 맞지 않는 경우 (별도 모델이 판정).

| | 맞는 스킬이 없는데 엉뚱한 스킬 반환 | 맞는 스킬이 있는데 엉뚱한 스킬 반환 | 쓸모 있는 스킬 반환 | 반환 개수 | 응답 크기 | 지연 p50 |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| 기본 게이트 | 88.7% | 46.4% | 50.5% | 4.83 | 1,559자 | 45 ms |
| `jev` (기본값) | 9.3% | 3.6% | 67.9% | 0.55 | 171자 | 207 ms |
| `jev`, 임계값 0.5·`k`개까지 | 34.0% | 13.3% | 79.6% | 1.95 | 426자 | 207 ms |
| `openai` (기본값) | 26.8% | 10.2% | 79.6% | 0.77 | 196자 | 466 ms |

- `jev` 기본값은 엉뚱한 스킬을 9% / 4%로 줄이는 대신, 쓸모 있는 스킬을 주는 비율이 80% → 68%로 내려감.
  더 많이 찾는 쪽이 필요하면 `SKILL_RAG_RERANK_THRESHOLD=0.5 SKILL_RAG_RERANK_MAX_HITS=0`.
- 임계값 0.9는 `jev`로 고른 값이라 `openai`에는 맞지 않음 (확률이 0과 1에 더 몰림). 개발셋에서는
  임계값을 0.999까지 올려도 `openai`는 맞는 스킬이 없는 질의의 22%에 엉뚱한 스킬을 반환함. 엉뚱한
  스킬을 피하는 것이 중요하면 `jev`를 쓸 것.
- 한국어 질의는 영어보다 약함 (`jev` 쓸모 있는 스킬 반환 58% 대 78%).
- 판정 모델이 전체 스킬을 훑는 방식(`SKILL_RAG_RERANK_SCAN_MAX`)은 이제 기본으로 켜져 있음
  (스킬 500개까지). `single` 방식에서는 이득이 작았지만(77.2% → 82.1%,
  `docs/benchmarks/2026-11-25-scan-results.md`), `candidates` 방식의 효과는 대부분 여기서 나옴.
  비용: 스킬 350개 기준 검색당 약 17,800토큰과 약 0.37초, 그리고 매 검색마다 전체 스킬의 이름과
  설명 앞 120자가 제공사로 전송됨. `0`으로 끄면 후보 16개의 이름·설명만 전송됨.
- 검색당 입력 토큰: `jev` 약 3,400, `openai` 약 5,100.

**(`single` 방식) 애매한 후보는 에이전트가 고른다.** 0.9에 못 미쳐도 0.7 이상인 스킬이 있으면 가장 높은 하나를
`status: "uncertain"`으로 돌려줌 (점수 없이 `"confidence": "low"` 표시, 설명 120자). 읽을지는 호출한
에이전트가 정함. 에이전트 역할을 하는 모델을 세워 "실제로 읽기로 한 스킬"을 센 결과 (새 테스트셋,
맞는 스킬 있음 194, 없음 97):

| | 쓸모 있는 스킬을 읽음 | 맞는 스킬이 없는데 엉뚱한 스킬을 읽음 | 맞는 스킬이 있는데 엉뚱한 스킬을 읽음 |
| --- | ---: | ---: | ---: |
| `jev`, 0.9 이상만 | 60.3% | 4.1% | 3.1% |
| `jev` + 애매한 후보 (`single` 방식 기본) | 67.0% | 8.2% | 2.1% |
| 판정 모델 없음, 게이트 결과를 에이전트가 판단 | 69.6% | 14.4% | 4.1% |
| 판정 모델 없음, `SKILL_RAG_LOCAL_CANDIDATES=3` | 62.9% | 7.2% | 4.6% |

- 쓸모 있는 스킬을 읽는 비율이 6.7점 오르는 대신, 맞는 스킬이 없는 요청에서 엉뚱한 스킬을 읽는 경우가
  97건 중 4건에서 8건으로 늘어남. 끄려면 `SKILL_RAG_RERANK_UNCERTAIN_FROM=0.9`.
- 판정 모델이 없어도 에이전트가 게이트 결과를 직접 걸러 내면 쓸모 있는 스킬을 읽는 비율은 비슷함.
  판정 모델이 주는 것은 엉뚱한 스킬을 덜 읽는 것(8% 대 14%)과 검색당 메타데이터 양(약 110자 대 1,210자).
- 한계: 에이전트는 빈 컨텍스트의 단발 모델 호출로 흉내 낸 것이고, 실제 하네스의 모델이 아님.
  `jev`로만 측정함. 자세한 내용: `docs/benchmarks/2026-11-25-agent2-results.md`.

전체 표·선택 과정·한계: `docs/benchmarks/2026-11-24-precision-results.md`. 코퍼스 크기별(50~350)
결과는 `docs/benchmarks/2026-11-24-scale-results.md` (임계값 0.5 시절 측정). 직접 쓴 질의로 잰 초기 수치
(`2026-11-24-heldout-jev-rerank.md`, `jev` recall@1 0.979)는 쉬운 질의에서의 상한으로만 볼 것.

```bash
# TypeSafe Jev
uv sync --extra rerank
export TYPESAFE_API_KEY=...
export SKILL_RAG_RERANK=jev

# 또는 OpenAI Decisions API (추가 패키지 없음)
export OPENAI_API_KEY=...
export SKILL_RAG_RERANK=openai
```

- 켜면 검색마다 **질의 문장과 후보 스킬의 이름·설명**이 선택한 제공사 API로 전송됨.
  스킬 본문과 경로는 전송되지 않음. 끄면 아무것도 외부로 나가지 않음.
- 입력 토큰이 과금됨.
- SDK 미설치, 키 없음, 크레딧 소진, 타임아웃 등 어떤 실패든 로컬 판정 결과를 그대로 반환함.
- 다른 모델을 붙이려면 `skill_rag.judges.Judge`(메서드 `fits`, `unavailable_reason`)를
  구현하고 `SKILL_RAG_RERANK=내패키지.모듈:팩토리`로 지정.
- `uv run skill-rag status`의 `rerank` 줄에서 현재 상태 확인.

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

## 라이선스

MIT. `LICENSE` 참고.
