import json
from pathlib import Path
from .models import NoteEvent, KEYS, KEY_SEMITONES, DIATONIC_HARP_KEYS


_KNOWLEDGE_DIR = Path(__file__).parent.parent / "knowledge"


def _load_key_profiles() -> dict:
    with open(_KNOWLEDGE_DIR / "key_profiles.json", encoding="utf-8") as f:
        return json.load(f)


def detect_key(notes: list[NoteEvent]) -> str:
    """Detect the musical key of a sequence of notes using K-K profiles.

    Returns key name like 'C', 'Am', etc.
    """
    profiles = _load_key_profiles()

    # Aggregate note durations per pitch class
    durations = [0.0] * 12
    for note in notes:
        pc = note.pitch % 12
        durations[pc] += note.duration

    total = sum(durations)
    if total == 0:
        return "C"

    # Normalize
    durations = [d / total for d in durations]

    # Compute correlation with each major and minor profile
    best_key = "C"
    best_corr = -999

    for i, tonic in enumerate(profiles["pitch_classes"]):
        # Major
        rotated_profile = _rotate_profile(profiles["major"], i)
        corr = _pearson_correlation(durations, rotated_profile)
        if corr > best_corr:
            best_corr = corr
            best_key = tonic

        # Minor
        rotated_profile = _rotate_profile(profiles["minor"], i)
        corr = _pearson_correlation(durations, rotated_profile)
        if corr > best_corr:
            best_corr = corr
            best_key = f"{tonic}m"

    return best_key


def recommend_harp_key(notes: list[NoteEvent], original_key: str) -> tuple[str, float]:
    """Recommend the best diatonic harmonica key for a given set of notes.

    Returns (harp_key, score). Higher score = better fit.
    """
    # Diatonic C harp can play: C D E F G A B (plus bends)
    # The best harp is one where the song notes mostly fall on natural holes

    # Get pitch class distribution
    durations = [0.0] * 12
    for note in notes:
        pc = note.pitch % 12
        durations[pc] += note.duration

    total = sum(durations)
    if total == 0:
        return "C", 0.0

    best_harp = "C"
    best_score = -999.0

    # Natural notes for C diatonic: C(0) D(2) E(4) F(5) G(7) A(9) B(11)
    c_natural = {0, 2, 4, 5, 7, 9, 11}

    for harp_name, harp_semitones in DIATONIC_HARP_KEYS.items():
        # When playing a song in original_key on a harp in harp_name,
        # the notes that fall on natural harp holes are those where:
        # (pitch_class - harp_semitones) % 12 is in c_natural
        score = 0.0
        for pc in range(12):
            relative_pc = (pc - harp_semitones) % 12
            if relative_pc in c_natural:
                score += durations[pc]
        if score > best_score:
            best_score = score
            best_harp = harp_name

    return best_harp, best_score


def transpose_notes(notes: list[NoteEvent], semitones: int) -> list[NoteEvent]:
    """Transpose all notes by a given number of semitones."""
    return [
        NoteEvent(
            pitch=n.pitch + semitones,
            start_time=n.start_time,
            duration=n.duration,
            velocity=n.velocity,
        )
        for n in notes
    ]


def _rotate_profile(profile: list[float], n: int) -> list[float]:
    """Rotate a 12-element profile by n positions."""
    return profile[-n:] + profile[:-n]


def _pearson_correlation(a: list[float], b: list[float]) -> float:
    n = len(a)
    mean_a = sum(a) / n
    mean_b = sum(b) / n
    cov = sum((x - mean_a) * (y - mean_b) for x, y in zip(a, b))
    var_a = sum((x - mean_a) ** 2 for x in a)
    var_b = sum((y - mean_b) ** 2 for y in b)
    if var_a == 0 or var_b == 0:
        return 0.0
    return cov / ((var_a * var_b) ** 0.5)
