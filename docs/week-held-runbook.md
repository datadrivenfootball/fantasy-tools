# Week held: runbook (JEG-1512)

A **week-held** alert means Supabase has a newer content week for one or more
sources than the site serves, and the rebuild chain has not published it. The
alert is a GitHub issue labelled `week-held` (GitHub emails the owner) and an
Urgent Linear sub-issue of JEG-1512 titled `Week N is held: the site still shows
week M [week-held:<season>:wN]`, labelled owner:claude.

Why it exists: Week 9, 2026. Every source had Week 9 in Supabase by
2026-11-04 00:38Z; the chain failed every run from 2026-11-01 to 2026-11-05
17:54Z (a week-history clock bug, JEG-1479, then the JEG-1511 waiver-band
tests), and the site served Week 8 for about 41 hours after Week 9 was complete.
The JEG-1194 `chain-stuck` issue never opened (it read the history index that
`make sync` had just rewritten from the unpublished candidate), and the 12-hour
generic ops-alert sat among about 20 fidelity alerts. Jeremy, 2026-11-05: "You
can not let data go late ever again."

## Where it fires

| Path | When | File |
|---|---|---|
| Chain | end of every main `rebuild-chain.yml` run that leaves a newer week unpublished (no wait) | `pipelines/week_held_alert.py --mode chain` |
| Tripwire | hourly at :50 (`source-lateness.yml`, its own schedule) when the committed chain status showing the hold is 2 h old | `--mode tripwire` |
| Drill | `source-lateness.yml` dispatched with `week_held_drill=true`: opens a `[drill]` issue and Linear sub-issue, then closes and archives both | `--mode drill` |

Not week-held (other alerts own these): a source whose own publisher is late
(`source-late`, docs/source-lateness.md); a source held for its own fidelity
problem (`ops-alert` fidelity issues); a chain red with no new week
(`chain-stuck` after 6 h, JEG-1194).

## Who and how fast

Owner: the Claude lane (coordinator). Response: same hour in waking hours
(America/Chicago). Jeremy rules on any test bar or value-model question.

## What to do

1. **Acknowledge** on the Linear sub-issue (comment: who is on it, start time),
   move it to In Progress.
2. **Diagnose** from the issue body: the failing step and tests are named. Open
   the run link. Classify:
   - *Infra / clock / import bug* (e.g. JEG-1479 history capture): fix it on a
     branch, prove with a branch dispatch of `rebuild-chain.yml`, merge.
   - *Data-sensitive test on new data* (e.g. JEG-1511 waiver band): reproduce
     locally on the new bake, then bring Jeremy the ruling as options
     (narrow exemption, move the test out of the blocking gate, or hold). Do not
     relax a bar without his ruling, quoted with the date.
   - *Code regression on main* (a merge broke a test the chain runs): revert or
     fix forward; main CI should have caught it, so link the PR.
   - *Per-source validation hold on a published run*: the rest of the week is
     live; fix that source's cause.
3. **Publish**: the next chain run publishes. Confirm `output/comparison-chain-status.json`
   (`success: true`), `data/history/index.json` served weeks, and the live site
   (`verify_live.py`). The GitHub issue closes itself; the Linear sub-issue gets a
   comment and is closed by a person after the live check.
4. **Record** the timeline and cause in a `docs/claude-log/` entry and on JEG-1485.

## Testing the alert

Dispatch `Source lateness check` with `week_held_drill=true` once (any branch).
The run log shows `github: opened #N`, `linear: opened and archived drill JEG-…`
and `github: closed #N`. Unit tests: `python3 -m unittest tests.test_week_held_alert`.
