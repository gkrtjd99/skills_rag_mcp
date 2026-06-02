# Tech Debt Tracker

No active execution plan is in progress. Promote any behavioral change to
`docs/superpowers/specs/` and `docs/superpowers/plans/` before implementation.

## Known Follow-ups

- Bootstrap refresh semantics: `skill-rag install` does not overwrite an
  existing `~/.skills/using-skill-rag` copy. Decide whether to preserve user
  edits forever, compare hashes and refresh, or add an explicit
  `--refresh-bootstrap`.
- Translation retry state: if sync runs before MarianMT models are cached,
  translation gracefully stores an empty augmentation. Because unchanged records
  are skipped later, users need `skill-rag reset && skill-rag sync` to recover.
  A future index/content-version marker could make this automatic.
- Duplicate frontmatter names: the index primary key is `path`, but
  `retrieve` and `get_skill` key several lookups by frontmatter `name`. Add a
  validation or collision policy if duplicate names appear in the corpus.
- CLI status completeness: `skill-rag status` reports the dense threshold but
  not BM25 threshold, RRF constant, translation toggle, or local-files-only
  model mode.
