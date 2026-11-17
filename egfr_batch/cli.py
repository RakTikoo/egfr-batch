"""Command-line interface for egfr-batch.

Subcommands:
  egfr-batch convert FILE --scr-unit mg/dL|umol/L [--scys-unit mg/L]
                     [--cockcroft-gault --cg-weight actual|ideal|adjusted]
                     [--deindex] [--out FILE]
  egfr-batch single --age YEARS --sex F|M --scr VALUE --scr-unit UNIT
                     [--scys VALUE --scys-unit mg/L] [same options]
  egfr-batch check   -- verify against a built-in published worked example

--scr-unit has NO default on purpose. Creatinine reported in umol/L is
88.4 times the same value in mg/dL; guessing the unit is the single
most dangerous silent error in this calculation, so the tool refuses.
The same rule applies to cystatin C: if a cystatin C value is used,
its unit must be declared too.
"""

from __future__ import annotations

import argparse
import csv
import sys
from pathlib import Path

from . import core
from .core import EgfrError

REFUSAL_SCR_UNIT = (
    "error: --scr-unit is required, and egfr-batch refuses to guess it.\n"
    "The same creatinine value means completely different things in "
    "mg/dL and in umol/L -- the two differ by a factor of 88.4. State it "
    "explicitly: --scr-unit mg/dL or --scr-unit umol/L.")

REFUSAL_SCYS_UNIT = (
    "error: cystatin C values are present, so --scys-unit is required, "
    "and egfr-batch refuses to guess it.\n"
    "NIDDK publishes the 2021 CKD-EPI creatinine-cystatin C equation "
    "with cystatin C in mg/L. State it explicitly: --scys-unit mg/L.")

REFUSAL_CG_WEIGHT = (
    "error: --cockcroft-gault needs --cg-weight, and egfr-batch refuses "
    "to choose a body weight for you.\n"
    "Actual, ideal and adjusted body weight can give very different "
    "Cockcroft-Gault results for the same person. State it explicitly: "
    "--cg-weight actual, --cg-weight ideal or --cg-weight adjusted.")

# Input column names (aliases map to the canonical name).
ALIASES = {
    "age": "age", "age_years": "age",
    "sex": "sex", "gender": "sex",
    "creatinine": "creatinine", "scr": "creatinine",
    "serum_creatinine": "creatinine",
    "cystatin_c": "cystatin_c", "scys": "cystatin_c",
    "cystatin": "cystatin_c",
    "height_cm": "height_cm", "height": "height_cm",
    "weight_kg": "weight_kg", "weight": "weight_kg",
}
REQUIRED_COLUMNS = ("age", "sex", "creatinine")


def build_parser():
    parser = argparse.ArgumentParser(
        prog="egfr-batch",
        description="Batch-compute CKD-EPI 2021 eGFR from a CSV of age, "
                    "sex and creatinine -- with declared units, or not "
                    "at all. Research/educational tool; not a medical "
                    "device.")
    sub = parser.add_subparsers(dest="command")

    conv = sub.add_parser(
        "convert", help="compute eGFR columns for a CSV file")
    conv.add_argument("file", help="input CSV with columns: age, sex, "
                                   "creatinine [, cystatin_c, height_cm, "
                                   "weight_kg]")
    conv.add_argument("--scr-unit", default=None,
                      help="unit of the creatinine column: mg/dL or "
                           "umol/L (required -- never guessed)")
    conv.add_argument("--scys-unit", default=None,
                      help="unit of the cystatin_c column: mg/L "
                           "(required if cystatin C values are used)")
    conv.add_argument("--cockcroft-gault", action="store_true",
                      help="also compute Cockcroft-Gault CrCl (needs "
                           "--cg-weight)")
    conv.add_argument("--cg-weight", default=None,
                      choices=("actual", "ideal", "adjusted"),
                      help="which body weight Cockcroft-Gault uses "
                           "(required with --cockcroft-gault -- never "
                           "silently chosen)")
    conv.add_argument("--deindex", action="store_true",
                      help="also de-index eGFR to mL/min using BSA "
                           "(Mosteller; needs height_cm and weight_kg)")
    conv.add_argument("--out", default=None,
                      help="output CSV (default: <input>_egfr.csv)")

    single = sub.add_parser(
        "single", help="compute eGFR for one person")
    single.add_argument("--age", type=float, required=True)
    single.add_argument("--sex", required=True, help="F or M")
    single.add_argument("--scr", type=float, required=True,
                        help="serum creatinine value")
    single.add_argument("--scr-unit", default=None,
                        help="unit of --scr: mg/dL or umol/L "
                             "(required -- never guessed)")
    single.add_argument("--scys", type=float, default=None,
                        help="serum cystatin C value (optional)")
    single.add_argument("--scys-unit", default=None,
                        help="unit of --scys: mg/L (required if "
                             "--scys is given)")
    single.add_argument("--height-cm", type=float, default=None)
    single.add_argument("--weight-kg", type=float, default=None)
    single.add_argument("--cockcroft-gault", action="store_true")
    single.add_argument("--cg-weight", default=None,
                        choices=("actual", "ideal", "adjusted"))
    single.add_argument("--deindex", action="store_true")

    sub.add_parser("check", help="verify the calculator against a "
                                 "built-in published worked example")
    return parser


