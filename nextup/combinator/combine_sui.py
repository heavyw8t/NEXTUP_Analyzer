"""
NEXTUP Sui combinator (v1.1).

CLI: python3 combine_sui.py <pieces.json> <k> <output.json> [--top N]

Sui-specific elimination rules (SUI-R1..R6) and scoring bonuses live in the
extra_eliminate / extra_score hooks. All shared scaffolding lives in shared.py.
"""

from __future__ import annotations

from shared import Combinator


LANGUAGE = "sui"

# Rounding piece suffixes (used by shared.py's same-direction-rounding filter).
ROUNDING_TYPES = {"A01", "A02", "A03"}

# Defensive-only piece suffixes (combos made only of these are noise).
# Covers pure validation / slippage / guard pieces.
DEFENSIVE_TYPES = {
    "B05",  # PAUSE_GATE
    "E04",  # SLIPPAGE_PROTECTION
    "E08",  # MINIMUM_SIZE_CHECK
    "G01",  # FUND_VERIFICATION
    "I01",  # INVARIANT_PRESERVATION
    "I02",  # BALANCE_ACCOUNTING
}

# Bridge piece suffixes: pieces that connect otherwise-disconnected code or
# state. Matches design doc section 4.
BRIDGE_TYPES = {
    # PTB composition handoff
    "K01", "K02", "K03", "K04",
    # Package upgrade (cross-version)
    "L01", "L02", "L03", "L04",
    # Dynamic (object) fields (cross-module)
    "M01", "M02", "M03",
    # Shared-object bridges across callers
    "J01", "J06",
}

# Conflicting actor pairs per design doc section 5.
CONFLICTING_ACTORS = [
    ("sender", "package_upgrader"),
    ("sender", "cap_holder"),
    ("shared_object_updater", "consensus"),
    ("module_publisher", "sender"),
    ("package_upgrader", "consensus"),
]

# Sui has no automated cron actor analogous to CosmWasm's sudo cron.
# Keeper bots are just senders with specific naming (see SUI-F01), not a
# consensus-level actor, so leave unset.
CRON_ACTOR = None


# ------------------ Sui-specific helpers ------------------

PRIORITY_CATEGORIES = {"J", "K", "L"}
MEDIUM_CATEGORIES = {"M", "N"}

PER_TYPE_OVERRIDES = {
    "SUI-B03": 1.3,
    "SUI-D03": 1.3,
    "SUI-E05": 1.3,
    "SUI-C03": 0.7,
}


def _suffix(piece: dict) -> str:
    """Return 'A01' from 'SUI-A01'. Copy of shared._piece_type_suffix to avoid
    importing private names."""
    t = piece.get("type", "")
    if "-" in t:
        t = t.split("-", 1)[1]
    return t.split("_", 1)[0] if "_" in t else t


def _full_type(piece: dict) -> str:
    return piece.get("type", "")


def _has_suffix(combo, suffix: str) -> bool:
    return any(_suffix(p) == suffix for p in combo)


def _has_category(combo, letter: str) -> bool:
    return any(p.get("category") == letter for p in combo)


def _is_immutable_piece(piece: dict) -> bool:
    """Piece anchored on an immutable/frozen object."""
    suffix = _suffix(piece)
    if suffix == "J04":
        return True
    ctx = piece.get("call_context", "").lower()
    state = " ".join(piece.get("state_touched", [])).lower()
    desc = piece.get("description", "").lower()
    snippet = piece.get("snippet", "").lower()
    blob = f"{ctx} {state} {desc} {snippet}"
    for tok in ("freeze_object", "frozen", "public_freeze_object", "immutable"):
        if tok in blob:
            return True
    return False


def _is_owned_object_piece(piece: dict) -> bool:
    """Piece anchored on an owned object (not shared)."""
    ctx = piece.get("call_context", "").lower()
    state = " ".join(piece.get("state_touched", [])).lower()
    desc = piece.get("description", "").lower()
    snippet = piece.get("snippet", "").lower()
    blob = f"{ctx} {state} {desc} {snippet}"
    if "owned" in blob and "shared" not in blob:
        return True
    return False


def _is_shared_uid_piece(piece: dict) -> bool:
    """Piece touches a shared object's UID."""
    ctx = piece.get("call_context", "").lower()
    state = " ".join(piece.get("state_touched", [])).lower()
    desc = piece.get("description", "").lower()
    snippet = piece.get("snippet", "").lower()
    blob = f"{ctx} {state} {desc} {snippet}"
    return "shared" in blob or "share_object" in blob or "public_share_object" in blob


def _is_transfer_piece(piece: dict) -> bool:
    suffix = _suffix(piece)
    if suffix in ("J01", "J06", "G01", "G02", "G03", "N03"):
        return True
    snippet = piece.get("snippet", "").lower()
    desc = piece.get("description", "").lower()
    blob = f"{snippet} {desc}"
    return "transfer::" in blob or "public_transfer" in blob


# ------------------ Extra elimination ------------------

