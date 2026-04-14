#!/usr/bin/env python3
"""
NEXTUP Combinator - Zero-token combination engine.
Generates, eliminates, scores, and ranks puzzle piece combinations.

Usage: python3 combine.py <pieces.json> <k=2|3|4> <output.json> [--top N]
"""

import json
import sys
from itertools import combinations
from collections import defaultdict


def load_pieces(path: str) -> list[dict]:
    with open(path) as f:
        return json.load(f)


def load_config(base_dir: str) -> tuple[dict, dict]:
    """Load elimination rules and scoring weights from config files."""
    try:
        with open(f"{base_dir}/elimination_rules.json") as f:
            rules = json.load(f)
    except FileNotFoundError:
        rules = DEFAULT_RULES
    try:
        with open(f"{base_dir}/scoring_weights.json") as f:
            weights = json.load(f)
    except FileNotFoundError:
        weights = DEFAULT_WEIGHTS
    return rules, weights


DEFAULT_RULES = {
    "min_categories": 2,
    "require_shared_contract_or_call": True,
    "require_interaction_link": True,
    "eliminate_actor_conflict": True,
    "cron_bridges_actors": True,
    "eliminate_redundant_same_direction_rounding": True,
    "eliminate_same_function_duplicate": True,
    "eliminate_read_only_combos": True,
    "eliminate_triple_protected": True,
    "eliminate_pure_defensive": True,
    "eliminate_no_state_overlap": True,
    "eliminate_all_neutral_same_context": True
}

DEFAULT_WEIGHTS = {
    "category_diversity": 2.0,
    "has_economic_piece": 3.0,
    "has_rounding_piece": 1.5,
    "has_oracle_piece": 2.0,
    "mixed_direction": 2.5,
    "same_state_touched": 2.0,
    "all_checked_arithmetic_penalty": 1.0
}

# Categories that indicate read-only context
READ_ONLY_INDICATORS = {"query", "view", "simulate"}

# Actor conflict pairs
CONFLICTING_ACTORS = {
    frozenset({"owner", "any_user"}),
    frozenset({"owner", "non_owner"}),
}

# Rounding types
ROUNDING_TYPES = {"A01", "A02", "A03"}

# Purely defensive piece types (protect, validate, gate -- don't create attack surface alone)
DEFENSIVE_TYPES = {"B01", "B02", "B04", "B05", "G01", "I01", "I02", "C06", "E04", "E08"}

# Bridge types that connect otherwise separate pieces (cron, multi-hop, callbacks)
BRIDGE_TYPES = {"F01", "F03", "F04"}


def quick_filter(combo: tuple[dict], rules: dict) -> bool:
    """Fast inline filter during combination generation. Returns True if combo passes."""
    categories = set(p["category"] for p in combo)

    # E5: Same-function duplicate
    if rules.get("eliminate_same_function_duplicate", True):
        locations = [(p["file"], p["function"], p.get("line_start")) for p in combo]
        if len(set(locations)) < len(combo):
            return False

    return True


def pieces_are_linked(a: dict, b: dict) -> bool:
    """Check if two individual pieces have a direct interaction link."""

    # 1. Shared state variable
    a_state = set(a.get("state_touched", []))
    b_state = set(b.get("state_touched", []))
    if a_state & b_state:
        return True

    # 2. Explicit dependency
    if a["id"] in b.get("depends_on", []) or b["id"] in a.get("depends_on", []):
        return True

    # 3. Same call context (same user action reaches both)
    a_ctx = a.get("call_context", "")
    b_ctx = b.get("call_context", "")
    if a_ctx and b_ctx and a_ctx == b_ctx:
        return True

    # 4. One is a bridge type (cron/multi-hop/callback connects everything in its scope)
    bridge_prefixes = {t[:3] for t in BRIDGE_TYPES}
    a_is_bridge = a.get("type", "")[:3] in bridge_prefixes
    b_is_bridge = b.get("type", "")[:3] in bridge_prefixes
    if a_is_bridge or b_is_bridge:
        # Bridge connects if they're in the same contract
        if a.get("contract") == b.get("contract"):
            return True

    # 5. Same function (very strong link -- same code path)
    if (a.get("file") == b.get("file") and
        a.get("function") == b.get("function") and
        a.get("function")):
        return True

    return False


def combo_is_connected(combo: tuple[dict]) -> bool:
    """Check that all pieces form a connected graph through pairwise interaction links.

    For k=2: just checks if the pair is linked.
    For k=3+: builds adjacency graph and checks full connectivity via BFS.
    Every piece must be reachable from every other piece.
    """
    n = len(combo)
    if n <= 1:
        return True

    # Build adjacency list
    adj = defaultdict(set)
    for i in range(n):
        for j in range(i + 1, n):
            if pieces_are_linked(combo[i], combo[j]):
                adj[i].add(j)
                adj[j].add(i)

    # BFS from node 0
    visited = {0}
    queue = [0]
    while queue:
        node = queue.pop(0)
        for neighbor in adj[node]:
            if neighbor not in visited:
                visited.add(neighbor)
                queue.append(neighbor)

    return len(visited) == n


