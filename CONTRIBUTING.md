# 参与贡献

> [English](CONTRIBUTING_EN.md)

## 项目当前状态

rwrsb 处于**维护期**：核心功能（骨架绑定编辑、动画工具、打包发布）已基本完成，后续主要做 bug 修复和小幅改进。RWR2 推出后可能有新的功能需求，欢迎提 issue 讨论。

没有自动化测试——所有改动依赖手动验证。

## 报 Bug

请在 GitHub 开 issue，标题用中文描述问题现象（如"导入含中文路径的 VOX 文件时崩溃"）。

**附上以下信息更容易定位问题：**

- `logs/` 目录下最新一份日志文件（路径一般在 `dist\rwrsb_bind\logs\` 或 `%LOCALAPPDATA%\rwrsb_gui\logs\`）
- 复现步骤（用了什么文件、做了什么操作、出现了什么结果）
- 操作系统版本和 Python 版本（如果是源码运行）

## 提建议

功能建议推荐先在 **RWR mod 交流群**里 @ SAIWA 讨论，确认方向后再开 issue 跟踪。这样可以避免做到一半才发现方向不对。

不确定的小改进也可以直接开 issue 描述想法，不需要先写代码。

## 提 Pull Request

1. Fork 本仓库，在本机跑 `setup.bat` 初始化环境
2. 从 `main` 创建分支，命名如 `feat/xxx` 或 `fix/xxx`
3. 修改代码，**不要引入新的第三方依赖**
4. commit 使用 [Conventional Commits](https://www.conventionalcommits.org/) 风格：
   - `feat: 新功能`
   - `fix: bug 修复`
   - `docs: 文档改动`
   - `refactor: 重构（不改行为）`
5. PR 描述里说明：**改了什么**、**怎么手动验证**、**是否影响 XML 导入导出格式**

改动骨架逻辑或坐标变换时，请特别验证：视口拖拽、面板编辑、预设保存/加载、undo/redo、XML 导出、删除 stick 后的绑定重排。这几个路径最容易互相干扰。

## 测试说明

本项目**没有自动化测试**。改完之后请参照 [RELEASE.md](RELEASE.md) 里的"发版前检查清单"手动跑一遍，确认主要功能没有退化。
