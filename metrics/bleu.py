# metrics/bleu.py
# ============================================================
# SatQuery AI — BLEU Score Metric
# ============================================================
# Responsibilities:
#   - Compute BLEU-4 score for captioning task
#   - Support corpus-level and sentence-level scoring
#   - Return per-sample scores + aggregate
#
# Used by:
#   - benchmarks/captioning_benchmark.py
# ============================================================

import logging
from typing import Any

import nltk
from nltk.translate.bleu_score import (
    corpus_bleu,
    sentence_bleu,
    SmoothingFunction,
)

from config import METRIC_CONFIG

logger = logging.getLogger(__name__)

# Ensure NLTK tokenizer is available
try:
    nltk.data.find("tokenizers/punkt")
except LookupError:
    nltk.download("punkt", quiet=True)

try:
    nltk.data.find("tokenizers/punkt_tab")
except LookupError:
    nltk.download("punkt_tab", quiet=True)


# ── Tokenization ──────────────────────────────────────────────
def _tokenize(text: str) -> list[str]:
    """
    Tokenizes text into lowercase word tokens.
    Uses NLTK word_tokenize for consistent tokenization.

    Args:
        text : Input string.

    Returns:
        List of lowercase token strings.
    """
    return nltk.word_tokenize(text.lower())


# ── Sentence-level BLEU ───────────────────────────────────────
def sentence_bleu_score(
    prediction: str,
    reference:  str,
    weights:    tuple = None,
) -> float:
    """
    Computes sentence-level BLEU score for one caption.
    Uses smoothing to handle short captions gracefully.

    Args:
        prediction : Model generated caption.
        reference  : Ground truth caption.
        weights    : N-gram weights. Default: BLEU-4 (0.25 each)

    Returns:
        BLEU score in [0.0, 1.0].
    """
    if weights is None:
        weights = METRIC_CONFIG["bleu_weights"]

    pred_tokens = _tokenize(prediction)
    ref_tokens  = _tokenize(reference)

    if not pred_tokens or not ref_tokens:
        return 0.0

    smoother = SmoothingFunction().method1

    score = sentence_bleu(
        references=[ref_tokens],
        hypothesis=pred_tokens,
        weights=weights,
        smoothing_function=smoother,
    )

    return round(float(score), 4)


# ── Corpus-level BLEU ─────────────────────────────────────────
def corpus_bleu_score(
    predictions: list[str],
    references:  list[str],
    weights:     tuple = None,
) -> float:
    """
    Computes corpus-level BLEU-4 score over all captions.
    Corpus-level is the standard evaluation metric for
    image captioning benchmarks.

    Args:
        predictions : List of model generated captions.
        references  : List of ground truth captions.
        weights     : N-gram weights. Default: BLEU-4.

    Returns:
        Corpus BLEU score in [0.0, 1.0].

    Raises:
        ValueError: If predictions and references differ in length.
    """
    if weights is None:
        weights = METRIC_CONFIG["bleu_weights"]

    if len(predictions) != len(references):
        raise ValueError(
            f"Length mismatch: {len(predictions)} predictions "
            f"vs {len(references)} references."
        )

    if not predictions:
        logger.warning("corpus_bleu_score called with empty lists.")
        return 0.0

    # NLTK corpus_bleu expects list of reference lists
    ref_tokens  = [[_tokenize(r)] for r in references]
    pred_tokens = [_tokenize(p)   for p in predictions]

    score = corpus_bleu(
        list_of_references=ref_tokens,
        hypotheses=pred_tokens,
        weights=weights,
    )

    return round(float(score), 4)


# ── Full Captioning Evaluation ────────────────────────────────
def compute_bleu(
    predictions: list[str],
    references:  list[str],
) -> dict[str, Any]:
    """
    Runs complete BLEU evaluation for captioning benchmark.
    Returns both corpus-level and per-sample scores.

    Args:
        predictions : List of model generated captions.
        references  : List of ground truth captions.

    Returns:
        Dict with:
            bleu4_corpus  (float) : Corpus BLEU-4 score
            bleu4_mean    (float) : Mean sentence BLEU-4
            total         (int)   : Total samples
            per_sample    (list)  : Per-sample score dicts
    """
    if len(predictions) != len(references):
        raise ValueError(
            f"Length mismatch: {len(predictions)} predictions "
            f"vs {len(references)} references."
        )

    if not predictions:
        return {
            "bleu4_corpus": 0.0,
            "bleu4_mean":   0.0,
            "total":        0,
            "per_sample":   [],
        }

    # Per-sample sentence BLEU
    per_sample     = []
    sentence_scores = []

    for idx, (pred, ref) in enumerate(
        zip(predictions, references)
    ):
        score = sentence_bleu_score(pred, ref)
        sentence_scores.append(score)

        per_sample.append({
            "idx":        idx,
            "prediction": pred,
            "reference":  ref,
            "bleu4":      score,
        })

    # Corpus-level BLEU
    bleu4_corpus = corpus_bleu_score(predictions, references)
    bleu4_mean   = round(
        sum(sentence_scores) / len(sentence_scores), 4
    )

    result = {
        "bleu4_corpus": bleu4_corpus,
        "bleu4_mean":   bleu4_mean,
        "total":        len(predictions),
        "per_sample":   per_sample,
    }

    logger.info(
        f"BLEU-4 — Corpus: {bleu4_corpus:.4f} | "
        f"Mean: {bleu4_mean:.4f} | "
        f"Total: {len(predictions)}"
    )

    return result


# ── Failure Analysis ──────────────────────────────────────────
def get_low_bleu_cases(
    per_sample: list[dict[str, Any]],
    threshold:  float = 0.1,
) -> list[dict[str, Any]]:
    """
    Returns samples with BLEU-4 below threshold.
    Used for failure analysis in baseline report.

    Args:
        per_sample : Output of compute_bleu()["per_sample"]
        threshold  : BLEU-4 below which sample is a failure.

    Returns:
        List of low-scoring sample dicts.
    """
    failures = [
        s for s in per_sample
        if s["bleu4"] < threshold
    ]

    logger.info(
        f"Low BLEU cases: {len(failures)}/{len(per_sample)} "
        f"(threshold={threshold})"
    )

    return failures