# RWRSB - rwrsb_bind + rwrsb_anim

> [English](README_EN.md)

`rwrsb_bind` 是一个面向 RWR 风格资源的体素骨架绑定编辑器。

它可以直接读取 `.vox` 或项目 XML，编辑骨架结构与体素绑定关系，并导出回目标 XML 格式。当前版本的重点是”可实用地编辑和复用骨架”，而不只是给默认人骨重新绑点。

![rwrsb_bind screenshot](docs/screenshot.png)

## 功能概览

- 读取 MagicaVoxel `.vox`
- 读取项目使用的 XML
- 编辑 `particle` 节点
- 编辑 `stick` 连线
- 给体素重新绑定骨段
- 保存和复用骨架预设
- 在视口中直接拖拽粒子点
- **Blender 风格选区 gizmo**（3 轴箭头 + 圆环），点把手锁轴平移 / 旋转，支持 Active / 中心 / 世界原点三种旋转中心
- 世界原点 RGB 三轴指示
- 网格显示、主次网格和网格吸附
- 中英双语界面
- UI 缩放
- 相机 Y 轴反转
- 导出 XML
- 导出 MagicaVoxel `.vox`（仅体素，不含骨架与绑定）
- 默认进入体素框选模式（避免误涂）

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

工具栏点 "Open Skeleton" → 选自定义 skeleton XML（必须恰好 17 根 stick，粒子建议不少于 13 个）→ 新建或加载动画 → 编辑 → 保存。

也可以直接把 XML 文件拖到窗口，工具会自动判断是骨架文件还是动画文件。

### 文件兼容性

- 输出 XML 格式与 `soldier_animations.xml` 兼容，可直接被 RWR 引擎读取
- 能读取游戏 1.98.1 自带的 `soldier_animations.xml`（其中含 `<!-- ---- -->` 这种不合规注释，工具会先剥掉注释再解析）
- `rwrac.exe` 导出的动画 XML 可以作为输入加载（注意 rwrac 的 particle name 字段通常带 `.dae` 后缀，加载后动画数据可用，但如有依赖粒子名的逻辑需手动修正 name）

### 网格吸附

工具栏 "Grid..." 按钮可开关视口网格和粒子拖动吸附。支持 0.5 / 1 / 自定义 步长，三个平面（XZ / XY / YZ）可独立开关。

### 骨段长度检查

动画面板右下角 "Check stick lengths" 复选框，开启后实时显示相对于第 0 帧参考长度偏差超过阈值的骨段，并在视口中用红色高亮。默认阈值 1%（与 vanilla 动画的自然漂移量匹配）。

### 选区 gizmo / 蒙皮 / 体素朝向

- 选中粒子后视口出现 Blender 风格 3 轴 gizmo：拖箭头沿轴平移、拖圆环绕轴旋转（Ctrl 15° 吸附）、拖中心球自由平移。两个工具的圆环旋转中心都跟随工具栏下拉框，可选 Active 粒子、选区几何中心或世界原点；修饰键 Shift/Ctrl/Alt 仍可作为快捷锁轴方式直接拖粒子。
- 蒙皮：默认「引擎精确」规则，与游戏一致——每根骨段的扭转按它在 XML 里的下标（0–16）查固定的表，参考方向取自粒子 1、2、3、4、5、8、9、10、11、12；原点是骨段的 a 端粒子；前臂继承上臂坐标系。**粒子和骨段的顺序本身有语义**，做异形骨时要留意。旧版的"查表 / 拓扑邻居"规则保留在动画面板的「蒙皮规则」下拉里作对比；粒子少于 13 个等情况会自动落回旧版并提示。
- bind pose 稳定性：动画模式录制蒙皮局部偏移时优先使用加载 skeleton/model 时快照的 canonical pose，并先把体素还原到 canonical 位置，避免切换动画后被上一段动画的蒙皮结果污染。
- Oriented voxel rendering：动画模式下每个体素 cube 朝向跟随骨段一起旋转，消除非 90° 旋转下的"楼梯"边缘。GPU 数据走 per-bone uniform，10w 体素也只需每帧 8 KB 上传。

### 引擎视图（工具栏「引擎...」）

- **结构检查**：粒子不足 13 个、体素绑在下标 ≥ 17 的骨段、上臂骨段端点与游戏取朝向的粒子对不一致、没有上半身层粒子、**bind 姿态下就会错位的骨段**（参考方向与骨段几乎平行时，游戏里这段体素静止时就已错位）等。绑骨工具面板也会显示。
- **逐骨段规则体检**：每根骨段套用的游戏规则、引用的粒子、本帧是否退化（参考方向与骨段平行时游戏里体素会塌缩或翻转）与畸变；「扫描整段动画」找出最差的一刻，点击跳过去；可在视口把需注意 / 异常的骨段标成橙 / 品红。
- **上下半身分层**：游戏用 `bodyAreaHint` 决定粒子属于哪一层——`2` 上半身（跟瞄准方向转、可被换弹等上身动画替换），其它为下半身（跟移动方向转）。可按层给粒子着色；绑骨工具的粒子属性里也改成了下拉框。
- **游戏内合成预览（只读）**：把当前动画和另一个动画按游戏的方式拼成上下半身（以粒子 8 对齐），并可拖动上身扭转角（游戏里奔跑最多约 37°、走路约 60°）。预览期间不能拖粒子，编辑数据不受影响。上身层是可选的：摔倒、飞扑、爬梯、游泳、趴下起身、投降、跳伞、受伤这些动作游戏里是整段播的，选到它们时会提示"合成只是假设"。

