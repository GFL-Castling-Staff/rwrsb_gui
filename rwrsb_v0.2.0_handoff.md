# rwrsb v0.2.0 Handoff — 骨骼多选编辑 + 体验改进

## 给接手 Claude 的说明

这个 handoff 用来在新对话里延续 rwrsb_gui 的迭代工作。当前项目在知识库里（rwrsb 的 GitHub 仓库），**开工前请先用 `project_knowledge_search` 读取以下文件**，了解 v0.1.0 的实现现状：

- `main.py` — 主循环、输入事件、视口拖拽
- `editor_state.py` — 可编辑状态、undo/redo、骨架 CRUD
- `ui_panels.py` — 右侧面板、工具栏、弹窗
- `renderer.py` — 体素与骨架渲染、粒子拾取
- `camera.py` — 相机与视图预设

注意 `project_knowledge_search` 返回的是 chunk 片段，可能切断函数体，必要时多次搜索或针对特定函数名查询。

项目主打 G23 实际使用场景，**动画关键帧本轮不做**，**旋转/缩放 gizmo 本轮不做**。专注把"多选粒子 + 整体平移 + 对齐 + 镜像"这条核心链路做扎实，顺便改掉几个已知的体验毛病。

---

## 当前版本事实（v0.1.0）

在开始写代码前请核实以下事实（用 `project_knowledge_search` 验证），如果和实际代码不符，以代码为准：

- **粒子拖拽**：已实现单个粒子拖动。`main.py` 里用 `g_drag_particle_idx: int`、`g_particle_drag_active: bool` 表示状态。拖动时支持 Shift/Ctrl/Alt 轴约束（锁 X/Y/Z）。
- **粒子拾取**：`renderer.py` 的 `pick_particle_screen` 做屏幕空间拾取。
- **粒子多选**：**还没有**。当前 `selected_particles` 这个概念在代码里不存在。
- **框选**：`renderer.py` 的 `box_select_voxels` 只作用于体素。`ui_state.box_selecting` 是框选状态 flag，`draw_box_select_overlay` 画选框。
- **工具模式**：`editor_state.tool_mode` 目前只有 `"brush"` 和 `"select"`（后者指体素框选）。**没有**独立的骨架编辑模式。
- **骨段可视**：`stick.visible: bool`，在 `_draw_stick_list` 里用 `o`/`-` 按钮逐个切换。**没有**一键全开/全关。骨段不可视时，绑定到它的体素在 `get_voxel_color` 里会被降饱和。
- **视图预设**：`camera.set_view_preset("front"|"side"|"top"|"perspective")`。中文按钮文案 "前视/侧视/顶视/3/4"。**没有**反面视图（后/反侧/底）。
- **文件打开/保存**：走 `draw_load_dialog` / `draw_save_dialog`，用户**手动输入路径**。拖拽文件进窗口的路径已实现（`main.py` 里应该有 drop callback）。**没有**系统文件对话框。
- **异常处理**：打包后的 exe 崩溃时**没有**日志文件或 UI 提示。

---

## 本轮需求清单

### P0 — 核心骨骼编辑链路

#### F1 — particle 多选数据模型

- `editor_state.py` 新增 `selected_particles: set[int]`（存 particle 的 index，不是 id，和现有 `active_particle_idx` 保持索引风格一致）
- 保留 `active_particle_idx`：多选时约定 active 是"最后点击加入的那个"，用于 F6 "对齐到 active"
- undo/redo 需覆盖 selected_particles 变化吗？**不覆盖**（选择状态是 UI 状态，不是数据状态，和 `selected_voxels` 保持一致策略 —— 查代码验证 selected_voxels 是否入 undo）

#### F2 — 点击多选交互

- **普通点击 particle**：清空 selected_particles，加入该点，设为 active
- **Shift+点击**：追加加入 selected_particles（如果已在则不动），设为 active
- **Ctrl+点击**：toggle 该点在 selected_particles 里的存在，如果新加入则设为 active，如果移除且该点是 active 则 active 回退到集合里任意一个（或 -1）
- **点击空白处**（未命中任何 particle 且未命中体素）：清空 selected_particles
- 注意和现有"Shift/Ctrl/Alt 轴约束"可能冲突 —— 查一下现有代码在哪个时机读这些修饰键。如果现有代码在**拖动开始时**读修饰键，那点击时读修饰键不冲突；如果在**按下时**读，需要区分"按下后立即松开 = 点击"和"按下后移动 = 拖动"

#### F3 — particle 框选

