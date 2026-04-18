# 任务:rwrsb_gui F8 (骨段可视一键切换) + F9 (ctypes 文件对话框) + Toast 接入迁移

## 项目背景

rwrsb_gui 是 RWR 体素骨架绑定编辑器。上一轮已经完成 F10 日志系统 + Toast 通知基础设施(`logger_setup.py` 模块 + `UIState.push_toast()` + `draw_toasts()` 渲染)。本轮做三件事:

1. **F8 骨段可视一键全显/全隐** — 三态切换按钮
2. **F9 ctypes + GetOpenFileNameW 文件对话框** — 新增 `file_dialogs.py`,替换现有 imgui 文本输入式对话框
3. **Toast 接入迁移** — 把现有 `_bone_error` / `_load_error` / `_save_error` 赋值点和新增的成功点位接入 `push_toast`

按 4 次 commit 分次交付,具体 commit 边界见下面"交付方式"。

---

## 开工前必读

再读一遍下面的文件以便对当前代码建立最新认知(上一轮改过了,不要相信记忆):

- `main.py` — 尤其是 `_load_file`(已经接了两条 toast) 和 `##overlay` 里 `draw_toasts` 调用方式
- `ui_panels.py` — `UIState.push_toast` 签名、`draw_toasts` 实现、`_TEXT` 字典结构、`_draw_stick_list` 当前逐条 `o`/`-` 按钮、`draw_load_dialog` / `draw_save_dialog` / `draw_preset_dialog` 当前对话框实现、`draw_bone_panel` 里镜像 / 对齐按钮的 try/except 结构
- `editor_state.py` — `StickEntry.clone()`、`_snapshot` / `_restore_snapshot`、`align_selected_particles` / `enter_mirror_mode` / `set_mirror_plane_from_camera` / `set_mirror_origin_from_pair_midpoint` / `normalize_mirror_plane_normal` 等方法的错误抛出点
- `xml_io.py` — 保存/解析失败的异常路径
- `rwrsb_gui.spec` — 确认还是 `console=False`,打包目标是 Windows

**重点确认**(上一轮结尾说过的):所有 `_bone_error` / `_load_error` / `_save_error` 赋值点要列出来 — 它们是 Toast 迁移的全部目标。在你动手前先 grep 一次这三个字段,确认清单完整。

---

## ================================================================
## Commit 1: F8 骨段可视一键切换
## ================================================================

### 设计决策(已拍板,不需再问)

1. **UI 状态视角**:`stick.visible` 彻底视为 UI 状态,不进 undo 栈。
2. **要改 `StickEntry.clone()` 的语义**:clone 不再拷贝 `visible`,克隆出来的 stick visible 默认 `True`。
3. **但 undo 不能把用户的可视偏好清掉**:在 `_snapshot` / `_restore_snapshot` 里**独立保留 visible** — snapshot 时按 `particle_a_id + particle_b_id` 记录 visible(因为 constraint_index 在 snapshot 间不稳定);restore 后按同一键查回来并覆盖,没匹配的默认 True。
4. **三态按钮**:sticks 为空时按钮 disabled;全显示时按钮显示"全部隐藏";全隐藏或混合时按钮显示"全部显示"。
5. **I18n**:新增 `show_all_sticks` / `hide_all_sticks` 两个 key。

### 交付内容

#### `editor_state.py`

1. **修改 `StickEntry.clone()`** — 不再拷贝 `visible`:

   ```python
   def clone(self):
       cloned = StickEntry(
           self.constraint_index,
           self.particle_a_id,
           self.particle_b_id,
           self.name,
           tuple(self.color),
       )
       # visible 是 UI 状态,不进克隆(undo 里靠独立机制保留)
       return cloned
   ```

2. **修改 `_snapshot()`** — 追加 `visible_by_pair`:

   ```python
   def _snapshot(self):
       return {
           "particles": copy.deepcopy(self.particles),
           "sticks": self._clone_sticks(),
           "bindings": copy.deepcopy(self.bindings),
           "active_stick_idx": self.active_stick_idx,
           "active_particle_idx": self.active_particle_idx,
           # 独立保留可视状态,不参与 undo/redo 回滚
           "visible_by_pair": {
               (s.particle_a_id, s.particle_b_id): s.visible for s in self.sticks
           },
       }
   ```

