## 2026-11-27 - Draft tool: pasted Vegas season props (part of JEG-1667)

Contract: Jeremy, 2026-11-27: "I'll paste the lines." Paste parser for
sportsbook season player prop pages, one dated snapshot for every league,
feeding ours through the same path as the 2026-09-12 snapshot. No scraping.

### Verified (check named)
- `tests/test_draft_vegas_paste.py` (11 tests):
  - The realistic invented sample parses to exactly 12 lines across 7 markets and 3 layouts.
  - It fails closed, listing the lines, on an unknown player, an out-of-range line, a wrong season, conflicting lines and a garbled over/under.
  - The tool writes a dated snapshot in the 2026-09-12 shape, or refuses and writes nothing.
  - Pasted lines move ours through `vegasStatLine` and `ddfDraftValues`.
- 55 draft tests pass.

### Claimed, not confirmed
- Real DraftKings and FanDuel pages copy in the layouts the sample uses: the sample is invented, not copied from a book. Jeremy's first real paste is the check.
- `draft_vegas_lines` migration written, not applied (needs Jeremy's yes).
