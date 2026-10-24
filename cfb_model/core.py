"""Chronological, opponent-adjusted CFB baseline. Not a validated profitable model."""
from __future__ import annotations
from dataclasses import dataclass
from math import erf, sqrt
from statistics import pstdev
import pandas as pd
from .data import normalize_games


def normal_cdf(z: float) -> float:
    return (1.0 + erf(z / sqrt(2.0))) / 2.0


@dataclass(frozen=True)
class Forecast:
    home_margin: float
    total: float
    home_win_prob: float
    margin_sigma: float
    total_sigma: float
    training_games: int
    home_sample: int
    away_sample: int

    @property
    def home_score(self):
        return (self.total + self.home_margin) / 2

    @property
    def away_score(self):
        return (self.total - self.home_margin) / 2

    def probability(self, outcome: str, line: float | None = None) -> float:
        if outcome == "HOME_WIN":
            return self.home_win_prob
        if outcome == "AWAY_WIN":
            return 1 - self.home_win_prob
        if outcome in ("HOME_COVER", "AWAY_COVER"):
            if line is None:
                raise ValueError("Spread requires a home-team handicap line")
            # A home spread of -3.5 covers if home margin exceeds +3.5.
            home_cover = normal_cdf((self.home_margin + line) / self.margin_sigma)
            return home_cover if outcome == "HOME_COVER" else 1 - home_cover
        if outcome in ("OVER", "UNDER"):
            if line is None:
                raise ValueError("Game total requires a line")
            over = normal_cdf((self.total - line) / self.total_sigma)
            return over if outcome == "OVER" else 1 - over
        raise ValueError("Unrecognized outcome: " + outcome)


class PowerModel:
    """Sequential point ratings + exponentially smoothed offense/defense.

    Only completed games supplied through update() affect ratings. Forecast() never
    accesses actual points in a future game. Hyperparameters fixed a priori;
    research use until held-out model validation.
    """
    def __init__(self, home_field: float = 2.5):
        self.home_field = home_field
        self.ratings = {}
        self.offense = {}
        self.defense = {}
        self.counts = {}
        self.last_season = None
        self.trained_games = 0
        self.margin_errors = []
        self.total_errors = []

    def new_season(self, season: int):
        if self.last_season is not None and season != self.last_season:
            # Regress power and points to population mean after offseason changes.
            self.ratings = {t: p * .70 for t, p in self.ratings.items()}
            self.offense = {t: 28 + (p - 28) * .65 for t, p in self.offense.items()}
            self.defense = {t: 28 + (p - 28) * .65 for t, p in self.defense.items()}
            self.counts = {t: 0 for t in self.counts}
        self.last_season = season

    def forecast(self, home: str, away: str, neutral: bool = False) -> Forecast:
        margin = self.ratings.get(home, 0) - self.ratings.get(away, 0) + (0 if neutral else self.home_field)
        h_off, a_off = self.offense.get(home, 28), self.offense.get(away, 28)
        h_def, a_def = self.defense.get(home, 28), self.defense.get(away, 28)
        # Shrink scoring estimates early; a stronger team can still have low pace.
        h_score = .5 * (h_off + a_def)
        a_score = .5 * (a_off + h_def)
        total = max(20, min(90, h_score + a_score))
        # Conservative empirical residual floors; minimum data is NOT validation.
        m_sig = max(14.0, pstdev(self.margin_errors[-700:])) if len(self.margin_errors) >= 40 else 17.0
        t_sig = max(12.0, pstdev(self.total_errors[-700:])) if len(self.total_errors) >= 40 else 16.0
        return Forecast(round(margin, 2), round(total, 2), normal_cdf(margin/m_sig),
                        m_sig, t_sig, self.trained_games,
                        self.counts.get(home, 0), self.counts.get(away, 0))

    def update(self, home: str, away: str, hp: float, ap: float, neutral=False):
        pre = self.forecast(home, away, neutral)
        residual = (hp-ap) - pre.home_margin
        self.margin_errors.append(residual)
        self.total_errors.append((hp+ap) - pre.total)
        # Two-sided point-rating update with bounded single-game shocks.
        step = .13 * max(-35.0, min(35.0, residual))
        self.ratings[home] = self.ratings.get(home, 0) + step / 2
        self.ratings[away] = self.ratings.get(away, 0) - step / 2
        # Prior regularization prevents outlier final scores dominating.
        for team, pts_for, pts_against in ((home,hp,ap),(away,ap,hp)):
            n = self.counts.get(team, 0)
            rate = .24 if n >= 3 else .15
            self.offense[team] = (1-rate)*self.offense.get(team, 28) + rate*pts_for
            self.defense[team] = (1-rate)*self.defense.get(team, 28) + rate*pts_against
            self.counts[team] = n+1
        self.trained_games += 1


def walk_forward(games: pd.DataFrame, min_history: int = 300):
    """Returns pregame predictions plus final fitted model. Never scores with future inputs."""
    games = normalize_games(games)
    model = PowerModel()
    rows = []
    for _, g in games.iterrows():
        model.new_season(int(g.season))
        pred = model.forecast(g.home_team, g.away_team, bool(g.neutral_site))
        row = {"game_id": g.game_id, "season": int(g.season), "week": int(g.week),
               "kickoff_utc": g.kickoff_utc, "home_team":g.home_team, "away_team":g.away_team,
               "completed":bool(g.completed), "eligible_history":pred.training_games >= min_history,
               "projected_home_margin": pred.home_margin, "projected_total": pred.total,
               "home_win_prob": pred.home_win_prob, "margin_sigma":pred.margin_sigma,
               "total_sigma":pred.total_sigma,"training_games":pred.training_games,
               "home_sample":pred.home_sample,"away_sample":pred.away_sample,
               "home_points":g.home_points,"away_points":g.away_points}
        rows.append(row)
        if g.completed:
            model.update(g.home_team, g.away_team, float(g.home_points), float(g.away_points), bool(g.neutral_site))
    return pd.DataFrame(rows), model
