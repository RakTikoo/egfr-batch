# egfr-batch — batch-compute CKD-EPI 2021 eGFR from a CSV

[![Ask DeepWiki](https://deepwiki.com/badge.svg)](https://deepwiki.com/RakTikoo/egfr-batch)

> **Research and educational tool only. Not a medical device. This tool
> does published-formula arithmetic only — it does not diagnose, stage,
> or interpret anything. Verify any result before clinical use.**

**Batch-compute CKD-EPI 2021 eGFR from a CSV of age, sex and creatinine
— with explicitly declared units, or not at all.**

Single-patient eGFR calculators are everywhere, but research work is
batch work: a cohort CSV, often with creatinine in µmol/L, gets pasted
into spreadsheet formulas that nobody can audit afterwards. A
peer-reviewed audit of 47 free online CKD-EPI calculators found only
36 (76.6%) accurate on all reference cases, with creatinine unit
conversion among the leading causes of error (Seiberth et al., *Eur J
Clin Pharmacol* 2020). `egfr-batch` is the file-level tool: point it at
a CSV, state the creatinine unit out loud, and get the same CSV back
with the eGFR values, the converted creatinine actually used, and a
per-row column naming the exact equation and version that produced
each number.

If you do not state `--scr-unit`, `egfr-batch` refuses and tells you
why. That refusal is the product: mg/dL and µmol/L readings of the same
blood sample differ by a factor of 88.4, and guessing wrong does not
crash — it silently returns a wrong number for every row.

**Quick install:** `pip install git+https://github.com/RakTikoo/egfr-batch`
(Python 3.10+, no dependencies, runs offline). Details under
[Install](#install).

## Demo

Input (`examples/patients.csv`):

```csv
id,age,sex,creatinine,cystatin_c,height_cm,weight_kg
P01,60,M,1.2,1.0,170,70
P02,50,F,1.0,1.2,165,60
P03,70,M,1.3,,178,82
P04,45,F,0.7,0.8,162,58
P05,80,M,2.0,1.8,172,75
```

```console
$ egfr-batch convert examples/patients.csv --scr-unit mg/dL \
      --scys-unit mg/L --cockcroft-gault --cg-weight actual --deindex \
      --out examples/patients_egfr.csv
computed 5 rows from examples/patients.csv
  creatinine unit declared: mg/dL (converted values are in scr_used_mg_dl)
  eGFRcr     : CKD-EPI 2021 (NIDDK / Inker et al. 2021), all 5 rows
  eGFRcr-cys : CKD-EPI 2021 (NIDDK / Inker et al. 2021), 4 rows with cystatin C (mg/L)
  Cockcroft-Gault CrCl: weight = actual (user-declared)
  de-indexed eGFR: mL/min, using BSA (Mosteller) x value / 1.73
  output     : examples/patients_egfr.csv
```

The output file is the input with these columns appended (shown here
trimmed to the result columns; the real file also carries one
provenance column per equation, e.g. `CKD-EPI 2021 eGFRcr (Inker et
al. NEJM 2021; NIDDK)`):

```csv
id,scr_used_mg_dl,egfr_cr_ml_min_1.73m2,egfr_cr_cys_ml_min_1.73m2,bsa_m2_mosteller,egfr_cr_deindexed_ml_min,egfr_cr_cys_deindexed_ml_min,cockcroft_gault_crcl_ml_min
P01,1.2000,69.2,76.8,1.818,72.8,80.7,64.8
P02,1.0000,68.6,64.2,1.658,65.8,61.6,63.8
P03,1.3000,59.1,,2.014,68.8,,61.3
P04,0.7000,108.6,109.0,1.616,101.4,101.8,92.9
P05,2.0000,33.1,34.0,1.893,36.2,37.2,31.2
```

Forget the unit, and this happens instead:

```console
$ egfr-batch convert examples/patients.csv
error: --scr-unit is required, and egfr-batch refuses to guess it.
The same creatinine value means completely different things in mg/dL
and in umol/L -- the two differ by a factor of 88.4. State it
explicitly: --scr-unit mg/dL or --scr-unit umol/L.
```

One person, one line (creatinine in µmol/L this time):

```console
$ egfr-batch single --age 60 --sex F --scr 106 --scr-unit umol/L \
      --scys 1.2 --scys-unit mg/L
age 60, sex F, creatinine 106 umol/L (= 1.1991 mg/dL)
  eGFRcr (CKD-EPI 2021): 51.9 mL/min/1.73 m2
  cystatin C 1.2 mg/L
  eGFRcr-cys (CKD-EPI 2021): 56.0 mL/min/1.73 m2
```

## Install

```console
$ pip install git+https://github.com/RakTikoo/egfr-batch
```

Requires Python ≥ 3.10. **No dependencies** — standard library only.
Everything runs offline; your CSV never leaves your machine.

Or install the wheel straight from this repo's release assets (no package
registry involved):

```sh
pip install https://github.com/RakTikoo/egfr-batch/releases/download/v0.1.0/egfr_batch-0.1.0-py3-none-any.whl
```

Or install from the git repo with pipx or uv:

```sh
pipx install git+https://github.com/RakTikoo/egfr-batch.git@v0.1.0
uv tool install --from git+https://github.com/RakTikoo/egfr-batch.git@v0.1.0 egfr-batch
```

With Homebrew (macOS/Linux):

```sh
brew tap RakTikoo/tools
brew install RakTikoo/tools/egfr-batch
```

With Scoop (Windows):

```powershell
scoop bucket add RakTikoo https://github.com/RakTikoo/scoop-bucket
scoop install egfr-batch
```

**For agent users:** this repository ships a `SKILL.md` for AI agents. Install it with `npx skills add RakTikoo/egfr-batch`.

## Usage

```
egfr-batch convert FILE --scr-unit mg/dL|umol/L [--scys-unit mg/L]
                   [--cockcroft-gault --cg-weight actual|ideal|adjusted]
                   [--deindex] [--out FILE]
egfr-batch single --age YEARS --sex F|M --scr VALUE --scr-unit UNIT
                  [--scys VALUE --scys-unit mg/L] [same options]
egfr-batch check
```

Input CSV columns:

- `age` — years. **Ages under 18 are refused**: the CKD-EPI 2021
  equations are adult equations (NIDDK: ages 18 and older). There is
  no paediatric equation in this tool. Ages over 130 are also
  refused as implausible.
- `sex` — `F`/`M` (also `female`/`male`). The published equations
  define coefficients for female and male only.
- `creatinine` — serum creatinine, in the unit you declare with
  `--scr-unit`. Creatinine should be standardised (IDMS-traceable),
  as the equations assume.
- `cystatin_c` — optional; serum cystatin C. If any row has a value,
  `--scys-unit mg/L` is required (NIDDK publishes cystatin C in mg/L
  with no conversion). Rows with an empty cell simply get no
  eGFRcr-cys value.
- `height_cm`, `weight_kg` — optional; used only by `--deindex` and by
  Cockcroft-Gault weight choices that need them.

Aliases (`scr`, `scys`, `gender`, `height`, `weight`) are accepted.

Options:

- `--scr-unit` — **required, never guessed**: `mg/dL` or `umol/L`
  (`µmol/L` spelling also accepted). µmol/L values are converted with
  the NIDDK factor, ÷ 88.4; the converted value used is written to
  every output row as `scr_used_mg_dl`.
- `--cockcroft-gault` — also compute Cockcroft-Gault creatinine
  clearance (mL/min, not indexed). Requires `--cg-weight`:
  - `actual` — the row's `weight_kg`;
  - `ideal` — Devine ideal body weight from `height_cm`;
  - `adjusted` — IBW + 0.4 × (actual − IBW).
  
  The choice is never made silently, and the weight actually used is
  written to every output row (`cockcroft_gault_weight`).
- `--deindex` — also report eGFR in mL/min (not per 1.73 m²):
  indexed value × BSA / 1.73, with BSA from the Mosteller formula.
  Needs `height_cm` and `weight_kg` on every row.

One bad row refuses the whole run, with the row number in the error,
and no output file is written — a partial batch with silently missing
values is worse than no batch.

### Verify your install

```console
$ egfr-batch check
egfr-batch check -- built-in published worked example
  input   : age 60, male, creatinine 1.2 mg/dL
  computed: eGFRcr 69.2311 mL/min/1.73 m2
  expected: eGFRcr 69.2311 mL/min/1.73 m2 (2021 CKD-EPI creatinine equation as published by NIDDK; published worked examples round this case to 69.2 -- see tests)
  result  : PASS (difference 0.0000, tolerance 0.05)
```

## Method

All equations are used exactly as published; nothing is fitted or
adjusted.

- **eGFRcr — CKD-EPI 2021** (Inker et al., *NEJM* 2021;385:1737–1749;
  NIDDK's published form):
  `142 × min(Scr/κ, 1)^α × max(Scr/κ, 1)^−1.200 × 0.9938^Age × 1.012 [female]`,
  κ = 0.7 (F) / 0.9 (M), α = −0.241 (F) / −0.302 (M), Scr in mg/dL.
  There is no race input: the 2021 equation has no race coefficient.
- **eGFRcr-cys — CKD-EPI 2021**:
  `135 × min(Scr/κ, 1)^α × max(Scr/κ, 1)^−0.544 × min(Scys/0.8, 1)^−0.323 × max(Scys/0.8, 1)^−0.778 × 0.9961^Age × 0.963 [female]`,
  α = −0.219 (F) / −0.144 (M), Scys in mg/L.
- **Cockcroft-Gault** (1976): `((140 − Age) × Weight) / (72 × Scr) × 0.85 [female]`, mL/min.
- **BSA** (Mosteller 1987): `sqrt(height_cm × weight_kg / 3600)` m².
- **Ideal body weight** (Devine): 50 kg (M) / 45.5 kg (F) + 2.3 kg per
  inch of height over 5 feet.

Output values are rounded to 1 decimal place in the CSV (the
`scr_used_mg_dl` column keeps 4 decimals so the conversion is
auditable). The library functions in `egfr_batch.core` return full
precision.

## Honest limits

- **Arithmetic only.** This tool computes the published equations and
  nothing else. It produces **no CKD staging, no diagnosis, no
  reference-range flagging, and no interpretation of any kind** — by
  design, not by omission. What a number means for a person is a
  clinical judgement this software does not make.
- **Not a medical device.** Research and educational use only. Verify
  results independently before any clinical use.
- **Adults only.** Ages under 18 are refused. The equations were
  developed and validated in adults; children need a paediatric
  equation, which this tool does not implement.
- **Assay assumptions are yours.** The CKD-EPI equations assume
  standardised (IDMS-traceable) creatinine and reference-standardised
  cystatin C. The tool cannot tell whether your laboratory values meet
  that assumption.
- **Cockcroft-Gault weight choice matters.** Actual, ideal and
  adjusted body weight can differ a lot for the same person; that is
  why the tool forces you to declare the choice and records it per
  row. It does not recommend one.
- **eGFR is an estimate.** The equations estimate GFR from markers;
  they do not measure it. Known non-GFR determinants of creatinine
  and cystatin C (muscle mass, diet, some medicines, illness) affect
  the inputs and therefore the outputs, and no calculator can correct
  for them.
- **Sex coefficients are the published ones.** The equations define
  female/male coefficients only; values outside `F`/`M` are refused
  rather than mapped to something the publication does not define.

## Tests

```console
$ python3 run_tests.py
```

49 tests (stdlib `unittest`, no dependencies): eGFRcr oracle cases
computed by hand from the NIDDK-published equation and cross-checked
against independently published worked examples (M/60/Scr 1.2 → 69.2,
M/65/Scr 1.2 → 67.1, and seven more published roundings); eGFRcr-cys
oracle cases including both-breakpoint boundary cases that reduce to
a closed form; boundary cases at Scr = κ for both sexes; the ÷88.4
unit conversion; the female factors; Cockcroft-Gault, Devine IBW,
adjusted weight, Mosteller BSA and de-indexing against hand-computed
values; and every refusal rule (missing unit, cystatin C without a
declared unit, age under 18, missing/non-numeric/non-positive values,
Cockcroft-Gault without a declared weight choice) — all of which must
fail with clean one-line errors, never tracebacks, and never write a
partial output file.

## Use with an AI agent

This repo ships a [SKILL.md](SKILL.md) written to the Agent Skills open
standard. If your coding agent supports skills, point it at this repo and
it can install egfr-batch, run it on your CSVs, and read the results for
you. The skill works as documented when the repo is cloned under its
real name (`egfr-batch`) — the standard matches a skill to its folder
name.

## License

MIT. Free and open source, for science.
