# NEXTUP puzzle-piece schema (v1.1)

Canonical contract shared by all five per-language taxonomies and combinators. Phase C authoring agents must conform to everything in this file. The hypothesis and filter agents consume this contract unchanged.

## 1. Taxonomy file (`nextup/taxonomy/{lang}.json`)

```json
{
  "version": "1.1.0",
  "language": "evm | solana | aptos | sui | c_cpp",
  "id_prefix": "EVM | SOL | APT | SUI | CPP",
  "categories": {
    "A": "Arithmetic & Precision",
    "...": "..."
  },
  "types": [
    {
      "id": "EVM-A01",
      "name": "ROUNDING_FLOOR",
      "category": "A",
      "description": "Value computation rounded down (floor division, truncation toward zero)",
      "markers": ["mulDiv", "/ (integer division)", "Math.floor", "mulDivDown"],
      "typical_direction": "favors_protocol"
    }
  ]
}
```

Rules:
- `id` is always `{PREFIX}-{LETTER}{2digits}` (e.g. `SOL-J01`). No unprefixed ids.
- `category` is a single letter. Native categories start at J and go upward per language.
- `markers` is a flat list of strings (no per-language sub-keys; the file is already per-language).
- `typical_direction` uses the extended enum below.

## 2. Piece-entry schema (extraction output, `pieces.json`)

One array element per tagged pattern instance. Fields are identical across all languages.

```json
{
  "id": "P001",
  "type": "SOL-J01",
  "category": "J",
  "file": "programs/amm/src/instructions/swap.rs",
  "function": "swap",
  "line_start": 124,
  "line_end": 124,
  "description": "Missing owner check on source_token_account before deriving swap output.",
  "state_touched": ["source_token_account", "pool_state"],
  "actor": "signer",
  "direction": "exploitable",
  "call_context": "swap_exact_amount_in",
  "contract": "amm_program",
  "depends_on": [],
  "snippet": "let src = &ctx.accounts.source_token_account;"
}
```

Field notes:
- `id` stays `P###` (pipeline-local), not language-prefixed. Language is implied by the piece `type`.
- `type` is language-prefixed and must exist in the corresponding `{lang}.json`.
- `actor` is an open string. The per-language combinator declares the valid set; extraction should use one of them. Values vary by language (see per-language design docs).
- `direction` extended enum: `favors_protocol | favors_user | neutral | exploitable | latent`. The last two exist for C/C++ where DeFi-centric "favors_*" is meaningless. Other languages keep using the first three; the combinator treats all five as opaque strings except when applying the `mixed_direction` scoring bonus (which fires when ≥2 distinct non-neutral values appear in a combo).
- `contract` is the language's primary unit of code isolation: Solidity contract, Solana program, Move module, C++ translation unit / library.
- `depends_on` holds other `P###` ids in the same pieces.json file.

## 3. Combinator output schema (`combinations.json`)

```json
{
  "metadata": {
    "language": "solana",
    "total_pieces": 42,
    "k": 3,
    "total_combinations": 11480,
    "quick_filtered": 210,
    "eliminated": 10890,
    "survivors": 380,
    "top_n": 100,
    "elimination_rate": 96.7
  },
  "combinations": [
    {
      "combo_id": "COMBO-0001",
      "score": 18.5,
      "pieces": ["P003", "P017", "P042"],
      "piece_types": ["SOL-J01", "SOL-L01", "SOL-K03"],
      "categories": ["J", "K", "L"],
      "directions": ["exploitable", "neutral"],
      "shared_state": ["source_token_account"],
      "locations": ["swap.rs:124", "swap.rs:158", "swap.rs:191"],
      "descriptions": ["...", "...", "..."],
      "snippets": ["...", "...", "..."]
    }
  ]
}
```

Rules:
- `metadata.language` is the new field added in v1.1; hypothesis agent should ignore unknown top-level fields (it already does).
- All other fields match the v1.0 schema. The hypothesis agent consumes this unchanged.

## 4. Per-language config files

`nextup/combinator/rules/{lang}.json`:

```json
{
  "min_categories": 2,
  "require_shared_contract_or_call": true,
  "require_interaction_link": true,
  "eliminate_actor_conflict": true,
  "eliminate_redundant_same_direction_rounding": true,
  "eliminate_same_function_duplicate": true,
  "eliminate_read_only_combos": true,
  "eliminate_pure_defensive": true,
  "eliminate_no_state_overlap": true,
  "eliminate_all_neutral_same_context": true,
  "custom_rules": []
}
```

The keyset matches what `shared.py` understands. `custom_rules` is a per-language list of rule keys the language's combinator script handles internally (documented in that script). Example for Solana: `["eliminate_all_query", "eliminate_no_account_overlap_no_cpi"]`.

`nextup/combinator/weights/{lang}.json`:

```json
{
  "category_diversity": 2.0,
  "has_economic_piece": 3.0,
  "has_rounding_piece": 1.5,
  "has_oracle_piece": 2.0,
  "mixed_direction": 2.5,
  "same_state_touched": 2.0,
  "all_checked_arithmetic_penalty": 1.0,
  "extras": {}
}
```

`extras` is an open object the per-language `combine_{lang}.py` reads for its native category bonuses and boolean-flag bonuses. Example for Solana: `{"has_pda_piece": 2.5, "has_cpi_piece": 2.0, "pda_plus_missing_owner_bonus": 3.0}`.

## 5. Invariants enforced by shared.py

- Input `pieces.json` must be a JSON array. No envelope.
- Output JSON is written atomically (write to temp, rename) so partial failure never corrupts the file.
- The CLI interface is fixed: `python3 combine_{lang}.py <pieces.json> <k> <output.json> [--top N]`. Default `--top`: 50 for k=2, 100 for k=3, 150 for k=4.
- The combinator is pure-Python stdlib. No third-party deps.

## 6. Version

Schema version: 1.1.0. Breaking change from 1.0 (singleton taxonomy + combinator) because piece `type` values are now language-prefixed and taxonomy files split. Old audits in flight use 1.0; new audits use 1.1.
