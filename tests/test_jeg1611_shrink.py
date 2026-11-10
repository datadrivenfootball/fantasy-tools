"""JEG-1611: unit tests of the shrunk expected-receptions model
(tools/research/jeg1611/shrink/model.py). Synthetic inputs plus the fitted model.json."""
from __future__ import annotations

import math
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools" / "research" / "jeg1611" / "shrink"))
import model as M  # noqa: E402

TOY = {"positions": {"WR": {"prior_form": "mean", "half_life_games": None, "season_decay": 1.0, "k": 4.0, "mean": 3.0},
                     "RB": {"prior_form": "linear_std", "half_life_games": None, "season_decay": 1.0, "k": 2.0,
                            "mean": 1.5, "a": 1.0, "b": 0.1}},
       "ratio_model": {"WR": {"half_life_games": None, "season_decay": 1.0, "k": 4.0, "mean": math.log1p(0.4),
                              "min_std_h": 1.0}},
       "qb": {"mean_rec_pg": 0.01}, "half_life_games": None, "season_decay": 1.0}


def test_shrink_formula_and_future_rows_ignored():
    hist = [(2024, w, 10.0, 16.0) for w in range(1, 5)]          # 4 games, 6 rec/g
    hist += [(2024, 9, 0.0, 30.0)]                                 # after the decision week: ignored
    rec_hat, n_eff, w = M.expected_receptions(hist, "WR", 5, 2024, TOY)
    assert n_eff == 4 and abs(w - 0.5) < 1e-12
    assert abs(rec_hat - (4 * 6 + 4 * 3) / 8) < 1e-12


def test_no_history_returns_prior_with_zero_weight():
    assert M.expected_receptions([], "WR", 5, 2024, TOY) == (3.0, 0.0, 0.0)
    rec_hat, n_eff, w = M.expected_receptions([(2024, 1, 5.0, 5.0)], "QB", 5, 2024, TOY)
    assert rec_hat == 0.01 and w == 0.0


def test_recency_and_season_decay():
    hist = [(2023, 1, 10.0, 12.0), (2024, 1, 10.0, 18.0)]
    n_eff, s_std, s_rec, n_raw = M.recency_sums(hist, 2024, 2, half_life=1.0, season_decay=0.5)
    # older game: one game back (x0.5) and one season back (x0.5)
    assert n_raw == 2 and abs(n_eff - 1.25) < 1e-12
    assert abs(s_rec / n_eff - (8 + 0.25 * 2) / 1.25) < 1e-12
    # decision in a later season applies the decay to every game
    assert abs(M.recency_sums(hist, 2025, 1, None, 0.5)[0] - (0.5 + 0.25)) < 1e-12


def test_role_aware_prior_uses_points_level():
    hist = [(2024, w, 20.0, 22.0) for w in range(1, 3)]            # 2 games, 2 rec/g, 20 std ppg
    rec_hat, _n, w = M.expected_receptions(hist, "RB", 5, 2024, TOY)
    prior = 1.0 + 0.1 * 20.0
    assert abs(w - 0.5) < 1e-12 and abs(rec_hat - (0.5 * 2 + 0.5 * prior)) < 1e-12


def test_fitted_model_json_loads_and_is_sane():
    m = M.load_model()
    for pos in M.SKILL_POS:
        pm = m["positions"][pos]
        assert pm["k"] >= 0 and 0 < pm["season_decay"] <= 1
        hist = [(2025, w, 8.0, 13.0) for w in range(1, 9)]
        rec_hat, n_eff, w = M.expected_receptions(hist, pos, 9, 2025, m)
        assert 0 < w <= 1 and 0 < rec_hat < 10 and n_eff > 0
        share, _n, ws = M.expected_reception_share(hist, pos, 9, 2025, m)
        assert 0 < share < 1.5 and 0 <= ws <= 1
