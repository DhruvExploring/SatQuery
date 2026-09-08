# datasets/cdvqa_loader.py
# ============================================================
# SatQuery AI — CDVQA Loader (SECOND Dataset)
# ============================================================
# Responsibilities:
#   - Load EVER-Z/torchange_second from HuggingFace
#   - Provide standardized bi-temporal image pairs
#   - Use predefined change-related questions
#   - Evaluate EarthMind's change reasoning ability
#
# Strategy:
#   No JSON annotations needed.
#   SECOND dataset provides before/after image pairs.
#   EarthMind answers predefined change questions.
#   Change mask used for ground truth verification.
#
# Dataset:
#   HuggingFace : EVER-Z/torchange_second
#   Train       : 2,968 pairs
#   Test        : 1,694 pairs
#   Image size  : 512 x 512 px
#   Columns     : t1_image, t2_image, t1_mask,
#                 t2_mask, change_mask, image_name
#
# Used by:
#   - benchmarks/change_vqa_benchmark.py
# ============================================================

import logging
from typing import Any

import numpy as np
from datasets import load_dataset
from PIL import Image

from config import DATASET_CONFIG

logger = logging.getLogger(__name__)


# ── Predefined Change Questions ───────────────────────────────
# These questions are asked to EarthMind for every image pair.
# No external annotation needed — questions are fixed.
# EarthMind answers based purely on visual reasoning.

CHANGE_QUESTIONS = [
    {
        "question": (
            "What has changed between the two satellite images?"
        ),
        "type": "open_ended",
    },
    {
        "question": (
            "Has any urban or built-up area changed "
            "between these two images?"
        ),
        "type": "presence",
    },
    {
        "question": (
            "Is there any change in vegetation or "
            "green areas between the two images?"
        ),
        "type": "presence",
    },
    {
        "question": (
            "Has the water body changed between "
            "the two satellite images?"
        ),
        "type": "presence",
    },
    {
        "question": (
            "Describe the land cover change visible "
            "between the before and after images."
        ),
        "type": "description",
    },
]

# Land cover classes in SECOND dataset
SECOND_CLASSES = {
    0: "no_change",
    1: "non_vegetated_ground",
    2: "tree",
    3: "low_vegetation",
    4: "water",
    5: "buildings",
    6: "playgrounds",
}