- 在骨骼编辑工具模式下（见 F4），框选目标从体素切换为 particle
- 新增 `box_select_particles(x0, y0, x1, y1, positions, mvp, vp_w, vp_h) -> list[int]`，参考 `box_select_voxels` 的实现
- 框选结果**替换** selected_particles（如果按住 Shift 框选则追加；Ctrl 框选则 toggle —— 这个按 F2 的修饰键语义延伸）
- 框选和点击的 overlay 共用 `draw_box_select_overlay`，不用重写

#### F4 — 工具模式扩展 + 修复"干扰多选"bug

**这是本轮最大的风险点**，现有的 `brush` / `select` 二元模式混着"鼠标状态 + 全局 flag"在 `main.py` 的鼠标事件里做判断，引入第三个模式要重新梳理判断矩阵。

- `editor_state.tool_mode` 扩展为三值：`"brush"` / `"voxel_select"` / `"bone_edit"`
  - `brush`：体素涂刷（原 brush）
  - `voxel_select`：体素框选（原 select，改名以区分）
  - `bone_edit`：**新增**，骨骼编辑模式，点击/框选目标是 particle
- 工具栏按钮：三个互斥的 toggle 按钮。快捷键建议 `B`/`V`/`E`（E for Edit bones），但要确认 `V` 不和现有快捷键冲突
- 粒子拖拽在哪些模式下可用？**只在 `bone_edit` 下可用**。这样能彻底消除 G23 提到的"框选工具去框选体素"问题。
  - 反过来说，`brush` / `voxel_select` 模式下点击粒子不触发拖拽，也不选中粒子
- 切换工具模式时：
  - 离开 `bone_edit` → 清空 selected_particles、退出镜像模式（见 F6b）
  - 离开 `voxel_select` → 是否清空 selected_voxels？按现有行为保留，别动
- 面板里"允许骨架编辑 / 允许骨段编辑 / 允许粒子编辑"这三个总开关和新的 tool_mode 是两回事，总开关是"是否允许修改数据"，tool_mode 是"当前鼠标在视口里做什么"。不要混淆。

#### F5 — 多选整体平移

- 拖动 selected_particles 中的任一成员时，拖动的世界空间 delta 应用到所有 selected_particles
- 现有单粒子拖动代码里的 `g_drag_particle_origin`（起点记录）要扩展为 `g_drag_origins: dict[int, Vector3]`，记录所有选中点的初始位置，每帧用 `origin + delta` 更新，避免累积误差
- 网格吸附的逻辑：只对**被直接拖动的那个点**做吸附（snap 到网格），其他点按相同 delta 跟随。不要每个点各自 snap，否则组内相对位置会变。
- undo 策略：多选平移整组算**一次** undo，在按下鼠标时 push，松开时不再 push
- 镜像模式开启时 F5 **禁用**，见 F6b

#### F6a — 命令式对齐（"对齐到 active"，B 解释）

- 骨骼面板里新增一组按钮：`Align X` / `Align Y` / `Align Z`（中文：对齐 X / 对齐 Y / 对齐 Z）
- 启用条件：`len(selected_particles) >= 2` 且 `active_particle_idx` 在 selected_particles 里
- 行为：把所有 selected_particles 在指定轴上的坐标改成 active particle 在该轴的坐标。其他两轴不动。
- 入 undo（算一次）
- UI 位置：放在粒子面板里"当前粒子"附近，或者单独一小节 "多选操作"

#### F6b — 状态式镜像（D 解释）

**本轮最精细的功能，需要仔细实现和测试。**

- 新增状态：`editor_state.mirror_mode: bool`、`mirror_axis: "x"|"y"|"z"` (默认 `"x"`)、`mirror_pair: tuple[int, int] | None`（两个 particle 的 index）
- UI：骨骼面板新增"进入镜像模式"按钮 + 轴选择（单选 X/Y/Z）
  - 进入条件：恰好选中 2 个 particle（`len(selected_particles) == 2`）。如果不满足，按钮禁用并给 tooltip 说明
  - 进入时：`mirror_pair = tuple(sorted(selected_particles))`，`mirror_mode = True`
  - 退出条件：显式按"退出镜像模式"按钮，或切换 tool_mode 离开 bone_edit，或 mirror_pair 里某个 particle 被删除
