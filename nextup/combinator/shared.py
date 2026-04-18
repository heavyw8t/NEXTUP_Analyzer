"""
NEXTUP combinator shared helper (v1.1).

Per-language `combine_{lang}.py` scripts import this module, construct a
`Combinator` with language-specific vocabulary and hooks, and call `.run()`.
All shared scaffolding (loading, connectivity via BFS, scoring skeleton,
CLI harness, atomic write) lives here. Language scripts own only vocabulary
constants and optional extra-rule / extra-score predicates.

CLI: python3 combine_{lang}.py <pieces.json> <k> <output.json> [--top N]
"""

from __future__ import annotations

import json
import os
import sys
import tempfile
from collections import defaultdict
from itertools import combinations
from typing import Callable, Iterable


PieceList = list[dict]
Combo = tuple[dict, ...]

DEFAULT_TOP_N = {2: 50, 3: 100, 4: 150}

DEFAULT_RULES = {
    "min_categories": 2,
    "require_shared_contract_or_call": True,
    "require_interaction_link": True,
    "eliminate_actor_conflict": True,
    "eliminate_redundant_same_direction_rounding": True,
    "eliminate_same_function_duplicate": True,
    "eliminate_read_only_combos": True,
    "eliminate_pure_defensive": True,
    "eliminate_no_state_overlap": True,
    "eliminate_all_neutral_same_context": True,
}

DEFAULT_WEIGHTS = {
    "category_diversity": 2.0,
    "has_economic_piece": 3.0,
    "has_rounding_piece": 1.5,
    "has_oracle_piece": 2.0,
    "mixed_direction": 2.5,
    "same_state_touched": 2.0,
    "all_checked_arithmetic_penalty": 1.0,
    "extras": {},
}

NON_NEUTRAL_DIRECTIONS = {"favors_protocol", "favors_user", "exploitable", "latent"}


def load_pieces(path: str) -> PieceList:
    with open(path) as f:
        data = json.load(f)
    if not isinstance(data, list):
        raise ValueError(f"pieces.json must be a JSON array, got {type(data).__name__}")
    return data


def load_config(lang: str, base_dir: str) -> tuple[dict, dict]:
    rules_path = os.path.join(base_dir, "rules", f"{lang}.json")
    weights_path = os.path.join(base_dir, "weights", f"{lang}.json")
    try:
        with open(rules_path) as f:
            rules = json.load(f)
    except FileNotFoundError:
        rules = dict(DEFAULT_RULES)
    try:
        with open(weights_path) as f:
            weights = json.load(f)
    except FileNotFoundError:
        weights = dict(DEFAULT_WEIGHTS)
    return rules, weights


def _piece_type_id(piece: dict) -> str:
    t = piece.get("type", "")
    return t.split("_", 1)[0] if t else ""


def _piece_type_suffix(piece: dict) -> str:
    """Return the un-prefixed portion of the type id (e.g. 'A01' from 'EVM-A01')."""
    t = piece.get("type", "")
    if "-" in t:
        t = t.split("-", 1)[1]
    return t.split("_", 1)[0] if "_" in t else t


def _piece_has_bridge(piece: dict, bridge_types: set[str]) -> bool:
    """Bridge matching accepts either full prefixed id (EVM-L01) or suffix (L01)."""
    full = piece.get("type", "")
    suffix = _piece_type_suffix(piece)
    return full in bridge_types or suffix in bridge_types or (suffix[:1] in bridge_types and len(suffix) >= 1)


