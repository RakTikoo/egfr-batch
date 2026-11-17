# Independent adversarial review — egfr-batch

Reviewer: independent subagent (did not build the tool). Date: 2026-11-17.
The gauntlet was run locally; at review time nothing had been published or pushed. Documented design decisions
were not changed (creatinine unit must be declared, never guessed; ages
<18 refused; no CKD staging/diagnosis/interpretation).

## What was checked

- **Full test battery** before fixes: `python3 run_tests.py` — 46 tests, all OK.
- **Independent oracle verification.** The CKD-EPI 2021 equations were
  re-implemented from scratch in a separate script (not calling the tool's
  code) using the constants in the task brief, cross-checked against the
  NIDDK "eGFR Equations for Adults" page as returned by web search
  (eGFRcr: 142 × min(SCr/κ,1)^α × max(SCr/κ,1)^−1.200 × 0.9938^Age × 1.012
  [F], κ 0.7 F / 0.9 M, α −0.241 F / −0.302 M; eGFRcr-cys: 135 × … ×
  max(SCr/κ,1)^−0.544 × min(Scys/0.8,1)^−0.323 × max(Scys/0.8,1)^−0.778 ×
  0.9961^Age × 0.963 [F], α −0.219 F / −0.144 M — all matching). A direct
  `browser.open` of the NIDDK page failed with a tool error, so the
  constants rest on the search-result text of that page plus two
  independent secondary sources that quote the same form.
  Result: independent and tool values agreed to 0.00 difference on all
  17 eGFRcr cases and all 8 eGFRcr-cys cases tried, including both
  Scr = κ boundaries (F 40 y Scr 0.7 → 112.0543; M 40 y Scr 0.9 →
  110.7256), both cr-cys double boundaries (closed form 135 × 0.9961^50
  [× 0.963]), age 18, age 90, µmol/L conversion (106 µmol/L = 1.1991
  mg/dL → F 60 eGFRcr 51.8683 → 51.9, cr-cys 55.9725 → 56.0, matching
  the README single demo), and all five README demo rows. The tests do
  not cite R `kidney.epi` outputs; their published roundings (calcist,
  4calculators, calchives, healthboard) all agree with the independent
  calculation within whole-number rounding. Cockcroft-Gault, Devine
  IBW, adjusted weight, Mosteller BSA and de-indexing also matched
  hand calculations exactly (e.g. CG M 60/1.2/70 kg = 64.8148; BSA
  170 cm/70 kg = 1.8181; de-indexed 69.2311 → 72.7575).
- **Adversarial probes** (core + CLI + CSV): missing/undeclared/wrong
  units (mmol/L refused; µmol/L spellings incl. µ/μ accepted; case and
  whitespace tolerated), Scr = κ continuity both sexes, cystatin
  breakpoint continuity, age exactly 18 (accepted), 17.999 / 17 / −5 /
  NaN / inf (refused cleanly), age 130 (accepted) / 131 (refused),
  missing/empty/whitespace/non-numeric/zero/negative/NaN/inf
  creatinine and cystatin C (all refused, row number given, no output
  file, no traceback), duplicate alias columns, header-only and empty
  files, missing file, BOM + CRLF input (handled), semicolon-delimited
  input (clean refusal), a stray `race` column (correctly ignored —
  the 2021 equation is race-free), cystatin present/absent per row,
  all three Cockcroft-Gault weight choices incl. missing height/weight,
  and de-indexing with missing/negative height/weight. All refusals
  exit 2 with a one-line error and never write a partial file.
- **Fresh-venv install + demo.** `python3 -m venv` worked once TMPDIR
  was pointed off the full 512 MB /tmp tmpfs (that, not ensurepip, was
  the environment problem; venv created with pip 24.0, Python 3.12).
  `pip install` from the local tree succeeded; the README demo command
  reproduced `examples/patients_egfr.csv` **byte-identically**, the
  `single` demo matched the README exactly (51.9 / 56.0), `check`
  PASSed, and the no-unit refusal matched. Re-verified after fixes:
  still byte-identical.
- **README / output safety audit.** Grep for stage/staging/diagnos/
  dose/treatment/flag/abnormal/G-category terms across code, tests and
  README: hits are only explicit negations ("produces no CKD staging,
  no diagnosis…") and the test asserting no such columns exist. No
  staging, diagnosis, dose or treatment output anywhere. README opens
  with "Research and educational tool only. Not a medical device…
  Verify any result before clinical use" and the Honest limits section
  repeats it; limits are complete (adults only, assay assumptions,
  CG weight choice, estimate-not-measurement, sex coefficients).

## Findings and fixes

1. **HIGH — silent data loss: de-indexed cr-cys column dropped.**
   `_output_fieldnames` keyed extra columns off the *first* row only.
   With `--deindex`, if row 1 had no cystatin C, the
   `egfr_cr_cys_deindexed_ml_min` column was omitted from the header
   entirely and every later row's value was silently discarded
   (DictWriter `extrasaction="ignore"`), rc=0. Reproduced before fix
   (row 2's 61.6 lost). **Fixed** in `egfr_batch/cli.py`: the header
   now includes an extra column if *any* row produced it. Regression
   test added; verified by hand after the fix (column present, row 1
   empty, row 2 = 61.6).
2. **MEDIUM — library API did not validate sex.** The CLI always goes
   through `parse_sex`, but direct `core` calls (the documented
   library surface) with an invalid sex raised a bare `KeyError`
   (`egfr_cr`), or silently used the wrong coefficients:
   `ideal_body_weight_kg` treated any non-"M" as female and
   `cockcroft_gault` treated it as male. **Fixed**: new
   `core.validate_sex` raising `EgfrError`, called by `egfr_cr`,
   `egfr_cr_cys`, `cockcroft_gault` and `ideal_body_weight_kg`.
   Regression test added.
3. **MEDIUM — Devine IBW goes non-positive for very short adults.**
   IBW (F, 100 cm) = −1.95 kg. The `ideal` path then failed downstream
   with the confusing message "weight for Cockcroft-Gault must be a
   positive number, got '-1.948…'", and the `adjusted` path silently
   built on the negative IBW (adjusted weight 14.83 kg for a 40 kg
   person). **Fixed**: `ideal_body_weight_kg` refuses with an
   explanation when IBW ≤ 0, covering both ideal and adjusted paths.
   Regression test added.
4. **LOW (doc) — age > 130 refusal was undocumented.** README now
   states it next to the under-18 rule, and the test count line was
   updated 46 → 49. No code change.

## Observations, not changed

- A malformed `height_cm` value refuses the run even when neither
  `--deindex` nor Cockcroft-Gault needs it (eager parsing), while a
  negative `weight_kg` passes through untouched when unused. Neither
  affects any computed value; left as-is.
- No plausibility caps on creatinine/cystatin beyond > 0 (Scr 0.01
  mg/dL → eGFRcr 380.5). That is the published formula applied
  literally; inventing caps would change documented behaviour.
- `parse_sex` also accepts "woman"/"man" beyond the documented
  female/male spellings — harmless.
- A creatinine of 106 *declared* as mg/dL yields eGFRcr 0.3: the tool
  cannot detect a wrong declaration, which is exactly why the unit
  must be declared and is echoed in the output (`scr_used_mg_dl`).

## After fixes

`python3 run_tests.py` — **49 tests, all OK** (46 original + 3 review
regressions). Fresh-venv reinstall of the fixed tree reproduced the
README demo byte-identically and `egfr-batch check` still PASSes.
