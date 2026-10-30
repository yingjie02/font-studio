"""导出字体 Tab：矢量化 + 组装 + 字体名称 + 进度 + 未确认提示 + 复制 + 备份 + 打开文件夹"""
import html
import json
import os
import subprocess
from pathlib import Path

import gradio as gr


def _make_copy_html(chars_text, count):
    js_text = json.dumps(chars_text, ensure_ascii=False)
    escaped_html = html.escape(chars_text)
    onclick = (
        "const text = " + js_text + ";"
        "const status = document.getElementById('copy-status');"
        "navigator.clipboard.writeText(text).then(function(){"
        "status.textContent = '✅ 已复制 ' + text.length + ' 个字';"
        "status.style.color = 'green';"
        "}).catch(function(){"
        "const ta = document.getElementById('char-text');"
        "if (ta) { ta.focus(); ta.select(); }"
        "try { if (document.execCommand('copy')) {"
        "status.textContent = '✅ 已复制 ' + text.length + ' 个字'; status.style.color = 'green';"
        "} else { status.textContent = '⚠️ 请手动 Ctrl+C'; status.style.color = 'orange'; }"
        "} catch(e) { status.textContent = '⚠️ 请手动 Ctrl+C'; status.style.color = 'orange'; }"
        "});"
    )
    onclick_attr = html.escape(onclick, quote=True)
    return f"""
<div style="font-family: system-ui, sans-serif;">
  <div style="display: flex; align-items: center; gap: 12px; margin-bottom: 12px;">
    <button type="button" onclick="{onclick_attr}"
            style="padding: 10px 22px; background: #ff6b35; color: white; border: none; border-radius: 6px; cursor: pointer; font-size: 15px; font-weight: 600;">
      📋 一键复制 {count} 个字
    </button>
    <span id="copy-status" style="font-size: 14px; color: #666;"></span>
  </div>
  <textarea id="char-text" readonly
            style="width: 100%; height: 160px; font-family: monospace; font-size: 13px; padding: 8px; border: 1px solid #ddd; border-radius: 4px; box-sizing: border-box; background: #fafafa;">{escaped_html}</textarea>
</div>
"""


def _open_folder(folder):
    try:
        folder = Path(folder)
        if not folder.exists():
            return f"文件夹不存在：{folder}"
        if os.name == 'nt':
            os.startfile(str(folder))
        else:
            subprocess.Popen(['xdg-open', str(folder)])
        return f"✅ 已打开：{folder}"
    except Exception as e:
        return f"打开失败：{e}"


