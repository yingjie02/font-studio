"""PNG 管理 Tab：查看/确认/编辑/删除 PNG 源文件 + 批量删除未确认"""
import os
import subprocess
import gradio as gr
from pathlib import Path
from PIL import Image


PAGE_SIZE = 50
STATUS_LABEL = {
    'all': '全部',
    'unconfirmed': '仅未确认',
    'confirmed': '仅已确认',
    'modified': '仅已修改',
}


def _open_external(png_path, ps_path=""):
    p = Path(png_path)
    if not p.exists():
        return f"文件不存在: {p}"
    if ps_path and Path(ps_path).exists():
        try:
            subprocess.Popen([ps_path, str(p)])
            return f"已用 PS 打开: {p.name}"
        except Exception as e:
            return f"PS 启动失败: {e}，改用默认程序"
    try:
        if os.name == 'nt':
            os.startfile(str(p))
        else:
            subprocess.Popen(['xdg-open', str(p)])
        return f"已用默认程序打开: {p.name}"
    except Exception as e:
        return f"打开失败: {e}"


def _reveal_in_explorer(png_path):
    p = Path(png_path)
    if not p.exists():
        return f"文件不存在: {p}"
    try:
        if os.name == 'nt':
            subprocess.Popen(['explorer', '/select,', str(p)])
        else:
            subprocess.Popen(['xdg-open', str(p.parent)])
        return f"已在资源管理器中定位: {p.name}"
    except Exception as e:
        return f"打开失败: {e}"


