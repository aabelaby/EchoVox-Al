# EchoVox-AI

**Lip Reading + Voice Cloning Web Application**

EchoVox is a Flask-based web app that predicts spoken sentences from video (lip reading) and clones voices using XTTS-v2. Upload a video, get a sentence prediction, then generate speech in a cloned voice.

## Features

- **Lip Reading** — Predicts sentences from mouth movements using a custom neural network + MediaPipe face landmarks
- **Voice Cloning** — Zero-shot voice cloning with Coqui XTTS-v2 (multi-language support)
- **Video Generation** — Combines original video with cloned voice audio
- **Web Interface** — Modern UI with real-time progress, system health monitoring, and download support

## Prerequisites

- **Python 3.9 – 3.13** (tested on 3.13)
- **Anaconda / Miniconda** (recommended) or any Python environment
- **~2 GB disk space** for XTTS-v2 model (auto-downloads on first use)

## Setup

### 1. Clone the repository

```bash
git clone https://github.com/aabelaby/EchoVox-Al.git
cd EchoVox-Al
```

### 2. Install dependencies

**Option A — pip (recommended):**
```bash
pip install -r requirements_flask.txt
```

**Option B — CPU-only PyTorch (saves disk space):**
```bash
pip install torch torchaudio --index-url https://download.pytorch.org/whl/cpu
pip install -r requirements_flask.txt
```

### 3. Add model checkpoints

The trained lip-reading model checkpoints are **not included** in the repo (too large for GitHub).

Copy your trained model files into the `checkpoints/` folder:
```
checkpoints/
  best_model.pt      (or final_model.pt)
  training_history.csv
```

> If you need to train a model from scratch, run: `python lip_reading_train.py`

### 4. Run the app

**Windows — double-click:**
```
start_webapp.bat
```

**Any OS — terminal:**
```bash
python app.py
```

Then open **http://localhost:5000** in your browser.

## How It Works

1. **Upload** a video file (MP4, AVI, MOV, MKV, WebM)
2. The app extracts mouth frames using MediaPipe face landmarks
3. A trained neural network predicts the spoken sentence
4. (Optional) Upload reference audio to clone the speaker's voice
5. XTTS-v2 generates speech in the cloned voice
6. Download the audio or combined video+audio output

## Project Structure

```
app.py                    # Flask web server (main entry point)
lip_reading_train.py      # Lip reading model + training pipeline
voice_cloning_engine.py   # XTTS-v2 voice cloning with patches
start_webapp.bat          # Windows launcher
requirements_flask.txt    # Python dependencies
templates/index.html      # Web UI
static/                   # CSS + JS assets
checkpoints/              # Model weights (not in repo)
```

## Troubleshooting

| Error | Fix |
|-------|-----|
| `No module named 'torch'` | `pip install torch torchaudio` |
| `No module named 'coqpit'` | `pip install coqui-tts` |
| `isin_mps_friendly` import error | `pip install "transformers>=4.43,<5"` |
| `TorchCodec` / FFmpeg error | Already patched in `voice_cloning_engine.py` — no action needed |
| `OMP: Error #15` (OpenMP) | Already patched in `app.py` — no action needed |
| Model checkpoint not found | Place `best_model.pt` in `checkpoints/` folder |

## Tech Stack

- **Backend:** Flask, PyTorch, MediaPipe, Coqui TTS (XTTS-v2)
- **Frontend:** HTML/CSS/JS
- **ML:** Custom lip-reading CNN/RNN, XTTS-v2 zero-shot voice cloning