def extra_eliminate(combo) -> bool:
    """Return True to KEEP the combo, False to drop it.

    Implements SUI-R1..R6 from design doc section 6.
    """
    suffixes = {_suffix(p) for p in combo}
    cats = {p.get("category", "") for p in combo}

    # SUI-R1: Immutable-only combo. If every piece is anchored on frozen state
    # and no L-category piece appears, drop the combo.
    all_immutable = all(_is_immutable_piece(p) for p in combo)
    if all_immutable and "L" not in cats:
        return False

    # SUI-R2: PTB atomicity. Combos whose narrative invents a partial-rollback
    # assumption WITHOUT including SUI-K03 (the piece that captures that
    # misconception) are dropped. Heuristic: description/snippet contains
    # partial-commit language across pieces but no K03 piece is present.
    if "K03" not in suffixes:
        partial_tokens = ("partial commit", "partial rollback", "step 2 fails", "step 1 persists")
        hit = any(
            any(tok in p.get("description", "").lower() or tok in p.get("snippet", "").lower() for tok in partial_tokens)
            for p in combo
        )
        if hit:
            return False

    # SUI-R3: Owned-object cross-sender. Combo requires two different senders
    # to both hold the same owned object without an intermediate transfer.
    actors = {p.get("actor", "") for p in combo}
    distinct_senders = len({a for a in actors if a in ("sender", "cap_holder", "module_publisher")}) >= 2
    owned_pieces = [p for p in combo if _is_owned_object_piece(p)]
    has_transfer = any(_is_transfer_piece(p) for p in combo)
    if distinct_senders and owned_pieces and not has_transfer:
        return False

    # SUI-R4: UpgradeCap immutability. If any piece explicitly records the
    # package as made_immutable (via call_context or snippet), eliminate every
    # combo that includes an L-category piece: upgrade path is closed.
    package_immutable = any(
        "make_immutable" in (p.get("snippet", "") + " " + p.get("description", "")).lower()
        for p in combo
    )
    if package_immutable and "L" in cats:
        return False

    # SUI-R5: Cap-gated + NO_ACCESS_CONTROL contradiction. If SUI-B01 and
    # SUI-B03 both appear and target the SAME function, drop as contradictory.
    if "B01" in suffixes and "B03" in suffixes:
        b_pieces = [p for p in combo if _suffix(p) in ("B01", "B03")]
        funcs = {(p.get("file", ""), p.get("function", "")) for p in b_pieces}
        if len(funcs) == 1:
            return False

    # SUI-R6: DOF without shared UID. If SUI-M02 is present but all pieces
    # look like they touch owned (not shared) UIDs and no transfer piece is
    # present, drop (the collision requires owner == attacker == victim).
    if "M02" in suffixes:
        touches_shared = any(_is_shared_uid_piece(p) for p in combo)
        if not touches_shared and not has_transfer:
            return False

    return True


# ------------------ Extra scoring ------------------

def extra_score(combo, base: float) -> float:
    s = base
    cats = {p.get("category", "") for p in combo}
    suffixes = {_suffix(p) for p in combo}
    full_types = {_full_type(p) for p in combo}

    # Priority-tier category multiplier (J / K / L).
    priority_hits = len(cats & PRIORITY_CATEGORIES)
    if priority_hits:
        s += priority_hits * 2.0  # priority_multiplier effective bonus

    # Medium-tier category bonus (M / N).
    medium_hits = len(cats & MEDIUM_CATEGORIES)
    if medium_hits:
        s += medium_hits * 1.5

    # If no priority-tier piece at all, apply combo_no_priority_penalty
    # (0.5x multiplier -> subtract half the current positive base).
    if not (cats & PRIORITY_CATEGORIES):
        s *= 0.5

    # Per-type overrides (boosts / demotions on individual SUI-* ids).
    for full in full_types:
        mult = PER_TYPE_OVERRIDES.get(full)
        if mult is not None:
            s += (mult - 1.0)  # additive shift per piece override

    # Bridge-piece presence bonus.
    bridge_hits = sum(1 for p in combo if _suffix(p) in BRIDGE_TYPES)
    if bridge_hits:
        s += bridge_hits * 2.0

    # Specific high-signal combos per design doc.
    # Version bump missing + shared-object write.
    if "J03" in suffixes and ("J01" in suffixes or "B03" in suffixes):
        s += 3.0

    # PTB handoff + spot-price-from-reserves (flash-loan shape).
    if ("K01" in suffixes or "K04" in suffixes) and "E05" in suffixes:
        s += 3.0

    # TreasuryCap leak + shared-object write (mint-authority leak path).
    if "N03" in suffixes and ("J01" in suffixes or "B03" in suffixes):
        s += 3.5

    # Shared-object write + DOF unbounded growth (griefing path).
    if "M01" in suffixes and ("J01" in suffixes or "B03" in suffixes):
        s += 2.5

    return round(s, 2)


# ------------------ Entry point ------------------

def main() -> None:
    combinator = Combinator(
        LANGUAGE,
        rounding_types=ROUNDING_TYPES,
        defensive_types=DEFENSIVE_TYPES,
        bridge_types=BRIDGE_TYPES,
        conflicting_actors=CONFLICTING_ACTORS,
        cron_actor=CRON_ACTOR,
        arithmetic_gap_type="A06",
        extra_eliminate=extra_eliminate,
        extra_score=extra_score,
    )
    combinator.run()


if __name__ == "__main__":
    main()
