from pathlib import Path
from .models import NoteEvent


def write_midi(notes: list[NoteEvent], output_path: Path, tempo: int, time_sig: str):
    """Write a single-track MIDI file (type 0) from note events.

    The output MIDI contains one track with the melody on channel 1.
    """
    import mido

    mid = mido.MidiFile(ticks_per_beat=480)
    track = mido.MidiTrack()
    mid.tracks.append(track)

    # Tempo
    tempo_us = mido.bpm2tempo(tempo)
    track.append(mido.MetaMessage("set_tempo", tempo=tempo_us, time=0))

    # Time signature
    parts = time_sig.split("/")
    num = int(parts[0])
    den = int(parts[1]) if len(parts) > 1 else 4
    track.append(mido.MetaMessage("time_signature", numerator=num, denominator=den, time=0))

    # Program change: Acoustic Grand Piano
    track.append(mido.Message("program_change", channel=0, program=0, time=0))

    # Sort notes by start time
    sorted_notes = sorted(notes, key=lambda n: n.start_time)

    # Build timeline of events
    events: list[tuple[float, str, int, int]] = []
    # (time_sec, type, pitch, velocity)

    for note in sorted_notes:
        events.append((note.start_time, "on", note.pitch, note.velocity))
        events.append((note.end_time, "off", note.pitch, 0))

    events.sort(key=lambda e: e[0])

    # Convert to MIDI messages with delta ticks
    last_time = 0.0
    for time_sec, etype, pitch, velocity in events:
        delta_ticks = int((time_sec - last_time) * 480 * tempo / 60)
        delta_ticks = max(0, delta_ticks)

        if etype == "on":
            track.append(mido.Message("note_on", channel=0, note=pitch,
                         velocity=velocity, time=delta_ticks))
        else:
            track.append(mido.Message("note_off", channel=0, note=pitch,
                         velocity=0, time=delta_ticks))
        last_time = time_sec

    # End of track
    track.append(mido.MetaMessage("end_of_track", time=0))

    mid.save(str(output_path))