- 镜像生效逻辑（在拖动 handler 里）：
  - 仅当 `mirror_mode == True` 且 `g_drag_particle_idx in mirror_pair` 时触发
  - 拖动的那个点正常跟鼠标走（含网格吸附、轴约束）
  - 伙伴点每帧计算镜像位置：设镜像轴为 `x`，拖动点当前位置 `(px, py, pz)`，则伙伴 `(-px, py, pz)`。镜像中心**恒为 0**（不是 pair 的中点），因为 RWR 人形骨架就是以 x=0 为对称面。
  - Y/Z 轴同理
- F5 多选整体平移在镜像模式下**禁用**：即使 selected_particles 有多个，拖动时只作用于被拖动的点 + 镜像伙伴
  - 实现：拖动 handler 开头判断，如果 `mirror_mode == True`，走镜像路径，不走 F5 路径
- 如果进入镜像模式后用户又多选了第 3 个 particle：允许，但第 3 个点不参与镜像，也不参与整体平移（镜像模式下整体平移本就禁用）。其实这种状态有点怪，简单起见**镜像模式下点击其他 particle 不改变 selected_particles**，或者**进入镜像模式时把 selected_particles 锁定为 mirror_pair**。我倾向后者，更清晰。
- undo：拖动算一次，镜像伙伴位置变化也一并记录（多选平移已经是整组算一次 undo，镜像同样处理）
- 边界情况：`mirror_axis = "x"` 时拖动点 x 被吸附到 0，伙伴也在 0 → 两点重叠，这是数学正确结果，不做特殊处理

---

### P1 — 体验改进

#### F7 — 视图按钮二次点击切换反面

- 新增状态 `camera._last_view_button: str | None`（camera.py 内部，不暴露给 UI）
- `set_view_preset(name)` 改造：
  - 如果 `name == _last_view_button`：切换到反面预设（前↔后、侧↔反侧、顶↔底，3/4 透视不参与反面切换，或者反面 = 对面角度的 3/4）
  - 否则：正常设置，`_last_view_button = name`
- 反面视角的计算：在 `set_view_preset` 里新增对应分支 `"back"`, `"back_side"`, `"bottom"`，调整 azimuth/elevation
- 重置 `_last_view_button` 的时机（**仅相机操作**触发重置，粒子编辑不影响）：
  - 右键旋转（`on_mouse_button` button==1 action==1）
  - 中键平移（button==2 action==1）
  - 滚轮缩放（on_scroll）
  - 正交/透视切换（`is_ortho` 变化）
  - 点击了**不同**的视图按钮 → 自然会被新的 name 覆盖，不用显式清空
- UI 无变化（依然是 3 个视图按钮 + 透视按钮），但体感上可以二次点击翻面
- 工具栏上可以在按钮上加一个小指示，比如当前可翻面时按钮文案显示"前视 ↔"，懒得做也行

#### F8 — 骨段可视一键全开/全关

- `_draw_stick_list` 上方加一行，两个按钮 `全部显示` / `全部隐藏`（或一个 toggle "可视: 全开/全关/混合"）
- 实现：遍历 `editor_state.sticks`，批量 `stick.visible = True/False`，然后 `editor_state.gpu_dirty = True`
- 建议做成**三态 toggle**：当前全部可视 → 按钮显示"全部隐藏"，点了变全隐；全部隐藏 → 显示"全部显示"；混合 → 显示"全部显示"，点了变全显。三态判断用 `all(s.visible for s in sticks)` 和 `any(s.visible for s in sticks)`。
- 入 undo 吗？可视是 UI 状态还是数据状态，查一下 `stick.visible` 是否会保存到 XML。如果会保存就入 undo，如果不会就不入。

#### F9 — 系统文件对话框

- `draw_load_dialog` 和 `draw_save_dialog` 里的"手动输入路径"改为调用系统对话框
- 实现用 `tkinter.filedialog`：

  ```python
  import tkinter
  from tkinter import filedialog

  def pick_open_file(title, filetypes):
      root = tkinter.Tk()
      root.withdraw()
      path = filedialog.askopenfilename(title=title, filetypes=filetypes)
      root.destroy()
      return path or None
  ```

- **风险**：tkinter 的 mainloop 可能和 GLFW 主循环抢焦点，或者在某些 Windows 机器上卡一下。如果实测有问题（表现为：对话框打不开、主窗口冻结、崩溃），退化方案是用 `ctypes` 调 Win32 `GetOpenFileName`。先试 tkinter，**出问题再换**。
- 拖拽打开**保留**，不要动现有的 drop callback
- 原来弹窗里的"输入路径"输入框可以保留作为兜底（比如用户想粘贴一个 UNC 路径），也可以去掉。建议保留，加一行"或直接输入/粘贴路径"

