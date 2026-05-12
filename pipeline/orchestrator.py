"""Pipeline orchestrator — ties all processing steps together."""

import time
from pathlib import Path
from typing import Callable, Optional

from .models import (
    PipelineContext, UserConfig, NoteEvent,
    HarmonicaType, ScoreType, KeyStrategy, KEYS, KEY_SEMITONES,
)


LogCallback = Callable[[str], None]


def run_pipeline(
    audio_path: Path,
    config: UserConfig,
    log: LogCallback,
) -> PipelineContext:
    """Execute the full processing pipeline.

    The log callback receives status messages for GUI display.
    """
    ctx = PipelineContext(audio_path=audio_path, config=config)
    output_dir = audio_path.parent

    steps: list[tuple[str, Callable]] = [
        ("[1/7] 正在分离主旋律 (Demucs)...", _step_separate),
        ("[2/7] 正在进行音高检测 (Basic Pitch)...", _step_detect_pitch),
        ("[3/7] 正在解析MIDI音符...", _step_parse_midi),
        ("[4/7] 正在分析调性...", _step_analyze_key),
        ("[5/7] 正在生成简谱...", _step_generate_jianpu),
        ("[6/7] 正在生成口琴谱...", _step_generate_tab),
        ("[7/7] 正在输出文件...", _step_write_output),
    ]

    # Skip tab generation when user only wants jianpu
    if config.score_type == ScoreType.JIANPU:
        steps = [s for s in steps if s[1] is not _step_generate_tab]

    for msg, step_fn in steps:
        t0 = time.time()
        log(msg)
        try:
            step_fn(ctx, output_dir)
        except Exception as e:
            log(f"错误: {e}")
            raise
        elapsed = time.time() - t0
        log(f"  完成 ({elapsed:.1f}s)")

    log("处理完成！")
    return ctx


def _step_separate(ctx: PipelineContext, output_dir: Path) -> None:
    from .source_separator import separate_source
    ctx.separated_audio = separate_source(
        ctx.audio_path, output_dir, stem_choice=ctx.config.stem_choice
    )


def _step_detect_pitch(ctx: PipelineContext, output_dir: Path) -> None:
    from .pitch_detector import detect_pitch
    ctx.raw_midi = detect_pitch(ctx.separated_audio)


def _step_parse_midi(ctx: PipelineContext, output_dir: Path) -> None:
    from .midi_parser import parse_midi
    notes, tempo, time_sig = parse_midi(ctx.raw_midi)
    ctx.notes = notes
    ctx.tempo = tempo
    ctx.time_signature = time_sig
    if not notes:
        raise ValueError("未检测到音符，请确保音频包含清晰旋律")


def _step_analyze_key(ctx: PipelineContext, output_dir: Path) -> None:
    from .key_analyzer import detect_key, recommend_harp_key, transpose_notes
    from .models import DIATONIC_HARP_KEYS

    ctx.original_key = detect_key(ctx.notes)
    harp_key, score = recommend_harp_key(ctx.notes, ctx.original_key)
    ctx.recommended_harp_key = harp_key

    if ctx.config.key_strategy == KeyStrategy.FORCE:
        ctx.harp_key_used = ctx.config.target_key
    else:
        ctx.harp_key_used = harp_key

    # Compute semitones to transpose
    if ctx.config.harmonica_type == HarmonicaType.DIATONIC:
        target_semitones = DIATONIC_HARP_KEYS.get(ctx.harp_key_used, 0)
        ctx.transposed_notes = transpose_notes(ctx.notes, -target_semitones)
        # Compute the transposed key for jianpu D field
        orig_key_name = ctx.original_key.rstrip("m")
        orig_pc = KEY_SEMITONES.get(orig_key_name, 0)
        transposed_pc = (orig_pc - target_semitones) % 12
        suffix = "m" if ctx.original_key.endswith("m") else ""
        ctx.transposed_key = KEYS[transposed_pc] + suffix
    else:
        # Chromatic: keep original pitch
        ctx.transposed_notes = ctx.notes
        ctx.transposed_key = ctx.original_key


def _step_generate_jianpu(ctx: PipelineContext, output_dir: Path) -> None:
    from .score_generator import generate_jianpu_score
    ctx.jianpu_lines = generate_jianpu_score(
        ctx.transposed_notes,
        ctx.transposed_key or ctx.original_key,
        ctx.tempo,
        ctx.time_signature,
    )


def _step_generate_tab(ctx: PipelineContext, output_dir: Path) -> None:
    from .score_generator import generate_harp_tab
    ctx.tab_lines, ctx.unplayable_notes = generate_harp_tab(
        ctx.transposed_notes,
        ctx.config.harmonica_type,
        ctx.harp_key_used,
        ctx.tempo,
        ctx.time_signature,
    )
    # Plan section 7: force transposition with unplayable notes → error
    if ctx.config.key_strategy == KeyStrategy.FORCE and ctx.unplayable_notes:
        names = sorted({n.pitch_name for n in ctx.unplayable_notes})
        raise ValueError(
            f"移调至{ctx.harp_key_used}后，仍有{', '.join(names)}无法在口琴上实现"
        )


def _step_write_output(ctx: PipelineContext, output_dir: Path) -> None:
    from .score_generator import build_markdown_output
    from .midi_writer import write_midi

    stem = ctx.audio_path.stem

    if ctx.config.output_md:
        md_content = build_markdown_output(
            audio_stem=stem,
            original_key=ctx.original_key,
            transposed_key=ctx.transposed_key or ctx.original_key,
            harp_key=ctx.harp_key_used,
            harmonica_type=ctx.config.harmonica_type,
            score_type=ctx.config.score_type,
            tempo=ctx.tempo,
            time_sig=ctx.time_signature,
            jianpu_lines=ctx.jianpu_lines,
            tab_lines=ctx.tab_lines,
            unplayable_notes=ctx.unplayable_notes,
            output_mid=ctx.config.output_mid,
        )
        md_path = output_dir / f"{stem}.md"
        md_path.write_text(md_content, encoding="utf-8")

    if ctx.config.output_mid:
        mid_path = output_dir / f"{stem}.mid"
        notes = ctx.transposed_notes if ctx.transposed_notes else ctx.notes
        write_midi(notes, mid_path, ctx.tempo, ctx.time_signature)

    if ctx.config.output_png and ctx.jianpu_lines:
        from .jianpu_renderer import render_jianpu_image
        png_path = output_dir / f"{stem}.png"
        render_jianpu_image(
            jianpu_lines=ctx.jianpu_lines,
            title=stem,
            key=ctx.transposed_key or ctx.original_key,
            time_sig=ctx.time_signature,
            tempo=ctx.tempo,
            output_path=png_path,
        )
