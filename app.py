import gradio as gr
from core.paths import get_app_data_dir, get_resource_path
from core.db import DB
from ui import tab_template, tab_scans, tab_png, tab_adjust, tab_export, tab_paragraph

DATA_DIR = get_app_data_dir()           # 可写数据
RES_DIR = get_resource_path()            # 只读资源（assets/charsets）

# 首次运行时，把打包进来的 assets/charsets 复制到用户数据目录
import shutil
for sub in ('assets', 'charsets'):
    src = RES_DIR / 'data' / sub
    dst = DATA_DIR / sub
    if src.exists() and not dst.exists():
        shutil.copytree(src, dst)
        print(f"[init] 初始化 {dst}")

db = DB(DATA_DIR / 'project.db')


def main():
    with gr.Blocks(title="字体工坊") as demo:
        gr.Markdown("# 字体工坊\n手写 → 字体，一站式本地工具")
        with gr.Tabs():
            with gr.Tab("① 生成模板"):
                tab_template.build(db, DATA_DIR)
            with gr.Tab("② 扫描件"):
                tab_scans.build(db, DATA_DIR)
            with gr.Tab("③ PNG 管理"):
                tab_png.build(db, DATA_DIR)
            with gr.Tab("④ 字体微调"):
                tab_adjust.build(db, DATA_DIR)
            with gr.Tab("⑤ 导出字体"):
                tab_export.build(db, DATA_DIR)
            with gr.Tab("⑥ 段落预览"):
                tab_paragraph.build(db, DATA_DIR)

    demo.launch(inbrowser=True, server_name="127.0.0.1")


if __name__ == '__main__':
    main()