#### F10 — 打包 exe 的错误日志

当前 `rwrsb_gui.spec` 用 `console=False`，所以 exe 运行时没 stderr 输出，崩溃了用户什么都看不到。

- 在 `main.py` 最前面（import 后、任何其他代码前）加日志初始化：

  ```python
  import sys
  import logging
  from pathlib import Path
  from datetime import datetime

  def _setup_logging():
      # 打包后 sys.frozen 为 True，日志放到 exe 所在目录
      if getattr(sys, 'frozen', False):
          log_dir = Path(sys.executable).parent / "logs"
      else:
          log_dir = Path(__file__).parent / "logs"
      log_dir.mkdir(exist_ok=True)
      log_file = log_dir / f"rwrsb_{datetime.now():%Y%m%d_%H%M%S}.log"
      logging.basicConfig(
          level=logging.INFO,
          format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
          handlers=[logging.FileHandler(log_file, encoding="utf-8")],
      )
      # 捕获未处理异常
      def excepthook(exc_type, exc_value, exc_tb):
          logging.exception("Uncaught exception", exc_info=(exc_type, exc_value, exc_tb))
      sys.excepthook = excepthook
      return log_file

  _LOG_FILE = _setup_logging()
  ```

- 在关键易错路径（XML 解析、VOX 解析、预设加载、文件导出）的 `except` 里用 `logging.exception(...)` 而不是只塞 `ui_state._bone_error`。这样 UI 仍能显示友好提示，日志里也有完整堆栈。
- UI 里的错误提示保持原样（`_bone_error` 等），但可以加一行"详细日志见 logs/ 目录"
- 测试用例：故意传一个损坏的 XML，看日志文件是否产生、UI 是否提示、程序是否不崩

---

## 不做的事（本轮明确排除）

- 旋转 gizmo、缩放 gizmo（G23 原话"手扭也不是不能用"、"或者就平移也行"）
- 动画关键帧（明确后置）
- 拖动时实时吸附到其他 particle（用 F6a 命令式对齐覆盖了这个需求）
- VOX 自动绑骨（Z-2414 提的，独立需求，另起炉灶）

---

## 实现顺序建议

按这个顺序做，每步做完可以在游戏内验证一次再推进，避免 bug 累积：

1. **F4（工具模式扩展）先做** — 这是其他所有功能的前置。引入 `bone_edit` 模式，把现有 `select` 重命名为 `voxel_select`。这一步不新增功能，只是重构。验证：现有功能（brush / 体素框选 / 单粒子拖拽）没退化。
2. **F1 + F2（多选数据模型 + 点击交互）** — 在 `bone_edit` 模式下，支持 Shift/Ctrl 多选。验证：粒子能被多选，视觉高亮正确。
3. **F5（多选整体平移）** — 拖动其中一个，其他跟随。验证：多选后拖动，相对位置不变。
4. **F3（particle 框选）** — 在 `bone_edit` 模式下框选粒子。验证：框选能选中预期的粒子，不误选体素。
5. **F6a（命令式对齐）** — 加三个对齐按钮。验证：对齐后坐标正确。
6. **F6b（镜像模式）** — 最复杂的一步，单独测。验证：进入/退出镜像、拖动一个另一个镜像跟随、镜像模式下禁用多选整体平移、切工具模式自动退出。
7. **F7（反面视图）** — 相对独立。验证：二次点击翻面、相机操作后重置。
8. **F8（骨段可视一键切换）** — 简单。验证：全开/全关/混合三态。
9. **F9（系统文件对话框）** — tkinter 先试。验证：对话框能开，不和 GLFW 冲突。
10. **F10（错误日志）** — 最后做，改动集中在 main.py 初始化和 except 块。验证：故意让程序崩一次，看日志。

---

## 工作量估计

按悲观/乐观区间给：

- F4（工具模式扩展）：**2-5 小时**。现有鼠标事件分发的判断矩阵可能比表面复杂。
- F1 + F2：**2-4 小时**
- F5：**2-4 小时**
- F3：**1-3 小时**
- F6a：**1-2 小时**
- F6b：**3-6 小时**（镜像模式状态机是真的要仔细写）
- F7：**1-2 小时**
- F8：**0.5-1 小时**
- F9：**2-5 小时**（tkinter 如果出事故可能翻倍）
- F10：**1-2 小时**

**总计：乐观 15.5 小时，悲观 34 小时**

建议分 **2-3 个对话**做：
- 对话 1：F4 + F1 + F2 + F3 + F5（多选链路打底）
- 对话 2：F6a + F6b + F7（对齐、镜像、视图）
- 对话 3：F8 + F9 + F10（体验打磨 + 打包问题）

