# datasets/vrsbench_loader.py
# ============================================================
# SatQuery AI — VRSBench Dataset Loader
# ============================================================
# Responsibilities:
#   - Load VRSBench "train" split (LLaVA-style conversations)
#     directly from the cached raw JSON (bypasses the upstream
#     HF `load_dataset` schema bug where some 'id' values are
#     strings like 'Final_Data/v1.2' instead of int64).
#   - Classify each conversation into VQA / captioning /
#     grounding based on its [vqa] / [caption] / [refer] tag.
#   - Resolve image filenames against the locally extracted
#     Images_train.zip / Images_val.zip contents.
#
# Used by:
#   - benchmarks/vqa_benchmark.py
#   - benchmarks/captioning_benchmark.py
#   - benchmarks/grounding_benchmark.py
# ============================================================

import json
import logging
import re
from pathlib import Path
from typing import Any, Optional

from huggingface_hub import hf_hub_download
from PIL import Image

from config import DATASET_CONFIG

logger = logging.getLogger(__name__)

BBOX_TOKEN_RE = re.compile(r"<(\d+)>")


# ── Standardized Sample Schema ───────────────────────────────
# Every loader in this project returns the same schema.
# This allows benchmarks to work with any dataset loader.
#
# VQA sample:
#   { "image": PIL.Image, "question": str, "answer": str,
#     "sample_id": str, "source": "vrsbench" }
#
# Captioning sample:
#   { "image": PIL.Image, "reference_caption": str,
#     "sample_id": str, "source": "vrsbench" }
#
# Grounding sample:
#   { "image": PIL.Image, "region_description": str,
#     "bbox": [x1, y1, x2, y2], "sample_id": str,
#     "source": "vrsbench" }