3. **修改 `_restore_snapshot()`** — 恢复后按 pair 覆盖 visible:

   ```python
   def _restore_snapshot(self, snapshot):
       self.particles = copy.deepcopy(snapshot["particles"])
       self.sticks = [stick.clone() for stick in snapshot["sticks"]]
       self.bindings = copy.deepcopy(snapshot["bindings"])
       self.active_stick_idx = int(snapshot["active_stick_idx"])
       self.active_particle_idx = int(snapshot.get("active_particle_idx", -1))
       self._normalize_stick_indices()

       # 恢复可视状态(跨 snapshot 按 particle pair 匹配,不按 constraint_index)
       vis_map = snapshot.get("visible_by_pair", {})
       for s in self.sticks:
           key = (s.particle_a_id, s.particle_b_id)
           # 兼容反向 pair 的匹配(保险)
           if key in vis_map:
               s.visible = vis_map[key]
           elif (s.particle_b_id, s.particle_a_id) in vis_map:
               s.visible = vis_map[(s.particle_b_id, s.particle_a_id)]
           # 没匹配就默认 True(新增 stick 或数据被改到匹配不上)

       self._dirty = True
       self.gpu_dirty = True
       self.skeleton_dirty = True
   ```

4. **新增两个辅助方法**:

   ```python
   def set_all_sticks_visible(self, visible: bool):
       """批量设置所有 stick 的 visible。触发 GPU 重传但不入 undo。"""
       for s in self.sticks:
           s.visible = bool(visible)
       self.gpu_dirty = True

   def all_sticks_visibility_state(self):
       """返回 'all' | 'none' | 'mixed' | 'empty'。UI 按钮状态用。"""
       if not self.sticks:
           return "empty"
       vis_count = sum(1 for s in self.sticks if s.visible)
       if vis_count == 0:
           return "none"
       if vis_count == len(self.sticks):
           return "all"
       return "mixed"
   ```

#### `ui_panels.py`

1. **`_TEXT` 字典两个 key 加中英翻译**:

   ```python
   # en:
   "show_all_sticks": "Show all",
   "hide_all_sticks": "Hide all",
   # zh:
   "show_all_sticks": "全部显示",
   "hide_all_sticks": "全部隐藏",
   ```

2. **修改 `_draw_stick_list`,在 for 循环之前加两/三个按钮**:

   ```python
   def _draw_stick_list(ui_state, editor_state):
       sticks = editor_state.sticks
       particles_by_id = {p["id"]: p for p in editor_state.particles}
       to_unbind = -1

       # ── F8: 可视一键切换 ──
       state = editor_state.all_sticks_visibility_state()
       if state == "empty":
           # 无 stick 时禁用按钮但仍占位,避免布局抖动
           imgui.begin_disabled()
           imgui.button(tr(ui_state, "show_all_sticks"))
           imgui.end_disabled()
       elif state == "all":
           # 当前全显示,按钮显示"全部隐藏"
           if imgui.button(tr(ui_state, "hide_all_sticks") + "##hide_all"):
               editor_state.set_all_sticks_visible(False)
       else:  # "none" 或 "mixed"
           # 当前全隐藏或混合,按钮显示"全部显示"
           if imgui.button(tr(ui_state, "show_all_sticks") + "##show_all"):
               editor_state.set_all_sticks_visible(True)

       imgui.separator()

       for idx, stick in enumerate(sticks):
           # ... 原有逐条渲染保持不变
   ```

   **注意**:`imgui.begin_disabled` / `imgui.end_disabled` 如果 pyimgui 版本不支持,用 `imgui.push_style_var(imgui.STYLE_ALPHA, 0.5)` 灰掉加一个 disabled-style 按钮;或者干脆这个分支 `imgui.text_disabled("...")` 显示提示文本。自己试,挑能 work 的方案。

### F8 验收

- [ ] sticks 非空、全显示 → 按钮显示"全部隐藏",点击后所有 stick 不可视,视觉上绑定的 voxel 降饱和
- [ ] 全隐藏 → 按钮显示"全部显示",点击后全部可视
- [ ] 混合状态 → 按钮显示"全部显示",点击后全部可视
- [ ] 每条 stick 后面的单独 `o`/`-` 按钮仍然工作,切换后三态按钮文案跟随正确更新
- [ ] 无 sticks 时按钮 disabled 不可点
- [ ] 改了几条 stick 可视,做一次**结构操作**(加一条 stick),然后 undo — undo 回滚结构,但**原来那几条的可视状态保留**
- [ ] F8 动作**不入 undo 栈** — 点"全部隐藏"后按 Ctrl+Z,不会恢复可视

