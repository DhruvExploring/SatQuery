# metrics/rouge.py
# ============================================================
# SatQuery AI — ROUGE-L Metric
# ============================================================
# Responsibilities:
#   - Compute ROUGE-L F1 score for captioning task
#   - Return per-sample scores + aggregate mean
#
# Why alongside BLEU-4:
#   BLEU-4 requires overlapping 4-grams in the SAME order as the
#   reference, which heavily penalizes captions that describe the
#   right content in different phrasing/structure. ROUGE-L (longest
#   common subsequence) gives partial credit for shared wording
#   without requiring exact n-gram runs, so it separates "wrong
#   content" from "right content, different style" failures.
#
# Used by:
#   - benchmarks/captioning_benchmark.py
# ============================================================

import logging
from typing import Any

from rouge_score import rouge_scorer

logger = logging.getLogger(__name__)

_scorer = rouge_scorer.RougeScorer(["rougeL"], use_stemmer=True)


# ── Sentence-level ROUGE-L ──────────────────────────────────────
def sentence_rouge_l(prediction: str, reference: str) -> float:
    """
    Computes ROUGE-L F1 for one predicted caption against its
    reference.

    Args:
        prediction : Model generated caption.
        reference  : Ground truth caption.

    Returns:
        ROUGE-L F-measure in [0.0, 1.0].
    """
    if not prediction.strip() or not reference.strip():
        return 0.0

    score = _scorer.score(reference, prediction)
    return round(float(score["rougeL"].fmeasure), 4)


# ── Full Captioning Evaluation ───────────────────────────────────
def compute_rouge(
    predictions: list[str],
    references:  list[str],
) -> dict[str, Any]:
    """
    Runs ROUGE-L evaluation for the captioning benchmark.

    Args:
        predictions : List of model generated captions.
        references  : List of ground truth captions.

    Returns:
        Dict with:
            rougeL_mean (float) : Mean ROUGE-L F1 across samples
            total       (int)   : Total samples
            per_sample  (list)  : Per-sample score dicts

    Raises:
        ValueError: If predictions and references differ in length.
    """
    if len(predictions) != len(references):
        raise ValueError(
            f"Length mismatch: {len(predictions)} predictions "
            f"vs {len(references)} references."
        )

    if not predictions:
        return {
            "rougeL_mean": 0.0,
            "total":       0,
            "per_sample":  [],
        }

    per_sample = []
    scores     = []

    for idx, (pred, ref) in enumerate(zip(predictions, references)):
        score = sentence_rouge_l(pred, ref)
        scores.append(score)

        per_sample.append({
            "idx":        idx,
            "prediction": pred,
            "reference":  ref,
            "rougeL":     score,
        })

    rougeL_mean = round(sum(scores) / len(scores), 4)

    result = {
        "rougeL_mean": rougeL_mean,
        "total":       len(predictions),
        "per_sample":  per_sample,
    }

    logger.info(
        f"ROUGE-L — Mean: {rougeL_mean:.4f} | "
        f"Total: {len(predictions)}"
    )

    return result
