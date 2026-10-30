"""生成待写字的 PDF 模板（完整复刻 wefont 原版 generate_template.py）+ 缓存管理"""
import json
import os
import tempfile
import random
import string
import shutil
from pathlib import Path

try:
    from fpdf import FPDF
except ImportError:
    FPDF = None

try:
    import qrcode
except ImportError:
    qrcode = None


DEFAULT_CELL_SIZE = 20
DEFAULT_FONT_SIZE = 14

PAPER_LEFT_MARGIN = 15
PAPER_TOP_MARGIN = 10
CELL_INNER_MARGIN = 3

subx = 6
suby = 2

PAPER_LENGTH = 180
PAPER_WIDTH = 260


def _id_generator(size):
    chars = string.ascii_uppercase + string.digits
    return ''.join(random.choice(chars) for _ in range(size))


def _draw_qrcode(qrstr, qrname):
    qr = qrcode.QRCode(version=10, error_correction=qrcode.constants.ERROR_CORRECT_L)
    qr.add_data(qrstr)
    qr.make()
    im = qr.make_image()
    im.save(qrname)


def _fill_one_page(pdf, chars, total_num, page_num, cell_size,
                   num_of_cols, num_of_rows, font_name, font_size,
                   draw_sub, finder_path):
    cols_of_first_row = num_of_cols - 3
    cols_of_second_row = num_of_cols - 2

    qr_data = {
        "version": "1.0",
        "data": {
            "cell_size": cell_size,
            "text": "".join(chars),
        }
    }
    qrstr = json.dumps(qr_data)
    qrname = _id_generator(10) + ".png"
    _draw_qrcode(qrstr, qrname)

    pdf.set_fill_color(0, 0, 0)
    pdf.cell(cell_size, cell_size, "", 0, 0, 'C')

    # 左上 finder
    pdf.image(str(finder_path),
              PAPER_LEFT_MARGIN + CELL_INNER_MARGIN,
              PAPER_TOP_MARGIN + CELL_INNER_MARGIN,
              cell_size - 2 * CELL_INNER_MARGIN,
              cell_size - 2 * CELL_INNER_MARGIN)
    # 右下 finder
    pdf.image(str(finder_path),
              PAPER_LEFT_MARGIN + (num_of_cols - 1) * cell_size + CELL_INNER_MARGIN,
              PAPER_TOP_MARGIN + (num_of_rows - 1) * cell_size + CELL_INNER_MARGIN,
              cell_size - 2 * CELL_INNER_MARGIN,
              cell_size - 2 * CELL_INNER_MARGIN)
    # 左下 finder
    pdf.image(str(finder_path),
              PAPER_LEFT_MARGIN + CELL_INNER_MARGIN,
              PAPER_TOP_MARGIN + (num_of_rows - 1) * cell_size + CELL_INNER_MARGIN,
              cell_size - 2 * CELL_INNER_MARGIN,
              cell_size - 2 * CELL_INNER_MARGIN)

    # 二维码（占 2×2 格）
    pdf.image(qrname,
              PAPER_LEFT_MARGIN + (num_of_cols - 2) * cell_size + CELL_INNER_MARGIN,
              PAPER_TOP_MARGIN + CELL_INNER_MARGIN,
              2 * cell_size - CELL_INNER_MARGIN,
              2 * cell_size - CELL_INNER_MARGIN)

    os.remove(qrname)

    pdf.set_fill_color(255, 255, 255)

    line_num = 1
    processed_chars_num = 0
    for char in chars:
        total_num = total_num + 1

        pdf.cell(cell_size, cell_size, char, 0, 0, 'C')

        factor = 0
        if line_num == 1:
            factor = 1

        x1 = PAPER_LEFT_MARGIN + cell_size * (processed_chars_num + factor) + CELL_INNER_MARGIN
        y1 = PAPER_TOP_MARGIN + cell_size * (line_num - 1) + CELL_INNER_MARGIN
        x2 = x1 + cell_size - 2 * CELL_INNER_MARGIN
        y2 = y1 + cell_size - 2 * CELL_INNER_MARGIN
        pdf.line(x1, y1, x2, y1)
        pdf.line(x1, y1, x1, y2)
        pdf.line(x1, y2, x2, y2)
        pdf.line(x2, y1, x2, y2)

        if draw_sub:
            pdf.set_font(font_name, '', 8)
            sx = x2 - subx
            sy = y2 - suby
            pdf.text(sx, sy, str(total_num))
            pdf.set_font(font_name, '', font_size)

        processed_chars_num = processed_chars_num + 1

        if line_num == 1 and processed_chars_num == cols_of_first_row:
            pdf.ln()
            line_num = line_num + 1
            processed_chars_num = 0
        elif line_num == 2 and processed_chars_num == cols_of_second_row:
            pdf.ln()
            line_num = line_num + 1
            processed_chars_num = 0
        elif line_num == num_of_rows - 1 and processed_chars_num == num_of_cols:
            pdf.ln()
            line_num = line_num + 1
            processed_chars_num = 1
            pdf.cell(cell_size, cell_size, '', 0, 0, 'C')
        elif processed_chars_num == num_of_cols:
            pdf.ln()
            line_num = line_num + 1
            processed_chars_num = 0

    page_num = page_num + 1

    pdf.set_font(font_name, '', 10)
    px = PAPER_LEFT_MARGIN + num_of_cols * cell_size
    py = PAPER_TOP_MARGIN + num_of_rows * cell_size + 4
    pdf.text(px, py, str(page_num))
    pdf.set_font(font_name, '', font_size)

    pdf.set_fill_color(0, 0, 0)
    pdf.cell(cell_size, cell_size, "", 0, 0, 'C')
    pdf.ln()

    return total_num, page_num


