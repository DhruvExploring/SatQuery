# reports/report_generator.py
# ============================================================
# SatQuery AI — Baseline Report Generator
# ============================================================
# Responsibilities:
#   - Collect all benchmark results from results/ folder
#   - Generate structured Excel report
#   - Generate JSON summary in RESULT_SCHEMA format
#   - Identify failure patterns across all tasks
#   - Produce Go/No-Go recommendation for team
#
# Input  : JSON files from reports/results/
# Output : Excel report + final JSON summary
#
# Used by:
#   - run_benchmark.py (called after all benchmarks finish)
#   - Raja uses output JSON schema for fine-tuned comparison
# ============================================================

import json
import logging
import os
from datetime import datetime
from pathlib import Path
from typing import Any, Optional

import pandas as pd

from config import OUTPUT_CONFIG, RESULT_SCHEMA, MODEL_CONFIG

logger = logging.getLogger(__name__)


class ReportGenerator:
    """
    Generates the final baseline report after all benchmarks run.

    Produces:
        1. reports/results/baseline_report.json
           — Structured summary in RESULT_SCHEMA format
           — Raja uses same schema for fine-tuned model
           — Enables direct before/after comparison

        2. reports/results/baseline_report.xlsx
           — Human-readable Excel with per-task sheets
           — Shared with full team for decision making

    Go/No-Go Logic:
        GO      : EarthMind soft accuracy >= 60% on VQA
        PARTIAL : 40% <= accuracy < 60%
        NO-GO   : accuracy < 40% (need alternative model)
    """

    GO_THRESHOLD      = 0.60
    PARTIAL_THRESHOLD = 0.40

    def __init__(self) -> None:
        self.results_dir = Path(OUTPUT_CONFIG["results_dir"])
        self.report_name = OUTPUT_CONFIG["report_name"]
        self.results_dir.mkdir(parents=True, exist_ok=True)

        logger.info("ReportGenerator initialized.")
        logger.info(f"  Results dir : {self.results_dir}")
        logger.info(f"  Report name : {self.report_name}")


    # ── Load Results ──────────────────────────────────────────
    def _load_json(self, filename: str) -> Optional[dict]:
        """
        Loads a benchmark result JSON file.

        Args:
            filename : JSON filename inside results_dir.

        Returns:
            Parsed dict or None if file not found.
        """
        path = self.results_dir / filename

        if not path.exists():
            logger.warning(f"Result file not found: {path}")
            return None

        with open(path) as f:
            return json.load(f)


    def _collect_results(self) -> dict[str, Any]:
        """
        Loads all benchmark result JSON files.

        Returns:
            Dict mapping task name → result dict.
        """
        result_files = {
            "vrsbench_vqa":        "vqa_vrsbench_vqa.json",
            "rsvqa_vqa":           "vqa_rsvqa_vqa.json",
            "vrsbench_captioning": "captioning_vrsbench_captioning.json",
            "vrsbench_grounding":  "grounding_vrsbench_grounding.json",
            "cdvqa_change_vqa":    "change_vqa_cdvqa.json",
        }

        collected = {}
        for task_name, filename in result_files.items():
            data = self._load_json(filename)
            if data:
                collected[task_name] = data
                logger.info(f"✅ Loaded: {filename}")
            else:
                logger.warning(f"⚠️  Missing: {filename}")

        return collected


    # ── Go/No-Go ──────────────────────────────────────────────
    def _determine_recommendation(
        self,
        results: dict[str, Any],
    ) -> str:
        """
        Determines Go/No-Go recommendation based on VQA accuracy.

        Logic:
            Primary metric : VRSBench VQA soft accuracy
            Fallback        : RSVQA VQA soft accuracy

            >= 60% → GO      (EarthMind is strong enough)
            >= 40% → PARTIAL (Fine-tuning needed)
            <  40% → NO-GO   (Consider alternative model)

        Args:
            results : Collected benchmark results dict.

        Returns:
            "GO", "PARTIAL", or "NO-GO"
        """
        # Try VRSBench VQA first
        vqa_acc = None

        if "vrsbench_vqa" in results:
            vqa_acc = results["vrsbench_vqa"].get("soft_accuracy")

        if vqa_acc is None and "rsvqa_vqa" in results:
            vqa_acc = results["rsvqa_vqa"].get("soft_accuracy")

        if vqa_acc is None:
            logger.warning(
                "No VQA results found — defaulting to PARTIAL."
            )
            return "PARTIAL"

        if vqa_acc >= self.GO_THRESHOLD:
            return "GO"
        elif vqa_acc >= self.PARTIAL_THRESHOLD:
            return "PARTIAL"
        else:
            return "NO-GO"


    # ── Failure Patterns ──────────────────────────────────────
    def _extract_failure_patterns(
        self,
        results: dict[str, Any],
    ) -> list[str]:
        """
        Extracts high-level failure patterns across all tasks.
        These patterns guide Raja's fine-tuning strategy.

        Args:
            results : Collected benchmark results dict.

        Returns:
            List of failure pattern strings.
        """
        patterns = []

        # VQA failure check
        for task_key in ("vrsbench_vqa", "rsvqa_vqa"):
            if task_key not in results:
                continue
            acc = results[task_key].get("soft_accuracy", 1.0)
            if acc < 0.60:
                patterns.append(
                    f"VQA accuracy below 60% on {task_key} "
                    f"({acc*100:.1f}%) — fine-tuning recommended."
                )

        # Captioning failure check
        if "vrsbench_captioning" in results:
            bleu = results["vrsbench_captioning"].get(
                "bleu4_corpus", 1.0
            )
            if bleu < 0.05:
                patterns.append(
                    f"Captioning BLEU-4 very low ({bleu:.4f}) — "
                    f"model not adapted for satellite captions."
                )

        # Grounding failure check
        if "vrsbench_grounding" in results:
            gr = results["vrsbench_grounding"]
            parse_rate = gr.get("parse_success", 1.0)
            miou       = gr.get("miou", 1.0)

            if parse_rate < 0.70:
                patterns.append(
                    f"Grounding bbox parse rate low "
                    f"({parse_rate*100:.1f}%) — "
                    f"model not outputting structured bbox."
                )
            if miou < 0.30:
                patterns.append(
                    f"Grounding mIoU low ({miou:.4f}) — "
                    f"spatial localization needs improvement."
                )

        # Change VQA failure check
        if "cdvqa_change_vqa" in results:
            ch  = results["cdvqa_change_vqa"]
            acc = ch.get("soft_accuracy", 1.0)

            if acc < 0.50:
                patterns.append(
                    f"Change VQA accuracy low ({acc*100:.1f}%) — "
                    f"bi-temporal reasoning needs fine-tuning."
                )

            # Per-type weak areas
            type_breakdown = ch.get("type_breakdown", {})
            weak_types = [
                t for t, m in type_breakdown.items()
                if m.get("soft_accuracy", 1.0) < 0.40
            ]
            if weak_types:
                patterns.append(
                    f"Weak change types: {', '.join(weak_types)} "
                    f"— Raja should prioritize these in fine-tuning."
                )

        if not patterns:
            patterns.append(
                "No significant failure patterns detected — "
                "model performance is acceptable across all tasks."
            )

        return patterns


    # ── Build JSON Summary ────────────────────────────────────
    def _build_json_summary(
        self,
        results:         dict[str, Any],
        recommendation:  str,
        failure_patterns: list[str],
    ) -> dict[str, Any]:
        """
        Builds the final JSON summary in RESULT_SCHEMA format.
        Raja uses this same schema for his fine-tuned model,
        enabling direct before/after comparison.

        Args:
            results          : Collected benchmark results.
            recommendation   : "GO", "PARTIAL", or "NO-GO"
            failure_patterns : List of failure pattern strings.

        Returns:
            Populated RESULT_SCHEMA dict.
        """
        summary = dict(RESULT_SCHEMA)
        summary["timestamp"]      = datetime.now().isoformat()
        summary["recommendation"] = recommendation
        summary["failure_patterns"] = failure_patterns

        # VRSBench VQA
        if "vrsbench_vqa" in results:
            r = results["vrsbench_vqa"]
            summary["vrsbench"]["vqa"] = {
                "accuracy":       r.get("soft_accuracy"),
                "exact_accuracy": r.get("exact_accuracy"),
                "sbert_cosine":   r.get("sbert_cosine"),
                "samples":        r.get("total_samples"),
            }

        # RSVQA VQA
        if "rsvqa_vqa" in results:
            r = results["rsvqa_vqa"]
            summary["rsvqa"]["vqa"] = {
                "accuracy":         r.get("soft_accuracy"),
                "exact_accuracy":   r.get("exact_accuracy"),
                "numeric_accuracy": r.get("numeric_accuracy"),
                "sbert_cosine":     r.get("sbert_cosine"),
                "samples":          r.get("total_samples"),
            }

        # VRSBench Captioning
        if "vrsbench_captioning" in results:
            r = results["vrsbench_captioning"]
            summary["vrsbench"]["captioning"] = {
                "bleu4":        r.get("bleu4_corpus"),
                "bleu4_mean":   r.get("bleu4_mean"),
                "rougeL":       r.get("rougeL_mean"),
                "meteor":       r.get("meteor_mean"),
                "cider":        r.get("cider_mean"),
                "sbert_cosine": r.get("sbert_cosine"),
                "samples":      r.get("total_samples"),
            }

        # VRSBench Grounding
        if "vrsbench_grounding" in results:
            r = results["vrsbench_grounding"]
            summary["vrsbench"]["grounding"] = {
                "miou":          r.get("miou"),
                "accuracy_50":   r.get("accuracy_50"),
                "accuracy_25":   r.get("accuracy_25"),
                "parse_success": r.get("parse_success"),
                "samples":       r.get("total_samples"),
            }

        # CDVQA Change VQA
        if "cdvqa_change_vqa" in results:
            r = results["cdvqa_change_vqa"]
            summary["cdvqa"]["change_vqa"] = {
                "accuracy":       r.get("soft_accuracy"),
                "exact_accuracy": r.get("exact_accuracy"),
                "samples":        r.get("total_samples"),
                "type_breakdown": r.get("type_breakdown", {}),
            }

        return summary


    # ── Excel Report ──────────────────────────────────────────
    def _build_excel(
        self,
        results:  dict[str, Any],
        summary:  dict[str, Any],
    ) -> None:
        """
        Generates a multi-sheet Excel report.

        Sheets:
            1. Summary     — One-page overview + Go/No-Go
            2. VQA         — VRSBench + RSVQA accuracy + SBERT + Numeric Match
            3. Captioning  — BLEU-4, ROUGE-L, METEOR, CIDEr, SBERT scores
            4. Grounding   — mIoU, Acc@50, Acc@25 scores
            5. Change VQA  — CDVQA scores + type breakdown

        Args:
            results : Collected benchmark result dicts.
            summary : Final JSON summary dict.
        """
        excel_path = (
            self.results_dir / f"{self.report_name}.xlsx"
        )

        with pd.ExcelWriter(excel_path, engine="openpyxl") as writer:

            # ── Sheet 1: Summary ─────────────────────────────
            model_title = summary.get("model", MODEL_CONFIG["name"])
            version_title = summary.get("version", "baseline")

            summary_rows = [
                [f"SatQuery AI — {model_title} Benchmark Report", ""],
                ["Model",     model_title],
                ["Version",   version_title],
                ["Timestamp", summary.get("timestamp", "")],
                ["Recommendation", summary.get("recommendation", "")],
                ["", ""],
                ["Task / Metric", "Score"],
            ]

            if summary["vrsbench"].get("vqa"):
                vqa_d = summary["vrsbench"]["vqa"]
                summary_rows.append([
                    "VRSBench VQA (Soft Accuracy)",
                    f"{vqa_d['accuracy']*100:.1f}%" if vqa_d.get('accuracy') is not None else "N/A",
                ])
                if vqa_d.get("exact_accuracy") is not None:
                    summary_rows.append([
                        "VRSBench VQA (Exact Accuracy)",
                        f"{vqa_d['exact_accuracy']*100:.1f}%",
                    ])
                if vqa_d.get("sbert_cosine") is not None:
                    summary_rows.append([
                        "VRSBench VQA (SBERT Cosine)",
                        f"{vqa_d['sbert_cosine']:.4f}",
                    ])

            if summary["rsvqa"].get("vqa"):
                rsvqa_d = summary["rsvqa"]["vqa"]
                summary_rows.append([
                    "RSVQA VQA (Soft Accuracy)",
                    f"{rsvqa_d['accuracy']*100:.1f}%" if rsvqa_d.get('accuracy') is not None else "N/A",
                ])
                if rsvqa_d.get("exact_accuracy") is not None:
                    summary_rows.append([
                        "RSVQA VQA (Exact Accuracy)",
                        f"{rsvqa_d['exact_accuracy']*100:.1f}%",
                    ])
                if rsvqa_d.get("numeric_accuracy") is not None:
                    summary_rows.append([
                        "RSVQA Numeric Accuracy",
                        f"{rsvqa_d['numeric_accuracy']*100:.1f}%",
                    ])
                if rsvqa_d.get("sbert_cosine") is not None:
                    summary_rows.append([
                        "RSVQA VQA (SBERT Cosine)",
                        f"{rsvqa_d['sbert_cosine']:.4f}",
                    ])

            if summary["vrsbench"].get("captioning"):
                cap_d = summary["vrsbench"]["captioning"]
                summary_rows.append([
                    "VRSBench Captioning (BLEU-4)",
                    f"{cap_d['bleu4']:.4f}" if cap_d.get('bleu4') is not None else "N/A",
                ])
                if cap_d.get("rougeL") is not None:
                    summary_rows.append([
                        "VRSBench Captioning (ROUGE-L)",
                        f"{cap_d['rougeL']:.4f}",
                    ])
                if cap_d.get("meteor") is not None:
                    summary_rows.append([
                        "Captioning METEOR",
                        f"{cap_d['meteor']:.4f}",
                    ])
                if cap_d.get("cider") is not None:
                    summary_rows.append([
                        "Captioning CIDEr",
                        f"{cap_d['cider']:.4f}",
                    ])
                if cap_d.get("sbert_cosine") is not None:
                    summary_rows.append([
                        "Captioning SBERT Cosine",
                        f"{cap_d['sbert_cosine']:.4f}",
                    ])

            if summary["vrsbench"].get("grounding"):
                gr_d = summary["vrsbench"]["grounding"]
                summary_rows.append([
                    "VRSBench Grounding (mIoU)",
                    f"{gr_d['miou']:.4f}" if gr_d.get('miou') is not None else "N/A",
                ])
                if gr_d.get("accuracy_50") is not None:
                    summary_rows.append([
                        "VRSBench Grounding (Acc@50)",
                        f"{gr_d['accuracy_50']*100:.1f}%",
                    ])

            if summary["cdvqa"].get("change_vqa"):
                ch_d = summary["cdvqa"]["change_vqa"]
                summary_rows.append([
                    "CDVQA Change VQA (Soft Accuracy)",
                    f"{ch_d['accuracy']*100:.1f}%" if ch_d.get('accuracy') is not None else "N/A",
                ])

            summary_rows.append(["", ""])
            summary_rows.append(["Failure Patterns", ""])
            for pattern in summary.get("failure_patterns", []):
                summary_rows.append(["", pattern])

            pd.DataFrame(summary_rows).to_excel(
                writer,
                sheet_name="Summary",
                index=False,
                header=False,
            )

            # ── Sheet 2: VQA ─────────────────────────────────
            vqa_rows = []
            for task_key in ("vrsbench_vqa", "rsvqa_vqa"):
                if task_key not in results:
                    continue
                r = results[task_key]
                vqa_rows.append({
                    "Dataset":                 r.get("dataset"),
                    "Samples":                 r.get("total_samples"),
                    "Exact Accuracy":          f"{r.get('exact_accuracy', 0)*100:.1f}%",
                    "Soft Accuracy":           f"{r.get('soft_accuracy', 0)*100:.1f}%",
                    "SBERT Cosine Similarity": r.get("sbert_cosine"),
                    "RSVQA Numeric Accuracy":  f"{r.get('numeric_accuracy', 0)*100:.1f}%" if "numeric_accuracy" in r else "N/A",
                    "Mean Confidence":         r.get("mean_confidence"),
                    "Failures":                r.get("failure_count"),
                    "Time (s)":                r.get("elapsed_sec"),
                })

            if vqa_rows:
                pd.DataFrame(vqa_rows).to_excel(
                    writer, sheet_name="VQA", index=False
                )

            # ── Sheet 3: Captioning ───────────────────────────
            if "vrsbench_captioning" in results:
                r = results["vrsbench_captioning"]
                cap_rows = [{
                    "Dataset":                 r.get("dataset"),
                    "Samples":                 r.get("total_samples"),
                    "BLEU-4 Corpus":           r.get("bleu4_corpus"),
                    "BLEU-4 Mean":             r.get("bleu4_mean"),
                    "ROUGE-L Mean":            r.get("rougeL_mean"),
                    "Captioning METEOR":       r.get("meteor_mean"),
                    "Captioning CIDEr":        r.get("cider_mean"),
                    "SBERT Cosine Similarity": r.get("sbert_cosine"),
                    "Mean Confidence":         r.get("mean_confidence"),
                    "Low BLEU Count":          r.get("low_bleu_count"),
                    "Time (s)":                r.get("elapsed_sec"),
                }]
                pd.DataFrame(cap_rows).to_excel(
                    writer, sheet_name="Captioning", index=False
                )

            # ── Sheet 4: Grounding ────────────────────────────
            if "vrsbench_grounding" in results:
                r = results["vrsbench_grounding"]
                gr_rows = [{
                    "Dataset":          r.get("dataset"),
                    "Samples":          r.get("total_samples"),
                    "mIoU":             r.get("miou"),
                    "Accuracy@50":      f"{r.get('accuracy_50',0)*100:.1f}%",
                    "Accuracy@25":      f"{r.get('accuracy_25',0)*100:.1f}%",
                    "Parse Success":    f"{r.get('parse_success',0)*100:.1f}%",
                    "Parse Failures":   r.get("parse_failure_count"),
                    "Low IoU Cases":    r.get("low_iou_count"),
                    "Time (s)":         r.get("elapsed_sec"),
                }]
                pd.DataFrame(gr_rows).to_excel(
                    writer, sheet_name="Grounding", index=False
                )

            # ── Sheet 5: Change VQA ───────────────────────────
            if "cdvqa_change_vqa" in results:
                r = results["cdvqa_change_vqa"]

                ch_rows = [{
                    "Dataset":        r.get("dataset"),
                    "Samples":        r.get("total_samples"),
                    "Exact Accuracy": f"{r.get('exact_accuracy',0)*100:.1f}%",
                    "Soft Accuracy":  f"{r.get('soft_accuracy',0)*100:.1f}%",
                    "Mean Confidence": r.get("mean_confidence"),
                    "Failures":       r.get("failure_count"),
                    "Time (s)":       r.get("elapsed_sec"),
                }]
                pd.DataFrame(ch_rows).to_excel(
                    writer,
                    sheet_name="ChangeVQA",
                    index=False,
                )

                # Per-type breakdown on same sheet
                type_breakdown = r.get("type_breakdown", {})
                if type_breakdown:
                    type_rows = [
                        {
                            "Change Type":    t,
                            "Count":          m.get("count"),
                            "Exact Accuracy": f"{m.get('exact_accuracy',0)*100:.1f}%",
                            "Soft Accuracy":  f"{m.get('soft_accuracy',0)*100:.1f}%",
                        }
                        for t, m in sorted(
                            type_breakdown.items(),
                            key=lambda x: x[1].get("soft_accuracy", 0),
                        )
                    ]
                    start_row = len(ch_rows) + 3
                    pd.DataFrame(type_rows).to_excel(
                        writer,
                        sheet_name="ChangeVQA",
                        index=False,
                        startrow=start_row,
                    )

        logger.info(f"✅ Excel report saved → {excel_path}")


    # ── Main Generate ─────────────────────────────────────────
    def generate(self) -> dict[str, Any]:
        """
        Runs the full report generation pipeline.

        Steps:
            1. Load all benchmark JSON results
            2. Determine Go/No-Go recommendation
            3. Extract failure patterns
            4. Build JSON summary
            5. Save JSON summary
            6. Build Excel report

        Returns:
            Final JSON summary dict.
        """
        logger.info("=" * 60)
        logger.info("Generating report...")
        logger.info("=" * 60)

        # Step 1: Collect results
        results = self._collect_results()

        if not results:
            logger.error(
                "No benchmark results found. "
                "Run benchmarks first via run_benchmark.py"
            )
            return {}

        # Step 2: Go/No-Go
        recommendation = self._determine_recommendation(results)
        logger.info(f"Recommendation: {recommendation}")

        # Step 3: Failure patterns
        failure_patterns = self._extract_failure_patterns(results)
        for p in failure_patterns:
            logger.info(f"  Pattern: {p}")

        # Step 4: Build JSON summary
        summary = self._build_json_summary(
            results,
            recommendation,
            failure_patterns,
        )

        # Step 5: Save JSON
        json_path = (
            self.results_dir / f"{self.report_name}.json"
        )
        with open(json_path, "w") as f:
            json.dump(summary, f, indent=2)
        logger.info(f"✅ JSON summary saved → {json_path}")

        # Step 6: Build Excel
        if OUTPUT_CONFIG.get("excel_report", True):
            self._build_excel(results, summary)

        logger.info("=" * 60)
        logger.info(
            f"Report complete — Recommendation: {recommendation}"
        )
        logger.info("=" * 60)

        return summary