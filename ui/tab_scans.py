import gradio as gr
from pathlib import Path


def build(db, data_dir):
    gr.Markdown("### ② 扫描件上传")
    gr.Markdown(
        "上传写好的扫描件 JPG，自动提取 PNG 到字体库。"
        "依赖 Docker 镜像 `wefont-cn-denoise`"
    )

    with gr.Row():
        btn_check = gr.Button("🔍 检查 Docker 环境", variant="secondary", scale=1)
    env_status = gr.Textbox(label="环境状态", max_lines=1, interactive=False)

    gr.Markdown("---")

    files = gr.File(
        label="拖拽上传 JPG（可多选）",
        file_count="multiple",
        file_types=[".jpg", ".jpeg", ".JPG", ".JPEG"],
        type="filepath",
    )
    btn_upload = gr.Button("上传并处理", variant="primary")
    log = gr.Textbox(label="处理日志", lines=20, interactive=False)

    def _check():
        from core.extract import check_docker
        ok, msg = check_docker()
        return ("✅ " if ok else "❌ ") + msg

    def _process(file_paths):
        if not file_paths:
            return "请先上传 JPG"
        from core.extract import extract_uploaded
        lines = []
        def log_fn(msg):
            lines.append(str(msg))
        extract_uploaded(file_paths, data_dir, db, log=log_fn)
        s = db.stats()
        lines.append("")
        lines.append(
            f"数据库：共 {s['total']} 字，已确认 {s['confirmed']}，"
            f"未确认 {s['unconfirmed']}，已修改 {s['modified']}"
        )
        return "\n".join(lines)

    btn_check.click(fn=_check, outputs=env_status)
    btn_upload.click(fn=_process, inputs=[files], outputs=log)