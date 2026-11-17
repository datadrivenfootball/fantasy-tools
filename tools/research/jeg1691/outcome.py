"""JEG-1691 v5: the outcome A / B / C picked mechanically (preregistration section 5).

decide() reads the primary battery, every sensitivity battery, the week-10-only battery
(fresh Sleeper) and T1, applies the rules in order and returns the outcome with every rule
that fired. No judgement enters: the doc's section 5 table is this function.
"""
from __future__ import annotations

HINGE_TESTS = ("T3", "T4", "T5", "T6", "T7", "T8")


def passes(b: dict) -> dict:
    """Per Tier 1 chart test: True when it passes (no-harm tests: no HARM cell)."""
    return {
        "T2": bool(b["T2"]) and all(x["pass"] for x in b["T2"].values()),
        "T3": bool(b["T3"]) and all(x["label"] == "PASS" for x in b["T3"].values()),
        "T4": bool(b["T4"]) and all(x["pass"] for x in b["T4"].values()),
        "T5": bool(b["T5"]) and all(x["pass"] for x in b["T5"].values()),
        "T6": bool(b["T6"]) and all(r["pass"] is True for x in b["T6"].values() for r in x.values()),
        "T7": all(x["label"] != "HARM" for x in b["T7"].values()),
        "T8": all(x["label"] != "HARM" for x in b["T8"].values()),
    }


def decide(primary: dict, sensitivity: dict, t1: dict | None) -> dict:
    """sensitivity: {name: battery}, including "W10-only" (fresh Sleeper). Rules in order;
    the first group that fires sets the outcome, later groups are still listed."""
    p = passes(primary)
    fired = []
    # 0. a harness failure on the decisive weeks voids the run
    if not p["T2"]:
        fired.append(("VOID", "T2 failed on the decisive weeks: the run is void; after a dated bug fix "
                              "weeks 11-14 become the decisive weeks of a B round"))
    t1v = None if t1 is None else t1["verdict"]
    t1d = None if t1 is None else t1["a"]["diff"]
    # 1. outcome A
    if t1v == "FAIL":
        fired.append(("A", "T1 FAIL: the position mix beats the player's own mix"))
    if t1v == "INCONCLUSIVE" and (t1d is None or t1d <= 0):
        fired.append(("A", f"T1 INCONCLUSIVE with point estimate {t1d} <= 0"))
    if not p["T4"]:
        fired.append(("A", "T4 FAIL (primary): the rebuild's moves do not track the reference mix's"))
    for t in ("T7", "T8"):
        if not p[t]:
            fired.append(("A", f"{t} HARM (primary)"))
    # 2. outcome B
    if t1v == "INCONCLUSIVE" and t1d is not None and t1d > 0:
        fired.append(("B", f"T1 INCONCLUSIVE with point estimate {t1d} > 0 (low power): B(ii)"))
    if t1 is None:
        fired.append(("B", "T1 not computed"))
    for t in ("T3", "T5", "T6"):
        if not p[t]:
            fired.append(("B", f"{t} fails (primary): B(i)"))
    for name, b in sensitivity.items():
        q = passes(b)
        for t in HINGE_TESTS:
            if p[t] and not q[t]:
                fired.append(("B", f"{t} hinges on {name}: passes in the primary, fails there"))
        if not q["T2"]:
            fired.append(("B", f"T2 fails under {name}"))
    order = {"VOID": 0, "A": 1, "B": 2}
    if fired:
        outcome = min((f[0] for f in fired), key=order.get)
    else:
        outcome = "C"
        fired.append(("C", "every Tier 1 test passes in the primary and in every sensitivity run, T1 PASS"))
    if outcome == "VOID":
        outcome = "B (void run)"
    return {"outcome": outcome, "rules_fired": [{"outcome": o, "rule": r} for o, r in fired],
            "primary_passes": p, "sensitivity_passes": {n: passes(b) for n, b in sensitivity.items()}}
