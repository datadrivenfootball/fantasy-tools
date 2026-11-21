"""JEG-1691 v5: statistics shared by the tests (pure)."""
from __future__ import annotations

import math
import random
import statistics

SEED = 16911
N_BOOT = 2000
N_SHUFFLE = 1000


def ranks(xs: list) -> list:
    """Average ranks (1-based), ties share the mean rank."""
    order = sorted(range(len(xs)), key=lambda i: xs[i])
    r = [0.0] * len(xs)
    i = 0
    while i < len(order):
        j = i
        while j + 1 < len(order) and xs[order[j + 1]] == xs[order[i]]:
            j += 1
        avg = (i + j) / 2 + 1
        for t in range(i, j + 1):
            r[order[t]] = avg
        i = j + 1
    return r


def pearson(a: list, b: list) -> float | None:
    n = len(a)
    if n < 3:
        return None
    ma, mb = sum(a) / n, sum(b) / n
    sa = math.sqrt(sum((x - ma) ** 2 for x in a))
    sb = math.sqrt(sum((y - mb) ** 2 for y in b))
    if sa == 0 or sb == 0:
        return None
    return sum((x - ma) * (y - mb) for x, y in zip(a, b)) / (sa * sb)


def spearman(a: list, b: list) -> float | None:
    return pearson(ranks(a), ranks(b))


def pct(values: dict) -> dict:
    """{key: percentile rank in (0, 1]} within the dict (average ranks / n)."""
    ks = list(values)
    r = ranks([values[k] for k in ks])
    n = len(ks)
    return {k: x / n for k, x in zip(ks, r)}


def moves(lo: dict, hi: dict, keys) -> dict:
    """Percentile move hi - lo over a common key set."""
    a, b = pct({k: lo[k] for k in keys}), pct({k: hi[k] for k in keys})
    return {k: b[k] - a[k] for k in keys}


def sd(xs: list) -> float | None:
    return statistics.pstdev(xs) if len(xs) >= 2 else None


def ci(draws: list) -> tuple:
    d = sorted(x for x in draws if x is not None)
    if not d:
        return (None, None)
    return (d[int(0.025 * len(d))], d[max(0, int(0.975 * len(d)) - 1)])


def resample(units: dict, rng: random.Random) -> dict:
    """{cell: [keys]} -> the same cells with keys drawn with replacement."""
    return {c: [ks[rng.randrange(len(ks))] for _ in ks] for c, ks in units.items() if ks}


def no_harm_label(c: tuple) -> str:
    lo, hi = c
    if lo is None:
        return "NA"
    return "PASS" if lo >= 0 else ("HARM" if hi < 0 else "INCONCLUSIVE")


def mean_or_none(xs):
    xs = [x for x in xs if x is not None]
    return statistics.fmean(xs) if xs else None
