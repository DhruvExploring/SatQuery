# run_benchmark.py
# ============================================================
# SatQuery AI — Main Benchmark Entry Point
# ============================================================
# This is the ONLY file you need to run.
# It orchestrates the full benchmarking pipeline:
#
#   1. Validate config and environment
#   2. Load EarthMind model
#   3. Load datasets
#   4. Run all enabled benchmark tasks
#   5. Unload model
#   6. Generate final report
#
# Usage:
#   python run_benchmark.py
#   python run_benchmark.py --tasks vqa captioning
#   python run_benchmark.py --datasets vrsbench
#   python run_benchmark.py --samples 50
#
# Output:
#   reports/results/vqa_*.json
#   reports/results/captioning_*.json
#   reports/results/grounding_*.json
#   reports/results/change_vqa_*.json
#   reports/results/baseline_report.json  ← Raja uses this
#   reports/results/baseline_report.xlsx  ← Team shares this
# ============================================================

import argparse
import logging
import os
import sys
import time
from datetime import datetime
from pathlib import Path

from config import (
    BENCHMARK_TASKS,
    DATASET_CONFIG,
    LOG_CONFIG,
    OUTPUT_CONFIG,
    validate_config,
)


# ── Logging Setup ─────────────────────────────────────────────
class SafeStreamHandler(logging.StreamHandler):
    def emit(self, record):
        try:
            super().emit(record)
        except Exception:
            try:
                msg = self.format(record)
                safe_msg = msg.encode(self.stream.encoding or "utf-8", errors="replace").decode(self.stream.encoding or "utf-8", errors="replace")
                self.stream.write(safe_msg + self.terminator)
                self.flush()
            except Exception:
                self.handleError(record)


def setup_logging() -> None:
    """
    Configures logging to both console and file.
    Log file: reports/benchmark.log
    """
    if os.name == "nt":
        os.system("chcp 65001 > nul")
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    if hasattr(sys.stderr, "reconfigure"):
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")

    log_path = Path(LOG_CONFIG["log_path"])
    log_path.parent.mkdir(parents=True, exist_ok=True)

    stream_handler = SafeStreamHandler(sys.stdout)
    file_handler = logging.FileHandler(log_path, mode="a", encoding="utf-8", errors="replace")

    logging.basicConfig(
        level=getattr(logging, LOG_CONFIG["level"]),
        format="%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
        handlers=[
            stream_handler,
            file_handler,
        ],
    )


# ── Argument Parser ───────────────────────────────────────────
def parse_args() -> argparse.Namespace:
    """
    Parses command line arguments.
    Allows running specific tasks or datasets
    without editing config.py.
    """
    parser = argparse.ArgumentParser(
        description="SatQuery AI — EarthMind Baseline Benchmark"
    )

    parser.add_argument(
        "--tasks",
        nargs="+",
        choices=["vqa", "captioning", "grounding", "change_vqa"],
        help="Tasks to run. Default: all enabled in config.py",
    )

    parser.add_argument(
        "--datasets",
        nargs="+",
        choices=["vrsbench", "rsvqa", "cdvqa"],
        help="Datasets to use. Default: all in config.py",
    )

    parser.add_argument(
        "--samples",
        type=int,
        default=None,
        help="Override sample count for quick testing.",
    )

    parser.add_argument(
        "--skip-report",
        action="store_true",
        help="Skip final report generation.",
    )

    return parser.parse_args()


