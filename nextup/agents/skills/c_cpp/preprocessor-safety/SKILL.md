---
name: "preprocessor-safety"
description: "Trigger Complex macro definitions detected (>10 non-trivial macros) - Macro safety and preprocessor hazard audit"
---

# Skill: PREPROCESSOR_SAFETY

> **Trigger**: Complex macros detected (function-like macros, multi-line macros, macros with side effects)
> **Covers**: Macro side effects, double evaluation, include order dependencies, conditional compilation hazards
> **Required**: NO (P2 priority, recommended when heavy macro usage detected)

## Trigger Patterns

```
#define.*\(|#define.*\\$|##|#if.*def|__attribute__|_Pragma|do\s*\{.*\}\s*while\s*\(0\)
```

## Reasoning Template

### Step 1: Macro Inventory

| # | Macro Name | Type | Arguments | Side Effects? | File:Line |
|---|-----------|------|-----------|-------------|-----------|
| 1 | {name} | Function-like/Object-like | {args} | YES/NO | {loc} |

**Categorize**:
- **FUNCTION_LIKE**: Takes arguments, expands to expression or statement
- **OBJECT_LIKE**: No arguments, expands to constant or expression
- **STRINGIFY**: Uses `#` operator
- **CONCAT**: Uses `##` token-pasting operator
- **MULTI_STATEMENT**: Expands to multiple statements (requires `do { } while(0)`)

### Step 2: Double Evaluation

For each function-like macro with arguments:
- [ ] Is any argument used more than once in the expansion?
- [ ] If yes: does the argument have side effects when passed? (e.g., `MAX(i++, j++)`)
- [ ] Is the macro used in performance-critical paths where the double-call cost matters?

Safe alternatives: inline function, template function, constexpr

| Macro | Argument Used N Times | Example Dangerous Call | Safe Alternative |
|-------|----------------------|----------------------|-----------------|

### Step 3: Macro Hygiene

For each function-like macro:
- [ ] Are macro arguments parenthesized in expansion? `(a) + (b)` not `a + b`
- [ ] Is the entire macro expression parenthesized? `((a) + (b))` not `(a) + (b)`
- [ ] Do multi-statement macros use `do { ... } while(0)` pattern?
- [ ] Are temporary variables in macros uniquely named? (use `__LINE__` suffix or GCC statement expressions)
- [ ] Does the macro introduce a dangling `else` hazard? (single-statement if without braces)

| Macro | Missing Parens? | Missing do-while? | Dangling else? |
|-------|---------------|------------------|---------------|

### Step 4: Conditional Compilation Safety

- [ ] Are there `#ifdef` guards that change security-critical behavior?
- [ ] Can a build configuration disable security checks? (e.g., `#ifdef NDEBUG` removing assertions, `#ifdef DEBUG` enabling unsafe logging)
- [ ] Are there platform-specific code paths (`#ifdef _WIN32`, `#ifdef __linux__`) with different security properties?
- [ ] Are there `#include` order dependencies that can change behavior if headers are reordered?
- [ ] Do any macros redefine standard library functions (e.g., `#define malloc my_malloc`) that could bypass security wrappers?

| Guard | Security-Critical Behavior Change | Build Config That Disables | Risk |
|-------|----------------------------------|--------------------------|------|

### Step 5: Token-Pasting and Stringification Hazards

For macros using `##` or `#`:
- [ ] Can token-pasting produce syntactically invalid tokens that only fail at specific instantiations?
- [ ] Can stringification capture sensitive data (keys, passwords) in error messages or logs?
- [ ] Are variadic macros (`__VA_ARGS__`) used safely (no format string injection)?

## Output Schema

```markdown
## Finding [MACRO-N]: Title

**Verdict**: CONFIRMED / PARTIAL / REFUTED
**Step Execution**: checkmark1,2,3,4,5 | xN(reason) | ?N(uncertain)
**Severity**: Critical/High/Medium/Low/Info
**Location**: file.h:LineN

**Macro Name**: {name}
**Hazard Type**: DOUBLE_EVAL / MISSING_PARENS / MISSING_DO_WHILE / CONDITIONAL_DISABLE / TOKEN_PASTE
**Example Dangerous Invocation**: {code showing how macro can be misused}

**Description**: What's wrong with the macro
**Impact**: What can go wrong (wrong result, buffer overflow, security check bypass)
**Recommendation**: Replace with inline function / add parentheses / use do-while / use constexpr
```

## Step Execution Checklist

- [ ] Step 1: ALL function-like and multi-statement macros enumerated
- [ ] Step 2: Double evaluation checked for every argument of every function-like macro
- [ ] Step 3: Hygiene (parens, do-while, dangling else) verified for each macro
- [ ] Step 4: Conditional compilation guards checked for security-behavior changes
- [ ] Step 5: Token-pasting and variadic macro hazards assessed
