"""
voice_cloning_engine.py — Voice Cloning Engine for Flask Integration
==================================================================
Extracted and adapted from voice_clone.py for use with Flask web application.
Includes all necessary patches and the VoiceCloningEngine class.
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

# ════════════════════════════════════════════════════════════════════════════
# PATCH 2.5 — force torchaudio to use soundfile instead of torchcodec
# torchaudio ≥ 2.11 defaults to torchcodec which requires FFmpeg shared libs.
# Redirect torchaudio.load / .save to soundfile-based implementation.
# ════════════════════════════════════════════════════════════════════════════
try:
    import torchaudio as _ta
    import soundfile as _sf_patch
    import numpy as _np_patch

    _original_ta_load = _ta.load

    def _patched_ta_load(uri, *args, **kwargs):
        """Load audio via soundfile, returning (waveform_tensor, sample_rate)."""
        try:
            data, sr = _sf_patch.read(uri, dtype="float32")
            waveform = torch.from_numpy(data)
            if waveform.ndim == 1:
                waveform = waveform.unsqueeze(0)        # (samples,) → (1, samples)
            else:
                waveform = waveform.T                    # (samples, ch) → (ch, samples)
            return waveform, sr
        except Exception:
            return _original_ta_load(uri, *args, **kwargs)

    _ta.load = _patched_ta_load
except Exception:
    pass

# Allowlist the globals PyTorch complains about (belt-and-suspenders)
try:
    from TTS.tts.configs.xtts_config import XttsConfig
    torch.serialization.add_safe_globals([XttsConfig])
except Exception:
    pass

# Replace load_fsspec with a version that forces weights_only=False
# (only needed for older TTS versions that have TTS.utils.io)
try:
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
except ImportError:
    # Newer TTS versions (coqui-tts >= 0.25) removed TTS.utils.io
    pass


# ════════════════════════════════════════════════════════════════════════════
# Normal imports and Voice Cloning Engine
# ════════════════════════════════════════════════════════════════════════════
import os
import uuid
import shutil
import logging
from pathlib import Path
from typing import Optional
import soundfile as sf

# ── Logging ───────────────────────────────────────────────────────────────────
logger = logging.getLogger(__name__)

# ── Environment & Force CPU ───────────────────────────────────────────────────
os.environ["CUDA_VISIBLE_DEVICES"] = ""
os.environ["COQUI_TOS_AGREED"] = "1"
DEVICE = "cpu"


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
            manager = ModelManager(progress_bar=False)
            result = manager.download_model(self.MODEL_NAME)
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

        model_dir = self._find_model_dir()
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
        """
        Clone a voice and synthesize the given text in that voice.
        
        Args:
            text: Text to synthesize
            reference_audio: Path to reference audio file
            output_path: Path to save output audio
            language: Language code (default: "en")
            speed: Speech speed (default: 1.0)
            
        Returns:
            Path to generated audio file
        """
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

    def get_supported_languages(self):
        """Get list of supported languages"""
        return [
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


# Global instance for Flask app
_voice_engine: Optional[VoiceCloningEngine] = None


def get_voice_engine():
    """Get or create the global voice cloning engine instance"""
    global _voice_engine
    if _voice_engine is None:
        _voice_engine = VoiceCloningEngine()
    return _voice_engine


def cleanup_voice_engine():
    """Cleanup the voice engine (call during app shutdown)"""
    global _voice_engine
    _voice_engine = None


class EchoVoxTTS:
    """
    Wrapper class to maintain compatibility with existing Flask app
    that expects EchoVoxTTS interface
    """
    
    def __init__(self, voice_file=None, api_key=None):
        """
        Initialize TTS with reference voice file
        
        Args:
            voice_file: Path to reference audio file
            api_key: Not used for XTTS, kept for compatibility
        """
        self.engine = get_voice_engine()
        self.reference_audio = voice_file
        
    def synthesize(self, text, output_path=None, play_audio=False):
        """
        Synthesize speech using cloned voice
        
        Args:
            text: Text to synthesize
            output_path: Path to save output (if None, generates temp path)
            play_audio: Whether to play audio (ignored for web app)
            
        Returns:
            Path to generated audio file
        """
        if output_path is None:
            output_path = f"voice_outputs/cloned_voice_{uuid.uuid4().hex}.wav"
            
        # Ensure output directory exists
        Path(output_path).parent.mkdir(exist_ok=True)
        
        return self.engine.clone(
            text=text,
            reference_audio=self.reference_audio,
            output_path=output_path
        )