### Commit 1 Conventional Commit message

```
feat(F8): one-click show/hide all sticks with three-state toggle
```

---

## ================================================================
## Commit 2: F9 ctypes GetOpenFileNameW 文件对话框
## ================================================================

### 设计决策

1. **平台**:仅 Windows。Linux/macOS 上 ctypes 调不到 comdlg32,要兜底到保留原有 imgui 输入框。检测方式:`sys.platform != "win32"` 或 `ctypes.windll.comdlg32` 加载失败。
2. **布局**:采用**方案 A** — 弹窗里顶部是"浏览..."按钮(调系统对话框),下方保留"或直接输入/粘贴路径"的 imgui input_text。保留原 OK/Cancel。
3. **对话框是同步阻塞**:`GetOpenFileNameW` 调用期间 GLFW 主循环冻结,接受这个行为(Windows 原生 app 的标准)。冻结结束后**补救 Toast 过期**:记录调用前 `t0 = time.time()`,返回后 `dt = time.time() - t0`,把所有当前 toasts 的 `expires_at` 和 `fade_start` 都加上 dt,让冻结期间不扣寿命。
4. **filter 格式是坑**:不能用 `c_wchar_p`(会在第一个 `\0` 截断),必须用 `create_unicode_buffer` 构造,最后两个 `\0\0` 不能少。
5. **返回值**:成功返回 `str` 路径;用户取消返回 `None`;调用失败(API 错误)抛异常由上层捕获。

### 交付内容

#### 新建 `file_dialogs.py`

