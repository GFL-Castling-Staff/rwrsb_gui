# rwrsb 架构概览

本文档面向"半年后回来维护的项目主"和"第一次接入的技术贡献者"，目标是让读者在 20 分钟内建立足够的心智模型，然后再去读具体代码。

---

## 1. 两个入口的关系

本仓库有两个独立的可执行入口：

| 入口 | 打包产物 | 用途 |
|------|---------|------|
| `main.py` | `rwrsb_bind.exe` | 绑骨工具：编辑体素模型的骨架结构与绑定关系 |
| `main_animation.py` | `rwrsb_anim.exe` | 动画工具：为 RWR soldier 骨架制作关键帧动画 |

两个入口**共用同一套源码模块**（`editor_state.py`、`ui_panels.py`、`renderer.py`、`camera.py`、`xml_io.py` 等），启动时各自创建独立的 `EditorState` 和 `UIState` 实例（存入模块级全局变量 `g_editor` / `g_ui`）。

`UIState.app_mode` 字段（`"skeleton"` / `"animation"`）是运行时的分流键：
- `ui_panels.py` 里的面板渲染函数会读这个字段决定显示哪些面板和按钮
- `main.py` 启动时设 `g_ui.app_mode = "skeleton"`，`main_animation.py` 设 `"animation"`

两个入口的主循环结构相同（GLFW 初始化 → 帧循环 → ImGui 渲染 → 事件分发），但动画工具额外处理播放 tick（`playback_time` 推进）和帧时间线 UI。

---

## 2. EditorState 单例状态中心

`EditorState`（`editor_state.py`）是项目事实上的单例状态中心。每个入口进程各有一个 `g_editor = EditorState()` 实例，持有所有可编辑数据和运行时状态。

以下按分组列出主要字段：

### 文件数据
| 字段 | 类型 | 说明 |
|------|------|------|
| `voxels` | `list` | 体素列表，每个元素是含位置 + 颜色的 dict |
| `particles` | `list` | 骨架节点列表，每个元素含 `id`、`x/y/z`、`name` 等 |
| `sticks` | `list[StickEntry]` | 骨段列表 |
| `bindings` | `dict` | `{constraint_index: [voxel_index, ...]}` |
| `source_path` | `str \| None` | 当前打开文件的路径 |
| `trans_bias` | `int` | MagicaVoxel → 世界坐标偏移量，默认 127，武器模型用 49 |

### 选择状态
| 字段 | 说明 |
|------|------|
| `selected_voxels` | `set[int]`，选中的体素 index 集合 |
| `selected_particles` | `set[int]`，选中的 particle index 集合 |
| `active_stick_idx` | 当前激活骨段的 index（面板高亮用） |
| `active_particle_idx` | 多选时"最后点击加入的那个"particle index，`-1` 表示无 |

### 工具模式与镜像模式
| 字段 | 说明 |
|------|------|
| `tool_mode` | `"brush"` / `"voxel_select"` / `"bone_edit"`，见第 4 节 |
| `mirror_mode` | `bool`，是否处于镜像编辑模式 |
| `mirror_axis` | `"x"` / `"y"` / `"z"` |
| `mirror_pair` | `tuple[int, int] \| None`，镜像的两个 particle index |
| `mirror_plane_origin` | `np.ndarray(3,)`，镜像平面原点 |
| `mirror_plane_normal` | `np.ndarray(3,)`，镜像平面法向量 |
| `mirror_edit_mode` | `bool`，镜像平面编辑子模式 |

### undo / redo
| 字段 | 说明 |
|------|------|
| `_undo_stack` | 快照列表（上限 64），见 `_snapshot` / `_restore_snapshot` |
| `_redo_stack` | redo 快照列表 |
| `_dirty` | XML 数据是否有未保存修改（标题栏 `*` 读取） |

