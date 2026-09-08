# benchmarks/vqa_benchmark.py
# ============================================================
# SatQuery AI — VQA Benchmark
# ============================================================
# Responsibilities:
#   - Run VQA evaluation on VRSBench and RSVQA datasets
#   - Feed each sample through EarthMind runner
#   - Compute accuracy metrics per dataset
#   - Save results to reports/results/
#
# Input  : Loaded dataset samples + EarthMind runner
# Output : Accuracy scores + per-sample JSON
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
from metrics.accuracy import compute_accuracy, get_failure_cases
from metrics.numeric_match import compute_numeric_match
from metrics.sbert_cosine import compute_sbert_cosine
from models.earthmind_runner import EarthMindRunner

logger = logging.getLogger(__name__)


class VQABenchmark:
    """
    Evaluates EarthMind on Visual Question Answering.

    Runs on:
        - VRSBench VQA split
        - RSVQA-LR (all question types)

    For each sample:
        1. Passes image + question to EarthMind
        2. Records predicted answer + confidence
        3. Computes exact and soft match accuracy
        4. Saves results to JSON

    Raja uses the same output schema for fine-tuned
    model evaluation — enabling direct comparison.
    """

    def __init__(self, runner: EarthMindRunner) -> None:
        """
        Args:
            runner : Loaded EarthMindRunner instance.
                     Must be loaded before calling run().
        """
        self.runner     = runner
        self.results_dir = Path(OUTPUT_CONFIG["results_dir"])
        self.results_dir.mkdir(parents=True, exist_ok=True)

        logger.info("VQABenchmark initialized.")


    def run(
        self,
        samples:     list[dict[str, Any]],
        dataset_name: str,
        is_binary:   bool = False,
    ) -> dict[str, Any]:
        """
        Runs VQA benchmark on a list of samples.

        Args:
            samples      : Standardized samples from a loader.
                           Each must have: image, question, answer
            dataset_name : Name tag for results file.
                           e.g. "vrsbench_vqa", "rsvqa_vqa"
            is_binary    : Set True for yes/no question types
                           (presence questions in RSVQA).

        Returns:
            Dict with accuracy scores and per-sample results.
        """
        if not samples:
            logger.warning(
                f"VQABenchmark.run() called with 0 samples "
                f"for {dataset_name}."
            )
            return {}

        if not self.runner.is_loaded:
            raise RuntimeError(
                "EarthMind not loaded. Call runner.load() first."
            )

        logger.info(
            f"Running VQA benchmark — "
            f"Dataset: {dataset_name} | "
            f"Samples: {len(samples)} | "
            f"Binary: {is_binary}"
        )

        predictions   = []
        ground_truths = []
        confidences   = []
        raw_outputs   = []

        start_time = time.time()

        for sample in tqdm(samples, desc=f"VQA [{dataset_name}]"):
            sample_id = sample.get("sample_id", "unknown")

            try:
                answer, confidence = self.runner.infer_vqa(
                    image=sample["image"],
                    question=sample["question"],
                )

                predictions.append(answer)
                ground_truths.append(sample["answer"])
                confidences.append(confidence)

                raw_outputs.append({
                    "sample_id":   sample_id,
                    "question":    sample["question"],
                    "ground_truth": sample["answer"],
                    "prediction":  answer,
                    "confidence":  confidence,
                    "source":      sample.get("source", "unknown"),
                    "q_type":      sample.get("question_type", "unknown"),
                })

            except Exception as e:
                logger.error(
                    f"VQA inference failed — "
                    f"sample_id={sample_id}: {e}"
                )
                # Record failure with empty prediction
                predictions.append("")
                ground_truths.append(sample["answer"])
                confidences.append(0.0)

                raw_outputs.append({
                    "sample_id":    sample_id,
                    "question":     sample["question"],
                    "ground_truth": sample["answer"],
                    "prediction":   "",
                    "confidence":   0.0,
                    "error":        str(e),
                    "source":       sample.get("source", "unknown"),
                })

        elapsed = time.time() - start_time

        # Compute accuracy
        accuracy_result = compute_accuracy(
            predictions=predictions,
            ground_truths=ground_truths,
            use_soft=True,
            is_binary=is_binary,
        )

        # Compute SBERT Cosine Semantic Similarity
        sbert_result = compute_sbert_cosine(
            predictions=predictions,
            references=ground_truths,
        )

        # Compute RSVQA Numeric Match if evaluating RSVQA
        numeric_result = None
        if "rsvqa" in dataset_name.lower():
            numeric_result = compute_numeric_match(
                predictions=predictions,
                references=ground_truths,
            )

        # Get failure cases
        failures = get_failure_cases(
            accuracy_result["per_sample"],
            threshold=0.5,
        )

        # Build final result
        result = {
            "task":           "vqa",
            "dataset":        dataset_name,
            "model":          "EarthMind-4B",
            "version":        "baseline",
            "total_samples":  len(samples),
            "elapsed_sec":    round(elapsed, 2),
            "sec_per_sample": round(elapsed / len(samples), 3),
            "exact_accuracy": accuracy_result["exact_accuracy"],
            "soft_accuracy":  accuracy_result["soft_accuracy"],
            "sbert_cosine":   sbert_result["mean_cosine"],
            "mean_confidence": round(
                sum(confidences) / len(confidences), 4
            ),
            "failure_count":  len(failures),
            "per_sample":     raw_outputs,
            "failures":       failures,
        }

        if numeric_result is not None:
            result["numeric_accuracy"] = numeric_result["numeric_accuracy"]

        # Save to JSON
        self._save(result, dataset_name)

        log_msg = (
            f"✅ VQA [{dataset_name}] complete — "
            f"Exact: {result['exact_accuracy']*100:.1f}% | "
            f"Soft: {result['soft_accuracy']*100:.1f}% | "
            f"SBERT: {result['sbert_cosine']:.4f} | "
        )
        if "numeric_accuracy" in result:
            log_msg += f"Numeric Acc: {result['numeric_accuracy']*100:.1f}% | "
        log_msg += f"Time: {elapsed:.1f}s"

        logger.info(log_msg)

        return result


    def _save(
        self,
        result: dict[str, Any],
        dataset_name: str,
    ) -> None:
        """
        Saves benchmark result to a JSON file.
        File: reports/results/vqa_{dataset_name}.json

        Args:
            result       : Full result dict from run().
            dataset_name : Used in filename.
        """
        output_path = (
            self.results_dir / f"vqa_{dataset_name}.json"
        )

        # PIL Images are not JSON serializable — remove them
        serializable = {
            k: v for k, v in result.items()
            if k != "per_sample"
        }
        serializable["per_sample"] = [
            {k2: v2 for k2, v2 in s.items() if k2 != "image"}
            for s in result.get("per_sample", [])
        ]

        with open(output_path, "w") as f:
            json.dump(serializable, f, indent=2)

        logger.info(f"Results saved → {output_path}")