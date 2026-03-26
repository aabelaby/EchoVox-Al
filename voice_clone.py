"""
voice_clone_api.py — Single-file Voice Cloning Backend (CPU only)
==================================================================
Patches applied at startup (before any TTS import):
  1. coqpit._deserialize  — fixes `issubclass() arg 1 must be a class`
  2. TTS.utils.io.load_fsspec — fixes PyTorch 2.6 weights_only=True default
  3. torch.serialization safe globals — allowlists XttsConfig

Install:
    pip install fastapi uvicorn[standard] python-multipart soundfile
    pip install torch torchaudio --index-url https://download.pytorch.org/whl/cpu
    pip install TTS

Run:
    python voice_clone_api.py

Docs:
    http://localhost:8000/docs
"""

# ════════════════════════════════════════════════════════════════════════════
# PATCH 1 — fix coqpit _deserialize (issubclass TypeError)
# Must happen before any TTS import.
# ════════════════════════════════════════════════════════════════════════════
import inspect
import typing
import coqpit.coqpit as _coqpit_mod


def _safe_deserialize(value, field_type):
    from coqpit.coqpit import Serializable

    if value is None:
        return value

    origin = getattr(field_type, "__origin__", None)

    if inspect.isclass(field_type):
        if issubclass(field_type, Serializable):
            if isinstance(value, dict):
                return field_type().deserialize(value)
            return value
        if issubclass(field_type, dict):
            return value
        try:
            return field_type(value)
        except Exception:
            return value

    if origin is list:
        args = getattr(field_type, "__args__", (None,))
        inner = args[0] if args else None
        if inner is not None:
            return [_safe_deserialize(v, inner) for v in (value or [])]
        return value

    if origin is dict:
        return value

    if origin is typing.Union:
        for arg in getattr(field_type, "__args__", ()):
            if arg is type(None):
                continue
            try:
                return _safe_deserialize(value, arg)
            except Exception:
                continue
        return value

    return value


_coqpit_mod._deserialize = _safe_deserialize


# ════════════════════════════════════════════════════════════════════════════
# PATCH 2 — fix PyTorch 2.6 weights_only=True breaking TTS checkpoint load
# Patch TTS.utils.io.load_fsspec to always pass weights_only=False.
# ════════════════════════════════════════════════════════════════════════════
import torch

# Allowlist the globals PyTorch complains about (belt-and-suspenders)
try:
    from TTS.tts.configs.xtts_config import XttsConfig
    torch.serialization.add_safe_globals([XttsConfig])
except Exception:
    pass

# Replace load_fsspec with a version that forces weights_only=False
import TTS.utils.io as _tts_io

_original_load_fsspec = _tts_io.load_fsspec


def _patched_load_fsspec(path, map_location=None, cache=False, **kwargs):
    # Force weights_only=False so PyTorch 2.6 loads legacy checkpoints
    kwargs["weights_only"] = False
    return _original_load_fsspec(path, map_location=map_location, cache=cache, **kwargs)


_tts_io.load_fsspec = _patched_load_fsspec

# Also patch the reference inside xtts.py if it imported load_fsspec directly
try:
    import TTS.tts.models.xtts as _xtts_mod
    _xtts_mod.load_fsspec = _patched_load_fsspec
except Exception:
    pass


# ════════════════════════════════════════════════════════════════════════════
# Normal imports
# ════════════════════════════════════════════════════════════════════════════
import os
import uuid
import shutil
import logging
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Optional

import uvicorn
import soundfile as sf
from fastapi import FastAPI, UploadFile, File, Form, HTTPException, BackgroundTasks
from fastapi.responses import FileResponse
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

# ── Logging ───────────────────────────────────────────────────────────────────
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(message)s",
)
logger = logging.getLogger(__name__)

# ── Force CPU ─────────────────────────────────────────────────────────────────
os.environ["CUDA_VISIBLE_DEVICES"] = ""
DEVICE = "cpu"

# ── Directories ───────────────────────────────────────────────────────────────
UPLOAD_DIR = Path("uploads")
OUTPUT_DIR = Path("outputs")
UPLOAD_DIR.mkdir(exist_ok=True)
OUTPUT_DIR.mkdir(exist_ok=True)


# ── Pydantic schemas ──────────────────────────────────────────────────────────