def generate_template_pdf(chars, output_path, cell_size=DEFAULT_CELL_SIZE,
                          assets_dir=None, draw_sub=True, log=print):
    """生成待写 PDF 模板（完整复刻原版）"""
    if FPDF is None:
        raise RuntimeError("fpdf 未安装：pip install fpdf2")
    if qrcode is None:
        raise RuntimeError("qrcode 未安装：pip install qrcode[pil]")

    from core.paths import get_app_data_dir
    assets_dir = Path(assets_dir) if assets_dir else get_app_data_dir() / 'assets'
    finder_path = assets_dir / 'finder.png'
    font_path = assets_dir / 'fireflysung.ttf'

    if not finder_path.exists():
        raise FileNotFoundError(f"缺少 finder 图片：{finder_path}")
    if not font_path.exists():
        raise FileNotFoundError(f"缺少字体文件：{font_path}")

    num_of_cols = PAPER_LENGTH // cell_size
    num_of_rows = PAPER_WIDTH // cell_size
    num_of_chars_per_page = num_of_cols * num_of_rows - 7

    font_filename = str(font_path)
    font_name = font_path.stem
    font_size = int(cell_size / DEFAULT_CELL_SIZE * DEFAULT_FONT_SIZE)

    chars = list(chars)
    total = len(chars)
    if total == 0:
        log("没有需要生成的字")
        return None

    total_pages = (total + num_of_chars_per_page - 1) // num_of_chars_per_page
    log(f"共 {total} 字，每页 {num_of_chars_per_page} 格（{num_of_cols}列 × {num_of_rows}行 - 7），共 {total_pages} 页")
    log(f"字格 {cell_size}mm，字号 {font_size}pt")

    pdf = FPDF()
    pdf.set_author('Leeyukuang')
    pdf.set_title(f'gb2312 Chinese font set template cell size {cell_size}')
    pdf.set_margins(PAPER_LEFT_MARGIN, PAPER_TOP_MARGIN)
    pdf.add_page()

    pdf.set_draw_color(230, 225, 225)
    pdf.set_text_color(200, 200, 200)
    pdf.add_font(font_name, '', font_filename)
    pdf.set_font(font_name, '', font_size)

    chars_of_this_page = []
    cnt = 0
    total_num = 0
    page_num = 0

    for char in chars:
        cnt += 1
        if cnt <= num_of_chars_per_page:
            chars_of_this_page.append(char)

        if cnt == num_of_chars_per_page:
            total_num, page_num = _fill_one_page(
                pdf, chars_of_this_page, total_num, page_num,
                cell_size, num_of_cols, num_of_rows,
                font_name, font_size, draw_sub, finder_path
            )
            log(f"  第 {page_num} 页完成")
            cnt = 0
            chars_of_this_page = []

    if len(chars_of_this_page):
        total_num, page_num = _fill_one_page(
            pdf, chars_of_this_page, total_num, page_num,
            cell_size, num_of_cols, num_of_rows,
            font_name, font_size, draw_sub, finder_path
        )
        log(f"  第 {page_num} 页完成（尾页）")

    pdf.output(str(output_path))
    log(f"PDF 已生成：{output_path}")
    return output_path


# ============================================================
# 缓存管理：预设字集 PDF 按参数缓存
# ============================================================

def get_or_create_cached_pdf(chars, cache_key, cell_size, draw_sub,
                              cache_dir, assets_dir, log=print):
    """按 cache_key 缓存完整预设字集的 PDF
    返回 (pdf_path, from_cache)
    """
    cache_dir = Path(cache_dir)
    cache_dir.mkdir(parents=True, exist_ok=True)
    cache_path = cache_dir / f"{cache_key}.pdf"

    if cache_path.exists():
        size_mb = cache_path.stat().st_size / 1024 / 1024
        log(f"✅ 命中缓存：{cache_path.name} ({size_mb:.1f}MB)")
        return cache_path, True

    log(f"📝 首次生成：{cache_path.name}")
    generate_template_pdf(
        sorted(chars), cache_path,
        cell_size=cell_size,
        assets_dir=assets_dir,
        draw_sub=draw_sub,
        log=log,
    )
    return cache_path, False


def list_cache_files(cache_dir):
    """列出缓存目录的所有 PDF"""
    cache_dir = Path(cache_dir)
    if not cache_dir.exists():
        return []
    files = sorted(cache_dir.glob('*.pdf'), key=lambda f: -f.stat().st_mtime)
    return [
        {'name': f.name, 'size_mb': f.stat().st_size / 1024 / 1024}
        for f in files
    ]


def clear_cache_dir(cache_dir):
    """清空缓存目录"""
    cache_dir = Path(cache_dir)
    if cache_dir.exists():
        for f in cache_dir.glob('*.pdf'):
            try:
                f.unlink()
            except Exception:
                pass
    cache_dir.mkdir(parents=True, exist_ok=True)