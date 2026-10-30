"""清空所有数据，重新开始"""
import shutil
from pathlib import Path

data_dir = Path(__file__).parent / 'data'

print("即将清空以下内容：")
print(f"  - {data_dir / 'project.db'}")
print(f"  - {data_dir / 'png_confirmed'}/")
print(f"  - {data_dir / 'png_unconfirmed'}/")
print(f"  - {data_dir / 'png'}/")
print(f"  - {data_dir / 'svg'}/")
print()

confirm = input("确认清空？输入 YES 继续: ").strip()
if confirm != 'YES':
    print("已取消")
    exit()

for p in [
    data_dir / 'project.db',
    data_dir / 'project.db-journal',
]:
    if p.exists():
        p.unlink()
        print(f"已删除 {p}")

for d in ['png_confirmed', 'png_unconfirmed', 'png', 'svg']:
    folder = data_dir / d
    if folder.exists():
        shutil.rmtree(folder)
        print(f"已删除 {folder}/")

print("✅ 清空完成，可以重新启动")