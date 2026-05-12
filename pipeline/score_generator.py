import json
from pathlib import Path
from typing import Callable, Optional

from .models import (
    NoteEvent, HarmonicaType, ScoreType, HarmonicaNote, KEYS, KEY_SEMITONES,
)

_KNOWLEDGE_DIR = Path(__file__).parent.parent / "knowledge"

# Major scale intervals from tonic (in semitones)
MAJOR_INTERVALS = [0, 2, 4, 5, 7, 9, 11]
JIANPU_NUMBERS = ["1", "2", "3", "4", "5", "6", "7"]

# Standard rhythm quantization targets (in beats)
RHYTHM_TARGETS = [0.25, 0.5, 0.75, 1.0, 1.5, 2.0, 3.0, 4.0, 5.0, 6.0]


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

    offset = (KEY_SEMITONES.get(harp_key, 0) - KEY_SEMITONES.get(base_key, 0)) % 12

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
        # Non-diatonic: find nearest diatonic note below and add #.
        # Always use # (not $) to match FQ reference and MIDI convention.
        # jianpu-spec: # comes AFTER the note number (unlike JE format)
        prev_interval = (semitone_interval - 1) % 12
        idx = MAJOR_INTERVALS.index(prev_interval)
        base = f"{JIANPU_NUMBERS[idx]}#"

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
    elif abs(beats - 5.0) < eps:
        return "----"
    elif abs(beats - 6.0) < eps:
        return "---."
    else:
        # Fallback: use augmentation lines
        n = round(beats) - 1
        return "-" * max(n, 3)


def _build_score_lines(
    notes: list[NoteEvent],
    token_fn: Callable[[NoteEvent], str],
    beat_duration: float,
    beats_per_bar: int,
) -> list[str]:
    """Build Q: lines with proper rest insertion, bar placement, and note splitting.

    Handles:
    - Rests (0) when there are gaps between notes
    - Notes that cross bar lines (split with correct durations)
    - Line wrapping at ~70 characters
    """
    if not notes:
        return ["Q: | 0 - - - |"]

    EPS = 0.02  # tolerance in seconds (~20ms)

    lines: list[str] = []
    current_line = "Q: | "
    bar_beats = 0.0
    current_time = 0.0  # absolute time in seconds

    def _emit_token(token_base: str, beats: float) -> None:
        """Write one token into the current line, splitting at bar boundaries."""
        nonlocal current_line, bar_beats

        remaining = beats
        while remaining > 0.005:
            space = beats_per_bar - bar_beats
            if remaining > space + 0.005:
                chunk = space
                remaining -= space
            else:
                chunk = remaining
                remaining = 0

            dur_suf = _duration_suffix(chunk)
            current_line += f"{token_base}{dur_suf} "
            bar_beats += chunk

            if bar_beats >= beats_per_bar - 0.005:
                # Close bar
                current_line += "| "
                if len(current_line) > 70:
                    lines.append(current_line.rstrip())
                    current_line = "Q: | "
                bar_beats = 0.0

    def _emit_rest(beats: float) -> None:
        """Insert a 0 rest of the given beat duration."""
        _emit_token("0", beats)

    for note in notes:
        # Insert rest for gap before this note
        if note.start_time > current_time + EPS:
            gap_beats = (note.start_time - current_time) / beat_duration
            _emit_rest(gap_beats)

        current_time = note.end_time
        note_beats = note.duration / beat_duration
        token = token_fn(note)
        _emit_token(token, note_beats)

    # Close remaining bar
    stripped = current_line.strip()
    if stripped != "Q: |":
        if not stripped.endswith("|"):
            current_line += "|"
        lines.append(current_line.rstrip())

    return lines if lines else ["Q: | 0 - - - |"]


def generate_jianpu_score(
    notes: list[NoteEvent],
    key: str,
    tempo: int,
    time_sig: str,
) -> list[str]:
    """Generate jianpu-spec Q lines from notes.

    Returns a list of Q: lines with bar lines inserted.
    """
    # Determine tonic for movable-do
    key_name = key.rstrip("m")
    tonic_pc = KEY_SEMITONES.get(key_name, 0)
    tonic_midi = 60 + tonic_pc  # Tonic in octave 4

    beat_duration = 60.0 / tempo

    parts = time_sig.split("/")
    beats_per_bar = int(parts[0]) if len(parts) == 2 else 4

    def token_fn(note: NoteEvent) -> str:
        return midi_to_jianpu(note.pitch, tonic_midi)

    return _build_score_lines(notes, token_fn, beat_duration, beats_per_bar)


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

    unplayable: list[NoteEvent] = []

    def token_fn(note: NoteEvent) -> str:
        entry = mapping.get(note.pitch)
        if entry is None:
            unplayable.append(note)
            return "?"
        return _format_harp_note(entry)

    lines = _build_score_lines(notes, token_fn, beat_duration, beats_per_bar)
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
    transposed_key: str,
    harp_key: str,
    harmonica_type: HarmonicaType,
    score_type: ScoreType,
    tempo: int,
    time_sig: str,
    jianpu_lines: list[str],
    tab_lines: list[str],
    unplayable_notes: list[NoteEvent],
    output_mid: bool,
) -> str:
    """Build the complete markdown output following jianpu-spec conventions."""

    from datetime import datetime

    type_label = "十孔布鲁斯口琴" if harmonica_type == HarmonicaType.DIATONIC else "半音阶口琴"
    now = datetime.now().strftime("%Y-%m-%d %H:%M")

    # D field uses the transposed key (the actual key of the notes in the score)
    jianpu_key = transposed_key.rstrip("m")
    # For minor keys, convert to relative major for the jianpu key signature.
    # In jianpu (movable-do), 1=C means do=C; Am's relative major is C.
    if transposed_key.endswith("m"):
        minor_tonic_pc = KEY_SEMITONES.get(jianpu_key, 0)
        relative_major_pc = (minor_tonic_pc + 3) % 12
        jianpu_key = KEYS[relative_major_pc]
    # Handle flat for jianpu-spec D field ($ = flat)
    jianpu_key_d = jianpu_key.replace("b", "$")

    lines = [
        f"# {audio_stem} - 口琴谱",
        "",
        "## 元信息",
        "",
        "| 项目 | 值 |",
        "| :--- | :--- |",
        f"| 原调 | {original_key} |",
        f"| 口琴类型 | {type_label} |",
        f"| 推荐口琴 | {harp_key}调{type_label} |",
        f"| 拍号 | {time_sig} |",
        f"| 速度 | {tempo} BPM |",
        f"| 生成时间 | {now} |",
        "",
    ]

    # Jianpu score section
    lines.append("## 简谱正文（jianpu-spec 格式）")
    lines.append("")
    lines.append("```")
    lines.append("V: 1.0")
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

        # Warnings for unplayable notes (only in harp tab mode)
        if unplayable_notes:
            uniq = {}
            for n in unplayable_notes:
                uniq[n.pitch_name] = uniq.get(n.pitch_name, 0) + 1
            note_list = ", ".join(f"{name}(×{cnt})" for name, cnt in sorted(uniq.items()))
            lines.append("> **注意**：以下音符无法在口琴上演奏：")
            lines.append(f"> {note_list}")
            lines.append("")

    if output_mid:
        lines.append("> 打开同名 `.mid` 文件可试听扒谱效果。")

    return "\n".join(lines)
