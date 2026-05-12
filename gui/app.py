"""Gradio web interface for the AutoHarpTranscriber."""

import threading
import queue
from pathlib import Path

import gradio as gr

from pipeline.models import (
    UserConfig, HarmonicaType, ScoreType, KeyStrategy, StemChoice, KEYS,
)
from pipeline.orchestrator import run_pipeline


def create_ui() -> gr.Blocks:
    """Build the Gradio Blocks UI."""

    with gr.Blocks(title="口琴谱自动生成工具") as app:
        gr.Markdown("# 口琴谱自动生成工具")
        gr.Markdown("输入音频 → 自动生成口琴谱（Markdown简谱 + MIDI试听）")

        with gr.Row():
            with gr.Column(scale=2):
                audio_input = gr.File(
                    label="选择音频文件",
                    file_types=[".mp3", ".wav", ".flac", ".ogg", ".m4a"],
                )

                with gr.Row():
                    harmonica_type = gr.Radio(
                        label="口琴类型",
                        choices=[
                            ("十孔布鲁斯口琴", "diatonic"),
                            ("半音阶口琴", "chromatic"),
                        ],
                        value="diatonic",
                    )

                with gr.Row():
                    score_type = gr.Radio(
                        label="输出谱面类型",
                        choices=[
                            ("口琴谱（孔号+技巧）", "harp_tab"),
                            ("简谱（纯数字）", "jianpu"),
                        ],
                        value="harp_tab",
                    )

                with gr.Row():
                    key_strategy = gr.Radio(
                        label="调性策略",
                        choices=[
                            ("自动推荐最佳口琴调性", "auto"),
                            ("强制使用指定调性", "force"),
                        ],
                        value="auto",
                    )

                target_key = gr.Dropdown(
                    label="目标调性（仅强制模式有效）",
                    choices=KEYS,
                    value="C",
                )

                stem_choice = gr.Radio(
                    label="音轨来源（纯音乐请选"器乐轨"）",
                    choices=[
                        ("自动检测", "auto"),
                        ("人声轨", "vocals"),
                        ("器乐轨", "other"),
                    ],
                    value="auto",
                )

                with gr.Row():
                    output_md = gr.Checkbox(label="输出 Markdown 谱面 (.md)", value=True, info="勾选后自动生成")
                    output_mid = gr.Checkbox(label="输出 MIDI 试听文件 (.mid)", value=True, info="勾选后自动生成，仅用于试听")
                    output_png = gr.Checkbox(label="输出简谱图片 (.png)", value=True, info="勾选后自动生成竖排数字简谱图片")

                process_btn = gr.Button("开始生成", variant="primary", size="lg")

            with gr.Column(scale=1):
                log_output = gr.Textbox(
                    label="处理日志",
                    lines=15,
                    max_lines=20,
                    autoscroll=True,
                )

                md_output = gr.File(label="Markdown 谱面", visible=True)
                mid_output = gr.File(label="MIDI 试听文件", visible=True)
                png_output = gr.File(label="简谱图片", visible=True)

        def process(audio_file, harm_type, score_t, key_strat, tgt_key, stem_ch, out_md, out_mid, out_png):
            if audio_file is None:
                yield "请先选择音频文件", None, None, None
                return

            config = UserConfig(
                harmonica_type=HarmonicaType(harm_type),
                score_type=ScoreType(score_t),
                key_strategy=KeyStrategy(key_strat),
                target_key=tgt_key,
                output_md=out_md,
                output_mid=out_mid,
                output_png=out_png,
                stem_choice=StemChoice(stem_ch),
            )

            audio_path = Path(audio_file) if isinstance(audio_file, str) else Path(audio_file.name)
            log_queue = queue.Queue()

            def log_callback(msg: str):
                log_queue.put(msg)

            result_ctx = {}

            def run():
                try:
                    ctx = run_pipeline(audio_path, config, log_callback)
                    result_ctx["ctx"] = ctx
                    result_ctx["error"] = None
                except Exception as e:
                    result_ctx["error"] = str(e)
                    result_ctx["ctx"] = None

            thread = threading.Thread(target=run, daemon=True)
            thread.start()

            # Poll for log messages while pipeline runs
            while thread.is_alive() or not log_queue.empty():
                lines = []
                while not log_queue.empty():
                    try:
                        lines.append(log_queue.get_nowait())
                    except queue.Empty:
                        break
                if lines:
                    yield "\n".join(lines), None, None, None
                else:
                    thread.join(timeout=0.1)

            # Final flush
            final_lines = []
            while not log_queue.empty():
                try:
                    final_lines.append(log_queue.get_nowait())
                except queue.Empty:
                    break

            log_text = "\n".join(final_lines) if final_lines else ""

            ctx = result_ctx.get("ctx")
            if result_ctx.get("error"):
                log_text += f"\n处理失败: {result_ctx['error']}"
                yield log_text, None, None, None
                return

            stem = audio_path.stem
            output_dir = audio_path.parent

            md_file = str(output_dir / f"{stem}.md") if out_md and (output_dir / f"{stem}.md").exists() else None
            mid_file = str(output_dir / f"{stem}.mid") if out_mid and (output_dir / f"{stem}.mid").exists() else None
            png_file = str(output_dir / f"{stem}.png") if out_png and (output_dir / f"{stem}.png").exists() else None

            yield log_text, md_file, mid_file, png_file

        process_btn.click(
            fn=process,
            inputs=[audio_input, harmonica_type, score_type, key_strategy, target_key, stem_choice, output_md, output_mid, output_png],
            outputs=[log_output, md_output, mid_output, png_output],
        )

    return app
