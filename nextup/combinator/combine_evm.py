#!/usr/bin/env python3
"""NEXTUP EVM combinator. See combinator/shared.py for the harness."""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from shared import Combinator, _piece_type_suffix, _piece_has_bridge

LANGUAGE = "evm"

ROUNDING_TYPES = {"A01", "A02", "A03", "A04", "A05", "G04"}
DEFENSIVE_TYPES = {"B05", "D02", "E04", "E08", "G01", "I01", "I02"}
BRIDGE_TYPES = {"D03", "J01", "K03", "L05", "L04", "F01", "F03", "C03", "D01", "B04"}
CONFLICTING_ACTORS = [
    ("owner", "any_user"),
    ("owner", "non_owner"),
    ("owner", "multisig"),
    ("keeper", "any_user"),
    ("initializer", "any_user"),
    ("self_callback", "any_user"),
    ("bridge_endpoint", "any_user"),
    ("governance", "keeper"),
    ("flash_borrower", "initializer"),
]
CRON_ACTOR = "keeper"

REENTRANCY_TYPES = {"L01", "L02", "L03"}
FLASH_CALLBACK_TYPE = "L05"
RESERVE_PRICE_TYPE = "E05"
READ_WRITE_GAP_TYPE = "C03"
DELEGATECALL_TYPE = "J01"
SELECTOR_CLASH_TYPE = "J05"
AUTHORIZE_GAP_TYPE = "J04"
INITIALIZER_DISABLE_MARKER = "_disableInitializers"
ORACLE_PRICE_TYPE = "D01"
EXTERNAL_CALL_TYPE = "D03"
FLASH_BORROWER_ACTOR = "flash_borrower"
INITIALIZER_ACTOR = "initializer"
ANY_USER_ACTOR = "any_user"
OWNER_ACTOR = "owner"
CROSS_CHAIN_ACTOR = "bridge_endpoint"


def _suffixes(combo):
    return {_piece_type_suffix(p) for p in combo}


def _actors(combo):
    return {p.get("actor", "any_user") for p in combo}


def _categories(combo):
    return {p.get("category", "") for p in combo}


def _is_view_only(piece):
    ctx = (piece.get("call_context", "") or "").lower()
    fn = (piece.get("function", "") or "").lower()
    return "view" in ctx or "pure" in ctx or fn.startswith("get") or fn.startswith("preview")


def _combo_has_bridge(combo):
    return any(_piece_has_bridge(p, BRIDGE_TYPES) for p in combo)