### 游戏外观

「视图...」里的「游戏外观（点精灵）」按游戏的方式画体素：屏幕对齐的方块带黑色描边，颜色调亮（饱和度 ×1.05、亮度 ×1.28），方块下半部压暗。不含场景光照与雾。

精灵大小默认按**像素**算，和游戏一致——游戏把边长按档位写死（高细节描边 4.2 / 本体 2.6，低细节 3.6 / 2.4）且关掉了距离衰减，所以镜头拉近体素不会跟着变大。也因此只有在游戏的镜头距离下才和实机一致：旁边的「游戏镜头」按钮一键设成透视 + 距离 1152 体素 + 俯角 58.4°。想要随缩放变化的旧行为，把「大小按像素」关掉即可。

### 动画检查

帧计数旁的 `[!]` 角标会提示：第一帧不在 0 秒、用了游戏不认识的 control key（游戏只认 14 个，其它一律当作 magazine）、有帧的 position 数与骨架不一致。只提示、不阻断保存。

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
5. 按 [rwrsb_bind.spec](rwrsb_bind.spec) 重新打包

打包成功后，输出位置是：

```text
dist\rwrsb_bind\rwrsb_bind.exe
```

发布时建议不要只拿单个 exe，而是把整个 `dist\rwrsb_bind` 文件夹压缩成 zip 再发。

原因是这个目录里除了 exe 之外，还会包含：

- PyInstaller 运行时文件
- `shaders/`
- `presets/`
- `glfw3.dll` 等打包资源

## 编辑流程

1. 打开 `.vox` 或 `.xml`
2. 在右侧面板检查或编辑骨架
3. 新增、修改或删除 `particle` / `stick`
4. 用 `brush` 或 `voxel_select` 做体素绑定
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

当前工程仍然是扁平 Python 工具仓库，运行时代码集中在根目录，资源按用途放在少量子目录。核心文件如下：

| 路径 | 职责 |
|------|------|
| `main.py` | 绑骨工具入口（`rwrsb_bind.exe`）；GLFW 主循环、视口输入、体素绑定、骨骼编辑 gizmo |
| `main_animation.py` | 动画工具入口（`rwrsb_anim.exe`）；动画播放 tick、关键帧编辑、动画工具视口交互 |
| `editor_state.py` | 核心状态中心；voxels / particles / sticks / bindings、undo/redo、预设、动画模式、蒙皮、canonical bind pose、规则体检与合成预览 |
| `engine_skin.py` | 与游戏一致的士兵体素蒙皮（按骨段下标查表、OGRE 四元数运算）、规则说明与结构检查，纯函数 + numpy |
| `ui_panels.py` | ImGui 面板、弹窗、工具栏、双语文案、toast、gizmo pivot 下拉和动画时间线 UI |
| `renderer.py` | OpenGL 渲染；体素、骨架、粒子、网格、gizmo、oriented voxel shader 数据上传 |
| `animation_io.py` | soldier animation XML 的解析、写出、索引、插值和 `Animation` / `AnimationFrame` 数据类 |
| `xml_io.py` | `.vox` 解析、项目 XML 解析/写出、RWR/MagicaVoxel 坐标转换 |
| `camera.py` | Orbit / Ortho 相机、视角预设、屏幕射线构造 |
| `file_dialogs.py` | Windows 文件打开/保存对话框封装 |
| `logger_setup.py` | 日志目录、文件日志和默认 logger 初始化 |
| `resource_utils.py` | 资源路径解析，兼容源码运行和 PyInstaller 打包 |
| `build.bat` / `setup.bat` / `run.bat` | 环境初始化、开发运行和打包脚本 |
| `rwrsb_bind.spec` / `rwrsb_anim.spec` | PyInstaller 打包配置 |
| `presets/` | 骨架预设 JSON |
| `shaders/` | GLSL shader |
| `docs/` | README 使用的截图等公开文档资源 |

本地调试材料和 AI 协作材料不属于发布结构：`logs/`、`claude_use/`、`history/`、`.claude/worktrees/` 以及临时 XML 样例默认不应进入发布提交。

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

- [main.py](main.py)
- [editor_state.py](editor_state.py)
- [xml_io.py](xml_io.py)
- [ui_panels.py](ui_panels.py)

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

发版流程见 [docs/release/RELEASE.md](docs/release/RELEASE.md)。

本次版本说明稿见 [docs/release/notes/RELEASE_NOTES_v1.1.1.md](docs/release/notes/RELEASE_NOTES_v1.1.1.md)（历史版本：[v1.1.0](docs/release/notes/RELEASE_NOTES_v1.1.0.md) / [v1.0.0](docs/release/notes/RELEASE_NOTES_v1.0.0.md) / [v0.1.0](docs/release/notes/RELEASE_NOTES_v0.1.0.md)）。

## 已知限制

- 最终运行效果仍然建议在本机 OpenGL 环境里实际验证
- 当前 XML 兼容性是面向本项目格式，不是任意通用 schema
- 当前发布包是目录版，不是单文件版 exe

## License

本项目采用 MIT License，详见 [LICENSE](LICENSE) 文件。