def eliminate(combo: tuple[dict], rules: dict) -> bool:
    """Apply elimination rules. Returns True if combo should be KEPT."""

    # E1: Contract isolation (multi-contract codebases)
    if rules.get("require_shared_contract_or_call", True):
        contracts = set(p.get("contract", "unknown") for p in combo)
        has_cross_call = any(p.get("type", "").startswith("D03") or
                           p.get("type") == "D03_CROSS_CONTRACT_CALL"
                           for p in combo)
        if len(contracts) > 1 and not has_cross_call:
            all_ids = set(p["id"] for p in combo)
            has_dep_link = any(
                dep in all_ids
                for p in combo
                for dep in p.get("depends_on", [])
            )
            if not has_dep_link:
                return False

    # E2: Actor conflict
    if rules.get("eliminate_actor_conflict", True):
        actors = set(p.get("actor", "any_user") for p in combo)
        has_cron = "cron" in actors
        bridge = rules.get("cron_bridges_actors", True) and has_cron

        if not bridge:
            for conflict_pair in CONFLICTING_ACTORS:
                if conflict_pair.issubset(actors):
                    return False

    # E3: Connectivity check (THE KEY RULE)
    # ALL pieces must form a connected graph through pairwise interaction links.
    # For k=2: the pair must be directly linked.
    # For k=3+: every piece must be reachable from every other through links.
    # This prevents "A links to B, but C is totally unrelated" from surviving.
    if rules.get("require_interaction_link", True):
        if not combo_is_connected(combo):
            return False

    # E4: Redundant same-direction rounding
    if rules.get("eliminate_redundant_same_direction_rounding", True):
        rounding_pieces = [p for p in combo if p.get("type", "")[:3] in {"A01", "A02"}]
        if len(rounding_pieces) == len(combo):
            directions = set(p.get("direction", "neutral") for p in rounding_pieces)
            if len(directions) == 1 and "neutral" not in directions:
                return False

    # E6: Read-only irrelevance
    if rules.get("eliminate_read_only_combos", True):
        all_read_only = all(
            any(ind in p.get("call_context", "").lower() for ind in READ_ONLY_INDICATORS)
            for p in combo
        )
        if all_read_only:
            return False

    # E7: Triple-protected path
    if rules.get("eliminate_triple_protected", True):
        protection_types = {"B01", "B05"}
        arithmetic_types = {"A06"}
        all_have_checked = all(
            p.get("type", "")[:3] not in arithmetic_types
            for p in combo
        )
        has_access_control = any(p.get("type", "")[:3] in protection_types for p in combo)
        has_pause = any(p.get("type", "")[:3] == "B05" for p in combo)

        if all_have_checked and has_access_control and has_pause and len(combo) <= 3:
            return False

    # E8: Pure defensive combo
    # If ALL pieces are purely defensive (access control, validation, slippage, invariant checks),
    # there's no attack surface to combine.
    if rules.get("eliminate_pure_defensive", True):
        all_defensive = all(
            p.get("type", "")[:3] in {t[:3] for t in DEFENSIVE_TYPES}
            for p in combo
        )
        if all_defensive:
            return False

    # E9: No state overlap + different call contexts + no dependency
    # Stricter than E3: pieces in the same file but touching completely different state
    # with different entry points and no dependency are very unlikely to interact.
    if rules.get("eliminate_no_state_overlap", True):
        state_counts = defaultdict(int)
        for p in combo:
            for st in p.get("state_touched", []):
                state_counts[st] += 1
        has_state_overlap = any(v > 1 for v in state_counts.values())

        contexts = set(p.get("call_context", "") for p in combo)
        all_different_contexts = len(contexts) == len(combo) and "" not in contexts

        all_ids = set(p["id"] for p in combo)
        has_dep = any(dep in all_ids for p in combo for dep in p.get("depends_on", []))

        has_bridge = any(p.get("type", "")[:3] in {t[:3] for t in BRIDGE_TYPES} for p in combo)

        if not has_state_overlap and all_different_contexts and not has_dep and not has_bridge:
            # No shared state, different entry points, no deps, no bridge → eliminate
            return False

    # E10: All neutral direction, same call context, no economic piece
    # Neutral + neutral in the same flow with no economic impact is boring.
    if rules.get("eliminate_all_neutral_same_context", True):
        all_neutral = all(p.get("direction", "neutral") == "neutral" for p in combo)
        no_economic = not any(p["category"] == "E" for p in combo)
        no_oracle = not any(p["category"] == "D" for p in combo)
        no_arithmetic_gap = not any(p.get("type", "")[:3] == "A06" for p in combo)
        no_unbounded = not any(p.get("type", "")[:3] == "C02" for p in combo)

        if all_neutral and no_economic and no_oracle and no_arithmetic_gap and no_unbounded:
            # All neutral, no economic/oracle/gap/unbounded → likely uninteresting
            contexts = set(p.get("call_context", "") for p in combo)
            if len(contexts) == 1:
                return False

    return True


