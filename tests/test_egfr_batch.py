"""Tests for egfr-batch.

Oracle discipline: the expected values below were NOT produced by
running this tool. They were computed by hand from the equations as
published by NIDDK (adults page, Inker et al. NEJM 2021) in a separate
scratch calculation, and then cross-checked against independently
published worked examples, which round to whole numbers:

  eGFRcr (CKD-EPI 2021):
    M, 60 y, Scr 1.2 mg/dL -> 69.2311   published worked example: 69.2
        (step-by-step worked example, calcist.com eGFR calculator page,
         citing the NKF/NIDDK 2021 equation; also 69 in its table)
    M, 65 y, Scr 1.2 mg/dL -> 67.1114   published worked example: 67.1
        (step-by-step worked example, 4calculators.com CKD-EPI page)
    M, 50 y, Scr 1.0 mg/dL -> 91.6915   published: 92  (calchives.com)
    F, 50 y, Scr 1.0 mg/dL -> 68.6335   published: 69  (calchives.com)
    M, 70 y, Scr 1.3 mg/dL -> 59.0985   published: 59  (calchives.com)
    F, 60 y, Scr 1.2 mg/dL -> 51.8213   published: 52  (calchives.com
        table; clinical-mcp example output also gives 52)
    M, 55 y, Scr 1.1 mg/dL -> 79.2780   published: 79  (healthboard.com)
    M, 70 y, Scr 1.5 mg/dL -> 49.7736   published: 50  (healthboard.com)
    F, 65 y, Scr 1.2 mg/dL -> 50.2347   published: 50  (healthboard.com)

  eGFRcr-cys (CKD-EPI 2021): computed by hand from the NIDDK-published
  equation (135, kappa as above, alpha -0.219 F / -0.144 M, Scr max
  exponent -0.544, cystatin C exponents -0.323 / -0.778 around the
  0.8 mg/L breakpoint, 0.9961^Age, x0.963 if female). The two boundary
  cases (Scr exactly kappa, cystatin C exactly 0.8) reduce to the
  closed form 135 x 0.9961^Age [x 0.963], which the tests assert
  independently of the general code path.

  Cockcroft-Gault, Devine IBW, adjusted weight and Mosteller BSA
  expected values were likewise computed by hand from the published
  formulas (arithmetic shown in the test comments).
"""

import csv
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from egfr_batch import core  # noqa: E402
from egfr_batch.core import EgfrError  # noqa: E402


def run_cli(*argv):
    env = dict(os.environ)
    env["PYTHONPATH"] = str(ROOT) + os.pathsep + env.get("PYTHONPATH", "")
    return subprocess.run(
        [sys.executable, "-m", "egfr_batch", *argv],
        capture_output=True, text=True, cwd=ROOT, env=env)


def write_csv(tmp, text, name="in.csv"):
    p = Path(tmp) / name
    p.write_text(text)
    return p


class EgfrCrOracleTests(unittest.TestCase):
    CASES = [
        # (age, sex, scr_mg_dl, hand-computed, published rounded)
        (60, "M", 1.2, 69.2311, 69.2),
        (65, "M", 1.2, 67.1114, 67.1),
        (50, "M", 1.0, 91.6915, 92),
        (50, "F", 1.0, 68.6335, 69),
        (70, "M", 1.3, 59.0985, 59),
        (60, "F", 1.2, 51.8213, 52),
        (55, "M", 1.1, 79.2780, 79),
        (70, "M", 1.5, 49.7736, 50),
        (65, "F", 1.2, 50.2347, 50),
    ]

    def test_oracle_cases(self):
        for age, sex, scr, expected, published in self.CASES:
            with self.subTest(age=age, sex=sex, scr=scr):
                got = core.egfr_cr(age, sex, scr)
                self.assertAlmostEqual(got, expected, delta=0.02)
                # Agrees with the independently published rounded value.
                self.assertAlmostEqual(got, published, delta=0.6)

    def test_boundary_female_scr_equals_kappa(self):
        # Scr = kappa = 0.7: min and max terms are both exactly 1, so
        # the result must equal the closed form 142 x 0.9938^40 x 1.012.
        got = core.egfr_cr(40, "F", 0.7)
        self.assertAlmostEqual(got, 142 * 0.9938 ** 40 * 1.012, places=9)
        self.assertAlmostEqual(got, 112.0543, delta=0.01)

    def test_boundary_male_scr_equals_kappa(self):
        got = core.egfr_cr(40, "M", 0.9)
        self.assertAlmostEqual(got, 142 * 0.9938 ** 40, places=9)
        self.assertAlmostEqual(got, 110.7256, delta=0.01)

    def test_continuity_across_kappa(self):
        # Just below and just above kappa the two limbs must meet:
        # no jump at the breakpoint for either sex.
        for sex, kappa in (("F", 0.7), ("M", 0.9)):
            below = core.egfr_cr(50, sex, kappa * 0.999)
            above = core.egfr_cr(50, sex, kappa * 1.001)
            self.assertLess(abs(below - above) / above, 0.005)

    def test_female_factor(self):
        # At Scr = kappa for each sex, every term except the published
        # 1.012 female factor is identical, so the ratio is exactly it.
        ratio = core.egfr_cr(40, "F", 0.7) / core.egfr_cr(40, "M", 0.9)
        self.assertAlmostEqual(ratio, 1.012, places=9)

    def test_known_case_for_check_subcommand(self):
        computed, expected = core.run_known_case()
        self.assertAlmostEqual(computed, expected, delta=0.05)


