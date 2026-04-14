# Smart Contract Audit Report Writing Primer
## For Sherlock Style Contest Reports (Extended: C/H/M/L/I)

---

## OVERVIEW

This primer defines the professional structure and style for writing smart contract vulnerability reports across severity levels: **Critical (C)**, **High (H)**, **Medium (M)**, **Low (L)**, and **Informational (I)**. Use this as input for LLMs to generate consistent, concise reports matching Sherlock's judging standards, extended to include Critical (catastrophic / protocol-ending) and Low/Informational (hardening, defense-in-depth) tiers.

**Key Principle**: Match each report's severity framing to the realistic worst-case impact. Critical = catastrophic or protocol-ending loss. High = direct loss of funds. Medium = loss with constraints / broken core functionality. Low = minor loss, limited impact, or defense-in-depth. Informational = no direct impact, best-practice notes.

Try to find the most severe possible impact the issue can realistically have.

---

## FILE NAMING CONVENTION (MANDATORY)

Each finding is written to its own file. File names MUST use severity-prefixed sequential IDs, zero-padded to 2 digits:

- Critical: `C-01.md`, `C-02.md`, ...
- High: `H-01.md`, `H-02.md`, ...
- Medium: `M-01.md`, `M-02.md`, ...
- Low: `L-01.md`, `L-02.md`, ...
- Informational: `I-01.md`, `I-02.md`, ...
- **Unclassified**: `U-01.md`, `U-02.md`, ... (see below)

Numbering resets per severity tier. Ordering within a tier: descending impact. The `SUMMARY.md` index groups findings by severity in the order C → H → M → L → I → U.

The finding's internal Title line MUST match its filename prefix (e.g., `# C-01 · [Title]`, `# H-03 · [Title]`, `# U-02 · [Title]`).

## UNCLASSIFIED (`U-NN`) — PRIMER NEVER DROPS FINDINGS

The primer governs **format and prose**, never validity or severity. If a finding cannot be cleanly classified under C/H/M/L/I using this primer's rubric — e.g., impact falls outside Sherlock's "direct protocol loss" scope, or the finding is systemically important but does not map to any severity-tier template — it MUST be written as `U-NN.md`, not dropped and not downgraded to force a fit.

Every `U-NN.md` file MUST include, immediately after the title:

```
**Unclassified reason:** {one sentence explaining why the primer could not classify it}
```

Example: `**Unclassified reason:** Primer's Sherlock rubric measures direct LP/protocol loss; this finding harms a third-party MPT issuer's compliance/tax revenue via AMM-internal transfer-fee waivers, which falls outside the rubric's scope.`

Everything else (Title, Locations, Root Cause, Impact, Attack Path, Mitigation) follows the structure of the closest-matching severity template. Record the Skeptic-Judge / verifier's original severity verdict inside the file body so downstream consumers can re-tier the finding under a different primer.

Only INVALIDATED (Skeptic-Judge logic-level refutation) and pre-screen REJECTED findings are excluded from the output directory entirely. Those exclusions are never primer-driven.

---

## UNIVERSAL STRUCTURE & STYLE GUIDELINES

### **General Principles**
- **Professional & Concise**: Every word serves a purpose; eliminate redundancy
- **Technical Precision**: Use exact terminology; avoid vague language
- **Proof-Driven**: Back claims with code references, concrete examples, and scenarios
- **Security-Focused**: Emphasize impact on protocol/users, not theoretical abstractions
- **Sherlock-Aligned (extended)**: Critical — catastrophic / protocol-ending (>10% of TVL, full insolvency, unbounded mint, or full governance seizure). High — >1% AND >$10. Medium — >0.01% AND >$10 OR broken core functionality. Low — quantifiable but minor loss, defense-in-depth, or loss requiring extensive external conditions. Informational — no direct loss; best-practice / hardening.
- **Structured Flow**: Each section builds logically toward the mitigation

---

## SECTION TEMPLATES BY SEVERITY

---

## **CRITICAL SEVERITY REPORTS** (Complete Structure)

### **1. Title**
- **Format**: `[Vulnerability Type]: [Catastrophic outcome description]`
- **Examples**:
  - "Unbounded Mint Authority Lets Attacker Drain Entire Protocol TVL in One Transaction"
  - "Governance Capture via Single-Ledger Flash-Vote Cycle, Enabling Permanent Fee Seizure"
- **Length**: 1 clear sentence, outcome-focused, catastrophic

