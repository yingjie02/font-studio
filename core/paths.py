"""统一的路径解析：兼容开发环境和 PyInstaller 打包环境"""
import os
import sys
from pathlib import Path


def is_frozen():
    return getattr(sys, 'frozen', False)


def get_resource_path(relative_path=''):
    """只读资源：assets、charsets、代码。
    开发时 = 项目根目录
    打包后 = sys._MEIPASS（只读临时解压目录）
    """
    if is_frozen():
        base = Path(sys._MEIPASS)
    else:
        base = Path(__file__).resolve().parent.parent
    return base / relative_path if relative_path else base


def get_app_data_dir():
    """可写数据：project.db、png_confirmed、svg、font.ttf。
    开发时 = 项目根/data
    打包后 = %APPDATA%/font-studio/data
    """
    if is_frozen():
        appdata = os.environ.get('APPDATA') or str(Path.home() / 'AppData' / 'Roaming')
        base = Path(appdata) / 'font-studio' / 'data'
    else:
        base = Path(__file__).resolve().parent.parent / 'data'
    base.mkdir(parents=True, exist_ok=True)
    return base