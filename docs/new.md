# 异形骨支持：骨段管理工作流

## 背景

RWR 引擎对 skeleton 的硬约束**只在骨段数（必须 = 17 根 stick）**，粒子数和拓扑都不限。已确认（commit `fdf4cf4`、`5af9bf2`）：
- 校验对象已从粒子数改为骨段数
- 蒙皮已支持任意拓扑（全局规则 + 邻居缓存，孤立骨自动 world-axis fallback）

剩下要解决的是 **"用户怎么舒服地建一个 17 骨段的异形骨"**。所有真实骨段 < 17 时需要补"哑铃骨段"（dummy = 两孤立粒子 + 孤立 stick + 无 voxel binding），> 17 时手动合并删减。

## 数据语义约定

- **dummy stick**：拓扑孤立的 stick（其两端粒子不与任何其他 stick 相连）+ 无 voxel binding。
- **dummy 粒子**：仅作为 dummy stick 端点存在的粒子。
- 标识方式：**派生检测**，不在数据结构上加 flag。理由：拓扑就是真理，加 `is_dummy` 字段会和真实拓扑产生一致性维护负担。提供一个 `EditorState.classify_sticks() -> dict[int, "skinned"|"dummy"]` helper，按 `bindings + 拓扑邻居` 判断即可。
- **17 是常量**：复用已加的 `animation_io.EXPECTED_STICK_COUNT`，不重复定义。

## Commit 列表

每个 commit 自成一体，可单独验证、单独回滚。

---

### Commit 1 — `feat(bind): live stick budget indicator`

**目标**：状态栏 / 骨段面板把 `Sticks: N` 改为 `Sticks: N / 17`，按差值染色（= 绿；≠ 红 / 黄）。让用户全程都知道还差几根。

**改动**：
- `ui_panels.py` 的 `sticks_count` 翻译串改为 `Sticks: {count} / {target}`（中英两份）
- 在 [ui_panels.py:1280](ui_panels.py:1280) 那一行把 `imgui.text` 换成 `imgui.text_colored`，按 `count == EXPECTED_STICK_COUNT` 选颜色（建议：等于 → 默认 / 不等于 → `(1.0, 0.6, 0.2)` 黄）
- 注意此面板对绑骨和动画工具都要展示

**验收**：打开 `presets/human_skeleton.json` 显示 `Sticks: 17 / 17`（默认色）；删 1 根变红/黄。

**补充**：当存在 dummy stick 时，指标应区分真实骨段数和 dummy 数，如 `Sticks: 17/17 (12 real + 5 dummy)`，避免用户误以为骨架完整。可在 bone 面板 `sticks_count` 行下方加一行小字 `dummy_count_hint`（仅在 dummy > 0 时显示）。

---

### Commit 2 — `feat(bind): pre-flight dialog for animation entry`

**目标**：进动画模式前，如果骨段数 ≠ 17，弹对话框说明差距，而不是只 toast。

**改动**：
- 在 `ui_panels.py` 加 `draw_anim_stick_count_dialog(ui_state, editor_state)`：显示当前骨段数 vs 17，列出后续 commit 会加的"补足/帮助"按钮入口（commit 4 之前先放占位，给"取消"按钮关闭即可）。
- `UIState` 加 `_show_anim_stick_count_dialog: bool = False`、`_anim_stick_count_diff: int = 0`。
- 把 `enter_animation_mode` 的 `try/except` 调用点（[ui_panels.py:2498/2560/2663](ui_panels.py:2498)、[main_animation.py:731/743/851](main_animation.py:731)）改为先检查 `len(sticks) != EXPECTED_STICK_COUNT`，命中则置位 dialog 标志，跳过原 try/except。
- 保留 `enter_animation_mode` 内部的 `ValueError` 兜底（防御万一），但 UI 不再依赖它。

**验收**：用 16 / 18 骨段的 skeleton 试图进动画 → 对话框弹出说明差几根，点"取消"回到绑骨。

**补充**：`> 17` 时对话框除显示差距数外，应加一行提示文字引导用户手动操作，如"请手动合并或删除多余骨段后重试"（翻译一条 `stick_count_over_target_hint`）。

---

### Commit 3 — `feat(bind): dummy stick classification helper`

**目标**：在 `EditorState` 上加一个纯派生函数 `classify_sticks()` 和 `dummy_stick_indices()`，给后续 UI / 渲染区分用。**纯逻辑、无副作用、无数据结构变更**。

**改动**：
- `editor_state.py` 加：
  ```python
  def classify_sticks(self) -> dict[int, str]:
      """每根 stick 标 'skinned' | 'connected_unskinned' | 'dummy'。
      dummy = 无 voxel binding 且 两端点不与其他 stick 共享。
      """
  def dummy_stick_indices(self) -> list[int]:
      ...
  ```
- 单测可选：写 1-2 个 vanilla preset case 验证。

**验收**：`presets/human_skeleton.json` 调用 `classify_sticks()` 全 17 根都不是 dummy；手动加一对孤立粒子 + 一根 stick → 该 stick 标记 dummy。

**补充**：`connected_unskinned`（有拓扑连接但无 voxel binding）在 Commit 5 的骨段列表中应给出弱提示，如名字旁加灰色 `(未绑定)` 标记，帮助用户发现遗漏的绑定。

---

### Commit 4 — `feat(bind): one-click pad to 17 sticks`

**目标**：骨段面板加按钮 `Pad to 17 (+N dummy)`，自动补 N 对孤立粒子 + N 根 dummy stick。