### 动画模式
| 字段 | 说明 |
|------|------|
| `animation_mode` | `bool`，是否处于动画编辑模式 |
| `current_animation` | `animation_io.Animation \| None` |
| `animation_source_doc` | `AnimationDocIndex \| None`，来源文档索引 |
| `animation_source_idx` | 来源文档里的动画下标 |
| `current_frame_idx` | 当前编辑帧的下标 |
| `playback_time` | 播放时间（秒） |
| `playback_playing` | `bool`，是否正在播放 |
| `playback_loop_preview` | `bool`，循环预览开关（独立于 `anim.loop`） |
| `_particle_positions_before_anim` | 进入动画模式前的 particle 位置备份，`exit_animation_mode` 时用于恢复 |
| `_anim_dirty` | 动画数据是否有未保存修改 |
| `_anim_undo_stack` | 动画模式独立 undo 栈 |
| `_anim_redo_stack` | 动画模式独立 redo 栈 |
| `_anim_reference_lengths` | 进入动画模式时记录的各骨段参考长度（骨段长度检查用） |

### baseline pose
| 字段 | 说明 |
|------|------|
| `_baseline_positions` | `list[tuple] \| None`，基准 pose 的 particle 位置 |
| `_baseline_name` | 基准 pose 名称（如 `"vanilla_still"`） |
| `_baseline_locked_indices` | `set[int]`，baseline 模式下被锁定不可拖动的 particle index |

### 骨架树缓存
| 字段 | 说明 |
|------|------|
| `_tree_parent` | `dict[int, int \| None]`，particle index → 父节点 index；root 的父为 `None` |
| `_tree_root_idx` | 当前 root 的 particle index；`-1` 表示未构建 |
| `_tree_dirty` | `True` 时下次访问前需要重建 |

### 渲染同步与蒙皮
| 字段 | 说明 |
|------|------|
| `gpu_dirty` | GPU 渲染缓冲区需要重建 |
| `skeleton_dirty` | 骨架线段数据需要重传给 renderer |
| `_voxel_local_offsets` | `{voxel_index: np.ndarray(3,)}`，每个绑定体素在其骨段局部坐标系里的固定偏移（蒙皮 bind pose） |
| `_voxel_groups` | 按 constraint_index 预分组的蒙皮数据，`update_voxel_positions_from_skeleton` 使用 |

---

## 3. 三组核心数据的关系

```
particles ──── sticks ──── bindings
   │              │             │
 id (uint)  constraint_index  key = constraint_index
 index       == sticks 下标    value = [voxel_index, ...]
```

**particles**：骨架节点，每个有唯一 `id`（持久化到 XML）和数组下标 index（UI 状态用）。两者不一样——增删 particle 后 index 变，但 id 不变。

**sticks**：骨段，每个 `StickEntry` 引用两个 particle 的 `id`（`particle_a_id` / `particle_b_id`）。`StickEntry.constraint_index` 必须恒等于该 stick 在 `self.sticks` 列表里的下标——`_normalize_stick_indices()` 在每次增删 stick 后强制维护此不变量。

**bindings**：`{constraint_index: [voxel_index, ...]}`，记录哪些体素绑定到哪个骨段。删除或重排 stick 后，binding 的 key（constraint_index）会跟着 `_normalize_stick_indices()` 一起重映射，否则会出现"体素绑定到错误骨段"的静默错误。

关键约束：**删除或重排 stick 时必须同步修正 bindings**，这是本项目里最容易引入 bug 的操作，修改时要额外验证。

---

## 4. tool_mode 三态语义和切换副作用

`EditorState.tool_mode` 控制鼠标在视口里的行为，三个值互斥：

| 值 | 语义 | 鼠标左键行为 |
|----|------|------------|
| `"brush"` | 体素涂刷 | 点击体素做绑定/涂色 |
| `"voxel_select"` | 体素框选 | 拖动画框，选中范围内体素更新 `selected_voxels` |
| `"bone_edit"` | 骨骼编辑 | 点击 particle 选中，支持多选/框选；**只有此模式下粒子拖拽生效** |

