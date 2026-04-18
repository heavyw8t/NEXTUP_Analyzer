#!/usr/bin/env python3
"""
NEXTUP Solana combinator.

Language-specific vocabulary and rules for Solana puzzle-piece combinations.
Delegates BFS connectivity, scoring skeleton, CLI, and atomic write to
`shared.Combinator`. Implements Solana-specific elimination and scoring
hooks covering account-topology, PDA, CPI, sysvar, Token-2022, and
lamport/rent concerns as defined in the Solana taxonomy design doc.

CLI: python3 combine_solana.py <pieces.json> <k> <output.json> [--top N]
"""

from __future__ import annotations

import os
import sys
from typing import Iterable

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from shared import Combinator, _piece_type_suffix, load_config  # noqa: E402


LANGUAGE = "solana"

# Rounding suffixes (A01 floor, A02 ceil, A03 mixed).
ROUNDING_TYPES = {"A01", "A02", "A03"}

# Purely defensive suffixes. A combo of only-defensive pieces has no attack
# surface to exploit. Chosen per design doc section 7 + typical_direction
# flags; these are pieces that validate, gate, or assert rather than create
# attack surface.
DEFENSIVE_TYPES = {
    "B01",  # SIGNER_AUTHORITY (access gate)
    "B04",  # GENESIS_BYPASS (one-shot init gate)
    "B05",  # PAUSE_GATE
    "C06",  # COLLECT_THEN_ITERATE (snapshot-before-mutate)
    "E04",  # SLIPPAGE_PROTECTION
    "E08",  # MINIMUM_SIZE_CHECK
    "G01",  # FUND_VERIFICATION
    "I01",  # INVARIANT_PRESERVATION
    "I02",  # BALANCE_ACCOUNTING
}

# Bridge suffixes per design doc section 4. CPI family (L01,L05,L06,L07),
# canonical CPI (D03), shared sysvar read (N03), account aliasing (J04),
# and PDA family (K01,K02,K05).
BRIDGE_TYPES = {
    "D03",  # CPI
    "J04",  # ACCOUNT_ALIASING
    "K01",  # UNCHECKED_PDA_DERIVATION
    "K02",  # SEED_COLLISION
    "K05",  # PDA_AUTHORITY_LEAK
    "L01",  # CPI_TARGET_UNCHECKED
    "L05",  # ACCOUNT_RELOAD_MISSING
    "L06",  # ARBITRARY_CPI
    "L07",  # CPI_OWNER_CHANGE
    "N03",  # SYSVAR_SHARED_READ
}

# Conflicting actor pairs per design doc section 5. `eliminate_actor_conflict`
# is loosened to false in rules/solana.json because Solana's capability model
# collapses most EVM-style conflicts into the one narrow is_signer invariant,
# which we express via the SOL-R4 coherence rule in `extra_eliminate`.
CONFLICTING_ACTORS = [
    ("signer", "non_signer"),
    ("pda", "signer"),
    ("upgrade_authority", "non_upgrade_authority"),
    ("mint_authority", "token_authority"),
]

# Solana has no native cron. Permissionless crank is just a signer and does
# NOT bridge actor conflicts the way EVM cron does.
CRON_ACTOR = None

# Read-only markers for Solana call contexts.
READ_ONLY_INDICATORS = ("view", "query", "simulate", "pure", "read_only", "get_")

# Token-2022 extension pairs that are mutually exclusive on one mint.
TOKEN22_INCOMPATIBLE_PAIRS = [
    ("O08", "O10"),  # NonTransferable + PermanentDelegate
    ("O08", "O09"),  # NonTransferable + ConfidentialTransfer
    ("O08", "O13"),  # NonTransferable + CpiGuard (irrelevant pairing)
]

# Compute-unit cost model (rule-of-thumb per design doc SOL-R5). Per-tx
# cap is 1.4M CU.
CU_TX_CAP = 1_400_000
CU_CPI_PIECE = 5_000
CU_PDA_DERIVE = 1_500
CU_PER_ACCOUNT = 100
CU_TOKEN22_HOOK = 50_000

# CPI-depth runtime limit.
CPI_DEPTH_LIMIT = 4


def _suffixes(combo) -> list[str]:
    return [_piece_type_suffix(p) for p in combo]


def _has_category(combo, letter: str) -> bool:
    return any(p.get("category") == letter for p in combo)


def _has_suffix(combo, suffixes: Iterable[str]) -> bool:
    sufs = set(suffixes)
    return any(_piece_type_suffix(p) in sufs for p in combo)


def _pieces_share_context(a: dict, b: dict) -> bool:
    """Return True if two pieces occupy the same instruction or program."""
    ctx_a = a.get("call_context", "")
    ctx_b = b.get("call_context", "")
    if ctx_a and ctx_b and ctx_a == ctx_b:
        return True
    if a.get("contract") and a.get("contract") == b.get("contract"):
        return True
    return False


