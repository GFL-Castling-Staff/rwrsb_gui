# rwrsb_gui

这是一个面向 RWR 风格资源的体素骨架绑定编辑器。

它可以直接读取 `.vox` 或项目 XML，编辑骨架结构与体素绑定关系，并导出回目标 XML 格式。当前版本的重点是“可实用地编辑和复用骨架”，而不只是给默认人骨重新绑点。

## 功能概览

- 读取 MagicaVoxel `.vox`
- 读取项目使用的 XML
- 编辑 `particle` 节点
- 编辑 `stick` 连线
- 给体素重新绑定骨段
- 保存和复用骨架预设
- 在视口中直接拖拽粒子点
- 网格显示、主次网格和网格吸附
- 中英双语界面
- UI 缩放
- 相机 Y 轴反转
- 导出 XML

## 运行环境

- Windows
- Python 3.10+
- 可用的 OpenGL 驱动

项目主要依赖：

- `moderngl`
- `glfw`
- `imgui[glfw]`
- `numpy`

## 快速开始

首次初始化环境：

```bat
setup.bat
```

启动编辑器：

```bat
run.bat
```

也可以直接运行：

```bat
.venv\Scripts\python main.py
```

如果要直接打开一个文件：

```bat
.venv\Scripts\python main.py path\to\model.vox
```

## 动画编辑器（rwrsb_anim.exe）

`rwrsb_anim` 是本仓库的第二个工具，用于制作和修改 RWR soldier XML 动画。

启动命令：

```bat
.venv\Scripts\python main_animation.py
```

### 启动行为

启动后自动加载内置的 vanilla 人形骨架（15 粒子），并自动进入空白动画编辑模式，可以直接开始 K 帧。

### 三种工作流

**A. 基础新建**

直接拖动粒子摆姿势 → 添加帧 → 在时间线调整帧时间 → 保存为 XML。

**B. 修改 vanilla 动画**

工具栏点 "加载动画" → 选 `soldier_animations.xml` → 在动画列表选 `walking`（或其他） → 编辑帧 → 保存。

**C. 异形骨骨架**

工具栏点 "Open Skeleton" → 选自定义 skeleton XML（必须恰好 15 个 particle）→ 新建或加载动画 → 编辑 → 保存。

也可以直接把 XML 文件拖到窗口，工具会自动判断是骨架文件还是动画文件。

### 文件兼容性

- 输出 XML 格式与 `soldier_animations.xml` 兼容，可直接被 RWR 引擎读取
- `rwrac.exe` 导出的动画 XML 可以作为输入加载（注意 rwrac 的 particle name 字段通常带 `.dae` 后缀，加载后动画数据可用，但如有依赖粒子名的逻辑需手动修正 name）

### 网格吸附

工具栏 "Grid..." 按钮可开关视口网格和粒子拖动吸附。支持 0.5 / 1 / 自定义 步长，三个平面（XZ / XY / YZ）可独立开关。

### 骨段长度检查

动画面板右下角 "Check stick lengths" 复选框，开启后实时显示相对于第 0 帧参考长度偏差超过阈值的骨段，并在视口中用红色高亮。默认阈值 1%（与 vanilla 动画的自然漂移量匹配）。

### 待实现

- Mixamo 动画导入（工具栏 "Import Mixamo" 按钮当前为禁用状态）

## build.bat 怎么用

`build.bat` 是项目的一键打包脚本，用来把当前工程打成 Windows 可分发目录包。

直接运行：

```bat
build.bat
```

它会自动做这几件事：

1. 检查 `.venv` 是否存在
2. 激活虚拟环境
3. 如果还没安装 `PyInstaller`，自动安装
4. 删除旧的 `build/` 和 `dist/`
5. 按 [rwrsb_gui.spec](D:/IMP/RWR/模型相关/【rwrsb_gui_v2】/rwrsb_gui_v2.2/rwrsb_gui/rwrsb_gui.spec) 重新打包

打包成功后，输出位置是：

```text
dist\rwrsb_gui\rwrsb_gui.exe
```

发布时建议不要只拿单个 exe，而是把整个 `dist\rwrsb_gui` 文件夹压缩成 zip 再发。

原因是这个目录里除了 exe 之外，还会包含：

- PyInstaller 运行时文件
- `shaders/`
- `presets/`
- `glfw3.dll` 等打包资源

## 编辑流程

1. 打开 `.vox` 或 `.xml`
2. 在右侧面板检查或编辑骨架
3. 新增、修改或删除 `particle` / `stick`
4. 用 `brush` 或 `select` 做体素绑定
5. 在视口中拖动粒子点微调骨架
6. 保存为 XML
7. 如有需要，把当前骨架另存为预设

## 编辑说明

- `particle` 是骨架节点，包含位置和元数据
- `stick` 连接两个粒子，对应一个绑定约束组
- 绑定关系依赖 `constraintIndex`
- `constraintIndex` 必须和当前 stick 顺序保持一致
- 删除或重排 stick 时，必须同步修正绑定映射
- 网格步长支持 `0.5`、`1`、或任意正整数体素
- 网格平面可以分别启用 `XZ / XY / YZ`
- 视口拖拽粒子支持轴约束：
  - `Shift`: 锁 X
  - `Ctrl`: 锁 Y
  - `Alt`: 锁 Z

