# SatQuery AI — Intelligent Satellite Image Analysis System

> **SIH 2026 | Problem Statement SIH26167 | Ministry: ISRO**
>
> An agentic vision-language assistant for analysing single and paired
> remote-sensing images through natural-language queries.

---

## Table of Contents

- [Project Overview](#project-overview)
- [System Architecture](#system-architecture)
- [Models Used](#models-used)
- [Datasets](#datasets)
- [Benchmark Results](#benchmark-results)
- [Fine-tuning - InternVL3](#fine-tuning---internvl3)
- [Evaluation Metrics](#evaluation-metrics)
- [Project Structure](#project-structure)
- [Setup and Installation](#setup-and-installation)
- [Running the Benchmark](#running-the-benchmark)
- [Running the API](#running-the-api)
- [Team](#team)

---

## Project Overview

SatQuery AI is a software-based agentic vision-language assistant that
enables users to analyse single and paired remote-sensing satellite
images through natural-language queries. The system automatically
selects the appropriate specialist model based on the query and input
type, executes the analysis, and returns evidence-grounded responses.

### Supported Tasks

| Task | Description | Model Used |
|------|-------------|------------|
| Visual Question Answering (VQA) | Answer questions about satellite images | EarthMind-4B |
| Image Captioning | Generate scene descriptions | EarthMind-4B |
| Region Grounding | Locate regions via text description | EarthMind-4B |
| Change VQA | Analyse change between two images | InternVL3-1B FT |
| SAR + Optical Fusion | Joint analysis of radar and optical imagery | EarthMind-4B |

### Supported Input Formats

- **Single Image** - GeoTIFF, TIFF, PNG, JPEG
- **Image Pair** - Optical + SAR (cross-modal) or Bi-temporal (change detection)

---

## System Architecture

```
User Query + Image(s)
        |
        v
  React Frontend
        |
        v
  FastAPI Gateway
        |
        v
  LangGraph Agentic Controller
  (Query classification and model routing)
        |
   _____|_____
  |           |
  v           v
EarthMind   InternVL3
  -4B        -1B FT
  (Primary)  (Change VQA)
  |           |
  |___________|
        |
        v
  Response Processor
  (Format + Confidence + Audit Trail)
        |
        v
  User Response
  (Text + Visual Evidence + Execution Summary)
```

### Agentic Controller Logic

The LangGraph-based controller automatically:
1. Classifies the query into task type (VQA, captioning, grounding, change, SAR)
2. Validates input images (format, modality, compatibility)
3. Selects the appropriate model from the registry
4. Executes the inference pipeline
5. Combines outputs and estimates confidence
6. Generates an auditable execution summary

---

## Models Used

### Primary Model - EarthMind-4B

| Property | Value |
|----------|-------|
| Model | EarthMind-4B |
| HuggingFace | [sy1998/EarthMind-4B](https://huggingface.co/sy1998/EarthMind-4B) |
| Paper | [arxiv.org/abs/2506.01667](https://arxiv.org/abs/2506.01667) |
| Parameters | 4 Billion |
| Training | Sentinel-1 (SAR) + Sentinel-2 (Optical) satellite imagery |
| Quantization | 4-bit NF4 for RTX 4060 (8GB VRAM) |

EarthMind-4B is a multi-modal, multi-sensor Vision-Language Model
specifically trained on satellite imagery. It supports both optical
and SAR inputs natively, making it ideal for the cross-modal
analysis required by this project.

### Specialist Model - InternVL3-1B5 Instruct (Fine-tuned)

| Property | Value |
|----------|-------|
| Base Model | OpenGVLab/InternVL3-1B |
| HuggingFace | [OpenGVLab/InternVL3-1B](https://huggingface.co/OpenGVLab/InternVL3-1B) |
| Paper | [arxiv.org/abs/2504.10479](https://arxiv.org/abs/2504.10479) |
| Parameters | 1.5 Billion |
| Fine-tuning | QLoRA on satellite datasets |
| Deployment | Change VQA specialist only |

InternVL3-1B5 was fine-tuned using QLoRA on four satellite datasets.
It achieved 100% soft accuracy on Change VQA tasks and is deployed
as a lightweight specialist for bi-temporal change analysis.

---

## Datasets

### Evaluation Datasets

| Dataset | HuggingFace | Task | Samples |
|---------|-------------|------|---------|
| VRSBench | [xiang709/VRSBench](https://huggingface.co/datasets/xiang709/VRSBench) | VQA + Captioning + Grounding | 200 each |
| RSVQA-HR-2k | [dmarsili/RSVQA-HR-2k](https://huggingface.co/datasets/dmarsili/RSVQA-HR-2k) | VQA | 500 |
| SECOND | [EVER-Z/torchange_second](https://huggingface.co/datasets/EVER-Z/torchange_second) | Change VQA | 200 |
| EarthMind-Bench | [sy1998/EarthMind-Bench](https://huggingface.co/datasets/sy1998/EarthMind-Bench) | Multi-task | 200 |

### Fine-tuning Datasets (InternVL3)

| Dataset | HuggingFace | Purpose |
|---------|-------------|---------|
| VRSBench | [xiang709/VRSBench](https://huggingface.co/datasets/xiang709/VRSBench) | VQA + Captioning + Grounding |
| SECOND | [EVER-Z/torchange_second](https://huggingface.co/datasets/EVER-Z/torchange_second) | Change VQA training |
| BigEarthNet.txt | [BIFOLD-BigEarthNetv2-0/BigEarthNet.txt](https://huggingface.co/datasets/BIFOLD-BigEarthNetv2-0/BigEarthNet.txt) | LULC domain knowledge |
| RSVQA-LR-2k | [dmarsili/RSVQA-LR-2k](https://huggingface.co/datasets/dmarsili/RSVQA-LR-2k) | Count and Area VQA |

---

## Benchmark Results

### EarthMind-4B Baseline (Primary Model)

| Task | Metric | Score |
|------|--------|-------|
| VRSBench VQA | Soft Accuracy | 72.0% |
| VRSBench VQA | SBERT Cosine | 0.880 |
| RSVQA VQA | Soft Accuracy | 48.8% |
| RSVQA VQA | SBERT Cosine | 0.719 |
| Captioning | BLEU-4 | 0.0845 |
| Captioning | ROUGE-L | 0.2885 |
| Captioning | METEOR | 0.3123 |
| Captioning | CIDEr | 0.2591 |
| Captioning | SBERT Cosine | 0.7318 |
| Grounding | mIoU | 0.3244 |
| Grounding | Accuracy@50 | 41.0% |
| Change VQA | Soft Accuracy | 99.5% |
| **Recommendation** | | **GO** |

### InternVL3-1B5 FT vs EarthMind-4B

| Metric | EarthMind-4B | InternVL3 FT | Winner |
|--------|-------------|--------------|--------|
| VRS VQA Soft | 72.0% | 29.0% | EarthMind |
| RSVQA VQA Soft | 48.8% | 33.2% | EarthMind |
| Caption BLEU-4 | 0.085 | 0.029 | EarthMind |
| Grounding mIoU | 0.324 | 0.083 | EarthMind |
| Change VQA Soft | 99.5% | 100.0% | InternVL3 FT |

---

## Fine-tuning - InternVL3

Two fine-tuning attempts were made using QLoRA
(Quantized Low-Rank Adaptation).

### Configuration

| Setting | V1 | V2 (Final) |
|---------|-----|------------|
| LoRA Rank | 8 | 4 |
| LoRA Alpha | 32 | 16 |
| LoRA Dropout | 0.1 | 0.3 |
| Learning Rate | 2e-5 | 1e-5 |
| Early Stopping | No | Yes (patience=3) |
| Validation Split | No | Yes (10%) |
| Replay Buffer | No | Yes (20%) |
| Best Checkpoint | Step 1248 (overfit) | Step 1200 (Val=0.0287) |

### V2 Training Loss Curve

```
Step  100: Train=8.32  Val=8.10
Step  300: Train=0.47  Val=0.43
Step  500: Train=0.01  Val=0.05
Step  700: Train=0.03  Val=0.03
Step  900: Train=0.00  Val=0.029  <- Best checkpoint
Step 1200: Train=0.00  Val=0.028  <- Final best saved
Step 1404: Training complete
```

### Fine-tuning Conclusion

InternVL3-1B5 experienced catastrophic forgetting during fine-tuning
where satellite domain learning overwrote baseline VQA capabilities.
The model is deployed as a specialist for Change VQA only where it
achieved 100% performance. EarthMind-4B remains the primary model
for all other tasks.

---

## Evaluation Metrics

| Metric | Task | Measures |
|--------|------|----------|
| Exact Match Accuracy | VQA | Exact string match after normalization |
| Soft Accuracy | VQA | Token overlap between prediction and GT |
| Numeric Accuracy | RSVQA | Number extraction and matching |
| SBERT Cosine | VQA + Captioning | Semantic similarity via Sentence-BERT |
| BLEU-4 | Captioning | 4-gram precision match |
| ROUGE-L | Captioning | Longest common subsequence |
| METEOR | Captioning | Synonym-aware unigram match |
| CIDEr | Captioning | TF-IDF weighted domain keyword consensus |
| mIoU | Grounding | Mean Intersection over Union of bounding boxes |
| Accuracy@50 | Grounding | Percentage of samples with IoU >= 0.50 |
| Parse Success | Grounding | Percentage of valid bbox format outputs |

---

## Project Structure

```
satquery-benchmark/
|
|-- config.py                        Central configuration
|-- run_benchmark.py                 Main benchmark entry point
|-- run_benchmark_internvl3.py       InternVL3 benchmark runner
|-- requirements.txt                 Python dependencies
|-- README.md                        This file
|
|-- models/
|   |-- earthmind_runner.py          EarthMind-4B inference wrapper
|   |-- internvl3_runner.py          InternVL3 inference wrapper
|   |-- earthmind/                   EarthMind-4B weights (not in Git)
|   |-- internvl3_finetuned_v2/      Fine-tuned InternVL3 (not in Git)
|
|-- datasets/
|   |-- vrsbench_loader.py           VRSBench dataset loader
|   |-- rsvqa_loader.py              RSVQA-HR-2k dataset loader
|   |-- cdvqa_loader.py              SECOND dataset loader
|
|-- benchmarks/
|   |-- vqa_benchmark.py             VQA evaluation pipeline
|   |-- captioning_benchmark.py      Captioning evaluation pipeline
|   |-- grounding_benchmark.py       Grounding evaluation pipeline
|   |-- change_vqa_benchmark.py      Change VQA evaluation pipeline
|
|-- metrics/
|   |-- accuracy.py                  Exact and soft match accuracy
|   |-- bleu.py                      BLEU-4 score
|   |-- rouge.py                     ROUGE-L score
|   |-- miou.py                      mIoU and accuracy thresholds
|   |-- meteor.py                    METEOR score
|   |-- cider.py                     CIDEr score
|   |-- sbert_cosine.py              SBERT cosine similarity
|   |-- numeric_match.py             Numeric extraction accuracy
|
|-- reports/
|   |-- report_generator.py          Excel and JSON report generator
|   |-- results/                     Benchmark result JSONs (not in Git)
|
|-- api/
|   |-- endpoint.py                  FastAPI inference endpoint
|
|-- raw_datasets/                    Downloaded datasets (not in Git)
|-- data/                            Generated training data (not in Git)
|-- .venv/                           Virtual environment (not in Git)
```

---

## Setup and Installation

### Requirements

- Python 3.10+
- CUDA-compatible GPU (RTX 4060 8GB or better)
- 16GB RAM minimum

### Installation

```bash
# Create virtual environment
python -m venv .venv

# Activate (Windows)
.venv\Scripts\activate

# Activate (Linux/Mac)
source .venv/bin/activate

# Install dependencies
pip install -r requirements.txt

# Download NLTK data
python -c "import nltk; nltk.download('punkt'); nltk.download('wordnet')"
```

### Download Models

```bash
# EarthMind-4B
huggingface-cli download sy1998/EarthMind-4B \
    --repo-type model \
    --local-dir ./models/earthmind

# InternVL3-1B (for fine-tuning)
huggingface-cli download OpenGVLab/InternVL3-1B \
    --repo-type model \
    --local-dir ./models/internvl3_base
```

### Download Datasets

```bash
# Set HF cache
set HF_HOME=D:\hf_cache

# VRSBench
huggingface-cli download xiang709/VRSBench \
    --repo-type dataset --local-dir ./raw_datasets/vrsbench

# RSVQA-HR-2k
huggingface-cli download dmarsili/RSVQA-HR-2k \
    --repo-type dataset --local-dir ./raw_datasets/rsvqa

# SECOND
huggingface-cli download EVER-Z/torchange_second \
    --repo-type dataset --local-dir ./raw_datasets/second

# EarthMind-Bench
huggingface-cli download sy1998/EarthMind-Bench \
    --repo-type dataset --local-dir ./raw_datasets/earthmind_bench
```

---

## Running the Benchmark

### Quick Test (10 samples)

```powershell
$env:PYTHONIOENCODING="utf-8"
$env:HF_HOME="D:\hf_cache"
& ".\.venv\Scripts\python.exe" run_benchmark.py --samples 10
```

### Full Benchmark - EarthMind

```powershell
$env:PYTHONIOENCODING="utf-8"
$env:HF_HOME="D:\hf_cache"
& ".\.venv\Scripts\python.exe" run_benchmark.py
```

### Full Benchmark - InternVL3 FT

```powershell
$env:PYTHONIOENCODING="utf-8"
$env:HF_HOME="D:\hf_cache"
& ".\.venv\Scripts\python.exe" run_benchmark_internvl3.py
```

### Specific Tasks Only

```powershell
# VQA and Captioning only
& ".\.venv\Scripts\python.exe" run_benchmark.py --tasks vqa captioning

# Grounding and Change VQA only
& ".\.venv\Scripts\python.exe" run_benchmark.py --tasks grounding change_vqa
```

### Results Location

```
reports/results/
|-- vqa_vrsbench_vqa.json
|-- vqa_rsvqa_vqa.json
|-- captioning_vrsbench_captioning.json
|-- grounding_vrsbench_grounding.json
|-- change_vqa_cdvqa.json
|-- baseline_report.json      <- Share this with team
|-- baseline_report.xlsx      <- Human readable Excel
```

---

## Running the API

### Start FastAPI Server

```powershell
$env:PYTHONIOENCODING="utf-8"
$env:HF_HOME="D:\hf_cache"
& ".\.venv\Scripts\python.exe" -m uvicorn api.endpoint:app \
    --host 0.0.0.0 --port 8001
```

### API Endpoints

| Endpoint | Method | Description |
|----------|--------|-------------|
| /api/v1/health | GET | Health check |
| /api/v1/status | GET | Model status and VRAM usage |
| /api/v1/inference | POST | Main inference (auto task detection) |
| /api/v1/inference/vqa | POST | VQA only |
| /api/v1/inference/caption | POST | Captioning only |
| /api/v1/inference/ground | POST | Grounding only |
| /api/v1/inference/change | POST | Change VQA (2 images) |

### API Documentation

After starting the server, visit:
`http://localhost:8001/docs`

---

## Team

| Name | Role |
|------|------|
| Karan Dalal | Baseline Benchmarking Lead |
| Dhruv | Metric Pipeline and Grounding Improvements |
| Raja | Fine-tuning Lead (InternVL3 + EarthMind) |
| Nishika / Shrishti | Agentic Orchestrator (LangGraph) |
| Fullstack Member | React Frontend + FastAPI Integration |

---

## References

1. EarthMind Paper - arxiv.org/abs/2506.01667
2. InternVL3 Paper - arxiv.org/abs/2504.10479
3. BigEarthNet.txt Paper - arxiv.org/abs/2501.12911
4. VRSBench Paper - github.com/lx709/VRSBench
5. SECOND Dataset - github.com/ggsDing/SECOND

---

*SatQuery AI - SIH 2026 - Team SatQuery*