class EgfrCrCysOracleTests(unittest.TestCase):
    CASES = [
        # (age, sex, scr_mg_dl, scys_mg_l, hand-computed from NIDDK eq.)
        (60, "M", 1.2, 1.0, 76.7622),
        (60, "F", 1.0, 1.2, 61.7833),
        (70, "F", 1.4, 1.8, 36.0917),
        (45, "M", 0.8, 0.9, 105.0837),
    ]

    def test_oracle_cases(self):
        for age, sex, scr, cys, expected in self.CASES:
            with self.subTest(age=age, sex=sex, scr=scr, cys=cys):
                self.assertAlmostEqual(
                    core.egfr_cr_cys(age, sex, scr, cys), expected,
                    delta=0.02)

    def test_boundary_both_breakpoints_male(self):
        # Scr = kappa (0.9) and Scys = 0.8: all ratio terms are 1, so
        # the result is the closed form 135 x 0.9961^50.
        got = core.egfr_cr_cys(50, "M", 0.9, 0.8)
        self.assertAlmostEqual(got, 135 * 0.9961 ** 50, places=9)
        self.assertAlmostEqual(got, 111.0403, delta=0.01)

    def test_boundary_both_breakpoints_female(self):
        got = core.egfr_cr_cys(50, "F", 0.7, 0.8)
        self.assertAlmostEqual(got, 135 * 0.9961 ** 50 * 0.963, places=9)
        self.assertAlmostEqual(got, 106.9318, delta=0.01)

    def test_continuity_across_cystatin_breakpoint(self):
        below = core.egfr_cr_cys(60, "M", 1.2, 0.8 * 0.999)
        above = core.egfr_cr_cys(60, "M", 1.2, 0.8 * 1.001)
        self.assertLess(abs(below - above) / above, 0.005)


class UnitConversionTests(unittest.TestCase):
    def test_umol_to_mgdl_factor(self):
        # NIDDK: creatinine umol/L to mg/dL, divide by 88.4.
        self.assertAlmostEqual(core.scr_to_mgdl(88.4, "umol/L"), 1.0,
                               places=12)
        self.assertAlmostEqual(core.scr_to_mgdl(106.08, "umol/L"), 1.2,
                               places=12)

    def test_mgdl_passthrough(self):
        self.assertEqual(core.scr_to_mgdl(1.2, "mg/dL"), 1.2)

    def test_umol_input_gives_same_egfr_as_mgdl(self):
        # 106.08 umol/L is exactly 1.2 mg/dL, so it must reproduce the
        # pinned M/60 oracle value.
        scr = core.scr_to_mgdl(106.08, "umol/L")
        self.assertAlmostEqual(core.egfr_cr(60, "M", scr), 69.2311,
                               delta=0.02)

    def test_unit_spellings(self):
        self.assertEqual(core.normalise_scr_unit("mg/dl"), "mg/dL")
        self.assertEqual(core.normalise_scr_unit("µmol/L"), "umol/L")
        self.assertEqual(core.normalise_scys_unit("mg/L"), "mg/L")
        with self.assertRaises(EgfrError):
            core.normalise_scr_unit("mmol/L")
        with self.assertRaises(EgfrError):
            core.normalise_scys_unit("nmol/L")


