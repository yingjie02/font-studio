"""字符预览：用当前字体或 SVG 渲染单个字/网格"""
from pathlib import Path
from PIL import Image, ImageDraw, ImageFont


def render_char_from_svg(svg_path, size=128, bg='white', fg='black'):
    """从 SVG 直接渲染单字（简易版，只画 path 轮廓）"""
    # 简化：直接读取 PNG，因为 PNG 就是字形的光栅图
    # 完整的 SVG 渲染需要 cairosvg 或类似库，这里先用 PNG
    png_path = Path(svg_path).parent.parent / 'png' / (Path(svg_path).stem + '.png')
    if not png_path.exists():
        return Image.new('RGB', (size, size), bg)
    img = Image.open(png_path).convert('RGB')
    img.thumbnail((size, size), Image.LANCZOS)
    canvas = Image.new('RGB', (size, size), bg)
    canvas.paste(img, ((size - img.width) // 2, (size - img.height) // 2))
    return canvas


def render_grid(db, size=64, cols=10, bg='white', fg='black'):
    """渲染所有字的网格图"""
    rows_data = db.all_chars()
    total = len(rows_data)
    if total == 0:
        return Image.new('RGB', (cols * size, size), bg)

    nrows = (total + cols - 1) // cols
    grid = Image.new('RGB', (cols * size, nrows * size), bg)
    draw = ImageDraw.Draw(grid)

    for i, row in enumerate(rows_data):
        r, c = divmod(i, cols)
        svg_path = row['svg_path']
        if not svg_path or not Path(svg_path).exists():
            continue
        png_path = Path(svg_path).parent.parent / 'png' / (Path(svg_path).stem + '.png')
        if not png_path.exists():
            continue
        try:
            img = Image.open(png_path).convert('L')
            img.thumbnail((size - 8, size - 8), Image.LANCZOS)
            thumb = Image.new('RGB', (size, size), bg)
            thumb.paste(Image.merge('RGB', [img, img, img]),
                        (c * size + (size - img.width) // 2, r * size + (size - img.height) // 2))
            grid.paste(thumb, (c * size, r * size))
        except Exception:
            pass

    return grid


def render_paragraph(text, font_path, size=48, bg='white', fg='black'):
    """用生成的 TTF 渲染一段文字"""
    try:
        font = ImageFont.truetype(str(font_path), size)
    except Exception:
        font = ImageFont.load_default()

    # 计算尺寸
    dummy = Image.new('RGB', (1, 1))
    bbox = ImageDraw.Draw(dummy).multiline_textbbox((0, 0), text, font=font)
    w = bbox[2] - bbox[0] + 40
    h = bbox[3] - bbox[1] + 40

    img = Image.new('RGB', (max(w, 200), max(h, 100)), bg)
    draw = ImageDraw.Draw(img)
    draw.multiline_text((20, 20), text, font=font, fill=fg)
    return img