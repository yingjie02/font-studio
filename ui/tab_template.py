"""生成模板 Tab：选字集 → 对比已写 → 生成待写 PDF + 下载完整预设（缓存）"""
import tempfile
from pathlib import Path

import gradio as gr


PRESETS = {
    "GB2312 全集（6763）": "gb2312.txt",
    "常用 4000 字": "gb2312_4k_常用四千字.txt",
    "常用 3000 字": "gb2312_3k_常用三千字.txt",
    "常用 2000 字": "gb2312_2k_常用二千字.txt",
    "常用 1000 字": "gb2312_1k_常用一千字.txt",
}


def _load_charset(path):
    try:
        text = Path(path).read_text(encoding='utf-8', errors='ignore')
        return set(c for c in text if c.strip())
    except Exception:
        return set()


def build(db, data_dir):
    charsets_dir = Path(data_dir) / 'charsets'
    assets_dir = Path(data_dir) / 'assets'
    cache_dir = Path(data_dir) / 'template_cache'

    missing_assets = []
    if not (assets_dir / 'finder.png').exists():
        missing_assets.append('finder.png')
    if not (assets_dir / 'fireflysung.ttf').exists():
        missing_assets.append('fireflysung.ttf')

    available_presets = []
    for name, fname in PRESETS.items():
        if (charsets_dir / fname).exists():
            available_presets.append(name)

    gr.Markdown("### ① 生成模板")
    gr.Markdown(
        "选择字集 → 对比已写 → 只生成还没写的字的 PDF → 打印 → 手写 → 扫描上传（Tab ②）"
    )

    if missing_assets:
        gr.Markdown(
            f"⚠️ **缺少资源文件**：{', '.join(missing_assets)}  \n"
            "请先运行 `python setup_assets.py` 从 Docker 镜像导出资源。"
        )

    if not available_presets:
        gr.Markdown(
            "⚠️ **缺少字集文件**：请运行 `python setup_assets.py` 导出到 `data/charsets/`。"
        )

    # ============ 参数区 ============
    with gr.Row():
        preset = gr.Dropdown(
            choices=available_presets,
            value=available_presets[0] if available_presets else None,
            label="预设字集",
            scale=2,
        )
        custom_file = gr.File(
            label="或上传自定义字集（.txt）",
            file_types=[".txt"],
            scale=1,
        )

    with gr.Row():
        cell_size = gr.Slider(
            15, 35, value=25, step=1, label="字格大小 (mm)", scale=2,
        )
        draw_sub = gr.Checkbox(
            value=False,
            label="显示格子序号",
            scale=1,
        )

    # ============ 两个生成按钮 ============
    with gr.Row():
        btn_generate = gr.Button("📄 生成待写 PDF（差集）", variant="primary", scale=1)
        btn_full = gr.Button("📥 下载完整预设 PDF（缓存）", variant="secondary", scale=1)

    with gr.Row():
        only_missing = gr.Checkbox(
            value=True,
            label="待写 PDF 只包含尚未写的字（取消勾选 = 生成全集，不走缓存）",
            scale=4,
        )

    log = gr.Textbox(label="日志", lines=20, interactive=False)
    output_pdf = gr.File(label="下载 PDF")

    # ============ 缓存管理 ============
    gr.Markdown("---")
    gr.Markdown("### 📦 模板缓存")
    gr.Markdown(
        "**完整预设 PDF 会按「字集 + 字格大小 + 序号开关」缓存**，同参数只生成一次。  \n"
        "缓存位置：`data/template_cache/`，可随时删除。"
    )

    with gr.Row():
        btn_refresh_cache = gr.Button("🔄 刷新缓存状态", scale=1)
        btn_clear_cache = gr.Button("🗑 清空所有缓存", variant="stop", scale=1)

    cache_info = gr.Textbox(label="缓存列表", lines=8, interactive=False)

    # ============ 逻辑 ============
    def _refresh_cache_info():
        from core.template import list_cache_files
        files = list_cache_files(cache_dir)
        if not files:
            return "📂 缓存为空"
        total_mb = sum(f['size_mb'] for f in files)
        lines = [f"共 {len(files)} 个缓存 PDF，合计 {total_mb:.1f}MB"]
        for f in files:
            lines.append(f"  • {f['name']}  ({f['size_mb']:.1f}MB)")
        return "\n".join(lines)

    def _generate_pending(preset_name, custom, missing_only_flag, cs, show_sub):
        """生成待写 PDF（差集或全集，不缓存）"""
        lines = []
        def log_fn(m):
            lines.append(str(m))

        if missing_assets:
            log_fn(f"❌ 缺少资源：{', '.join(missing_assets)}")
            log_fn("请运行 python setup_assets.py")
            return "\n".join(lines), None

        # 加载字集
        if custom:
            path = custom if isinstance(custom, str) else custom.name
            target = _load_charset(path)
            log_fn(f"使用自定义字集：{Path(path).name}")
        elif preset_name:
            filename = PRESETS.get(preset_name)
            full_path = charsets_dir / filename
            if not full_path.exists():
                log_fn(f"❌ 字集不存在：{full_path}")
                return "\n".join(lines), None
            target = _load_charset(full_path)
            log_fn(f"使用字集：{filename}")
        else:
            log_fn("请选择字集或上传自定义文件")
            return "\n".join(lines), None

        log_fn(f"字集共 {len(target)} 个字")

        have = {r['char'] for r in db.all_chars()}
        log_fn(f"数据库已有 {len(have)} 个字")

        if missing_only_flag:
            target = target - have
            log_fn(f"过滤后，还需要写 {len(target)} 个字")
        else:
            log_fn(f"未过滤，将生成全部 {len(target)} 个字")

        if not target:
            log_fn("✅ 这个字集已经全部写完了！")
            return "\n".join(lines), None

        chars = sorted(target)
        log_fn("开始生成 PDF...")

        try:
            from core.template import generate_template_pdf
            tmp_dir = Path(tempfile.mkdtemp())
            suffix = "pending" if missing_only_flag else "full"
            output = tmp_dir / f'template_{int(cs)}mm_{len(chars)}chars_{suffix}.pdf'
            generate_template_pdf(
                chars, output,
                cell_size=int(cs),
                assets_dir=assets_dir,
                draw_sub=show_sub,
                log=log_fn,
            )
            return "\n".join(lines), str(output)
        except Exception as e:
            import traceback
            log_fn(f"❌ 生成失败: {e}")
            log_fn(traceback.format_exc())
            return "\n".join(lines), None

    def _download_full(preset_name, cs, show_sub):
        """下载完整预设 PDF（带缓存）"""
        lines = []
        def log_fn(m):
            lines.append(str(m))

        if missing_assets:
            log_fn(f"❌ 缺少资源：{', '.join(missing_assets)}")
            log_fn("请运行 python setup_assets.py")
            return "\n".join(lines), None

        if not preset_name:
            log_fn("请选择预设字集（自定义字集不支持缓存下载）")
            return "\n".join(lines), None

        filename = PRESETS.get(preset_name)
        if not filename:
            log_fn(f"未知预设：{preset_name}")
            return "\n".join(lines), None

        charset_path = charsets_dir / filename
        if not charset_path.exists():
            log_fn(f"字集不存在：{charset_path}")
            return "\n".join(lines), None

        chars = _load_charset(charset_path)
        if not chars:
            log_fn("字集为空")
            return "\n".join(lines), None

        log_fn(f"预设：{preset_name}，共 {len(chars)} 字")
        log_fn(f"参数：字格 {int(cs)}mm，序号 {'显示' if show_sub else '不显示'}")

        cache_key = f"{Path(filename).stem}_{int(cs)}mm_{'sub' if show_sub else 'nosub'}"

        try:
            from core.template import get_or_create_cached_pdf
            pdf_path, from_cache = get_or_create_cached_pdf(
                chars, cache_key, int(cs), show_sub,
                cache_dir, assets_dir, log=log_fn,
            )
            log_fn("")
            if from_cache:
                log_fn("✅ 从缓存加载（不重新生成）")
            else:
                log_fn("📝 首次生成，已存入缓存")
            return "\n".join(lines), str(pdf_path)
        except Exception as e:
            import traceback
            log_fn(f"❌ 生成失败: {e}")
            log_fn(traceback.format_exc())
            return "\n".join(lines), None

    def _clear_cache():
        from core.template import clear_cache_dir
        clear_cache_dir(cache_dir)
        return _refresh_cache_info()

    # ============ 绑定 ============
    btn_generate.click(
        fn=_generate_pending,
        inputs=[preset, custom_file, only_missing, cell_size, draw_sub],
        outputs=[log, output_pdf],
    )
    btn_full.click(
        fn=_download_full,
        inputs=[preset, cell_size, draw_sub],
        outputs=[log, output_pdf],
    )
    btn_refresh_cache.click(fn=_refresh_cache_info, outputs=cache_info)
    btn_clear_cache.click(fn=_clear_cache, outputs=cache_info)

    # 页面加载时自动显示缓存状态
    try:
        cache_info.value = _refresh_cache_info()
    except Exception:
        pass