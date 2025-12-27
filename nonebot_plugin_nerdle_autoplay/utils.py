# 由 nonebot_plugin_nerdle 的 utils.py 修改而来
import json
from io import BytesIO
from pathlib import Path

from PIL import Image, ImageFont
from PIL.Image import Image as IMG

# 资源目录
RESOURCES_DIR = Path(__file__).parent / "resources"
FONTS_DIR = RESOURCES_DIR / "fonts"
DATA_DIR = RESOURCES_DIR / "data"

def load_font(name: str, fontsize: int):
    """加载字体"""
    try:
        font_path = FONTS_DIR / name
        return ImageFont.truetype(str(font_path), fontsize, encoding="utf-8")
    except:
        return ImageFont.load_default()

def save_png(frame: IMG) -> BytesIO:
    """保存图片为PNG格式"""
    output = BytesIO()
    frame = frame.convert("RGBA")
    frame.save(output, format="png")
    output.seek(0)
    return output

def create_resources_dirs():
    """创建资源目录"""
    FONTS_DIR.mkdir(parents=True, exist_ok=True)
    DATA_DIR.mkdir(parents=True, exist_ok=True)