> 注意：`tool_mode`（鼠标在视口里做什么）和 `allow_skeleton_edit` / `allow_stick_edit` / `allow_particle_edit`（是否允许修改数据）是两个正交的概念，不要混淆。

**切换副作用**（由 `set_tool_mode()` 执行）：
- 离开 `"bone_edit"` 时：`selected_particles.clear()`、`active_particle_idx = -1`、调用 `exit_mirror_mode()`
- 离开 `"voxel_select"` 时：`selected_voxels` **保留**（和现有行为一致）

工具栏快捷键：`B`（brush）/ `V`（voxel_select）/ `E`（bone_edit）。

---

## 5. 修饰键语义统一表

同一个修饰键在不同场景下含义不同：

| 场景 | Shift | Ctrl | Alt | Shift+Alt |
|------|-------|------|-----|-----------|
| 粒子拖拽轴约束 | 锁 X 轴 | 锁 Y 轴 | 锁 Z 轴 | — |
| 点击 particle 多选 | 加选（追加） | Toggle（已选则移出） | — | 减选（移出） |
| 框选 particle | 加选（追加） | Toggle | — | 减选（移出） |

轴约束（拖拽时）和多选（点击/框选时）读修饰键的时机不同：轴约束在**拖动开始（mousedown + 移动）**时读，多选在**点击（mousedown + 无移动 + mouseup）**时读，因此不冲突。

---

## 6. 绑骨模式 vs 动画模式状态切换

### 进入动画模式：`enter_animation_mode(animation)`

前置条件：`len(particles) == EXPECTED_PARTICLE_COUNT (15)`，否则抛 `ValueError`。

执行顺序：
1. 若 `animation.frames` 为空，自动追加一帧（= 当前 particle 姿态）
2. 备份当前 particle 位置到 `_particle_positions_before_anim`
3. 清空 `selected_particles` 和镜像模式
4. 设 `animation_mode = True`，清空动画 undo/redo 栈
5. 以 still pose（备份的位置）作为 bind pose 调用 `record_voxel_bind_pose()`
6. 调用 `_apply_frame_to_particles(0)` 把 particle 位置设为第 0 帧
7. 调用 `_record_reference_lengths()` 记录各骨段参考长度

### 退出动画模式：`exit_animation_mode(force=False)`

- 若 `_anim_dirty == True` 且 `force=False`，返回 `"dirty_needs_confirmation"`，UI 层弹确认对话框
- 否则：恢复 `_particle_positions_before_anim` 里的 particle 位置，调用 `update_voxel_positions_from_skeleton()` 把体素归位到 bind pose

### 关键区别：蒙皮只在动画模式下触发

`_mark_skeleton_changed()` 在 `animation_mode == True` 时会调用 `update_voxel_positions_from_skeleton()`（蒙皮）；绑骨模式下不调用。

原因：绑骨模式下体素是体模型本身，拖粒子只是在挪骨架标注点，体素位置不应跟着变。动画模式下才需要体素跟着骨架变形（蒙皮效果）。

---

## 7. 关键约定与隐式知识

### EXPECTED_PARTICLE_COUNT = 15

定义在 `animation_io.py`。RWR 引擎硬编码：soldier animation XML 每帧必须正好 15 个 particle 位置，多一个少一个都会解析失败。动画工具的骨架加载、帧编辑、XML 导出全部依赖此约束。

### constraintIndex == sticks 列表下标

`StickEntry.constraint_index` 必须始终等于该 stick 在 `EditorState.sticks` 列表里的数组下标。这个不变量由 `_normalize_stick_indices()` 维护——每次增删或重排 stick 后都会调用它。bindings 的 key 也是 constraint_index，所以 `_normalize_stick_indices()` 同时负责重映射 bindings。

### trans_bias：127 vs 49