也可以按 F4-F6 一个对话、F7-F10 一个对话，取决于第一个对话跑出来的复杂度。

---

## 风险点明列

1. **F4 工具模式扩展**：现有 `main.py` 的鼠标事件路由没有看过完整代码，实际判断矩阵可能更复杂（比如 brush 模式按右键旋转相机、select 模式按 Shift 拖动改成框选等）。如果发现现有代码有隐式耦合，先花时间梳理清楚再动手，别盲目加 if-else。
2. **F6b 镜像模式状态机**：镜像轴、拖动点、伙伴点、网格吸附、轴约束的优先级需要理清楚。建议先画个决策树再写代码。特别注意：镜像模式下，"Shift 锁 X 轴"这种现有轴约束是否还生效？我的建议是**镜像模式下禁用轴约束**，因为镜像本身就是对称约束，叠加会让用户困惑。但这点需要 SAIWA 确认。
3. **F9 tkinter 和 GLFW 共存**：没有实测数据。如果 `Tk().withdraw()` 后 GLFW 窗口失焦或假死，第一反应不是修 tkinter，而是换 ctypes 方案。别在 tkinter 上死磕超过 1 小时。
4. **F10 日志路径**：打包后 `Path(sys.executable).parent` 可能指向 `dist/rwrsb_gui/`，普通用户解压到 Program Files 可能没写权限。考虑退化到 `%APPDATA%/rwrsb_gui/logs/`。但本项目主要是内部用，先放 exe 同级目录，出问题再调。

---

## 需求原始出处（追溯用）

G23 和 Z-2414 在 QQ 群聊里提出的需求，主要动机是 G23 的使用场景："调整人形骨架，修正错位的 particle，之前只能在外部写脚本改 XML"。G23 的原话关键点：

- "我可能都不需要体素，我需要改骨"
- "选择骨骼，缩放骨骼，移动骨骼，旋转骨骼" —— 实际上缩放/旋转本轮不做，G23 自己后补"或者就平移也行"
- "框选骨骼然后平移"
- "左边的胳膊那个点可以在上下移动的时候与右手点对齐" —— 这句推动了 F6 对齐功能
- "现在如果我可以选择两个或者更多点，然后移动，然后左右对齐，再做一段动画，那无敌了" —— 动画后置
- 三个体验改进（一键可视、文件对话框、错误日志）是 SAIWA 自己补的

Z-2414 提了"vox 自动绑骨"，独立需求，本轮不做。

---

## 测试检查清单（发版前）

在 `RELEASE.md` 原有检查清单基础上，本轮新增：

- [ ] `bone_edit` 模式下，点击粒子可选中，Shift/Ctrl 多选工作正常
- [ ] `bone_edit` 模式下框选粒子，不误选体素
- [ ] `brush` / `voxel_select` 模式下点击粒子不触发拖拽
- [ ] 多选后拖动任一选中点，其他点按相同 delta 跟随
- [ ] 多选整体平移是一次 undo
- [ ] 对齐 X/Y/Z 按钮工作正常，其他两轴不动
- [ ] 进入镜像模式需要恰好选中 2 个 particle
- [ ] 镜像模式下拖一个 particle，伙伴实时对称跟随
- [ ] 镜像模式下切换工具模式会自动退出镜像
- [ ] 视图按钮二次点击切换反面
- [ ] 任何相机操作后，视图按钮重新点击从"第一次"开始计数
- [ ] 骨段可视一键全开/全关/三态判断正确
- [ ] 文件对话框能正常打开、选择、取消
- [ ] 故意传损坏文件，UI 有提示 + 日志有记录 + 程序不崩
- [ ] 打包 exe 后，`logs/` 目录能在 exe 同级生成

---

## 给接手 Claude 的最后提醒

- SAIWA 偏好**设计先行**：拿不准的设计决策先停下来问，不要直接写 300 行代码。
- SAIWA 偏好**增量提交**：每个 F 做完可以提一次 commit。`feat: add particle multi-selection` 这种 Conventional Commits 风格。
- SAIWA 会**手动在游戏内验证**：本项目没有自动化测试，每个改动你都要明确告诉 SAIWA 怎么手动复现验证。
- 知识库里可能有历史对话记录，如果遇到"这里之前讨论过吗"的情况，可以用 `conversation_search` 查。
- 工作量估计请用"乐观/悲观"区间表述，不要给单一数字。
