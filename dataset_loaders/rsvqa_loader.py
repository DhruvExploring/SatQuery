# datasets/rsvqa_loader.py
# ============================================================
# SatQuery AI — RSVQA-HR-2k Dataset Loader
# ============================================================
# Responsibilities:
#   - Load RSVQA-HR-2k dataset from HuggingFace
#   - Provide standardized VQA samples for evaluation
#   - Support question type filtering
#   - Handle High Resolution satellite images (512x512)
#
# Dataset:
#   HuggingFace: dmarsili/RSVQA-HR-2k
#   Split:       validation (2,000 samples)
#   Image size:  512 x 512 px
#   Columns:     image, question, answer
#
# Used by:
#   - benchmarks/vqa_benchmark.py
# ============================================================

import logging
from typing import Any, Optional

from datasets import load_dataset
from PIL import Image

from config import DATASET_CONFIG

logger = logging.getLogger(__name__)


class RSVQALoader:
    """
    Loader for the RSVQA-HR-2k (High Resolution) dataset.

    RSVQA-HR-2k is a 2,000-sample validation subset of the
    original RSVQA-HR dataset, ported to HuggingFace for
    ease of use in remote sensing VQA evaluation.

    Image resolution: 512 x 512 pixels (high resolution).
    This is more realistic for satellite imagery evaluation
    compared to the Low Resolution (LR) variant.

    Question types include:
        - Presence   : "Is there a water area?"
        - Count      : "How many buildings are there?"
        - Comparison : "Are there more roads than buildings?"
        - Area       : "What is the area covered by roads?"

    Original dataset: rsvqa.sylvainlobry.com/#dataset
    HuggingFace:      dmarsili/RSVQA-HR-2k
    """

    # Answer patterns used to infer question type
    # when explicit type labels are absent in this dataset
    BINARY_ANSWERS  = {"yes", "no"}
    COUNT_PATTERN   = r"^\d+$"
    AREA_PATTERN    = r"^\d+m2$"

    def __init__(self) -> None:
        self.cfg         = DATASET_CONFIG["rsvqa"]
        self.hf_repo     = self.cfg["hf_repo"]       # dmarsili/RSVQA-HR-2k
        self.split       = self.cfg["split"]          # validation
        self.max_samples = self.cfg["samples"]
        self._raw        = None

        logger.info("RSVQALoader initialized.")
        logger.info(f"  Repo    : {self.hf_repo}")
        logger.info(f"  Split   : {self.split}")
        logger.info(f"  Samples : {self.max_samples}")


    # ── Load ──────────────────────────────────────────────────
    def _load_raw(self) -> None:
        """
        Downloads and caches RSVQA-HR-2k from HuggingFace.
        Called once — result is reused across all load calls.
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
            f"✅ RSVQA-HR-2k loaded — "
            f"{len(self._raw)} total samples available."
        )


    # ── Image Extraction ──────────────────────────────────────
    def _get_image(self, sample: dict[str, Any]) -> Image.Image:
        """
        Extracts and validates PIL image from an RSVQA sample.

        RSVQA-HR-2k stores images directly as PIL objects
        in the HuggingFace dataset (Parquet format).
        All images are 512x512 RGB satellite tiles.

        Args:
            sample : Raw dataset row dict.

        Returns:
            PIL.Image in RGB mode.

        Raises:
            ValueError : If no image can be extracted.
        """
        img = sample.get("image")

        if img is None:
            raise ValueError(
                f"No 'image' key in sample. "
                f"Available keys: {list(sample.keys())}"
            )

        if isinstance(img, Image.Image):
            return img.convert("RGB")

        if isinstance(img, str):
            return Image.open(img).convert("RGB")

        if isinstance(img, bytes):
            import io
            return Image.open(io.BytesIO(img)).convert("RGB")

        raise ValueError(
            f"Cannot extract image from type: {type(img)}"
        )


    # ── Question Type Inference ───────────────────────────────
    def _infer_question_type(
        self,
        question: str,
        answer:   str,
    ) -> str:
        """
        Infers question type from question text and answer.

        RSVQA-HR-2k does not include explicit type labels,
        so we infer them from answer patterns and question
        keywords.

        Types:
            presence   : Binary yes/no questions
            count      : Numeric count answers
            area       : Area in m2 (e.g., "495m2")
            comparison : Comparative yes/no questions
            unknown    : Cannot be determined

        Args:
            question : Question string.
            answer   : Ground truth answer string.

        Returns:
            Question type string.
        """
        import re

        ans_lower = answer.lower().strip()
        q_lower   = question.lower().strip()

        # Binary presence
        if ans_lower in self.BINARY_ANSWERS:
            if any(w in q_lower for w in
                   ["more", "less", "equal", "than"]):
                return "comparison"
            return "presence"

        # Count (pure integer answer)
        if re.match(self.COUNT_PATTERN, ans_lower):
            return "count"

        # Area (e.g., "495m2", "0m2")
        if re.match(self.AREA_PATTERN, ans_lower):
            return "area"

        return "unknown"


    # ── VQA Loader ────────────────────────────────────────────
    def load_vqa(
        self,
        question_type: Optional[str] = None,
    ) -> list[dict[str, Any]]:
        """
        Returns VQA samples from RSVQA-HR-2k.

        Args:
            question_type : Optional filter. One of:
                            "presence", "count", "area",
                            "comparison", "unknown"
                            None = all types included.

        Each sample contains:
            image         (PIL.Image) : 512x512 satellite image
            question      (str)       : Natural language question
            answer        (str)       : Ground truth answer
            question_type (str)       : Inferred question type
            is_binary     (bool)      : True for yes/no answers
            sample_id     (str)       : Row index as string
            source        (str)       : "rsvqa_hr"

        Returns:
            List of standardized VQA sample dicts.
        """
        self._load_raw()

        valid_types = {
            "presence", "count", "area",
            "comparison", "unknown"
        }

        if question_type and question_type not in valid_types:
            raise ValueError(
                f"Invalid question_type: '{question_type}'. "
                f"Choose from: {sorted(valid_types)}"
            )

        samples = []
        skipped = 0

        for idx, row in enumerate(self._raw):
            if len(samples) >= self.max_samples:
                break

            try:
                question = str(
                    row.get("question", "")
                ).strip()

                answer = str(
                    row.get("answer", "")
                ).strip()

                if not question or not answer:
                    logger.debug(
                        f"Skipping row {idx} — "
                        f"empty question or answer."
                    )
                    skipped += 1
                    continue

                # Infer question type
                q_type = self._infer_question_type(
                    question, answer
                )

                # Apply type filter if requested
                if question_type and q_type != question_type:
                    continue

                image = self._get_image(row)

                samples.append({
                    "image":         image,
                    "question":      question,
                    "answer":        answer,
                    "question_type": q_type,
                    "is_binary":     answer.lower() in
                                     self.BINARY_ANSWERS,
                    "sample_id":     str(idx),
                    "source":        "rsvqa_hr",
                })

            except Exception as e:
                logger.warning(
                    f"RSVQA-HR-2k row {idx} skipped: {e}"
                )
                skipped += 1
                continue

        logger.info(
            f"✅ RSVQA-HR-2k VQA: "
            f"{len(samples)} samples ready."
        )
        if skipped:
            logger.info(f"   Skipped: {skipped} rows.")
        if question_type:
            logger.info(f"   Filter : type='{question_type}'")

        return samples


    # ── Type Distribution ─────────────────────────────────────
    def get_type_distribution(self) -> dict[str, int]:
        """
        Returns count of each inferred question type.
        Useful for understanding dataset balance before
        running the benchmark.

        Returns:
            Dict mapping question_type -> count.

        Example output:
            {
                "presence":   620,
                "comparison": 580,
                "count":      450,
                "area":       320,
                "unknown":    30
            }
        """
        self._load_raw()
        distribution: dict[str, int] = {}

        for row in self._raw:
            question = str(row.get("question", "")).strip()
            answer   = str(row.get("answer",   "")).strip()
            q_type   = self._infer_question_type(
                question, answer
            )
            distribution[q_type] = (
                distribution.get(q_type, 0) + 1
            )

        logger.info(
            f"RSVQA-HR-2k type distribution: {distribution}"
        )
        return distribution


    # ── Binary Only ───────────────────────────────────────────
    def load_binary_vqa(self) -> list[dict[str, Any]]:
        """
        Convenience method — returns only yes/no samples.
        Combines presence + comparison types.

        Used by vqa_benchmark.py with is_binary=True
        for more lenient accuracy computation.

        Returns:
            List of binary VQA sample dicts.
        """
        self._load_raw()
        all_samples = self.load_vqa()

        binary = [s for s in all_samples if s["is_binary"]]

        logger.info(
            f"✅ RSVQA-HR-2k Binary VQA: "
            f"{len(binary)} samples ready."
        )
        return binary