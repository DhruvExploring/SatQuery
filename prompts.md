# Prompts & Dataset Patterns Reference — `satquery-benchmark`

This document details all prompt templates, internal system instructions, formatting rules, question types, and answer patterns used across datasets and model inference inside [models/earthmind_runner.py](file:///c:/Users/karan/OneDrive/Desktop/satquery-benchmark/models/earthmind_runner.py).

---

## 📋 Summary of Model Inference Prompts

| Function | Task | Input Modality | Prompt / Template | Purpose |
| :--- | :--- | :--- | :--- | :--- |
| `infer()` | Core Base Inference | Single or Paired Images + Query | `f"<image>{question}"` | Base multi-modal wrapper token required by EarthMind's `predict_forward()` |
| `infer_vqa()` | Visual Question Answering | Single Optical / Aerial Image | Passes query directly to `infer()` with `<image>{question}` | Answers direct user queries (presence, counting, object identification) |
| `infer_captioning()` | Scene Captioning | Single Satellite Image | `"Describe the land cover, major objects, and environmental context visible in this satellite image."` | Directs model to generate full environmental & terrain scene description |
| `infer_grounding()` | Object Grounding / Localization | Single Satellite Image | `f"Locate '{region_description}' in this satellite image. Return ONLY 4 numbers as bounding box in this exact format: [x1, y1, x2, y2] where all values are between 0.0 and 1.0. Do not write anything else. Example output: [0.2, 0.3, 0.6, 0.8]"` | Strict few-shot formatting prompt forcing model to output only normalized bounding boxes |
| `infer_change_vqa()` | Bi-temporal Change Detection | Image Pair ($T_1$ Before + $T_2$ After) | Passes change query to `infer()` with `video=[image, image2]` | Multi-image comparative reasoning for detecting differences between two dates |
| `infer_sar_optical()` | Cross-Modal Fusion | Optical RGB + SAR Image | `f"You are analyzing a co-registered optical and SAR satellite image pair of the same geographic area. Use both images together to answer: {question}"` | Grounds optical and SAR characteristics simultaneously for cross-sensor analysis |
| `_build_prompt()` (Single) | Standardized Persona Prompt | Single Satellite Image | `f"You are an expert Earth Observation analyst. You are given a satellite image. Question: {question} Provide a concise and accurate answer."` | System persona prompt providing domain grounding for general VQA |
| `_build_prompt()` (Paired) | Standardized Persona Prompt | Co-registered Image Pair | `f"You are an expert Earth Observation analyst. You are given two co-registered satellite images. Question: {question} Provide a concise and accurate answer."` | System persona prompt providing domain grounding for paired satellite images |

---

## 📊 Dataset Question Types & Answer Patterns

### 1. RSVQA-HR-2k (`dmarsili/RSVQA-HR-2k`)
The RSVQA dataset evaluates fine-grained high-resolution aerial imagery understanding across 4 distinct reasoning categories:

| Question Type | Answer Pattern | Example Question | Target Output Type |
| :--- | :--- | :--- | :--- |
| **Comparison** | Yes or No | *"Are there more roads than buildings?"* | Binary (`yes` / `no`) |
| **Presence** | Yes or No | *"Is there a water area in the image?"* | Binary (`yes` / `no`) |
| **Count** | Whole number (e.g. 3, 7, 12) | *"How many buildings are visible?"* | Integer count (`^\d+$`) |
| **Area** | Number + m² (e.g. 495m2, 0m2) | *"What area do the roads cover?"* | Spatial metric (`^\d+m2$`) |
| **Total** | **Mixed** | **-** | **All patterns combined** |

---

### 2. VRSBench (`xiang709/VRSBench`)
| Split Tag | Task | Prompt Format | Expected Model Output |
| :--- | :--- | :--- | :--- |
| `[vqa]` | Visual QA | `<image>[vqa] {question}` | Direct concise answer (e.g. `"airport"`, `"industrial area"`) |
| `[caption]` | Scene Captioning | `<image>[caption]` | Multi-sentence description of terrain, land use, and objects |
| `[refer]` | Region Grounding | `<image>[refer] Locate <p>{region_description}</p>` | Normalized Bounding Box `[x1, y1, x2, y2]` |

---

### 3. SECOND / CDVQA (`EVER-Z/torchange_second`)
| Task | Modality | Prompt Format | Expected Model Output |
| :--- | :--- | :--- | :--- |
| Change Detection VQA | $T_1$ (Before) + $T_2$ (After) | `f"<image><image> Has any land cover changed between these two images?"` | Binary `yes` / `no` + change class identification |

---

## 🔍 Detailed Breakdown by Function

### 1. Base Multi-Modal Token Wrapper (`infer`)
- **Code Location**: [models/earthmind_runner.py#L209](file:///c:/Users/karan/OneDrive/Desktop/satquery-benchmark/models/earthmind_runner.py#L209)
- **Prompt**:
  ```python
  prompt = f"<image>{question}"
  ```
- **Context & Reason**: EarthMind (`Sa2VAChatModel`) uses special `<image>` and `<IMG_CONTEXT>` tokens to insert visual token embeddings before text tokens inside its causal attention mechanism.

---

### 2. Scene Captioning Prompt (`infer_captioning`)
- **Code Location**: [models/earthmind_runner.py#L264-L267](file:///c:/Users/karan/OneDrive/Desktop/satquery-benchmark/models/earthmind_runner.py#L264-L267)
- **Prompt**:
  ```text
  Describe the land cover, major objects, and environmental context visible in this satellite image.
  ```
- **Used by**: `benchmarks/captioning_benchmark.py` (VRSBench captioning split)
- **Goal**: Guides EarthMind to cover terrain types (e.g., dense forest, urban, agricultural), artificial infrastructure, and geographic setting.

---

### 3. Text-Guided Region Grounding Prompt (`infer_grounding`)
- **Code Location**: [models/earthmind_runner.py#L282-L288](file:///c:/Users/karan/OneDrive/Desktop/satquery-benchmark/models/earthmind_runner.py#L282-L288)
- **Prompt**:
  ```text
  Locate '{region_description}' in this satellite image. Return ONLY 4 numbers as bounding box in this exact format: [x1, y1, x2, y2] where all values are between 0.0 and 1.0. Do not write anything else. Example output: [0.2, 0.3, 0.6, 0.8]
  ```
- **Used by**: `benchmarks/grounding_benchmark.py` (VRSBench grounding split)
- **Goal**: Eliminates conversational filler text and enforces raw JSON-like bounding box coordinates `[x1, y1, x2, y2]` to maximize parsing success and mIoU score accuracy.

---

### 4. Cross-Modal SAR + Optical Prompt (`infer_sar_optical`)
- **Code Location**: [models/earthmind_runner.py#L318-L322](file:///c:/Users/karan/OneDrive/Desktop/satquery-benchmark/models/earthmind_runner.py#L318-L322)
- **Prompt**:
  ```text
  You are analyzing a co-registered optical and SAR satellite image pair of the same geographic area. Use both images together to answer: {question}
  ```
- **Used by**: SIH cross-modal reasoning demo / API endpoints
- **Goal**: Informs the model that two distinct sensor representations of the exact same geographical extent are provided, enabling complementary feature extraction (e.g., surface texture via SAR + spectral features via Optical).

---

### 5. Domain Expert Persona Prompt (`_build_prompt`)
- **Code Location**: [models/earthmind_runner.py#L333-L346](file:///c:/Users/karan/OneDrive/Desktop/satquery-benchmark/models/earthmind_runner.py#L333-L346)
- **Prompts**:
  - **Single Image (`paired=False`)**:
    ```text
    You are an expert Earth Observation analyst. You are given a satellite image. Question: {question} Provide a concise and accurate answer.
    ```
  - **Paired Images (`paired=True`)**:
    ```text
    You are an expert Earth Observation analyst. You are given two co-registered satellite images. Question: {question} Provide a concise and accurate answer.
    ```
- **Goal**: System persona framing designed to enforce direct, professional, concise answers and reduce hallucination.

---

## 🧹 Post-Processing & Special Tokens Stripped

In all inference methods, model outputs undergo automated token cleanup before returning:
- **Cleaned Tokens**: `<|end|>`, `<|endoftext|>`, `<|im_end|>`
- **Code Reference**: [models/earthmind_runner.py#L230-L232](file:///c:/Users/karan/OneDrive/Desktop/satquery-benchmark/models/earthmind_runner.py#L230-L232)
