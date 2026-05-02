# RWRSB Windows 发布包说明

这个 7z 包用于直接分发给 Windows 用户。解压后根目录包含：

- `rwrsb_bind/`：骨架与绑定编辑器，入口为 `rwrsb_bind\rwrsb_bind.exe`
- `rwrsb_anim/`：动画编辑器，入口为 `rwrsb_anim\rwrsb_anim.exe`
- `README.md` / `README_EN.md`：项目说明
- `LICENSE`：许可证
- `VERSION`：版本号

运行时请保留整个文件夹结构，不要只复制单个 `.exe`。PyInstaller 生成的 `_internal/`、`shaders/`、`presets/` 和依赖 DLL 都是运行所需文件。

如果程序无法启动，请优先确认：

- 显卡驱动和 OpenGL 环境正常
- 解压路径可写，且没有被安全软件隔离 DLL
- `rwrsb_bind.exe` 或 `rwrsb_anim.exe` 是从各自完整目录中启动的
