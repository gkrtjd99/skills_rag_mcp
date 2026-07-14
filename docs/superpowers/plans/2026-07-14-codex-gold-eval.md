# Codex System-Skill Gold Evaluation Plan

Status: Implemented; model-backed verification pending an explicit download

- [x] Stop stale skill-rag test processes before maintenance.
- [x] Remove the local Hugging Face model cache and derived LanceDB/benchmark
  artifacts without deleting `~/.skills`.
- [x] Replace mismatched personal gold names with the five Codex system skills.
- [x] Add `make eval-codex` and configurable personal-eval paths.
- [ ] Run the model-backed Codex evaluation after an explicit model download.

The last item is intentionally separate: cache cleanup means this change can
be verified with the offline test suite without silently downloading a model.
