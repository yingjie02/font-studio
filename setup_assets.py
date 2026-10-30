"""从 Docker 镜像里导出字体和字集资源到 data/assets/ 和 data/charsets/"""
import subprocess
from pathlib import Path

data_dir = Path(__file__).parent / 'data'
assets_dir = data_dir / 'assets'
charsets_dir = data_dir / 'charsets'
assets_dir.mkdir(parents=True, exist_ok=True)
charsets_dir.mkdir(parents=True, exist_ok=True)

DOCKER_IMAGE = "ghcr.io/yingjie02/wefont-docker:latest"

inner = (
    "cp /workspace/wefont/src/config/finder.png /workspace/assets/ && "
    "cp /workspace/wefont/src/config/fireflysung.ttf /workspace/assets/ && "
    "cp /workspace/wefont/src/config/gb2312*.txt /workspace/charsets/"
)

cmd = [
    "docker", "run", "--rm",
    "-v", f"{assets_dir.absolute()}:/workspace/assets",
    "-v", f"{charsets_dir.absolute()}:/workspace/charsets",
    DOCKER_IMAGE,
    "bash", "-c", inner,
]

print("导出资源...")
print(" ".join(cmd))
subprocess.run(cmd, check=True)

print("\n导出完成：")
for f in assets_dir.glob('*'):
    print(f"  assets/{f.name}  ({f.stat().st_size} bytes)")
for f in charsets_dir.glob('*.txt'):
    print(f"  charsets/{f.name}")