## Summary

What does this PR change or add?

## Checklist

- [ ] I ran `ruff check mainframe_brain tests` (zero errors)
- [ ] I ran `pytest tests/` (all tests pass)
- [ ] I added golden fixtures for new/updated extractor behavior
- [ ] I updated docs if user-facing (README, ARCHITECTURE.md, SCHEMA.md)
- [ ] I followed the cross-extractor ownership protocol (one node type, one extractor)

## Extractor changes

If this touches an extractor:
- [ ] Golden fixture test covers the new/existing behavior
- [ ] `can_handle()` is exclusive (no two extractors emit the same node type from the same file)
- [ ] Post-REPLACING expansion hashing is correct (COPY REPLACING hash ≠ base hash)

## Notes for reviewers

Any gotchas, design decisions, or areas that need extra attention?