def extra_eliminate(combo):
    suffixes = _suffixes(combo)
    actors = _actors(combo)

    # EVM-R1: view-only combo with no bridge to a non-view callee.
    if all(_is_view_only(p) for p in combo) and not _combo_has_bridge(combo):
        return False

    # EVM-R2: spot price without atomic bridge (flash callback).
    if RESERVE_PRICE_TYPE in suffixes or ORACLE_PRICE_TYPE in suffixes:
        twap_markers = {"TWAP", "observe", "consult"}
        has_twap = any(
            any(m.lower() in (p.get("snippet", "") or "").lower() for m in twap_markers)
            for p in combo
        )
        if has_twap and FLASH_CALLBACK_TYPE not in suffixes and FLASH_BORROWER_ACTOR not in actors:
            return False

    # EVM-R3: locked initializer with no authorize gap.
    if INITIALIZER_ACTOR in actors and AUTHORIZE_GAP_TYPE not in suffixes:
        if any(INITIALIZER_DISABLE_MARKER in (p.get("snippet", "") or "") for p in combo):
            return False

    # EVM-R4: delegatecall gadget with no reachable sink and no selector clash.
    if DELEGATECALL_TYPE in suffixes and SELECTOR_CLASH_TYPE not in suffixes:
        if all(p.get("actor") in (OWNER_ACTOR, "delegate") for p in combo):
            return False

    # EVM-R5: reentrancy pieces where every function is nonReentrant (guard intact).
    if suffixes & REENTRANCY_TYPES:
        guarded = all(
            "nonreentrant" in (p.get("snippet", "") or "").lower()
            or "reentrancyguard" in (p.get("snippet", "") or "").lower()
            for p in combo
        )
        guard_collision = suffixes & {"J06", "J02"}
        if guarded and not guard_collision:
            return False

    # EVM-R8: authenticated cross-chain combo.
    if CROSS_CHAIN_ACTOR in actors:
        has_auth = any(
            "srcEid" in (p.get("snippet", "") or "") and "sender" in (p.get("snippet", "") or "")
            for p in combo
        )
        if has_auth and "J03" not in suffixes and "B03" not in suffixes:
            return False

    # EVM-R9: reserve-price pricing but slippage bound absorbs manipulation.
    if RESERVE_PRICE_TYPE in suffixes and "E04" in suffixes:
        user_slippage = any(
            "minamountout" in (p.get("snippet", "") or "").lower()
            and p.get("actor") == ANY_USER_ACTOR
            for p in combo
        )
        if user_slippage:
            return False

    # EVM-R10: owner action behind timelock with non-theft, non-pause impact.
    if OWNER_ACTOR in actors:
        timelocked = any(
            "timelock" in (p.get("snippet", "") or "").lower()
            or "mindelay" in (p.get("snippet", "") or "").lower()
            for p in combo
        )
        if timelocked:
            theft_or_pause = any(
                kw in (p.get("description", "") or "").lower()
                for p in combo
                for kw in ("theft", "steal", "drain", "pause", "emergency")
            )
            if not theft_or_pause:
                return False

    return True


def extra_score(combo, base):
    suffixes = _suffixes(combo)
    actors = _actors(combo)
    cats = _categories(combo)
    s = base

    # Bridge priority.
    bridge_count = sum(1 for p in combo if _piece_has_bridge(p, BRIDGE_TYPES))
    s += bridge_count * 0.5

    # Category weighting for J/K/L.
    if "J" in cats:
        s += 1.4
    if "K" in cats:
        s += 1.25
    if "L" in cats:
        s += 1.5

    # Actor weighting.
    if ANY_USER_ACTOR in actors:
        s += 1.4
    if FLASH_BORROWER_ACTOR in actors:
        s += 1.35
    if "keeper" in actors:
        s += 0.5
    if OWNER_ACTOR in actors:
        s -= 0.5
    if "governance" in actors:
        s -= 0.3
    if INITIALIZER_ACTOR in actors:
        s += 1.0

    # Chain length bonus.
    if len(combo) >= 3:
        s += (len(combo) - 2) * 1.5

    # Duplicate piece penalty.
    type_list = [p.get("type", "") for p in combo]
    if len(set(type_list)) < len(type_list):
        s -= 3.0

    # Reentrancy + read-write gap bonus.
    if (suffixes & REENTRANCY_TYPES) and READ_WRITE_GAP_TYPE in suffixes:
        s += 3.0

    # Delegatecall + selector clash bonus.
    if DELEGATECALL_TYPE in suffixes and SELECTOR_CLASH_TYPE in suffixes:
        s += 2.5

    # Flash callback + reserve-price bonus.
    if FLASH_CALLBACK_TYPE in suffixes and RESERVE_PRICE_TYPE in suffixes:
        s += 3.0

    # Oracle + external call bonus.
    if ORACLE_PRICE_TYPE in suffixes and EXTERNAL_CALL_TYPE in suffixes:
        s += 1.5

    # External-call presence broadens blast radius.
    if EXTERNAL_CALL_TYPE in suffixes:
        s += 0.5

    return round(s, 2)


if __name__ == "__main__":
    Combinator(
        language=LANGUAGE,
        rounding_types=ROUNDING_TYPES,
        defensive_types=DEFENSIVE_TYPES,
        bridge_types=BRIDGE_TYPES,
        conflicting_actors=CONFLICTING_ACTORS,
        cron_actor=CRON_ACTOR,
        extra_eliminate=extra_eliminate,
        extra_score=extra_score,
    ).run()