class StatusResponse(BaseModel):
    status: str
    message: str
    device: Optional[str] = None


class CloneResponse(BaseModel):
    audio_id: str
    download_url: str
    message: str


# ── TTS Engine ────────────────────────────────────────────────────────────────

class VoiceCloningEngine:
    """Zero-shot voice cloning — XTTS-v2, CPU only. All patches applied above."""

    MODEL_NAME = "tts_models/multilingual/multi-dataset/xtts_v2"

    def __init__(self):
        logger.info("Loading XTTS-v2 on CPU …")
        self._load_model()
        logger.info("XTTS-v2 ready ✓")

    def _find_model_dir(self) -> Path:
        try:
            from TTS.utils.manage import ModelManager
            manager   = ModelManager(progress_bar=False)
            result    = manager.download_model(self.MODEL_NAME)
            candidate = Path(result[0])
            d = candidate.parent if candidate.is_file() else candidate
            if (d / "config.json").exists():
                return d
        except Exception as e:
            logger.warning(f"ModelManager lookup failed ({e}), scanning cache …")

        import platform
        if platform.system() == "Windows":
            base = Path(os.environ.get("LOCALAPPDATA", "")) / "tts"
        else:
            base = Path.home() / ".local" / "share" / "tts"

        for cfg in base.rglob("config.json"):
            if "xtts_v2" in str(cfg):
                return cfg.parent

        raise FileNotFoundError(
            f"XTTS-v2 model not found under {base}.\n"
            "Pre-download: python -c \"from TTS.api import TTS; "
            "TTS('tts_models/multilingual/multi-dataset/xtts_v2')\""
        )

    def _load_model(self):
        from TTS.tts.configs.xtts_config import XttsConfig
        from TTS.tts.models.xtts import Xtts

        model_dir   = self._find_model_dir()
        config_path = model_dir / "config.json"
        logger.info(f"Model directory : {model_dir}")

        if not config_path.exists():
            raise FileNotFoundError(f"config.json not found in {model_dir}")

        config = XttsConfig()
        config.load_json(str(config_path))          # safe — coqpit patched

        self.model = Xtts.init_from_config(config)
        self.model.load_checkpoint(                 # safe — load_fsspec patched
            config,
            checkpoint_dir=str(model_dir),
            eval=True,
        )
        self.model.to(DEVICE)
        self.config = config
        logger.info("Weights loaded ✓")

    def clone(
        self,
        text: str,
        reference_audio: str,
        output_path: str,
        language: str = "en",
        speed: float = 1.0,
    ) -> str:
        if not os.path.isfile(reference_audio):
            raise FileNotFoundError(f"Reference audio not found: {reference_audio}")

        logger.info(f"Synthesising | lang={language} speed={speed}")

        gpt_cond_latent, speaker_embedding = self.model.get_conditioning_latents(
            audio_path=[reference_audio]
        )

        outputs = self.model.inference(
            text=text,
            language=language,
            gpt_cond_latent=gpt_cond_latent,
            speaker_embedding=speaker_embedding,
            temperature=0.7,
            speed=speed,
        )

        wav_np = torch.tensor(outputs["wav"]).squeeze().cpu().numpy()
        sf.write(output_path, wav_np, samplerate=self.config.audio.output_sample_rate)

        logger.info(f"Saved → {output_path}")
        return output_path


# ── Lifespan ──────────────────────────────────────────────────────────────────

engine: Optional[VoiceCloningEngine] = None


@asynccontextmanager
async def lifespan(app: FastAPI):
    global engine
    logger.info("Startup — loading TTS engine …")
    engine = VoiceCloningEngine()
    yield
    logger.info("Shutdown.")


# ── App ───────────────────────────────────────────────────────────────────────

