"""SVG → TTF 组装
- 按 bbox 缩放，最大边 800
- 缩放后 bbox 居中到 1000×1000
- lsb 手动从 coordinates 算
- 翻转 y 轴 + 最后强制反转坐标（解决黑白颠倒）
"""
import re
import array
from pathlib import Path

from fontTools.fontBuilder import FontBuilder
from fontTools.pens.ttGlyphPen import TTGlyphPen
from fontTools.pens.cu2quPen import Cu2QuPen
from fontTools.ttLib.tables._g_l_y_f import GlyphCoordinates
from svg.path import parse_path


EM = 1000
DEFAULT_SCALE = 800.0
BASELINE_DESCENT = 200
ASCENT = 800

FORCE_REVERSE = True
DEFAULT_FONT_NAME = 'MyHandwriting'


def _parse_svg_path(svg_content):
    d_match = re.search(r'<path[^>]*\sd="([^"]+)"', svg_content)
    vb_match = re.search(r'viewBox="(\d+)\s+(\d+)\s+(\d+)\s+(\d+)"', svg_content)
    if not d_match or not vb_match:
        return None, None
    return d_match.group(1), (int(vb_match.group(3)), int(vb_match.group(4)))


def _calc_glyph_xmin(glyph):
    if glyph.numberOfContours <= 0:
        return 0
    try:
        xs = [float(c[0]) for c in glyph.coordinates]
        if not xs:
            return 0
        return int(min(xs))
    except Exception:
        return 0


def _svg_to_glyph(svg_content, dy=0, dx=0, scale_override=None):
    d, (vw, vh) = _parse_svg_path(svg_content)
    if d is None:
        return None, EM, 0

    try:
        path_obj = parse_path(d)
    except Exception:
        return None, EM, 0

    xs, ys = [], []
    for seg in path_obj:
        for t in (0.0, 0.25, 0.5, 0.75, 1.0):
            try:
                p = seg.point(t)
                xs.append(p.real)
                ys.append(p.imag)
            except Exception:
                continue
    if not xs:
        return None, EM, 0

    minx, maxx = min(xs), max(xs)
    miny, maxy = min(ys), max(ys)
    w = maxx - minx
    h = maxy - miny

    if w <= 0 or h <= 0:
        return None, EM, 0

    scale = DEFAULT_SCALE / max(w, h)
    if scale_override and scale_override != 1.0:
        scale *= scale_override

    s_xmin = minx * scale
    s_xmax = maxx * scale
    s_ymin = miny * scale
    s_ymax = maxy * scale
    s_w = s_xmax - s_xmin
    s_h = s_ymax - s_ymin
    ttf_ymin = -s_ymax

    dx_offset = (EM - s_w) / 2 - s_xmin + dx
    dy_offset = (EM - s_h) / 2 - ttf_ymin + dy

    tx = lambda x: x * scale + dx_offset
    ty = lambda y: -y * scale + dy_offset

    tt_pen = TTGlyphPen(None)
    pen = Cu2QuPen(tt_pen, max_err=1.0, reverse_direction=False)

    try:
        for seg in path_obj:
            cls = type(seg).__name__
            if cls == 'Move':
                end = seg.end
                pen.moveTo((tx(end.real), ty(end.imag)))
            elif cls == 'Line':
                end = seg.end
                pen.lineTo((tx(end.real), ty(end.imag)))
            elif cls == 'CubicBezier':
                pen.curveTo(
                    (tx(seg.control1.real), ty(seg.control1.imag)),
                    (tx(seg.control2.real), ty(seg.control2.imag)),
                    (tx(seg.end.real), ty(seg.end.imag)),
                )
            elif cls == 'QuadraticBezier':
                pen.qCurveTo(
                    (tx(seg.control.real), ty(seg.control.imag)),
                    (tx(seg.end.real), ty(seg.end.imag)),
                )
            elif cls == 'Close':
                pen.closePath()
            elif cls == 'Arc':
                pen.lineTo((tx(seg.end.real), ty(seg.end.imag)))
    except Exception as e:
        print(f"  [warn] path draw error: {e}")

    try:
        glyph = tt_pen.glyph()
    except Exception as e:
        print(f"  [warn] glyph build error: {e}")
        return None, EM, 0

    lsb = _calc_glyph_xmin(glyph)
    return glyph, EM, lsb


def _reverse_glyph(glyph):
    if glyph.numberOfContours <= 0:
        return
    coords = glyph.coordinates
    flags = glyph.flags
    endPts = glyph.endPtsOfContours

    new_coords = []
    new_flags = []
    new_endPts = []
    start = 0
    for end in endPts:
        for i in range(end, start - 1, -1):
            new_coords.append((coords[i][0], coords[i][1]))
            new_flags.append(flags[i])
        new_endPts.append(len(new_coords) - 1)
        start = end + 1

    glyph.coordinates = GlyphCoordinates(new_coords)
    glyph.flags = array.array('B', new_flags)
    glyph.endPtsOfContours = new_endPts


