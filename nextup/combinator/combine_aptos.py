"""
NEXTUP Aptos-Move combinator (v1.1).

Wraps `shared.Combinator` with Aptos-native vocabulary and hook predicates:

  * DEFENSIVE_TYPES: suffix-only ids whose sole role is a guard / assertion.
  * BRIDGE_TYPES: suffix-only ids that cross module / capability / entry
    boundaries -- chains with at least one bridge survive APT-R1-style
    connectivity filtering.
  * CONFLICTING_ACTORS: aptos design-doc section 5 pairs.
  * CRON_ACTOR: Aptos has no native cron / keeper primitive.

`extra_eliminate` encodes APT-R1 through APT-R6 from aptos_design.md section 6.
`extra_score` layers category boosts (J/K/L/M/N), the Section-4 bridge +
J/N bonus, and the design-specific "drop-missing + loss-path" pattern.
"""

from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from shared import Combinator, _piece_type_suffix, _piece_has_bridge  # noqa: E402


LANGUAGE = "aptos"

# Rounding suffix ids (shared.py matches on suffix when filtering rounding combos).
ROUNDING_TYPES = {"A01", "A02", "A03"}

# Pieces whose role is purely defensive / validating. A combo of nothing but
# defensive pieces has no exploit surface and is eliminated by
# `eliminate_pure_defensive` (shared.py).
DEFENSIVE_TYPES = {
    "B01",  # SIGNER_GATED
    "B04",  # INIT_MODULE_PATH
    "B05",  # PAUSE_GATE
    "E04",  # SLIPPAGE_PROTECTION
    "E08",  # MINIMUM_SIZE_CHECK
    "G01",  # FUND_VERIFICATION
    "I01",  # INVARIANT_PRESERVATION
    "I02",  # BALANCE_ACCOUNTING
}

# Bridge pieces (design-doc section 4). SUFFIX only -- shared.py tolerates
# either suffix or full prefixed id.
BRIDGE_TYPES = {
    "M01",  # UNSAFE_PUBLIC_ENTRY     -- external tx -> internal logic
    "M02",  # INTERNAL_VIA_ENTRY
    "N01",  # DISPATCHABLE_REENTRY    -- forward-call / back-call half
    "N02",  # CLOSURE_CALLBACK_REENTRY
    "N04",  # TRANSITIVE_CALL_CYCLE
    "K02",  # CAPABILITY_LEAK_VIA_RETURN
    "K05",  # SIGNER_CAP_AUTH_GAP
    "L01",  # METADATA_NOT_VALIDATED  -- FA cross-module
    "L02",  # PRIMARY_STORE_DIRECT_WITHDRAW
    "L04",  # SPONSOR_FEE_BYPASS
    "D03",  # CROSS_MODULE_CALL
}

# Design-doc section 5 actor conflict pairs.
CONFLICTING_ACTORS = [
    ("signer", "non_signer_impersonator"),
    ("governance", "module_publisher"),
    ("cap_holder", "signer"),
    ("delegate", "cap_holder"),
    ("framework", "module_publisher"),
]

# Aptos has no native cron / keeper primitive -- off-chain keepers just call
# `public entry`. No bridge actor to exempt from conflict elimination.
CRON_ACTOR = None


# --- suffix sets used by extra_eliminate / extra_score ---

CATEGORY_J_SUFFIX_PREFIX = "J"
CATEGORY_K_SUFFIX_PREFIX = "K"
CATEGORY_L_SUFFIX_PREFIX = "L"
CATEGORY_M_SUFFIX_PREFIX = "M"
CATEGORY_N_SUFFIX_PREFIX = "N"

# Capability / ref suffixes used by APT-R6.
CAPABILITY_SUFFIXES = {"K02", "K05"}

# Suffixes that denote a `public entry` or mutating-public piece.
ENTRY_MUTATE_SUFFIXES = {"M01", "M02", "M04", "B03"}

# View-mutates escape hatch for APT-R2.
VIEW_MUTATES_SUFFIX = "M03"

# Ability-mismatch suffixes used by APT-R5.
COPY_ON_VALUE_SUFFIX = "J01"
DROP_ON_OBLIGATION_SUFFIX = "J02"