def _estimate_cu(combo) -> int:
    total = 0
    for p in combo:
        suf = _piece_type_suffix(p)
        cat = p.get("category")
        # Each CPI-like piece adds a full CPI cost.
        if cat == "L" or suf == "D03":
            total += CU_CPI_PIECE
        # Each PDA derivation piece adds SHA256-keyed derivation cost.
        if cat == "K":
            total += CU_PDA_DERIVE
        # TransferHook adds substantial CU.
        if suf == "O03":
            total += CU_TOKEN22_HOOK
        # Per-account access (approximate by state_touched count).
        total += CU_PER_ACCOUNT * max(1, len(p.get("state_touched", [])))
    return total


def _count_cpi_depth(combo) -> int:
    # Each CPI-family piece in the combo adds one depth step.
    return sum(
        1
        for p in combo
        if p.get("category") == "L" or _piece_type_suffix(p) == "D03"
    )


# ---------- extra_eliminate ----------


def extra_eliminate(combo) -> bool:
    """Return True to KEEP, False to DROP.

    Implements the Solana-specific SOL-R* rules beyond the shared library.
    """
    suffixes = _suffixes(combo)
    categories = [p.get("category", "") for p in combo]

    # SOL-R1 ACCOUNT_OVERLAP_REQUIREMENT: connectivity on Solana is via
    # shared accounts, CPI, shared PDA, or shared sysvar. Eliminate if
    # none of those are present.
    state_sets = [set(p.get("state_touched", [])) for p in combo]
    any_overlap = False
    for i in range(len(state_sets)):
        for j in range(i + 1, len(state_sets)):
            if state_sets[i] & state_sets[j]:
                any_overlap = True
                break
        if any_overlap:
            break
    has_cpi = any(c == "L" for c in categories) or "D03" in suffixes
    has_pda = any(c == "K" for c in categories)
    has_shared_sysvar = "N03" in suffixes
    if not (any_overlap or has_cpi or has_pda or has_shared_sysvar):
        return False

    # SOL-R2 ALL_QUERY_ELIMINATION: every piece is read-only (no state
    # mutation, no CPI, no lamport arithmetic, no token flow, no oracle
    # mutation). Solana programs manifest impact only through account
    # mutation.
    def _is_query_piece(p: dict) -> bool:
        ctx = p.get("call_context", "").lower()
        if any(ind in ctx for ind in READ_ONLY_INDICATORS):
            return True
        suf = _piece_type_suffix(p)
        # D04 account state read and D01 oracle price dep are read-only by
        # construction unless paired with a mutating piece.
        return suf in {"D04", "D01"}

    has_cpi_piece = has_cpi
    has_lamport_piece = any(c == "M" for c in categories)
    has_token_flow = any(c == "G" for c in categories) or any(
        c == "O" for c in categories
    )
    has_mutation = any(
        c in {"C", "E", "J", "K", "M", "G", "O"} for c in categories
    )
    if (
        all(_is_query_piece(p) for p in combo)
        and not has_cpi_piece
        and not has_lamport_piece
        and not has_token_flow
        and not has_mutation
    ):
        return False

    # SOL-R4 SIGNER_REQUIREMENT_COHERENCE: if one piece is `signer` but
    # every state-mutating piece acts on accounts whose authority is
    # `non_signer`, the signer is incidental and cannot be chained into
    # the mutation.
    actors = [p.get("actor", "") for p in combo]
    mutating_cats = {"C", "E", "J", "K", "M", "G", "O"}
    mutating_pieces = [
        p for p in combo if p.get("category", "") in mutating_cats
    ]
    if (
        "signer" in actors
        and mutating_pieces
        and all(p.get("actor", "") == "non_signer" for p in mutating_pieces)
    ):
        return False

    # SOL-R5 CU_BUDGET_FEASIBILITY: sequential CU budget must fit in one
    # transaction (1.4M). Cross-transaction chains are still allowed for
    # staleness-class combos (at least one L05 piece).
    cu = _estimate_cu(combo)
    if cu > CU_TX_CAP and "L05" not in suffixes:
        return False

    # SOL-R6 TOKEN22_EXTENSION_COHERENCE: drop combos containing two
    # mutually-exclusive Token-2022 extensions on the same mint.
    for a, b in TOKEN22_INCOMPATIBLE_PAIRS:
        if a in suffixes and b in suffixes:
            return False

    # SOL-R7 CPI_DEPTH_LIMIT: depth > 4 is unreachable.
    if _count_cpi_depth(combo) > CPI_DEPTH_LIMIT:
        return False

    # SOL-R8 REMAINING_ACCOUNTS_DEPENDENCY: J08 needs a consumer (a C/G/L
    # piece that actually processes remaining_accounts).
    if "J08" in suffixes:
        consumer_cats = {"C", "G", "L"}
        has_consumer = any(
            p.get("category", "") in consumer_cats
            and _piece_type_suffix(p) != "J08"
            for p in combo
        )
        if not has_consumer:
            return False

    return True


