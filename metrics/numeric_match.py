# metrics/numeric_match.py
# ============================================================
# SatQuery AI — Numeric Exact Match Metric
# ============================================================
# Responsibilities:
#   - Extract numerical values from prediction and reference strings
#   - Compare extracted numbers exactly (accounting for int/float/units)
#   - Specialized for RSVQA Count and Area tasks
#
# Examples:
#   - "495m2" vs "495" -> Match (495 == 495)
#   - "There are 3 buildings" vs "3" -> Match (3 == 3)
#   - "0m2" vs "0" -> Match (0 == 0)
#
# Used by:
#   - benchmarks/vqa_benchmark.py (RSVQA dataset only)
# ============================================================

import logging
import re
from typing import Any, List, Optional, Tuple, Union

logger = logging.getLogger(__name__)

# Regex pattern for integers and decimal numbers
NUMERIC_REGEX = re.compile(r"[-+]?(?:\d*\.\d+|\d+)")


def extract_numbers(text: str) -> List[float]:
    """
    Extracts all numeric values from a given text string.

    Args:
        text : Natural language string or formatted measurement (e.g. '495m2', '3').

    Returns:
        List of extracted numbers as floats.
    """
    if not text or not isinstance(text, str):
        return []

    # Clean text: remove commas in numbers like 1,000
    cleaned = text.replace(",", "")
    matches = NUMERIC_REGEX.findall(cleaned)
    results = []
    for m in matches:
        try:
            results.append(float(m))
        except ValueError:
            continue
    return results


TupleResult = Tuple[bool, Optional[float], Optional[float]]


def match_numeric_single(prediction: str, reference: str) -> TupleResult:
    """
    Evaluates numeric match between a single prediction and reference.

    Args:
        prediction : Model predicted text.
        reference  : Ground truth text.

    Returns:
        tuple of (is_match: bool, pred_num: Optional[float], ref_num: Optional[float])
    """
    pred_nums = extract_numbers(prediction)
    ref_nums = extract_numbers(reference)

    pred_val = pred_nums[0] if pred_nums else None
    ref_val = ref_nums[0] if ref_nums else None

    if ref_val is None:
        # Reference has no numeric value (e.g., non-numeric question)
        is_match = False
    elif pred_val is None:
        is_match = False
    else:
        # Check equality with small float tolerance
        is_match = abs(pred_val - ref_val) < 1e-5

    return is_match, pred_val, ref_val


def compute_numeric_match(
    predictions: list[str],
    references: list[str],
) -> dict[str, Any]:
    """
    Computes numeric extract match accuracy across a dataset.

    Args:
        predictions : List of model generated strings.
        references  : List of ground truth reference strings.

    Returns:
        Dict with:
            numeric_accuracy (float) : Exact match accuracy of extracted numbers in [0.0, 1.0].
            total            (int)   : Total samples evaluated.
            matched_count    (int)   : Count of correct numeric matches.
            per_sample       (list)  : Detailed per-sample records.

    Raises:
        ValueError: If predictions and references have differing lengths.
    """
    if len(predictions) != len(references):
        raise ValueError(
            f"Length mismatch: {len(predictions)} predictions vs {len(references)} references."
        )

    if not predictions:
        return {
            "numeric_accuracy": 0.0,
            "total": 0,
            "matched_count": 0,
            "per_sample": [],
        }

    per_sample = []
    matched_count = 0

    for idx, (pred, ref) in enumerate(zip(predictions, references)):
        is_match, pred_num, ref_num = match_numeric_single(pred, ref)
        if is_match:
            matched_count += 1

        per_sample.append({
            "idx": idx,
            "prediction": pred,
            "reference": ref,
            "extracted_prediction": pred_num,
            "extracted_reference": ref_num,
            "is_match": is_match,
        })

    accuracy = round(matched_count / len(predictions), 4) if predictions else 0.0

    result = {
        "numeric_accuracy": accuracy,
        "total": len(predictions),
        "matched_count": matched_count,
        "per_sample": per_sample,
    }

    logger.info(
        f"Numeric Match — Accuracy: {accuracy*100:.2f}% | "
        f"Matched: {matched_count}/{len(predictions)}"
    )

    return result
