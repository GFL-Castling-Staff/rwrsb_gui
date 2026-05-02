# rwrsb v1.1.1 发布说明

> [English](RELEASE_NOTES_v1.1.1_EN.md)

本版本是 v1.1.0 之后的维护修复版本，重点解决 gizmo 旋转中心一致性、动画切换后的蒙皮污染，以及更多骨段在大姿态变化下的 roll 漂移。

## 亮点

- **两个工具统一旋转中心选择**：`rwrsb_bind` 和 `rwrsb_anim` 的 gizmo 圆环旋转都跟随同一个 pivot 下拉框，支持 Active 粒子、选区几何中心和世界原点。
- **canonical bind pose 修复**：动画模式录制蒙皮局部偏移时使用加载 skeleton/model 时快照的 canonical pose，并先还原 canonical voxel 位置，避免切换动画后沿用上一段动画变形后的体素。
- **表驱动 lateral reference 蒙皮**：把原先只覆盖 hip/shoulder 横骨的 roll 参考扩展为规则表，覆盖颈头、手部末端、胸肩交叉骨和腿部骨段，减少纯两点骨段的绕轴扭转漂移。

## 改动内容

### Gizmo / UI

- `UIState.rotate_pivot_mode` 现在同时驱动两个工具的 gizmo 中心和圆环旋转 pivot。
- pivot 模式支持：
  - `active`：Active 粒子；如果 Active 不在选择集中，fallback 到选区中心。
  - `centroid`：当前选中粒子的几何中心。
  - `world_origin`：世界原点。
- `rwrsb_bind` 不再固定以 Active 粒子作为 rotate pivot。

### 蒙皮

- 新增 `_canonical_skeleton_pose` 和 `_canonical_voxel_positions`，在加载 skeleton/model 后快照 canonical bind 状态。
- `enter_animation_mode()` 录制 bind pose 时优先使用 canonical skeleton pose。
- 录制 voxel local offsets 前会把 `self.voxels` 恢复到 canonical voxel positions，防止上一段动画的实时蒙皮结果污染下一段动画。
- lateral reference 规则改为表驱动：
  - `"midspine_to_origin"`：hip / shoulder bridge。
  - `"shoulder_lateral"`：neck→head、elbow→hand、midspine/shoulder、shoulder/neck 等上半身骨段。
  - `"hip_lateral"`：hip→midspine 和腿部骨段。

### 文档

- README 同步 gizmo pivot、canonical bind pose 和 lateral reference 蒙皮说明。
- ARCHITECTURE 同步动画模式进入流程、canonical 状态字段、表驱动 lateral reference 规则和 gizmo pivot 语义。
- 过时的 Claude 实现提示 / handoff 文档移到本地 `history/archive/`，并通过 `.gitignore` 排除，不再作为发布文档的一部分。

## 已知限制

- gizmo 旋转仍然是“选中粒子坐标旋转”，不是持久化的对象级 transform；如果需要像 Blender 对象模式那样整体旋转 voxel + skeleton，应该作为单独功能设计。
- 非 90° 整体模型旋转如果直接落到 voxel 坐标，仍会遇到 XML 体素坐标整数化导致的重采样/失真问题。
