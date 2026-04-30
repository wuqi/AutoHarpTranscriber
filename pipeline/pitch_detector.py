from pathlib import Path


def detect_pitch(audio_path: Path, output_dir: Path) -> Path:
    """Run Basic Pitch on the separated audio to produce a MIDI file.

    Returns the path to the generated MIDI file.
    """
    from basic_pitch.internals import ICASSP_2022_MODEL_PATH
    from basic_pitch import predict
    import tensorflow as tf

    model_output, midi_data, note_events = predict(
        str(audio_path),
        model_or_model_path=ICASSP_2022_MODEL_PATH,
    )

    midi_path = output_dir / f"{audio_path.stem}_raw.mid"
    midi_data.write(str(midi_path))

    return midi_path