```python
"""
file_dialogs.py
Windows 原生文件对话框(ctypes + comdlg32 GetOpenFileNameW / GetSaveFileNameW)。
非 Windows 平台函数返回 None,调用方应保留文本输入框作为兜底。
"""
import ctypes
import ctypes.wintypes as wt
import sys
import logging
from typing import Optional, Sequence, Tuple

logger = logging.getLogger(__name__)


def _is_supported() -> bool:
    return sys.platform == "win32"


# OPENFILENAMEW 结构体(参考 Win32 CommDlg.h)
class _OPENFILENAMEW(ctypes.Structure):
    _fields_ = [
        ("lStructSize",       wt.DWORD),
        ("hwndOwner",         wt.HWND),
        ("hInstance",         wt.HINSTANCE),
        ("lpstrFilter",       wt.LPCWSTR),
        ("lpstrCustomFilter", wt.LPWSTR),
        ("nMaxCustFilter",    wt.DWORD),
        ("nFilterIndex",      wt.DWORD),
        ("lpstrFile",         wt.LPWSTR),
        ("nMaxFile",          wt.DWORD),
        ("lpstrFileTitle",    wt.LPWSTR),
        ("nMaxFileTitle",     wt.DWORD),
        ("lpstrInitialDir",   wt.LPCWSTR),
        ("lpstrTitle",        wt.LPCWSTR),
        ("Flags",             wt.DWORD),
        ("nFileOffset",       wt.WORD),
        ("nFileExtension",    wt.WORD),
        ("lpstrDefExt",       wt.LPCWSTR),
        ("lCustData",         ctypes.c_void_p),
        ("lpfnHook",          ctypes.c_void_p),
        ("lpTemplateName",    wt.LPCWSTR),
        ("pvReserved",        ctypes.c_void_p),
        ("dwReserved",        wt.DWORD),
        ("FlagsEx",           wt.DWORD),
    ]


# Flags
_OFN_FILEMUSTEXIST   = 0x00001000
_OFN_PATHMUSTEXIST   = 0x00000800
_OFN_HIDEREADONLY    = 0x00000004
_OFN_EXPLORER        = 0x00080000
_OFN_OVERWRITEPROMPT = 0x00000002


def _build_filter(filters: Sequence[Tuple[str, str]]) -> ctypes.Array:
    """
    filters = [("VOX files", "*.vox"), ("All files", "*.*")]
    返回 ctypes wide buffer,格式 "VOX files\0*.vox\0All files\0*.*\0\0"
    """
    parts = []
    for label, pattern in filters:
        parts.append(label)
        parts.append(pattern)
    s = "\0".join(parts) + "\0\0"   # 末尾 double null
    buf = ctypes.create_unicode_buffer(s, len(s))
    return buf


def _common_ofn(title: str, filters, initial_path: str = "") -> _OPENFILENAMEW:
    path_buf = ctypes.create_unicode_buffer(1024)
    if initial_path:
        # 预填初始路径(不超过缓冲长度 - 1)
        init = initial_path[:1023]
        for i, ch in enumerate(init):
            path_buf[i] = ch
    filter_buf = _build_filter(filters)

    ofn = _OPENFILENAMEW()
    ofn.lStructSize = ctypes.sizeof(_OPENFILENAMEW)
    ofn.hwndOwner = None
    ofn.lpstrFilter = ctypes.cast(filter_buf, wt.LPCWSTR)
    ofn.lpstrFile = ctypes.cast(path_buf, wt.LPWSTR)
    ofn.nMaxFile = 1024
    ofn.lpstrTitle = title
    ofn.Flags = _OFN_EXPLORER | _OFN_HIDEREADONLY

    # 持有引用防止 GC
    ofn._path_buf = path_buf
    ofn._filter_buf = filter_buf
    return ofn


def open_file_dialog(
    title: str,
    filters: Sequence[Tuple[str, str]],
    initial_path: str = "",
) -> Optional[str]:
    """
    弹 Windows 原生"打开文件"对话框。返回用户选择的路径;用户取消返回 None。
    filters: [("VOX files", "*.vox"), ...]
    非 Windows 平台直接返回 None。
    """
    if not _is_supported():
        return None

    try:
        comdlg32 = ctypes.windll.comdlg32
    except (OSError, AttributeError):
        logger.warning("comdlg32 not available, falling back")
        return None

    ofn = _common_ofn(title, filters, initial_path)
    ofn.Flags |= _OFN_FILEMUSTEXIST | _OFN_PATHMUSTEXIST

    GetOpenFileNameW = comdlg32.GetOpenFileNameW
    GetOpenFileNameW.argtypes = [ctypes.POINTER(_OPENFILENAMEW)]
    GetOpenFileNameW.restype = wt.BOOL

    ok = GetOpenFileNameW(ctypes.byref(ofn))
    if not ok:
        # 用户取消或报错。CommDlgExtendedError 返回 0 = 取消。
        err = comdlg32.CommDlgExtendedError()
        if err != 0:
            logger.warning("GetOpenFileNameW failed, CommDlgExtendedError=%d", err)
        return None

    return ofn._path_buf.value


def save_file_dialog(
    title: str,
    filters: Sequence[Tuple[str, str]],
    initial_path: str = "",
    default_ext: str = "",
) -> Optional[str]:
    """
    弹 Windows 原生"保存文件"对话框。返回用户选择的路径;用户取消返回 None。
    default_ext 例如 "xml",会自动补后缀。
    """
    if not _is_supported():
        return None

    try:
        comdlg32 = ctypes.windll.comdlg32
    except (OSError, AttributeError):
        logger.warning("comdlg32 not available, falling back")
        return None

    ofn = _common_ofn(title, filters, initial_path)
    ofn.Flags |= _OFN_OVERWRITEPROMPT | _OFN_PATHMUSTEXIST
    if default_ext:
        ofn.lpstrDefExt = default_ext

    GetSaveFileNameW = comdlg32.GetSaveFileNameW
    GetSaveFileNameW.argtypes = [ctypes.POINTER(_OPENFILENAMEW)]
    GetSaveFileNameW.restype = wt.BOOL

    ok = GetSaveFileNameW(ctypes.byref(ofn))
    if not ok:
        err = comdlg32.CommDlgExtendedError()
        if err != 0:
            logger.warning("GetSaveFileNameW failed, CommDlgExtendedError=%d", err)
        return None

    return ofn._path_buf.value
```

#### 修改 `ui_panels.py`

**`_TEXT` 字典加三个 key**(中英):

```python
# en:
"browse": "Browse...",
"or_paste_path": "or paste a path below:",
"file_dialog_unavailable": "System file dialog unavailable, enter path manually:",
# zh:
"browse": "浏览...",
"or_paste_path": "或直接输入/粘贴路径:",
"file_dialog_unavailable": "系统对话框不可用,请手动输入路径:",
```

**修改 `draw_load_dialog`**(在 popup 里 OK 按钮之前加 "浏览..." 按钮区):

