import gradio as gr
from pathlib import Path


def build(db, data_dir):
    gr.Markdown("### ⑤ 段落预览\n\n用生成的字体渲染一段文字")

    text = gr.Textbox(
        label="输入文字",
        value="我走过山时，山不说话；\n我路过海时，海不说话。",
        lines=5,
    )
    size = gr.Slider(16, 96, value=48, step=4, label="字号")

    btn = gr.Button("渲染", variant="primary")
    output = gr.Image(label="预览", type="pil")

    def _render(text, size):
        font_path = data_dir / 'font.ttf'
        if not font_path.exists():
            from PIL import Image, ImageDraw
            img = Image.new('RGB', (600, 100), 'white')
            ImageDraw.Draw(img).text((20, 40), "请先组装字体", fill='red')
            return img
        from core.preview import render_paragraph
        return render_paragraph(text, font_path, size=int(size))

    btn.click(fn=_render, inputs=[text, size], outputs=output)