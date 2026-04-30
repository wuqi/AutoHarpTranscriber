import json
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

from .models import (
    NoteEvent, UserConfig, HarmonicaType, ScoreType, HarmonicaNote, KEYS, NOTE_NAMES,
)

_KNOWLEDGE_DIR = Path(__file__).parent.parent / "knowledge"

# Major scale intervals from tonic (in semitones)
MAJOR_INTERVALS = [0, 2, 4, 5, 7, 9, 11]
JIANPU_NUMBERS = ["1", "2", "3", "4", "5", "6", "7"]

# Standard rhythm quantization targets (in beats)
RHYTHM_TARGETS = [0.25, 0.5, 0.75, 1.0, 1.5, 2.0, 3.0, 4.0]


def _load_mapping(harmonica_type: HarmonicaType, harp_key: str) -> dict[int, HarmonicaNote]:
    """Load and compute harmonica mapping for a given type and key.

    For diatonic, the C mapping is transposed to other keys.
    """
    if harmonica_type == HarmonicaType.DIATONIC:
        path = _KNOWLEDGE_DIR / "diatonic_c.json"
    else:
        path = _KNOWLEDGE_DIR / "chromatic.json"

    with open(path, encoding="utf-8") as f:
        data = json.load(f)

    base_key = data["key"]
    mapping: dict[int, HarmonicaNote] = {}

    base_semitones = {"C": 0, "C#": 1, "D": 2, "D#": 3, "E": 4, "F": 5,
                      "F#": 6, "G": 7, "G#": 8, "A": 9, "A#": 10, "B": 11}
    offset = (base_semitones.get(harp_key, 0) - base_semitones.get(base_key, 0)) % 12

    for midi_str, entry in data["mapping"].items():
        midi = int(midi_str)
        if harmonica_type == HarmonicaType.DIATONIC:
            mapping[midi + offset] = HarmonicaNote(
                hole=entry["hole"],
                action=entry["action"],
                technique=entry.get("technique"),
            )
        else:
            mapping[midi] = HarmonicaNote(
                hole=entry["hole"],
                action=entry["action"],
                technique=("slide" if entry.get("slide") else None),
            )

    return mapping


def midi_to_jianpu(pitch: int, tonic_midi: int) -> str:
    """Convert a MIDI pitch to jianpu-spec note representation.

    Uses movable-do (首调) system relative to the tonic.
    """
    pc = pitch % 12
    tonic_pc = tonic_midi % 12

    # Find interval from tonic in semitones
    semitone_interval = (pc - tonic_pc) % 12

    # Try to find in major scale
    try:
        idx = MAJOR_INTERVALS.index(semitone_interval)
        base = JIANPU_NUMBERS[idx]
    except ValueError:
        # Non-diatonic: find nearest and add accidental
        # jianpu-spec: #/$ comes AFTER the note number (unlike JE format)
        prev_interval = (semitone_interval - 1) % 12
        if prev_interval in MAJOR_INTERVALS:
            idx = MAJOR_INTERVALS.index(prev_interval)
            base = f"{JIANPU_NUMBERS[idx]}#"
        else:
            next_interval = (semitone_interval + 1) % 12
            if next_interval in MAJOR_INTERVALS:
                idx = MAJOR_INTERVALS.index(next_interval)
                base = f"{JIANPU_NUMBERS[idx]}$"
            else:
                base = f"{JIANPU_NUMBERS[(semitone_interval - 1) % 7]}#"

    # Octave markers
    if pitch >= tonic_midi:
        high = (pitch - tonic_midi) // 12
        markers = "'" * high
    else:
        low = (tonic_midi - 1 - pitch) // 12 + 1
        markers = "," * low

    return f"{base}{markers}"


def _quantize_beats(beats: float) -> float:
    """Quantize beat duration to nearest standard rhythm value."""
    return min(RHYTHM_TARGETS, key=lambda t: abs(t - beats))


