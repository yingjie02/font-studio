"""扫描件上传：调用 Docker 基础镜像解析 JPG → PNG（保存到 png_unconfirmed/）
使用基础版镜像，保留所有笔画细节（不降噪，避免点/顿被误删）
"""
import subprocess
from pathlib import Path


# 基础版镜像（保留所有笔画）
DOCKER_IMAGE = "ghcr.io/yingjie02/wefont-docker:latest"

# 如果你想用本地构建的镜像，改成：
# DOCKER_IMAGE = "wefont-cn-base"


def check_docker(log=print):
    """检查 Docker 和镜像是否可用"""
    try:
        r = subprocess.run(['docker', 'ps'], capture_output=True, text=True, timeout=10)
        if r.returncode != 0:
            return False, "Docker 未运行"
    except FileNotFoundError:
        return False, "Docker 未安装"
    except Exception as e:
        return False, f"Docker 错误: {e}"

    try:
        r = subprocess.run(
            ['docker', 'image', 'inspect', DOCKER_IMAGE],
            capture_output=True, text=True, timeout=10
        )
        if r.returncode != 0:
            return False, (
                f"镜像 {DOCKER_IMAGE} 不存在，请先：\n"
                f"docker pull ghcr.io/yingjie02/wefont-docker:latest"
            )
    except Exception as e:
        return False, f"检查镜像失败: {e}"

    return True, f"Docker 就绪，镜像 {DOCKER_IMAGE} 可用（基础版，不降噪）"


def extract_one(jpg_path, png_dir, log=print):
    jpg_path = Path(jpg_path).absolute()
    png_dir = Path(png_dir).absolute()
    png_dir.mkdir(parents=True, exist_ok=True)

    inner = (
        "cd /workspace/wefont/src && "
        "rm -f uni*.png && "
        f"python parse_template.py '/workspace/input/{jpg_path.name}' && "
        "cp uni*.png /workspace/png/"
    )
    cmd = [
        "docker", "run", "--rm",
        "-v", f"{jpg_path.parent}:/workspace/input:ro",
        "-v", f"{png_dir}:/workspace/png",
        DOCKER_IMAGE,
        "bash", "-c", inner,
    ]
    log(f"  → docker run ... {jpg_path.name}")
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        err = (result.stderr or result.stdout or "")[:500]
        raise RuntimeError(f"Docker exit {result.returncode}: {err}")
    return True


def extract_uploaded(files, data_dir, db, log=print):
    """提取到 png_unconfirmed/"""
    png_dir = Path(data_dir) / 'png_unconfirmed'
    png_dir.mkdir(parents=True, exist_ok=True)

    if not files:
        log("没有上传文件")
        return 0

    log(f"开始处理 {len(files)} 个文件")
    total_new = 0
    for i, f in enumerate(files, 1):
        src = Path(f) if isinstance(f, (str, Path)) else Path(f.name)
        log(f"[{i}/{len(files)}] {src.name}")

        try:
            extract_one(src, png_dir, log=log)
        except Exception as e:
            log(f"  ✗ 失败: {e}")
            continue

        # 注册新 PNG
        new_count = 0
        for png in png_dir.glob('uni*.png'):
            hex_code = png.stem[3:]
            try:
                char = chr(int(hex_code, 16))
            except ValueError:
                continue
            existing = db.get_char(char)
            # 如果已确认，跳过（已确认的优先）
            if existing and existing['confirmed'] == 1:
                continue
            if not existing or not existing['png_path'] or not Path(existing['png_path']).exists():
                db.upsert_char(
                    char,
                    png_path=str(png.absolute()),
                    png_mtime=png.stat().st_mtime,
                    confirmed=0,
                )
                new_count += 1
        log(f"  本次新增 {new_count} 个字")
        total_new += new_count

    # 最后从文件夹同步一次（保证 DB 状态准确）
    db.sync_from_folders()

    log(f"全部完成，本次共新增 {total_new} 个字")
    return total_new