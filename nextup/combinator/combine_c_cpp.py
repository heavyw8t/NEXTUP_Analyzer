#!/usr/bin/env python3
"""
NEXTUP C/C++ combinator.

Uses the shared Combinator scaffolding (shared.py) and adds C/C++-specific
extra elimination rules (CPP-R1..R6) and scoring bonuses. C/C++ taxonomy has
no DeFi rounding semantics, so ROUNDING_TYPES is empty and several DeFi-
centric defaults are loosened in rules/c_cpp.json.

CLI: python3 combine_c_cpp.py <pieces.json> <k> <output.json> [--top N]
"""

from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from shared import Combinator, _piece_type_suffix, _piece_has_bridge  # noqa: E402


LANGUAGE = "c_cpp"

# C/C++ has no DeFi-style rounding direction pairs. Leave empty so the
# shared `eliminate_redundant_same_direction_rounding` filter never fires.
ROUNDING_TYPES: set[str] = set()

# Purely defensive pieces (suffix-only). A combo made entirely of these has
# no attack surface. For C/C++, only I01 is purely defensive in isolation
# (assert / static_assert). Everything else is either an anchor or neutral.
DEFENSIVE_TYPES: set[str] = {"I01"}

# Bridge pieces (suffix-only). These tie pieces across function boundaries,
# threads, or trust boundaries. See design doc section 4.
#   K* — alias / lifetime bridges (allocation site to use site).
#   L* — lock-acquisition bridges (cross-thread happens-before).
#   M* — input-boundary bridges (external channel to internal state).
#   J06 — zero-size alloc is a bridge by construction (alloc site to first use).
BRIDGE_TYPES: set[str] = {
    "K01", "K02", "K03", "K04", "K05", "K06", "K07",
    "L01", "L02", "L03", "L04", "L05", "L06",
    "M01", "M02", "M03", "M04", "M05", "M06",
    "J06",
}

# Per design doc section 5: no mutual-exclusion actor conflicts in C/C++.
# signal_handler / interrupt_handler constraints are modeled as reachability,
# not mutual exclusion, so they are not encoded here.
CONFLICTING_ACTORS: list[tuple[str, str]] = []

# No cron/keeper concept in systems C/C++.
CRON_ACTOR: str | None = None


# --- category / family helpers ---

MEMORY_SAFETY_SUFFIXES = {"J01", "J02", "J03", "J04", "J05", "J06", "J07", "J08"}
ALIASING_SUFFIXES = {"K01", "K02", "K03", "K04", "K05", "K06", "K07"}
CONCURRENCY_SUFFIXES = {"L01", "L02", "L03", "L04", "L05", "L06"}
INPUT_SUFFIXES = {"M01", "M02", "M03", "M04", "M05", "M06"}
UB_SUFFIXES = {"N01", "N02", "N03", "N04", "N05", "N06"}
RESOURCE_SUFFIXES = {"O01", "O02", "O03", "O04", "O05", "O06"}
ARITHMETIC_SUFFIXES = {"A04", "A05", "A06", "A07"}

STRANDED_RESOURCE_SUFFIXES = {"O01", "O02", "O05", "L06"}

# Actors that count for the "multi-thread" bonus.
THREAD_ACTORS = {"main_thread", "worker_thread", "signal_handler", "async_callback"}

# Sanitizer keywords in markers / descriptions. Used by CPP-R1 (sanitizer
# duplicate pruning) and by CPP-R5 (ASan/TSan incompatibility flagging).
SANITIZER_KEYWORDS = {
    "ASan": ["ASan", "asan", "-fsanitize=address", "AddressSanitizer"],
    "TSan": ["TSan", "tsan", "-fsanitize=thread", "ThreadSanitizer"],
    "MSan": ["MSan", "msan", "-fsanitize=memory", "MemorySanitizer"],
    "UBSan": ["UBSan", "ubsan", "-fsanitize=undefined", "UndefinedBehaviorSanitizer"],
    "LSan": ["LSan", "lsan", "-fsanitize=leak", "LeakSanitizer"],
}

# Functions that do I/O, allocation, shared-state access, or syscalls.
# Used by CPP-R3 pure-compute pruning: a combo is "pure compute" if NO piece
# mentions any of these in snippet / description / markers.
IO_KEYWORDS = [
    "malloc", "calloc", "realloc", "free", "new ", "delete",
    "fopen", "fclose", "open", "close", "read", "write", "recv", "send",
    "socket", "accept", "connect", "pthread_", "std::thread",
    "mutex", "lock_guard", "atomic", "printf", "fprintf", "sprintf",
    "snprintf", "syslog", "dlopen", "dlsym", "syscall", "ioctl",
    "mmap", "munmap", "shm_", "msg", "pipe", "fork", "exec",
    "sigaction", "signal",
]


def _combo_has_any_suffix(combo, suffixes: set[str]) -> bool:
    return any(_piece_type_suffix(p) in suffixes for p in combo)