```python
def draw_load_dialog(ui_state, editor_state, renderer, skeleton_sticks_ref, WIN_W, WIN_H):
    if not ui_state.show_load_dialog:
        return
    # 导入放在函数内避免循环 import 风险
    from file_dialogs import open_file_dialog, _is_supported

    title = tr(ui_state, "open_file")
    imgui.open_popup(title)
    imgui.set_next_window_position(WIN_W // 2 - 270, WIN_H // 2 - 80)
    imgui.set_next_window_size(540 * ui_state.ui_scale, 160 * ui_state.ui_scale)
    opened, _ = imgui.begin_popup_modal(title, flags=imgui.WINDOW_NO_RESIZE)
    if opened:
        fmt = "VOX" if ui_state.load_mode == "vox" else "XML"

        # ── F9: 浏览按钮 ──
        if _is_supported():
            if imgui.button(tr(ui_state, "browse") + "##browse_load", width=-1):
                _handle_browse_load(ui_state, editor_state, renderer, skeleton_sticks_ref)
            imgui.text_disabled(tr(ui_state, "or_paste_path"))
        else:
            imgui.text_colored(tr(ui_state, "file_dialog_unavailable"), 1.0, 0.8, 0.3, 1.0)

        imgui.text(tr(ui_state, "enter_file_path", fmt=fmt))
        imgui.set_next_item_width(-1)
        _, ui_state.load_path_buf = imgui.input_text("##lp", ui_state.load_path_buf, 1024)

        # ... 原有 OK/Cancel 保持不变
```

**新增辅助 `_handle_browse_load` 函数**(放在 `ui_panels.py` 文件级或 `draw_load_dialog` 近旁):

```python
def _handle_browse_load(ui_state, editor_state, renderer, skeleton_sticks_ref):
    """调 Windows 原生打开对话框,选中后立即执行加载流程。"""
    import time
    from file_dialogs import open_file_dialog

    if ui_state.load_mode == "vox":
        filters = [("MagicaVoxel files", "*.vox"), ("All files", "*.*")]
    else:
        filters = [("XML files", "*.xml"), ("All files", "*.*")]

    t0 = time.time()
    try:
        path = open_file_dialog(tr(ui_state, "open_file"), filters)
    except Exception as exc:
        ui_state._load_error = str(exc)
        ui_state.push_toast(f"打开对话框失败: {exc}", "error", exc_info=True)
        return
    finally:
        # 补救 toast 过期:冻结期间不扣寿命
        dt = time.time() - t0
        for t in ui_state.toasts:
            t.expires_at += dt
            t.fade_start += dt

    if path is None:
        # 用户取消,不提示
        return

    # 直接走加载流程
    try:
        if ui_state.load_mode == "vox":
            editor_state.load_vox(path, ui_state.trans_bias)
        else:
            sk = editor_state.load_xml(path, ui_state.trans_bias)
            skeleton_sticks_ref[0] = sk.get("sticks", [])
            renderer.upload_skeleton_lines(editor_state.particles, editor_state.sticks)
        editor_state.gpu_dirty = True
        ui_state._load_error = ""
        ui_state.show_load_dialog = False
        from pathlib import Path
        ui_state.push_toast(f"已加载: {Path(path).name}", "success")
    except Exception as exc:
        ui_state._load_error = str(exc)
        ui_state.push_toast(f"加载失败: {exc}", "error", exc_info=True)
```

**`draw_save_dialog` 同理改造**:加"浏览..."按钮,按下调 `save_file_dialog`,选中后立即调 `editor_state.save_xml(path, ...)` 并处理成功/失败 toast、关闭 dialog、补救 toast 过期。默认扩展名 `"xml"`,filters `[("XML files", "*.xml")]`。initial_path 用 `ui_state.save_path_buf` 或 `editor_state.source_path`。

**`draw_preset_dialog`**:本轮**不动**(preset 是 JSON 文件,走内部预设目录,不需要文件对话框)。

### F9 验收

- [ ] 点工具栏"打开 VOX",弹出旧 imgui dialog,里面有"浏览..."按钮
- [ ] 点"浏览...",弹 Windows 系统对话框,选 vox 文件,回来后 vox 加载成功、dialog 关闭、有绿色成功 toast
- [ ] 同样流程走 XML 打开 / XML 保存
- [ ] 系统对话框取消,不弹失败 toast,旧 dialog 保持打开,用户可以点 Cancel 退出
- [ ] 路径含中文(如 `D:\测试\模型.vox`),加载正常,toast 正确显示中文文件名
- [ ] 选了一个不存在的文件:`_OFN_FILEMUSTEXIST` 会让系统对话框自己提示,不会让我们的代码拿到不存在的路径
- [ ] 保存时同名文件:`_OFN_OVERWRITEPROMPT` 系统自己弹"覆盖?"确认
- [ ] 系统对话框期间 Toast 不过期 — 先弹一条 toast,立刻点"浏览...",慢慢选 10 秒,回来后 toast 剩余时间看起来合理
- [ ] 旧 input_text 输入框仍然可以用(粘贴路径 + OK)作为兜底

