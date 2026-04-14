# Self-Check Checklists - C/C++

> **Usage**: Orchestrator reviews these checklists at the end of each phase to verify completeness before proceeding.

---

## After Recon (Before Phase 2)

- [ ] Build system detected (CMake / Make / Autoconf / Meson / Bazel / Conan)?
- [ ] Compiler identified (gcc / clang / MSVC) and version noted?
- [ ] Compilation with sanitizers attempted (or skip reason documented)?
- [ ] cppcheck run (or grep fallback documented if not installed)?
- [ ] clang-tidy run (or grep fallback documented if not installed)?
- [ ] All external dependencies identified (Conan conanfile.txt/py + CMake find_package + pkg-config)?
- [ ] All C/C++ security-relevant patterns detected (memory alloc, crypto, threading, network I/O, IPC)?
- [ ] Template recommendations include C/C++-specific skills (memory-safety, crypto-ops, concurrency)?
- [ ] BINDING MANIFEST present in template_recommendations.md?
- [ ] Known CVEs in identified dependencies checked (NVD / MITRE CVE search)?
- [ ] Language standard detected (C89/C99/C11/C17, C++11/14/17/20)? Standard affects which UB is defined.
- [ ] Custom memory allocator present? (if yes: flag for special analysis)

---

## After Breadth (Before Phase 4a)

- [ ] All REQUIRED templates have agents spawned?
- [ ] spawn_manifest.md created?
- [ ] All expected analysis_*.md files exist?
- [ ] Memory safety coverage: malloc/calloc/new allocation sites inventoried?
- [ ] Memory safety coverage: free/delete deallocation paths traced?
- [ ] Buffer operation coverage: all memcpy/strcpy/sprintf call sites catalogued?
- [ ] Integer safety: arithmetic on external input identified (overflow candidates)?
- [ ] Concurrency coverage (if THREADING flag): mutex/atomic usage mapped?
- [ ] Crypto coverage (if CRYPTO_OPS flag): constant-time operations, secret memory clearing checked?
- [ ] Signal handler safety: async-signal-safe functions only? No malloc/free in handlers?
- [ ] Format string usage: user input ever passed as format string to printf/fprintf/syslog?

---

## After Inventory (Phase 4a)

- [ ] Static analysis findings promoted to findings_inventory.md? (cppcheck/clang-tidy detectors)
- [ ] Memory ownership model traced for all major data structures?
- [ ] All pointer/buffer handoffs traced from source to consumer and deallocation?
- [ ] Elevated signals from attack_surface.md addressed in findings_inventory.md?
- [ ] Function pointer tables audited (vtables, callback arrays)? Are entries validated?
- [ ] Imported/exported symbols inventoried for shared libraries?

---

## After Adaptive Depth Loop (Phase 4b)

### Iteration 1
- [ ] All 4 depth agents spawned in a single parallel message?
- [ ] Blind Spot Scanner A spawned? (Memory & Buffer Operations)
- [ ] Blind Spot Scanner B spawned? (Type Safety & Integer Operations)
- [ ] Blind Spot Scanner C spawned? (Concurrency & Resource Management)
- [ ] Validation Sweep Agent spawned?
- [ ] Sanitizer campaign run (if Thorough mode AND CMakeLists.txt found AND tests found)?
- [ ] LibFuzzer campaign run (if harnesses exist, or generated for Thorough mode)?
- [ ] ThreadSanitizer run separately (if THREADING flag set in attack_surface.md)?
- [ ] Depth agents contain evidence tags ([BOUNDARY:*], [VARIATION:*], [TRACE:*])?
- [ ] phase4b_manifest.md written BEFORE agents spawned?
- [ ] Manifest verified after agents complete?

### Model Diversity (Thorough mode)
- [ ] depth-memory-ownership: opus?
- [ ] depth-state-trace: opus?
- [ ] depth-edge-case: sonnet?
- [ ] depth-external: sonnet?
- [ ] All scanners, validation sweep: sonnet?

### Confidence Scoring
- [ ] All findings have composite confidence scores?
- [ ] Dynamic budget cap applied (depth_floor + complexity adjustment, max 20)?
- [ ] confidence_distribution.md written with CONFIDENT/UNCERTAIN/LOW_CONFIDENCE breakdown?

### Iteration 2 (Thorough only - mandatory if any uncertain Medium+)
- [ ] If any uncertain Medium+ findings: iteration 2 micro-niche agents spawned?
- [ ] Spawn priority computed: (1 - confidence) x severity_weight?
- [ ] CHAIN_ESCALATED findings use effective_severity (Medium weight) not literal severity?
- [ ] No iteration 2 skip reasoning uses banned phrases ("for efficiency", "small codebase")?

### Iteration 3 (Thorough only - if progress made in iter 2)
- [ ] If progress in iteration 2: iteration 3 micro-niche agents spawned?
- [ ] Still-uncertain findings after iter 3 forced to CONTESTED if confidence < 0.4?

### Design Stress Testing (UNCONDITIONAL in Thorough mode)
- [ ] Design Stress Testing agent spawned at DONE regardless of budget?
- [ ] DST checked: max connections/threads behavior?
- [ ] DST checked: OOM (malloc NULL return) handling?
- [ ] DST checked: stack depth / recursion limits?
- [ ] DST checked: thread contention at maximum load?
- [ ] DST checked: queue/buffer overflow under load?

### C/C++ Security Rule Coverage
- [ ] CC1 (Buffer Overflow): All buffer/string operations bounds-checked?
- [ ] CC2 (Use-After-Free): All free()/delete'd pointers traced; no subsequent use?
- [ ] CC3 (Integer Overflow): All arithmetic on external input bounded with overflow check?
- [ ] CC4 (Timing Side Channels): Secret comparisons use constant-time functions (memcmp is NOT constant-time)?
- [ ] CC5 (Uninitialized Memory): All variables initialized before use (especially stack arrays)?
- [ ] CC6 (Format String): No user-controlled strings used as printf format argument?
- [ ] CC7 (Race Conditions): All shared mutable state protected by mutex or atomic?
- [ ] CC8 (Memory Leak): All allocation paths have matching deallocation on all exit paths?
- [ ] CC9 (Double-Free): No pointer freed twice; NULL assignment after free enforced?
- [ ] CC10 (Secret Clearing): Sensitive data cleared with explicit_bzero/SecureZeroMemory/OPENSSL_cleanse, NOT memset (which may be optimized away)?
- [ ] CC11 (Null Dereference): All pointer parameters NULL-checked before dereference?
- [ ] CC12 (Signed/Unsigned Mismatch): No silent sign-extension producing negative-as-large-positive?

---

## After Verification (Phase 5)

- [ ] PoC compilation successful with sanitizers enabled?
- [ ] Sanitizer output confirms finding (e.g., ASan reports heap-buffer-overflow at expected line)?
- [ ] For memory findings: valgrind/ASan run with PoC input shows violation?
- [ ] For crypto findings: timing measurements (perf stat / clock_gettime) demonstrate variance?
- [ ] For race conditions: TSan output confirms data race when PoC threads run concurrently?
- [ ] DUAL-PERSPECTIVE verification applied (confirm the bug AND confirm the exploit path)?
- [ ] ANTI-DOWNGRADE guard applied: scanner-confirmed findings ([SANITIZER-PASS]) cannot be downgraded without new contradicting evidence?
- [ ] For CONTESTED findings: specific evidence gap documented (what would be needed to confirm)?