### **2. Summary** (50-70 words)
- **Open with**: The core vulnerability in one sentence
- **Then state**: The catastrophic consequence in 1-2 sentences
- **State Critical threshold**: Protocol-ending, irreversible, or >10% TVL loss
- **Example**: "A missing access-control check on the fee-vault withdrawal path lets any caller drain the entire fee vault in a single transaction. This extracts >10% of protocol TVL irreversibly, exceeds $10+, and leaves no recovery path short of redeployment, meeting Critical severity thresholds."
- **Avoid**: Explaining HOW it works (that's for Root Cause)

### **3. Root Cause** (100-150 words)
- **Answer**: Why does this vulnerability exist?
- **Structure**:
  1. Identify the intended invariant / access pattern
  2. Identify what actually happens
  3. Point to the specific code / logic failure
- Include: file names, function names, line anchors

### **4. Impact** (80-120 words)
- **Quantify precisely**: Dollar amounts, percentage of funds at risk, number of users affected, reversibility
- **Meet Critical thresholds**: Explicitly state protocol-ending / >10% TVL / unrecoverable
- **Structure**:
  1. Direct impact (quantified loss)
  2. Cascading effects (downstream systems, other markets)
  3. Severity justification (why Critical, not High — irreversibility, magnitude, ease of exploitation)

### **5. Attack Path** (120-200 words, numbered steps)
- Step-by-step, concrete transaction values, reproducible
- Include any pre-conditions and setup phases
- Show exactly which state transitions break which invariants

### **6. Mitigation** (60-100 words)
- Prescriptive: exact code pattern, architectural fix, or multi-site change
- If the fix requires coordinated changes across several locations, enumerate them
- Address any edge cases and new failure modes introduced

---

## **HIGH SEVERITY REPORTS** (Complete Structure)

### **1. Title**
- **Format**: `[Vulnerability Type]: [Clear, outcome-focused description]`
- **Examples**:
  - "Intent Orders Are Guaranteed to Execute But Fees Are Not Accounted in Collateral"
  - "Vault Executes Swaps Without Slippage Protection, Causing Direct Loss of Funds"
  - "Users Can Abuse Oracle Discrepancies to Mint More OHM Than Needed"
- **Length**: 1 clear sentence, outcome-focused, measurable

### **2. Summary** (40-60 words)
- Open with the core vulnerability, then the consequence
- **State Sherlock threshold**: Confirm loss meets >1% AND >$10

### **3. Root Cause** (80-120 words)
- Intended behavior → actual behavior → code/logic failure
- Include file/function/line anchors

### **4. Impact** (60-100 words)
- Quantify: dollar amounts, % of funds, users affected
- State >1% AND >$10; justify High vs Medium (direct loss, no extensive conditions)

### **5. Attack Path** (100-150 words, numbered steps)
- Step-by-step, specific parameter values, reproducible

### **6. Mitigation** (50-80 words)
- Prescriptive code pattern or architectural fix

---

## **MEDIUM SEVERITY REPORTS** (Complete Structure)

### **1. Title**
Same as High; focus on outcome.

### **2. Summary** (20-30 words)
- State Sherlock threshold: >0.01% AND >$10 OR broken core functionality

### **3. Root Cause** (50-100 words)
- Explain the design choice or implementation gap

### **4. Impact** (20-30 words)
- Magnitude: fee loss, users affected, broken-functionality scope

### **5. Attack Path** (30-80 words, numbered steps)
- Include constraints/conditions required for Medium classification

### **6. Mitigation** (20-30 words)
- Prescriptive fix

---

## **LOW SEVERITY REPORTS** (Compact Structure)

Low findings represent minor, constrained, or defense-in-depth issues. Keep them short but still reproducible.

### **1. Title**
Outcome-focused, honest about limited impact.

### **2. Summary** (15-25 words)
- One sentence on the issue; one sentence on the bounded consequence
- State why NOT Medium: constraints too extensive, loss below Medium threshold, or no direct financial loss but hardening warranted

### **3. Root Cause** (40-80 words)
- Brief: intended vs actual; file/function anchor

### **4. Impact** (15-30 words)
- Bounded scope; quantify if possible; explicitly note why this is Low not Medium

### **5. Attack Path or Trigger Scenario** (30-60 words, numbered or prose)
- Show the path briefly; OK to skip Attack Path if the issue is non-adversarial (e.g., edge-case rounding)

### **6. Mitigation** (15-30 words)
- One- to three-line fix

---

## **INFORMATIONAL REPORTS** (Minimal Structure)

Informational findings have no direct loss but are worth recording for hygiene, documentation, or future-proofing.

### **1. Title**
Short, descriptive (e.g., "Redundant zero-amount check in AMMDeposit::applyGuts").

### **2. Summary** (10-20 words)
- State the observation and why it matters (code smell, future refactor risk, docs gap)

### **3. Details** (30-60 words)
- What is happening, where (file/line), and what it means
- Explicitly note: no direct financial impact

### **4. Recommendation** (10-25 words)
- One-line improvement

Note: Informational findings should NOT claim exploitability. If they do, re-classify them as Low or higher.

---

## FORMATTING RULES

1. **Filename**: `{C|H|M|L|I}-NN.md` zero-padded (e.g. `C-01.md`, `H-03.md`, `L-12.md`).
2. **Internal Title**: `# {C|H|M|L|I}-NN · [Title]` matching the filename.
3. **Headings**: Use markdown `##` for main sections, `###` for subsections
4. **Code References**: Backticks for function names, file names, line anchors (`file.cpp:123`)
5. **Numbers**: Spell out single digits (one, two), numerals for larger values
6. **Emphasis**: **bold** for key vulnerability concepts, *italics* for technical nuance
7. **Thresholds**: Explicitly state Sherlock-extended criteria met (Critical / >1% AND >$10 / >0.01% AND >$10 / bounded-Low / Info-only)
8. **Avoid**:
   - Passive voice (use active: "the protocol loses funds" not "funds are lost")
   - Jargon without explanation
   - Speculation ("could potentially"); use certainties ("does")
   - Repetition across sections

---

## CHECKLIST FOR REPORT QUALITY

- Filename matches severity prefix and internal title
- Title is outcome-focused
- Summary is a complete thought, not a fragment
- Severity threshold explicitly stated and justified:
  - **Critical**: catastrophic / protocol-ending / >10% TVL / unrecoverable
  - **High**: >1% AND >$10, no extensive preconditions
  - **Medium**: >0.01% AND >$10 OR broken core functionality
  - **Low**: bounded loss OR defense-in-depth OR extensive preconditions
  - **Informational**: no direct loss; hygiene / hardening / future-proofing
- Root Cause explains WHY, not WHAT
- Attack Path / Trigger Scenario is present where severity requires it (Critical/High/Medium mandatory; Low optional; Informational not required)
- Mitigation is prescriptive
- No section repeats another
- Claims backed by code references or mathematical proof
- Active voice throughout
- Precise language ("does", not "could")
- Word count within target range for severity
- Professional tone maintained
- Critical findings justify the step up from High (irreversibility / magnitude / ease)
- Low findings justify the step down from Medium (below threshold / extensive preconditions)
- Informational findings do NOT claim exploitability

---

## FINAL NOTES

- **Consistency is key**: Use this primer for every report to maintain professional quality
- **Full-severity coverage**: Emit reports across C/H/M/L/I — do NOT silently drop Low/Info
- **Adapt, don't copy**: Templates are guides; customize language to your vulnerability
- **Rigor matters**: Every claim must be defensible; back it with code or math
- **Quantification essential**: Dollar amounts and percentages are critical — estimates acceptable if clearly marked
- **Brevity is power**: Remove all unnecessary words while maintaining clarity
- **Security first**: Frame everything through impact on protocol/users

---

## SEVERITY REFERENCE (EXTENDED)

**Critical**: Catastrophic or protocol-ending loss. Examples: unbounded mint, full treasury drain, full governance seizure, unrecoverable insolvency, corruption of consensus-critical state. Typically >10% TVL, irreversible, or systemically fatal.

**High**: Direct loss of funds >1% AND >$10 without extensive external conditions, or permanently frozen funds.

**Medium**: Loss of funds >0.01% AND >$10 requiring constraints, OR broken core functionality (DOS), OR temporarily frozen funds.

**Low**: Quantifiable but minor loss; OR loss requiring extensive/unlikely preconditions; OR defense-in-depth hardening with a concrete code anchor.

**Informational**: No direct loss. Code hygiene, redundant checks, documentation gaps, future-refactor hazards, stylistic divergence from elsewhere in the codebase.

**Invalid per Sherlock**: Gas optimization, zero address checks, UX issues, admin mistakes, incorrect event values, front-running initializers, design decisions without loss.