## 项目结构

- `main.py`
  - 绑骨工具主入口（`rwrsb_gui.exe`）
  - GLFW 窗口生命周期
  - 输入事件
  - 视口拖拽
  - UI 生效逻辑
- `main_animation.py`
  - 动画工具主入口（`rwrsb_anim.exe`）
  - 粒子拾取/拖动、drop 加载
  - 动画播放主循环
- `animation_io.py`
  - `Animation` / `AnimationFrame` 数据类
  - soldier animation XML 解析与写出
  - 帧间插值
- `editor_state.py`
  - 可编辑项目状态
  - Undo/Redo
  - 骨架 CRUD
  - 绑定数据
  - 预设 CRUD
- `ui_panels.py`
  - 右侧面板和弹窗
  - 中英双语文案
  - UI 设置项
- `renderer.py`
  - 体素渲染
  - 骨架渲染
  - 粒子拾取
  - 网格渲染
- `camera.py`
  - Orbit / Ortho 相机
  - 视角预设
  - 射线构造
- `xml_io.py`
  - `.vox` 解析
  - XML 解析
  - XML 写出
  - 坐标转换
- `resource_utils.py`
  - 统一资源路径
  - 兼容源码运行和 PyInstaller 打包
- `presets/`
  - 骨架预设 JSON
- `shaders/`
  - GLSL 着色器

## XML 数据模型

XML 工作流主要围绕三块数据：

- `voxels`
  - 体素位置和颜色
- `skeleton`
  - `particle`
  - `stick`
- `skeletonVoxelBindings`
  - `group constraintIndex="..."`
  - 属于某个骨段组的体素索引

几个关键约束：

- Particle ID 必须唯一
- Stick 两端必须引用存在的粒子
- `group.constraintIndex` 必须等于 stick 的下标
- 编辑骨架后，导出时必须保留正确的绑定关系

## 预设

骨架预设保存在 `presets/` 下的 JSON 文件中。

当前仓库内已有：

- `human_skeleton.json`
- `88.json`

预设只保存骨架结构：

- particles
- sticks

体素绑定属于具体项目数据，不作为预设的一部分。

## 给开发者的说明

- 新机器先跑 `setup.bat`
- `.venv/` 只保留在本地，不要提交
- 不要提交 `__pycache__/`
- 如果改了解析或导出逻辑，至少要测一次 `.vox` 和 `.xml`
- 坐标转换改动要特别小心，它会同时影响导入和导出
- stick 删除和重排最容易把 binding 搞坏，修改时要重点验证

## 给 AI 接手者的说明

如果后续要继续扩展这个项目，建议先读：

- [main.py](D:/IMP/RWR/模型相关/【rwrsb_gui_v2】/rwrsb_gui_v2.2/rwrsb_gui/main.py)
- [editor_state.py](D:/IMP/RWR/模型相关/【rwrsb_gui_v2】/rwrsb_gui_v2.2/rwrsb_gui/editor_state.py)
- [xml_io.py](D:/IMP/RWR/模型相关/【rwrsb_gui_v2】/rwrsb_gui_v2.2/rwrsb_gui/xml_io.py)
- [ui_panels.py](D:/IMP/RWR/模型相关/【rwrsb_gui_v2】/rwrsb_gui_v2.2/rwrsb_gui/ui_panels.py)

建议遵守的边界：

- `editor_state.py` 负责状态和业务规则
- `renderer.py` 负责绘制与拾取
- `ui_panels.py` 负责界面调用，不要重复实现业务逻辑
- `xml_io.py` 负责文件格式解析与写出

如果改动骨架逻辑，至少一起检查：

- 视口拖拽
- 面板编辑
- 预设保存/加载
- undo/redo
- XML 导出
- 删除 stick 后的绑定重排

## Git 清洁

仓库会忽略这些本地产物：

```gitignore
.venv/
__pycache__/
*.py[cod]
build/
dist/
```

如果这些文件以后又被误跟踪，应该把它们从 Git 索引里移除，而不是直接删本地文件。

## 发布

发版流程见 [RELEASE.md](D:/IMP/RWR/模型相关/【rwrsb_gui_v2】/rwrsb_gui_v2.2/rwrsb_gui/RELEASE.md)。

本次版本说明稿见 [RELEASE_NOTES_v0.1.0.md](D:/IMP/RWR/模型相关/【rwrsb_gui_v2】/rwrsb_gui_v2.2/rwrsb_gui/RELEASE_NOTES_v0.1.0.md)。

## 已知限制

- 最终运行效果仍然建议在本机 OpenGL 环境里实际验证
- 当前 XML 兼容性是面向本项目格式，不是任意通用 schema
- 当前发布包是目录版，不是单文件版 exe

## License

本项目采用 MIT License，详见 [LICENSE](LICENSE) 文件。