class CDVQALoader:
    """
    Loader for change VQA using the SECOND dataset.

    Uses EVER-Z/torchange_second which contains the exact
    same 2,968 image pairs that the original CDVQA paper
    built its dataset upon.

    Each sample provides:
        - t1_image    : Pre-event satellite image (before)
        - t2_image    : Post-event satellite image (after)
        - change_mask : Pixel-level change annotation
        - image_name  : Unique identifier

    EarthMind is evaluated on predefined change questions
    without requiring external JSON annotations.
    Change mask is used to derive ground truth context
    for result validation.
    """

    def __init__(self) -> None:
        self.cfg         = DATASET_CONFIG["cdvqa"]
        self.hf_repo     = self.cfg["hf_repo"]
        self.split       = self.cfg["split"]
        self.max_samples = self.cfg["samples"]
        self._raw        = None

        logger.info("CDVQALoader initialized.")
        logger.info(f"  Repo    : {self.hf_repo}")
        logger.info(f"  Split   : {self.split}")
        logger.info(f"  Samples : {self.max_samples}")


    # ── Load ──────────────────────────────────────────────────
    def _load_raw(self) -> None:
        """
        Downloads and caches SECOND dataset from HuggingFace.
        Called once — result reused across all load calls.
        """
        if self._raw is not None:
            return

        logger.info(
            f"Downloading {self.hf_repo} "
            f"(split={self.split})..."
        )

        self._raw = load_dataset(
            self.hf_repo,
            split=self.split,
            trust_remote_code=True,
        )

        logger.info(
            f"✅ SECOND dataset loaded — "
            f"{len(self._raw)} image pairs available."
        )
        logger.info(
            f"   Columns: {self._raw.column_names}"
        )


    # ── Image Extraction ──────────────────────────────────────
    def _get_image(
        self,
        sample: dict[str, Any],
        key:    str,
    ) -> Image.Image:
        """
        Extracts a PIL Image from a SECOND dataset sample.

        Args:
            sample : Raw dataset row.
            key    : Column name (t1_image or t2_image).

        Returns:
            PIL.Image in RGB mode.

        Raises:
            ValueError : If image cannot be extracted.
        """
        img = sample.get(key)

        if img is None:
            raise ValueError(
                f"Key '{key}' not found in sample. "
                f"Available: {list(sample.keys())}"
            )

        if isinstance(img, Image.Image):
            return img.convert("RGB")

        if isinstance(img, bytes):
            import io
            return Image.open(
                io.BytesIO(img)
            ).convert("RGB")

        raise ValueError(
            f"Cannot extract image from type: {type(img)}"
        )


    # ── Change Mask Analysis ──────────────────────────────────
    def _analyze_change_mask(
        self,
        mask: Any,
        t1_mask: Any = None,
        t2_mask: Any = None,
    ) -> dict[str, Any]:
        """
        Analyzes the SECOND dataset change mask and land cover masks.

        In the SECOND dataset:
          - change_mask is a binary mask (0 = no change, 255 = change).
          - t1_mask / t2_mask contain land cover class IDs (1-6).
        """
        try:
            if isinstance(mask, Image.Image):
                mask_array = np.array(mask)
            elif isinstance(mask, np.ndarray):
                mask_array = mask
            else:
                mask_array = np.array(mask)

            total_pixels = mask_array.size
            changed_pixels = np.sum(mask_array > 0)
            change_ratio = round(float(changed_pixels) / total_pixels, 4)
            has_change = change_ratio > 0.0005  # > 0.05% changed pixels

            changed_classes = []
            dominant_change = "no_change"

            if has_change and (t1_mask is not None or t2_mask is not None):
                changed_idx = mask_array > 0
                class_counts = {}

                for m in (t1_mask, t2_mask):
                    if m is not None:
                        m_arr = np.array(m) if isinstance(m, Image.Image) else np.array(m)
                        unique_c, counts_c = np.unique(m_arr[changed_idx], return_counts=True)
                        for c, count in zip(unique_c, counts_c):
                            c_int = int(c)
                            if c_int not in (0, 255):
                                c_name = SECOND_CLASSES.get(c_int, f"class_{c_int}")
                                class_counts[c_name] = class_counts.get(c_name, 0) + int(count)

                if class_counts:
                    changed_classes = list(class_counts.keys())
                    dominant_change = max(class_counts, key=class_counts.get)
                else:
                    dominant_change = "general_change"
            elif has_change:
                dominant_change = "general_change"

            return {
                "has_change":      has_change,
                "changed_classes": changed_classes,
                "change_ratio":    change_ratio,
                "dominant_change": dominant_change,
            }

        except Exception as e:
            logger.warning(f"Mask analysis failed: {e}")
            return {
                "has_change":      None,
                "changed_classes": [],
                "change_ratio":    None,
                "dominant_change": "unknown",
            }


    # ── Main Loader ───────────────────────────────────────────
    def load_change_vqa(
        self,
        question_index: int = 0,
    ) -> list[dict[str, Any]]:
        """
        Returns change VQA samples from SECOND dataset.

        Each sample contains a before/after image pair
        with a predefined change question.

        Args:
            question_index : Index into CHANGE_QUESTIONS list.
                             Default 0 = open-ended question.
                             Range: 0 to 4.

        Each sample contains:
            image_before   (PIL.Image) : Pre-event image
            image_after    (PIL.Image) : Post-event image
            question       (str)       : Change question
            question_type  (str)       : open_ended/presence/description
            change_context (dict)      : GT from change mask
            image_name     (str)       : Unique identifier
            sample_id      (str)       : Index string
            source         (str)       : "second"

        Returns:
            List of standardized change-VQA sample dicts.
        """
        self._load_raw()

        if not 0 <= question_index < len(CHANGE_QUESTIONS):
            raise ValueError(
                f"question_index must be 0–"
                f"{len(CHANGE_QUESTIONS) - 1}. "
                f"Got: {question_index}"
            )

        selected_q = CHANGE_QUESTIONS[question_index]
        samples    = []
        skipped    = 0

        logger.info(
            f"Loading change VQA samples — "
            f"Question: '{selected_q['question'][:60]}...'"
        )

        for idx, row in enumerate(self._raw):
            if len(samples) >= self.max_samples:
                break

            try:
                # Extract before + after images
                image_before = self._get_image(row, "t1_image")
                image_after  = self._get_image(row, "t2_image")

                # Analyze change mask for GT context
                change_mask    = row.get("change_mask")
                t1_mask        = row.get("t1_mask")
                t2_mask        = row.get("t2_mask")
                change_context = self._analyze_change_mask(
                    change_mask, t1_mask, t2_mask
                )

                image_name = str(
                    row.get("image_name", f"sample_{idx}")
                )

                samples.append({
                    "image_before":   image_before,
                    "image_after":    image_after,
                    "question":       selected_q["question"],
                    "question_type":  selected_q["type"],
                    "change_type":    change_context["dominant_change"],
                    "answer": (
                        "yes" if change_context.get("has_change")
                        else "no"
                    ),
                    "change_context": change_context,
                    "image_name":     image_name,
                    "sample_id":      str(idx),
                    "source":         "second",
                })

            except Exception as e:
                logger.warning(
                    f"SECOND row {idx} skipped: {e}"
                )
                skipped += 1
                continue

        logger.info(
            f"✅ Change VQA: {len(samples)} samples ready."
        )
        if skipped:
            logger.info(f"   Skipped: {skipped} rows.")

        return samples


    # ── Multi-Question Loader ─────────────────────────────────
    def load_all_questions(self) -> list[dict[str, Any]]:
        """
        Returns samples for ALL predefined change questions.
        Each image pair appears multiple times —
        once per question.

        Useful for comprehensive evaluation across all
        change question types.

        Returns:
            Combined list of all question samples.
        """
        self._load_raw()
        all_samples = []

        for q_idx in range(len(CHANGE_QUESTIONS)):
            samples = self.load_change_vqa(
                question_index=q_idx
            )
            all_samples.extend(samples)
            logger.info(
                f"Question {q_idx + 1}/{len(CHANGE_QUESTIONS)}"
                f" loaded: {len(samples)} samples."
            )

        logger.info(
            f"✅ All questions loaded: "
            f"{len(all_samples)} total samples."
        )
        return all_samples


    # ── Change Summary ────────────────────────────────────────
    def get_change_distribution(self) -> dict[str, int]:
        """
        Returns distribution of dominant change classes
        across the dataset.

        Useful for understanding which change types are
        most common — helps identify where EarthMind
        may struggle.

        Returns:
            Dict mapping change_class -> count.
        """
        self._load_raw()
        distribution: dict[str, int] = {}
        limit = min(500, len(self._raw))

        for idx, row in enumerate(self._raw):
            if idx >= limit:
                break

            mask    = row.get("change_mask")
            context = self._analyze_change_mask(mask)
            dominant = context["dominant_change"]
            distribution[dominant] = (
                distribution.get(dominant, 0) + 1
            )

        logger.info(
            f"Change distribution (n={limit}): "
            f"{distribution}"
        )
        return distribution