# "Loss-path" suffixes for the drop-missing + loss-path bonus (design-doc
# weight hint). A chain that combines APT-J02 (silent drop of obligation)
# with any path that loses value is uniquely Aptos-severe.
LOSS_PATH_SUFFIXES = {
    "A01",  # ROUNDING_FLOOR
    "A04",  # PRECISION_TRUNCATION
    "G04",  # DUST_ACCUMULATION
    "L04",  # SPONSOR_FEE_BYPASS
    "E03",  # FEE_COMPUTATION
}


def _suffixes(combo) -> list[str]:
    return [_piece_type_suffix(p) for p in combo]


def _categories(combo) -> set[str]:
    return {p.get("category", "") for p in combo}


def _contracts(combo) -> set[str]:
    return {p.get("contract", "") for p in combo}


def _state_set(combo) -> set[str]:
    s: set[str] = set()
    for p in combo:
        for st in p.get("state_touched", []):
            s.add(st)
    return s


def _shared_state(combo) -> set[str]:
    from collections import Counter

    c: Counter[str] = Counter()
    for p in combo:
        for st in p.get("state_touched", []):
            c[st] += 1
    return {st for st, n in c.items() if n > 1}


# ---- APT-R1 ... APT-R6 ----

def _r1_same_module_disjoint_resources(combo) -> bool:
    """Keep unless every piece is in the same module AND touches a resource-
    disjoint state set AND no capability-bearing piece is present."""
    contracts = _contracts(combo)
    if len(contracts) != 1 or "" in contracts:
        return True
    if _shared_state(combo):
        return True
    # Any depends_on link between pieces keeps the chain alive.
    all_ids = {p["id"] for p in combo}
    if any(dep in all_ids for p in combo for dep in p.get("depends_on", [])):
        return True
    # Capability-bearing piece implies information flow beyond resources.
    if any(_piece_type_suffix(p) in CAPABILITY_SUFFIXES for p in combo):
        return True
    return False


def _r2_all_view_no_entry(combo) -> bool:
    """Keep unless every piece is `#[view]` and no mutating / entry piece is
    present. APT-M03 VIEW_MUTATES is itself the finding and bypasses."""
    suffixes = _suffixes(combo)
    if VIEW_MUTATES_SUFFIX in suffixes:
        return True
    is_view = [
        "view" in (p.get("call_context", "") or "").lower()
        or "#[view]" in (p.get("snippet", "") or "")
        for p in combo
    ]
    if not all(is_view):
        return True
    # All view AND no entry/mutating suffix -> drop.
    if any(s in ENTRY_MUTATE_SUFFIXES for s in suffixes):
        return True
    return False


def _r4_upgrade_policy_immutable(combo) -> bool:
    """Drop if any piece declares `upgrade_policy::immutable` in its snippet
    AND the chain requires upgrade-driven behavior change (heuristic: another
    piece references `upgrade` / `publish_package`)."""
    immutable = False
    upgrade_dep = False
    for p in combo:
        snip = (p.get("snippet", "") or "").lower()
        if "upgrade_policy::immutable" in snip or "upgrade_policy=immutable" in snip:
            immutable = True
        if "publish_package" in snip or "upgrade_package" in snip or "code::publish" in snip:
            upgrade_dep = True
    if immutable and upgrade_dep:
        return False
    return True


def extra_eliminate(combo) -> bool:
    """Return True to KEEP, False to drop. Runs AFTER shared.py default rules."""
    if not _r1_same_module_disjoint_resources(combo):
        return False
    if not _r2_all_view_no_entry(combo):
        return False
    if not _r4_upgrade_policy_immutable(combo):
        return False
    return True


# ---- scoring bonuses ----

