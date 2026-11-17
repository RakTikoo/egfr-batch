"""Core calculation logic for egfr-batch.

Everything here is published-formula arithmetic, and nothing else:

- 2021 CKD-EPI creatinine equation (eGFRcr) and 2021 CKD-EPI
  creatinine-cystatin C equation (eGFRcr-cys), exactly as published by
  NIDDK (National Institute of Diabetes and Digestive and Kidney
  Diseases), from Inker et al., "New Creatinine- and Cystatin C-Based
  Equations to Estimate GFR without Race", NEJM 2021;385:1737-1749.
- Cockcroft-Gault creatinine clearance (Cockcroft & Gault, Nephron
  1976;16:31-41), only when the caller explicitly asks for it and
  explicitly declares which body weight to use.
- Body surface area by the Mosteller formula (Mosteller, NEJM
  1987;317:1098), used only to de-index an indexed eGFR
  (multiply by BSA / 1.73) when the caller explicitly asks for it.

This module computes numbers. It does not interpret them: there is no
staging, no flagging, and no diagnostic output anywhere in this tool.

Units are never guessed. Creatinine must be declared as mg/dL or
umol/L by the caller and is converted with the NIDDK-published factor
(umol/L to mg/dL: divide by 88.4). Cystatin C is used in mg/L, the
unit NIDDK publishes for it ("cystatin C does not require unit
conversion"), and the caller must declare that unit explicitly too.

The adult CKD-EPI equations are for ages 18 and older (NIDDK). Younger
ages are refused, not extrapolated.
"""

from __future__ import annotations

import math

# --- Published constants: 2021 CKD-EPI creatinine (NIDDK / Inker 2021) ---
CR_COEFF = 142.0
CR_KAPPA = {"F": 0.7, "M": 0.9}
CR_ALPHA = {"F": -0.241, "M": -0.302}
CR_MAX_EXPONENT = -1.200
CR_AGE_FACTOR = 0.9938
CR_FEMALE_FACTOR = 1.012

# --- Published constants: 2021 CKD-EPI creatinine-cystatin C --------------
CRCYS_COEFF = 135.0
CRCYS_ALPHA = {"F": -0.219, "M": -0.144}  # kappa is the same as for eGFRcr
CRCYS_SCR_MAX_EXPONENT = -0.544
CYS_BREAKPOINT = 0.8  # mg/L
CYS_MIN_EXPONENT = -0.323
CYS_MAX_EXPONENT = -0.778
CRCYS_AGE_FACTOR = 0.9961
CRCYS_FEMALE_FACTOR = 0.963

# NIDDK conversion: serum creatinine umol/L to mg/dL, divide by 88.4.
UMOL_PER_MGDL = 88.4

SCR_UNITS = ("mg/dL", "umol/L")
SCYS_UNITS = ("mg/L",)

MIN_ADULT_AGE = 18.0

EQUATION_CR = "CKD-EPI 2021 eGFRcr (Inker et al. NEJM 2021; NIDDK)"
EQUATION_CRCYS = "CKD-EPI 2021 eGFRcr-cys (Inker et al. NEJM 2021; NIDDK)"
EQUATION_CG = "Cockcroft-Gault CrCl (Cockcroft & Gault 1976)"

# Built-in reference case, also used by `egfr-batch check` and the tests.
# A 60-year-old male with Scr 1.2 mg/dL. Independently published worked
# examples give 69.2 for exactly this case (see tests/test_egfr_batch.py
# for the pinned oracle values and their sources).
KNOWN_AGE = 60.0
KNOWN_SEX = "M"
KNOWN_SCR_MGDL = 1.2
KNOWN_EGFR_CR = 69.2311  # computed from the published equation; see tests


class EgfrError(Exception):
    """A user-facing error: print the message, exit non-zero, no traceback."""


def normalise_scr_unit(text):
    """Return the canonical creatinine unit or raise EgfrError."""
    if text is None:
        return None
    t = str(text).strip().lower().replace("µ", "u").replace("μ", "u")
    if t in ("mg/dl", "mgdl"):
        return "mg/dL"
    if t in ("umol/l", "umol", "micromol/l", "umoll"):
        return "umol/L"
    raise EgfrError(
        f"creatinine unit '{text}' is not understood. "
        "Use --scr-unit mg/dL or --scr-unit umol/L.")