### Commit 2 Conventional Commit message

```
feat(F9): native Windows file dialog via ctypes GetOpenFileNameW/GetSaveFileNameW
```

---

## ================================================================
## Commit 3: Toast 迁移 — 现有 error 点位
## ================================================================

### 范围

把现有所有 `_bone_error = str(exc)` / `_load_error = str(exc)` / `_save_error = str(exc)` 赋值点改成**原赋值保留 + 额外 push 一条 error toast**。策略:

- 对话框内保留红字不动(之前已经这么定了),toast 只是额外反馈
- 开工前自己 grep 一次清单,**全覆盖**,别漏

### 清单(预期目标,开工前以 grep 实际结果为准)

在 `ui_panels.py` 里:

- `draw_load_dialog` OK 按钮 try/except 的 `_load_error = str(exc)` + `_load_error = tr(ui_state, "file_not_found")` → 都加 toast
- `draw_save_dialog` 保存按钮 try/except 的 `_save_error = str(exc)` → 加 toast
- `draw_preset_dialog` 里加载/保存/删除预设的每个 `_bone_error = str(exc)` → 加 toast
- `draw_bone_panel` 里 `align_selected_particles("x"/"y"/"z")` 的三处 → 加 toast
- `draw_bone_panel` 里 `enter_mirror_mode` 的 → 加 toast
- `draw_bone_panel` 里 `set_mirror_plane_from_camera` / `set_mirror_origin_from_pair_midpoint` / `normalize_mirror_plane_normal` 三处 → 加 toast
- `_draw_active_stick_editor` 里 `update_stick` 的 → 加 toast
- `_draw_add_stick` 里 `add_stick` 的 → 加 toast
- `_draw_particle_editor` 里 `add_particle` / `update_particle` / `delete_particle` 里的错误 → 加 toast

### 迁移模式

原代码:
```python
try:
    editor_state.align_selected_particles("x")
    ui_state._bone_error = ""
except Exception as exc:
    ui_state._bone_error = str(exc)
```

改为:
```python
try:
    editor_state.align_selected_particles("x")
    ui_state._bone_error = ""
except Exception as exc:
    ui_state._bone_error = str(exc)
    ui_state.push_toast(f"对齐失败: {exc}", "error", exc_info=True)
```

注意:
- **`exc_info=True`** 让 logger 自动抓堆栈(`push_toast` 内部调 logger 时会透传)。这是在 except 块内才有效的 Python 特性。
- **toast 消息要加具体动作前缀**(如"对齐失败"、"加载失败"、"保存失败")。不要直接 `push_toast(str(exc), "error")`,用户看到"Active particle must be part of the selection"会懵,要给上下文。
- **前置条件不满足**(ValueError 这类,比如 `"Need at least 2 selected particles"`):语义上是**用户操作不合法**,toast 仍用 `"error"` level(红色),这是正确的 — 用户对它的反应是"哦我忘了先选"。
- **push_toast 对 `exc_info=True` 的支持**:上一轮 `push_toast` 签名是 `exc_info=None`,内部 `logger.error(message, exc_info=exc_info)`。传 `True` 也支持(Python logging 原生特性)。
- **重复 exception 的合并保护**:`push_toast` 已有合并逻辑,连续点同一个按钮连续失败会自动合并计数,不需要额外处理。

### Commit 3 验收

- [ ] 每个 error 赋值点都有对应的 push_toast(grep `_bone_error = str`、`_load_error = str`、`_save_error = str` 确认)
- [ ] 连续触发同一个错误 3 次,toast 合并显示 ×3,日志文件**只有一条** error 记录 + 堆栈(不是三条)
- [ ] 不同错误交替触发,每条都进 toast 栈、按时间排序
- [ ] 对话框里红字仍然显示(没被替换成 toast),dialog 关闭后红字也消失(现有行为不变)

### Commit 3 Conventional Commit message

```
feat: migrate all UI error assignments to push_toast
```

---

## ================================================================
## Commit 4: 成功点位 Toast + 镜像模式 toast
## ================================================================