class CockcroftGaultAndBsaTests(unittest.TestCase):
    def test_cg_male(self):
        # (140-60) x 70 / (72 x 1.2) = 5600 / 86.4 = 64.8148...
        self.assertAlmostEqual(core.cockcroft_gault(60, "M", 1.2, 70.0),
                               64.8148, delta=0.01)

    def test_cg_female_factor(self):
        # Same case x 0.85 = 55.0926; and the F/M ratio is exactly 0.85.
        self.assertAlmostEqual(core.cockcroft_gault(60, "F", 1.2, 70.0),
                               55.0926, delta=0.01)
        ratio = (core.cockcroft_gault(60, "F", 1.2, 70.0)
                 / core.cockcroft_gault(60, "M", 1.2, 70.0))
        self.assertAlmostEqual(ratio, 0.85, places=9)

    def test_ibw_devine(self):
        # M, 170 cm = 66.929 in: 50 + 2.3 x 6.929 = 65.9370 kg
        self.assertAlmostEqual(core.ideal_body_weight_kg("M", 170.0),
                               65.9370, delta=0.01)
        # F, 165 cm = 64.961 in: 45.5 + 2.3 x 4.961 = 56.9094 kg
        self.assertAlmostEqual(core.ideal_body_weight_kg("F", 165.0),
                               56.9094, delta=0.01)

    def test_adjusted_weight(self):
        # IBW 65.9370 + 0.4 x (90 - 65.9370) = 75.5622 kg
        w, _ = core.cg_weight_kg("adjusted", "M", 170.0, 90.0)
        self.assertAlmostEqual(w, 75.5622, delta=0.01)
        # CG with that weight, M, 50 y, Scr 1.0: 90 x 75.5622 / 72 = 94.4528
        self.assertAlmostEqual(core.cockcroft_gault(50, "M", 1.0, w),
                               94.4528, delta=0.01)

    def test_cg_ideal_weight_path(self):
        # F, 55 y, Scr 0.9, IBW 56.9094: (85 x 56.9094 / (72 x 0.9)) x 0.85
        w, _ = core.cg_weight_kg("ideal", "F", 165.0, None)
        self.assertAlmostEqual(core.cockcroft_gault(55, "F", 0.9, w),
                               63.4523, delta=0.01)

    def test_bsa_mosteller(self):
        # sqrt(170 x 70 / 3600) = sqrt(3.30555...) = 1.8181 m2
        self.assertAlmostEqual(core.bsa_mosteller(170.0, 70.0), 1.8181,
                               delta=0.001)

    def test_deindex(self):
        # M/60/Scr 1.2 oracle 69.2311 x BSA 1.8181187 / 1.73 = 72.7575
        bsa = core.bsa_mosteller(170.0, 70.0)
        self.assertAlmostEqual(
            core.deindex(core.egfr_cr(60, "M", 1.2), bsa), 72.7575,
            delta=0.02)
        # Same de-indexing applied to the cr-cys oracle 76.7622 = 80.6722
        self.assertAlmostEqual(
            core.deindex(core.egfr_cr_cys(60, "M", 1.2, 1.0), bsa),
            80.6722, delta=0.02)


class CoreRefusalTests(unittest.TestCase):
    def test_age_under_18_refused(self):
        with self.assertRaises(EgfrError):
            core.egfr_cr(17, "M", 1.0)
        with self.assertRaises(EgfrError):
            core.egfr_cr_cys(10, "F", 0.7, 0.8)

    def test_age_18_accepted(self):
        self.assertGreater(core.egfr_cr(18, "M", 1.0), 0)

    def test_nonpositive_creatinine_refused(self):
        for bad in (0, -1.0):
            with self.assertRaises(EgfrError):
                core.egfr_cr(60, "M", bad)

    def test_bad_sex_refused(self):
        with self.assertRaises(EgfrError):
            core.parse_sex("X")


