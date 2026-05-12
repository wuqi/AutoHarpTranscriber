from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Optional


class HarmonicaType(Enum):
    DIATONIC = "diatonic"
    CHROMATIC = "chromatic"


class ScoreType(Enum):
    HARP_TAB = "harp_tab"
    JIANPU = "jianpu"


class KeyStrategy(Enum):
    AUTO = "auto"
    FORCE = "force"


class StemChoice(Enum):
    AUTO = "auto"
    VOCALS = "vocals"
    OTHER = "other"


KEYS = ["C", "C#", "D", "D#", "E", "F", "F#", "G", "G#", "A", "A#", "B"]

KEY_SEMITONES = {k: i for i, k in enumerate(KEYS)}

NOTE_NAMES = ["C", "C#", "D", "D#", "E", "F", "F#", "G", "G#", "A", "A#", "B"]

# Diatonic harmonica keys and how many semitones their layout is shifted from C
DIATONIC_HARP_KEYS = {
    "C": 0, "C#": 1, "D": 2, "D#": 3, "E": 4, "F": 5, "F#": 6,
    "G": 7, "G#": 8, "A": 9, "A#": 10, "B": 11,
}


@dataclass
class NoteEvent:
    pitch: int        # MIDI pitch (60 = C4)
    start_time: float
    duration: float
    velocity: int = 80

    @property
    def end_time(self) -> float:
        return self.start_time + self.duration

    @property
    def pitch_name(self) -> str:
        octave = (self.pitch // 12) - 1
        name = NOTE_NAMES[self.pitch % 12]
        return f"{name}{octave}"


@dataclass
class UserConfig:
    harmonica_type: HarmonicaType = HarmonicaType.DIATONIC
    score_type: ScoreType = ScoreType.HARP_TAB
    key_strategy: KeyStrategy = KeyStrategy.AUTO
    target_key: str = "C"
    output_md: bool = True
    output_mid: bool = True
    output_png: bool = True
    stem_choice: StemChoice = StemChoice.AUTO


@dataclass
class HarmonicaNote:
    hole: int
    action: str       # "blow" or "draw"
    technique: Optional[str] = None


@dataclass
class PipelineContext:
    audio_path: Path
    config: UserConfig = field(default_factory=UserConfig)

    # Intermediate results
    separated_audio: Optional[Path] = None
    raw_midi: Optional[Path] = None
    notes: list[NoteEvent] = field(default_factory=list)

    # Key analysis results
    original_key: Optional[str] = None
    transposed_key: Optional[str] = None
    recommended_harp_key: Optional[str] = None
    harp_key_used: Optional[str] = None
    transposed_notes: list[NoteEvent] = field(default_factory=list)

    # Score generation results
    jianpu_lines: list[str] = field(default_factory=list)
    tab_lines: list[str] = field(default_factory=list)
    unplayable_notes: list[NoteEvent] = field(default_factory=list)

    # Metadata
    tempo: int = 120
    time_signature: str = "4/4"