### 范围

按之前拍板的筛选:**仅对用户可感知且可能失败的操作弹 success**。对齐 / undo / redo / 归一化这类视觉有反馈的,**不弹**。

### 清单

新增的 success / info toast 点位:

1. **文件加载**(已在 Commit 1 之前就有了,在 `_load_file` 和 Commit 2 的 `_handle_browse_load` 里已经加过) — 确认不要重复加
2. **文件保存**(`draw_save_dialog` OK + `_handle_browse_save`):成功后 `push_toast(f"已保存: {Path(path).name}", "success")`
3. **预设加载**:成功后 `push_toast(f"已加载预设: {name}", "success")`
4. **预设保存**:成功后 `push_toast(f"已保存预设: {name}", "success")`
5. **预设删除**:成功后 `push_toast(f"已删除预设: {name}", "success")`
6. **进入镜像模式**:成功后 `push_toast(f"进入镜像模式: {axis} 轴", "info")`
7. **退出镜像模式**:成功后 `push_toast("已退出镜像模式", "info")`

### 不加 toast 的地方(明确排除)

- 对齐 X/Y/Z(视觉反馈足够)
- undo/redo(视觉反馈足够)
- 工具模式切换(status bar 已显示)
- `set_mirror_plane_from_camera` / `normalize_mirror_plane_normal` 等镜像平面细调操作的成功(细调场景下 toast 反而打扰)
- 体素 bind/unbind/clear selection(视觉反馈足够)
- 新增/删除 stick 或 particle(面板里列表立即变化,视觉反馈足够)

### 实现位置

在现有各 try/except 的**成功分支**追加 `push_toast`。比如 `draw_save_dialog`:

```python
try:
    editor_state.save_xml(path, skeleton_sticks_ref[0])
    ui_state._save_error = ""
    ui_state.show_save_dialog = False
    imgui.close_current_popup()
    from pathlib import Path
    ui_state.push_toast(f"已保存: {Path(path).name}", "success")
except Exception as exc:
    ui_state._save_error = str(exc)
    ui_state.push_toast(f"保存失败: {exc}", "error", exc_info=True)
```

### 镜像模式 toast 的特殊点

`enter_mirror_mode` 的成功 toast 需要知道当前 axis。要么在 `editor_state.enter_mirror_mode()` 成功后读 `editor_state.mirror_axis`,要么让 `enter_mirror_mode` 返回 axis。用前者:

```python
try:
    editor_state.enter_mirror_mode()
    ui_state._bone_error = ""
    ui_state.push_toast(f"进入镜像模式: {editor_state.mirror_axis} 轴", "info")
except Exception as exc:
    ui_state._bone_error = str(exc)
    ui_state.push_toast(f"进入镜像模式失败: {exc}", "error", exc_info=True)
```

`exit_mirror_mode` 不会抛异常(看代码是直接设 flag),所以:

```python
# 按退出按钮的分支
editor_state.exit_mirror_mode()
ui_state.push_toast("已退出镜像模式", "info")
```

**但注意**:`set_tool_mode` 里切出 bone_edit 也会调 `exit_mirror_mode()`(用户切工具模式时自动退出镜像)。这种**隐式退出**要不要发 toast?

我的建议:**不发**。切工具模式是用户主动操作,本身视觉反馈足够,再多一条"已退出镜像模式"反而冗余。只有**显式点"退出镜像模式"按钮**才发 toast。

实现:在 `set_tool_mode` 里调 `exit_mirror_mode()`,不加 toast;在 `draw_bone_panel` 的"退出镜像模式"按钮 handler 里加 toast。

同理:`delete_particle` 如果删的粒子是 mirror_pair 的一员,会隐式 `exit_mirror_mode()`,这个分支也**不发**退出 toast — 因为 particle 删除本身就是个破坏性操作,用户预期会看到"镜像伙伴丢了"这种副作用,不需要额外 toast 污染。

### Commit 4 验收

- [ ] 文件保存成功弹绿色 toast
- [ ] 预设三个操作(加载/保存/删除)成功各自弹绿色 toast
- [ ] 显式点"进入镜像模式"弹蓝色 info toast,显示轴名
- [ ] 显式点"退出镜像模式"弹蓝色 info toast
- [ ] 切工具模式导致的隐式退出镜像**不弹** toast
- [ ] 删除 mirror_pair 中的粒子导致的隐式退出镜像**不弹** toast

