"""Synthetic draft data for the draft tool tests (JEG-1667 Phase 1).

No third-party numbers: every player, projection, rank and dollar value here
is generated. The shape is DraftData's bundle (app/draft/draft-data.js)."""
from __future__ import annotations

POSITIONS = {"QB": 32, "RB": 72, "WR": 90, "TE": 36, "K": 16, "DST": 16}
TEAMS = ["ARI", "ATL", "BAL", "BUF", "CAR", "CHI", "CIN", "CLE", "DAL", "DEN", "DET", "GB", "HOU", "IND", "JAX", "KC"]
PULLED_AT = "2026-11-28T11:15:18+00:00"


def _proj(pos: str, i: int) -> dict:
    fade = max(0.05, 1 - i / (POSITIONS[pos] * 0.95))
    zero = dict(pass_yds=0, pass_tds=0, ints=0, rush_yds=0, rush_tds=0, rec=0, rec_yds=0, rec_tds=0, fum_lost=1)
    if pos == "QB":
        zero.update(pass_yds=4400 * fade, pass_tds=34 * fade, ints=11, rush_yds=450 * fade, rush_tds=5 * fade)
    elif pos == "RB":
        zero.update(rush_yds=1500 * fade, rush_tds=13 * fade, rec=60 * fade, rec_yds=480 * fade, rec_tds=3 * fade)
    elif pos == "WR":
        zero.update(rec=115 * fade, rec_yds=1550 * fade, rec_tds=11 * fade)
    else:
        zero.update(rec=95 * fade, rec_yds=1050 * fade, rec_tds=8 * fade)
    return {k: round(v, 1) for k, v in zero.items()}


def bundle() -> dict:
    players, skill = [], []
    n = 0
    for pos, count in POSITIONS.items():
        for i in range(count):
            n += 1
            p = {"key": str(1000 + n), "name": f"{pos} Player {i + 1:02d}", "pos": pos, "team": TEAMS[(n * 7) % len(TEAMS)],
                 "bye": 5 + (n * 3) % 10, "proj": None, "vegas": None, "ecr": {}, "espn": {}}
            if pos in ("QB", "RB", "WR", "TE"):
                p["proj"] = _proj(pos, i)
                # the first few at each position carry Vegas lines, some partial
                if i < 4 and pos != "QB":
                    p["vegas"] = {"season_rec_yds": round(p["proj"]["rec_yds"] * 0.9, 1)}
                    if i < 2:
                        p["vegas"].update(season_receptions=round(p["proj"]["rec"] * 0.9, 1), season_rec_tds=round(p["proj"]["rec_tds"] * 0.9, 1))
                        if pos == "RB":
                            p["vegas"].update(season_rush_yds=round(p["proj"]["rush_yds"] * 0.9, 1), season_rush_tds=round(p["proj"]["rush_tds"] * 0.9, 1))
                skill.append((pos, i, p))
            players.append(p)
    # Market order differs from ours: a fixed position weight and a small shuffle.
    weight = {"QB": 0.62, "RB": 1.0, "WR": 0.97, "TE": 0.7}
    ranked = sorted(skill, key=lambda t: (-(1 - t[1] / POSITIONS[t[0]]) * weight[t[0]] - ((int(t[2]["key"]) * 37) % 11) / 400, t[2]["key"]))
    for rank, (_pos, _i, p) in enumerate(ranked, start=1):
        tier = 1 + rank // 12
        for fmt in ("STD", "HALF", "PPR"):
            p["ecr"][fmt] = {"rank": rank, "tier": tier, "sd": 2.0}
        dollars = max(0, round(72 * (0.972 ** rank) - 1))
        p["espn"] = {"STD": dollars, "PPR": dollars, "aav": dollars * 1.02}
    kd = [p for p in players if p["pos"] in ("K", "DST")]
    for j, p in enumerate(kd):
        for fmt in ("STD", "HALF", "PPR"):
            p["ecr"][fmt] = {"rank": 150 + j, "tier": 14, "sd": 5.0}
    return {"v": 1, "season": 2026,
            "asOf": {"pullDate": "2026-11-28", "pulledAt": PULLED_AT,
                     "sources": {"fantasypros_ecr": {"pullDate": "2026-11-28", "pulledAt": PULLED_AT},
                                 "espn": {"pullDate": "2026-11-28", "pulledAt": PULLED_AT}},
                     "projections": "2026-09-11", "vegas": "2026-09-12", "vegasSource": "paste"},
            "credits": ["Synthetic test data"], "players": players,
            "dropped": {"unnamedProjections": 0, "vegasUnmatched": 0}}
