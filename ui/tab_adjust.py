"""字体微调 Tab：只调整 dy/dx/scale"""
import gradio as gr
from pathlib import Path
from PIL import Image


PAGE_SIZE = 50
STATUS_LABEL = {
    'all': '全部',
    'adjusted': '仅参数微调',
}


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

    def _render_preview(png_path, dy, dx, scale, size=200):
        try:
            img = Image.open(png_path).convert('L')
        except Exception:
            return Image.new('RGB', (size, size), 'white')
        inv = img.point(lambda x: 255 - x)
        bbox = inv.getbbox()
        if not bbox:
            return Image.new('RGB', (size, size), 'white')
        char_img = img.crop(bbox)
        w, h = char_img.size
        em = 1000
        base_scale = 800 / max(w, h) if max(w, h) > 0 else 1.0
        final_scale = base_scale * scale
        new_w = max(1, int(w * final_scale))
        new_h = max(1, int(h * final_scale))
        char_scaled = char_img.resize((new_w, new_h), Image.LANCZOS)
        canvas = Image.new('L', (em, em), 255)
        px = (em - new_w) // 2 + int(dx)
        py = (em - new_h) // 2 - int(dy)
        canvas.paste(char_scaled, (px, py))
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
            if png_path:
                preview = _render_preview(
                    png_path, row['dy'] or 0, row['dx'] or 0, row['scale'] or 1.0, 80
                )
            else:
                preview = Image.new('RGB', (80, 80), 'white')

            dy = row['dy'] or 0
            dx = row['dx'] or 0
            sc = row['scale'] or 1.0
            changed = (dy != 0 or dx != 0 or sc != 1.0)
            label = f"{char} {'⚙' if changed else '·'}"
            images.append((preview, label))
            char_list.append(char)
            page_data.append({
                'char': char,
                'dy': dy, 'dx': dx, 'scale': sc,
                'png_path': str(png_path) if png_path else None,
            })

        s = db.stats()
        info = (
            f"**第 {page_idx+1} / {max_page+1} 页**  |  筛选 {start+1}-{end} / 共 {total}  |  "
            f"全库：{s['total']} 字，参数微调 {s['adjusted']} 个"
        )
        return images, info, page_idx, page_data, char_list

    init_images, init_info, init_page, init_data, init_chars = _render_page(0, 'all')

    current_page = gr.State(init_page)
    current_page_chars = gr.State(init_data)
    current_page_char_list = gr.State(init_chars)
    current_status = gr.State('all')
    current_char_index = gr.State(-1)

    gr.Markdown("### ④ 字体微调")
    gr.Markdown("只调整字体参数（位置/缩放）。**⚙ 表示有微调**")

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

    with gr.Row():
        btn_prev = gr.Button("⬅ 上一页", scale=1)
        page_num = gr.Number(value=init_page + 1, label="跳转", precision=0, scale=1)
        btn_next = gr.Button("下一页 ➡", scale=1)
        btn_refresh = gr.Button("🔄 刷新", variant="secondary", scale=1)

    gallery = gr.Gallery(
        value=init_images, label="点击选择", columns=10, rows=5, height=520,
        allow_preview=False, object_fit="contain",
    )

    gr.Markdown("---")
    gr.Markdown("### ✏️ 单字调整")

    with gr.Row():
        edit_char = gr.Textbox(label="当前字符", max_lines=1, interactive=False, scale=1)
        edit_status = gr.Textbox(label="状态", max_lines=1, interactive=False, scale=3)

    with gr.Row():
        btn_prev_char = gr.Button("⬅ 上一个字", variant="secondary", scale=1)
        btn_next_char = gr.Button("下一个字 ➡", variant="secondary", scale=1)

    with gr.Row():
        with gr.Column(scale=1):
            preview_image = gr.Image(label="字体效果预览", type="pil", height=320)
        with gr.Column(scale=2):
            dy_slider = gr.Slider(-200, 200, value=0, step=5, label="垂直偏移 dy（正数上移）")
            dx_slider = gr.Slider(-200, 200, value=0, step=5, label="水平偏移 dx（正数右移）")
            scale_slider = gr.Slider(0.5, 2.0, value=1.0, step=0.05, label="缩放倍数")
            with gr.Row():
                btn_save = gr.Button("💾 保存参数", variant="primary", scale=1)
                btn_reset = gr.Button("↺ 重置参数", scale=1)

    file_status = gr.Textbox(label="操作结果", max_lines=2, interactive=False)

    def _refresh_page(page_idx, status, char_idx=-1):
        images, info, page, data, chars = _render_page(page_idx, status)
        return (
            gr.update(value=images), info, page, gr.update(value=data),
            gr.update(value=chars), gr.update(value=page + 1), char_idx,
        )

    def _on_filter_change(status):
        return (*_refresh_page(0, status, -1), status)

    def _goto(page_idx, status):
        return _refresh_page(page_idx, status, -1)

    def _prev(page_idx, status):
        return _refresh_page(int(page_idx) - 1, status, -1)

    def _next(page_idx, status):
        return _refresh_page(int(page_idx) + 1, status, -1)

    def _on_select(evt: gr.SelectData, page_data):
        if not page_data:
            return "", 0, 0, 1.0, None, "", -1
        idx = evt.index
        if idx >= len(page_data):
            return "", 0, 0, 1.0, None, "", -1
        item = page_data[idx]
        preview = None
        if item['png_path']:
            preview = _render_preview(item['png_path'], item['dy'], item['dx'], item['scale'], 320)
        st = f"已选中 '{item['char']}'  dy={item['dy']}  dx={item['dx']}  scale={item['scale']}"
        return item['char'], item['dy'], item['dx'], item['scale'], preview, st, idx

    def _nav_char(direction, char_idx, current_chars, page_idx, status):
        empty = (
            gr.update(), gr.update(), gr.update(), gr.update(),
            gr.update(), gr.update(),
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

        preview = None
        if png_path:
            preview = _render_preview(
                png_path, target_row['dy'] or 0, target_row['dx'] or 0,
                target_row['scale'] or 1.0, 320,
            )

        st = f"已选中 '{target_char}'  ({new_global+1}/{len(rows)})"

        if int(new_page) != int(page_idx):
            images, info, page, data, chars = _render_page(new_page, status)
            return (
                gr.update(value=images), info, page, gr.update(value=data),
                gr.update(value=chars), gr.update(value=page + 1),
                target_char, target_row['dy'] or 0, target_row['dx'] or 0,
                target_row['scale'] or 1.0, preview, st, new_local,
            )
        return (
            gr.update(), gr.update(), gr.update(), gr.update(),
            gr.update(), gr.update(),
            target_char, target_row['dy'] or 0, target_row['dx'] or 0,
            target_row['scale'] or 1.0, preview, st, new_local,
        )

    def _on_slider(char, dy, dx, scale):
        if not char:
            return None
        png = db.get_png_path(char)
        if not png:
            return None
        return _render_preview(png, dy, dx, scale, 320)

    def _on_save(char, dy, dx, scale, page_idx, status):
        if not char:
            return gr.update(), "请先选字", gr.update(), gr.update()
        row = db.get_char(char)
        if not row:
            return gr.update(), f"无 '{char}'", gr.update(), gr.update()
        db.upsert_char(char, dy=int(dy), dx=int(dx), scale=float(scale))
        out = _refresh_page(int(page_idx), status)
        return out[0], f"✅ 已保存 '{char}'", out[3], out[4]

    def _on_reset(char, page_idx, status):
        if not char:
            return 0, 0, 1.0, "请先选字", gr.update(), gr.update(), gr.update()
        db.upsert_char(char, dy=0, dx=0, scale=1.0)
        out = _refresh_page(int(page_idx), status)
        return 0, 0, 1.0, f"↺ 已重置 '{char}'", out[0], out[3], out[4]

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
        preview = None
        if item['png_path']:
            preview = _render_preview(item['png_path'], item['dy'], item['dx'], item['scale'], 320)
        return (
            gr.update(value=images), info, page, gr.update(value=data),
            gr.update(value=chars), gr.update(value=page + 1),
            item['char'], item['dy'], item['dx'], item['scale'], preview,
            f"✅ 找到 '{target}'", local_idx,
        )

    refresh_outputs = [gallery, page_info, current_page, current_page_chars,
                       current_page_char_list, page_num, current_char_index]

    btn_prev.click(fn=_prev, inputs=[current_page, current_status], outputs=refresh_outputs)
    btn_next.click(fn=_next, inputs=[current_page, current_status], outputs=refresh_outputs)
    btn_refresh.click(fn=_goto, inputs=[current_page, current_status], outputs=refresh_outputs)
    page_num.submit(fn=lambda v, s: _goto(int(v) - 1, s),
                    inputs=[page_num, current_status], outputs=refresh_outputs)

    btn_apply_filter.click(fn=_on_filter_change, inputs=[status_filter],
                           outputs=refresh_outputs + [current_status])

    search_outputs = [
        gallery, page_info, current_page, current_page_chars, current_page_char_list,
        page_num, edit_char, dy_slider, dx_slider, scale_slider, preview_image,
        search_status, current_char_index,
    ]
    btn_search.click(fn=_search, inputs=[search_input, current_status], outputs=search_outputs)
    search_input.submit(fn=_search, inputs=[search_input, current_status], outputs=search_outputs)

    gallery.select(fn=_on_select, inputs=[current_page_chars],
                   outputs=[edit_char, dy_slider, dx_slider, scale_slider, preview_image,
                            edit_status, current_char_index])

    nav_outputs = [
        gallery, page_info, current_page, current_page_chars, current_page_char_list,
        page_num, edit_char, dy_slider, dx_slider, scale_slider, preview_image,
        edit_status, current_char_index,
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

    for s in (dy_slider, dx_slider, scale_slider):
        s.change(fn=_on_slider, inputs=[edit_char, dy_slider, dx_slider, scale_slider],
                 outputs=preview_image)

    btn_save.click(fn=_on_save,
                   inputs=[edit_char, dy_slider, dx_slider, scale_slider, current_page, current_status],
                   outputs=[gallery, file_status, current_page_chars, current_page_char_list])
    btn_reset.click(fn=_on_reset, inputs=[edit_char, current_page, current_status],
                    outputs=[dy_slider, dx_slider, scale_slider, file_status, gallery,
                             current_page_chars, current_page_char_list])