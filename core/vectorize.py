"""PNG → SVG 矢量化，使用 potracer
potrace 追踪暗色区域。PNG 是白底黑字（字=暗），所以直接传原图就能追踪字的笔画。
不要反色！反色会追踪背景，导致 SVG 反相。
"""

from pathlib import Path
from PIL import Image
import potrace


def png_to_svg(png_path, svg_path, turd_size=2, alpha_max=1.0):
    img = Image.open(png_path).convert('L')
    bitmap = potrace.Bitmap(img)

    path = bitmap.trace(
        turdsize=turd_size,
        alphamax=alpha_max,
        opticurve=True,
        opttolerance=0.2,
    )

    parts = []
    for curve in path:
        start = curve.start_point
        parts.append(f"M{start.x:.2f},{start.y:.2f}")
        for segment in curve:
            if segment.is_corner:
                c = segment.c
                end = segment.end_point
                parts.append(f"L{c.x:.2f},{c.y:.2f}")
                parts.append(f"L{end.x:.2f},{end.y:.2f}")
            else:
                c1 = segment.c1
                c2 = segment.c2
                end = segment.end_point
                parts.append(
                    f"C{c1.x:.2f},{c1.y:.2f} "
                    f"{c2.x:.2f},{c2.y:.2f} "
                    f"{end.x:.2f},{end.y:.2f}"
                )
        parts.append("Z")

    d = " ".join(parts)
    svg = (
        f'<?xml version="1.0" encoding="UTF-8"?>\n'
        f'<svg xmlns="http://www.w3.org/2000/svg" '
        f'width="{img.width}" height="{img.height}" '
        f'viewBox="0 0 {img.width} {img.height}">\n'
        f'<rect width="100%" height="100%" fill="white"/>\n'
        f'<path d="{d}" fill="black"/>\n'
        f'</svg>\n'
    )

    Path(svg_path).write_text(svg, encoding='utf-8')
    return svg_path


def vectorize_incremental(db, data_dir, log=print, progress_callback=None):
    """增量矢量化
    progress_callback(current, total, desc) 可选
    """
    data_dir = Path(data_dir)
    svg_dir = data_dir / 'svg'
    svg_dir.mkdir(parents=True, exist_ok=True)

    todo = []
    for row in db.all_chars():
        png_path = row['png_path']
        if not png_path or not Path(png_path).exists():
            continue
        png_mtime = Path(png_path).stat().st_mtime
        svg_path = row['svg_path']
        # 跳过：SVG 文件存在且比 PNG 新
        if (svg_path and Path(svg_path).exists()
                and row['svg_mtime'] and row['svg_mtime'] >= png_mtime):
            continue
        todo.append(row)

    if not todo:
        log("✅ 所有 PNG 都已矢量化，无需重新生成")
        return 0

    total = len(todo)
    log(f"开始矢量化：{total} 个字符")
    ok = 0
    for i, row in enumerate(todo, 1):
        char = row['char']

        if progress_callback:
            try:
                progress_callback(i - 1, total, f"矢量化 {char} ({i}/{total})")
            except Exception:
                pass

        png_path = row['png_path']
        svg_path = svg_dir / f"uni{ord(char):04x}.svg"
        try:
            png_to_svg(png_path, svg_path)
            db.upsert_char(
                char,
                svg_path=str(svg_path.absolute()),
                svg_mtime=Path(svg_path).stat().st_mtime,
            )
            ok += 1
            if i % 50 == 0 or i == total:
                log(f"  [{i}/{total}] {char} ✓")
        except Exception as e:
            log(f"  [{i}/{total}] {char} ✗ {e}")

    if progress_callback:
        try:
            progress_callback(total, total, "矢量化完成")
        except Exception:
            pass

    log(f"矢量化完成：{ok}/{total}")
    return ok