def build(db, data_dir):
    gr.Markdown("### ⑤ 导出字体")

    # ============ 字体名称 ============
    with gr.Row():
        font_name_input = gr.Textbox(
            label="字体名称（安装后在 Word 里显示的名字）",
            value="MyHandwriting",
            max_lines=1,
            scale=3,
        )
        btn_refresh_stats = gr.Button("🔄 刷新状态", variant="secondary", scale=1)

    stats_display = gr.Textbox(label="当前状态", max_lines=2, interactive=False)

    # ============ 操作按钮 ============
    with gr.Row():
        btn_vec = gr.Button("① 矢量化（PNG → SVG）", variant="secondary", scale=1)
        btn_asm = gr.Button("② 组装字体（SVG → TTF）", variant="primary", scale=1)

    log = gr.Textbox(label="日志", lines=20, interactive=False)

    with gr.Row():
        font_file = gr.File(label="下载字体", scale=2)
        btn_open_font_folder = gr.Button("📂 打开输出文件夹", variant="secondary", scale=1)

    # ============ 复制 ============
    gr.Markdown("---")
    gr.Markdown("### 📋 当前字体包含的所有字符")
    with gr.Row():
        btn_refresh_chars = gr.Button("🔄 刷新字符列表", variant="secondary", scale=1)
        char_stats = gr.Textbox(label="统计", max_lines=1, interactive=False, scale=2)
    copy_html = gr.HTML()

    # ============ 备份 ============
    gr.Markdown("---")
    gr.Markdown("### 💾 备份与恢复")
    with gr.Row():
        btn_backup = gr.Button("💾 生成备份", variant="primary", scale=1)
        backup_file = gr.File(label="下载备份")
    with gr.Row():
        restore_input = gr.File(label="上传备份 zip", file_types=[".zip"], scale=3)
        btn_restore = gr.Button("📥 恢复备份", variant="secondary", scale=1)
    backup_log = gr.Textbox(label="备份/恢复状态", lines=3, interactive=False)

    # ============ 逻辑 ============
    def _refresh_stats():
        s = db.stats()
        msg = (
            f"共 {s['total']} 字  |  "
            f"已确认 {s['confirmed']}  |  "
            f"未确认 {s['unconfirmed']}  |  "
            f"已修改 {s['modified']}  |  "
            f"参数微调 {s['adjusted']}"
        )
        return msg

    def _vectorize(progress=gr.Progress()):
        from core.vectorize import vectorize_incremental
        lines = []

        def log_fn(m):
            lines.append(str(m))

        def cb(current, total, desc):
            if total > 0:
                progress(current / total, desc=desc)

        try:
            vectorize_incremental(db, data_dir, log=log_fn, progress_callback=cb)
        except Exception as e:
            import traceback
            log_fn(f"❌ 失败：{e}")
            log_fn(traceback.format_exc())
        return "\n".join(lines)

    def _assemble(font_name, progress=gr.Progress()):
        from core.assemble import assemble_incremental
        lines = []

        def log_fn(m):
            lines.append(str(m))

        if not font_name or not font_name.strip():
            log_fn("❌ 字体名称不能为空")
            return "\n".join(lines), None

        # 未确认提示
        s = db.stats()
        if s['unconfirmed'] > 0:
            log_fn(f"⚠️ 注意：有 {s['unconfirmed']} 个字未确认（confirmed=0），仍会包含在字体中")

        def cb(current, total, desc):
            if total > 0:
                progress(current / total, desc=desc)

        fp = data_dir / 'font.ttf'
        try:
            assemble_incremental(
                db, data_dir, fp,
                font_name=font_name.strip(),
                log=log_fn,
                progress_callback=cb,
            )
        except Exception as e:
            import traceback
            log_fn(f"❌ 失败：{e}")
            log_fn(traceback.format_exc())
            return "\n".join(lines), None

        if fp.exists():
            return "\n".join(lines), str(fp)
        return "\n".join(lines), None

    def _refresh_chars():
        rows = db.all_chars()
        chars = [r['char'] for r in rows]
        total = len(chars)
        if total == 0:
            return _make_copy_html("", 0), "共 0 个字"
        return _make_copy_html(''.join(chars), total), f"共 {total} 个字"

    def _do_backup():
        from datetime import datetime
        ts = datetime.now().strftime('%Y%m%d_%H%M%S')
        target = data_dir / 'backups' / f'font_backup_{ts}.zip'
        lines = []
        try:
            db.backup(target, log=lambda m: lines.append(str(m)))
            return "\n".join(lines), str(target)
        except Exception as e:
            return f"备份失败: {e}", None

    def _do_restore(file_obj):
        if not file_obj:
            return "请先上传 zip"
        lines = []
        try:
            path = file_obj if isinstance(file_obj, (str, Path)) else file_obj.name
            ok, msg = db.restore(path, log=lambda m: lines.append(str(m)))
            s = db.stats()
            lines.append(
                f"数据库现状：共 {s['total']} 字，已确认 {s['confirmed']}，未确认 {s['unconfirmed']}"
            )
            return "\n".join(lines)
        except Exception as e:
            import traceback
            return f"恢复失败: {e}\n{traceback.format_exc()}"

    def _open_font_folder():
        return _open_folder(data_dir)

    # ============ 绑定 ============
    btn_vec.click(fn=_vectorize, outputs=log)
    btn_asm.click(fn=_assemble, inputs=[font_name_input], outputs=[log, font_file])
    btn_refresh_chars.click(fn=_refresh_chars, outputs=[copy_html, char_stats])
    btn_refresh_stats.click(fn=_refresh_stats, outputs=stats_display)
    btn_backup.click(fn=_do_backup, outputs=[backup_log, backup_file])
    btn_restore.click(fn=_do_restore, inputs=[restore_input], outputs=backup_log)
    btn_open_font_folder.click(fn=_open_font_folder, outputs=backup_log)

    # 页面加载时自动填充
    try:
        init_html, init_stats = _refresh_chars()
        copy_html.value = init_html
        char_stats.value = init_stats
        stats_display.value = _refresh_stats()
    except Exception:
        pass