def _duration_suffix(beats: float) -> str:
    """Convert beat count to jianpu-spec duration suffix."""
    beats = _quantize_beats(beats)
    eps = 0.05

    if abs(beats - 0.25) < eps:
        return "//"
    elif abs(beats - 0.5) < eps:
        return "/"
    elif abs(beats - 0.75) < eps:
        return "/."
    elif abs(beats - 1.0) < eps:
        return ""
    elif abs(beats - 1.5) < eps:
        return "."
    elif abs(beats - 2.0) < eps:
        return "-"
    elif abs(beats - 3.0) < eps:
        return "--"
    elif abs(beats - 4.0) < eps:
        return "---"
    else:
        return ""


def generate_jianpu_score(
    notes: list[NoteEvent],
    key: str,
    tempo: int,
    time_sig: str,
) -> list[str]:
    """Generate jianpu-spec Q lines from notes.

    Returns a list of Q: lines with bar lines inserted.
    """
    if not notes:
        return ["Q: | 0 - - - |"]

    # Determine tonic for movable-do
    key_name = key.rstrip("m")
    tonic_semitones = {"C": 0, "C#": 1, "D": 2, "D#": 3, "E": 4, "F": 5,
                       "F#": 6, "G": 7, "G#": 8, "A": 9, "A#": 10, "B": 11}
    tonic_pc = tonic_semitones.get(key_name, 0)
    tonic_midi = 60 + tonic_pc  # Tonic in octave 4

    beat_duration = 60.0 / tempo

    # Parse time signature
    parts = time_sig.split("/")
    beats_per_bar = int(parts[0]) if len(parts) == 2 else 4

    lines: list[str] = []
    current_line = "Q: | "
    bar_beats = 0.0

    for note in notes:
        note_beats = note.duration / beat_duration
        jianpu_note = midi_to_jianpu(note.pitch, tonic_midi)
        dur_suffix = _duration_suffix(note_beats)
        token = f"{jianpu_note}{dur_suffix}"

        # Check if we need a new bar
        if bar_beats + note_beats > beats_per_bar + 0.1:
            # Close previous bar and start new one
            current_line += " | "
            bar_beats = 0.0

        current_line += f"{token} "
        bar_beats += note_beats

        # Line wrapping at ~80 chars
        if len(current_line) > 70:
            current_line += "|"
            lines.append(current_line)
            current_line = "Q: | "
            bar_beats = 0.0

    # Close remaining bar
    if current_line.strip() != "Q: |":
        if not current_line.rstrip().endswith("|"):
            current_line += "|"
        lines.append(current_line)

    if not lines:
        return ["Q: | 0 - - - |"]

    return lines


def generate_harp_tab(
    notes: list[NoteEvent],
    harmonica_type: HarmonicaType,
    harp_key: str,
    tempo: int,
    time_sig: str,
) -> tuple[list[str], list[NoteEvent]]:
    """Generate harmonica tablature Q lines.

    Returns (tab_lines, unplayable_notes).
    """
    mapping = _load_mapping(harmonica_type, harp_key)
    beat_duration = 60.0 / tempo
    parts = time_sig.split("/")
    beats_per_bar = int(parts[0]) if len(parts) == 2 else 4

    lines: list[str] = []
    unplayable: list[NoteEvent] = []
    current_line = "Q: | "
    bar_beats = 0.0

    for note in notes:
        note_beats = note.duration / beat_duration

        entry = mapping.get(note.pitch)
        if entry is None:
            unplayable.append(note)
            token = "?"
        else:
            token = _format_harp_note(entry)

        dur_suffix = _duration_suffix(note_beats)
        token = f"{token}{dur_suffix}"

        if bar_beats + note_beats > beats_per_bar + 0.1:
            current_line += " | "
            bar_beats = 0.0

        current_line += f"{token} "
        bar_beats += note_beats

        if len(current_line) > 70:
            current_line += "|"
            lines.append(current_line)
            current_line = "Q: | "
            bar_beats = 0.0

    if current_line.strip() != "Q: |":
        if not current_line.rstrip().endswith("|"):
            current_line += "|"
        lines.append(current_line)

    if not lines:
        return ["Q: | ? - - - |"], unplayable

    return lines, unplayable


