# Report Template

> **CRITICAL**: The final audit report MUST be written to `AUDIT_REPORT.md` in the project root.
> **This is the LAST step.** If writing before verification is complete, STOP and go back.

---

## ID System - MANDATORY

The report uses **clean sequential severity-prefixed IDs only**:
- Critical: `C-01`, `C-02`, ...
- High: `H-01`, `H-02`, ...
- Medium: `M-01`, `M-02`, ...
- Low: `L-01`, `L-02`, ...
- Informational: `I-01`, `I-02`, ...

**HARD RULES**:
1. **NO internal pipeline IDs** appear anywhere in the client-facing report. This means NO hypothesis IDs (H-1 from hypotheses.md), NO chain IDs (CH-1), NO agent finding IDs (CS-1, AC-2, TF-4, BLIND-3, EN-1, SE-1, VS-1, DEPTH-X-N, SLITHER-N), and NO mapping references. These are internal audit infrastructure, the reader has never seen them.
2. **NO cross-finding references inside a finding's body.** Do not write "see C-01", "related to H-03", "fixing L-02", "per M-02", or any other pointer to another finding by ID, inside the prose of any individual finding. Each finding must stand alone because contests are often judged one issue at a time and the reader of a given finding may not have seen the others. If the content of another finding is relevant, inline the relevant fact in plain language rather than pointing at an ID. The only place finding IDs may legitimately appear in the client-facing report is the top-level index/TOC that lists all findings.
3. Each severity tier numbers independently starting from 01.
4. The Index Agent (Step 6a) assigns these IDs. Tier writers and assembler use them as-is.

---

## Severity Matrix (Impact × Likelihood)

| | **Likelihood: High** (no prerequisites, anyone) | **Likelihood: Medium** (specific conditions) | **Likelihood: Low** (unlikely/complex setup) |
|---|---|---|---|
| **Impact: High** (direct fund loss/permanent lock) | **Critical** | **High** | **Medium** |
| **Impact: Medium** (conditional fund loss, protocol breakage) | **High** | **Medium** | **Medium** |
| **Impact: Low** (broken views, incorrect data, non-fund) | **Medium** | **Low** | **Low** |
| **Impact: Informational** (quality, style, unused code) | **Informational** | **Informational** | **Informational** |