def normalise_scys_unit(text):
    """Return the canonical cystatin C unit or raise EgfrError."""
    if text is None:
        return None
    t = str(text).strip().lower()
    if t in ("mg/l", "mgl"):
        return "mg/L"
    raise EgfrError(
        f"cystatin C unit '{text}' is not supported. NIDDK publishes the "
        "2021 CKD-EPI creatinine-cystatin C equation with cystatin C in "
        "mg/L and no unit conversion. Convert to mg/L first, then declare "
        "--scys-unit mg/L.")


def parse_sex(value, where=""):
    """Parse a sex value to 'F' or 'M'. The equations define only these."""
    t = str(value).strip().lower() if value is not None else ""
    if t in ("f", "female", "woman"):
        return "F"
    if t in ("m", "male", "man"):
        return "M"
    raise EgfrError(
        f"{where}sex value '{value}' is not understood. The published "
        "equations define coefficients for female and male only; use "
        "F or M (female/male are also accepted).")


def scr_to_mgdl(value, unit):
    """Convert a creatinine value to mg/dL using the declared unit."""
    if unit == "mg/dL":
        return value
    if unit == "umol/L":
        return value / UMOL_PER_MGDL
    raise EgfrError(f"creatinine unit '{unit}' was not declared.")


def validate_age(age, where=""):
    if age is None or not math.isfinite(age):
        raise EgfrError(f"{where}age is missing or not a number.")
    if age < MIN_ADULT_AGE:
        raise EgfrError(
            f"{where}age {age:g} is under 18. The CKD-EPI 2021 equations "
            "published by NIDDK are adult equations (ages 18 and older); "
            "this tool refuses to apply them to younger ages.")
    if age > 130:
        raise EgfrError(f"{where}age {age:g} is not plausible as years.")


def validate_sex(sex):
    """Core functions take the canonical 'F'/'M' only (parse_sex maps
    user input onto them). Anything else is refused with EgfrError --
    never a bare KeyError, and never a silent default to one sex's
    coefficients (review fix: ideal_body_weight_kg treated any non-'M'
    value as female, and cockcroft_gault treated it as male)."""
    if sex not in ("F", "M"):
        raise EgfrError(
            f"sex '{sex}' is not understood. The published equations "
            "define coefficients for female and male only; use 'F' or "
            "'M' (see parse_sex for accepted spellings).")


def validate_positive(value, name, where=""):
    if value is None or not math.isfinite(value) or value <= 0:
        raise EgfrError(
            f"{where}{name} must be a positive number, got '{value}'.")
    return value


def egfr_cr(age, sex, scr_mgdl):
    """2021 CKD-EPI creatinine eGFR, mL/min/1.73 m2.

    eGFR = 142 x min(Scr/k, 1)^alpha x max(Scr/k, 1)^-1.200
           x 0.9938^Age x 1.012 [if female]
    k = 0.7 (F) / 0.9 (M); alpha = -0.241 (F) / -0.302 (M).
    Scr is standardised serum creatinine in mg/dL.
    """
    validate_sex(sex)
    validate_age(age)
    validate_positive(scr_mgdl, "creatinine")
    ratio = scr_mgdl / CR_KAPPA[sex]
    value = (CR_COEFF
             * min(ratio, 1.0) ** CR_ALPHA[sex]
             * max(ratio, 1.0) ** CR_MAX_EXPONENT
             * CR_AGE_FACTOR ** age)
    if sex == "F":
        value *= CR_FEMALE_FACTOR
    return value


def egfr_cr_cys(age, sex, scr_mgdl, scys_mg_l):
    """2021 CKD-EPI creatinine-cystatin C eGFR, mL/min/1.73 m2.

    eGFR = 135 x min(Scr/k, 1)^alpha x max(Scr/k, 1)^-0.544
           x min(Scys/0.8, 1)^-0.323 x max(Scys/0.8, 1)^-0.778
           x 0.9961^Age x 0.963 [if female]
    k = 0.7 (F) / 0.9 (M); alpha = -0.219 (F) / -0.144 (M).
    Scr in mg/dL, Scys (cystatin C) in mg/L.
    """
    validate_sex(sex)
    validate_age(age)
    validate_positive(scr_mgdl, "creatinine")
    validate_positive(scys_mg_l, "cystatin C")
    scr_ratio = scr_mgdl / CR_KAPPA[sex]
    cys_ratio = scys_mg_l / CYS_BREAKPOINT
    value = (CRCYS_COEFF
             * min(scr_ratio, 1.0) ** CRCYS_ALPHA[sex]
             * max(scr_ratio, 1.0) ** CRCYS_SCR_MAX_EXPONENT
             * min(cys_ratio, 1.0) ** CYS_MIN_EXPONENT
             * max(cys_ratio, 1.0) ** CYS_MAX_EXPONENT
             * CRCYS_AGE_FACTOR ** age)
    if sex == "F":
        value *= CRCYS_FEMALE_FACTOR
    return value


