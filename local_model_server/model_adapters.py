"""Model adapters for the local VLM server.

InternVL's loading/preprocessing/chat pattern below matches OpenGVLab's published
usage example (verified against the OpenGVLab/InternVL3_5-1B model card — the
default for LOCAL_VLM_MODEL_ID=internvl-1b) and has been stable across the
InternVL model family. Requires transformers>=4.52.1 per that model card.

EarthMind-4B (sy1998/EarthMind-4B) ships its own modeling_earthmind_chat.py built
on the same SA2VA/InternVL lineage, but its Hugging Face model card is empty —
there is no published usage example to verify against. EarthMindAdapter assumes
the same .chat(...) signature as InternVL as a best effort. The first time you
actually run it, confirm the response looks right and adjust generate() below if
the real signature differs.
"""

from __future__ import annotations

import torch
import torchvision.transforms as T
from PIL import Image
from torchvision.transforms.functional import InterpolationMode

IMAGENET_MEAN = (0.485, 0.456, 0.406)
IMAGENET_STD = (0.229, 0.224, 0.225)


def resolve_device_and_dtype(requested: str) -> tuple[str, torch.dtype]:
    requested = (requested or "auto").strip().lower()
    if requested == "auto":
        if torch.cuda.is_available():
            requested = "cuda"
        elif torch.backends.mps.is_available():
            requested = "mps"
        else:
            requested = "cpu"

    if requested == "cuda":
        return "cuda", torch.bfloat16
    if requested == "mps":
        # bfloat16/float16 op coverage on MPS is inconsistent for custom
        # trust_remote_code architectures; float32 trades speed for correctness.
        return "mps", torch.float32
    return "cpu", torch.float32


def _build_transform(input_size: int) -> T.Compose:
    return T.Compose(
        [
            T.Lambda(lambda img: img.convert("RGB") if img.mode != "RGB" else img),
            T.Resize((input_size, input_size), interpolation=InterpolationMode.BICUBIC),
            T.ToTensor(),
            T.Normalize(mean=IMAGENET_MEAN, std=IMAGENET_STD),
        ]
    )


def _find_closest_aspect_ratio(
    aspect_ratio: float,
    target_ratios: list[tuple[int, int]],
    width: int,
    height: int,
    image_size: int,
) -> tuple[int, int]:
    best_ratio_diff = float("inf")
    best_ratio = (1, 1)
    area = width * height
    for ratio in target_ratios:
        target_aspect_ratio = ratio[0] / ratio[1]
        ratio_diff = abs(aspect_ratio - target_aspect_ratio)
        if ratio_diff < best_ratio_diff:
            best_ratio_diff = ratio_diff
            best_ratio = ratio
        elif ratio_diff == best_ratio_diff and area > 0.5 * image_size * image_size * ratio[0] * ratio[1]:
            best_ratio = ratio
    return best_ratio


def _dynamic_preprocess(
    image: Image.Image,
    min_num: int = 1,
    max_num: int = 12,
    image_size: int = 448,
    use_thumbnail: bool = True,
) -> list[Image.Image]:
    orig_width, orig_height = image.size
    aspect_ratio = orig_width / orig_height

    target_ratios = sorted(
        {
            (i, j)
            for n in range(min_num, max_num + 1)
            for i in range(1, n + 1)
            for j in range(1, n + 1)
            if min_num <= i * j <= max_num
        },
        key=lambda x: x[0] * x[1],
    )

    target_aspect_ratio = _find_closest_aspect_ratio(
        aspect_ratio, target_ratios, orig_width, orig_height, image_size
    )
    target_width = image_size * target_aspect_ratio[0]
    target_height = image_size * target_aspect_ratio[1]
    blocks = target_aspect_ratio[0] * target_aspect_ratio[1]

    resized_img = image.resize((target_width, target_height))
    processed_images = []
    columns = target_width // image_size
    for i in range(blocks):
        box = (
            (i % columns) * image_size,
            (i // columns) * image_size,
            ((i % columns) + 1) * image_size,
            ((i // columns) + 1) * image_size,
        )
        processed_images.append(resized_img.crop(box))

    if use_thumbnail and len(processed_images) != 1:
        processed_images.append(image.resize((image_size, image_size)))
    return processed_images


def load_image_tensor(image: Image.Image, input_size: int = 448, max_num: int = 12) -> torch.Tensor:
    transform = _build_transform(input_size)
    tiles = _dynamic_preprocess(image, image_size=input_size, use_thumbnail=True, max_num=max_num)
    return torch.stack([transform(tile) for tile in tiles])


class InternVLAdapter:
    """Loads any InternVL-chat-family model via transformers + trust_remote_code."""

    def __init__(self, repo_id: str, device: str, dtype: torch.dtype) -> None:
        from transformers import AutoModel, AutoTokenizer

        self.device = device
        self.dtype = dtype
        model_kwargs: dict = {"trust_remote_code": True, "low_cpu_mem_usage": True}
        if dtype is not None:
            model_kwargs["torch_dtype"] = dtype
        self.model = AutoModel.from_pretrained(repo_id, **model_kwargs).eval().to(device)
        self.tokenizer = AutoTokenizer.from_pretrained(
            repo_id, trust_remote_code=True, use_fast=False
        )

    def generate(self, image: Image.Image, query: str) -> str:
        pixel_values = load_image_tensor(image).to(self.device)
        if self.dtype is not None:
            pixel_values = pixel_values.to(self.dtype)
        prompt = query if "<image>" in query else f"<image>\n{query}"
        generation_config = {"max_new_tokens": 512, "do_sample": False}
        return self.model.chat(self.tokenizer, pixel_values, prompt, generation_config)


class EarthMindAdapter(InternVLAdapter):
    """Best-effort adapter for sy1998/EarthMind-4B — see module docstring."""