**Downgrade modifiers** (applied after matrix lookup):
- On-chain-only exploit (no UI/off-chain path) → −1 tier. NOTE: this applies ONLY when the impact is confined to on-chain state. If the impact crosses the on-chain/off-chain boundary (e.g., corrupted events affecting indexers, frontends, or monitoring systems), do NOT downgrade.
- View-function-only impact → cap at Medium
- Attack path requires fully-trusted actor (per project's stated trust assumptions) to act maliciously → −1 tier (floor: Informational). This applies ONLY to `FULLY_TRUSTED` actors (governance multisig, DAO, timelock). Semi-trusted actors (admin, operator, keeper, oracle) are NOT downgraded here - their likelihood is already captured by the matrix ("specific conditions" or "unlikely/complex setup"). Finding is still reported with a note: *"Severity adjusted - attack requires {actor} to violate stated trust assumption: {assumption}."*

---

## Root-Cause Consolidation Rule

Findings that share the same root cause MUST be consolidated into a single finding. Same **variable** does not mean same root cause - if findings require **different fixes**, they are separate root causes.
- Use the **highest severity** from the matrix across all sub-impacts
- List each sub-impact as a bullet under **Impact**
- The **Location** field lists all affected sites
- Example: "Missing validation in `setFee()`" causing both overpayment and broken accounting → one finding, list both impacts

**Consolidated findings**: When the Index Agent merges multiple hypotheses into one report finding (same fix pattern + same severity + same vulnerability class), the tier writer MUST:
- Use a class-level title (e.g., "Missing event emission on admin state changes"), not a single-location title
- List ALL affected locations in a table under **Location**:
  ```
  | Contract | Function | Line | Issue |
  |----------|----------|------|-------|
  ```
- Provide ONE consolidated recommendation covering all locations
- Reference the Consolidation Map in report_index.md for the internal hypothesis list

---

## Finding Section Format - MANDATORY FOR EVERY FINDING

Every finding gets its own full section. No catch-all tables, no grouped summaries, no "remaining findings" dumps. A finding that only appears in a table row is effectively invisible to the reader.

The finding body follows the Sherlock six-section schema. Inside the consolidated audit document, the finding is wrapped by an H3 title header (`### [X-NN] Title [status]`) and the six sub-sections are labeled with bold-italic markers (`***Label***`) on their own line, because `###` inside a section body is banned. When a finding is extracted to a standalone file for contest submission, the H3 title becomes the H1, and the `***Label***` markers become H2 (`## Summary`, `## Root Cause`, etc.).

```markdown
### [X-NN] Title [VERIFIED/UNVERIFIED/CONTESTED]

Severity: Critical/High/Medium/Low/Informational
Location: `SourceFile.ext:L123-L145`
Confidence: HIGH/MEDIUM/LOW (N agents confirmed, Static Analysis: Y/N, PoC: PASS/FAIL/SKIPPED)

***Summary***

[One short paragraph: core bug, consequence, severity claim with the Sherlock threshold met. State severity once here. No separate severity-justification subsection anywhere in the finding.]

***Root Cause***

[Intended behavior, actual behavior, specific code site that diverges. Line-number anchors appear only in this section. This is the ONLY sub-section where `file.ext:NNN`, `file.ext:NNN-MMM`, `file.ext:N,M`, or any other numeric line callout may appear. Every other sub-section (Summary, Impact, Attack Path, Mitigation, Proof of Concept) must refer to code by file name alone, by function/method name, or by descriptive role ("the deposit transactor", "the fee-commit block"). The top-level `Location:` metadata field at the head of the finding is exempt and may contain a line range.]

***Impact***

[Who loses, quantified with a small realistic example (e.g. $1,000 transfer losing $20 to a 2% fee). No marketcap-scale projections; judges discount exaggerated numbers. State the percentage that carries the severity argument. Consequences only, no mechanism.]

***Attack Path***

[Numbered steps, one or two sentences each, with concrete parameter values. A reader should be able to reproduce the attack from the steps.]

***Mitigation***

[One primary fix, optionally one alternative. Two to three sentences per option. Prescriptive, not suggestive.]

***Proof of Concept***

[Runnable test or script, or "See Attack Path" if the attack path is itself fully reproducible.]
```

Word budgets (hard caps, applied to the text inside each sub-section, excluding PoC code):

| Section | Critical / High | Medium |
| ------- | --------------- | ------ |
| Summary | ≤ 80 words | ≤ 40 words |
| Root Cause | ≤ 120 words | ≤ 70 words |
| Impact | ≤ 100 words | ≤ 40 words |
| Attack Path | ≤ 150 words | ≤ 80 words |
| Mitigation | ≤ 80 words | ≤ 40 words |
| Body total (excluding PoC) | ≤ 500 words | ≤ 250 words |

Shorter is better when still complete. If a section runs over, cut content; never split into a new sub-section.

Content rules:
1. Severity is stated once, inside Summary. The Impact section quantifies loss in percent and USD; the numbers carry the threshold argument by themselves. No separate "Severity justification" block.
2. Impact describes consequences, not mechanism. If a sentence explains how the bug fires, it belongs in Root Cause or Attack Path.
3. One concrete example per finding, total. If Attack Path has numbered steps with realistic values, do not add a separate example block.
4. Impact numbers stay small and realistic (e.g., "$1,000 transfer loses $20 at 2% fee"). Avoid marketcap-scale projections, adoption-rate scenarios, or multi-year annualized losses. The percentage carries the severity argument; the dollar figure is illustrative, not the argument.
5. Tables cap at 5 rows. If the pattern is monotonic, show a 5-row representative slice plus the closed-form formula.
6. No historical or framing paragraphs. Delete "net new under upgrade X", "pre-upgrade this worked differently", "first time X meets Y" unless it materially changes the severity argument.
7. Mitigation gives at most two options. 2-3 sentences each.
8. First sentence of every sub-section must stand alone. A reader skimming only openings should still understand the finding.

Formatting rules:
1. Line-number anchors appear only in Root Cause. This applies to every numeric line reference, in any syntactic form: `file.ext:NNN`, `file.ext:NNN-MMM`, `file.ext:N,M`, `L123`, `line 184-195`, "at lines 69 and 87", or any other prose that names a line number. Summary, Impact, Attack Path, Mitigation, Proof of Concept, and any trailing Anchors/Evidence block must refer to code by file name alone, by function/method name (`AMMVote::applyVote`), or by descriptive role ("the deposit transactor", "the fee-commit block"). The top-level `Location:` metadata field at the head of the finding is the one exception and may contain a line range. The writer must scan every sub-section after drafting and strip any stray numeric line callout; it is a mechanical check, not a judgment call.
2. No cross-finding references inside a finding's body. No "see C-01", "related to H-03", "fixing L-02", or any other ID pointer inside the prose of any individual finding. Each finding stands alone. This applies to both internal pipeline IDs and final report IDs. The only place finding IDs may legitimately appear in the client-facing report is the top-level index, TOC, and Priority Remediation Order list.
3. At most one file reference per sentence. Split or reword if naming two files or two line ranges.
4. File and function names go in backticks. Do not bold them.
5. Sub-section labels use `***Label***` on their own line, never `###`, never plain `**Label**`.
6. Chain findings: describe the full attack sequence inside this finding's Attack Path. Do not point the reader at sibling findings to understand the chain. Inline the relevant facts.
7. Include actual problematic code in PoC, not just a line reference.

Before vs after example (Impact section, showing the bloat pattern this template exists to prevent):

Before (168 words, cluttered with file references and projections, reads as exaggerated):

> The AMM fee waiver at `AMMDeposit.cpp:592-599` and `AMMWithdraw.cpp:665-666` means that every transfer routed through the wrap pays the issuer zero `TransferFee`. Acme Corp, a hypothetical MPT issuer with 10,000 daily active wallets moving an aggregate $10M/day in ACME, has expected fee revenue of $200k/day, or $73M/year. At 10% adoption the annual loss is $7.3M. At 50% adoption, $36.5M. At 100% adoption the issuer sees $0 in fee revenue. The code path is in `AMMDeposit.cpp`, `AMMWithdraw.cpp`, and `AMMHelpers.cpp`, all of which hard-code `WaiveTransferFee::Yes` on the external legs. Meets Sherlock Critical per the official severity definition.

After (62 words, same information, credible, no redundant file references):

> Every laundered transfer pays the issuer zero `TransferFee`, a 100% loss of the configured fee on that transfer. A $1,000 transfer at a 2% `TransferFee` costs the issuer $20 per event. The bypass is repeatable without limit and works against any MPT with non-zero `TransferFee`. Loss clears the Sherlock Critical thresholds on any transfer of $5,000 or more at 2%.

The after version drops redundant file anchors (they belong in Root Cause), drops the adoption-scenario projections (they hurt credibility), and drops the Sherlock-criteria meta-commentary (implicit from the numbers).

---

## Report Structure

```markdown
# Security Audit Report - [Project Name]

**Date**: [YYYY-MM-DD]
**Auditor**: Automated Security Analysis (Claude Opus 4.6)
**Scope**: [description]
**Language/Version**: [language and version]
**Build Status**: [Compiled successfully / Failed - reason]
**Static Analysis Status**: [Available / Unavailable - reason]

---

## Executive Summary

[2-3 paragraph overview: what the protocol does, what was found at a high level, and the most critical risks. Written for a non-technical stakeholder.]

## Summary

| Severity | Count |
|----------|-------|
| Critical | [count] |
| High | [count] |
| Medium | [count] |
| Low | [count] |
| Informational | [count] |

### Components Audited

| Component | Path | Lines | Description |
|----------|------|-------|-------------|

---

## Critical Findings

### [C-01] Title [VERIFIED]
[Full finding section per format above]

### [C-02] Title [VERIFIED]
[Full finding section]

---

## High Findings

### [H-01] Title [VERIFIED/UNVERIFIED/CONTESTED]
[Full finding section]

### [H-02] Title [VERIFIED/UNVERIFIED/CONTESTED]
[Full finding section]

[... every High finding gets its own section ...]

---

## Medium Findings

### [M-01] Title [VERIFIED/FALSE_POSITIVE/CONTESTED]
[Full finding section]

### [M-02] Title [VERIFIED/FALSE_POSITIVE/CONTESTED]
[Full finding section]

[... every Medium finding gets its own section ...]

---

## Low Findings

### [L-01] Title
[Full finding section - Recommendation field optional for Low]

### [L-02] Title
[Full finding section]

[... every Low finding gets its own section ...]

---

## Informational Findings

### [I-01] Title
[Full finding section - PoC Result field optional for Informational]

[... every Informational finding gets its own section ...]

---

## Priority Remediation Order

[Numbered list from most to least urgent. Use report IDs only.]

1. **C-01**: [one-line reason] - Immediate
2. **C-02**: [one-line reason] - Immediate
3. **H-01**: [one-line reason] - Before launch
...

---

## Appendix A: Internal Audit Traceability (Optional)

> **NOTE**: This appendix is for the audit team's internal reference only. It maps internal pipeline IDs to report IDs. It is NOT required for the client and may be omitted from client-facing deliverables.

| Report ID | Internal Hypothesis | Chain | Verification | Agent Sources |
|-----------|-------------------|-------|--------------|---------------|
| C-01 | [internal ref] | [chain ref] | CONFIRMED | [agent list] |
| H-01 | [internal ref] | - | CONFIRMED | [agent list] |
| ... | ... | ... | ... | ... |

### Excluded Findings

| Internal ID | Severity | Title | Exclusion Reason |
|-------------|----------|-------|-----------------|
| [internal ref] | Medium | [title] | FALSE_POSITIVE - verified not exploitable |
| [internal ref] | Low | [title] | Duplicate of M-03 |
```

---

## Quality Gates

Before the report is considered complete, verify:

1. **Every finding has its own section** - no finding exists only in a table row
2. **No internal IDs in body** - search the report for patterns like `[CS-`, `[AC-`, `[TF-`, `[BLIND-`, `[EN-`, `[SE-`, `[VS-`, `[DEPTH-`, `[SLITHER-`, `CH-`, and hypothesis `H-` followed by a number in brackets. NONE should appear outside Appendix A.
3. **Finding count matches summary** - the number of `###` sections per severity tier equals the count in the summary table
4. **No cross-finding references in finding bodies** - search each finding's sub-sections (`***Summary***` through `***Proof of Concept***`) for patterns like `see C-`, `see H-`, `see M-`, `see L-`, `see I-`, `related to`, `per C-`, `per H-`, etc. NONE should appear inside a finding's body. Finding IDs may appear only in the top-level index, severity tables, and Priority Remediation Order list.
5. **Severity consistency** - if a verifier downgraded/upgraded a finding, the report reflects the FINAL severity, not the original hypothesis severity
