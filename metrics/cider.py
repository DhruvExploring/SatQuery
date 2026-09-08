# metrics/cider.py
# ============================================================
# SatQuery AI — CIDEr Metric (Pure Python Implementation)
# ============================================================
# Responsibilities:
#   - Compute CIDEr (Consensus-based Image Description Evaluation) score
#   - Implement TF-IDF weighted n-gram consensus from scratch (1 to 4-grams)
#   - Rare/domain-specific satellite terms receive higher weights than generic words
#   - Pure Python implementation without external pycocoevalcap dependency
#
# Reference:
#   Vedantam et al., "CIDEr: Consensus-based Image Description Evaluation", CVPR 2015
#
# Used by:
#   - benchmarks/captioning_benchmark.py
# ============================================================

import collections
import logging
import math
import re
from typing import Any, Dict, List, Tuple, Union

logger = logging.getLogger(__name__)


def clean_tokenize(text: str) -> List[str]:
    """
    Cleans and tokenizes text into lowercase alphanumeric words.

    Args:
        text: Input string.

    Returns:
        List of cleaned token strings.
    """
    if not text or not isinstance(text, str):
        return []
    return re.findall(r"\b\w+\b", text.lower())


def get_ngrams(words: List[str], n: int) -> collections.Counter:
    """
    Extracts n-grams of order n from a list of words.

    Args:
        words: Tokenized sentence.
        n: N-gram length (1 to 4).

    Returns:
        Counter mapping tuple of tokens -> frequency count.
    """
    if len(words) < n:
        return collections.Counter()
    return collections.Counter(tuple(words[i : i + n]) for i in range(len(words) - n + 1))


class CIDErScorer:
    """
    Computes CIDEr scores for a corpus of candidate captions and references.
    Calculates TF-IDF consensus across 1-gram, 2-gram, 3-gram, and 4-gram levels.
    """

    def __init__(self, n: int = 4, sigma: float = 6.0) -> None:
        self.n = n
        self.sigma = sigma
        self.doc_freq: List[Dict[Tuple[str, ...], int]] = [
            collections.defaultdict(int) for _ in range(n)
        ]
        self.total_docs = 0

    def compute_doc_freq(self, references: List[Union[str, List[str]]]) -> None:
        """
        Computes document frequency of all n-grams across reference captions.

        Args:
            references: List of reference caption strings (or lists of references per image).
        """
        self.total_docs = len(references)
        self.doc_freq = [collections.defaultdict(int) for _ in range(self.n)]

        for ref_item in references:
            ref_list = [ref_item] if isinstance(ref_item, str) else ref_item
            for k in range(1, self.n + 1):
                seen_ngrams = set()
                for ref_str in ref_list:
                    tokens = clean_tokenize(ref_str)
                    seen_ngrams.update(get_ngrams(tokens, k).keys())
                for ngram in seen_ngrams:
                    self.doc_freq[k - 1][ngram] += 1

    def _compute_vector(
        self,
        text: str,
        n_order: int,
    ) -> Tuple[Dict[Tuple[str, ...], float], float]:
        """
        Computes TF-IDF vector and its L2 norm for a single text at n-gram order `n_order`.

        Returns:
            Tuple of (tfidf_dict, l2_norm).
        """
        tokens = clean_tokenize(text)
        ngram_counts = get_ngrams(tokens, n_order)
        total_ngrams = sum(ngram_counts.values())

        if total_ngrams == 0:
            return {}, 0.0

        tfidf_vec = {}
        sum_sq = 0.0

        for ngram, count in ngram_counts.items():
            tf = count / total_ngrams
            df = self.doc_freq[n_order - 1].get(ngram, 0)
            # Standard consensus IDF: log( (N + 1) / (df + 1) )
            idf = math.log((self.total_docs + 1.0) / (df + 1.0))
            val = tf * idf
            tfidf_vec[ngram] = val
            sum_sq += val * val

        l2_norm = math.sqrt(sum_sq)
        return tfidf_vec, l2_norm

    def score_single(
        self,
        prediction: str,
        reference: Union[str, List[str]],
    ) -> float:
        """
        Computes CIDEr score for a single candidate prediction against its reference(s).

        Args:
            prediction: Model predicted caption string.
            reference: Ground truth reference string or list of references.

        Returns:
            CIDEr score (scaled by 10 as in the official CIDEr metric).
        """
        if not prediction.strip():
            return 0.0

        ref_list = [reference] if isinstance(reference, str) else reference
        if not ref_list or not any(r.strip() for r in ref_list):
            return 0.0

        pred_tokens = clean_tokenize(prediction)
        pred_len = len(pred_tokens)

        # Average reference length for length penalty
        ref_lens = [len(clean_tokenize(r)) for r in ref_list]
        avg_ref_len = sum(ref_lens) / len(ref_lens) if ref_lens else 0.0

        if avg_ref_len == 0.0 or pred_len == 0:
            return 0.0

        # Gaussian length penalty
        delta = pred_len - avg_ref_len
        length_penalty = math.exp(- (delta * delta) / (2.0 * self.sigma * self.sigma))

        ngram_scores = []
        for k in range(1, self.n + 1):
            pred_vec, pred_norm = self._compute_vector(prediction, k)
            if pred_norm == 0.0:
                ngram_scores.append(0.0)
                continue

            ref_scores = []
            for ref_str in ref_list:
                ref_vec, ref_norm = self._compute_vector(ref_str, k)
                if ref_norm == 0.0:
                    ref_scores.append(0.0)
                    continue

                # Dot product
                common_keys = set(pred_vec.keys()) & set(ref_vec.keys())
                dot_prod = sum(pred_vec[key] * ref_vec[key] for key in common_keys)
                sim = dot_prod / (pred_norm * ref_norm + 1e-10)
                ref_scores.append(sim)

            avg_ref_score = sum(ref_scores) / len(ref_scores) if ref_scores else 0.0
            ngram_scores.append(avg_ref_score)

        cider_val = (sum(ngram_scores) / self.n) * length_penalty * 10.0
        return round(float(cider_val), 4)