def _check_option_combinations(args):
    if getattr(args, "cockcroft_gault", False) and not args.cg_weight:
        print(REFUSAL_CG_WEIGHT, file=sys.stderr)
        return False
    if args.cg_weight and not args.cockcroft_gault:
        print("error: --cg-weight was given but --cockcroft-gault was "
              "not. Add --cockcroft-gault to compute Cockcroft-Gault, "
              "or drop --cg-weight.", file=sys.stderr)
        return False
    return True


def _num(row, col, where):
    raw = row.get(col)
    if raw is None or str(raw).strip() == "":
        raise EgfrError(f"{where}{col} is missing.")
    try:
        return float(str(raw).strip())
    except ValueError:
        raise EgfrError(f"{where}{col} value '{raw}' is not a number.")


def _opt_num(row, col, where):
    raw = row.get(col)
    if raw is None or str(raw).strip() == "":
        return None
    try:
        return float(str(raw).strip())
    except ValueError:
        raise EgfrError(f"{where}{col} value '{raw}' is not a number.")


def compute_row(age, sex, scr_mgdl, scys_mg_l, height_cm, weight_kg,
                want_cg, cg_weight_choice, want_deindex, where=""):
    """Compute every requested value for one person. Returns a dict."""
    out = {}
    out["scr_used_mg_dl"] = f"{scr_mgdl:.4f}"
    cr = core.egfr_cr(age, sex, scr_mgdl)
    out["egfr_cr_ml_min_1.73m2"] = f"{cr:.1f}"
    out["egfr_cr_equation"] = core.EQUATION_CR
    crcys = None
    if scys_mg_l is not None:
        crcys = core.egfr_cr_cys(age, sex, scr_mgdl, scys_mg_l)
        out["egfr_cr_cys_ml_min_1.73m2"] = f"{crcys:.1f}"
        out["egfr_cr_cys_equation"] = core.EQUATION_CRCYS
    if want_deindex:
        if height_cm is None or weight_kg is None:
            raise EgfrError(
                f"{where}--deindex needs height_cm and weight_kg for "
                "every row (BSA, Mosteller formula).")
        bsa = core.bsa_mosteller(height_cm, weight_kg)
        out["bsa_m2_mosteller"] = f"{bsa:.3f}"
        out["egfr_cr_deindexed_ml_min"] = f"{core.deindex(cr, bsa):.1f}"
        if crcys is not None:
            out["egfr_cr_cys_deindexed_ml_min"] = \
                f"{core.deindex(crcys, bsa):.1f}"
    if want_cg:
        w, label = core.cg_weight_kg(cg_weight_choice, sex, height_cm,
                                     weight_kg, where)
        cg = core.cockcroft_gault(age, sex, scr_mgdl, w)
        out["cockcroft_gault_crcl_ml_min"] = f"{cg:.1f}"
        out["cockcroft_gault_weight"] = f"{label}: {w:.2f} kg"
        out["cockcroft_gault_equation"] = core.EQUATION_CG
    return out


def _output_fieldnames(input_fields, computed_rows, has_cys):
    fields = list(input_fields)
    fields.append("scr_used_mg_dl")
    fields.append("egfr_cr_ml_min_1.73m2")
    fields.append("egfr_cr_equation")
    if has_cys:
        fields.append("egfr_cr_cys_ml_min_1.73m2")
        fields.append("egfr_cr_cys_equation")
    # An extra column belongs in the header if ANY row produced it --
    # not just the first row. (Review fix: with --deindex, a first row
    # without cystatin C has no egfr_cr_cys_deindexed value, and keying
    # off that row alone silently dropped the whole column, losing the
    # de-indexed cr-cys values of every later row.)
    for extra in ("bsa_m2_mosteller", "egfr_cr_deindexed_ml_min",
                  "egfr_cr_cys_deindexed_ml_min",
                  "cockcroft_gault_crcl_ml_min",
                  "cockcroft_gault_weight", "cockcroft_gault_equation"):
        if extra not in fields and \
                any(extra in row for row in computed_rows):
            fields.append(extra)
    return fields