**改动**：
- `EditorState.pad_dummy_sticks_to_target(target=EXPECTED_STICK_COUNT)`：
  - 计算 `need = target - len(self.sticks)`，需要 ≤ 0 直接返回。
  - 选一块远离 voxel 模型的位置（比如沿 -X 轴远端），按 `(particle_count_now + i)` 步进生成两两成对的粒子。
  - 粒子命名 `dummy_pX_a` / `dummy_pX_b`，id 取当前最大 id + 偏移避免冲突。
  - 调 `_normalize_stick_indices()` + `_mark_skeleton_changed()`。
  - 推 undo（标准 `_push_undo`）。
- 在 commit 2 的对话框里加这个按钮：仅当 `len(sticks) < 17` 时启用。
- 骨段面板顶部也直接显示这个按钮，永远可点（`> 17` 时灰）。
- 翻译：`pad_to_target_sticks` / `pad_to_target_sticks_tip` 两条。

**验收**：12 骨段 skeleton 点 Pad 按钮 → 立刻变 17 / 17（5 对孤立粒子在远端）。能 Ctrl+Z 撤销。

**补充**：
- **命名防冲突**：dummy 粒子用 `_dummy_N_a` / `_dummy_N_b` 前缀（下划线开头降低与用户命名冲突概率），生成前检查名称冲突，冲突时自动加后缀。
- **位置启发式**：不写死 -X 远端，改为动态计算 `min(voxel_x) - max(voxel_span) * 1.5`（确保在任何模型尺寸下都在视口外），无 voxel 时默认放 `(-50, 0, 0)`。
- **预设加载交互**：加载预设后 dummy 粒子/骨段应被清理（预设自带完整骨架拓扑）。`load_skeleton_preset` 内部调用一次 `_prune_dummy_sticks()` 清理孤立 dummy 后再恢复。
- **幂等性**：`pad_dummy_sticks_to_target` 需判断 `need <= 0` 时直接返回（已在 plan 中）；但若已有部分 dummy 且仍不足 17，应只补差额，不重复创建。

---

### Commit 5 — `feat(bind): visually distinguish dummy sticks`

**目标**：dummy stick 在 3D 视口染色更暗 / 配独立可见性开关；骨段列表分组显示。

**改动**：
- `renderer.py` 画骨段线段时：dummy stick（按 `dummy_stick_indices()`）颜色乘 0.4 alpha 或换灰色。
- **Renderer API**：`upload_skeleton_lines()` 新增可选参数 `dummy_indices: set[int] | None = None`，不混用现有 `visible` 字段（`visible` 是用户偏好，dummy 是拓扑属性，语义不同）。渲染时 dummy stick 的颜色/alpha 由该集合决定。
- `UIState.show_dummy_sticks: bool = True`，骨段面板加 checkbox 切换。
- 骨段列表（[ui_panels.py:1099](ui_panels.py:1099) 附近）按 classify 结果分两段渲染：先 skinned + connected_unskinned，再 `--- Dummy (N) ---` 折叠区。
- 翻译：`show_dummy_sticks` / `dummy_section_header`。

**验收**：补 5 根 dummy 后，视口能立刻分辨真实骨段和 dummy；toggle 可隐藏 dummy。

---

### Commit 6 — `feat(bind): guard against accidental stick removal at target`

**目标**：在骨段数 == 17 时删除骨段会破坏动画就绪态，给用户红字警告。

**改动**：
- 删除骨段的入口（搜 `del self.sticks` / `pop` / 删除按钮 handler）增加 toast：`tr(ui_state, "stick_count_dropped_below_target", count=N)`，配色 warning。
- 不阻断操作（用户有时确实要重新设计），只提示。
- 翻译：一条 warning 字符串。

**验收**：17 根状态下删 1 根，弹 "骨段数已降至 16/17，进入动画模式将受阻" toast。

---

### Commit 7 — `docs(architecture): document heterogeneous skeleton workflow`

**目标**：补一节 `docs/architecture/ARCHITECTURE.md`：异形骨工作流（先建真实拓扑 → Pad to 17 → 检查 dummy 视觉 → 进动画）。说明 dummy 是派生定义不是数据 flag、为什么 17 是引擎硬约束。

**改动**：
- 在 § 7 「关键约定与隐式知识」加一小节 `异形骨与 dummy stick`。中英两份。
- **修正 § 7 已有过期内容**：`EXPECTED_PARTICLE_COUNT = 15` 小节 → 改为 `EXPECTED_STICK_COUNT = 17`，说明引擎只校验骨段数、不限粒子数和拓扑。

**验收**：人读完一遍能复述出"为什么要补 17 根"和"dummy 是怎么识别的"。

---

## 实现顺序与依赖

- Commit 1：独立。
- Commit 2：独立（对话框先放占位按钮，commit 4 落地后再补功能）。
- Commit 3：commit 4、5 的依赖。
- Commit 4：依赖 3，复用 commit 2 的对话框。
- Commit 5：依赖 3。
- Commit 6：独立。
- Commit 7：所有 feature commit 之后写。

建议按 1 → 3 → 2 → 4 → 5 → 6 → 7 实现（先把派生分类立起来，UI 跟上）。

## 不做的事 / 范围外

- **不做 dummy stick 的数据 flag**（派生即可，避免一致性负担）
- **不做自动合并 > 17 骨段**（语义不明确，让用户手动）
- **不做 dummy stick 在动画文件里被特殊处理**（动画只关心粒子位置，dummy 粒子和普通粒子在 XML 里没区别）
- **不做 dummy stick 模板预设**（先看 commit 4 够不够用）