def bsa_mosteller(height_cm, weight_kg):
    """Body surface area in m2: sqrt(height_cm x weight_kg / 3600)."""
    validate_positive(height_cm, "height_cm")
    validate_positive(weight_kg, "weight_kg")
    return math.sqrt(height_cm * weight_kg / 3600.0)


def deindex(egfr_indexed, bsa_m2):
    """De-index an eGFR (mL/min/1.73 m2) to mL/min: x BSA / 1.73."""
    validate_positive(bsa_m2, "BSA")
    return egfr_indexed * bsa_m2 / 1.73


def ideal_body_weight_kg(sex, height_cm):
    """Devine ideal body weight: 50 (M) / 45.5 (F) kg + 2.3 kg per inch
    of height over 5 feet (60 inches). Used only when the caller
    explicitly declares --cg-weight ideal or adjusted."""
    validate_sex(sex)
    validate_positive(height_cm, "height_cm")
    inches_over = height_cm / 2.54 - 60.0
    base = 50.0 if sex == "M" else 45.5
    ibw = base + 2.3 * inches_over
    if ibw <= 0:
        # The Devine formula is a straight line; far below 5 feet it
        # crosses zero (at ~102 cm for females, ~97 cm for males) and
        # would hand Cockcroft-Gault a non-positive weight. Refuse
        # with the reason instead of a confusing downstream error or
        # an adjusted weight built on a negative IBW (review fix).
        raise EgfrError(
            f"ideal body weight (Devine) for height {height_cm:g} cm "
            f"is {ibw:.2f} kg, which is not positive. The Devine "
            "formula does not give a usable weight at this height, so "
            "Cockcroft-Gault with --cg-weight ideal or adjusted "
            "cannot be computed for this row.")
    return ibw


def cg_weight_kg(choice, sex, height_cm, weight_kg, where=""):
    """Resolve the explicitly declared Cockcroft-Gault weight choice."""
    if choice == "actual":
        if weight_kg is None:
            raise EgfrError(
                f"{where}--cg-weight actual needs a weight_kg value.")
        return validate_positive(weight_kg, "weight_kg", where), "actual"
    if height_cm is None:
        raise EgfrError(
            f"{where}--cg-weight {choice} needs a height_cm value "
            "to compute ideal body weight (Devine).")
    ibw = ideal_body_weight_kg(sex, height_cm)
    if choice == "ideal":
        return ibw, "ideal (Devine)"
    if choice == "adjusted":
        if weight_kg is None:
            raise EgfrError(
                f"{where}--cg-weight adjusted needs a weight_kg value.")
        validate_positive(weight_kg, "weight_kg", where)
        return ibw + 0.4 * (weight_kg - ibw), "adjusted (IBW + 0.4 x (actual - IBW))"
    raise EgfrError(f"unknown --cg-weight choice '{choice}'.")


def cockcroft_gault(age, sex, scr_mgdl, weight_kg):
    """Cockcroft-Gault creatinine clearance, mL/min (not indexed).

    CrCl = ((140 - Age) x Weight_kg / (72 x Scr_mg/dL)) x 0.85 [if female]
    """
    validate_sex(sex)
    validate_age(age)
    validate_positive(scr_mgdl, "creatinine")
    validate_positive(weight_kg, "weight for Cockcroft-Gault")
    value = (140.0 - age) * weight_kg / (72.0 * scr_mgdl)
    if sex == "F":
        value *= 0.85
    return value


def run_known_case():
    """Compute the built-in reference case; return (computed, expected)."""
    return egfr_cr(KNOWN_AGE, KNOWN_SEX, KNOWN_SCR_MGDL), KNOWN_EGFR_CR
