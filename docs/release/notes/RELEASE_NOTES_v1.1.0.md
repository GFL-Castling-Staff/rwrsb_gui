# rwrsb v1.1.0 发版说明

> [English](RELEASE_NOTES_v1.1.0_EN.md)

## 亮点

- **Blender 风格选区 gizmo**：`rwrsb_anim` 与 `rwrsb_bind` 两个工具都引入，选中粒子后视口出现 3 轴箭头 + 圆环 + 中心球。点把手锁轴平移 / 旋转，比用修饰键直观，但 Shift/Ctrl/Alt 修饰键路径仍然保留。
- **Oriented voxel rendering**：动画模式下每个体素 cube 朝向跟随骨段一起旋转，消除非 90° 旋转下肢体边缘的"楼梯"伪影。GPU 数据走 per-bone uniform mat4，10w 体素也只需每帧 8 KB 上传。
- **身体横骨蒙皮修复**：胯部 (`righthip<->lefthip`) 和肩部 (`rightshoulder<->leftshoulder`) 横骨用 midspine 作为 roll 参考，告别躯干侧扭/前倾时的胯部和肩部体素扭转漂移。
- **`rwrsb_bind` 默认进入体素框选模式**（之前是涂抹笔刷），避免误涂。

非破坏性升级：XML 格式与 v1.0.0 完全兼容，没有 breaking change，所以走 1.1.0 而不是 2.0.0。

---

## 本次改动内容

### 新功能（gizmo / 渲染 / UI）

- 选区 gizmo（两个工具）：屏幕空间恒定缩放、hover 高亮、命中即消费点击；箭头/中心 → 平移、圆环 → 旋转（1px=1°，Ctrl 15° 吸附）；可在 toolbar 设置 popup 调箭头长度（40-200px）
- Oriented voxel rendering：renderer 加 per-bone orientation uniform mat4[128] + per-voxel bone idx VBO；shader 加 `mat3 R = mat3(u_bone_orientations[int(i_bone_idx)])` 旋转
- 身体横骨蒙皮：`_compute_body_bridge_frame` 用横骨两端 + midspine 三点构造正交基，bind 和 now 自洽；识别窗口窄（仅 hip/shoulder pair）
- `rwrsb_anim` 移除 toolbar Move/Rotate 切换按钮，gizmo 接管平移/旋转区分
- `rwrsb_bind` 新增 toolbar `View...` popup（世界原点开关 + gizmo 箭头长度滑条）
- `rwrsb_bind` 视口显示世界原点 RGB 三轴指示（与 anim 一致）
- `rwrsb_bind` 新增 rotate drag 路径（之前只有平移）

### 行为变化

- `EditorState.tool_mode` 默认值：`"brush"` → `"voxel_select"`
- `rwrsb_anim` 直接拖粒子无条件走平移路径；旋转必须通过 gizmo 圆环触发
- Length-Clamp 不再受 `anim_drag_mode` 门控，启用后对所有平移生效（gizmo 箭头 + 直接拖粒子）

### Bug 修复

- 拖动时实时蒙皮：粒子拖动期间体素跟随骨架变形，不再"等到播放才看到效果"
- 删除 / 复制帧后视口姿态保持在 `playback_time` 插值，不再强制跳到某个 keyframe
- 蒙皮 bind pose 旋转跟踪修复，避免 stick frame 不连续时的体素抖动
- 选区 gizmo 在侧视图下大小恒定（之前会因世界 X 轴与视线平行导致缩放爆炸）

### 国际化

- UI 文案完整英文翻译（v1.0 之后增量加入），与中文同步通过 `tr(ui_state, key)` 双语
- 文档英文版（README_EN / ARCHITECTURE_EN / RELEASE_EN / CONTRIBUTING_EN / RELEASE_NOTES_*_EN）

### 文档

- ARCHITECTURE 新增第 10 节"选区 gizmo 与 oriented voxel rendering"，第 7 节新增"身体横骨蒙皮"子段；字段表与 tool_mode 默认值同步
- README 功能概览补 gizmo / 世界原点 / 默认体素框选；动画工具段补蒙皮 / 体素朝向说明

---

## 发版前项目主需要手动做的事

- [ ] 运行 `python main.py`，截图主界面（包含 gizmo 显示效果），更新 `docs/screenshot.png`
- [ ] 运行 `build.bat`，确认输出在 `dist\rwrsb_bind\rwrsb_bind.exe`
- [ ] 启动两个 exe，确认窗口正常运行；选个粒子验证 gizmo 渲染、拖箭头、拖圆环
- [ ] 加载 vanilla 动画播放，肉眼检查肢体在非 90° 旋转下边缘平滑（无阶梯）；胯部/肩部姿态扭转时不再乱卷
- [ ] 打 tag `v1.1.0`、压 zip 为 `rwrsb_bind-v1.1.0-windows.zip` 上传 GitHub Release

---

## 已知限制

- bind 工具的 rotate pivot 暂固定为 active 粒子，不像 anim 那样有 active/centroid/world_origin 切换。如果有需求可后续加。
- gizmo 旋转方向当前是 "1px = 1°，向右为正"，绕不同轴时方向感可能反直觉。本版本暂不调整，看实际反馈。
- Oriented voxel 性能在百万级体素的极端模型下未实测；当前架构理论上支持，每帧上传仍是 ~8 KB。
