from pathlib import Path
from typing import Optional

from .models import StemChoice


def separate_source(
    audio_path: Path,
    output_dir: Optional[Path] = None,
    stem_choice: StemChoice = StemChoice.AUTO,
) -> Path:
    """Separate the main melody track using Demucs.

    Returns the path to the chosen stem (vocals or other).
    With AUTO, measures RMS energy of vocals; if too quiet, falls back to other.
    """
    import demucs.api
    import soundfile as sf
    import numpy as np

    if output_dir is None:
        output_dir = audio_path.parent / "demucs_output"

    separator = demucs.api.Separator(model="htdemucs")
    _, separated = separator.separate_audio_file(str(audio_path))

    stem_dir = output_dir / "htdemucs" / audio_path.stem
    vocals_path = stem_dir / "vocals.wav"
    other_path = stem_dir / "other.wav"

    if stem_choice == StemChoice.VOCALS:
        if vocals_path.exists():
            return vocals_path
        raise FileNotFoundError(f"Vocals stem not found: {vocals_path}")

    if stem_choice == StemChoice.OTHER:
        if other_path.exists():
            return other_path
        raise FileNotFoundError(f"Other stem not found: {other_path}")

    # AUTO: measure vocals energy, decide
    if not vocals_path.exists():
        return other_path if other_path.exists() else _raise_not_found(stem_dir)

    # Check RMS of vocals stem
    try:
        samples, sr = sf.read(str(vocals_path))
        if samples.ndim > 1:
            samples = samples.mean(axis=1)
        rms = float(np.sqrt(np.mean(samples ** 2)))
    except Exception:
        rms = 0.0

    # If vocals are too quiet (< 1% of max amplitude), use other instead
    if rms < 0.005:
        if other_path.exists():
            return other_path

    return vocals_path


def _raise_not_found(stem_dir: Path) -> None:
    raise FileNotFoundError(f"Demucs did not produce output in {stem_dir}")
