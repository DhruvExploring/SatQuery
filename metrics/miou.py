# metrics/miou.py
# ============================================================
# SatQuery AI — mIoU (Mean Intersection over Union) Metric
# ============================================================
# Responsibilities:
#   - Parse predicted bounding boxes from model text output
#   - Compute IoU between predicted and ground truth boxes
#   - Compute mIoU over a list of grounding samples
#   - Return per-sample results + aggregate score
#
# Used by:
#   - benchmarks/grounding_benchmark.py
# ============================================================

import logging
import re
from typing import Any, Optional

logger = logging.getLogger(__name__)


# ── Bounding Box Parsing ──────────────────────────────────────
def parse_bbox(text: str) -> Optional[list[float]]:
    """
    Parses a bounding box from model output text.

    EarthMind is prompted to return boxes as:
        "[x1, y1, x2, y2]"
    in normalized coordinates [0.0, 1.0].

    Handles common formats:
        "[0.1, 0.2, 0.8, 0.9]"
        "(0.1, 0.2, 0.8, 0.9)"
        "0.1 0.2 0.8 0.9"
        "x1=0.1, y1=0.2, x2=0.8, y2=0.9"

    Args:
        text : Raw model output string.

    Returns:
        List of 4 floats [x1, y1, x2, y2] or None if parsing fails.
    """
    if not text:
        return None

    # Try to extract 4 numbers from the text
    numbers = re.findall(r"[-+]?\d*\.?\d+", text)

    if len(numbers) < 4:
        logger.debug(
            f"Could not parse bbox from: '{text[:100]}' "
            f"— found only {len(numbers)} numbers."
        )
        return None

    try:
        # Take the first 4 numbers found
        bbox = [float(n) for n in numbers[:4]]

        # Validate range — should be [0, 1] for normalized
        # If values > 1, they might be pixel coordinates
        if all(0.0 <= v <= 1.0 for v in bbox):
            return bbox

        # Values > 1 — likely pixel coordinates, return as-is
        # grounding_benchmark will handle normalization
        return bbox

    except (ValueError, TypeError) as e:
        logger.debug(f"bbox parse error: {e}")
        return None


def _validate_bbox(bbox: list[float]) -> bool:
    """
    Validates that a bounding box is geometrically valid.

    Checks:
        - Has exactly 4 values
        - x1 < x2 and y1 < y2
        - All values are non-negative

    Args:
        bbox : List of [x1, y1, x2, y2].

    Returns:
        True if valid, False otherwise.
    """
    if len(bbox) != 4:
        return False

    x1, y1, x2, y2 = bbox

    if x1 >= x2 or y1 >= y2:
        return False

    if any(v < 0 for v in bbox):
        return False

    return True


# ── IoU Computation ───────────────────────────────────────────
def compute_iou(
    pred_bbox: list[float],
    gt_bbox:   list[float],
) -> float:
    """
    Computes Intersection over Union (IoU) between two boxes.

    Both boxes should be in [x1, y1, x2, y2] format.
    Coordinates can be normalized [0,1] or pixel values —
    both work as long as they are in the same coordinate space.

    Args:
        pred_bbox : Predicted box [x1, y1, x2, y2].
        gt_bbox   : Ground truth box [x1, y1, x2, y2].

    Returns:
        IoU score in [0.0, 1.0].
        Returns 0.0 if either box is invalid.
    """
    if not _validate_bbox(pred_bbox) or not _validate_bbox(gt_bbox):
        return 0.0

    px1, py1, px2, py2 = pred_bbox
    gx1, gy1, gx2, gy2 = gt_bbox

    # Intersection coordinates
    ix1 = max(px1, gx1)
    iy1 = max(py1, gy1)
    ix2 = min(px2, gx2)
    iy2 = min(py2, gy2)

    # No intersection
    if ix2 <= ix1 or iy2 <= iy1:
        return 0.0

    # Areas
    intersection = (ix2 - ix1) * (iy2 - iy1)
    pred_area    = (px2 - px1) * (py2 - py1)
    gt_area      = (gx2 - gx1) * (gy2 - gy1)
    union        = pred_area + gt_area - intersection

    if union <= 0:
        return 0.0

    return round(intersection / union, 4)


