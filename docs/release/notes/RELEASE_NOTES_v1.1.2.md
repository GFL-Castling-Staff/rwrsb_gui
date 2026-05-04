# rwrsb v1.1.2 发布说明

> [English](RELEASE_NOTES_v1.1.2_EN.md)

本版本是 v1.1.1 之后的维护版本，重点是把 `rwrsb_bind` 的骨架建模工作流落地到视口操作上（点选粒子 / stick、拉链建骨段、批量平移、删除、撤销恢复选择），并修掉粒子面板树节点导致的选择状态被逐帧覆盖的 bug。

## 亮点

- **视口直接建骨架**：选中粒子、连骨段、生成新粒子、拉链一气呵成都能在视口里完成，不必来回点右侧面板。
- **粒子面板树节点不再覆盖外部 active**：以前展开树节点会每帧把 `active_particle_idx` 强制设回该 idx，导致点空白取消不掉、右侧闪烁、gizmo 锁在世界原点；现在只有点 header 当帧才设 active。
- **撤销 / 重做恢复选择集**：undo snapshot 把 `selected_particles` 也存进去，回退后选择状态保持一致。

## 改动内容

### 绑骨视口工作流（`rwrsb_bind`）

- 视口点击 stick 即可设为 active stick；普通点击 stick 会清空粒子选择，避免后续拉链从错误粒子起步。
- 重叠粒子上重复点击会循环切换命中的粒子。
- 粒子拾取优先级高于 gizmo，避免 active 粒子的 80px 箭头吞掉对其它粒子的点击。
- 选中两个粒子时一键 `connect`，自动建立 stick。
- 在 active 粒子附近沿 X / Y / Z 生成新粒子（spawn-near）。
- 拉链工作流：在 active 粒子沿轴生成新粒子并自动连一根 stick，新粒子自动设为 active，便于继续拉。
- 选中粒子或 active stick 都可用 `Delete` 键 / 删除按钮删除，整批删除是一次 undo。
- 方向键平移所有 selected_particles，整次平移合并为一次 undo。
- mirror 模式下移动粒子时网格吸附会把法线方向也量化到栅格上。
- 框选 stale 修饰键 bug 修复：每次起新框时按下的修饰键决定语义。

### 粒子面板

- 列表支持名字 / ID 过滤，active 粒子的树节点会自动展开，便于跟随选择切换。
- **修复**：树节点不再每帧无条件 `set_active_particle`，改为只在 header 被点击当帧才设。修复了"点空白取消不掉、右侧闪烁、gizmo 锁世界原点"三联症状。

### 渲染 / 高亮

- bind 工具同步 `renderer.highlight_active_particle_idx`，多选时区分 active 粒子（青色）和其它选中粒子（淡黄）。

### 数据 / 持久化

- `save_xml` 始终使用当前 `self.sticks`，不再写出加载时的快照。
- undo snapshot 包含 `selected_particles`，undo / redo 后选区状态完整恢复。

## 已知限制

- 与 v1.1.1 一致：gizmo 旋转仍然是"选中粒子坐标旋转"，不是持久化对象级 transform。
- 非 90° 整体模型旋转直接落到 voxel 坐标，仍会遇到 XML 整数化的重采样/失真问题。
