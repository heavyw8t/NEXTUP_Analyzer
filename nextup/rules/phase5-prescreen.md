# Phase 5 Pre-Screen: Early Exit + Invalidation Hints + External Research

> **Purpose**: Filter trivially invalid findings before burning verification budget, enrich surviving findings with adversarial invalidation hints and external protocol research.
> **Trigger**: Always runs at the start of Phase 5, before spawning any verification agents.
> **Budget**: 1 sonnet batch agent (selector) + 0-1 sonnet agents (external research). Negligible cost.
> **Artifacts consumed by**: Phase 5 verifier agents (enriched prompts), Phase 5.2 Final Validation agents.

---

## Orchestrator Flow

```
Phase 4c (Chain Analysis)
    ↓
Phase 5 Pre-Screen
    Step 0a: Early Exit Check (orchestrator inline)
    Step 0b: Invalidation Library Selector (sonnet, batched)
    Step 0c: External Protocol Research (sonnet, parallel, conditional)
    ↓
Phase 5: Verification (verifiers receive pre-screen enrichment)
```

---

## Step 0a: Early Exit Check (Orchestrator Inline)

For each finding in `{SCRATCHPAD}/hypotheses.md`, run two mechanical checks:

### Check 1: Broken Reference

For each finding's `Location` field (file:line):
1. Does the referenced file exist at `{PROJECT_PATH}`?
2. Does the referenced line range contain code consistent with the finding's description?

Use `Read` to verify. If the file does not exist OR the line range is empty/comments-only:
- Mark finding as `EARLY_EXIT: BROKEN_REF`
- Set verdict to `FALSE_POSITIVE` with reason: "Referenced location `{file:line}` does not contain the claimed code."
- Remove from verification queue

### Check 2: Pure Trusted-Actor Finding

For each finding, check if the ENTIRE attack path requires a fully-trusted actor (per `{SCRATCHPAD}/design_context.md` trust model) to act maliciously with NO other dimension:

