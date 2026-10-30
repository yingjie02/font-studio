# Font Studio · 字体工坊

**把中文手写扫描件变成可用的 TTF 字体。** 全程本地，无需上传。

[wefont](https://github.com/wenzhenl/wefont) 的现代化重写：**Python 3 + Gradio + fonttools** 替代了 Python 2.7 + FontForge，增加了图形界面、单字级断点续传、模板缓存、单字微调、备份恢复。

## 为什么不用 wefont？

| wefont | Font Studio |
| :--- | :--- |
| Python 2.7 + FontForge，环境配置复杂 | Python 3.10+，`pip install` 即可 |
| 纯命令行 | 6 个 Tab 的 Gradio 界面 |
| 中断后重新处理全部 | 每个字独立状态，只处理变更部分 |
| 无单字微调 | 每字可调 dy / dx / scale |
| 模板每次重生成 | 完整预设按参数缓存 |

## 核心流程

```
① 生成待写 PDF → 打印 → 手写 → 扫描
                                    ↓
② 上传扫描件 → 自动提取单字 PNG
                                    ↓
③ PNG 管理 → 确认 / PS 修改 / 删除
                                    ↓
④ 字体微调 → 调每字位置和缩放
                                    ↓
⑤ 导出字体 → 矢量化 → 组装 TTF → 安装
                                    ↓
⑥ 段落预览 → 验证效果
```

## 环境要求

- **Python 3.10+**
- **Docker Desktop**（仅 Tab ② 扫描件提取需要，其他 Tab 不需要）

## 快速开始

```bash
git clone https://github.com/<你的用户名>/font-studio.git
cd font-studio

python -m venv venv
# Windows:  .\venv\Scripts\activate
# macOS/Linux:  source venv/bin/activate

pip install -r requirements.txt

# 一次性拉取提取镜像（约 500MB）
docker pull ghcr.io/yingjie02/wefont-docker:latest

# 一次性导出模板资源（finder.png + 参考字体 + 字集）
python setup_assets.py

# 启动
python app.py
```

浏览器打开 **http://127.0.0.1:7860**。

## 关键特性

- **断点续传**：每个字的 PNG / SVG / 组装状态独立记录，中断后重跑只处理变更
- **文件夹即状态**：已确认的字在 `data/png_confirmed/`，未确认在 `data/png_unconfirmed/`，直接拖文件也能改状态
- **单字微调**：每字独立调 `dy`（垂直）/ `dx`（水平）/ `scale`（缩放），滑块实时预览
- **模板缓存**：完整预设 PDF 按 `(字集, 字格大小, 序号开关)` 缓存，同参数秒出
- **备份恢复**：一键打包所有数据为 zip，恢复时已确认优先
- **Word 兼容**：生成的字体自动修复 `name` 表和 `OS/2` 表，Word 里不回退到等线

## 相关项目

- [wefont](https://github.com/wenzhenl/wefont) — 原始项目（Python 2.7 + FontForge）
- [wefont-docker](https://github.com/yingjie02/wefont-docker) — 本项目使用的提取镜像

## License

MIT（或遵循 wefont 原始许可）
