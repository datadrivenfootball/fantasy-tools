# Steelman review brief (JEG-1601, part of JEG-1597)

Role: adversarial, read-only reviewer. Do not edit, commit, comment on Linear, or run anything
that writes. You may run read-only commands and the existing tests/scripts that write only under
`tools/research/jeg1597/out/` if you need to verify a number.

Worktree: `/Users/botcomp/code/fantasy-tools-jeg1597` (branch `claude/JEG-1597-scoring-aware`).

Under review: the draft reader page `docs/research/jeg1597/page/how-we-got-to-the-values.html`
("How we got to the values", scoring section). Its claims must be backed by:
- `docs/research/jeg1597/step1-scoring-assignment.md` (scoring inference; failed its labelled test)
- `docs/research/jeg1597/fantasycalc-pegged-or-blend.md` (FantasyCalc base = 12-team Full PPR)
- `docs/research/jeg1597/step2-decomposition.md`, `step3-proposal.md` (method, week 9 changes)
- `docs/research/jeg1597/step4-preregistration.md` (tests stated before results; see its change log)
- `docs/research/jeg1597/step4-results.md`, `tools/research/jeg1597/out/step4_results.json`
- `docs/methodology.md` VP-0, VP-2, VP-4, VP-6.3, VP-9 (what DDF does today)

Readers: fantasy players reading on a phone. House style: plain words, no hype; "Analyst charts"
= average of CBS Sports, USA Today, FantasyPros; "Live market" = FantasyCalc; never a bare
"Market"; no demo/illustrative/mock labels.

Judge two things:
1. **Clear**: can a fantasy player follow it, and does any sentence mislead?
2. **Logic holds**: is every claim supported by the docs and data above, are the tests fair,
   are the verdicts stated correctly per the pre-registered rules, is anything overclaimed or
   left out that a skeptic would need (including negative results and the steelman that
   FantasyCalc's flat response reflects real market behaviour)?

Reply in at most 25 lines, in this shape:
```
CLEAR: yes|no
LOGIC_HOLDS: yes|no
OBJECTIONS (strongest first, max 3):
1. <claim or gap> | evidence: <file:line or number> | fix: <one line>
2. ...
```
Answer "yes" only if you would sign off on the page as it stands. Minor wording nits do not
make it "no"; say them in one line at the end.
