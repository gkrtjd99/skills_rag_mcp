# skill_rag

[한국어](README.md) | **English**

A local search server (MCP) for agent skills. When you have hundreds of
skills, the agent looks up the ones that fit each request instead of carrying
every description in its context. Works with Claude Code, Codex, and other
MCP clients.

## Purpose

Claude Code and Codex put the name and description of every installed skill
into the context of every session. With many skills this causes two problems.

- **Context cost.** The descriptions of 350 skills take about 33,750 tokens,
  all the time.
- **Wrong skills get loaded.** The longer the list, the more often the agent
  picks an unrelated skill. In our measurement it loaded a wrong skill on
  54.2% of requests that no skill matched.

skill-rag loads one small guide skill at session start, keeps the rest under
`~/.skills/`, and lets the agent find them per task with `search_skills` and
fetch only the bodies it needs with `get_skill`.

## When to use it

Everything below comes from this repository's measurements (see
[Effect](#effect)).

**Use it when**

- You have hundreds of skills. A description costs about 100 tokens, so 350
  skills occupy about 33,750 tokens in every session.
- You can use a judge model (`jev`): you have a TypeSafe API key, the request
  text and skill names and descriptions may leave the machine, and about
  $0.0009 and 0.55 s per search are acceptable.
- The agent often loads unrelated skills and goes off track.
- Requests are in Korean and skill descriptions are in English (Korean
  requests 89.7%, English 92.6%).
- You want Claude Code and Codex to share one skill store.

**Do not use it when**

- You have a few dozen skills. The whole list is about 2,000 tokens, so there
  is little to save.
- You cannot use a judge model (offline, or nothing may leave the machine).
  Search without a judge loaded a useful skill on 69.6% of requests; loading
  every description scored 93.8% on the same requests.
- Missing the right skill is much worse than loading a wrong one. Search
  loads a useful skill 4 to 5 points less often than loading every
  description.
- You rely on calling skills directly with `/skill-name`. Skills moved with
  `adopt` cannot be called that way.

**Not measured**

- The current default at 50 to 200 skills.
- More than 500 skills. The judge's whole-corpus scan turns off and
  candidates come from the local ranking.
- Real Claude Code or Codex sessions. The agent in the measurements is a
  model standing in for one. After installing, `uv run skill-rag usage` shows
  how many recommended skills were actually loaded.

## Features

- **Local hybrid search.** `intfloat/multilingual-e5-base` embeddings combined
  with BM25, running locally. Korean requests match English descriptions.
- **Judge model (optional).** `jev`, `openai`, or your own judge scans every
  skill, shortlists candidates, and returns up to 8 with a fit probability of
  0.5 or more. The agent chooses.
- **Metadata first, bodies later.** Search returns names and short
  descriptions; the agent reads a body only for the skill it picks with
  `get_skill`.
- **Skills named in the request are returned directly.** `/name` or
  `name skill` in the request returns that skill without judging.
- **A skill already loaded is not recommended again** within the same session.
- **Collecting and moving skills.** `collect` links harness skills into the
  store; `adopt` moves skills into the store and out of the harness list;
  `restore` puts them back.
- **Usage log.** What was recommended and what was actually loaded, kept in a
  local file.
- **Automatic indexing.** A skill added under `~/.skills/` is searchable
  within 30 seconds.
- **Falls back to local search.** If the judge call fails, the local result
  is returned.

## Effect

At 350 skills, with a model acting as the agent and counting what it chose to
load. The configuration was chosen first and then run once on a test set it
had not seen (191 requests with a matching skill, 96 without):

| | Useful skill loaded | Wrong skill loaded when none matches | Skill metadata in context |
| --- | ---: | ---: | --- |
| **Search + `jev` (the default once a judge is on)** | 91.1% | 9.4% | about 650 characters per search (about 160 tokens) |
| Search + `jev`, one candidate only (`STYLE=single`) | 74.9% | 0.0% | about 90 characters per search |
| No search, all 350 descriptions in context | 94.8% | 54.2% | about 33,750 tokens, always |

- Search with `jev` loads a useful skill 3.7 points less often than loading
  every description, loads a wrong one a sixth as often, and uses about 1/200
  of the context.
- **Without a judge (a plain install) these numbers do not hold.** On another
  test set search without a judge scored 69.6% / 14.4%, and loading every
  description scored 93.8% / 34.0% on the same requests.
- Cost: about 21,000 `jev` input tokens (about $0.0009) and 0.55 s per
  search. Every search sends the query and **every skill's name and first 120
  characters of description** to TypeSafe (never a body).
- Limits: the agent is one model call with an empty context and may differ
  from a real harness; requests are model-written. The same configuration
  scored 96.2% on the dev set, so read the absolute values as about ±5
  points. Only 350 skills and `jev` were measured (on the two pools below).
- Details: `docs/benchmarks/2026-11-25-candidates-results.md`,
  `docs/benchmarks/2026-11-25-native-baseline-results.md`.

**Measured again on a different set of skills.** Every setting above was
chosen on one pool of skills, so the unchanged configuration was run once
more on 350 new skills from 107 repositories, none of which had been used
before (196 requests with a matching skill, 96 without):

| | Useful skill loaded | Wrong skill loaded when none matches |
| --- | ---: | ---: |
| **Search + `jev`** | 88.8% (first pool 91.1%) | 10.4% (first pool 9.4%) |
| Search + `jev`, one candidate only | 71.4% (74.9%) | 4.2% (0.0%) |
| No search, all 350 descriptions in context | 93.9% (94.8%) | 43.8% (54.2%) |

- All conditions fixed in advance are met (useful at least 86.1%; wrong
  loads at most 13% and below half of what loading every description gives).
  Against loading every description: 5.1 points fewer useful loads, about a
  quarter of the wrong loads.
- The 10.4% is one request above the 10% limit used when the configuration
  was chosen. Both pools sit at that limit.
- The request writer, the agent models, and the adjudicator are the same as
  in the first measurement. Details:
  `docs/benchmarks/2026-11-25-second-corpus-results.md`.

## Usage

Requirements: Python 3.13 or later and [uv](https://docs.astral.sh/uv/).

```bash
git clone https://github.com/gkrtjd99/skills_rag_mcp.git
cd skills_rag_mcp
make install
```

To get the numbers in the table, turn the judge on. The MCP server process
must see these environment variables.

```bash
uv sync --extra rerank
export TYPESAFE_API_KEY=...
export SKILL_RAG_RERANK=jev
```

Claude Code or Codex started from a terminal inherits that shell's
environment. If the shell environment does not reach it, as when it is
started as an app, put the variables into the MCP server registration (note
that the API key then sits in a configuration file).

Check the setup with the `note` lines at the end of `uv run skill-rag
status`. They appear when no judge is active, when there are too few skills
for search to pay, or when the installed guide skill is from an older
version. `make install` prints the same notes.

Restart the harness; nothing else is needed after that. The agent calls
`search_skills` when a new task starts and reads a fitting skill with
`get_skill`. To make it use a particular skill, write `/skill-name` or
`skill-name skill` in the request.

To take skills out of the harness list, which is what actually shrinks the
context, run `adopt` (see
[Keeping skills only in the store](#keeping-skills-only-in-the-store-adopt)).
With `collect` alone the harness still loads every description.

```bash
uv run skill-rag adopt --dry-run
uv run skill-rag adopt
```

### Upgrading

```bash
git pull
make install
uv sync --extra rerank
uv run skill-rag install --refresh-bootstrap
```

- `make install` runs `uv sync` again, which removes the judge's extra
  package, so run `uv sync --extra rerank` again if you use `jev`.
- `--refresh-bootstrap` overwrites the installed guide skill
  (`~/.skills/using-skill-rag`) with the new version. 0.4.0 added the
  `candidates` and `uncertain` search statuses, and an older guide skill does
  not know how to handle them. Back the skill up first if you edited it.
- Restart the harness afterwards.

## How it works

```
user message
   │
   ▼
agent → search_skills(query)
           │  1. local hybrid search (embeddings + BM25)
           │  2. the judge scores each candidate's fit (if enabled)
           ▼
        candidate metadata (name, description, score)
           │
           ▼ only what the agent judges to fit
        get_skill(name) ─→ SKILL.md body
```

- Embeddings: `intfloat/multilingual-e5-base` running locally with the model's
  `query:`/`passage:` prompts (no external API calls). Strong cross-lingual
  retrieval — Korean queries match English skill descriptions.
- Retrieval keeps the LanceDB metadata and BM25 structure hot between MCP
  calls, and uses a small local Korean intent bridge. Warm searches stay below
  the one-second target on a roughly 50-skill corpus.
- Search returns metadata only, with hit descriptions capped at 280 characters (120 after a judge);
  `get_skill` is the explicit path for the full body.
- Vector DB: LanceDB
- Index: auto-synced with a 30s TTL cache on each `search_skills` call

## Install details

```bash
git clone https://github.com/gkrtjd99/skills_rag_mcp.git
cd skills_rag_mcp
make install
```

`make install` is idempotent and does, in order:

1. `uv sync`
2. Installs the bootstrap meta-skill at `~/.skills/using-skill-rag/` and
   symlinks it into `~/.claude/skills/` and `~/.codex/skills/`
3. `skill-rag collect` — symlinks discovered harness skills into `~/.skills/`
4. `skill-rag sync` — downloads the embedding model on first run and builds the index. Local description translation is optional and disabled by default.
5. Registers the MCP server (Claude Code via `claude mcp add`; Codex via
   `~/.codex/config.toml`)

Restart the harness afterward.

> Upgrading from the previous unprompted E5 index? Schema metadata detects the
> stale embedding profile and rebuilds it on the next sync. You can also run
> `uv run skill-rag reset && uv run skill-rag sync` explicitly. Set
> `SKILL_RAG_TRANSLATE=1` only when local ko↔en description augmentation is
> needed; it adds an index-time translation model and cost.

### Sanity check

After restarting the harness, in a fresh session:

- Confirm the `using-skill-rag` meta-skill auto-loads at start
- Confirm the `mcp__skill-rag__search_skills` tool is visible in any message
- Try it directly: `search_skills(query="...", k=5)` → `{status: "ok"|"candidates"|"uncertain"|"no_match", hits, ...}`

You can also verify the same search from the CLI:

```bash
uv run skill-rag query "deploy to vercel"
```

### Other MCP-compatible clients (Cursor, Windsurf, etc.)

`make install` auto-registers Claude Code and Codex only. For other clients,
register the MCP server manually using:

```
uv --directory <repo> run skill-rag mcp
```

## Uninstall

```bash
make uninstall   # removes skill-rag's footprint; keeps hand-placed skills
make purge       # also empties ~/.skills entirely
```

`uninstall` reverses install: unregisters the MCP server, removes the harness
bootstrap symlinks and the index, and removes collected symlinks + the bootstrap
skill. Hand-placed real skill directories under `~/.skills` are preserved unless
you use `purge`.

## Adding a skill

Write a file at `~/.skills/<name>/SKILL.md`:

```markdown
---
name: my-skill
description: One-line description. Search accuracy depends on this.
---

# Body
Detailed usage of the skill.
```

It is auto-indexed within 30s on the next `search_skills` call.

## CLI

| Command | Description |
| --- | --- |
| `uv run skill-rag status` | Show corpus path, model, index size, threshold |
| `uv run skill-rag collect [--dry-run]` | Symlink harness skills into `~/.skills/` |
| `uv run skill-rag adopt [names...] [--from DIR] [--dry-run]` | **Move** skills into `~/.skills/` (the harness stops loading them) |
| `uv run skill-rag restore [names...] [--dry-run]` | Move adopted skills back to where they were |
| `uv run skill-rag usage [--json]` | How often skills were suggested and then actually loaded |
| `uv run skill-rag sync` | Manually sync the index |
| `uv run skill-rag query "<text>"` | Inspect search results |
| `uv run skill-rag list-skills` | List indexed skills |
| `uv run skill-rag eval` | Measure recall@5 against the public fixture eval |
| `make eval-natural` | Evaluate the bilingual natural-language fixture at top-1 |
| `make eval-no-match` | Evaluate no-match accuracy on unrelated queries |
| `make eval-codex` | Evaluate the five Codex system skills with the fixed gold set |
| `make eval-personal` | Evaluate a personal corpus with its matching gold set (`SKILL_RAG_EVAL_CORPUS`, `SKILL_RAG_EVAL_DATASET`) |
| `uv run skill-rag reset` | Reset the index |
| `uv run skill-rag mcp` | Run the MCP server |
| `uv run skill-rag install [--refresh-bootstrap]` | Install bootstrap + collect/index + register MCP (use `make install`). `--refresh-bootstrap` overwrites the existing meta-skill from the template. `--no-collect` skips linking harness and plugin skills (for serving only adopted skills) |
| `uv run skill-rag uninstall [--purge] [--dry-run] [-y]` | Reverse install; `--purge` empties `~/.skills` |

### Keeping skills only in the store (adopt)

`collect` leaves a skill where it is and links to it, so the harness still puts
every skill description into each session's context. `adopt` moves the skill
directory into `~/.skills/`, leaving the harness with only the bootstrap skill
and serving the rest through `search_skills` / `get_skill`.

```bash
uv run skill-rag adopt --dry-run                      # see what would move
uv run skill-rag adopt                                # from ~/.claude/skills and ~/.codex/skills
uv run skill-rag adopt --from ~/work/app/.claude/skills   # project-installed skills into the global store
uv run skill-rag restore                              # everything back where it was
```

- Only direct child directories are moved; symlinks, plugin caches, and nested
  folders are left alone.
- Moves are recorded, so `restore` and `uninstall` put skills back. If the
  original location is occupied again nothing is overwritten and the skill
  stays in the store (`--purge` does not delete it either).
- Restart the harness afterwards so the skills leave its listing. Adopted
  skills can no longer be invoked as `/skill-name`.
- `get_skill` returns the skill's `path`, so bundled scripts and references
  still work.

### Usage log

What `search_skills` suggested, and whether the agent then loaded it with
`get_skill`, is recorded in a local file. Nothing leaves the machine. The
default mode (`stats`) stores skill names and scores, not request text. To
build an evaluation set from real requests, set `SKILL_RAG_USAGE_LOG=full`.
`uv run skill-rag usage` shows, per skill, how often it was suggested and how
often it was loaded afterwards. A skill already loaded in the same session (one
MCP server process) is not suggested again.

## Environment variables

| Variable | Default | Description |
| --- | --- | --- |
| `SKILL_RAG_CORPUS_PATH` | `~/.skills` | Corpus path |
| `SKILL_RAG_INDEX_PATH` | `./var/index.lance` | LanceDB path |
| `SKILL_RAG_MODEL` | `intfloat/multilingual-e5-base` | Embedding model |
| `SKILL_RAG_LOCAL_FILES_ONLY` | `1` | Load embedding and translation models from local cache only |
| `SKILL_RAG_MAX_SEQ_LENGTH` | `128` | Embedding input token cap (queries and skill passages) |
| `SKILL_RAG_DENSE_BODY_CHARS` | `300` | Opening-body characters added to dense passages (`0` uses name/description only; BM25 keeps the full body) |
| `SKILL_RAG_SCORE_THRESHOLD` | `0.78` | Dense match threshold calibrated against positive and negative fixtures |
| `SKILL_RAG_DENSE_ONLY_THRESHOLD` | `0.86` | Higher confidence required when a dense hit has no meaningful lexical evidence |
| `SKILL_RAG_DENSE_ONLY_MARGIN_THRESHOLD` | `0.05` | Top-vs-runner-up cosine gap accepted for a strong small-corpus dense match |
| `SKILL_RAG_BM25_THRESHOLD` | `0.30` | Normalized BM25 threshold |
| `SKILL_RAG_BM25_MIN_QUERY_COVERAGE` | `0.50` | Meaningful query-term coverage required for lexical rescue |
| `SKILL_RAG_RRF_K` | `60` | Dense/BM25 reciprocal-rank-fusion constant |
| `SKILL_RAG_DENSE_CANDIDATE_MULTIPLIER` | `4` | Dense shortlist multiplier relative to requested `k` |
| `SKILL_RAG_MIN_DENSE_CANDIDATES` | `20` | Minimum dense shortlist size |
| `SKILL_RAG_MAX_HIT_DESCRIPTION_CHARS` | `280` | MCP metadata description cap (`0` disables the cap) |
| `SKILL_RAG_TRANSLATE` | `0` | Optional local description translation at index time (`1` enables) |
| `SKILL_RAG_SYNC_TTL` | `30` | Sync cache TTL (seconds) |
| `SKILL_RAG_USAGE_LOG` | `stats` | Local usage log: `stats` (skill names and scores only), `full` (also request text), `off` |
| `SKILL_RAG_USAGE_PATH` | `./var/usage.jsonl` | Usage log file |
| `SKILL_RAG_EXCLUDE_LOADED` | `1` | Leave skills already loaded in this session out of suggestions (`0` disables) |
| `SKILL_RAG_EXPLICIT` | `1` | When the request names a skill outright (`/name`, `name skill`), return it without a judgment (`0` turns it off) |
| `SKILL_RAG_RERANK` | (off) | Second-stage fit judge: `jev`, `openai`, or your own `package.module:factory` (cloud call, see below) |
| `SKILL_RAG_RERANK_CANDIDATES` | `16` | Candidate skills shown to the judge |
| `SKILL_RAG_RERANK_STYLE` | `candidates` | `candidates`: return several candidates at or above the floor and let the agent choose. `single`: only the one sure skill (uses the threshold below) |
| `SKILL_RAG_RERANK_FLOOR` | `0.5` | `candidates` style: lowest fit probability shown |
| `SKILL_RAG_RERANK_SHOWN` | `8` | `candidates` style: most candidates shown |
| `SKILL_RAG_RERANK_SCAN_MAX` | `500` | Largest corpus the judge scans whole to build the shortlist (`0` disables; the local ranking picks the shortlist) |
| `SKILL_RAG_RERANK_THRESHOLD` | `0.9` | `single` style: minimum fit probability for a skill to be returned (chosen with `jev`) |
| `SKILL_RAG_RERANK_MAX_HITS` | `1` | `single` style: most skills returned per search (`0` means up to `k`) |
| `SKILL_RAG_RERANK_MODEL` | (provider default) | Pin the judge model id (for example `jev-1.14.0`, `gpt-6-luna`) |
| `SKILL_RAG_RERANK_TIMEOUT` | `5` | Judge request timeout (seconds) |
| `SKILL_RAG_RERANK_COOLDOWN` | `60` | Seconds to stay on the local gate after a failed judge call |
| `SKILL_RAG_RERANK_DESCRIPTION_CHARS` | `120` | Description cap for judged hits (`0` disables the cap) |
| `SKILL_RAG_RERANK_UNCERTAIN_FROM` | `0.7` | `single` style: below the threshold, return the single best skill at or above this probability as an `uncertain` candidate (a value at or above the threshold turns it off) |
| `SKILL_RAG_LOCAL_CANDIDATES` | `0` | Without a judge, return the top N of the local ranking as `uncertain` candidates (`0` keeps the default gate) |

### Optional: judge rerank (off by default)

The default thresholds are calibrated on the public fixture and lose accuracy
on other corpora. When enabled, the judge scans every skill to pick 16
candidates and returns, per candidate, the probability that it fits the
query. The default style (`candidates`) returns the candidates at or above
0.5, best first, at most 8, with 120-character descriptions, as
`status: "candidates"`, and **the agent chooses**: with the candidates in
view the agent selects better than the judge. Results are in the table under
[Effect](#effect).

What follows records the `single` style, the earlier default (only the one
skill at or above 0.9). It hardly ever returns a wrong skill and returns a
useful one much less often. Use it with `SKILL_RAG_RERANK_STYLE=single`.

**Benchmark (rules and configuration committed first, then one run on a test
set nobody had seen).** A 350-skill corpus from skills.sh and 293 queries
written by another model from skill bodies only (196 with a matching skill, 97
without; English and Korean). "Wrong skill" means the first returned skill
does not actually fit, as judged by a separate model.

| | Wrong skill when none matches | Wrong skill when one matches | Useful skill returned | Skills returned | Response size | Latency p50 |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| Default gate | 88.7% | 46.4% | 50.5% | 4.83 | 1,559 chars | 45 ms |
| `jev` (defaults) | 9.3% | 3.6% | 67.9% | 0.55 | 171 chars | 207 ms |
| `jev`, threshold 0.5, up to `k` | 34.0% | 13.3% | 79.6% | 1.95 | 426 chars | 207 ms |
| `openai` (defaults) | 26.8% | 10.2% | 79.6% | 0.77 | 196 chars | 466 ms |

- The `jev` defaults cut wrong skills to 9% / 4% at the price of returning a
  useful skill for 68% of matching requests instead of 80%. For more recall
  use `SKILL_RAG_RERANK_THRESHOLD=0.5 SKILL_RAG_RERANK_MAX_HITS=0`.
- The 0.9 threshold was chosen with `jev` and does not suit `openai`, whose
  probabilities sit closer to 0 and 1. On dev data `openai` still returns a
  wrong skill for 22% of no-match requests at a threshold of 0.999. Use `jev`
  when avoiding wrong skills matters.
- Korean requests are weaker than English (`jev` useful rate 58% against 78%).
- Letting the judge scan the whole corpus (`SKILL_RAG_RERANK_SCAN_MAX`) is now
  on by default (up to 500 skills). Under the `single` style its gain was
  small (77.2% to 82.1%, `docs/benchmarks/2026-11-25-scan-results.md`); under
  `candidates` it is most of the result. Cost at 350 skills: about 17,800
  input tokens and 0.37 s per search, and every skill's name and first 120
  characters of description are sent to the provider on every search. With
  `0` only the 16 shortlisted names and descriptions are sent.
- Input tokens per search: about 3,400 for `jev`, 5,100 for `openai`.

**(`single` style) The agent decides the uncertain cases.** When no skill reaches 0.9 but one
is at or above 0.7, the best one is returned as `status: "uncertain"` (no
score, `"confidence": "low"`, a 120-character description) and the calling
agent decides whether to load it. Measured with a model acting as the agent,
counting what it chose to load (fresh test set, 194 matching and 97 no-match
requests):

| | Useful skill loaded | Wrong skill loaded when none matches | Wrong skill loaded when one matches |
| --- | ---: | ---: | ---: |
| `jev`, 0.9 and above only | 60.3% | 4.1% | 3.1% |
| `jev` plus the uncertain candidate (`single` style default) | 67.0% | 8.2% | 2.1% |
| No judge, agent reads the gate's result | 69.6% | 14.4% | 4.1% |
| No judge, `SKILL_RAG_LOCAL_CANDIDATES=3` | 62.9% | 7.2% | 4.6% |

- The useful rate rises by 6.7 points; wrong loads on no-match requests go
  from 4 to 8 of 97. Turn it off with `SKILL_RAG_RERANK_UNCERTAIN_FROM=0.9`.
- Without a judge, an agent filtering the gate's result loads a useful skill
  about as often. What the judge buys is fewer wrong loads (8% against 14%)
  and less metadata per search (about 110 characters against 1,210).
- Limits: the agent is one model call with an empty context, not the model in
  a real harness, and only `jev` was measured. Details:
  `docs/benchmarks/2026-11-25-agent2-results.md`.

Full tables, how the configuration was chosen, and limits:
`docs/benchmarks/2026-11-24-precision-results.md`. Results by corpus size (50
to 350, measured at the earlier 0.5 threshold):
`docs/benchmarks/2026-11-24-scale-results.md`. The first numbers, from
author-written queries (`2026-11-24-heldout-jev-rerank.md`, `jev` recall@1
0.979), are an upper bound on an easy set.

```bash
# TypeSafe Jev
uv sync --extra rerank
export TYPESAFE_API_KEY=...
export SKILL_RAG_RERANK=jev

# or the OpenAI Decisions API (no extra package)
export OPENAI_API_KEY=...
export SKILL_RAG_RERANK=openai
```

- When on, every search sends **the query text and the candidate skills'
  names and descriptions** to the chosen provider's API. Skill bodies and
  paths are not sent. When off, nothing leaves the machine.
- Input tokens are billed.
- Any failure (SDK missing, no key, no credits, timeout) returns the local
  gate's result.
- To plug in another model, implement `skill_rag.judges.Judge` (methods
  `fits` and `unavailable_reason`) and set
  `SKILL_RAG_RERANK=your_package.module:factory`.
- Check the `rerank` line of `uv run skill-rag status`.

`skill-rag eval` defaults to repository-owned fixtures under `eval/fixtures/`
so GitHub users get the same benchmark. The Codex system-skill gold set targets
`~/.codex/skills/.system` on the current machine:

```bash
make eval-codex
```

For an arbitrary personal corpus, create a matching gold set using skill names
that actually exist in that corpus and provide both paths:

```bash
SKILL_RAG_EVAL_CORPUS=~/.skills \
SKILL_RAG_EVAL_DATASET=eval/my-corpus-queries.jsonl \
make eval-personal
```

Use `make benchmark-docker` for the model matrix, or
`make benchmark-natural-docker` for the stricter bilingual natural-language
comparison.

## Docs

- `AGENTS.md` — reading order before an agent's first task
- `ARCHITECTURE.md` — module structure
- `docs/product-specs/skill-rag.md` — what and why
- `docs/design-docs/` — design decision log
- `docs/design-docs/implementation-history.md` — completed historical specs/plans
- `docs/superpowers/` — active feature specs/plans, when present

## License

MIT. See `LICENSE`.
