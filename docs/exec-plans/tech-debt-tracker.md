# Tech Debt Tracker

No active execution plan is in progress. Promote any behavioral change to
`docs/superpowers/specs/` and `docs/superpowers/plans/` before implementation.

## Known Follow-ups

- Translation retry state: if sync runs before MarianMT models are cached,
  translation gracefully stores an empty augmentation. Because unchanged records
  are skipped later, users need `skill-rag reset && skill-rag sync` to recover.
  A future index/content-version marker could make this automatic.