def _combo_has_input_bridge(combo) -> bool:
    return any(_piece_type_suffix(p) in INPUT_SUFFIXES for p in combo)


def _combo_text_blob(combo) -> str:
    parts = []
    for p in combo:
        parts.append(p.get("snippet", "") or "")
        parts.append(p.get("description", "") or "")
        for m in p.get("markers", []) or []:
            parts.append(m if isinstance(m, str) else "")
    return "\n".join(parts)


def _combo_sanitizers(combo) -> set[str]:
    """Return the set of sanitizer names referenced by the combo's text."""
    blob = _combo_text_blob(combo)
    hit: set[str] = set()
    for name, keys in SANITIZER_KEYWORDS.items():
        for k in keys:
            if k in blob:
                hit.add(name)
                break
    return hit


# --- extra eliminate (CPP-R1..R6) ---

def extra_eliminate(combo) -> bool:
    """Return True to KEEP, False to DROP."""

    # CPP-R1: sanitizer-duplicate pruning.
    # If every piece sits in the same file+function+line and they all share a
    # single sanitizer signal, the "combo" is one primitive reported thrice.
    sanitizers = _combo_sanitizers(combo)
    if len(sanitizers) == 1:
        locs = {(p.get("file"), p.get("function"), p.get("line_start")) for p in combo}
        if len(locs) == 1:
            return False

    # CPP-R2: template-only pruning.
    # If every piece is in a header (.h / .hpp / .hh / .ipp / .tpp) and no
    # piece lists a concrete instantiation in state_touched, drop. The
    # combinator earns its keep on instantiated code.
    def _is_header(path: str) -> bool:
        return any(path.endswith(ext) for ext in (".h", ".hpp", ".hh", ".ipp", ".tpp", ".hxx"))

    if all(_is_header(p.get("file", "")) for p in combo):
        instantiated = any(
            any("<" in s and ">" in s for s in (p.get("state_touched") or []))
            for p in combo
        )
        if not instantiated:
            return False

    # CPP-R3: pure-compute pruning.
    # If NO piece touches I/O / alloc / shared state / syscalls AND there is
    # no CPP-M* bridge, the chain cannot cross a trust boundary.
    blob = _combo_text_blob(combo)
    has_io = any(kw in blob for kw in IO_KEYWORDS)
    has_m_bridge = _combo_has_input_bridge(combo)
    has_shared_state = any(p.get("state_touched") for p in combo)
    if not has_io and not has_m_bridge and not has_shared_state:
        return False

    # CPP-R4: same-translation-unit static pruning.
    # If every piece references the same contract (TU) AND every function name
    # looks static-scoped AND there is no M bridge or L bridge, downgrade by
    # dropping. (The scoring pass cannot "downgrade confidence" directly;
    # eliminating is the available knob.)
    contracts = {p.get("contract", "") for p in combo}
    if len(contracts) == 1 and "" not in contracts:
        has_l_bridge = _combo_has_any_suffix(combo, CONCURRENCY_SUFFIXES)
        if not has_m_bridge and not has_l_bridge:
            # Heuristic: if every piece lacks any bridge suffix AND lacks a
            # D03 cross-module call, it is intra-TU static code.
            has_any_bridge = any(_piece_has_bridge(p, BRIDGE_TYPES) for p in combo)
            has_cross_module = any(_piece_type_suffix(p) == "D03" for p in combo)
            if not has_any_bridge and not has_cross_module:
                # Only drop if ALSO arithmetic-only or resource-only (boring
                # intra-TU combos). Leave J/K/N combos alone; they may still
                # be real.
                cats = {p.get("category") for p in combo}
                if cats.issubset({"A", "O", "C", "I"}):
                    return False

    # CPP-R5: sanitizer-incompatible pruning.
    # ASan and TSan cannot be combined in one build. If the combo needs both
    # sanitizers simultaneously to prove it, mark and keep (the shared pipeline
    # cannot emit a SPLIT-VERIFY flag, so we keep and let the verifier handle
    # it per phase5-poc-execution.md).
    if {"ASan", "TSan"}.issubset(sanitizers):
        # Keep, but the verification phase will split-verify.
        pass

    # CPP-R6: already-patched pruning is fork-ancestry-driven. The combinator
    # has no access to fork-ancestry results here; recon / phase-4b consumes
    # that signal. Stub: if any piece has a "patched_cve" marker in its
    # state_touched list (authoring convention), drop the combo.
    if any(
        any(isinstance(s, str) and s.startswith("patched_cve:") for s in (p.get("state_touched") or []))
        for p in combo
    ):
        return False

    return True


# --- extra score ---