`trans_bias` 是 MagicaVoxel 坐标系转换到 RWR 世界坐标系的偏移量，来源于 RWR 引擎坐标系定义（参考 rwrwc.py 的 `Transformation`）。

- 默认值 `127`：适用于人形 soldier 模型
- `49`：适用于武器模型（尺寸更小，bias 更小）

修改 trans_bias 后，所有体素坐标和骨架坐标都会一起偏移，两者的相对关系不变。

### 预设只保存骨架，不保存绑定

骨架预设（`presets/*.json`）只保存 `particles` + `sticks`，不保存 `bindings`。binding 属于具体体素模型的项目数据，不具有跨模型复用价值。加载预设时 bindings 会被清空。

### stick.visible 不进 clone，走 visible_by_pair 通道

`StickEntry.clone()` 不拷贝 `visible` 字段（反直觉！）。原因：`visible` 是 UI 状态（用户的可视偏好），undo/redo 不应该重置它。`_snapshot()` 里通过 `visible_by_pair` 字典（key = `(particle_a_id, particle_b_id)`）独立保存可视状态，`_restore_snapshot()` 恢复时按 particle pair 匹配回写，没匹配到的 stick 默认 `True`。见第 8 节。

---

## 8. 5 种 dirty flag 关系表

| flag | 含义 | 由谁置位 | 由谁消费 / 清零 |
|------|------|----------|----------------|
| `_dirty` | XML 数据有未保存修改 | 骨架 / 绑定任何修改（`_mark_skeleton_changed` / `_mark_bindings_changed`） | 保存文件后清零；标题栏 `*` 和退出守卫读取 |
| `gpu_dirty` | GPU 渲染缓冲区需要重建 | 同上，以及体素可视变化 | 渲染循环每帧检测，重建缓冲区后清零 |
| `skeleton_dirty` | 骨架线段数据需要重传给 renderer | `_mark_skeleton_changed()` | renderer 重传 skeleton lines 后清零 |
| `_tree_dirty` | 骨架树缓存失效 | 粒子 / 骨段增删改（`_mark_skeleton_changed`） | 下次访问 `_tree_parent` 属性前调用 `_rebuild_tree()` 重建，完成后清零 |
| `_anim_dirty` | 当前动画有未保存修改 | 动画模式下帧编辑操作 | 动画保存后清零；动画面板标题 `*` 和退出守卫读取 |

`gpu_dirty` 和 `skeleton_dirty` 经常同时被置位，但消费者不同：`gpu_dirty` 触发 VBO 重建（体素颜色），`skeleton_dirty` 触发骨架线段数据重传（两者各自有独立的 GPU buffer）。

---

## 9. bone / stick 命名说明 + particle id / index 区分

### bone vs stick

`bone` 是项目早期命名，后来统一改称 `stick`（骨段）。目前代码里两套命名共存：

- **当前命名**（主）：`StickEntry`、`self.sticks`、`active_stick_idx`、`set_all_sticks_visible()`
- **遗留别名**（兼容）：`@property bones`（转发到 `sticks`）、`@property active_bone_idx`（转发到 `active_stick_idx`）、常量 `BONE_COLORS`

遗留别名保留是为向前兼容（历史 handoff 文档和早期代码引用了它们）。**新代码统一用 stick 系列**，不要再用 bone 别名。

### particle id vs index

particle 有两种"编号"，语义和用途不同：

| | `id` | `index` |
|-|------|---------|
| 类型 | `int`（uint），存在 particle dict 的 `"id"` 字段 | 数组下标（0-based） |
| 用途 | XML 持久化；`StickEntry.particle_a_id / particle_b_id` | UI 选择状态：`selected_particles`、`active_particle_idx` |
| 稳定性 | 增删 particle 后 id 不变 | 增删 particle 后其他 particle 的 index 可能变 |

规则：**凡是需要持久化到文件或跨 undo 帧保持引用的，用 id；凡是只在当前会话内用的 UI 状态，用 index。**