# ---------- extra_score ----------


def extra_score(combo, base: float) -> float:
    """Apply Solana-specific scoring bonuses on top of the shared base."""
    weights_path = os.path.join(
        os.path.dirname(os.path.abspath(__file__)), "weights", f"{LANGUAGE}.json"
    )
    extras = {}
    try:
        import json

        with open(weights_path) as f:
            extras = json.load(f).get("extras", {})
    except FileNotFoundError:
        extras = {}

    suffixes = _suffixes(combo)
    suf_set = set(suffixes)
    categories = [p.get("category", "") for p in combo]

    s = base

    # Category-weight multiplier applied to the category-diversity baseline.
    # We do this as additive bonuses per category rather than mutating the
    # shared score, to keep composition transparent.
    cat_weights = extras.get("category_weights", {})
    for cat in set(categories):
        mult = cat_weights.get(cat, 1.0)
        if mult != 1.0:
            # Count of pieces in that category; each contributes (mult - 1.0)
            # as a bonus scaled by category_diversity (2.0 shared default).
            n = sum(1 for c in categories if c == cat)
            s += n * (mult - 1.0) * 2.0

    # Per-type overrides: additive bonus per matching piece.
    type_overrides = extras.get("type_overrides", {})
    for suf in suffixes:
        mult = type_overrides.get(suf, 1.0)
        if mult != 1.0:
            s += (mult - 1.0) * 2.0

    # Boolean-flag bonuses.
    if any(c == "K" for c in categories):
        s += extras.get("has_pda_piece", 0.0)
    if any(c == "L" for c in categories) or "D03" in suf_set:
        s += extras.get("has_cpi_piece", 0.0)
    if any(c == "J" for c in categories):
        s += extras.get("has_account_model_piece", 0.0)
    if any(c == "O" for c in categories):
        s += extras.get("has_token_2022_piece", 0.0)
    if any(c == "M" for c in categories):
        s += extras.get("has_lamports_piece", 0.0)
    if any(c == "N" for c in categories):
        s += extras.get("has_sysvar_piece", 0.0)

    # SOL-R3 PDA + missing-owner bonus: K* piece + J01 piece in the same
    # call_context or same contract.
    k_pieces = [p for p in combo if p.get("category") == "K"]
    j01_pieces = [p for p in combo if _piece_type_suffix(p) == "J01"]
    if k_pieces and j01_pieces:
        for kp in k_pieces:
            for jp in j01_pieces:
                if _pieces_share_context(kp, jp):
                    s += extras.get("pda_plus_missing_owner_bonus", 0.0)
                    break
            else:
                continue
            break

    # L05 (reload missing) + E* (pricing / fees): stale balance used in
    # pricing.
    if "L05" in suf_set and any(c == "E" for c in categories):
        s += extras.get("reload_plus_pricing_bonus", 0.0)

    # L01 (CPI target unchecked) + G03 (mint_and_burn): fake token program
    # for mint/burn.
    if "L01" in suf_set and "G03" in suf_set:
        s += extras.get("cpi_target_plus_mint_burn_bonus", 0.0)

    # J08 (remaining accounts injection) + L06 (arbitrary CPI): attacker
    # routing.
    if "J08" in suf_set and "L06" in suf_set:
        s += extras.get("remaining_accounts_plus_arbitrary_cpi_bonus", 0.0)

    # O10 (PermanentDelegate) + any vault-holding piece (G category or
    # O02 canonical ATA).
    if "O10" in suf_set and (any(c == "G" for c in categories) or "O02" in suf_set):
        s += extras.get("permanent_delegate_plus_vault_bonus", 0.0)

    # N06 (sysvar spoofing) + flash-loan guard (N03 introspection or L05
    # reload guard): Wormhole-class class composition.
    if "N06" in suf_set and ("N03" in suf_set or "L05" in suf_set):
        s += extras.get("sysvar_spoof_plus_flash_guard_bonus", 0.0)

    return round(s, 2)


def main() -> None:
    combinator = Combinator(
        LANGUAGE,
        rounding_types=ROUNDING_TYPES,
        defensive_types=DEFENSIVE_TYPES,
        bridge_types=BRIDGE_TYPES,
        conflicting_actors=CONFLICTING_ACTORS,
        read_only_indicators=READ_ONLY_INDICATORS,
        cron_actor=CRON_ACTOR,
        arithmetic_gap_type="A06",
        extra_eliminate=extra_eliminate,
        extra_score=extra_score,
    )
    combinator.run()


if __name__ == "__main__":
    main()