def compute_cider(
    predictions: list[str],
    references: list[Union[str, List[str]]],
    n: int = 4,
    sigma: float = 6.0,
) -> dict[str, Any]:
    """
    Computes CIDEr score across a dataset of captioning predictions.

    Args:
        predictions : List of candidate caption strings.
        references  : List of reference caption strings (or lists of references).
        n           : Maximum n-gram order (default: 4).
        sigma       : Standard deviation for Gaussian length penalty (default: 6.0).

    Returns:
        Dict with:
            cider_mean (float) : Mean CIDEr score across the dataset.
            total      (int)   : Total samples evaluated.
            per_sample (list)  : Per-sample detailed evaluation scores.

    Raises:
        ValueError: If predictions and references differ in length.
    """
    if len(predictions) != len(references):
        raise ValueError(
            f"Length mismatch: {len(predictions)} predictions vs {len(references)} references."
        )

    if not predictions:
        return {
            "cider_mean": 0.0,
            "total": 0,
            "per_sample": [],
        }

    scorer = CIDErScorer(n=n, sigma=sigma)
    scorer.compute_doc_freq(references)

    per_sample = []
    scores = []

    for idx, (pred, ref) in enumerate(zip(predictions, references)):
        score = scorer.score_single(pred, ref)
        scores.append(score)

        ref_display = ref if isinstance(ref, str) else (ref[0] if ref else "")
        per_sample.append({
            "idx": idx,
            "prediction": pred,
            "reference": ref_display,
            "cider": score,
        })

    cider_mean = round(sum(scores) / len(scores), 4) if scores else 0.0

    result = {
        "cider_mean": cider_mean,
        "total": len(predictions),
        "per_sample": per_sample,
    }

    logger.info(
        f"CIDEr — Mean: {cider_mean:.4f} | Total: {len(predictions)}"
    )

    return result
