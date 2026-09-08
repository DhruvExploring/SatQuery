# benchmarks/captioning_benchmark.py
# ============================================================
# SatQuery AI — Captioning Benchmark
# ============================================================
# Responsibilities:
#   - Run scene captioning on VRSBench captioning split
#   - Compute BLEU-4 score against reference captions
#   - Save per-sample + aggregate results
#
# Input  : VRSBench captioning samples + EarthMind runner
# Output : BLEU-4 scores + per-sample JSON
#
# Used by:
#   - run_benchmark.py
# ============================================================

import json
import logging
import time
from pathlib import Path
from typing import Any

from tqdm import tqdm

from config import OUTPUT_CONFIG
from metrics.bleu import compute_bleu, get_low_bleu_cases
from metrics.cider import compute_cider
from metrics.meteor import compute_meteor
from metrics.rouge import compute_rouge
from metrics.sbert_cosine import compute_sbert_cosine
from models.earthmind_runner import EarthMindRunner

logger = logging.getLogger(__name__)


class CaptioningBenchmark:
    """
    Evaluates EarthMind on satellite image captioning.

    Runs on:
        - VRSBench captioning split

    For each sample:
        1. Passes image to EarthMind with captioning prompt
        2. Records generated caption + confidence
        3. Computes BLEU-4 against reference caption
        4. Saves results to JSON

    BLEU-4 is the standard metric for image captioning.
    Paper baseline: best model scores ~1.66% BLEU-4.
    Post-fine-tuning target: ~34% BLEU-4 (RS-InternVL paper).
    """

    def __init__(self, runner: EarthMindRunner) -> None:
        """
        Args:
            runner : Loaded EarthMindRunner instance.
        """
        self.runner      = runner
        self.results_dir = Path(OUTPUT_CONFIG["results_dir"])
        self.results_dir.mkdir(parents=True, exist_ok=True)

        logger.info("CaptioningBenchmark initialized.")


    def run(
        self,
        samples:      list[dict[str, Any]],
        dataset_name: str = "vrsbench_captioning",
    ) -> dict[str, Any]:
        """
        Runs captioning benchmark on a list of samples.

        Args:
            samples      : Standardized captioning samples.
                           Each must have: image, reference_caption
            dataset_name : Name tag for results file.

        Returns:
            Dict with BLEU scores and per-sample results.
        """
        if not samples:
            logger.warning(
                "CaptioningBenchmark.run() called with 0 samples."
            )
            return {}

        if not self.runner.is_loaded:
            raise RuntimeError(
                "EarthMind not loaded. Call runner.load() first."
            )

        logger.info(
            f"Running Captioning benchmark — "
            f"Dataset: {dataset_name} | "
            f"Samples: {len(samples)}"
        )

        predictions = []
        references  = []
        confidences = []
        raw_outputs = []

        start_time = time.time()

        for sample in tqdm(
            samples, desc=f"Captioning [{dataset_name}]"
        ):
            sample_id = sample.get("sample_id", "unknown")

            try:
                caption, confidence = self.runner.infer_captioning(
                    image=sample["image"],
                )

                predictions.append(caption)
                references.append(sample["reference_caption"])
                confidences.append(confidence)

                raw_outputs.append({
                    "sample_id":         sample_id,
                    "reference_caption": sample["reference_caption"],
                    "predicted_caption": caption,
                    "confidence":        confidence,
                    "source":            sample.get("source", "unknown"),
                })

            except Exception as e:
                logger.error(
                    f"Captioning inference failed — "
                    f"sample_id={sample_id}: {e}"
                )
                predictions.append("")
                references.append(sample["reference_caption"])
                confidences.append(0.0)

                raw_outputs.append({
                    "sample_id":         sample_id,
                    "reference_caption": sample["reference_caption"],
                    "predicted_caption": "",
                    "confidence":        0.0,
                    "error":             str(e),
                    "source":            sample.get("source", "unknown"),
                })

        elapsed = time.time() - start_time

        # Compute BLEU scores
        bleu_result = compute_bleu(
            predictions=predictions,
            references=references,
        )

        # Compute ROUGE-L
        rouge_result = compute_rouge(
            predictions=predictions,
            references=references,
        )

        # Compute METEOR (exact match, stemming, WordNet synonyms)
        meteor_result = compute_meteor(
            predictions=predictions,
            references=references,
        )

        # Compute CIDEr (TF-IDF weighted n-gram consensus)
        cider_result = compute_cider(
            predictions=predictions,
            references=references,
        )

        # Compute SBERT Cosine Semantic Similarity
        sbert_result = compute_sbert_cosine(
            predictions=predictions,
            references=references,
        )

        # Get low-scoring cases
        low_bleu = get_low_bleu_cases(
            bleu_result["per_sample"],
            threshold=0.1,
        )

        result = {
            "task":           "captioning",
            "dataset":        dataset_name,
            "model":          "EarthMind-4B",
            "version":        "baseline",
            "total_samples":  len(samples),
            "elapsed_sec":    round(elapsed, 2),
            "sec_per_sample": round(elapsed / len(samples), 3),
            "bleu4_corpus":   bleu_result["bleu4_corpus"],
            "bleu4_mean":     bleu_result["bleu4_mean"],
            "rougeL_mean":    rouge_result["rougeL_mean"],
            "meteor_mean":    meteor_result["meteor_mean"],
            "cider_mean":     cider_result["cider_mean"],
            "sbert_cosine":   sbert_result["mean_cosine"],
            "mean_confidence": round(
                sum(confidences) / len(confidences), 4
            ),
            "low_bleu_count": len(low_bleu),
            "per_sample":     raw_outputs,
            "low_bleu_cases": low_bleu,
        }

        self._save(result, dataset_name)

        logger.info(
            f"✅ Captioning [{dataset_name}] complete — "
            f"BLEU-4 Corpus: {result['bleu4_corpus']:.4f} | "
            f"ROUGE-L: {result['rougeL_mean']:.4f} | "
            f"METEOR: {result['meteor_mean']:.4f} | "
            f"CIDEr: {result['cider_mean']:.4f} | "
            f"SBERT: {result['sbert_cosine']:.4f} | "
            f"Time: {elapsed:.1f}s"
        )

        return result


    def _save(
        self,
        result:       dict[str, Any],
        dataset_name: str,
    ) -> None:
        """
        Saves captioning result to JSON.
        File: reports/results/captioning_{dataset_name}.json
        """
        output_path = (
            self.results_dir / f"captioning_{dataset_name}.json"
        )

        serializable = {
            k: v for k, v in result.items()
            if k not in ("per_sample", "low_bleu_cases")
        }
        serializable["per_sample"] = [
            {k2: v2 for k2, v2 in s.items() if k2 != "image"}
            for s in result.get("per_sample", [])
        ]

        with open(output_path, "w") as f:
            json.dump(serializable, f, indent=2)

        logger.info(f"Results saved → {output_path}")