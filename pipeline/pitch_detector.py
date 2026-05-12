from pathlib import Path


def detect_pitch(audio_path: Path) -> Path:
    """Run Basic Pitch on the separated audio to produce a MIDI file.

    Returns the path to the generated MIDI file.
    The raw MIDI is written next to the separated audio (not in the user's directory).
    """
    from basic_pitch.internals import ICASSP_2022_MODEL_PATH
    from basic_pitch import predict

    model_output, midi_data, note_events = predict(
        str(audio_path),
        model_or_model_path=ICASSP_2022_MODEL_PATH,
    )

    midi_path = audio_path.parent / f"{audio_path.stem}_raw.mid"
    midi_data.write(str(midi_path))

    return midi_path
