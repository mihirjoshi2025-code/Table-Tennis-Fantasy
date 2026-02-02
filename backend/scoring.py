"""
Fantasy scoring for table tennis matches.
Implements the TABLE TENNIS FANTASY SCORING RUBRIC.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any


# ---------- Core match scoring ----------
MATCH_WIN_POINTS = 10
MATCH_LOSS_POINTS = -3
SWEEP_BONUS = 4  # 3-0 or equivalent
FIVE_SET_PARTICIPATION = 2  # win or loss

# ---------- Set & point performance ----------
SET_WON_POINTS = 2
SET_LOST_POINTS = -1
NET_DIFF_BONUS_THRESHOLD = 10
NET_DIFF_BONUS_POINTS = 3
NET_DIFF_PENALTY_THRESHOLD = -10
NET_DIFF_PENALTY_POINTS = -3

# ---------- Clutch & momentum ----------
COMEBACK_SET_POINTS = 2  # wins set after trailing by 4+
DECIDING_SET_WIN_POINTS = 3
STREAK_BREAK_POINTS = 1  # per occurrence
STREAK_3_PLUS_POINTS = 1  # per occurrence

# ---------- Style-based ----------
FOREHAND_WINNER_POINTS = 0.5
BACKHAND_WINNER_POINTS = 0.5
SERVICE_WINNER_POINTS = 0.5
UNFORCED_ERROR_POINTS = -0.5

# ---------- Risk & underdog ----------
DEFEATS_HIGHER_RANKED_POINTS = 3
HEAVY_FAVORITE_LOSS_POINTS = -2
FIRST_MATCH_AFTER_ABSENCE_POINTS = 1


@dataclass
class MatchResult:
    """Minimal match outcome for core scoring."""
    winner_id: str
    loser_id: str
    sets_winner: int  # sets won by winner
    sets_loser: int   # sets won by loser
    best_of: int      # 3 or 5


@dataclass
class MatchStats:
    """Aggregated stats for one player in a match (used for fantasy scoring)."""
    player_id: str
    # From MatchResult / derived
    is_winner: bool = False
    sets_won: int = 0
    sets_lost: int = 0
    best_of: int = 5
    # Point differential (total points won - points lost in match)
    net_point_differential: int = 0
    # Clutch
    comeback_sets: int = 0       # sets won after trailing by 4+ in that set
    won_deciding_set: bool = False
    streak_breaks: int = 0       # broke opponent's 3+ point streak
    streaks_3_plus: int = 0      # won 3+ consecutive points (occurrences)
    # Style
    forehand_winners: int = 0
    backhand_winners: int = 0
    service_winners: int = 0
    unforced_errors: int = 0
    # Risk (optional)
    defeated_higher_ranked: bool = False
    lost_as_heavy_favorite: bool = False
    first_match_after_absence: bool = False


def _core_match_points(stats: MatchStats) -> int:
    """Match win/loss, sweep bonus, five-set participation."""
    points = 0
    if stats.is_winner:
        points += MATCH_WIN_POINTS
        # Sweep: won 3-0 (best of 5) or 2-0 (best of 3)
        sets_to_sweep = 2 if stats.best_of == 3 else 3
        if stats.sets_won >= sets_to_sweep and stats.sets_lost == 0:
            points += SWEEP_BONUS
    else:
        points += MATCH_LOSS_POINTS
    # Five-set match (best_of == 5 and total sets played == 5)
    total_sets = stats.sets_won + stats.sets_lost
    if stats.best_of == 5 and total_sets == 5:
        points += FIVE_SET_PARTICIPATION
    return points


def _set_point_performance_points(stats: MatchStats) -> int:
    """Set won/lost, net point differential."""
    points = stats.sets_won * SET_WON_POINTS + stats.sets_lost * SET_LOST_POINTS
    if stats.net_point_differential >= NET_DIFF_BONUS_THRESHOLD:
        points += NET_DIFF_BONUS_POINTS
    elif stats.net_point_differential <= NET_DIFF_PENALTY_THRESHOLD:
        points += NET_DIFF_PENALTY_POINTS
    return points


def _clutch_momentum_points(stats: MatchStats) -> int:
    """Comeback sets, deciding set, streak break, 3+ streaks."""
    points = stats.comeback_sets * COMEBACK_SET_POINTS
    if stats.won_deciding_set:
        points += DECIDING_SET_WIN_POINTS
    points += stats.streak_breaks * STREAK_BREAK_POINTS
    points += stats.streaks_3_plus * STREAK_3_PLUS_POINTS
    return points


def _style_points(stats: MatchStats) -> float:
    """Forehand/backhand/service winners, unforced errors."""
    points = (
        stats.forehand_winners * FOREHAND_WINNER_POINTS
        + stats.backhand_winners * BACKHAND_WINNER_POINTS
        + stats.service_winners * SERVICE_WINNER_POINTS
        + stats.unforced_errors * UNFORCED_ERROR_POINTS
    )
    return points


def _risk_modifier_points(stats: MatchStats) -> int:
    """Defeats higher-ranked, heavy favorite loss, first match after absence."""
    points = 0
    if stats.defeated_higher_ranked:
        points += DEFEATS_HIGHER_RANKED_POINTS
    if stats.lost_as_heavy_favorite:
        points += HEAVY_FAVORITE_LOSS_POINTS
    if stats.first_match_after_absence:
        points += FIRST_MATCH_AFTER_ABSENCE_POINTS
    return points


def compute_fantasy_score(stats: MatchStats) -> float:
    """
    Compute total fantasy points for one player from their match stats.
    Returns a float (may have 0.5 increments from style stats); round as needed for display.
    """
    total = (
        _core_match_points(stats)
        + _set_point_performance_points(stats)
        + _clutch_momentum_points(stats)
        + _style_points(stats)
        + _risk_modifier_points(stats)
    )
    return total


def build_stats_for_player(
    player_id: str,
    result: MatchResult,
    net_point_differential: int = 0,
    comeback_sets: int = 0,
    won_deciding_set: bool = False,
    streak_breaks: int = 0,
    streaks_3_plus: int = 0,
    forehand_winners: int = 0,
    backhand_winners: int = 0,
    service_winners: int = 0,
    unforced_errors: int = 0,
    defeated_higher_ranked: bool = False,
    lost_as_heavy_favorite: bool = False,
    first_match_after_absence: bool = False,
) -> MatchStats:
    """Build MatchStats for one player from result + optional aggregates."""
    is_winner = player_id == result.winner_id
    sets_won = result.sets_winner if is_winner else result.sets_loser
    sets_lost = result.sets_loser if is_winner else result.sets_winner
    return MatchStats(
        player_id=player_id,
        is_winner=is_winner,
        sets_won=sets_won,
        sets_lost=sets_lost,
        best_of=result.best_of,
        net_point_differential=net_point_differential,
        comeback_sets=comeback_sets,
        won_deciding_set=won_deciding_set,
        streak_breaks=streak_breaks,
        streaks_3_plus=streaks_3_plus,
        forehand_winners=forehand_winners,
        backhand_winners=backhand_winners,
        service_winners=service_winners,
        unforced_errors=unforced_errors,
        defeated_higher_ranked=defeated_higher_ranked,
        lost_as_heavy_favorite=lost_as_heavy_favorite,
        first_match_after_absence=first_match_after_absence,
    )


# ---------- Aggregation from point events (simulation or live) ----------

def _shot_type_key(shot_type: str) -> str:
    return (shot_type or "").strip().lower()


def aggregate_stats_from_events(
    events: list[Any],
    winner_id: str,
    player_a_id: str,
    player_b_id: str,
    best_of: int = 5,
) -> tuple[MatchStats, MatchStats]:
    """
    Build MatchStats for both players from a list of point events.
    Each event is a dict or object with: outcome.winner_id, outcome.shot_type,
    score_before, score_after, set_index, set_scores_after, streak_broken, streak_continuing.
    """
    result = MatchResult(
        winner_id=winner_id,
        loser_id=player_b_id if winner_id == player_a_id else player_a_id,
        sets_winner=0,
        sets_loser=0,
        best_of=best_of,
    )
    if events:
        last = events[-1]
        # set_scores_after: (sets_a, sets_b) or similar
        if hasattr(last, "set_scores_after"):
            sa, sb = last.set_scores_after[0], last.set_scores_after[1]
        else:
            sa = last.get("set_scores_after", [0, 0])[0]
            sb = last.get("set_scores_after", [0, 0])[1]
        result = MatchResult(
            winner_id=winner_id,
            loser_id=player_b_id if winner_id == player_a_id else player_a_id,
            sets_winner=sa if winner_id == player_a_id else sb,
            sets_loser=sb if winner_id == player_a_id else sa,
            best_of=best_of,
        )

    # Per-set point totals for differential and comeback detection
    set_points_a: list[int] = []
    set_points_b: list[int] = []
    current_set = -1
    points_a_in_set = 0
    points_b_in_set = 0

    # Per-player style and clutch counts
    fh_a, bh_a, sv_a, ue_a = 0, 0, 0, 0
    fh_b, bh_b, sv_b, ue_b = 0, 0, 0, 0
    streak_breaks_a, streak_breaks_b = 0, 0
    streaks_3_plus_a, streaks_3_plus_b = 0, 0
    comeback_sets_a, comeback_sets_b = 0, 0
    # Track max deficit in current set (for comeback)
    max_deficit_a, max_deficit_b = 0, 0
    # Consecutive points for 3+ streak
    consec_a, consec_b = 0, 0

    deciding_set_index = best_of - 1
    won_deciding_a = False
    won_deciding_b = False

    for ev in events:
        if hasattr(ev, "outcome"):
            winner = ev.outcome.winner_id
            shot = _shot_type_key(getattr(ev.outcome, "shot_type", "") or "")
        else:
            o = ev.get("outcome", {})
            winner = o.get("winner_id", "")
            shot = _shot_type_key(o.get("shot_type", "") or "")

        if hasattr(ev, "set_index"):
            si = ev.set_index
        else:
            si = ev.get("set_index", 0)
        if hasattr(ev, "score_before"):
            sb = ev.score_before
        else:
            sb = tuple(ev.get("score_before", (0, 0)))
        if hasattr(ev, "score_after"):
            sa_after = ev.score_after
        else:
            sa_after = tuple(ev.get("score_after", (0, 0)))
        streak_broken = getattr(ev, "streak_broken", False) or ev.get("streak_broken", False)
        streak_continuing = getattr(ev, "streak_continuing", None) or ev.get("streak_continuing")

        # New set: flush previous set and check comeback
        if si != current_set:
            if current_set >= 0:
                set_points_a.append(points_a_in_set)
                set_points_b.append(points_b_in_set)
                # Did A win this set after trailing by 4+?
                if points_a_in_set > points_b_in_set and max_deficit_a >= 4:
                    comeback_sets_a += 1
                elif points_b_in_set > points_a_in_set and max_deficit_b >= 4:
                    comeback_sets_b += 1
                if current_set == deciding_set_index:
                    if points_a_in_set > points_b_in_set:
                        won_deciding_a = True
                    else:
                        won_deciding_b = True
            current_set = si
            points_a_in_set, points_b_in_set = 0, 0
            max_deficit_a, max_deficit_b = 0, 0

        # Point to winner (points = rallies in the set)
        if winner == player_a_id:
            points_a_in_set += 1
            consec_a += 1
            consec_b = 0
            if consec_a == 3:
                streaks_3_plus_a += 1
            elif consec_a > 3:
                pass  # same streak, no extra point
            if streak_broken:
                streak_breaks_a += 1
            if shot == "forehand":
                fh_a += 1
            elif shot == "backhand":
                bh_a += 1
            elif shot == "service":
                sv_a += 1
            elif shot == "unforced_error":
                ue_a += 1
        else:
            points_b_in_set += 1
            consec_b += 1
            consec_a = 0
            if consec_b == 3:
                streaks_3_plus_b += 1
            if streak_broken:
                streak_breaks_b += 1
            if shot == "forehand":
                fh_b += 1
            elif shot == "backhand":
                bh_b += 1
            elif shot == "service":
                sv_b += 1
            elif shot == "unforced_error":
                ue_b += 1

        # Max deficit in set (points = rallies); for "trailing by 4+ points"
        def_a = points_b_in_set - points_a_in_set
        def_b = points_a_in_set - points_b_in_set
        if def_a > max_deficit_a:
            max_deficit_a = def_a
        if def_b > max_deficit_b:
            max_deficit_b = def_b

    if current_set >= 0:
        set_points_a.append(points_a_in_set)
        set_points_b.append(points_b_in_set)
        if points_a_in_set > points_b_in_set and max_deficit_a >= 4:
            comeback_sets_a += 1
        elif points_b_in_set > points_a_in_set and max_deficit_b >= 4:
            comeback_sets_b += 1
        if current_set == deciding_set_index:
            if points_a_in_set > points_b_in_set:
                won_deciding_a = True
            else:
                won_deciding_b = True

    total_points_a = sum(set_points_a)
    total_points_b = sum(set_points_b)
    net_a = total_points_a - total_points_b
    net_b = total_points_b - total_points_a

    stats_a = build_stats_for_player(
        player_a_id,
        result,
        net_point_differential=net_a,
        comeback_sets=comeback_sets_a,
        won_deciding_set=won_deciding_a,
        streak_breaks=streak_breaks_a,
        streaks_3_plus=streaks_3_plus_a,
        forehand_winners=fh_a,
        backhand_winners=bh_a,
        service_winners=sv_a,
        unforced_errors=ue_a,
    )
    stats_b = build_stats_for_player(
        player_b_id,
        result,
        net_point_differential=net_b,
        comeback_sets=comeback_sets_b,
        won_deciding_set=won_deciding_b,
        streak_breaks=streak_breaks_b,
        streaks_3_plus=streaks_3_plus_b,
        forehand_winners=fh_b,
        backhand_winners=bh_b,
        service_winners=sv_b,
        unforced_errors=ue_b,
    )
    return stats_a, stats_b
