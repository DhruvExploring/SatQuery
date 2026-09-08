# metrics/accuracy.py
# ============================================================
# SatQuery AI — Accuracy Metric
# ============================================================
# Responsibilities:
#   - Compute exact match accuracy for VQA tasks
#   - Compute soft match (normalized string comparison)
#   - Handle yes/no binary answer normalization
#   - Return per-sample results + aggregate score
#
# Used by:
#   - benchmarks/vqa_benchmark.py
#   - benchmarks/change_vqa_benchmark.py
# ============================================================

import logging
import re
import string
from typing import Any

logger = logging.getLogger(__name__)


# ── Constants ────────────────────────────────────────────────
YES_TOKENS = {"yes", "true", "correct", "affirmative", "1"}
NO_TOKENS  = {"no",  "false", "incorrect", "negative",  "0"}


# ── Normalization ─────────────────────────────────────────────
def _normalize(text: str) -> str:
    """
    Normalizes a string for fair comparison.

    Steps:
        1. Lowercase
        2. Strip leading/trailing whitespace
        3. Remove punctuation
        4. Collapse multiple spaces to one

    Args:
        text : Raw string from model or ground truth.

    Returns:
        Normalized string.
    """
    text = text.lower().strip()
    text = text.translate(str.maketrans("", "", string.punctuation))
    text = re.sub(r"\s+", " ", text)
    return text


def _normalize_binary(text: str) -> str:
    """
    Normalizes yes/no answers to a canonical form.
    Maps variations ("correct", "affirmative") → "yes"
    Maps variations ("incorrect", "negative")  → "no"

    Args:
        text : Raw answer string.

    Returns:
        "yes", "no", or the original normalized text.
    """
    norm = _normalize(text)

    if norm in YES_TOKENS:
        return "yes"
    if norm in NO_TOKENS:
        return "no"

    # Check if the answer starts with yes/no
    if norm.startswith("yes"):
        return "yes"
    if norm.startswith("no"):
        return "no"

    return norm


# ── Per-Sample Scoring ────────────────────────────────────────
def exact_match(prediction: str, ground_truth: str) -> bool:
    """
    Returns True if prediction matches ground truth exactly
    after normalization.

    Args:
        prediction   : Model's output answer.
        ground_truth : Dataset ground truth answer.

    Returns:
        True if exact match, False otherwise.
    """
    return _normalize(prediction) == _normalize(ground_truth)


def soft_match(prediction: str, ground_truth: str) -> float:
    """
    Returns a soft match score in [0.0, 1.0].
    Checks if ground truth tokens appear in prediction.

    Useful when model gives verbose answers:
        GT: "yes"
        Pred: "Yes, there is a river visible."
        Exact match → False
        Soft match  → 1.0 ✅

    Args:
        prediction   : Model's output answer.
        ground_truth : Dataset ground truth answer.

    Returns:
        Float in [0.0, 1.0].
    """
    pred_norm = _normalize(prediction)
    gt_norm   = _normalize(ground_truth)

    if not gt_norm:
        return 0.0

    # Full exact match
    if pred_norm == gt_norm:
        return 1.0

    # Check if all GT tokens appear in prediction
    gt_tokens   = set(gt_norm.split())
    pred_tokens = set(pred_norm.split())

    if not gt_tokens:
        return 0.0

    overlap = gt_tokens & pred_tokens
    return len(overlap) / len(gt_tokens)


def binary_match(prediction: str, ground_truth: str) -> bool:
    """
    Returns True if both prediction and ground truth
    resolve to the same yes/no canonical value.

    Args:
        prediction   : Model's output answer.
        ground_truth : Dataset ground truth answer.

    Returns:
        True if binary match, False otherwise.
    """
    return (
        _normalize_binary(prediction)
        == _normalize_binary(ground_truth)
    )


# ── Aggregate Accuracy ────────────────────────────────────────
def compute_accuracy(
    predictions:   list[str],
    ground_truths: list[str],
    use_soft:      bool = True,
    is_binary:     bool = False,
) -> dict[str, Any]:
    """
    Computes accuracy over a list of predictions.

    Args:
        predictions   : List of model output strings.
        ground_truths : List of ground truth strings.
        use_soft      : If True, uses soft match alongside exact.
                        Recommended for VQA where answers
                        may be verbose.
        is_binary     : If True, normalizes yes/no answers.
                        Set True for presence-type questions.

    Returns:
        Dict with:
            exact_accuracy (float) : Exact match accuracy [0,1]
            soft_accuracy  (float) : Soft match accuracy [0,1]
            total          (int)   : Total samples evaluated
            correct_exact  (int)   : Exact match count
            correct_soft   (int)   : Soft match count
            per_sample     (list)  : Per-sample result dicts

    Raises:
        ValueError: If predictions and ground_truths lengths differ.
    """
    if len(predictions) != len(ground_truths):
        raise ValueError(
            f"Length mismatch: {len(predictions)} predictions "
            f"vs {len(ground_truths)} ground truths."
        )

    if not predictions:
        logger.warning("compute_accuracy called with empty lists.")
        return {
            "exact_accuracy": 0.0,
            "soft_accuracy":  0.0,
            "total":          0,
            "correct_exact":  0,
            "correct_soft":   0,
            "per_sample":     [],
        }

    correct_exact = 0
    correct_soft  = 0
    per_sample    = []

    for idx, (pred, gt) in enumerate(
        zip(predictions, ground_truths)
    ):
        if is_binary:
            is_exact = binary_match(pred, gt)
            soft_sc  = 1.0 if is_exact else 0.0
        else:
            is_exact = exact_match(pred, gt)
            soft_sc  = soft_match(pred, gt) if use_soft else (
                1.0 if is_exact else 0.0
            )

        if is_exact:
            correct_exact += 1
        if soft_sc >= 0.5:
            correct_soft += 1

        per_sample.append({
            "idx":          idx,
            "prediction":   pred,
            "ground_truth": gt,
            "exact_match":  is_exact,
            "soft_score":   round(soft_sc, 4),
        })

    total = len(predictions)

    result = {
        "exact_accuracy": round(correct_exact / total, 4),
        "soft_accuracy":  round(correct_soft  / total, 4),
        "total":          total,
        "correct_exact":  correct_exact,
        "correct_soft":   correct_soft,
        "per_sample":     per_sample,
    }

    logger.info(
        f"Accuracy — Exact: {result['exact_accuracy']*100:.1f}% | "
        f"Soft: {result['soft_accuracy']*100:.1f}% | "
        f"Total: {total}"
    )

    return result


# ── Failure Analysis ──────────────────────────────────────────
def get_failure_cases(
    per_sample: list[dict[str, Any]],
    threshold:  float = 0.5,
) -> list[dict[str, Any]]:
    """
    Returns samples where the model failed (soft_score < threshold).
    Used to generate failure patterns for the baseline report.

    Args:
        per_sample : Output of compute_accuracy()["per_sample"]
        threshold  : Soft score below which a sample is a failure.

    Returns:
        List of failed sample dicts.
    """
    failures = [
        s for s in per_sample
        if s["soft_score"] < threshold
    ]

    logger.info(
        f"Failure cases: {len(failures)}/{len(per_sample)} "
        f"(threshold={threshold})"
    )

    return failures