app = FastAPI(
    title="Voice Cloning API",
    description="Zero-shot voice cloning — Coqui XTTS-v2, CPU mode",
    version="4.0.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ── Helpers ───────────────────────────────────────────────────────────────────

def _save_upload(file: UploadFile, dest: Path) -> Path:
    ext  = Path(file.filename).suffix or ".wav"
    path = dest / f"{uuid.uuid4()}{ext}"
    with path.open("wb") as f:
        shutil.copyfileobj(file.file, f)
    return path


def _cleanup(*paths: Path):
    for p in paths:
        try:
            p.unlink(missing_ok=True)
        except Exception:
            pass


# ── Routes ────────────────────────────────────────────────────────────────────

@app.get("/", response_model=StatusResponse)
def root():
    return StatusResponse(status="ok", message="Voice Cloning API is running", device=DEVICE)


@app.get("/health", response_model=StatusResponse)
def health():
    return StatusResponse(status="ok", message="Healthy — CPU mode", device=DEVICE)


@app.get("/languages")
def supported_languages():
    return {
        "languages": [
            {"code": "en",    "name": "English"},
            {"code": "hi",    "name": "Hindi"},
            {"code": "es",    "name": "Spanish"},
            {"code": "fr",    "name": "French"},
            {"code": "de",    "name": "German"},
            {"code": "it",    "name": "Italian"},
            {"code": "pt",    "name": "Portuguese"},
            {"code": "pl",    "name": "Polish"},
            {"code": "tr",    "name": "Turkish"},
            {"code": "ru",    "name": "Russian"},
            {"code": "nl",    "name": "Dutch"},
            {"code": "cs",    "name": "Czech"},
            {"code": "ar",    "name": "Arabic"},
            {"code": "zh-cn", "name": "Chinese (Simplified)"},
            {"code": "ja",    "name": "Japanese"},
            {"code": "hu",    "name": "Hungarian"},
            {"code": "ko",    "name": "Korean"},
        ]
    }


@app.post("/clone", response_model=CloneResponse)
async def clone_voice(
    background_tasks: BackgroundTasks,
    text: str                  = Form(...,  description="Text to synthesise (max 1000 chars)"),
    reference_audio: UploadFile = File(..., description="Speaker WAV/MP3 reference (6–30 sec)"),
    language: str              = Form("en", description="Language code e.g. en, hi, fr"),
    speed: float               = Form(1.0,  ge=0.5, le=2.0, description="Speed 0.5–2.0"),
):
    """
    Clone a voice and synthesise the given text in that voice.

    - **text**: What to speak — max 1000 characters.
    - **reference_audio**: Clean WAV or MP3 of the target speaker (6–30 sec).
    - **language**: Language of the *text* (not necessarily the reference).
    - **speed**: 1.0 = normal, 0.8 = slower, 1.2 = faster.

    Returns a one-time `/audio/{id}` URL. File is deleted after download.

    > ⚠️ CPU mode: expect 20–60 seconds per request.
    """
    if engine is None:
        raise HTTPException(503, "TTS engine not ready, please retry.")
    if not text.strip():
        raise HTTPException(400, "text cannot be empty.")
    if len(text) > 1000:
        raise HTTPException(400, "text too long — max 1000 characters.")

    fname = reference_audio.filename or ""
    if not fname.lower().endswith((".wav", ".mp3")):
        raise HTTPException(400, "Unsupported file type. Upload WAV or MP3.")

    ref_path    = _save_upload(reference_audio, UPLOAD_DIR)
    audio_id    = str(uuid.uuid4())
    output_path = OUTPUT_DIR / f"{audio_id}.wav"

    try:
        engine.clone(
            text=text,
            reference_audio=str(ref_path),
            output_path=str(output_path),
            language=language,
            speed=speed,
        )
    except Exception as exc:
        _cleanup(ref_path, output_path)
        logger.exception("Clone failed")
        raise HTTPException(500, f"Voice cloning failed: {exc}")

    background_tasks.add_task(_cleanup, ref_path)

    return CloneResponse(
        audio_id=audio_id,
        download_url=f"/audio/{audio_id}",
        message="Voice cloning successful.",
    )


@app.get("/audio/{audio_id}")
def download_audio(audio_id: str, background_tasks: BackgroundTasks):
    """One-time download — file deleted after this request."""
    if not all(c in "0123456789abcdef-" for c in audio_id):
        raise HTTPException(400, "Invalid audio ID.")

    path = OUTPUT_DIR / f"{audio_id}.wav"
    if not path.exists():
        raise HTTPException(404, "Audio not found or already downloaded.")

    background_tasks.add_task(_cleanup, path)
    return FileResponse(str(path), media_type="audio/wav", filename=f"cloned_{audio_id}.wav")


# ── Entry point ───────────────────────────────────────────────────────────────

if __name__ == "__main__":
    uvicorn.run("voice_clone:app", host="0.0.0.0", port=8000, reload=False, workers=1)