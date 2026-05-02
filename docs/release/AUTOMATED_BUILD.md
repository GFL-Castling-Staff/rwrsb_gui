# GitHub Actions 自动构建说明

本项目的 Windows 发布包由 `.github/workflows/build-windows.yml` 构建。

## 产物结构

Action 会生成一个 7z 文件：

```text
dist/rwrsb_gui-v<版本号>-windows.7z
```

7z 内部包含：

```text
rwrsb_bind/
rwrsb_anim/
README.md
README_EN.md
LICENSE
VERSION
PACKAGE_README.md
```

## 手动触发构建

进入 GitHub 仓库页面：

1. 打开 `Actions`
2. 选择 `Build Windows package`
3. 点击 `Run workflow`
4. 构建完成后，在 workflow run 的 `Artifacts` 中下载 `rwrsb-windows-7z`

这种方式适合测试构建，不会自动创建 GitHub Release。

## 正式发布

正式发布时推送 tag：

```bat
git tag -a v1.1.0 -m "v1.1.0"
git push origin v1.1.0
```

Action 会自动：

1. 安装 Python 3.11
2. 创建 `.venv`
3. 安装 `requirements.txt`
4. 执行 `build.bat`
5. 执行 `scripts/package_release.ps1`
6. 上传 `dist/*.7z` 为 workflow artifact
7. 为 tag 创建 GitHub Release，并上传同一个 7z

如果存在 `docs/release/notes/RELEASE_NOTES_<tag>.md`，例如 `RELEASE_NOTES_v1.1.0.md`，Release 正文会使用该文件；否则使用 `docs/release/PACKAGE_README.md`。

## 本地生成同款 7z

本地先准备环境并构建：

```bat
setup.bat
build.bat
```

然后执行：

```powershell
.\scripts\package_release.ps1
```

输出文件位于 `dist/`。脚本依赖 7-Zip，需要 `7z.exe` 或 `7za.exe` 可用。