def build(db, data_dir):
    def _get_png_path(row):
        if row['png_path'] and Path(row['png_path']).exists():
            return Path(row['png_path'])
        hex_code = f"{ord(row['char']):04x}"
        for folder in (data_dir / 'png_confirmed', data_dir / 'png_unconfirmed', data_dir / 'png'):
            candidate = folder / f"uni{hex_code}.png"
            if candidate.exists():
                return candidate
        return None

    def _render_png(png_path, size=80):
        try:
            img = Image.open(png_path).convert('L')
        except Exception:
            return Image.new('RGB', (size, size), 'white')
        inv = img.point(lambda x: 255 - x)
        bbox = inv.getbbox()
        if bbox:
            img = img.crop(bbox)
        w, h = img.size
        side = max(w, h, 1)
        canvas = Image.new('L', (side, side), 255)
        canvas.paste(img, ((side - w) // 2, (side - h) // 2))
        canvas.thumbnail((size, size), Image.LANCZOS)
        return canvas.convert('RGB')

    def _render_page(page_idx, status_filter):
        rows = db.filter_chars(status_filter)
        total = len(rows)
        if total == 0:
            return [], "当前筛选下没有字", 0, [], []

        max_page = (total - 1) // PAGE_SIZE
        page_idx = max(0, min(int(page_idx), max_page))
        start = page_idx * PAGE_SIZE
        end = min(start + PAGE_SIZE, total)
        page_rows = rows[start:end]

        images = []
        page_data = []
        char_list = []

        for row in page_rows:
            char = row['char']
            png_path = _get_png_path(row)
            preview = _render_png(png_path, 80) if png_path else Image.new('RGB', (80, 80), 'white')
            marks = ['✓' if row['confirmed'] else '○']
            if row['modified']:
                marks.append('✱')
            label = f"{char} {''.join(marks)}"
            images.append((preview, label))
            char_list.append(char)
            page_data.append({
                'char': char,
                'confirmed': row['confirmed'],
                'modified': row['modified'],
                'png_path': str(png_path) if png_path else None,
            })

        s = db.stats()
        info = (
            f"**第 {page_idx+1} / {max_page+1} 页**  |  筛选 {start+1}-{end} / 共 {total}  |  "
            f"全库：{s['total']} 字，已确认 {s['confirmed']}，未确认 {s['unconfirmed']}，已修改 {s['modified']}"
        )
        return images, info, page_idx, page_data, char_list

    init_images, init_info, init_page, init_data, init_chars = _render_page(0, 'all')

    current_page = gr.State(init_page)
    current_page_chars = gr.State(init_data)
    current_page_char_list = gr.State(init_chars)
    current_status = gr.State('all')
    current_char_index = gr.State(-1)

    gr.Markdown("### ③ PNG 管理")
    gr.Markdown(
        "**✓ 已确认** / **○ 未确认** / **✱ 已修改**  \n"
        "确认后文件会移到 `data/png_confirmed/`，未确认在 `data/png_unconfirmed/`"
    )

    # ============ 搜索与筛选 ============
    with gr.Row():
        search_input = gr.Textbox(label="🔍 按字搜索", placeholder="输入一个字", max_lines=1, scale=4)
        btn_search = gr.Button("查找", variant="primary", scale=1)
    search_status = gr.Textbox(label="搜索状态", max_lines=1, interactive=False)

    with gr.Row():
        status_filter = gr.Radio(
            choices=[(v, k) for k, v in STATUS_LABEL.items()],
            value='all', label="筛选", scale=3,
        )
        btn_apply_filter = gr.Button("应用筛选", variant="secondary", scale=1)

    page_info = gr.Markdown(value=init_info)

    # ============ 翻页 ============
    with gr.Row():
        btn_prev = gr.Button("⬅ 上一页", scale=1)
        page_num = gr.Number(value=init_page + 1, label="跳转", precision=0, scale=1)
        btn_next = gr.Button("下一页 ➡", scale=1)
        btn_refresh = gr.Button("🔄 刷新", variant="secondary", scale=1)

    gallery = gr.Gallery(
        value=init_images, label="点击选择", columns=10, rows=5, height=520,
        allow_preview=False, object_fit="contain",
    )

    # ============ 批量操作 ============
    gr.Markdown("---")
    gr.Markdown("### 📦 批量操作（当前页）")
    batch_chars = gr.CheckboxGroup(
        choices=init_chars, value=init_chars,
        label="勾选（默认全选当前页）", scale=4,
    )
    with gr.Row():
        btn_batch_confirm = gr.Button("✓ 确认选中", variant="primary", scale=1)
        btn_batch_unconfirm = gr.Button("○ 取消确认选中", scale=1)
        btn_batch_delete = gr.Button("🗑 删除选中", variant="stop", scale=1)
    with gr.Row():
        btn_delete_all_unconfirmed = gr.Button(
            "🗑 删除所有未确认的字（危险，无法恢复）",
            variant="stop",
            scale=1,
        )
    batch_log = gr.Textbox(label="批量结果", max_lines=2, interactive=False)

    # ============ 单字管理 ============
    gr.Markdown("---")
    gr.Markdown("### 🖼 单字管理")

    with gr.Row():
        edit_char = gr.Textbox(label="当前字符", max_lines=1, interactive=False, scale=1)
        edit_status = gr.Textbox(label="状态", max_lines=1, interactive=False, scale=3)

    with gr.Row():
        btn_prev_char = gr.Button("⬅ 上一个字", variant="secondary", scale=1)
        btn_next_char = gr.Button("下一个字 ➡", variant="secondary", scale=1)

    with gr.Row():
        with gr.Column(scale=1):
            preview_image = gr.Image(label="PNG 原图", type="pil", height=300)
        with gr.Column(scale=1):
            char_info = gr.Textbox(label="字信息", lines=4, interactive=False)
            ps_path_input = gr.Textbox(
                label="PS 路径（可选）",
                placeholder=r"C:\Program Files\Adobe\Adobe Photoshop 2024\Photoshop.exe",
            )

    gr.Markdown("**操作**")
    with gr.Row():
        btn_confirm = gr.Button("✓ 标记已确认", variant="primary", scale=1)
        btn_unconfirm = gr.Button("○ 取消确认", scale=1)
        btn_mark_modified = gr.Button("✱ 标记已修改", scale=1)
        btn_clear_modified = gr.Button("清除已修改", scale=1)
    with gr.Row():
        btn_open_ext = gr.Button("🖼 打开外部程序编辑", scale=1)
        btn_reveal = gr.Button("📁 在资源管理器定位", scale=1)
        btn_delete = gr.Button("🗑 删除此字", variant="stop", scale=1)

    file_status = gr.Textbox(label="操作结果", max_lines=2, interactive=False)

    # ============ 事件逻辑 ============
    def _refresh_page(page_idx, status, char_idx=-1):
        images, info, page, data, chars = _render_page(page_idx, status)
        return (
            gr.update(value=images), info, page, gr.update(value=data),
            gr.update(value=chars), gr.update(choices=chars, value=chars),
            gr.update(value=page + 1), char_idx,
        )

    def _on_filter_change(status):
        return (*_refresh_page(0, status, -1), status)

    def _goto(page_idx, status):
        return _refresh_page(page_idx, status, -1)

    def _prev(page_idx, status):
        return _refresh_page(int(page_idx) - 1, status, -1)

    def _next(page_idx, status):
        return _refresh_page(int(page_idx) + 1, status, -1)

    def _make_info(item):
        return (
            f"字符：{item['char']}\n"
            f"已确认：{'是' if item['confirmed'] else '否'}\n"
            f"已修改：{'是' if item['modified'] else '否'}\n"
            f"PNG：{item['png_path'] or '无'}"
        )

    def _on_select(evt: gr.SelectData, page_data):
        if not page_data:
            return "", None, "", "", -1
        idx = evt.index
        if idx >= len(page_data):
            return "", None, "", "", -1
        item = page_data[idx]
        preview = _render_png(item['png_path'], 400) if item['png_path'] else None
        return item['char'], preview, _make_info(item), f"已选中 '{item['char']}'", idx

    def _nav_char(direction, char_idx, current_chars, page_idx, status):
        empty = (
            gr.update(), gr.update(), gr.update(), gr.update(),
            gr.update(), gr.update(), gr.update(),
            gr.update(), gr.update(), gr.update(), gr.update(), gr.update(),
        )
        if not current_chars or char_idx < 0 or char_idx >= len(current_chars):
            return (*empty, "请先选一个字", -1)

        current_char = current_chars[char_idx]
        rows = db.filter_chars(status)
        global_idx = -1
        for i, r in enumerate(rows):
            if r['char'] == current_char:
                global_idx = i
                break
        if global_idx < 0:
            return (*empty, f"'{current_char}' 不在筛选结果中", -1)

        new_global = global_idx + direction
        if new_global < 0:
            return (*empty, "已经是第一个了", char_idx)
        if new_global >= len(rows):
            return (*empty, "已经是最后一个了", char_idx)

        new_page = new_global // PAGE_SIZE
        new_local = new_global % PAGE_SIZE
        target_row = rows[new_global]
        target_char = target_row['char']

        png_path = None
        hex_code = f"{ord(target_char):04x}"
        for folder in (data_dir / 'png_confirmed', data_dir / 'png_unconfirmed', data_dir / 'png'):
            p = folder / f"uni{hex_code}.png"
            if p.exists():
                png_path = p
                break

        preview = _render_png(png_path, 400) if png_path else None
        item = {
            'char': target_char,
            'confirmed': target_row['confirmed'],
            'modified': target_row['modified'],
            'png_path': str(png_path) if png_path else None,
        }
        st = f"已选中 '{target_char}'  ({new_global+1}/{len(rows)})"

        if int(new_page) != int(page_idx):
            images, info, page, data, chars = _render_page(new_page, status)
            return (
                gr.update(value=images), info, page, gr.update(value=data),
                gr.update(value=chars), gr.update(choices=chars, value=chars),
                gr.update(value=page + 1),
                target_char, preview, _make_info(item), st, new_local,
            )
        return (
            gr.update(), gr.update(), gr.update(), gr.update(),
            gr.update(), gr.update(), gr.update(),
            target_char, preview, _make_info(item), st, new_local,
        )

    def _on_confirm(char, page_idx, status):
        if not char:
            return "请先选字", gr.update(), gr.update(), gr.update(), gr.update()
        db.set_confirmed(char, True)
        out = _refresh_page(int(page_idx), status)
        row = db.get_char(char)
        item = {'char': char, 'confirmed': row['confirmed'], 'modified': row['modified'], 'png_path': None}
        return f"✓ '{char}' 已确认", out[0], out[3], out[4], _make_info(item)

    def _on_unconfirm(char, page_idx, status):
        if not char:
            return "请先选字", gr.update(), gr.update(), gr.update(), gr.update()
        db.set_confirmed(char, False)
        out = _refresh_page(int(page_idx), status)
        row = db.get_char(char)
        item = {'char': char, 'confirmed': row['confirmed'], 'modified': row['modified'], 'png_path': None}
        return f"○ '{char}' 已取消确认", out[0], out[3], out[4], _make_info(item)

    def _on_mark_modified(char, page_idx, status):
        if not char:
            return "请先选字", gr.update(), gr.update(), gr.update(), gr.update()
        db.set_modified(char, True)
        out = _refresh_page(int(page_idx), status)
        row = db.get_char(char)
        item = {'char': char, 'confirmed': row['confirmed'], 'modified': row['modified'], 'png_path': None}
        return f"✱ '{char}' 已标记为已修改", out[0], out[3], out[4], _make_info(item)

    def _on_clear_modified(char, page_idx, status):
        if not char:
            return "请先选字", gr.update(), gr.update(), gr.update(), gr.update()
        db.set_modified(char, False)
        out = _refresh_page(int(page_idx), status)
        row = db.get_char(char)
        item = {'char': char, 'confirmed': row['confirmed'], 'modified': row['modified'], 'png_path': None}
        return f"已清除 '{char}' 的修改标记", out[0], out[3], out[4], _make_info(item)

    def _on_open_ext(char, ps_path):
        if not char:
            return "请先选字"
        png = db.get_png_path(char)
        if not png:
            return f"'{char}' 的 PNG 不存在"
        msg = _open_external(png, ps_path)
        db.set_modified(char, True)
        return msg + "（已自动标记为已修改）"

    def _on_reveal(char):
        if not char:
            return "请先选字"
        png = db.get_png_path(char)
        if not png:
            return f"'{char}' 的 PNG 不存在"
        return _reveal_in_explorer(png)

    def _on_delete(char, page_idx, status):
        if not char:
            return "请先选字", gr.update(), gr.update(), gr.update(), gr.update(), gr.update(), -1
        if not db.delete_char(char):
            return f"删除失败：无 '{char}'", gr.update(), gr.update(), gr.update(), gr.update(), gr.update(), -1
        out = _refresh_page(int(page_idx), status)
        return f"🗑 已删除 '{char}'", out[0], out[3], out[4], "", None, "", -1

    def _batch_confirm(chars, page_idx, status):
        if not chars:
            return "未勾选", gr.update(), gr.update(), gr.update()
        n = db.batch_set_confirmed(chars, True)
        out = _refresh_page(int(page_idx), status)
        return f"✓ 已确认 {n} 个字", out[0], out[3], out[4]

    def _batch_unconfirm(chars, page_idx, status):
        if not chars:
            return "未勾选", gr.update(), gr.update(), gr.update()
        n = db.batch_set_confirmed(chars, False)
        out = _refresh_page(int(page_idx), status)
        return f"○ 已取消确认 {n} 个字", out[0], out[3], out[4]

    def _batch_delete(chars, page_idx, status):
        if not chars:
            return "未勾选", gr.update(), gr.update(), gr.update()
        n = 0
        for c in chars:
            if db.delete_char(c):
                n += 1
        out = _refresh_page(int(page_idx), status)
        return f"🗑 已删除 {n} 个字", out[0], out[3], out[4]

    def _delete_all_unconfirmed(page_idx, status):
        s = db.stats()
        n_unconf = s['unconfirmed']
        if n_unconf == 0:
            return "没有未确认的字", gr.update(), gr.update(), gr.update()

        n = db.delete_all_unconfirmed()
        out = _refresh_page(int(page_idx), status)
        return f"🗑 已删除全部 {n} 个未确认的字（含 PNG 和 SVG）", out[0], out[3], out[4]

    def _search(char, status):
        empty = (
            gr.update(), gr.update(), gr.update(), gr.update(), gr.update(),
            gr.update(), gr.update(), gr.update(), gr.update(), gr.update(),
            gr.update(), gr.update(),
        )
        if not char or not char.strip():
            return (*empty, "请输入字符", -1)
        target = char.strip()[0]
        row = db.get_char(target)
        if not row:
            return (*empty, f"❌ 无 '{target}'", -1)
        rows = db.filter_chars(status)
        idx = None
        for i, r in enumerate(rows):
            if r['char'] == target:
                idx = i
                break
        if idx is None:
            return (*empty, f"'{target}' 存在但被筛选排除", -1)

        page_idx = idx // PAGE_SIZE
        local_idx = idx % PAGE_SIZE
        images, info, page, data, chars = _render_page(page_idx, status)
        item = data[local_idx]
        preview = _render_png(item['png_path'], 400) if item['png_path'] else None
        return (
            gr.update(value=images), info, page, gr.update(value=data),
            gr.update(value=chars), gr.update(choices=chars, value=chars),
            gr.update(value=page + 1),
            item['char'], preview, _make_info(item),
            f"✅ 找到 '{target}'：第 {page_idx+1} 页第 {local_idx+1} 个", local_idx,
        )

    # ============ 绑定事件 ============
    refresh_outputs = [gallery, page_info, current_page, current_page_chars,
                       current_page_char_list, batch_chars, page_num, current_char_index]

    btn_prev.click(fn=_prev, inputs=[current_page, current_status], outputs=refresh_outputs)
    btn_next.click(fn=_next, inputs=[current_page, current_status], outputs=refresh_outputs)
    btn_refresh.click(fn=_goto, inputs=[current_page, current_status], outputs=refresh_outputs)
    page_num.submit(fn=lambda v, s: _goto(int(v) - 1, s),
                    inputs=[page_num, current_status], outputs=refresh_outputs)

    btn_apply_filter.click(fn=_on_filter_change, inputs=[status_filter],
                           outputs=refresh_outputs + [current_status])

    search_outputs = [
        gallery, page_info, current_page, current_page_chars, current_page_char_list,
        batch_chars, page_num, edit_char, preview_image, char_info, search_status,
        current_char_index,
    ]
    btn_search.click(fn=_search, inputs=[search_input, current_status], outputs=search_outputs)
    search_input.submit(fn=_search, inputs=[search_input, current_status], outputs=search_outputs)

    gallery.select(fn=_on_select, inputs=[current_page_chars],
                   outputs=[edit_char, preview_image, char_info, edit_status, current_char_index])

    nav_outputs = [
        gallery, page_info, current_page, current_page_chars, current_page_char_list,
        batch_chars, page_num, edit_char, preview_image, char_info, edit_status,
        current_char_index,
    ]
    btn_prev_char.click(
        fn=lambda idx, chars, page, st: _nav_char(-1, idx, chars, page, st),
        inputs=[current_char_index, current_page_char_list, current_page, current_status],
        outputs=nav_outputs,
    )
    btn_next_char.click(
        fn=lambda idx, chars, page, st: _nav_char(1, idx, chars, page, st),
        inputs=[current_char_index, current_page_char_list, current_page, current_status],
        outputs=nav_outputs,
    )

    btn_confirm.click(fn=_on_confirm, inputs=[edit_char, current_page, current_status],
                      outputs=[file_status, gallery, current_page_chars, current_page_char_list, char_info])
    btn_unconfirm.click(fn=_on_unconfirm, inputs=[edit_char, current_page, current_status],
                        outputs=[file_status, gallery, current_page_chars, current_page_char_list, char_info])
    btn_mark_modified.click(fn=_on_mark_modified, inputs=[edit_char, current_page, current_status],
                            outputs=[file_status, gallery, current_page_chars, current_page_char_list, char_info])
    btn_clear_modified.click(fn=_on_clear_modified, inputs=[edit_char, current_page, current_status],
                             outputs=[file_status, gallery, current_page_chars, current_page_char_list, char_info])

    btn_open_ext.click(fn=_on_open_ext, inputs=[edit_char, ps_path_input], outputs=file_status)
    btn_reveal.click(fn=_on_reveal, inputs=[edit_char], outputs=file_status)
    btn_delete.click(fn=_on_delete, inputs=[edit_char, current_page, current_status],
                     outputs=[file_status, gallery, current_page_chars,
                              current_page_char_list, edit_char, preview_image,
                              char_info, current_char_index])

    btn_batch_confirm.click(fn=_batch_confirm, inputs=[batch_chars, current_page, current_status],
                            outputs=[batch_log, gallery, current_page_chars, current_page_char_list])
    btn_batch_unconfirm.click(fn=_batch_unconfirm, inputs=[batch_chars, current_page, current_status],
                              outputs=[batch_log, gallery, current_page_chars, current_page_char_list])
    btn_batch_delete.click(fn=_batch_delete, inputs=[batch_chars, current_page, current_status],
                           outputs=[batch_log, gallery, current_page_chars, current_page_char_list])
    btn_delete_all_unconfirmed.click(
        fn=_delete_all_unconfirmed,
        inputs=[current_page, current_status],
        outputs=[batch_log, gallery, current_page_chars, current_page_char_list],
    )