CSV_BASIC = "age,sex,creatinine,cystatin_c,height_cm,weight_kg\n" \
            "60,M,1.2,1.0,170,70\n" \
            "50,F,1.0,,165,60\n"


class CliConvertTests(unittest.TestCase):
    def _convert(self, tmp, text=CSV_BASIC, *extra):
        src = write_csv(tmp, text)
        out = Path(tmp) / "out.csv"
        proc = run_cli("convert", str(src), "--out", str(out), *extra)
        return proc, out

    def test_end_to_end_mgdl(self):
        with tempfile.TemporaryDirectory() as tmp:
            proc, out = self._convert(
                tmp, CSV_BASIC, "--scr-unit", "mg/dL",
                "--scys-unit", "mg/L", "--cockcroft-gault",
                "--cg-weight", "actual", "--deindex")
            self.assertEqual(proc.returncode, 0, proc.stderr)
            with out.open() as fh:
                rows = list(csv.DictReader(fh))
            self.assertEqual(len(rows), 2)
            r0 = rows[0]
            self.assertEqual(r0["scr_used_mg_dl"], "1.2000")
            self.assertEqual(r0["egfr_cr_ml_min_1.73m2"], "69.2")
            self.assertEqual(r0["egfr_cr_cys_ml_min_1.73m2"], "76.8")
            self.assertEqual(r0["egfr_cr_deindexed_ml_min"], "72.8")
            self.assertEqual(r0["cockcroft_gault_crcl_ml_min"], "64.8")
            self.assertIn("CKD-EPI 2021", r0["egfr_cr_equation"])
            self.assertIn("CKD-EPI 2021", r0["egfr_cr_cys_equation"])
            # Row 2 has no cystatin C: cr-cys cells stay empty.
            self.assertEqual(rows[1]["egfr_cr_cys_ml_min_1.73m2"], "")
            self.assertEqual(rows[1]["egfr_cr_ml_min_1.73m2"], "68.6")

    def test_no_staging_or_flag_columns(self):
        with tempfile.TemporaryDirectory() as tmp:
            proc, out = self._convert(tmp, CSV_BASIC, "--scr-unit",
                                      "mg/dL", "--scys-unit", "mg/L")
            self.assertEqual(proc.returncode, 0, proc.stderr)
            header = out.read_text().splitlines()[0].lower()
            for forbidden in ("stage", "diagnos", "flag", "abnormal",
                              "category"):
                self.assertNotIn(forbidden, header)

    def test_umol_csv_matches_mgdl_csv(self):
        umol = "age,sex,creatinine\n60,M,106.08\n50,F,88.4\n"
        mgdl = "age,sex,creatinine\n60,M,1.2\n50,F,1.0\n"
        with tempfile.TemporaryDirectory() as tmp:
            p1, o1 = self._convert(tmp, umol, "--scr-unit", "umol/L")
            self.assertEqual(p1.returncode, 0, p1.stderr)
            with o1.open() as fh:
                rows_umol = list(csv.DictReader(fh))
            src = write_csv(tmp, mgdl, "in2.csv")
            o2 = Path(tmp) / "out2.csv"
            p2 = run_cli("convert", str(src), "--out", str(o2),
                         "--scr-unit", "mg/dL")
            self.assertEqual(p2.returncode, 0, p2.stderr)
            with o2.open() as fh:
                rows_mgdl = list(csv.DictReader(fh))
            for a, b in zip(rows_umol, rows_mgdl):
                self.assertEqual(a["egfr_cr_ml_min_1.73m2"],
                                 b["egfr_cr_ml_min_1.73m2"])

    def test_missing_scr_unit_refused(self):
        with tempfile.TemporaryDirectory() as tmp:
            proc, out = self._convert(tmp)
            self.assertNotEqual(proc.returncode, 0)
            self.assertIn("refuses to guess", proc.stderr)
            self.assertIn("--scr-unit", proc.stderr)
            self.assertFalse(out.exists())
            self.assertNotIn("Traceback", proc.stderr)

    def test_cystatin_without_scys_unit_refused(self):
        with tempfile.TemporaryDirectory() as tmp:
            proc, out = self._convert(tmp, CSV_BASIC, "--scr-unit",
                                      "mg/dL")
            self.assertNotEqual(proc.returncode, 0)
            self.assertIn("--scys-unit", proc.stderr)
            self.assertFalse(out.exists())

    def test_age_under_18_row_refused_no_output(self):
        text = "age,sex,creatinine\n60,M,1.2\n17,F,0.8\n"
        with tempfile.TemporaryDirectory() as tmp:
            proc, out = self._convert(tmp, text, "--scr-unit", "mg/dL")
            self.assertNotEqual(proc.returncode, 0)
            self.assertIn("under 18", proc.stderr)
            self.assertIn("row 2", proc.stderr)
            self.assertFalse(out.exists())
            self.assertNotIn("Traceback", proc.stderr)

    def test_missing_creatinine_value_refused(self):
        text = "age,sex,creatinine\n60,M,\n"
        with tempfile.TemporaryDirectory() as tmp:
            proc, _ = self._convert(tmp, text, "--scr-unit", "mg/dL")
            self.assertNotEqual(proc.returncode, 0)
            self.assertIn("creatinine is missing", proc.stderr)

    def test_non_numeric_age_refused(self):
        text = "age,sex,creatinine\nsixty,M,1.2\n"
        with tempfile.TemporaryDirectory() as tmp:
            proc, _ = self._convert(tmp, text, "--scr-unit", "mg/dL")
            self.assertNotEqual(proc.returncode, 0)
            self.assertIn("not a number", proc.stderr)
            self.assertNotIn("Traceback", proc.stderr)

    def test_bad_sex_refused(self):
        text = "age,sex,creatinine\n60,X,1.2\n"
        with tempfile.TemporaryDirectory() as tmp:
            proc, _ = self._convert(tmp, text, "--scr-unit", "mg/dL")
            self.assertNotEqual(proc.returncode, 0)
            self.assertIn("sex value 'X'", proc.stderr)

    def test_missing_required_column_refused(self):
        text = "age,creatinine\n60,1.2\n"
        with tempfile.TemporaryDirectory() as tmp:
            proc, _ = self._convert(tmp, text, "--scr-unit", "mg/dL")
            self.assertNotEqual(proc.returncode, 0)
            self.assertIn("'sex' not found", proc.stderr)

    def test_cg_without_weight_choice_refused(self):
        with tempfile.TemporaryDirectory() as tmp:
            proc, _ = self._convert(tmp, CSV_BASIC, "--scr-unit", "mg/dL",
                                    "--scys-unit", "mg/L",
                                    "--cockcroft-gault")
            self.assertNotEqual(proc.returncode, 0)
            self.assertIn("--cg-weight", proc.stderr)
            self.assertIn("refuses", proc.stderr)

    def test_cg_weight_without_cg_flag_refused(self):
        with tempfile.TemporaryDirectory() as tmp:
            proc, _ = self._convert(tmp, CSV_BASIC, "--scr-unit", "mg/dL",
                                    "--scys-unit", "mg/L",
                                    "--cg-weight", "actual")
            self.assertNotEqual(proc.returncode, 0)
            self.assertIn("--cockcroft-gault", proc.stderr)

    def test_deindex_without_height_refused(self):
        text = "age,sex,creatinine,weight_kg\n60,M,1.2,70\n"
        with tempfile.TemporaryDirectory() as tmp:
            proc, _ = self._convert(tmp, text, "--scr-unit", "mg/dL",
                                    "--deindex")
            self.assertNotEqual(proc.returncode, 0)
            self.assertIn("height_cm and weight_kg", proc.stderr)

    def test_empty_file_refused(self):
        with tempfile.TemporaryDirectory() as tmp:
            src = write_csv(tmp, "")
            proc = run_cli("convert", str(src), "--scr-unit", "mg/dL")
            self.assertNotEqual(proc.returncode, 0)
            self.assertNotIn("Traceback", proc.stderr)