def cmd_convert(args):
    if args.scr_unit is None:
        print(REFUSAL_SCR_UNIT, file=sys.stderr)
        return 2
    scr_unit = core.normalise_scr_unit(args.scr_unit)
    scys_unit = core.normalise_scys_unit(args.scys_unit)
    if not _check_option_combinations(args):
        return 2

    path = Path(args.file)
    if not path.is_file():
        raise EgfrError(f"input file not found: {args.file}")
    if path.stat().st_size == 0:
        raise EgfrError(f"input file is empty: {args.file}")
    try:
        with path.open(newline="", encoding="utf-8-sig") as fh:
            reader = csv.DictReader(fh)
            raw_fields = reader.fieldnames or []
            rows = list(reader)
    except EgfrError:
        raise
    except Exception as exc:
        raise EgfrError(f"could not read {args.file} as CSV: {exc}")
    if not rows:
        raise EgfrError(f"{args.file} contains no data rows.")

    # Map the header onto canonical column names.
    colmap = {}
    for field in raw_fields:
        canon = ALIASES.get(str(field).strip().lower())
        if canon:
            if canon in colmap:
                raise EgfrError(
                    f"columns '{colmap[canon]}' and '{field}' both map "
                    f"to '{canon}'; keep only one.")
            colmap[canon] = field
    for required in REQUIRED_COLUMNS:
        if required not in colmap:
            raise EgfrError(
                f"required column '{required}' not found in {args.file}. "
                f"Available columns: {', '.join(raw_fields)}")

    has_cys_values = False
    if "cystatin_c" in colmap:
        has_cys_values = any(
            str(r.get(colmap["cystatin_c"]) or "").strip() != ""
            for r in rows)
    if has_cys_values and scys_unit is None:
        print(REFUSAL_SCYS_UNIT, file=sys.stderr)
        return 2
    if scys_unit is not None and not has_cys_values:
        print("note: --scys-unit was given but the file has no cystatin "
              "C values; eGFRcr-cys will not be computed.",
              file=sys.stderr)

    # Compute everything BEFORE writing anything: one bad row refuses
    # the whole run, so a partial output file is never produced.
    computed = []
    for i, raw in enumerate(rows, start=1):
        where = f"row {i}: "
        row = {canon: raw.get(orig) for canon, orig in colmap.items()}
        age = _num(row, "age", where)
        core.validate_age(age, where)
        sex = core.parse_sex(row.get("sex"), where)
        scr_raw = _num(row, "creatinine", where)
        core.validate_positive(scr_raw, "creatinine", where)
        scr_mgdl = core.scr_to_mgdl(scr_raw, scr_unit)
        scys = None
        if has_cys_values:
            scys = _opt_num(row, "cystatin_c", where)
            if scys is not None:
                core.validate_positive(scys, "cystatin_c", where)
        height = _opt_num(row, "height_cm", where) \
            if "height_cm" in colmap else None
        weight = _opt_num(row, "weight_kg", where) \
            if "weight_kg" in colmap else None
        out = compute_row(age, sex, scr_mgdl, scys, height, weight,
                          args.cockcroft_gault, args.cg_weight,
                          args.deindex, where)
        merged = dict(raw)
        merged.update(out)
        computed.append(merged)

    fields = _output_fieldnames(raw_fields, computed, has_cys_values)
    # Rows without cystatin C still need the (empty) cr-cys columns.
    for merged in computed:
        for field in fields:
            merged.setdefault(field, "")

    out_path = Path(args.out) if args.out else \
        path.with_name(path.stem + "_egfr.csv")
    try:
        with out_path.open("w", newline="", encoding="utf-8") as fh:
            writer = csv.DictWriter(fh, fieldnames=fields,
                                    extrasaction="ignore")
            writer.writeheader()
            writer.writerows(computed)
    except Exception as exc:
        raise EgfrError(f"could not write output file {out_path}: {exc}")

    n_cys = sum(1 for m in computed if m.get("egfr_cr_cys_ml_min_1.73m2"))
    print(f"computed {len(computed)} rows from {args.file}")
    print(f"  creatinine unit declared: {scr_unit} "
          f"(converted values are in scr_used_mg_dl)")
    print(f"  eGFRcr     : CKD-EPI 2021 (NIDDK / Inker et al. 2021), "
          f"all {len(computed)} rows")
    if has_cys_values:
        print(f"  eGFRcr-cys : CKD-EPI 2021 (NIDDK / Inker et al. 2021), "
              f"{n_cys} rows with cystatin C ({scys_unit})")
    if args.cockcroft_gault:
        print(f"  Cockcroft-Gault CrCl: weight = {args.cg_weight} "
              f"(user-declared)")
    if args.deindex:
        print("  de-indexed eGFR: mL/min, using BSA (Mosteller) x "
              "value / 1.73")
    print(f"  output     : {out_path}")
    return 0