def _format_harp_note(entry: HarmonicaNote) -> str:
    """Format a HarmonicaNote into tab notation."""
    hole = entry.hole
    action = entry.action
    technique = entry.technique

    if technique is None:
        return f"{hole}{'+' if action == 'blow' else '-'}"

    if technique == "bend_semi":
        return f"{hole}'"
    elif technique == "bend_whole":
        return f'{hole}"'
    elif technique == "bend_one_and_half":
        return f"{hole}'''"
    elif technique == "overblow":
        return f"{hole}+OB"
    elif technique == "overdraw":
        return f"{hole}-OD"
    elif technique == "slide":
        return f"{hole}{'+' if action == 'blow' else '-'}◀"

    return f"{hole}{'+' if action == 'blow' else '-'}"


def build_markdown_output(
    audio_stem: str,
    original_key: str,
    harp_key: str,
    harmonica_type: HarmonicaType,
    score_type: ScoreType,
    tempo: int,
    time_sig: str,
    jianpu_lines: list[str],
    tab_lines: list[str],
    unplayable_notes: list[NoteEvent],
    output_md: bool,
    output_mid: bool,
) -> str:
    """Build the complete markdown output following jianpu-spec conventions."""

    from datetime import datetime

    type_label = "十孔布鲁斯口琴" if harmonica_type == HarmonicaType.DIATONIC else "半音阶口琴"
    now = datetime.now().strftime("%Y-%m-%d %H:%M")

    jianpu_key = original_key.rstrip("m")
    # Handle sharp/flat for jianpu-spec D field
    jianpu_key_d = jianpu_key.replace("#", "#").replace("b", "$")

    lines = [
        f"# {audio_stem} - 口琴谱",
        "",
        "## 元信息",
        "",
        "| 项目 | 值 |",
        "| :--- | :--- |",
        f"| 原调 | {original_key} |",
        f"| 口琴类型 | {type_label} |",
        f"| 使用口琴调性 | {harp_key}调 |",
        f"| 拍号 | {time_sig} |",
        f"| 速度 | {tempo} BPM |",
        f"| 生成时间 | {now} |",
        "",
    ]

    # Jianpu score section
    lines.append("## 简谱正文（jianpu-spec 格式）")
    lines.append("")
    lines.append("```")
    lines.append(f"V: 1.0")
    lines.append(f"B: {audio_stem}")
    lines.append(f"D: {jianpu_key_d}")
    lines.append(f"P: {time_sig}")
    lines.append(f"J: {tempo}")
    for qline in jianpu_lines:
        lines.append(qline)
    lines.append("```")
    lines.append("")

    # Harmonica tab section
    if score_type == ScoreType.HARP_TAB:
        if harmonica_type == HarmonicaType.DIATONIC:
            lines.append("## 口琴谱（十孔）")
            lines.append("")
            lines.append("技巧符号说明：")
            lines.append("- `4+` = 第4孔吹气，`4-` = 第4孔吸气")
            lines.append("- `3'` = 第3孔半音压音，`3\"` = 第3孔全音压音，`3'''` = 第3孔1.5音压音")
            lines.append("- `6+OB` = 第6孔超吹，`6-OD` = 第6孔超吸")
        else:
            lines.append("## 口琴谱（半音阶）")
            lines.append("")
            lines.append("技巧符号说明：")
            lines.append("- `4+` = 第4孔吹气（不按键），`4-` = 第4孔吸气（不按键）")
            lines.append("- `4+◀` = 第4孔吹气+按下半音键")

        lines.append("")
        lines.append("```")
        for tline in tab_lines:
            lines.append(tline)
        lines.append("```")
        lines.append("")

    # Warnings for unplayable notes
    if unplayable_notes:
        uniq = {}
        for n in unplayable_notes:
            uniq[n.pitch_name] = uniq.get(n.pitch_name, 0) + 1
        note_list = ", ".join(f"{name}(×{cnt})" for name, cnt in sorted(uniq.items()))
        lines.append("> **注意**：以下音符无法在口琴上演奏：")
        lines.append(f"> {note_list}")
        lines.append("")

    if output_mid:
        lines.append(f"> 打开同名 `.mid` 文件可试听扒谱效果。")

    return "\n".join(lines)