def extra_score(combo, base: float) -> float:
    """Apply C/C++ scoring bonuses from design doc section 7."""
    import os as _os
    import json as _json

    # Load weights.extras lazily. shared.py already loaded rules + weights
    # and passed `base`; we need the extras dict for the per-bonus values.
    base_dir = _os.path.dirname(_os.path.abspath(__file__))
    try:
        with open(_os.path.join(base_dir, "weights", f"{LANGUAGE}.json")) as f:
            weights = _json.load(f)
        extras = weights.get("extras", {}) or {}
    except FileNotFoundError:
        extras = {}

    s = base

    has_j = _combo_has_any_suffix(combo, MEMORY_SAFETY_SUFFIXES)
    has_k = _combo_has_any_suffix(combo, ALIASING_SUFFIXES)
    has_l = _combo_has_any_suffix(combo, CONCURRENCY_SUFFIXES)
    has_m = _combo_has_any_suffix(combo, INPUT_SUFFIXES)
    has_n = _combo_has_any_suffix(combo, UB_SUFFIXES)
    has_o = _combo_has_any_suffix(combo, RESOURCE_SUFFIXES)
    has_a = _combo_has_any_suffix(combo, ARITHMETIC_SUFFIXES)

    if has_j:
        s += extras.get("has_memory_safety_piece", 3.0)
    if has_k:
        s += extras.get("has_aliasing_piece", 2.0)
    if has_l:
        s += extras.get("has_concurrency_piece", 3.0)
    if has_n:
        s += extras.get("has_ub_piece", 2.0)
    if has_o:
        s += extras.get("stranded_resource_floor_bonus", 1.0) if any(
            _piece_type_suffix(p) in STRANDED_RESOURCE_SUFFIXES for p in combo
        ) else extras.get("has_resource_piece", 1.0)
    if has_a:
        s += extras.get("has_arithmetic_piece", 1.0)

    # Input validation piece on the trust boundary: actor outside plain
    # main_thread init. Proxy: any piece whose actor is in THREAD_ACTORS,
    # or an M piece at all (external input is by definition a trust boundary).
    if has_m:
        s += extras.get("has_input_validation_piece", 3.0)

    # Arithmetic piece paired with J or M: "+2 if paired".
    if has_a and (has_j or has_m):
        s += extras.get("arithmetic_plus_memory_or_input_bonus", 2.0)

    # Multiplicative: J + M => x1.5 (input-to-corruption chain).
    if has_j and has_m:
        s *= extras.get("input_to_corruption_multiplier", 1.5)

    # Multiplicative: L + >=2 distinct actors => x1.3.
    actors = {p.get("actor", "") for p in combo if p.get("actor")}
    if has_l and len(actors) >= 2:
        s *= extras.get("concurrency_multi_actor_multiplier", 1.3)

    # Mixed-actor threads bonus: >=2 of the THREAD_ACTORS set present.
    thread_actor_hits = actors & THREAD_ACTORS
    if len(thread_actor_hits) >= 2:
        s += extras.get("mixed_actor_threads_bonus", 2.0)

    # Signal-handler + non-signal-safe call.
    if "signal_handler" in actors:
        blob = _combo_text_blob(combo).lower()
        non_safe = any(
            kw in blob for kw in ("malloc", "printf", "fprintf", "syslog", "mutex", "lock_guard")
        )
        if non_safe:
            s += extras.get("signal_plus_unsafe_call_bonus", 3.0)
        # L05 itself is the same pattern; avoid double-count by only adding
        # once per combo.

    # RAII bypass + exception path.
    has_raii_bypass = any(_piece_type_suffix(p) == "O01" for p in combo)
    if has_raii_bypass:
        blob = _combo_text_blob(combo)
        if "throw" in blob or "exception" in blob or "noexcept(false)" in blob:
            s += extras.get("raii_plus_exception_bonus", 2.0)

    # Penalty: all pieces same function AND no M bridge.
    funcs = {(p.get("file"), p.get("function")) for p in combo}
    if len(funcs) == 1 and not has_m:
        s -= extras.get("all_pieces_same_function_no_m_penalty", 2.0)

    # Penalty: all pieces in templates (header-only).
    def _is_header(path: str) -> bool:
        return any(path.endswith(ext) for ext in (".h", ".hpp", ".hh", ".ipp", ".tpp", ".hxx"))

    if all(_is_header(p.get("file", "")) for p in combo):
        s -= extras.get("all_in_templates_penalty", 3.0)

    # Penalty: O06 (DSE-dependent secret clear) outside crypto context.
    has_dse = any(_piece_type_suffix(p) == "O06" for p in combo)
    if has_dse:
        blob = _combo_text_blob(combo).lower()
        crypto_ctx = any(
            kw in blob for kw in ("crypt", "key", "aes", "rsa", "ecdsa", "ed25519", "hmac", "hash", "secret", "password", "cipher")
        )
        if not crypto_ctx:
            s -= extras.get("dse_no_crypto_context_penalty", 1.0)

    return round(s, 2)


# --- entry point ---

def main() -> None:
    combinator = Combinator(
        language=LANGUAGE,
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
