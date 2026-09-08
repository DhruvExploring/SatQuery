# benchmarks/change_vqa_benchmark.py
# ============================================================
# SatQuery AI — Change VQA Benchmark
# ============================================================
# Responsibilities:
#   - Run change-based VQA on CDVQA dataset
#   - Feed bi-temporal image pairs to EarthMind
#   - Compute accuracy on change-related questions
#   - Identify common failure patterns
#
# Input  : CDVQA samples + EarthMind runner
# Output : Accuracy scores + per-sample JSON
#
# Used by:
#   - run_benchmark.py
# ============================================================

import json
import logging
import time
from collections import defaultdict
from pathlib import Path
from typing import Any

from tqdm import tqdm

from config import OUTPUT_CONFIG
from metrics.accuracy import compute_accuracy, get_failure_cases
from models.earthmind_runner import EarthMindRunner

logger = logging.getLogger(__name__)


class ChangeVQABenchmark:
    """
    Evaluates EarthMind on bi-temporal change VQA.

    Runs on:
        - CDVQA dataset

    For each sample:
        1. Passes BEFORE + AFTER images to EarthMind
        2. EarthMind reasons about what changed
        3. Records answer + confidence
        4. Computes accuracy against ground truth

    This is a MANDATORY task per the SIH PS:
    "Change description or change-based visual question
     answering from a bi-temporal image pair shall be
     mandatory."

    Results are broken down by change_type to identify
    which types of change EarthMind handles well or poorly.
    This directly informs Raja's fine-tuning focus areas.
    """

    def __init__(self, runner: EarthMindRunner) -> None:
        """
        Args:
            runner : Loaded EarthMindRunner instance.
        """
        self.runner      = runner
        self.results_dir = Path(OUTPUT_CONFIG["results_dir"])
        self.results_dir.mkdir(parents=True, exist_ok=True)

        logger.info("ChangeVQABenchmark initialized.")


    def run(
        self,
        samples:      list[dict[str, Any]],
        dataset_name: str = "cdvqa",
    ) -> dict[str, Any]:
        """
        Runs change VQA benchmark on bi-temporal image pairs.

        Args:
            samples      : Standardized CDVQA samples.
                           Each must have:
                               image_before, image_after,
                               question, answer
            dataset_name : Name tag for results file.

        Returns:
            Dict with accuracy scores, per-change-type
            breakdown, and failure patterns.
        """
        if not samples:
            logger.warning(
                "ChangeVQABenchmark.run() called with 0 samples."
            )
            return {}

        if not self.runner.is_loaded:
            raise RuntimeError(
                "EarthMind not loaded. Call runner.load() first."
            )

        logger.info(
            f"Running Change-VQA benchmark — "
            f"Dataset: {dataset_name} | "
            f"Samples: {len(samples)}"
        )

        predictions   = []
        ground_truths = []
        confidences   = []
        raw_outputs   = []

        # Track per-change-type results for failure analysis
        type_predictions:   dict[str, list[str]] = defaultdict(list)
        type_ground_truths: dict[str, list[str]] = defaultdict(list)

        start_time = time.time()

        for sample in tqdm(
            samples, desc=f"ChangeVQA [{dataset_name}]"
        ):
            sample_id   = sample.get("sample_id", "unknown")
            change_type = sample.get("change_type", "unknown")

            try:
                answer, confidence = self.runner.infer_change_vqa(
                    image_before=sample["image_before"],
                    image_after=sample["image_after"],
                    question=sample["question"],
                )

                predictions.append(answer)
                ground_truths.append(sample["answer"])
                confidences.append(confidence)

                type_predictions[change_type].append(answer)
                type_ground_truths[change_type].append(
                    sample["answer"]
                )

                raw_outputs.append({
                    "sample_id":    sample_id,
                    "question":     sample["question"],
                    "ground_truth": sample["answer"],
                    "prediction":   answer,
                    "confidence":   confidence,
                    "change_type":  change_type,
                    "source":       sample.get("source", "cdvqa"),
                })

            except Exception as e:
                logger.error(
                    f"ChangeVQA inference failed — "
                    f"sample_id={sample_id}: {e}"
                )
                predictions.append("")
                ground_truths.append(sample["answer"])
                confidences.append(0.0)

                type_predictions[change_type].append("")
                type_ground_truths[change_type].append(
                    sample["answer"]
                )

                raw_outputs.append({
                    "sample_id":    sample_id,
                    "question":     sample["question"],
                    "ground_truth": sample["answer"],
                    "prediction":   "",
                    "confidence":   0.0,
                    "change_type":  change_type,
                    "error":        str(e),
                    "source":       sample.get("source", "cdvqa"),
                })

        elapsed = time.time() - start_time

        # Overall accuracy
        accuracy_result = compute_accuracy(
            predictions=predictions,
            ground_truths=ground_truths,
            use_soft=True,
            is_binary=False,
        )

        # Per-change-type accuracy breakdown
        type_breakdown = self._compute_type_breakdown(
            type_predictions,
            type_ground_truths,
        )

        # Failure cases
        failures = get_failure_cases(
            accuracy_result["per_sample"],
            threshold=0.5,
        )

        result = {
            "task":            "change_vqa",
            "dataset":         dataset_name,
            "model":           "EarthMind-4B",
            "version":         "baseline",
            "total_samples":   len(samples),
            "elapsed_sec":     round(elapsed, 2),
            "sec_per_sample":  round(elapsed / len(samples), 3),
            "exact_accuracy":  accuracy_result["exact_accuracy"],
            "soft_accuracy":   accuracy_result["soft_accuracy"],
            "mean_confidence": round(
                sum(confidences) / len(confidences), 4
            ),
            "failure_count":   len(failures),
            "type_breakdown":  type_breakdown,
            "per_sample":      raw_outputs,
            "failures":        failures,
        }

        self._save(result, dataset_name)

        logger.info(
            f"✅ ChangeVQA [{dataset_name}] complete — "
            f"Exact: {result['exact_accuracy']*100:.1f}% | "
            f"Soft: {result['soft_accuracy']*100:.1f}% | "
            f"Time: {elapsed:.1f}s"
        )

        # Log type breakdown for Raja's reference
        self._log_type_breakdown(type_breakdown)

        return result


    def _compute_type_breakdown(
        self,
        type_predictions:   dict[str, list[str]],
        type_ground_truths: dict[str, list[str]],
    ) -> dict[str, dict[str, Any]]:
        """
        Computes accuracy per change type.

        This breakdown is critical for Raja's fine-tuning:
        Types with low accuracy need more training data focus.

        Args:
            type_predictions   : Predictions grouped by change type.
            type_ground_truths : GT answers grouped by change type.

        Returns:
            Dict mapping change_type → accuracy metrics.
        """
        breakdown = {}

        for change_type in type_predictions:
            preds = type_predictions[change_type]
            gts   = type_ground_truths[change_type]

            if not preds:
                continue

            acc = compute_accuracy(
                predictions=preds,
                ground_truths=gts,
                use_soft=True,
            )

            breakdown[change_type] = {
                "count":          len(preds),
                "exact_accuracy": acc["exact_accuracy"],
                "soft_accuracy":  acc["soft_accuracy"],
            }

        return breakdown


    def _log_type_breakdown(
        self,
        type_breakdown: dict[str, dict[str, Any]],
    ) -> None:
        """
        Logs per-type accuracy for Raja's reference.
        Highlights change types where model is weakest.
        """
        if not type_breakdown:
            return

        logger.info("Change-type accuracy breakdown (for Raja):")
        logger.info(f"  {'Type':<25} {'Count':>6} {'Exact':>8} {'Soft':>8}")
        logger.info(f"  {'-'*50}")

        # Sort by soft accuracy ascending (weakest first)
        sorted_types = sorted(
            type_breakdown.items(),
            key=lambda x: x[1]["soft_accuracy"],
        )

        for change_type, metrics in sorted_types:
            logger.info(
                f"  {change_type:<25} "
                f"{metrics['count']:>6} "
                f"{metrics['exact_accuracy']*100:>7.1f}% "
                f"{metrics['soft_accuracy']*100:>7.1f}%"
            )


    def _save(
        self,
        result:       dict[str, Any],
        dataset_name: str,
    ) -> None:
        """
        Saves change-VQA result to JSON.
        File: reports/results/change_vqa_{dataset_name}.json
        """
        output_path = (
            self.results_dir / f"change_vqa_{dataset_name}.json"
        )

        serializable = {
            k: v for k, v in result.items()
            if k not in ("per_sample", "failures")
        }
        serializable["per_sample"] = [
            {
                k2: v2 for k2, v2 in s.items()
                if k2 not in ("image_before", "image_after")
            }
            for s in result.get("per_sample", [])
        ]

        with open(output_path, "w") as f:
            json.dump(serializable, f, indent=2)

        logger.info(f"Results saved → {output_path}")