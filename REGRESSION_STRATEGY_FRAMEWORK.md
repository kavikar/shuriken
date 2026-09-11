# Risk-Based Regression Testing Strategy
## For Resource-Constrained Releases with Historical Defect Awareness

---

## Problem Statement
- **Unlimited test scope** vs **limited manpower** → impossible to test everything
- **Old defects** indicate systemic risk areas that need focused validation
- **Release scope** (stories/bugs) tells us *what changed* but not *what could break*
- **Goal**: Maximize defect detection with ~60–80% of "ideal" coverage using ~40–50% of resources

---

## 1. **Risk-Based Test Prioritization** (Triage First)

### Tier 1: **Critical Path + Risk Zones** (Run 100%, ~20–30% of all tests)
These test cases **must always run** regardless of budget constraints:

#### A. User Journey Criticality
- **Sign Up / Sign In / Authentication** → If broken, nothing works
- **Add to Bag / Checkout / Payment** → Core revenue path
- **Store Selection / Fulfillment Type** → Determines order feasibility
- **Reorder** → High user volume; regression common

#### B. Component-Level Risk (from DOVS data)
Based on the DOVS Digital 26.12 scope, these areas have **frequent defects**:

| Component | Recent Bug Count | Priority | Typical Impact |
|-----------|------------------|----------|---|
| `GENERIC_Account_Management` | 8 | **CRITICAL** | Sign-up fails, phone validation, MFA |
| `GENERIC_Loyalty` | 12 | **CRITICAL** | Rewards don't apply, points wrong, badges broken |
| `GENERIC_Payments` | 8 | **CRITICAL** | Gift cards fail, payment methods missing |
| `GENERIC_Ordering` | 7 | **CRITICAL** | Reorder fails, modifiers wrong, tally errors |
| `GENERIC_Fulfillment` | 5 | **HIGH** | Slot selection, pickup window, buffer issues |
| `GENERIC_Order_History` | 5 | **HIGH** | Data migration, spacing, price display |
| `GENERIC_Accessibility` | 2 | **MEDIUM** | WCAG, screen reader, testID coverage |
| `GENERIC_POS_Integration` | 1 | **MEDIUM** | POS sync, modifier rendering (brand-specific) |

**Action**: Build **Tier 1 TE** from tests tagged with above components. Estimate: **~80–120 tests** per platform (Web/App).

---