def cmd_single(args):
    if args.scr_unit is None:
        print(REFUSAL_SCR_UNIT, file=sys.stderr)
        return 2
    scr_unit = core.normalise_scr_unit(args.scr_unit)
    if args.scys is not None and args.scys_unit is None:
        print(REFUSAL_SCYS_UNIT, file=sys.stderr)
        return 2
    scys_unit = core.normalise_scys_unit(args.scys_unit)
    if not _check_option_combinations(args):
        return 2
    core.validate_age(args.age)
    sex = core.parse_sex(args.sex)
    core.validate_positive(args.scr, "creatinine")
    scr_mgdl = core.scr_to_mgdl(args.scr, scr_unit)
    if args.scys is not None:
        core.validate_positive(args.scys, "cystatin C")
    out = compute_row(args.age, sex, scr_mgdl, args.scys,
                      args.height_cm, args.weight_kg,
                      args.cockcroft_gault, args.cg_weight, args.deindex)
    print(f"age {args.age:g}, sex {sex}, creatinine {args.scr:g} "
          f"{scr_unit} (= {scr_mgdl:.4f} mg/dL)")
    print(f"  eGFRcr (CKD-EPI 2021): "
          f"{out['egfr_cr_ml_min_1.73m2']} mL/min/1.73 m2")
    if "egfr_cr_cys_ml_min_1.73m2" in out:
        print(f"  cystatin C {args.scys:g} {scys_unit}")
        print(f"  eGFRcr-cys (CKD-EPI 2021): "
              f"{out['egfr_cr_cys_ml_min_1.73m2']} mL/min/1.73 m2")
    if "bsa_m2_mosteller" in out:
        print(f"  BSA (Mosteller): {out['bsa_m2_mosteller']} m2")
        print(f"  eGFRcr de-indexed: "
              f"{out['egfr_cr_deindexed_ml_min']} mL/min")
        if "egfr_cr_cys_deindexed_ml_min" in out:
            print(f"  eGFRcr-cys de-indexed: "
                  f"{out['egfr_cr_cys_deindexed_ml_min']} mL/min")
    if "cockcroft_gault_crcl_ml_min" in out:
        print(f"  Cockcroft-Gault CrCl: "
              f"{out['cockcroft_gault_crcl_ml_min']} mL/min "
              f"(weight: {out['cockcroft_gault_weight']})")
    return 0


def cmd_check(_args):
    computed, expected = core.run_known_case()
    diff = abs(computed - expected)
    print("egfr-batch check -- built-in published worked example")
    print(f"  input   : age {core.KNOWN_AGE:g}, male, creatinine "
          f"{core.KNOWN_SCR_MGDL} mg/dL")
    print(f"  computed: eGFRcr {computed:.4f} mL/min/1.73 m2")
    print(f"  expected: eGFRcr {expected:.4f} mL/min/1.73 m2 "
          "(2021 CKD-EPI creatinine equation as published by NIDDK; "
          "published worked examples round this case to 69.2 -- see "
          "tests)")
    if diff <= 0.05:
        print(f"  result  : PASS (difference {diff:.4f}, tolerance 0.05)")
        return 0
    print(f"  result  : FAIL (difference {diff:.4f} exceeds tolerance "
          "0.05)")
    return 1


def main(argv=None):
    parser = build_parser()
    args = parser.parse_args(sys.argv[1:] if argv is None else argv)
    if args.command is None:
        parser.print_help(sys.stderr)
        return 2
    try:
        if args.command == "convert":
            return cmd_convert(args)
        if args.command == "single":
            return cmd_single(args)
        if args.command == "check":
            return cmd_check(args)
    except EgfrError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    except Exception as exc:  # user errors must never show a traceback
        print(f"error: {exc}", file=sys.stderr)
        return 2
    return 2


if __name__ == "__main__":
    sys.exit(main())
