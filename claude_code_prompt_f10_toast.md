# 任务:rwrsb_gui 增加日志系统 + Toast 通知面板 (F10 + Toast)

## 项目背景

rwrsb_gui 是 RWR 风格体素骨架绑定编辑器,技术栈 Python 3.10+ / pyimgui / ModernGL / GLFW / numpy,目标平台 Windows。发布形态是 PyInstaller 打包的目录版 exe (`console=False`)。

当前项目已完成 F1-F7 (粒子多选、框选、整体平移、对齐、镜像模式、反面视图),本轮只做两件事:

1. **F10 日志系统**:新建 `logger_setup.py`,提供 Python 标准 logging,支持文件轮转,捕获未处理异常,供 exe 用户排查崩溃用。
2. **Toast 通知面板**:视口左上角的浮层消息栏,给用户即时操作反馈。

F8 (骨段可视一键切换) 和 F9 (ctypes 文件对话框) 不在本轮,下轮做。

---

## 开工前必读

在写任何代码之前,先读完下面这些文件,建立准确认知:

- `main.py` — 主入口、GLFW 回调、主循环、`_load_file`
- `ui_panels.py` — UIState、所有面板、对话框、`draw_box_select_overlay`
- `editor_state.py` — EditorState、所有 print 点
- `xml_io.py` — 解析和写出,可能有 print 点
- `rwrsb_gui.spec` — PyInstaller 配置,看 `console=False`
- `README.md` / `RELEASE.md` — 了解项目发布流程

重点确认:

- 当前代码里所有 `print(...)` 的位置和内容,准备迁移到 logger
- `UIState.__init__` 的字段列表,准备追加 toast 相关字段
- `main.py` 里 `##overlay` 窗口的构造方式,toast 要复用它的 draw list
- 现有 `_load_error` / `_save_error` / `_bone_error` 三个字段的发送点(本轮不动这些,只做基础设施)

---

## 交付物清单

### 新建

- `logger_setup.py` — 日志初始化模块

### 修改

- `main.py` — 最顶部调用 logger 初始化;主循环用 try/except 包裹;GLFW 回调加异常捕获;替换 `print` 为 logger 调用;在 `##overlay` 窗口里调用 `draw_toasts`
- `ui_panels.py` — 新增 `Toast` 类、`UIState.push_toast()` 方法、`draw_toasts()` 渲染函数;`UIState.__init__` 加 toast 字段;本文件所有相关 print 迁移(如果有)
- `editor_state.py` — 所有 print 迁移为 logger
- `xml_io.py` — 所有 print 迁移为 logger (如果有的话)

### 不新建 commit、不动

- 现有的 `_load_error` / `_save_error` / `_bone_error` 字段和赋值点 — 本轮保持原样
- `draw_load_dialog` / `draw_save_dialog` 的 OK 分支 — 本轮不加 toast,下轮做
- F8 / F9 所有相关文件

---

## F10 日志系统详细规格

### 新文件 `logger_setup.py`

核心 API:

```python
def init_logger() -> Path:
    """
    初始化 root logger。返回实际使用的日志目录(供 UI 展示)。
    在 main.py 任何其他 import 之前调用。
    """
```

实现要求:

1. **日志目录选择 + 降级**:
   - 打包后 (`sys.frozen == True`):首选 `Path(sys.executable).parent / "logs"`
   - 源码运行:首选 `Path(__file__).parent / "logs"`
   - **写权限测试**:`mkdir` 成功后 `touch` 一个测试文件,能写就用,不能写(如装到 `C:\Program Files\`)就退化到 `Path(os.environ.get("LOCALAPPDATA", Path.home())) / "rwrsb_gui" / "logs"`
   - 降级路径也失败时最终退化到 `Path(tempfile.gettempdir()) / "rwrsb_gui" / "logs"`,不抛异常(日志系统本身不能把程序搞崩)

2. **RotatingFileHandler**:
   - 文件名 `rwrsb.log`
   - `maxBytes=5_000_000` (5MB)
   - `backupCount=5` (保留 5 个历史文件,总共 30MB 上限)
   - `encoding="utf-8"`

3. **格式**:
   ```
   %(asctime)s [%(levelname)s] %(name)s: %(message)s
   ```
   日期格式 `%Y-%m-%d %H:%M:%S`

4. **级别**:root logger 默认 `INFO`;提供一个简单的方式让将来可以改 DEBUG(暂时不搞命令行参数,环境变量 `RWRSB_LOG_LEVEL=DEBUG` 识别即可,没设就 INFO)

5. **StreamHandler**:同时加一个输出到 `sys.stderr` 的 handler(开发时跑源码能看到)。打包后 `console=False` 这个 handler 会被吞掉但不影响文件输出。

6. **sys.excepthook**:设置为 `logging.exception("Uncaught exception", exc_info=...)` 风格,保证主线程未捕获异常能落盘。
   
   **重要**:`excepthook` 对 GLFW 回调里的异常不生效(glfw C 层会吞)。这部分靠 main.py 每个回调里自己 try/except(见下文)。

7. **启动日志**:初始化完后立刻写一条 `logger.info("rwrsb_gui started, log dir: %s", log_dir)`,方便排查时确认 log 系统起来了。

### main.py 改动

1. **最顶部**(`import sys / os` 之后、其他项目模块 import 之前)调用:
   ```python
   from logger_setup import init_logger
   _LOG_DIR = init_logger()
   ```
   然后再 import `camera`/`editor_state`/`ui_panels` 等。

2. **所有 `print` 替换为 logger**:
   - `print(f"[ui] loaded font: {font_path}")` → `logger.info("loaded font: %s", font_path)`
   - `print("[ui] using default imgui font")` → `logger.warning("using default imgui font (no CJK font found)")`
   - `print(f'[diag] voxel count = {len(g_editor.voxels)}')` 等所有 `[diag]` → `logger.debug(...)`(诊断信息降级到 DEBUG,默认看不到,避免刷屏)
   - `print(f'[load] failed: {e}')` + `traceback.print_exc()` → `logger.exception("load file failed: %s", path)` (logger.exception 自动带堆栈,不需要 traceback)
   - 文件顶部加 `logger = logging.getLogger(__name__)`

3. **GLFW 回调异常捕获**:给每个 glfw 回调 (`on_mouse_button`、`on_cursor_pos`、`on_scroll`、`on_key`、`on_char`、`on_drop`、`on_resize`) 套一层装饰器或手工 try/except。推荐用装饰器简化:
   ```python
   def _safe_callback(fn):
       @functools.wraps(fn)
       def wrapper(*args, **kwargs):
           try:
               return fn(*args, **kwargs)
           except Exception:
               logger.exception("GLFW callback %s failed", fn.__name__)
       return wrapper
   ```
   然后 `@_safe_callback` 装饰所有 on_xxx 函数。**例外**:imgui 自己的 mouse/keyboard/char/scroll callback 先调用的那几行不要吞,只吞业务逻辑的异常 — 如果 imgui 回调自身失败,让它崩出来(那是框架 bug)。最简单的做法是装饰器捕获后 `logger.exception` 然后 return,不 re-raise。

4. **主循环异常捕获**:`while not glfw.window_should_close(window):` 循环体**整体**套一层 try/except,每帧失败 logger.exception 但不退出(避免一个偶发异常就把整个程序干掉)。但如果**同一异常连续 N 帧(N=30)发生**,考虑退出(防止无限刷屏);实现可以加个帧计数器,见后面"健壮性"段。

5. `main()` 函数外再套一层最外层 try/except,兜底 GLFW init 失败这种启动期异常。

---

## Toast 通知面板详细规格

### 数据结构 (放在 `ui_panels.py`)

```python
@dataclass
class Toast:
    message: str
    level: str         # "success" | "info" | "error"
    created_at: float  # time.time(),用于合并时显示"x秒前"(可选);也用于排序
    expires_at: float  # 绝对时间,hover 暂停时需要延长这个值
    count: int = 1     # 合并计数
    fade_start: float = 0.0  # expires_at - 0.5,alpha 开始衰减的时刻
    _is_hovered: bool = False  # 上一帧是否 hover 中,用于暂停 TTL
```

### `UIState` 新增字段

```python
self.toasts: list[Toast] = []
self._toast_last_update = 0.0  # 上一帧时间戳,用于算 delta
```

### `UIState.push_toast()` 方法

```python
def push_toast(self, message: str, level: str = "info",
               also_log: bool = True, exc_info=None) -> None:
    """
    推送一条 toast 到左上角浮层。

    合并逻辑:如果栈顶(最新那条,即列表第一条)的 message 和 level 完全相同,
    计数+1,重置 TTL,并且**不再次写 log**(避免循环操作刷爆日志)。

    level 映射到 Python logging 级别:
        success -> INFO
        info    -> INFO
        error   -> ERROR
    """
```

实现要求:

1. **合并判定**:`len(self.toasts) > 0 and self.toasts[0].message == message and self.toasts[0].level == level` → 合并(计数+1,刷新 TTL,不写 log)

2. **TTL 分级**(按"完整显示+淡出"秒数):
   - `success`: 3.0 + 0.5 = 3.5 秒
   - `info`: 3.0 + 0.5 = 3.5 秒
   - `error`: 5.5 + 0.5 = 6.0 秒
   在常量里定义,别散在代码里

3. **硬顶上限 6 条**:push 后如果 `len(self.toasts) > 6`,**移除最老的**(列表末尾,因为新的插在头部)

4. **合并时不写 log**;其他情况都按 `also_log=True` 写(级别映射:success/info → `logger.info(...)`,error → `logger.error(...)`,`exc_info` 透传给 logger)

5. **非合并的新 push**:`insert(0, toast)`(新的在最前)

### `draw_toasts(ui_state, WIN_W, toolbar_h, ui_scale, draw_list)` 函数

在 `main.py` 主循环里,`##overlay` 窗口内、`draw_box_select_overlay` 之后调用。签名里 `draw_list` 是 `imgui.get_window_draw_list()` 得到的对象。

渲染要求:

1. **位置**:起点 `(8 * ui_scale, toolbar_h + 8)` — toolbar 下方、视口内左上角,留 8px padding (ui_scale 缩放 padding 的 X 不缩放 Y,因为 toolbar_h 已经缩放过了,toast 的 8px 垂直间距跟随 ui_scale 即可)

2. **每条 toast 尺寸**:
   - 宽度固定 `320 * ui_scale`
   - 高度 = 文本行高 + 上下 padding(8px 上下 padding,ui_scale 缩放)
   - 文本自动换行:用 `imgui.push_text_wrap_pos(text_x + text_width)`,或手算换行 — **简单点**,如果超长就截断加省略号,`max_chars = 48` 字符,超了 `msg[:47] + "…"`
   - **有 count >= 2 时消息后缀加 ` ×N`**

3. **背景颜色**(带透明度,80% 基础透明度):
   - success: `(0.15, 0.55, 0.20, 0.85 * alpha)` — 深绿
   - info:    `(0.20, 0.40, 0.65, 0.85 * alpha)` — 深蓝
   - error:   `(0.65, 0.20, 0.20, 0.85 * alpha)` — 深红
   - 文字颜色统一 `(1, 1, 1, alpha)` 白色

4. **圆角矩形**:用 `draw_list.add_rect_filled(x, y, x+w, y+h, color, rounding=4.0)`,`add_text` 画文本

5. **逐帧时间推进**:
   ```python
   now = time.time()
   for toast in ui_state.toasts:
       if toast._is_hovered:
           # hover 时整条往后推迟:expires_at 和 fade_start 加上本帧 dt
           dt = now - ui_state._toast_last_update
           toast.expires_at += dt
           toast.fade_start += dt
   ui_state._toast_last_update = now
   ui_state.toasts = [t for t in ui_state.toasts if t.expires_at > now]
   ```

6. **Alpha 淡出**:
   ```python
   if now < toast.fade_start:
       alpha = 1.0
   else:
       alpha = max(0.0, (toast.expires_at - now) / 0.5)
   ```

7. **Hover 检测**:每帧画完一条后,用 `imgui.is_mouse_hovering_rect(x, y, x+w, y+h)` 判断(因为 overlay 窗口设了 `WINDOW_NO_INPUTS`,不能用 is_item_hovered,要用 mouse_hovering_rect)。把结果存到 `toast._is_hovered`,下一帧用

8. **堆叠布局**:
   - 新消息在最前(index 0),在最上面
   - 每条之间垂直间距 4px(ui_scale 缩放)
   - 从上到下按列表顺序画

### `main.py` 里如何挂

在现有的 `##overlay` window 内:

```python
imgui.begin("##overlay", flags=(imgui.WINDOW_NO_TITLE_BAR | ... | imgui.WINDOW_NO_INPUTS))
draw_box_select_overlay(g_ui)
draw_list = imgui.get_window_draw_list()
_, toolbar_h, _ = _ui_layout_metrics()
draw_toasts(g_ui, WIN_W, toolbar_h, g_ui.ui_scale, draw_list)
imgui.end()
```

### 本轮唯一的 push_toast 接入点

为了验证系统工作,在 `_load_file` 里:
- try 块成功结尾处加 `g_ui.push_toast(f"已加载: {Path(path).name}", "success")`
- except 块里加 `g_ui.push_toast(f"加载失败: {e}", "error", exc_info=sys.exc_info())`

其余业务代码的 toast 接入点**本轮不做**,下轮 F8/F9 时一起搞。

---

## 验收清单

开发完后自己跑过一遍:

### F10 日志

- [ ] 源码运行 `python main.py`,`./logs/rwrsb.log` 生成,里面有 `started, log dir:` 一行
- [ ] 让 logs/ 目录的写权限被拒(例如 Windows 上 chmod 或 linux 下 `chmod 000`),程序**不崩**,退化到 LOCALAPPDATA/临时目录
- [ ] 在 `main()` 里人为插 `raise RuntimeError("test uncaught")`,日志里有完整堆栈
- [ ] 在 `on_mouse_button` 里人为插 `raise RuntimeError("test callback")`,日志里有 `GLFW callback on_mouse_button failed` 和堆栈,程序**继续运行**
- [ ] 传一个损坏的 XML (比如故意改坏根节点标签),UI 弹 error toast + log 有 exception 堆栈 + 程序不崩
- [ ] 日志文件写到 5MB,自动轮转,`rwrsb.log.1` 出现,最多保留 5 个备份
- [ ] 环境变量 `RWRSB_LOG_LEVEL=DEBUG` 设上,重启,`[diag]` 那些信息可见

### Toast

- [ ] 触发一次加载,左上角出现绿色"已加载: xxx",3.5 秒后淡出
- [ ] 触发加载失败,红色"加载失败: xxx",6 秒后淡出
- [ ] 连续触发 3 次同一错误,显示一条"xxx ×3"
- [ ] 连续触发 10 条不同错误,最多同时显示 6 条,最老的被挤掉
- [ ] hover 任一 toast,该条不淡出;移开继续计时
- [ ] ui_scale 拉到 1.5 或 0.8,toast 尺寸和字体跟着缩放
- [ ] toast 半透明,能看到底下的 3D 场景
- [ ] toast 不拦截鼠标点击 — 在 toast 位置点击能穿透选到 particle/voxel
- [ ] 合并触发时,日志文件里只有第一次的 log,后续合并不写日志

---

## 几个容易踩的坑

1. **imgui.get_window_draw_list() 的坐标系**:是窗口局部坐标还是屏幕绝对坐标?——是**屏幕绝对坐标**。`##overlay` 窗口位置是 (0,0),所以直接用 toolbar_h 等绝对像素值即可。

2. **`imgui.is_mouse_hovering_rect` 在 `WINDOW_NO_INPUTS` 窗口里是否生效**:是的,它查的是 imgui 的 mouse pos 而不是依赖窗口 focus;但如果不放心可以直接比较 `imgui.get_io().mouse_pos` 和矩形。

3. **HiDPI**:`imgui.get_window_draw_list()` 用的是 imgui 逻辑坐标,不是 framebuffer 像素。所以 `toolbar_h` 这种值直接用就好,别乘 scale_x/scale_y。

4. **`logger.exception` 必须在 except 块内**才能自动抓堆栈,否则 `exc_info` 为 None 只会打消息。如果在 except 外想抓,手动传 `exc_info=sys.exc_info()` 或 `exc_info=True`。

5. **`RotatingFileHandler` 在 Windows 上的坑**:轮转时会尝试 rename 正在被其他 handler 打开的文件,极偶发报错。如果遇到,考虑 `delay=True` 或者 `TimedRotatingFileHandler`,但不要一上来就换,先用 `RotatingFileHandler(..., delay=True)` 测。

6. **循环内 `logger.exception` 泛滥**:主循环里如果同一异常每帧触发,日志瞬间 5MB 爆。加个保护:记住上一帧的异常类型+消息,相同则只记 count,不同了 flush 一条 `"previous error repeated N times"`。简单实现:

   ```python
   _last_loop_err = (None, None, 0)  # (type_name, msg, count)
   while not glfw.window_should_close(window):
       try:
           ...
           _last_loop_err = (None, None, 0) if _last_loop_err[2] == 0 else _last_loop_err
           # 上面这行是"正常帧"时,如果之前有累积错误,flush 一条总结
           if _last_loop_err[2] > 0:
               logger.error("previous error '%s: %s' repeated %d times",
                            _last_loop_err[0], _last_loop_err[1], _last_loop_err[2])
               _last_loop_err = (None, None, 0)
       except Exception as e:
           typ, msg = type(e).__name__, str(e)
           if _last_loop_err[0] == typ and _last_loop_err[1] == msg:
               _last_loop_err = (typ, msg, _last_loop_err[2] + 1)
               # 累计中,不写 log
           else:
               # 新错误或换错误
               if _last_loop_err[2] > 0:
                   logger.error("previous error ... repeated %d times", _last_loop_err[2])
               logger.exception("main loop error")
               _last_loop_err = (typ, msg, 0)  # 第一次写了,计数清零
   ```

   如果嫌复杂,**最简实现**:加一个 `_frame_err_count`,同一帧错误 `logger.exception` 只调前 3 次,之后静默;每成功一帧重置。勉强够用。
   **你自己判断取哪种。保守起见选简单的,别把防抖逻辑写复杂导致它自己 bug。**

---

## 编码风格

- 跟随项目现有风格(4 空格缩进、中文注释 OK、`snake_case`)
- 不引入新依赖 — 只用标准库 `logging`、`logging.handlers`、`time`、`dataclasses`、`pathlib`、`tempfile`、`os`、`sys`、`functools`
- 不改 `rwrsb_gui.spec` — logger_setup 用到的都是标准库,PyInstaller 自动打包

---

## 交付方式

1. 做完自己跑一遍上面的验收清单
2. 按 Conventional Commits 分 2 次提交:
   - `feat: add logger_setup module with rotating file handler and uncaught exception hook`
   - `feat: add toast notification overlay with merge/fade/hover-pause`
3. 如果有任何你不确定的决策(上面没覆盖的边界情况),**先问再写**,不要猜着做
4. 完成后给 SAIWA 发一条总结,包含:
   - 改了哪些文件
   - 每个验收项是否通过(通过的打 ✔,没测的说明原因)
   - 任何偏离本文档的决策(如果有)
   - 建议下轮 F8/F9 接入 toast 的点位清单(就是现在 `_bone_error` / `_load_error` / `_save_error` 赋值的那些位置,下轮每个点位要加对应的 `push_toast`)