class VRSBenchLoader:
    """
    Loader for the VRSBench remote sensing benchmark dataset.

    VRSBench contains:
        - 29,614 satellite images
        - 52,472 object references
        - 123,221 VQA pairs

    Reference: https://huggingface.co/datasets/xiang709/VRSBench
    """

    def __init__(self) -> None:
        self.cfg         = DATASET_CONFIG["vrsbench"]
        self.hf_repo     = self.cfg["hf_repo"]
        self.split       = self.cfg["split"]
        self.max_samples = self.cfg["samples"]
        self._raw: Optional[list[dict[str, Any]]] = None
        self._image_index: Optional[dict[str, Path]] = None

        logger.info("VRSBenchLoader initialized.")
        logger.info(f"  Repo    : {self.hf_repo}")
        logger.info(f"  Split   : {self.split}")
        logger.info(f"  Samples : {self.max_samples}")

    # ── Raw JSON loading (bypasses broken HF loader) ─────────
    def _load_raw(self) -> None:
        """
        Loads the raw VRSBench_<split>.json directly, bypassing
        HF `datasets`' automatic arrow-schema inference (which
        crashes on mixed int/string 'id' values in this repo).
        """
        if self._raw is not None:
            return

        filename = f"VRSBench_{self.split}.json"
        logger.info(f"Loading {filename} from HuggingFace cache...")
        path = hf_hub_download(
            repo_id=self.hf_repo,
            filename=filename,
            repo_type="dataset",
        )
        with open(path, encoding="utf-8") as f:
            self._raw = json.load(f)

        logger.info(f"✅ VRSBench loaded — {len(self._raw)} samples.")

    # ── Image path resolution ─────────────────────────────────
    def _build_image_index(self) -> None:
        if self._image_index is not None:
            return

        images_root = Path(self.cfg["local_path"]) / "images"
        self._image_index = {
            p.name: p for p in images_root.rglob("*.png")
        }
        logger.info(
            f"Indexed {len(self._image_index)} VRSBench image files."
        )

    def _get_image(self, image_name: str) -> Image.Image:
        """
        Resolves a VRSBench image filename to the extracted
        Images_train.zip / Images_val.zip contents on disk.
        """
        self._build_image_index()
        path = self._image_index.get(image_name)
        if path is None:
            raise ValueError(f"Image not found: {image_name}")
        return Image.open(path).convert("RGB")

    # ── Conversation helpers ───────────────────────────────────
    @staticmethod
    def _tag(human_text: str) -> str:
        """Extracts the [vqa] / [caption] / [refer] tag from a prompt."""
        m = re.search(r"\[(vqa|caption|refer)\]", human_text)
        return m.group(1) if m else "vqa"

    @staticmethod
    def _parse_bbox(gpt_text: str) -> Optional[list[float]]:
        """Parses '{<x1><y1><x2><y2>}' (0-100 scale) into normalized floats."""
        nums = BBOX_TOKEN_RE.findall(gpt_text)
        if len(nums) < 4:
            return None
        x1, y1, x2, y2 = (int(n) / 100.0 for n in nums[:4])
        return [x1, y1, x2, y2]

    @staticmethod
    def _region_description(human_text: str) -> str:
        """Extracts the text inside <p>...</p> from a [refer] prompt."""
        m = re.search(r"<p>(.*?)</p>", human_text)
        return m.group(1).strip() if m else human_text.strip()

    # ── Task 1: VQA ──────────────────────────────────────────
    def load_vqa(self) -> list[dict[str, Any]]:
        """
        Returns VQA samples from VRSBench.

        Each sample contains:
            image    (PIL.Image) : Satellite image
            question (str)       : Natural language question
            answer   (str)       : Ground truth answer
            sample_id (str)      : Unique identifier
            source   (str)       : "vrsbench"

        Returns:
            List of standardized VQA dicts.
        """
        self._load_raw()
        samples = []

        for row in self._raw:
            if len(samples) >= self.max_samples:
                break

            human = row["conversations"][0]["value"]
            gpt   = row["conversations"][1]["value"]
            if self._tag(human) != "vqa":
                continue

            try:
                question = human.replace("<image>", "").split("]", 1)[-1].strip()
                samples.append({
                    "image":     self._get_image(row["image"]),
                    "question":  question,
                    "answer":    gpt.strip(),
                    "sample_id": str(row.get("id", row["image"])),
                    "source":    "vrsbench",
                })
            except Exception as e:
                logger.warning(f"VRSBench VQA row skipped: {e}")
                continue

        logger.info(f"✅ VRSBench VQA: {len(samples)} samples ready.")
        return samples


    # ── Task 2: Captioning ────────────────────────────────────
    def load_captioning(self) -> list[dict[str, Any]]:
        """
        Returns captioning samples from VRSBench.

        Each sample contains:
            image              (PIL.Image) : Satellite image
            reference_caption  (str)       : Ground truth caption
            sample_id          (str)       : Unique identifier
            source             (str)       : "vrsbench"

        Returns:
            List of standardized captioning dicts.
        """
        self._load_raw()
        samples = []

        for row in self._raw:
            if len(samples) >= self.max_samples:
                break

            human = row["conversations"][0]["value"]
            gpt   = row["conversations"][1]["value"]
            if self._tag(human) != "caption":
                continue

            try:
                samples.append({
                    "image":             self._get_image(row["image"]),
                    "reference_caption": gpt.strip(),
                    "sample_id":         str(row.get("id", row["image"])),
                    "source":            "vrsbench",
                })
            except Exception as e:
                logger.warning(f"VRSBench captioning row skipped: {e}")
                continue

        logger.info(
            f"✅ VRSBench Captioning: {len(samples)} samples ready."
        )
        return samples


    # ── Task 3: Grounding ─────────────────────────────────────
    def load_grounding(self) -> list[dict[str, Any]]:
        """
        Returns region grounding samples from VRSBench.

        Each sample contains:
            image               (PIL.Image)    : Satellite image
            region_description  (str)          : Text description of region
            bbox                (list[float])  : [x1, y1, x2, y2] normalized
            sample_id           (str)          : Unique identifier
            source              (str)          : "vrsbench"

        Returns:
            List of standardized grounding dicts.
        """
        self._load_raw()
        samples = []

        for row in self._raw:
            if len(samples) >= self.max_samples:
                break

            human = row["conversations"][0]["value"]
            gpt   = row["conversations"][1]["value"]
            if self._tag(human) != "refer":
                continue

            bbox = self._parse_bbox(gpt)
            if bbox is None:
                continue

            try:
                samples.append({
                    "image":              self._get_image(row["image"]),
                    "region_description": self._region_description(human),
                    "bbox":               bbox,
                    "sample_id":          str(row.get("id", row["image"])),
                    "source":             "vrsbench",
                })
            except Exception as e:
                logger.warning(f"VRSBench grounding row skipped: {e}")
                continue

        logger.info(
            f"✅ VRSBench Grounding: {len(samples)} samples ready."
        )
        return samples