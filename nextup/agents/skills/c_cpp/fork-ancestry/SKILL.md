---
name: "fork-ancestry"
description: "Trigger Always (run during recon TASK 0) - Research protocol's fork lineage and known vulnerabilities"
---

# Skill: FORK_ANCESTRY

> **Trigger**: Always (run during recon)
> **Covers**: Known vulnerabilities in upstream code, patches not applied, divergence from upstream
> **Required**: NO (recommended for all audits)

## Trigger Patterns

Always run during recon phase.

## Reasoning Template

### Step 1: Identify Upstream

- Check git history for fork point (`git log --oneline --follow` on key files)
- Check README/docs for "based on", "forked from", "derived from" references
- Check build files (CMakeLists.txt, configure.ac, Makefile) for upstream library versions
- Identify vendored third-party code in `third_party/`, `vendor/`, `deps/`, `external/` directories

| Component | Upstream Project | Upstream Version | Fork Point (date/commit) |
|-----------|----------------|-----------------|-------------------------|

### Step 2: Known Vulnerability Research

Use WebSearch to find:
- CVEs for the upstream project and identified version
- Security advisories (GitHub Security Advisories, NVD, OSS-Fuzz reports)
- Past audit reports for upstream (search for "{project} audit" or "{project} security review")
- Known exploit PoCs

| CVE/Advisory | Severity | Description | Affected Versions | This Fork Affected? |
|-------------|---------|-------------|------------------|-------------------|

### Step 3: Patch Analysis

For each known vulnerability in upstream:
- [ ] Is the fix present in this fork? (search for the fix commit's changed lines)
- [ ] Was the fix modified after being applied (potentially breaking it)?
- [ ] Are there other instances of the same vulnerable pattern? (grep for the pattern)

| Vulnerability | Fix Applied? | Fix Intact? | Other Instances? |
|--------------|------------|------------|-----------------|

### Step 4: Divergence Risk

Identify areas where the fork diverges from upstream in security-sensitive ways:
- [ ] Are security-relevant upstream commits (post-fork) missing from this fork?
- [ ] Has the fork modified upstream's security-critical functions?
- [ ] Are there local patches that disable upstream safety checks?

| Divergence | File | Nature | Security Impact |
|-----------|------|--------|----------------|

## Output Schema

```markdown
## Finding [FORK-N]: Title

**Verdict**: CONFIRMED / PARTIAL / REFUTED
**Step Execution**: checkmark1,2,3,4 | xN(reason) | ?N(uncertain)
**Severity**: Critical/High/Medium/Low/Info
**Location**: file.c:LineN (or "entire codebase" for lineage findings)

**Upstream Project**: {name and version}
**CVE/Advisory**: {identifier or N/A}
**Patch Status**: MISSING / PARTIAL / APPLIED / NOT_APPLICABLE

**Description**: What vulnerability exists in upstream and whether it affects this fork
**Impact**: What an attacker can do exploiting this issue
**Recommendation**: Apply upstream patch / backport fix / update to patched version
```

## Step Execution Checklist

- [ ] Step 1: Upstream project and version identified from git history and build files
- [ ] Step 2: CVEs and advisories researched via WebSearch for identified upstream and version
- [ ] Step 3: Each known vulnerability checked for patch presence in this fork
- [ ] Step 4: Security-relevant divergences from upstream documented
