from pathlib import Path
from .models import NoteEvent


def parse_midi(midi_path: Path) -> tuple[list[NoteEvent], int, str]:
    """Parse a MIDI file and extract note events, tempo, and time signature.

    Returns (notes, tempo_bpm, time_signature).
    """
    import mido

    mid = mido.MidiFile(str(midi_path))

    # Extract tempo
    tempo = 120
    time_sig = "4/4"
    for track in mid.tracks:
        for msg in track:
            if msg.type == "set_tempo":
                tempo = int(mido.tempo2bpm(msg.tempo))
            if msg.type == "time_signature":
                time_sig = f"{msg.numerator}/{msg.denominator}"

    # Extract notes from all tracks
    notes: list[NoteEvent] = []
    ticks_per_beat = mid.ticks_per_beat

    for track in mid.tracks:
        current_time = 0.0
        active_notes: dict[int, tuple[float, int]] = {}  # pitch -> (start_time, velocity)
        current_tempo = tempo

        for msg in track:
            # Accumulate time before processing the message
            current_time += mido.tick2second(
                msg.time, ticks_per_beat, mido.bpm2tempo(current_tempo)
            )

            if msg.type == "set_tempo":
                current_tempo = int(mido.tempo2bpm(msg.tempo))

            if msg.type == "note_on" and msg.velocity > 0:
                active_notes[msg.note] = (current_time, msg.velocity)
            elif msg.type == "note_off" or (msg.type == "note_on" and msg.velocity == 0):
                if msg.note in active_notes:
                    start_time, velocity = active_notes.pop(msg.note)
                    duration = current_time - start_time
                    if duration > 0.01:  # filter out clicks
                        notes.append(NoteEvent(
                            pitch=msg.note,
                            start_time=start_time,
                            duration=duration,
                            velocity=velocity,
                        ))

    # Sort by start time
    notes.sort(key=lambda n: n.start_time)

    return notes, tempo, time_sig
