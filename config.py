# config.py
# ============================================================
# SatQuery AI — Benchmark Configuration
# ============================================================
# Central configuration file for the entire benchmarking
# pipeline. All paths, model settings, dataset parameters,
# and evaluation options are defined here.
#
# Every other module imports from this file.
# To change any setting, change it HERE - not inside modules.
# ============================================================

import os
import sys
from pathlib import Path

# ── Ensure UTF-8 Console and IO Encoding on Windows ─────────
os.environ["PYTHONIOENCODING"] = "utf-8"
if os.name == "nt":
    try:
        os.system("chcp 65001 > nul")
    except Exception:
        pass

if hasattr(sys.stdout, "reconfigure"):
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass
if hasattr(sys.stderr, "reconfigure"):
    try:
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

# ── Force HuggingFace to use D Drive Cache ──────────────────
os.environ["HF_HOME"] = "D:/hf_cache"
os.environ["HF_DATASETS_CACHE"] = "D:/hf_cache/datasets"
os.environ["HF_HUB_CACHE"] = "D:/hf_cache/hub"

# ── Project Root ────────────────────────────────────────────
ROOT_DIR = Path(__file__).parent.resolve()

# ── Model Configuration ─────────────────────────────────────
MODEL_CONFIG = {
    "name":           "EarthMind-4B",
    "hf_repo":        "sy1998/EarthMind-4B",
    "local_path":     "D:/models/earthmind",
    "device":         "cuda",       # RTX 4060
    "load_in_4bit":   True,         # Quantize to fit 8GB VRAM
    "max_new_tokens": 128,
    "temperature":    0.0,          # Greedy decoding for eval
    "trust_remote":   True,
}

# ── Fine-Tuned InternVL3 Model Configuration ───────────────
INTERNVL3_CONFIG = {
    "name":           "InternVL3-1B-FT",
    "model_name":     "InternVL3-1B-FT",
    "hf_repo":        "OpenGVLab/InternVL3_5-1B-Instruct",
    "base_path":      "D:/models/internvl3_5_1b",
    "local_path":     "./models/internvl3_finetuned_v2",
    "device":         "cuda",       # RTX 4060
    "load_in_4bit":   True,         # Quantize to fit 8GB VRAM
    "max_new_tokens": 256,
    "temperature":    0.0,          # Greedy decoding for eval
    "trust_remote":   True,
}

# ── Dataset Paths ────────────────────────────────────────────
# local_path points to D:\raw_datasets (actual download location, more disk space)
DATASET_CONFIG = {
    "vrsbench": {
        "hf_repo":    "xiang709/VRSBench",
        "local_path": "D:/raw_datasets/vrsbench",
        "split":      "train",   # eval_* files reference image names that don't match our images/ folder
        "samples":    200,          # Increase after testing
    },
    "rsvqa": {
        "hf_repo":    "dmarsili/RSVQA-HR-2k",
        "local_path": "D:/raw_datasets/rsvqa",
        "split":      "validation",        # ← validation hai yahan
        "samples":    500,
    },
    "cdvqa": {
        "hf_repo":    "EVER-Z/torchange_second",
        "local_path": "D:/raw_datasets/second",
        "split":      "train",
        "samples":    200,
    },
    "earthmind_bench": {
        "hf_repo":    "sy1998/EarthMind-Bench",
        "local_path": "D:/raw_datasets/earthmind_bench",
        "split":      "test",
        "samples":    200,
    },
}

# ── Benchmark Tasks ──────────────────────────────────────────
# Controls which tasks run when run_benchmark.py is executed.
# Set any to False to skip during development.
BENCHMARK_TASKS = {
    "vqa":        True,
    "captioning": True,
    "grounding":  True,
    "change_vqa": True,
}

# ── Metric Configuration ─────────────────────────────────────
METRIC_CONFIG = {
    # BLEU score n-gram weights (standard BLEU-4)
    "bleu_weights": (0.25, 0.25, 0.25, 0.25),

    # mIoU threshold for grounding correctness
    "iou_threshold": 0.5,

    # Confidence interval for reporting (95%)
    "ci_level": 0.95,
}

# ── Output Configuration ─────────────────────────────────────
OUTPUT_CONFIG = {
    "results_dir":   str(ROOT_DIR / "reports" / "results"),
    "report_name":   "baseline_report",
    "save_per_task": True,   # Save JSON after each task
    "save_failures": True,   # Log failed samples separately
    "excel_report":  True,   # Generate Excel summary
}

# ── Logging ──────────────────────────────────────────────────
LOG_CONFIG = {
    "level":      "INFO",
    "log_to_file": True,
    "log_path":   str(ROOT_DIR / "reports" / "benchmark.log"),
}

# ── API Configuration (Sprint 4) ────────────────────────────
API_CONFIG = {
    "host": "0.0.0.0",
    "port": 8001,
    "version": "v1",
    "endpoint_prefix": "/api/v1",
}

# ── Result Schema ────────────────────────────────────────────
# This schema is shared with Raja's fine-tuning pipeline.
# Raja will use the same structure with version="finetuned".
RESULT_SCHEMA = {
    "model":      MODEL_CONFIG["name"],
    "version":    "baseline",        # Raja uses "finetuned"
    "timestamp":  None,              # Filled at runtime
    "vrsbench":   {
        "vqa":        {"accuracy": None, "samples": None},
        "captioning": {"bleu4":    None, "samples": None},
        "grounding":  {"miou":     None, "samples": None},
    },
    "rsvqa": {
        "vqa": {"accuracy": None, "samples": None},
    },
    "cdvqa": {
        "change_vqa": {"accuracy": None, "samples": None},
    },
    "failure_patterns": [],
    "recommendation":   None,        # "GO" / "NO-GO" / "PARTIAL"
}


# ── Runtime Validation ───────────────────────────────────────
def validate_config() -> None:
    """
    Validates that required directories and model path exist.
    Called at startup by run_benchmark.py before any task runs.

    Raises:
        FileNotFoundError: If the model directory is missing.
        RuntimeError: If CUDA is unavailable on the system.
    """
    import torch

    # Check model exists locally
    model_path = Path(MODEL_CONFIG["local_path"])
    if not model_path.exists():
        raise FileNotFoundError(
            f"EarthMind model not found at: {model_path}\n"
            f"Run: huggingface-cli download {MODEL_CONFIG['hf_repo']} "
            f"--local-dir {model_path}"
        )

    # Check CUDA
    if MODEL_CONFIG["device"] == "cuda" and not torch.cuda.is_available():
        raise RuntimeError(
            "CUDA not available. Check your GPU drivers.\n"
            "Alternatively, set MODEL_CONFIG['device'] = 'cpu' "
            "in config.py (will be slow)."
        )

    # Create output directories if missing
    os.makedirs(OUTPUT_CONFIG["results_dir"], exist_ok=True)
    os.makedirs(Path(LOG_CONFIG["log_path"]).parent, exist_ok=True)

    import sys
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    if hasattr(sys.stderr, "reconfigure"):
        sys.stderr.reconfigure(encoding="utf-8")

    print("[OK] Config validation passed.")
    print(f"   Model  : {MODEL_CONFIG['name']}")
    print(f"   Device : {MODEL_CONFIG['device']} "
          f"({torch.cuda.get_device_name(0) if torch.cuda.is_available() else 'CPU'})")
    print(f"   Results: {OUTPUT_CONFIG['results_dir']}")