**Is pure trusted-actor if ALL of these are true**:
1. The attack path starts with an admin/owner/governance/multisig action
2. The action is within that role's documented permissions
3. No external precondition manipulation, no path via unprivileged actor, no code bug triggered by legitimate admin operation
4. The finding is NOT about unexpected code behavior from a correct admin call (that's a code bug)

If pure trusted-actor:
- Cap severity at **Low** (do not mark FALSE_POSITIVE — trusted-actor findings are still reported)
- Tag with `[TRUSTED-ACTOR-CAP]`
- Log: `"Early exit cap: {ID} capped at Low — pure trusted-actor attack path"`

### Step 0a Output

Write to `{SCRATCHPAD}/prescreen_early_exit.md`:

```markdown
# Pre-Screen Early Exit Results

## Broken References (removed from verification queue)
| ID | Location | Reason |
|----|----------|--------|

## Trusted-Actor Caps (severity capped at Low)
| ID | Original Severity | Actor | Reason |
|----|-------------------|-------|--------|

## Surviving Findings: {N} (proceed to Step 0b)
```

---

## Step 0b: Invalidation Library Selector (Sonnet, Batched)

Spawn a single sonnet agent that processes ALL surviving findings in one batch:

```
Task(subagent_type="general-purpose", model="sonnet", prompt="
You are the Invalidation Library Selector. For each finding below, pick the 2-3 most applicable generic invalidation reasons from the library. These will be passed to verifier agents as adversarial hints.

## Findings to Screen

{FOR EACH SURVIVING FINDING, PASTE:}
### {HYPOTHESIS_ID}: {TITLE}
- **Severity**: {SEVERITY}
- **Location**: {LOCATION}
- **Root Cause**: {1-line root cause from hypotheses.md}
- **Attack Summary**: {2-3 sentence description}

## Invalidation Library

{PASTE FULL CONTENT OF {NEXTUP_HOME}/rules/invalidation-library.md}

## Your Task

For EACH finding, select the 2-3 invalidation reasons from the library that are MOST LIKELY to apply. You are NOT checking whether they actually hold — just selecting the most plausible candidates based on the finding's characteristics.

**Selection criteria**:
- Does the finding's attack path match the reason's pattern?
- Could the reason plausibly apply given the finding's description?
- Prefer reasons from different categories over multiple reasons from the same category

**Do NOT select reasons that are obviously irrelevant** (e.g., don't select 'flash loan fees' for a finding that doesn't involve flash loans).

## Output

For each finding:

```
### {HYPOTHESIS_ID}
1. **{REASON_ID}**: {REASON_TITLE} — {1 sentence why this might apply}
2. **{REASON_ID}**: {REASON_TITLE} — {1 sentence why this might apply}
3. **{REASON_ID}**: {REASON_TITLE} — {1 sentence why this might apply}
```

Return: 'DONE: {N} findings screened, {T} total invalidation hints assigned'
")
```

### Step 0b Output

Write agent output to `{SCRATCHPAD}/prescreen_invalidation_hints.md`.

---

## Step 0c: External Protocol Research (Sonnet, Conditional)

### Detection

Scan all surviving findings for references to external protocols. Check:
1. Finding descriptions mentioning external protocol behavior (oracle return values, exchange rates, redemption mechanics, fee structures)
2. Cross-reference with `{SCRATCHPAD}/design_context.md` external dependencies section
3. Cross-reference with `{SCRATCHPAD}/attack_surface.md` external interaction points

Common external protocols to detect: Chainlink, Uniswap, Aave, Compound, Lido, Pendle, Curve, Balancer, MakerDAO, Ethena, GMX, Morpho, EigenLayer, LayerZero, Pyth, Switchboard.

### If external dependencies found in findings

Spawn ONE sonnet agent to research ALL external claims in parallel:

```
Task(subagent_type="general-purpose", model="sonnet", prompt="
You are the External Protocol Research Agent. Several findings reference external protocol behavior. Your job is to verify these claims using web search.

## External Claims to Verify

{FOR EACH FINDING WITH EXTERNAL DEPENDENCY:}
### {HYPOTHESIS_ID}: {EXTERNAL_CLAIM}
- **Protocol**: {EXTERNAL_PROTOCOL_NAME}
- **Claim**: {what the finding assumes about external behavior — e.g., 'Chainlink returns 8 decimals for ETH/USD', 'Pendle expired PT redeems 1:1'}
- **Finding depends on this because**: {why the claim matters for the exploit}

## Instructions

For EACH claim:
1. Use WebSearch to find authoritative documentation
   - Search: '{protocol} {function_name} documentation'
   - Search: 'site:docs.{protocol} {topic}'
   - Search: '{protocol} {topic} audit finding'
2. Check audit reports or forum discussions
3. If WebSearch fails, try WebFetch on known docs URLs

## Output

For each claim:
```
### {HYPOTHESIS_ID}: {PROTOCOL} Claim
**Claim**: {the claim}
**Verified**: TRUE / FALSE / UNVERIFIABLE
**Evidence**: {links, doc quotes, on-chain references}
**Summary**: {2-3 sentences on actual behavior}
```

Return: 'DONE: {N} external claims researched, {V} verified, {F} false, {U} unverifiable'
")
```

### If no external dependencies found

Skip Step 0c. Set `EXTERNAL_RESEARCH = "No external protocol dependencies detected in findings."`

### Step 0c Output

Write agent output to `{SCRATCHPAD}/prescreen_external_research.md`.

---

## Injecting Pre-Screen Results into Verifiers

When the orchestrator spawns Phase 5 verification agents, each verifier's prompt is enriched with:

### 1. Invalidation Hints (from Step 0b)

Add this section to each verifier prompt, after the existing DUAL-PERSPECTIVE VERIFICATION section:

```
## ADVERSARIAL INVALIDATION HINTS (from pre-screen)

The following generic invalidation reasons were flagged as potentially applicable to this finding.
You MUST explicitly address each one during your defender-perspective analysis (Phase 2).
For each hint: either (a) confirm it holds with code evidence → lean toward FALSE_POSITIVE,
or (b) refute it with code evidence → proceed with verification.

{PASTE THE 2-3 HINTS FOR THIS FINDING FROM prescreen_invalidation_hints.md}

These are HINTS, not verdicts. A hint that HOLDS is strong evidence toward FALSE_POSITIVE.
A hint that FAILS is useful context but does not prove the finding is valid.
```

### 2. External Research (from Step 0c)

Add this section to verifier prompts for findings with external dependencies:

```
## EXTERNAL PROTOCOL RESEARCH (from pre-screen)

The following claims about external protocol behavior were researched via web search.
Use these VERIFIED facts over your own assumptions. If this research contradicts a
common assumption, trust the research.

{PASTE RELEVANT CLAIM RESULTS FROM prescreen_external_research.md}

If a claim is marked UNVERIFIABLE: any verdict that depends on assumptions about
{protocol}'s behavior MUST be CONTESTED, not CONFIRMED or FALSE_POSITIVE.
```

### 3. Anti-Hallucination Rule for External Claims

Add this rule to the ANTI-HALLUCINATION RULES section of ALL verification prompts:

```
7. Do NOT make confident claims about external protocol behavior (return values, decimals,
   exchange rates, redemption mechanics) based on your training data. If your verdict depends
   on how an external protocol's function behaves:
   - Use the External Protocol Research section above if available — trust it over assumptions.
   - If no research is available, and you cannot verify from in-scope code alone, your
     verdict MUST be CONTESTED, not CONFIRMED or FALSE_POSITIVE.
   - "I believe Protocol X's function Y always returns Z" is NOT evidence.
```

---

## Scratchpad Artifacts

| File | Written By | Contents |
|------|-----------|----------|
| `prescreen_early_exit.md` | Orchestrator (Step 0a) | Broken refs, trusted-actor caps, surviving count |
| `prescreen_invalidation_hints.md` | Sonnet selector (Step 0b) | 2-3 invalidation hints per finding |
| `prescreen_external_research.md` | Sonnet researcher (Step 0c) | External protocol claim verification results |

---

## Budget Impact

| Component | Cost | Model |
|-----------|------|-------|
| Early exit check | 0 (orchestrator inline) | - |
| Invalidation selector | 1 agent | sonnet |
| External research | 0-1 agent (conditional) | sonnet |
| **Typical total** | **1-2 agents** | |

The pre-screen typically saves more verification budget (by early-exiting broken refs and enriching verifiers to reach faster verdicts) than it costs.