def extra_score(combo, base: float) -> float:
    s = float(base)
    suffixes = _suffixes(combo)
    cats = _categories(combo)

    # Category multipliers (design-doc section 7). Applied additively as
    # bonuses to `base`, scaled by `(multiplier - 1.0) * base_slice`, where
    # `base_slice` is a proxy equal to category_diversity weight (2.0) so the
    # bonus is non-trivial but does not double the score.
    #
    # We implement this as explicit additive bonuses defined in
    # weights/aptos.json extras, which is both simpler and keeps the combinator
    # deterministic under score-weight tuning.
    #
    # The orchestrator reads `extras` from weights. shared.py does not pass
    # weights into `extra_score`, so we recover them via closure.
    w = _weights_cache["extras"] if _weights_cache else {}

    if "J" in cats:
        s += float(w.get("category_j_abilities_boost", 1.5))
    if "K" in cats:
        s += float(w.get("category_k_resources_boost", 1.4))
    if "L" in cats:
        s += float(w.get("category_l_fungible_asset_boost", 1.3))
    if "N" in cats:
        s += float(w.get("category_n_reentrancy_boost", 1.3))
    if "M" in cats:
        s += float(w.get("category_m_entry_boost", 1.1))

    # Oracle Pyth / Switchboard emphasis (R16).
    oracle_markers = ("pyth", "switchboard")
    if any(
        p.get("category") == "D"
        and any(m in (p.get("snippet", "") + " " + " ".join(p.get("state_touched", []))).lower()
                for m in oracle_markers)
        for p in combo
    ):
        s += float(w.get("oracle_pyth_switchboard_boost", 1.2))

    # Section-4 bridge + J/N piece -> +0.2x bump.
    has_bridge = any(_piece_has_bridge(p, set(BRIDGE_TYPES)) for p in combo)
    has_jn = any(s0.startswith(CATEGORY_J_SUFFIX_PREFIX) or s0.startswith(CATEGORY_N_SUFFIX_PREFIX)
                 for s0 in suffixes)
    if has_bridge and has_jn:
        s += float(w.get("bridge_plus_j_or_n_bonus", 0.2))

    # Drop-missing + loss-path (design-doc hint).
    if DROP_ON_OBLIGATION_SUFFIX in suffixes and any(sx in LOSS_PATH_SUFFIXES for sx in suffixes):
        s += float(w.get("drop_missing_plus_loss_path_bonus", 2.5))

    # SignerCapability leak / auth-gap paired with an entry piece.
    if ("K05" in suffixes or "K02" in suffixes) and any(sx in ENTRY_MUTATE_SUFFIXES for sx in suffixes):
        s += float(w.get("signer_cap_plus_entry_bonus", 2.0))

    # Capability leak paired with a signer gate -- shows the leak circumvents
    # the gate.
    if "K02" in suffixes and "B01" in suffixes:
        s += float(w.get("capability_leak_plus_signer_gate_bonus", 2.0))

    # FA metadata-not-validated combined with a dispatchable call path.
    if "L01" in suffixes and ("N01" in suffixes or "L02" in suffixes or "L04" in suffixes):
        s += float(w.get("metadata_missing_plus_dispatchable_bonus", 2.0))

    # Reentrancy piece alongside same-state mutation.
    if any(sx.startswith(CATEGORY_N_SUFFIX_PREFIX) for sx in suffixes) and _shared_state(combo):
        s += float(w.get("reentrancy_plus_state_mutation_bonus", 2.5))

    return round(s, 2)


# shared.Combinator does not pass weights to extra_score; stash via hook.
_weights_cache: dict = {}


def _post_metadata(metadata: dict, survivors) -> None:
    metadata["bridge_types"] = sorted(BRIDGE_TYPES)
    metadata["defensive_types"] = sorted(DEFENSIVE_TYPES)
    metadata["conflicting_actor_pairs"] = [list(pair) for pair in CONFLICTING_ACTORS]


def _build_combinator() -> Combinator:
    return Combinator(
        language=LANGUAGE,
        rounding_types=ROUNDING_TYPES,
        defensive_types=DEFENSIVE_TYPES,
        bridge_types=BRIDGE_TYPES,
        conflicting_actors=CONFLICTING_ACTORS,
        read_only_indicators=("view", "query", "simulate", "pure"),
        cron_actor=CRON_ACTOR,
        arithmetic_gap_type="A06",
        extra_eliminate=extra_eliminate,
        extra_score=extra_score,
        post_metadata=_post_metadata,
    )


def main(argv: list[str] | None = None) -> None:
    # Pre-load weights so extra_score can read the extras block.
    from shared import load_config

    base_dir = os.path.dirname(os.path.abspath(__file__))
    _rules, weights = load_config(LANGUAGE, base_dir)
    _weights_cache.clear()
    _weights_cache["extras"] = weights.get("extras", {}) or {}

    combinator = _build_combinator()
    combinator.run(argv)


if __name__ == "__main__":
    main()
