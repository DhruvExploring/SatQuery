# benchmarks/grounding_benchmark.py
# ============================================================
# SatQuery AI — Grounding Benchmark
# ============================================================
# Responsibilities:
#   - Run text-guided region grounding on VRSBench
#   - Parse bounding box from EarthMind text output
#   - Compute mIoU and Acc@50 / Acc@25
#   - Save per-sample + aggregate results
#
# Input  : VRSBench grounding samples + EarthMind runner
# Output : mIoU scores + per-sample JSON
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
from metrics.miou import (
    compute_miou,
    get_grounding_failures,
)
from models.earthmind_runner import EarthMindRunner

logger = logging.getLogger(__name__)


class GroundingBenchmark:
    """
    Evaluates EarthMind on text-guided region grounding.

    Runs on:
        - VRSBench grounding split

    For each sample:
        1. Passes image + region description to EarthMind
        2. Parses predicted bounding box from text output
        3. Computes IoU with ground truth bbox
        4. Reports mIoU and Accuracy@50

    Paper baseline reference:
        GPT-5.2  : 25.16% mIoU
        EarthMind: 22.65% mIoU (multi-sensor)
    """

    def __init__(self, runner: EarthMindRunner) -> None:
        """
        Args:
            runner : Loaded EarthMindRunner instance.
        """
        self.runner      = runner
        self.results_dir = Path(OUTPUT_CONFIG["results_dir"])
        self.results_dir.mkdir(parents=True, exist_ok=True)

        logger.info("GroundingBenchmark initialized.")


    def run(
        self,
        samples:      list[dict[str, Any]],
        dataset_name: str = "vrsbench_grounding",
    ) -> dict[str, Any]:
        """
        Runs grounding benchmark on a list of samples.

        Args:
            samples      : Standardized grounding samples.
                           Each must have:
                               image, region_description, bbox
            dataset_name : Name tag for results file.

        Returns:
            Dict with mIoU scores and per-sample results.
        """
        if not samples:
            logger.warning(
                "GroundingBenchmark.run() called with 0 samples."
            )
            return {}

        if not self.runner.is_loaded:
            raise RuntimeError(
                "EarthMind not loaded. Call runner.load() first."
            )

        logger.info(
            f"Running Grounding benchmark — "
            f"Dataset: {dataset_name} | "
            f"Samples: {len(samples)}"
        )

        raw_predictions = []
        ground_truths   = []
        confidences     = []
        raw_outputs     = []

        start_time = time.time()

        for sample in tqdm(
            samples, desc=f"Grounding [{dataset_name}]"
        ):
            sample_id   = sample.get("sample_id", "unknown")
            region_desc = sample["region_description"]
            gt_bbox     = sample["bbox"]

            try:
                pred_text, confidence = self.runner.infer_grounding(
                    image=sample["image"],
                    region_description=region_desc,
                )

                raw_predictions.append(pred_text)
                ground_truths.append(gt_bbox)
                confidences.append(confidence)

                raw_outputs.append({
                    "sample_id":         sample_id,
                    "region_description": region_desc,
                    "gt_bbox":           gt_bbox,
                    "prediction_raw":    pred_text,
                    "confidence":        confidence,
                    "source":            sample.get("source", "unknown"),
                })

            except Exception as e:
                logger.error(
                    f"Grounding inference failed — "
                    f"sample_id={sample_id}: {e}"
                )
                raw_predictions.append("")
                ground_truths.append(gt_bbox)
                confidences.append(0.0)

                raw_outputs.append({
                    "sample_id":          sample_id,
                    "region_description": region_desc,
                    "gt_bbox":            gt_bbox,
                    "prediction_raw":     "",
                    "confidence":         0.0,
                    "error":              str(e),
                    "source":             sample.get("source", "unknown"),
                })

        elapsed = time.time() - start_time

        # Compute mIoU
        miou_result = compute_miou(
            predictions=raw_predictions,
            ground_truths=ground_truths,
        )

        # Get failure breakdown
        failure_breakdown = get_grounding_failures(
            miou_result["per_sample"],
            iou_threshold=0.5,
        )

        result = {
            "task":            "grounding",
            "dataset":         dataset_name,
            "model":           "EarthMind-4B",
            "version":         "baseline",
            "total_samples":   len(samples),
            "elapsed_sec":     round(elapsed, 2),
            "sec_per_sample":  round(elapsed / len(samples), 3),
            "miou":            miou_result["miou"],
            "accuracy_50":     miou_result["accuracy_50"],
            "accuracy_25":     miou_result["accuracy_25"],
            "parse_success":   miou_result["parse_success"],
            "mean_confidence": round(
                sum(confidences) / len(confidences), 4
            ),
            "parse_failure_count": len(
                failure_breakdown["parse_failures"]
            ),
            "low_iou_count": len(
                failure_breakdown["low_iou_cases"]
            ),
            "per_sample":      raw_outputs,
            "failure_breakdown": {
                "parse_failures": failure_breakdown["parse_failures"],
                "low_iou_cases":  failure_breakdown["low_iou_cases"],
            },
        }

        self._save(result, dataset_name)

        logger.info(
            f"✅ Grounding [{dataset_name}] complete — "
            f"mIoU: {result['miou']:.4f} | "
            f"Acc@50: {result['accuracy_50']*100:.1f}% | "
            f"Parse: {result['parse_success']*100:.1f}% | "
            f"Time: {elapsed:.1f}s"
        )

        return result


    def _save(
        self,
        result:       dict[str, Any],
        dataset_name: str,
    ) -> None:
        """
        Saves grounding result to JSON.
        File: reports/results/grounding_{dataset_name}.json
        """
        output_path = (
            self.results_dir / f"grounding_{dataset_name}.json"
        )

        serializable = {
            k: v for k, v in result.items()
            if k not in ("per_sample", "failure_breakdown")
        }
        serializable["per_sample"] = [
            {k2: v2 for k2, v2 in s.items() if k2 != "image"}
            for s in result.get("per_sample", [])
        ]

        with open(output_path, "w") as f:
            json.dump(serializable, f, indent=2)

        logger.info(f"Results saved → {output_path}")