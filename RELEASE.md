# 发版说明

这份文档用于说明如何把当前项目整理成 GitHub Release。

## 推荐发版流程

1. 确认工作区干净，没有未预期的修改
2. 先用源码运行一次，确认基本功能正常
3. 执行 `build.bat` 生成 Windows 发布包
4. 在本机测试 `dist\rwrsb_bind\rwrsb_bind.exe`
5. 把整个 `dist\rwrsb_bind` 文件夹压缩成 zip
6. 确认版本号和 tag，例如 `v0.1.0`
7. 在 GitHub 上创建 Release
8. 上传 zip 包，并粘贴对应版本说明

## build.bat 的作用

`build.bat` 是当前项目的标准打包入口。

它会自动完成：

1. 检查虚拟环境是否存在
2. 激活 `.venv`
3. 自动安装 `PyInstaller`（如果缺失）
4. 清理旧的 `build/` 和 `dist/`
5. 根据 [rwrsb_bind.spec](rwrsb_bind.spec) 重新构建发布包

执行方式：

```bat
build.bat
```

输出结果：

```text
dist\rwrsb_bind\rwrsb_bind.exe
```

注意：

- 发布时建议压缩整个 `dist\rwrsb_bind`，不要只单独发 exe
- 因为运行时还需要 `_internal/`、资源文件和依赖 DLL

## 推荐上传的发布物

建议文件名：

- `rwrsb_bind-v1.0.0-windows.zip`

zip 内应包含：

- `rwrsb_bind.exe`
- PyInstaller 生成的 `_internal/`
- `shaders/`
- `presets/`

## Release 页面建议填写内容

建议标题：

- `rwrsb_bind v1.0.0`

建议正文：

- 可以直接使用 [RELEASE_NOTES_v1.0.0.md](RELEASE_NOTES_v1.0.0.md)

## 发版前检查清单

- `.vox` 读取正常
- `.xml` 读取正常
- XML 导出正常
- 粒子拖拽正常
- 网格显示和吸附正常
- 中英切换正常
- UI 缩放正常
- 反转 Y 轴正常
- 预设保存和加载正常
- 打包后的 exe 能在本机启动

## 已知现实问题

- OpenGL 类程序是否能稳定运行，仍取决于目标机器驱动
- 目录版发布通常比单文件版更稳
- 如果目标机器缺少系统运行库或显卡环境异常，仍可能需要单独排查