def _sanitize_ps_name(name):
    """PS name 只允许 ASCII 字母、数字、连字符"""
    ascii_only = re.sub(r'[^A-Za-z0-9\-]', '', name)
    if not ascii_only:
        return DEFAULT_FONT_NAME + '-Regular'
    return ascii_only + '-Regular'


def assemble_incremental(db, data_dir, font_path,
                         font_name=DEFAULT_FONT_NAME,
                         log=print, progress_callback=None):
    """组装字体
    progress_callback(current, total, desc) 可选
    """
    data_dir = Path(data_dir)
    font_path = Path(font_path)

    if not font_name or not font_name.strip():
        font_name = DEFAULT_FONT_NAME
    font_name = font_name.strip()

    all_rows = [r for r in db.all_chars() if r['svg_path'] and Path(r['svg_path']).exists()]
    if not all_rows:
        log("没有 SVG，无法组装")
        return None

    total = len(all_rows)
    log(f"开始组装：{total} 个字形，字体名称：{font_name}")
    log(f"FORCE_REVERSE = {FORCE_REVERSE}, DEFAULT_SCALE = {DEFAULT_SCALE}")

    glyph_order = ['.notdef'] + [f"uni{ord(r['char']):04x}" for r in all_rows]
    cmap = {ord(r['char']): f"uni{ord(r['char']):04x}" for r in all_rows}

    glyphs = {'.notdef': TTGlyphPen(None).glyph()}
    metrics = {'.notdef': (EM, 0)}

    ok = fail = 0
    for i, row in enumerate(all_rows, 1):
        char = row['char']
        glyph_name = f"uni{ord(char):04x}"

        if progress_callback:
            try:
                progress_callback(i - 1, total, f"组装 {char} ({i}/{total})")
            except Exception:
                pass

        try:
            svg_content = Path(row['svg_path']).read_text(encoding='utf-8')
            g, adv, lsb = _svg_to_glyph(
                svg_content,
                dy=row['dy'] or 0,
                dx=row['dx'] or 0,
                scale_override=row['scale'] if row['scale'] != 1.0 else None,
            )
            if g is None:
                g = TTGlyphPen(None).glyph()
                lsb = 0
                fail += 1
            else:
                ok += 1
            glyphs[glyph_name] = g
            metrics[glyph_name] = (adv, lsb)
        except Exception as e:
            log(f"  ✗ {char}: {e}")
            glyphs[glyph_name] = TTGlyphPen(None).glyph()
            metrics[glyph_name] = (EM, 0)
            fail += 1

    log(f"字形绘制：成功 {ok}，失败 {fail}")

    if progress_callback:
        try:
            progress_callback(total, total, "生成字体文件...")
        except Exception:
            pass

    fb = FontBuilder(EM, isTTF=True)
    fb.setupGlyphOrder(glyph_order)
    fb.setupCharacterMap(cmap)
    fb.setupGlyf(glyphs)
    fb.setupHorizontalMetrics(metrics)
    fb.setupHorizontalHeader(ascent=ASCENT, descent=-BASELINE_DESCENT)
    fb.setupNameTable({
        'familyName': font_name,
        'styleName': 'Regular',
        'uniqueFontIdentifier': f'{font_name} Regular 1.0',
        'fullName': f'{font_name} Regular',
        'psName': _sanitize_ps_name(font_name),
    })
    fb.setupOS2(
        sTypoAscender=ASCENT,
        sTypoDescender=-BASELINE_DESCENT,
        usWinAscent=ASCENT,
        usWinDescent=BASELINE_DESCENT,
    )
    fb.setupPost()

    font = fb.font
    font['OS/2'].ulCodePageRange1 |= (1 << 18) | (1 << 19)

    if FORCE_REVERSE:
        reversed_count = 0
        for glyph_name in font.getGlyphOrder():
            glyph = font['glyf'][glyph_name]
            if glyph.numberOfContours > 0:
                _reverse_glyph(glyph)
                reversed_count += 1
        log(f"强制反转了 {reversed_count} 个字形")

    for ch in ['一', '月', '国']:
        gn = f"uni{ord(ch):04x}"
        g = font['glyf'].get(gn)
        if g and g.numberOfContours > 0:
            adv, lsb = metrics.get(gn, (EM, 0))
            xs = [float(c[0]) for c in g.coordinates]
            ys = [float(c[1]) for c in g.coordinates]
            xmin = int(min(xs)) if xs else 0
            xmax = int(max(xs)) if xs else 0
            ymin = int(min(ys)) if ys else 0
            ymax = int(max(ys)) if ys else 0
            log(f"诊断 {ch}: bbox=({xmin},{ymin})-({xmax},{ymax}) 宽{xmax-xmin} 高{ymax-ymin} lsb={lsb} adv={adv}")

    font_path.parent.mkdir(parents=True, exist_ok=True)
    font.save(str(font_path))
    log(f"字体已保存：{font_path}")

    font_mtime = font_path.stat().st_mtime
    for row in all_rows:
        db.upsert_char(row['char'], in_font=1, font_mtime=font_mtime)

    return font_path