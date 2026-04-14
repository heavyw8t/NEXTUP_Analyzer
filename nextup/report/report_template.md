# NEXTUP Report Template

The final report is written by the Filter Agent to `{SCRATCHPAD}/findings.md`.

The orchestrator then prints a summary to the user:

```
=== NEXTUP Results ===
Mode: {lightweight|middleweight|heavyw8t}
Scope: {path}
Language: {language}

Pieces extracted: {N}
Combinations generated: {N}
After elimination: {N}
Hypotheses generated: {N}
Findings after filtering: {N}

Findings:
  Critical: {N}
  High:     {N}
  Medium:   {N}
  Low:      {N}
  Info:     {N}

Top findings:
  [NX-01] {title} (Critical, confidence: 85)
  [NX-02] {title} (High, confidence: 72)
  [NX-03] {title} (Medium, confidence: 60)

Full report: {SCRATCHPAD}/findings.md
```