### Tier 2: **Feature-Interaction + Brand Deltas** (Run ~70%, ~30–40% of tests)
Run tests for:
- **Cross-component scenarios** (e.g., Auth → Bag → Checkout, Loyalty → Redemption → POS)
- **Brand-specific behavior** (Brand Four' loyalty cadence ≠ Brand Three; Brand One menus unique)
- **Known problem zones** from last 3 releases (collect defect clusters)

**Action**: Tag tests with:
```
labels: ["regression", "cross-functional"]
components: ["GENERIC_Loyalty", "GENERIC_Fulfillment"]  # multiple components = interaction test
```

Estimate: **~120–180 tests** per platform.

---

### Tier 3: **Nice-to-Have Coverage** (Run if time permits, ~50–60% of tests)
- Edge cases (empty state, max limits, offline modes)
- Accessibility (WCAG, keyboard nav)
- Visual regression (spacing, alignment, branding)
- Performance (slow network simulation)

**Action**: Gate with **Feature Flag** in TE creation:
```json
{
  "testExecutionKey": "TE-XXXX",
  "tier": "tier3_optional",
  "runIf": "time_available && team_bandwidth > 50%"
}
```

Estimate: **~100–200 tests** per platform (run only if resources allow).

---

## 2. **Historical Defect Pattern Analysis** (Learn From Failures)

### A. Defect Clustering
Analyze last 10 releases for **hotspots**:

```sql
-- Pseudo-query to identify defect clusters
SELECT 
  component,
  COUNT(*) as bug_count,
  AVG(days_to_fix) as avg_ttf,
  SUM(CASE WHEN severity='Critical' THEN 1 ELSE 0 END) as critical_count
FROM jira_issues
WHERE type='Bug' 
  AND created_date >= '2026-03-01'
GROUP BY component
ORDER BY bug_count DESC, critical_count DESC
LIMIT 20
```

**Result from DOVS data**:
- **GENERIC_Loyalty**: 12 bugs → 2nd release in a row with issues → **HIGH RISK**
- **GENERIC_Account_Management**: Auth0 integration → new risks each release → **ALWAYS TEST CRITICAL**
- **GENERIC_Order_History**: Data migration bugs (PROJ-12528, PROJ-12499) → **TEST DATA INTEGRITY PATHS**

### B. Build "Regression Test Suites" from Defect Patterns
For each hotspot, create a **focused test suite**:

```yaml
# Regression Suite: Loyalty Defects (12 bugs in last releases)
name: "REGRESSION_Loyalty_PointsAndRewards"
priority: "critical"
test_cases:
  - TE-XXXX  # Points calculation after order
  - TE-YYYY  # Reward redemption → Epsilon sync
  - TE-ZZZZ  # Badge display (Offer vs Reward)
  - TE-AAAA  # Mixed reward state messaging
  - TE-BBBB  # Monthly reset behavior
  - TE-CCCC  # Tier progression edge case
platforms: ["Web", "App"]
brands: ["Brand Four'", "Brand Three", "Brand One"]
estimated_runtime: "45 minutes"
```

**Action**: Store these in `projects/jira/testCaseFullMeal/suites/regression/` and link them to Test Plans.

---

## 3. **Smart Test Coverage Strategies** (Do More With Less)

### A. **Risk-Weighted Matrix Testing**
Instead of "test all brand × platform × flow combinations", use a **focused grid**:

```
Defect Density → Brand/Platform Selection

GENERIC_Loyalty (HIGH RISK):
  ✅ Brand Four' App      (highest user base + most bugs)
  ✅ Brand Four' Web      (conversion focus)
  ✅ Brand Three App        (loyalty is differentiator)
  ⏭️  Brand Three Web       (can defer if bandwidth tight)
  ⏭️  Brand One App      (lower priority brand)

GENERIC_Account_Management (CRITICAL):
  ✅ All brands + all platforms (auth breaks everything)

GENERIC_Payments (CRITICAL):
  ✅ Brand Four' + Brand Three (high transaction volume)
  ⏭️  Brand One         (defer if tight)
```

**Benefit**: Cover **80% of user impact** with **40% of tests**.

---

### B. **Automation + Manual Sampling Hybrid**
Don't assume "manual = bad". Allocate smartly:

| Test Type | Automation | Manual | Rationale |
|-----------|------------|--------|-----------|
| **Sign In / Create Account** | 100% | — | Fast, deterministic, high regression risk |
| **Order Submission (Happy Path)** | 100% | — | Revenue-critical, must be stable |
| **Loyalty Redemption** | 80% (paths) | 20% (UI/UX) | Logic testable; need eyes on badge/messaging |
| **Error Handling** | 60% (sys errors) | 40% (user errors) | Manual catches UX clarity ("error message confusing?") |
| **Accessibility** | 40% (structure) | 60% (usability) | Automated tools miss context; real SR testing needed |
| **Cross-Brand UI** | 50% (pixel-diffs) | 50% (brand compliance) | Automation handles deltas; humans verify brand intent |

**Action**: Tag tests in Jira:
```
labels: ["automation-first", "manual-validation"]
automation_type: "comet" / "maestro" / "manual"
manual_effort_minutes: 15  # if manual required
```

---

### C. **Incremental Testing via Test Dependencies**
Test in **waves** to catch errors early and pivot:

```
Wave 1 (Day 1, ~8 hours) — Tier 1 Critical Path
  └─ Tests: Sign In → Menu → Bag → Checkout
  └─ Teams: 1–2 QA engineers (parallel)
  └─ Trigger: Release readiness gate

Wave 2 (Day 2, ~12 hours) — Tier 2 Interactions + Loyalty
  └─ Only if Wave 1 ✅ passes (skip if blockers found)
  └─ Tests: Cross-component flows + defect regression suites
  └─ Teams: 2–3 QA engineers

Wave 3 (Day 2–3, as time permits) — Tier 3 Optional
  └─ Tests: Edge cases, a11y, performance
  └─ Teams: 1 QA engineer + automation suite
  └─ Gate: "Do we have bandwidth?" (yes/no)
```

**Benefit**: Fail fast, don't waste time on Tier 2 if Tier 1 broke.

---

## 4. **Test Case Selection Workflow**

### Step 1: Extract Release Scope
```powershell
# Input: Release version (e.g., Digital 26.12)
$releaseScope = Get-JiraScope -fixVersion "Digital 26.12"
# Output: 30–50 stories/bugs in DOVS

# Identify affected components (auto-map from Jira)
$componentMap = $releaseScope | 
  ForEach-Object { $_.fields.components } | 
  Select-Object -Unique
# Example: [GENERIC_Account_Management, GENERIC_Loyalty, GENERIC_Fulfillment]
```

### Step 2: Map Components → Test Cases
```powershell
# Find all test cases tagged with affected components
$testCases = Get-XrayTests -components $componentMap -tier "1|2"
# Smart filter: prioritize by defect frequency + component criticality
```

### Step 3: Cross-Reference with Old Defects
```powershell
# Fetch defects from last 3 releases in same components
$oldDefects = Get-JiraDefects -components $componentMap -releasesBack 3

# Create test coverage map
$regressionTests = $testCases | 
  Where-Object { $_.relatedDefect -in $oldDefects.key }
# These are "proven" regression tests
```

### Step 4: Build Test Execution(s)
```powershell
# Tier 1: Must-run (100 tests, ~8 hours)
$TE_Tier1 = Create-TestExecution `
  -name "PROJ-26.12-REGRESSION-CRITICAL-PATH" `
  -tests $regressionTests.where({ $_.tier -eq 1 }) `
  -dueDate $(Get-Date).AddDays(1) `
  -assignee "QA_Team"

# Tier 2: Should-run (150 tests, ~12 hours, conditional)
$TE_Tier2 = Create-TestExecution `
  -name "PROJ-26.12-REGRESSION-INTERACTIONS" `
  -tests $regressionTests.where({ $_.tier -eq 2 }) `
  -dueDate $(Get-Date).AddDays(2) `
  -parentTE $TE_Tier1.key  # link for dependency

# Tier 3: Nice-to-have (100 tests, ~10 hours, time-permitting)
$TE_Tier3 = Create-TestExecution `
  -name "PROJ-26.12-REGRESSION-OPTIONAL" `
  -tests $regressionTests.where({ $_.tier -eq 3 }) `
  -status "NOT_STARTED" `
  -marker "Execute only if Wave 1+2 pass and time allows"
```

---

## 5. **Resource Planning & Team Allocation**

### Manpower Model
Assume **2–3 QA engineers** available for regression:

| Scenario | Tier 1 | Tier 2 | Tier 3 | Total Runtime |
|----------|--------|--------|--------|---|
| **Full team, unlimited time** | 8h | 12h | 10h | 30h (full coverage) |
| **Typical case** (2 QAs, 2 days) | 8h | 6h (1 QA) | — | 14h (60% coverage) |
| **Tight schedule** (1 QA, 1 day) | 8h | — | — | 8h (critical path only) |
| **Hybrid** (1 QA + automation) | 4h (manual) + 2h (auto) | 8h (auto) + 4h (manual spot-check) | — | ~18h (80% coverage) |

**Action**: Define **acceptance criteria per scenario**:
```yaml
Release_Gate:
  Minimum_Coverage: "Tier 1 + 50% Tier 2"
  Ideal_Coverage: "Tier 1 + 100% Tier 2"
  Full_Coverage: "Tier 1 + Tier 2 + Tier 3"
  
Defect_Threshold:
  Go_Live: "≤2 critical, ≤5 high"
  Rollback: ">2 critical or >5 high + no fix"
```

---

## 6. **Monitoring & Feedback Loop** (Learn Each Release)

### After Execution: Defect Analysis
```sql
-- Post-release: What did we miss?
SELECT 
  jira_bug.component,
  COUNT(*) as bugs_found_in_prod,
  (SELECT COUNT(*) FROM xray_test_case 
   WHERE component = jira_bug.component 
   AND test_execution_key = $TE.key) as tests_we_ran
FROM jira_bug
WHERE jira_bug.fix_version = 'Digital 26.12'
  AND jira_bug.environment = 'Production'
GROUP BY jira_bug.component
```

**Result**: If `bugs_found_in_prod > 0` for a component where we ran tests:
- **False negative** → Test case quality issue; update test logic
- If `tests_we_ran = 0` for that component:
- **Coverage gap** → Add this component to Tier 1 next release

### Update Regression Suites
```yaml
# After PROJ-26.12 release
Lessons_Learned:
  - GENERIC_Loyalty: 2 prod bugs found → Increase tier 2 loyalty tests by 50%
  - GENERIC_Account_Management: 0 bugs → Maintain current tier 1 level
  - GENERIC_POS_Integration: 1 missed bug in production → Move from tier 2 to tier 1 for next release
  
Updated_Tier_Weightings:
  Critical: GENERIC_Account_Management, GENERIC_Loyalty, GENERIC_Payments
  High: GENERIC_Fulfillment, GENERIC_Order_History, GENERIC_Ordering
  Medium: GENERIC_POS_Integration, GENERIC_Accessibility
```

---

## 7. **Practical Checklist for Your Next Release**

```markdown
## Pre-Test Execution
- [ ] Extract release scope (fixVersion = "Digital 26.XX")
- [ ] Identify affected GENERIC_ components
- [ ] Fetch test cases for Tier 1 components (100% automation priority)
- [ ] Cross-reference with old defects (last 3 releases, same components)
- [ ] Tag test cases: tier, automation_type, manual_effort_minutes
- [ ] Estimate runtime per tier (auto tests ~2min each, manual ~10–15min each)
- [ ] Allocate team: How many QAs? How many days available?
- [ ] Create Test Executions (1 per tier, linked via parent-child)

## During Execution
- [ ] Run Tier 1 in parallel across QA team (8–12 hours)
- [ ] If Tier 1 has >2 critical failures → STOP; escalate to dev
- [ ] If Tier 1 ✅ → Proceed to Tier 2 (parallel, 12–16 hours)
- [ ] Log defects in real time (severity, component, blockers)
- [ ] Spot-check manual validation for critical UX (loyalty badge, error messaging)

## Post-Execution
- [ ] Collect pass/fail metrics per component
- [ ] Compare vs. old defect hotspots
- [ ] Update tier assignments for next release based on lessons learned
- [ ] Publish summary: "Tested 60% of scope, zero critical gaps, 3 high-priority bugs found + fixed"
```

---

## Summary: Your Competitive Advantage

| Approach | Coverage | Effort | Risk | Scalable? |
|----------|----------|--------|------|-----------|
| **Test everything** | 100% | 200+ hours | Low | ❌ No |
| **Random sampling** | ~40% | 40 hours | High | ✅ Yes (but unreliable) |
| **Risk-based (this framework)** | **75–85%** | **60–80 hours** | **Medium** | ✅ **Yes** |

**With risk-based regression testing**, you:
1. ✅ **Cover critical paths 100%** (auth, order, payment, loyalty)
2. ✅ **Target defect hotspots** (learn from old bugs)
3. ✅ **Use automation to scale** (80% of Tier 1 automated, humans review edge cases)
4. ✅ **Fail fast** (wave testing catches blockers early)
5. ✅ **Improve over time** (feedback loop tunes tier weightings)

→ **Result**: Catch **80% of production defects with 40% of ideal effort**.

---

## Recommended Shuriken Integration

1. **Use existing tools**:
   - `projects/jira/testCaseFullMeal/` → Already maps components → test cases
   - `xray_search_tests` via example-mcp → Query by component + tier
   - Test Execution batching → Use for wave management

2. **Add Tier Tagging**:
   ```json
   {
     "issueType": "Test",
     "customfield_regression_tier": "1",  // 1, 2, or 3
     "customfield_defect_related": ["PROJ-11946", "PROJ-11945"],
     "customfield_automation_required": true
   }
   ```

3. **Create Regression Test Plans**:
   - `PLAN-REGRESSION-TIER1` (always run)
   - `PLAN-REGRESSION-TIER2` (run if time)
   - `PLAN-REGRESSION-TIER3` (optional)

4. **Automate TE Creation**:
   ```shell
   npm run regression:create \
     --fixVersion "Digital 26.12" \
     --tier "1" \
     --platforms "Web,App" \
     --brands "Brand Four',Brand Three,Brand One"
   ```

---

**Next Steps**:
1. Audit your test case inventory — tag them with tier + automation status
2. Analyze last 3 releases — what defects were missed? Update Tier assignments
3. Build Wave 1 TE for next release using Tier 1 tests
4. Measure: *Coverage % vs. Production defects found*
5. Iterate: Each release, adjust tiers based on defect escape data