### Commit 4 Conventional Commit message

```
feat: add success toasts for file/preset operations and mirror mode transitions
```

---

## 几个容易踩的坑

### F8 相关

1. **`_restore_snapshot` 的 visible 恢复逻辑**:原来 `_restore_snapshot` 没有 visible 处理,上一轮 `clone()` 是拷贝 visible 的,靠 snapshot→clone 间接保留可视。现在 `clone()` 不再拷贝,必须**显式**在 `_restore_snapshot` 里用 `visible_by_pair` 恢复,否则 undo/redo 后所有 stick visible 变回 True(等于清空用户的可视偏好)。这是本轮最容易漏的一个点,必测。

2. **StickEntry 非 snapshot 语境下的 clone 使用**:搜一下 `editor_state.py` 里所有 `stick.clone()` 或 `self._clone_sticks()` 的调用点。除了 snapshot,还有没有别的地方调用 clone 需要保留 visible?如果有,要么单独处理要么把改 clone 的决策再重新评估(但按我们的设计,snapshot 是唯一需要特殊处理的点,其他调用都应该接受"clone 得到默认 True")。

### F9 相关

3. **ctypes filter 字符串末尾的 double null**:`create_unicode_buffer(s, len(s))` 的第二参数长度是 **wchar 数**(含终止 `\0`),不是字节数。自己确认 s 里的 `\0` 个数。

4. **路径缓冲区太小会截断**:1024 wchar 对 Windows 路径一般够(最大 260 个字符的传统路径限制);如果用户用长路径前缀 `\\?\` 或 UNC 路径可能突破。给个 2048 更保守。本轮 1024 够用,有 bug 再说。

5. **`hwndOwner = None`(NULL)**:意味着对话框没有 owner 窗口。副作用:对话框不是 GLFW 主窗口的 modal child,可能弹在屏幕别处而不是主窗口中央。本轮接受,将来 F9++ 可以拿 `glfw.get_win32_window(window)` 作为 owner。

6. **对话框冻结期间 `time.time()` 不变?** 错,它是实时时钟,**会变**。冻结的只是 Python 解释器(对话框在同一线程内弹出,Python 代码暂停执行,但 time 继续走)。所以"补救 toast 过期"的 dt 计算才有意义。

### Toast 迁移相关

7. **`push_toast` 合并保护的粒度**:合并判定是**栈顶**一条。如果连续发两条不同 error 再发第一条那条,不会合并(栈顶是第二条)。这是正确语义,不要改成"遍历整个栈找匹配"。

8. **exc_info=True 的传播**:`push_toast(..., exc_info=True)` → 内部 `logger.error(message, exc_info=True)` → logger 读 `sys.exc_info()`。如果 push_toast 不是在 except 块内被调用,`sys.exc_info()` 返回 `(None, None, None)`,logger 不写堆栈。所以 **push_toast 必须在 except 块内调用**才能带堆栈。这已经是所有迁移点位的自然情况,但 prompt 后续如果有人往 except 块外加 push_toast 要注意。

---

## 编码风格

- 跟随项目现有风格(4 空格缩进、中文注释 OK、snake_case)
- `file_dialogs.py` 不引入新依赖 — 只用 `ctypes`、`ctypes.wintypes`、`sys`、`logging`、`typing`
- 不改 `rwrsb_gui.spec`
- i18n 新 key 放在 `_TEXT` 字典的 en / zh 两个分支里,位置合适即可

---

## 交付方式

**4 次独立 commit**,顺序和 message 如上标注。每完成一个 commit:

1. 自己跑一遍对应的验收清单
2. 在消息里总结:改了哪些文件、哪些验收项通过 ✔、没测的项目说明原因、任何偏离本文档的决策

**开工顺序建议**:Commit 1(F8) → Commit 2(F9) → Commit 3(error 迁移) → Commit 4(success 迁移)。F8 最独立;F9 中等复杂度但独立模块;Commit 3/4 是分散扫尾,放最后心智负担最小。

**不确定的决策务必先问 SAIWA**,不要猜着做。特别是:
- F8 的 `_restore_snapshot` 恢复逻辑如果发现与现有代码冲突(比如现有 `_restore_snapshot` 有额外字段处理)
- F9 的 ctypes 定义如果在 pyimgui 或 GLFW 版本下有异常
- Toast 迁移时发现有我没列到清单里但有 `_*_error = str(exc)` 的点位(可能是我漏了),也要加,并在交付时报告