def score(combo: tuple[dict], weights: dict) -> float:
    """Score a combination for prioritization. Higher = more interesting."""
    s = 0.0

    categories = set(p["category"] for p in combo)
    s += len(categories) * weights.get("category_diversity", 2.0)

    if any(p["category"] == "E" for p in combo):
        s += weights.get("has_economic_piece", 3.0)

    if any(p.get("type", "")[:3] in ROUNDING_TYPES for p in combo):
        s += weights.get("has_rounding_piece", 1.5)

    if any(p["category"] == "D" for p in combo):
        s += weights.get("has_oracle_piece", 2.0)

    # Mixed direction
    directions = set(p.get("direction", "neutral") for p in combo if p.get("direction") != "neutral")
    if len(directions) > 1:
        s += weights.get("mixed_direction", 2.5)

    # Same state touched (pieces that interact on the same state variable)
    all_state = defaultdict(int)
    for p in combo:
        for st in p.get("state_touched", []):
            all_state[st] += 1
    if any(v > 1 for v in all_state.values()):
        s += weights.get("same_state_touched", 2.0)

    # Penalty: all checked arithmetic (no gaps)
    if all(p.get("type", "")[:3] != "A06" for p in combo):
        has_arithmetic = any(p["category"] == "A" for p in combo)
        if has_arithmetic:
            s -= weights.get("all_checked_arithmetic_penalty", 1.0)

    return round(s, 2)


def build_combo_entry(combo: tuple[dict], combo_score: float, combo_id: int) -> dict:
    """Build a JSON-serializable combo entry."""
    return {
        "combo_id": f"COMBO-{combo_id:04d}",
        "score": combo_score,
        "pieces": [p["id"] for p in combo],
        "piece_types": [p.get("type", "unknown") for p in combo],
        "categories": sorted(set(p["category"] for p in combo)),
        "directions": sorted(set(p.get("direction", "neutral") for p in combo)),
        "shared_state": sorted(set(
            st for p in combo for st in p.get("state_touched", [])
            if sum(1 for p2 in combo for s2 in p2.get("state_touched", []) if s2 == st) > 1
        )),
        "locations": [f"{p['file']}:{p.get('line_start', '?')}" for p in combo],
        "descriptions": [p.get("description", "") for p in combo],
        "snippets": [p.get("snippet", "") for p in combo]
    }


def main():
    if len(sys.argv) < 4:
        print("Usage: python3 combine.py <pieces.json> <k=2|3|4> <output.json> [--top N]")
        sys.exit(1)

    pieces_path = sys.argv[1]
    k = int(sys.argv[2])
    output_path = sys.argv[3]

    # Parse optional --top N
    top_n = {2: 50, 3: 100, 4: 150}.get(k, 100)  # defaults per mode
    if "--top" in sys.argv:
        top_idx = sys.argv.index("--top")
        if top_idx + 1 < len(sys.argv):
            top_n = int(sys.argv[top_idx + 1])

    # Load
    pieces = load_pieces(pieces_path)
    import os
    base_dir = os.path.dirname(os.path.abspath(__file__))
    rules, weights = load_config(base_dir)

    # Stats
    total_generated = 0
    quick_filtered = 0
    eliminated = 0
    survivors = []

    # Generate + filter + eliminate + score
    for combo in combinations(pieces, k):
        total_generated += 1

        if not quick_filter(combo, rules):
            quick_filtered += 1
            continue

        if not eliminate(combo, rules):
            eliminated += 1
            continue

        combo_score = score(combo, weights)
        survivors.append((combo, combo_score))

    # Sort by score descending
    survivors.sort(key=lambda x: x[1], reverse=True)

    # Take top N
    top_combos = survivors[:top_n]

    # Build output
    output = {
        "metadata": {
            "total_pieces": len(pieces),
            "k": k,
            "total_combinations": total_generated,
            "quick_filtered": quick_filtered,
            "eliminated": eliminated,
            "survivors": len(survivors),
            "top_n": len(top_combos),
            "elimination_rate": round((quick_filtered + eliminated) / max(total_generated, 1) * 100, 1)
        },
        "combinations": [
            build_combo_entry(combo, combo_score, i + 1)
            for i, (combo, combo_score) in enumerate(top_combos)
        ]
    }

    with open(output_path, "w") as f:
        json.dump(output, f, indent=2)

    # Print stats
    meta = output["metadata"]
    print(f"NEXTUP Combinator Results (k={k})")
    print(f"  Pieces:        {meta['total_pieces']}")
    print(f"  Combinations:  {meta['total_combinations']}")
    print(f"  Quick-filtered: {meta['quick_filtered']}")
    print(f"  Eliminated:    {meta['eliminated']}")
    print(f"  Survivors:     {meta['survivors']}")
    print(f"  Top-N output:  {meta['top_n']}")
    print(f"  Elimination:   {meta['elimination_rate']}%")
    if top_combos:
        print(f"  Top score:     {top_combos[0][1]}")
        print(f"  Bottom score:  {top_combos[-1][1]}")


if __name__ == "__main__":
    main()
