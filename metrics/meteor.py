# metrics/meteor.py
# ============================================================
# SatQuery AI — METEOR Metric
# ============================================================
# Responsibilities:
#   - Compute METEOR score for image captioning evaluation
#   - Support exact word match, stemming, and WordNet synonym matching
#   - Return per-sample scores + aggregate mean
#
# Why METEOR:
#   METEOR (Metric for Evaluation of Translation with Explicit ORdering)
#   evaluates translation and caption quality based on harmonic mean
#   of unigram precision and recall, with explicit word-to-word matching
#   including morphological variants (stemming) and WordNet synonyms.
#
# Used by:
#   - benchmarks/captioning_benchmark.py
# ============================================================

import logging
from typing import Any, List

import nltk
from nltk.translate.meteor_score import single_meteor_score

logger = logging.getLogger(__name__)

# Ensure required NLTK resources are available
for resource in ["wordnet", "omw-1.4", "punkt"]:
    try:
        nltk.download(resource, quiet=True)
    except Exception as e:
        logger.debug(f"NLTK download check for {resource}: {e}")


def tokenize_caption(text: str) -> List[str]:
    """
    Tokenizes caption text into a list of word tokens.

    Args:
        text: Caption string.

    Returns:
        List of lowercase word tokens.
    """
    if not text or not isinstance(text, str):
        return []
    try:
        tokens = nltk.word_tokenize(text.lower())
    except Exception:
        tokens = text.lower().strip().split()
    return tokens


def sentence_meteor(prediction: str, reference: str) -> float:
    """
    Computes METEOR score for a single predicted caption against reference.

    Args:
        prediction : Model generated caption.
        reference  : Ground truth caption.

    Returns:
        METEOR score in [0.0, 1.0].
    """
    if not prediction.strip() or not reference.strip():
        return 0.0

    pred_tokens = tokenize_caption(prediction)
    ref_tokens = tokenize_caption(reference)

    if not pred_tokens or not ref_tokens:
        return 0.0

    try:
        score = single_meteor_score(ref_tokens, pred_tokens)
        return round(float(score), 4)
    except Exception as e:
        logger.warning(f"Error computing single METEOR score: {e}")
        return 0.0


def compute_meteor(
    predictions: list[str],
    references: list[str],
) -> dict[str, Any]:
    """
    Runs METEOR evaluation across captioning predictions.

    Args:
        predictions : List of model generated captions.
        references  : List of ground truth reference captions.

    Returns:
        Dict with:
            meteor_mean (float) : Mean METEOR score across samples in [0.0, 1.0].
            total       (int)   : Total samples evaluated.
            per_sample  (list)  : Per-sample evaluation records.

    Raises:
        ValueError: If predictions and references differ in length.
    """
    if len(predictions) != len(references):
        raise ValueError(
            f"Length mismatch: {len(predictions)} predictions vs {len(references)} references."
        )

    if not predictions:
        return {
            "meteor_mean": 0.0,
            "total": 0,
            "per_sample": [],
        }

    per_sample = []
    scores = []

    for idx, (pred, ref) in enumerate(zip(predictions, references)):
        score = sentence_meteor(pred, ref)
        scores.append(score)

        per_sample.append({
            "idx": idx,
            "prediction": pred,
            "reference": ref,
            "meteor": score,
        })

    meteor_mean = round(sum(scores) / len(scores), 4) if scores else 0.0

    result = {
        "meteor_mean": meteor_mean,
        "total": len(predictions),
        "per_sample": per_sample,
    }

    logger.info(
        f"METEOR — Mean: {meteor_mean:.4f} | Total: {len(predictions)}"
    )

    return result
