# rwrsb_bind v1.0.0 发版说明

> [English](RELEASE_NOTES_v1.0.0_EN.md)

## 重要变更：工具重命名

`rwrsb_gui.exe` 已重命名为 **`rwrsb_bind.exe`**。

原名称 `rwrsb_gui` 过于模糊（两个工具都是 GUI），`rwrsb_bind` 更直接地传达"骨架绑定编辑器"的实际语义。v1.0.0 版本号跳变是这次 breaking change 的信号。

**升级时建议的操作：**

1. 下载新版 `rwrsb_bind-v1.0.0-windows.zip`，解压到任意目录
2. 手动删除旧的 `dist\rwrsb_gui\` 目录（可选，不影响新版运行，但旧目录不会自动清理）
3. 用新的 `rwrsb_bind.exe` 替换桌面快捷方式或启动脚本

日志目录保持不变（仍位于 `%LOCALAPPDATA%\rwrsb_gui\logs\` 或 exe 同级 `logs\`），历史日志不受影响。

---

## 本次改动内容

### 规范化与文档

- 新增 `LICENSE`（MIT，2025-2026，SAIWA）
- 新增 `ARCHITECTURE.md`：9 节架构概览，涵盖 EditorState 字段分组、tool_mode 三态、修饰键统一表、动画模式切换、5 种 dirty flag 等隐式知识
- 新增 `CONTRIBUTING.md`：报 bug / 提建议 / 提 PR 流程说明
- `README.md`：修复硬编码本地路径，加截图占位（待项目主截图后替换 `docs/screenshot.png`）
- `editor_state.py`：EditorState class docstring（9 分组）；_snapshot / _restore_snapshot / StickEntry.clone 三处 docstring 说明 visible 通道设计决策
- `ui_panels.py`：UIState class docstring
- `camera.py`：OrbitCamera class docstring
- `xml_io.py`：parse_vox / parse_xml / write_xml 加类型标注
- `renderer.py`：box_select_voxels / pick_particle_screen / box_select_particles 加类型标注

### 重命名（Breaking Change）

- `rwrsb_gui.spec` → `rwrsb_bind.spec`
- 窗口标题 `rwrsb v2.0` → `rwrsb_bind v1.0.0`
- build.bat、README.md、RELEASE.md 内所有工具名引用同步更新
- `logger_setup.py` 日志路径**有意保留** `rwrsb_gui`，确保历史日志不变为孤岛

---

## 发版前项目主需要手动做的事

- [ ] 运行 `python main.py`，截编辑器主界面图，保存为 `docs/screenshot.png`，删除 `docs/screenshot.placeholder.txt`
- [ ] 运行 `build.bat`，确认输出在 `dist\rwrsb_bind\rwrsb_bind.exe`
- [ ] 启动 `dist\rwrsb_bind\rwrsb_bind.exe`，确认窗口标题显示 `rwrsb_bind v1.0.0`
- [ ] 启动 `dist\rwrsb_anim\rwrsb_anim.exe`（或 `python main_animation.py`），确认动画工具未受影响
- [ ] 在仓库根目录 grep `rwrsb_gui`，确认只剩 `RELEASE_NOTES_v0.1.0.md`（历史文档）和 `logger_setup.py`（有意保留）