# ── Task Runner ───────────────────────────────────────────────
def run_all(
    tasks:    list[str],
    datasets: list[str],
    samples:  int | None,
) -> dict:
    """
    Runs all requested benchmark tasks in sequence.

    Flow:
        Load Model → Run Tasks → Unload Model → Report

    Args:
        tasks    : List of task names to run.
        datasets : List of dataset names to use.
        samples  : Optional override for sample count.

    Returns:
        Dict of all task results.
    """
    logger = logging.getLogger(__name__)

    # Override sample counts if --samples passed
    if samples:
        for key in DATASET_CONFIG:
            DATASET_CONFIG[key]["samples"] = samples
        logger.info(f"Sample count overridden to {samples}")

    all_results = {}

    # ── Step 1: Load Model ────────────────────────────────────
    from models.earthmind_runner import runner
    logger.info("Loading EarthMind-4B...")
    runner.load()
    logger.info(f"Model status: {runner.status()}")

    # ── Step 2: VQA Task ──────────────────────────────────────
    if "vqa" in tasks:
        from benchmarks.vqa_benchmark import VQABenchmark
        vqa_bench = VQABenchmark(runner)

        if "vrsbench" in datasets:
            from dataset_loaders.vrsbench_loader import VRSBenchLoader
            vrs_loader = VRSBenchLoader()
            vrs_vqa    = vrs_loader.load_vqa()

            logger.info(
                f"Running VQA on VRSBench "
                f"({len(vrs_vqa)} samples)..."
            )
            result = vqa_bench.run(
                samples=vrs_vqa,
                dataset_name="vrsbench_vqa",
            )
            all_results["vrsbench_vqa"] = result

        if "rsvqa" in datasets:
            from dataset_loaders.rsvqa_loader import RSVQALoader
            rsvqa_loader = RSVQALoader()
            rsvqa_vqa    = rsvqa_loader.load_vqa()

            logger.info(
                f"Running VQA on RSVQA "
                f"({len(rsvqa_vqa)} samples)..."
            )
            result = vqa_bench.run(
                samples=rsvqa_vqa,
                dataset_name="rsvqa_vqa",
            )
            all_results["rsvqa_vqa"] = result

    # ── Step 3: Captioning Task ───────────────────────────────
    if "captioning" in tasks:
        if "vrsbench" in datasets:
            from benchmarks.captioning_benchmark import (
                CaptioningBenchmark,
            )
            from dataset_loaders.vrsbench_loader import VRSBenchLoader

            vrs_loader  = VRSBenchLoader()
            vrs_cap     = vrs_loader.load_captioning()
            cap_bench   = CaptioningBenchmark(runner)

            logger.info(
                f"Running Captioning on VRSBench "
                f"({len(vrs_cap)} samples)..."
            )
            result = cap_bench.run(
                samples=vrs_cap,
                dataset_name="vrsbench_captioning",
            )
            all_results["vrsbench_captioning"] = result

    # ── Step 4: Grounding Task ────────────────────────────────
    if "grounding" in tasks:
        if "vrsbench" in datasets:
            from benchmarks.grounding_benchmark import (
                GroundingBenchmark,
            )
            from dataset_loaders.vrsbench_loader import VRSBenchLoader

            vrs_loader = VRSBenchLoader()
            vrs_ground = vrs_loader.load_grounding()
            gr_bench   = GroundingBenchmark(runner)

            logger.info(
                f"Running Grounding on VRSBench "
                f"({len(vrs_ground)} samples)..."
            )
            result = gr_bench.run(
                samples=vrs_ground,
                dataset_name="vrsbench_grounding",
            )
            all_results["vrsbench_grounding"] = result

    # ── Step 5: Change VQA Task ───────────────────────────────
    if "change_vqa" in tasks:
        if "cdvqa" in datasets:
            from benchmarks.change_vqa_benchmark import (
                ChangeVQABenchmark,
            )
            from dataset_loaders.cdvqa_loader import CDVQALoader

            cdvqa_loader = CDVQALoader()
            cdvqa_samples = cdvqa_loader.load_change_vqa()
            ch_bench      = ChangeVQABenchmark(runner)

            logger.info(
                f"Running Change-VQA on CDVQA "
                f"({len(cdvqa_samples)} samples)..."
            )
            result = ch_bench.run(
                samples=cdvqa_samples,
                dataset_name="cdvqa",
            )
            all_results["cdvqa_change_vqa"] = result

    # ── Step 6: Unload Model ──────────────────────────────────
    runner.unload()
    logger.info("EarthMind unloaded — VRAM freed.")

    return all_results


# ── Main ──────────────────────────────────────────────────────
def main() -> None:
    """
    Main entry point for the benchmark pipeline.
    """
    setup_logging()
    logger = logging.getLogger(__name__)

    logger.info("=" * 60)
    logger.info("SatQuery AI — EarthMind Baseline Benchmark")
    logger.info(f"Started: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    logger.info("=" * 60)

    # Parse arguments
    args = parse_args()

    # Determine which tasks to run
    tasks = args.tasks or [
        t for t, enabled in BENCHMARK_TASKS.items()
        if enabled
    ]

    # Determine which datasets to use
    datasets = args.datasets or ["vrsbench", "rsvqa", "cdvqa"]

    logger.info(f"Tasks    : {tasks}")
    logger.info(f"Datasets : {datasets}")
    logger.info(f"Samples  : {args.samples or 'from config'}")

    # Validate environment
    try:
        validate_config()
    except (FileNotFoundError, RuntimeError) as e:
        logger.error(f"Config validation failed: {e}")
        sys.exit(1)

    # Run benchmarks
    start_time = time.time()

    try:
        all_results = run_all(
            tasks=tasks,
            datasets=datasets,
            samples=args.samples,
        )
    except Exception as e:
        logger.error(f"Benchmark pipeline failed: {e}", exc_info=True)
        sys.exit(1)

    total_elapsed = time.time() - start_time
    logger.info(f"All benchmarks complete in {total_elapsed:.1f}s")

    # Generate report
    if not args.skip_report:
        from reports.report_generator import ReportGenerator
        reporter = ReportGenerator()
        summary  = reporter.generate()

        rec = summary.get("recommendation", "UNKNOWN")
        logger.info(f"Final Recommendation: {rec}")

        if rec == "GO":
            logger.info(
                "✅ GO — EarthMind is strong enough. "
                "Fine-tuning will improve further."
            )
        elif rec == "PARTIAL":
            logger.info(
                "⚠️  PARTIAL — Fine-tuning is needed. "
                "Share failure patterns with Raja."
            )
        else:
            logger.info(
                "❌ NO-GO — Consider alternative model. "
                "Discuss with team before proceeding."
            )

    logger.info("=" * 60)
    logger.info("Benchmark pipeline finished.")
    logger.info(
        f"Results: {OUTPUT_CONFIG['results_dir']}"
    )
    logger.info("=" * 60)


if __name__ == "__main__":
    main()