# ── Full Grounding Evaluation ─────────────────────────────────
def compute_miou(
    predictions:   list[str],
    ground_truths: list[list[float]],
    iou_threshold: float = None,
) -> dict[str, Any]:
    """
    Computes mIoU for the grounding benchmark.

    For each sample:
        1. Parses predicted bbox from model text output
        2. Computes IoU with ground truth bbox
        3. Marks as correct if IoU >= threshold

    Args:
        predictions   : List of model text outputs (raw strings).
                        Each string should contain a bbox.
        ground_truths : List of GT bboxes [[x1,y1,x2,y2], ...].
        iou_threshold : Minimum IoU to count as correct.
                        Default from config (0.5).

    Returns:
        Dict with:
            miou          (float) : Mean IoU across all samples
            accuracy_50   (float) : % samples with IoU >= 0.50
            accuracy_25   (float) : % samples with IoU >= 0.25
            parse_success (float) : % samples where bbox was parsed
            total         (int)   : Total samples
            per_sample    (list)  : Per-sample result dicts

    Raises:
        ValueError: If predictions and ground_truths differ in length.
    """
    from config import METRIC_CONFIG
    if iou_threshold is None:
        iou_threshold = METRIC_CONFIG["iou_threshold"]

    if len(predictions) != len(ground_truths):
        raise ValueError(
            f"Length mismatch: {len(predictions)} predictions "
            f"vs {len(ground_truths)} ground truths."
        )

    if not predictions:
        logger.warning("compute_miou called with empty lists.")
        return {
            "miou":          0.0,
            "accuracy_50":   0.0,
            "accuracy_25":   0.0,
            "parse_success": 0.0,
            "total":         0,
            "per_sample":    [],
        }

    iou_scores    = []
    parse_success = 0
    correct_50    = 0
    correct_25    = 0
    per_sample    = []

    for idx, (pred_text, gt_bbox) in enumerate(
        zip(predictions, ground_truths)
    ):
        pred_bbox = parse_bbox(pred_text)
        parsed    = pred_bbox is not None

        if parsed:
            parse_success += 1
            iou = compute_iou(pred_bbox, gt_bbox)
        else:
            iou = 0.0

        iou_scores.append(iou)

        if iou >= 0.50:
            correct_50 += 1
        if iou >= 0.25:
            correct_25 += 1

        per_sample.append({
            "idx":            idx,
            "prediction_raw": pred_text,
            "pred_bbox":      pred_bbox,
            "gt_bbox":        gt_bbox,
            "iou":            iou,
            "parsed":         parsed,
            "correct_50":     iou >= 0.50,
            "correct_25":     iou >= 0.25,
        })

    total = len(predictions)

    result = {
        "miou":          round(sum(iou_scores) / total, 4),
        "accuracy_50":   round(correct_50    / total, 4),
        "accuracy_25":   round(correct_25    / total, 4),
        "parse_success": round(parse_success / total, 4),
        "total":         total,
        "per_sample":    per_sample,
    }

    logger.info(
        f"mIoU — Mean: {result['miou']:.4f} | "
        f"Acc@50: {result['accuracy_50']*100:.1f}% | "
        f"Acc@25: {result['accuracy_25']*100:.1f}% | "
        f"Parse: {result['parse_success']*100:.1f}%"
    )

    return result


# ── Failure Analysis ──────────────────────────────────────────
def get_grounding_failures(
    per_sample: list[dict[str, Any]],
    iou_threshold: float = 0.5,
) -> dict[str, list[dict]]:
    """
    Splits grounding failures into two categories:
        1. parse_failures  — model did not output a valid bbox
        2. low_iou_cases   — bbox parsed but IoU too low

    Args:
        per_sample    : Output of compute_miou()["per_sample"]
        iou_threshold : IoU below which sample is a failure.

    Returns:
        Dict with "parse_failures" and "low_iou_cases" lists.
    """
    parse_failures = [s for s in per_sample if not s["parsed"]]
    low_iou_cases  = [
        s for s in per_sample
        if s["parsed"] and s["iou"] < iou_threshold
    ]

    logger.info(
        f"Grounding failures — "
        f"Parse failures: {len(parse_failures)} | "
        f"Low IoU: {len(low_iou_cases)}"
    )

    return {
        "parse_failures": parse_failures,
        "low_iou_cases":  low_iou_cases,
    }