class Combinator:
    """
    Per-language combinator.

    Hooks (all optional, called with the original piece dicts):
      - extra_eliminate(combo) -> bool: return True to KEEP, False to drop.
      - extra_score(combo, base) -> float: return new score to overwrite base.
      - post_metadata(metadata, survivors) -> None: mutate metadata in place.
    """

    def __init__(
        self,
        language: str,
        *,
        rounding_types: Iterable[str] = (),
        defensive_types: Iterable[str] = (),
        bridge_types: Iterable[str] = (),
        conflicting_actors: Iterable[tuple[str, str]] = (),
        read_only_indicators: Iterable[str] = ("view", "query", "simulate", "pure"),
        cron_actor: str | None = None,
        arithmetic_gap_type: str = "A06",
        extra_eliminate: Callable[[Combo], bool] | None = None,
        extra_score: Callable[[Combo, float], float] | None = None,
        post_metadata: Callable[[dict, list[tuple[Combo, float]]], None] | None = None,
    ) -> None:
        self.language = language
        self.rounding_types = set(rounding_types)
        self.defensive_types = set(defensive_types)
        self.bridge_types = set(bridge_types)
        self.conflicting_actors = {frozenset(pair) for pair in conflicting_actors}
        self.read_only_indicators = set(read_only_indicators)
        self.cron_actor = cron_actor
        self.arithmetic_gap_type = arithmetic_gap_type
        self.extra_eliminate = extra_eliminate
        self.extra_score = extra_score
        self.post_metadata = post_metadata

    # --- connectivity ---

    def _pieces_are_linked(self, a: dict, b: dict) -> bool:
        a_state = set(a.get("state_touched", []))
        b_state = set(b.get("state_touched", []))
        if a_state & b_state:
            return True

        if a["id"] in b.get("depends_on", []) or b["id"] in a.get("depends_on", []):
            return True

        a_ctx = a.get("call_context", "")
        b_ctx = b.get("call_context", "")
        if a_ctx and b_ctx and a_ctx == b_ctx:
            return True

        a_bridge = _piece_has_bridge(a, self.bridge_types)
        b_bridge = _piece_has_bridge(b, self.bridge_types)
        if (a_bridge or b_bridge) and a.get("contract") == b.get("contract"):
            return True

        if (
            a.get("file") == b.get("file")
            and a.get("function") == b.get("function")
            and a.get("function")
        ):
            return True

        return False

    def _combo_connected(self, combo: Combo) -> bool:
        n = len(combo)
        if n <= 1:
            return True
        adj: dict[int, set[int]] = defaultdict(set)
        for i in range(n):
            for j in range(i + 1, n):
                if self._pieces_are_linked(combo[i], combo[j]):
                    adj[i].add(j)
                    adj[j].add(i)
        visited = {0}
        queue = [0]
        while queue:
            node = queue.pop(0)
            for nb in adj[node]:
                if nb not in visited:
                    visited.add(nb)
                    queue.append(nb)
        return len(visited) == n

    # --- filters ---

    def _quick_filter(self, combo: Combo, rules: dict) -> bool:
        if rules.get("eliminate_same_function_duplicate", True):
            locs = [(p["file"], p["function"], p.get("line_start")) for p in combo]
            if len(set(locs)) < len(combo):
                return False
        return True

    def _eliminate(self, combo: Combo, rules: dict) -> bool:
        if rules.get("min_categories", 2) > 1:
            cats = {p["category"] for p in combo}
            if len(cats) < rules["min_categories"]:
                # one-category combos only survive if explicitly allowed
                if not rules.get("allow_single_category", False):
                    return False

        if rules.get("require_shared_contract_or_call", True):
            contracts = {p.get("contract", "unknown") for p in combo}
            has_cross = any(
                _piece_type_suffix(p).startswith("D03") for p in combo
            )
            if len(contracts) > 1 and not has_cross:
                all_ids = {p["id"] for p in combo}
                has_dep = any(
                    dep in all_ids
                    for p in combo
                    for dep in p.get("depends_on", [])
                )
                if not has_dep:
                    return False

        if rules.get("eliminate_actor_conflict", True):
            actors = {p.get("actor", "any_user") for p in combo}
            bridge = self.cron_actor is not None and self.cron_actor in actors
            if not bridge:
                for pair in self.conflicting_actors:
                    if pair.issubset(actors):
                        return False

        if rules.get("require_interaction_link", True):
            if not self._combo_connected(combo):
                return False

        if rules.get("eliminate_redundant_same_direction_rounding", True):
            rounding = [
                p for p in combo if _piece_type_suffix(p) in self.rounding_types
            ]
            if len(rounding) == len(combo):
                dirs = {p.get("direction", "neutral") for p in rounding}
                if len(dirs) == 1 and "neutral" not in dirs:
                    return False

        if rules.get("eliminate_read_only_combos", True):
            if all(
                any(ind in p.get("call_context", "").lower() for ind in self.read_only_indicators)
                for p in combo
            ):
                return False

        if rules.get("eliminate_pure_defensive", True):
            if all(_piece_type_suffix(p) in self.defensive_types for p in combo):
                return False

        if rules.get("eliminate_no_state_overlap", True):
            state_counts: dict[str, int] = defaultdict(int)
            for p in combo:
                for st in p.get("state_touched", []):
                    state_counts[st] += 1
            overlap = any(v > 1 for v in state_counts.values())
            ctxs = {p.get("call_context", "") for p in combo}
            all_diff_ctx = len(ctxs) == len(combo) and "" not in ctxs
            all_ids = {p["id"] for p in combo}
            has_dep = any(dep in all_ids for p in combo for dep in p.get("depends_on", []))
            has_bridge = any(_piece_has_bridge(p, self.bridge_types) for p in combo)
            if not overlap and all_diff_ctx and not has_dep and not has_bridge:
                return False

        if rules.get("eliminate_all_neutral_same_context", True):
            all_neutral = all(p.get("direction", "neutral") == "neutral" for p in combo)
            no_econ = not any(p.get("category") == "E" for p in combo)
            no_oracle = not any(p.get("category") == "D" for p in combo)
            no_gap = not any(_piece_type_suffix(p) == self.arithmetic_gap_type for p in combo)
            no_unbounded = not any(_piece_type_suffix(p).startswith("C02") for p in combo)
            if all_neutral and no_econ and no_oracle and no_gap and no_unbounded:
                ctxs = {p.get("call_context", "") for p in combo}
                if len(ctxs) == 1:
                    return False

        if self.extra_eliminate is not None:
            if not self.extra_eliminate(combo):
                return False

        return True

    # --- scoring ---

    def _score(self, combo: Combo, weights: dict) -> float:
        s = 0.0
        cats = {p["category"] for p in combo}
        s += len(cats) * weights.get("category_diversity", 2.0)

        if any(p["category"] == "E" for p in combo):
            s += weights.get("has_economic_piece", 3.0)

        if any(_piece_type_suffix(p) in self.rounding_types for p in combo):
            s += weights.get("has_rounding_piece", 1.5)

        if any(p["category"] == "D" for p in combo):
            s += weights.get("has_oracle_piece", 2.0)

        dirs = {
            p.get("direction", "neutral")
            for p in combo
            if p.get("direction", "neutral") in NON_NEUTRAL_DIRECTIONS
        }
        if len(dirs) > 1:
            s += weights.get("mixed_direction", 2.5)

        state_counts: dict[str, int] = defaultdict(int)
        for p in combo:
            for st in p.get("state_touched", []):
                state_counts[st] += 1
        if any(v > 1 for v in state_counts.values()):
            s += weights.get("same_state_touched", 2.0)

        if all(_piece_type_suffix(p) != self.arithmetic_gap_type for p in combo):
            if any(p["category"] == "A" for p in combo):
                s -= weights.get("all_checked_arithmetic_penalty", 1.0)

        if self.extra_score is not None:
            s = self.extra_score(combo, s)

        return round(s, 2)

    # --- output ---

    def _build_entry(self, combo: Combo, score: float, combo_id: int) -> dict:
        return {
            "combo_id": f"COMBO-{combo_id:04d}",
            "score": score,
            "pieces": [p["id"] for p in combo],
            "piece_types": [p.get("type", "unknown") for p in combo],
            "categories": sorted({p["category"] for p in combo}),
            "directions": sorted({p.get("direction", "neutral") for p in combo}),
            "shared_state": sorted({
                st for p in combo for st in p.get("state_touched", [])
                if sum(1 for q in combo for s2 in q.get("state_touched", []) if s2 == st) > 1
            }),
            "locations": [f"{p['file']}:{p.get('line_start', '?')}" for p in combo],
            "descriptions": [p.get("description", "") for p in combo],
            "snippets": [p.get("snippet", "") for p in combo],
        }

    # --- run ---

    def run(self, argv: list[str] | None = None) -> None:
        argv = argv if argv is not None else sys.argv[1:]
        if len(argv) < 3:
            script = f"combine_{self.language}.py"
            print(f"Usage: python3 {script} <pieces.json> <k> <output.json> [--top N]")
            sys.exit(1)

        pieces_path, k_str, output_path, *rest = argv
        k = int(k_str)
        top_n = DEFAULT_TOP_N.get(k, 100)
        if "--top" in rest:
            idx = rest.index("--top")
            top_n = int(rest[idx + 1])

        pieces = load_pieces(pieces_path)
        base_dir = os.path.dirname(os.path.abspath(__file__))
        rules, weights = load_config(self.language, base_dir)

        total = 0
        quick_filtered = 0
        eliminated = 0
        survivors: list[tuple[Combo, float]] = []

        for combo in combinations(pieces, k):
            total += 1
            if not self._quick_filter(combo, rules):
                quick_filtered += 1
                continue
            if not self._eliminate(combo, rules):
                eliminated += 1
                continue
            survivors.append((combo, self._score(combo, weights)))

        survivors.sort(key=lambda x: x[1], reverse=True)
        top = survivors[:top_n]

        metadata = {
            "language": self.language,
            "total_pieces": len(pieces),
            "k": k,
            "total_combinations": total,
            "quick_filtered": quick_filtered,
            "eliminated": eliminated,
            "survivors": len(survivors),
            "top_n": len(top),
            "elimination_rate": round(
                (quick_filtered + eliminated) / max(total, 1) * 100, 1
            ),
        }
        if self.post_metadata is not None:
            self.post_metadata(metadata, survivors)

        output = {
            "metadata": metadata,
            "combinations": [
                self._build_entry(combo, score, i + 1)
                for i, (combo, score) in enumerate(top)
            ],
        }

        # Atomic write.
        dirpath = os.path.dirname(os.path.abspath(output_path)) or "."
        with tempfile.NamedTemporaryFile(
            mode="w", dir=dirpath, prefix=".nextup_tmp_", suffix=".json", delete=False
        ) as tmp:
            json.dump(output, tmp, indent=2)
            tmp_name = tmp.name
        os.replace(tmp_name, output_path)

        print(f"NEXTUP Combinator Results ({self.language}, k={k})")
        print(f"  Pieces:         {metadata['total_pieces']}")
        print(f"  Combinations:   {metadata['total_combinations']}")
        print(f"  Quick-filtered: {metadata['quick_filtered']}")
        print(f"  Eliminated:     {metadata['eliminated']}")
        print(f"  Survivors:      {metadata['survivors']}")
        print(f"  Top-N output:   {metadata['top_n']}")
        print(f"  Elimination:    {metadata['elimination_rate']}%")
        if top:
            print(f"  Top score:      {top[0][1]}")
            print(f"  Bottom score:   {top[-1][1]}")
