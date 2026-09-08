# metrics/sbert_cosine.py
# ============================================================
# SatQuery AI — SBERT Cosine Similarity Metric
# ============================================================
# Responsibilities:
#   - Compute semantic embedding cosine similarity between predictions and references
#   - Uses sentence-transformers with 'all-MiniLM-L6-v2'
#   - Applied to both VQA and Captioning evaluation tasks
#
# Mathematical note:
#   Cosine similarity outputs values in [-1.0, 1.0].
#   Values are NOT clamped to [0, 1] to preserve true directional alignment.
#
# Used by:
#   - benchmarks/vqa_benchmark.py
#   - benchmarks/captioning_benchmark.py
# ============================================================

import logging
from typing import Any, Optional

import torch

logger = logging.getLogger(__name__)

# Global model cache to avoid re-instantiating the SBERT encoder
_sbert_model = None
_MODEL_NAME = "all-MiniLM-L6-v2"


def get_sbert_model():
    """
    Loads and caches the SentenceTransformer model.

    Raises:
        ImportError: If sentence-transformers package is not installed.
    """
    global _sbert_model
    if _sbert_model is None:
        try:
            from sentence_transformers import SentenceTransformer
        except ImportError as e:
            raise ImportError(
                "sentence-transformers is not installed. Please install it via "
                "'pip install sentence-transformers' to compute SBERT Cosine Similarity."
            ) from e

        logger.info(f"Loading SentenceTransformer model: {_MODEL_NAME}...")
        _sbert_model = SentenceTransformer(_MODEL_NAME)
    return _sbert_model


def compute_sbert_cosine(
    predictions: list[str],
    references: list[str],
    batch_size: int = 64,
) -> dict[str, Any]:
    """
    Computes SBERT embedding cosine similarity across candidate predictions and references.

    Args:
        predictions : List of predicted strings (answers or captions).
        references  : List of ground truth reference strings.
        batch_size  : Batch size for encoding embeddings.

    Returns:
        Dict with:
            mean_cosine (float) : Mean cosine similarity in [-1.0, 1.0].
            total       (int)   : Total evaluated samples.
            per_sample  (list)  : Per-sample evaluation dictionaries.

    Raises:
        ValueError: If predictions and references differ in length.
        ImportError: If sentence-transformers is missing.
    """
    if len(predictions) != len(references):
        raise ValueError(
            f"Length mismatch: {len(predictions)} predictions vs {len(references)} references."
        )

    if not predictions:
        return {
            "mean_cosine": 0.0,
            "total": 0,
            "per_sample": [],
        }

    model = get_sbert_model()

    # Clean text inputs for encoding (convert empty strings to placeholder spaces)
    preds_clean = [p.strip() if p.strip() else " " for p in predictions]
    refs_clean = [r.strip() if r.strip() else " " for r in references]

    # Compute dense embeddings with L2 normalization
    embeddings_pred = model.encode(
        preds_clean,
        batch_size=batch_size,
        show_progress_bar=False,
        convert_to_tensor=True,
        normalize_embeddings=True,
    )

    embeddings_ref = model.encode(
        refs_clean,
        batch_size=batch_size,
        show_progress_bar=False,
        convert_to_tensor=True,
        normalize_embeddings=True,
    )

    # For unit vectors, cosine similarity is the dot product
    cosine_scores = (embeddings_pred * embeddings_ref).sum(dim=-1)
    cosine_scores_list = cosine_scores.cpu().tolist()

    per_sample = []
    scores = []

    for idx, (pred, ref, score) in enumerate(
        zip(predictions, references, cosine_scores_list)
    ):
        # Empty prediction against non-empty reference defaults to 0.0
        if not pred.strip() and ref.strip():
            score_val = 0.0
        else:
            score_val = round(float(score), 4)

        scores.append(score_val)
        per_sample.append({
            "idx": idx,
            "prediction": pred,
            "reference": ref,
            "cosine_similarity": score_val,
        })

    mean_cosine = round(sum(scores) / len(scores), 4) if scores else 0.0

    result = {
        "mean_cosine": mean_cosine,
        "total": len(predictions),
        "per_sample": per_sample,
    }

    logger.info(
        f"SBERT Cosine Similarity — Mean: {mean_cosine:.4f} | Total: {len(predictions)}"
    )

    return result