class ReviewRegressionTests(unittest.TestCase):
    """Regressions pinned by the independent adversarial review
    (REVIEW.md): silent column loss, library-level sex validation,
    and the non-positive Devine IBW guard."""

    def test_deindexed_crcys_column_when_first_row_lacks_cystatin(self):
        # First row has no cystatin C, second row does: with --deindex
        # the egfr_cr_cys_deindexed column must still be written, with
        # the second row's value (64.2453 x BSA 1.658/1.73 -> 61.6).
        text = ("age,sex,creatinine,cystatin_c,height_cm,weight_kg\n"
                "60,M,1.2,,170,70\n"
                "50,F,1.0,1.2,165,60\n")
        with tempfile.TemporaryDirectory() as tmp:
            src = write_csv(tmp, text)
            out = Path(tmp) / "out.csv"
            proc = run_cli("convert", str(src), "--out", str(out),
                           "--scr-unit", "mg/dL", "--scys-unit", "mg/L",
                           "--deindex")
            self.assertEqual(proc.returncode, 0, proc.stderr)
            with out.open() as fh:
                rows = list(csv.DictReader(fh))
            self.assertIn("egfr_cr_cys_deindexed_ml_min", rows[0])
            self.assertEqual(rows[0]["egfr_cr_cys_deindexed_ml_min"], "")
            self.assertEqual(rows[1]["egfr_cr_cys_deindexed_ml_min"],
                             "61.6")

    def test_core_invalid_sex_raises_egfr_error_not_keyerror(self):
        for call in (
                lambda: core.egfr_cr(60, "X", 1.0),
                lambda: core.egfr_cr(60, "f", 0.7),
                lambda: core.egfr_cr_cys(60, "X", 1.0, 1.0),
                lambda: core.cockcroft_gault(60, "X", 1.0, 70.0),
                lambda: core.ideal_body_weight_kg("X", 170.0)):
            with self.assertRaises(EgfrError):
                call()

    def test_ibw_nonpositive_refused_with_reason(self):
        # Devine IBW for a 100 cm female is -1.95 kg: both the ideal
        # and adjusted Cockcroft-Gault paths must refuse cleanly.
        with self.assertRaises(EgfrError):
            core.ideal_body_weight_kg("F", 100.0)
        with self.assertRaises(EgfrError):
            core.cg_weight_kg("ideal", "F", 100.0, 40.0)
        with self.assertRaises(EgfrError):
            core.cg_weight_kg("adjusted", "F", 100.0, 40.0)


class CliSingleAndCheckTests(unittest.TestCase):
    def test_single_mgdl(self):
        proc = run_cli("single", "--age", "60", "--sex", "M",
                       "--scr", "1.2", "--scr-unit", "mg/dL")
        self.assertEqual(proc.returncode, 0, proc.stderr)
        self.assertIn("69.2 mL/min/1.73 m2", proc.stdout)

    def test_single_umol_matches(self):
        proc = run_cli("single", "--age", "60", "--sex", "M",
                       "--scr", "106.08", "--scr-unit", "umol/L")
        self.assertEqual(proc.returncode, 0, proc.stderr)
        self.assertIn("69.2 mL/min/1.73 m2", proc.stdout)

    def test_single_missing_unit_refused(self):
        proc = run_cli("single", "--age", "60", "--sex", "M",
                       "--scr", "1.2")
        self.assertNotEqual(proc.returncode, 0)
        self.assertIn("refuses to guess", proc.stderr)

    def test_single_scys_without_unit_refused(self):
        proc = run_cli("single", "--age", "60", "--sex", "M",
                       "--scr", "1.2", "--scr-unit", "mg/dL",
                       "--scys", "1.0")
        self.assertNotEqual(proc.returncode, 0)
        self.assertIn("--scys-unit", proc.stderr)

    def test_single_under_18_refused(self):
        proc = run_cli("single", "--age", "12", "--sex", "F",
                       "--scr", "0.7", "--scr-unit", "mg/dL")
        self.assertNotEqual(proc.returncode, 0)
        self.assertIn("under 18", proc.stderr)

    def test_single_unknown_unit_refused(self):
        proc = run_cli("single", "--age", "60", "--sex", "M",
                       "--scr", "1.2", "--scr-unit", "mmol/L")
        self.assertNotEqual(proc.returncode, 0)
        self.assertNotIn("Traceback", proc.stderr)

    def test_check_subcommand(self):
        proc = run_cli("check")
        self.assertEqual(proc.returncode, 0, proc.stderr)
        self.assertIn("PASS", proc.stdout)


if __name__ == "__main__":
    unittest.main()
