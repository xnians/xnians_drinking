# 开源参考与许可证核查

> 本文件对应大赛"学术诚信与 AI 使用规范"中「资料来源和授权情况清楚」一项。
> 原则：**能复用就复用，但要查许可证、标注出处、说清改了什么**；许可证不兼容的一律不用。

核查时间：2026-11-24（2026-11-24 补充：日历控件改为自绘、新增读图自检图）

## 一、已采纳

| 来源 | 许可证 | 用了什么 | 改动程度 | 位置 |
| --- | --- | --- | --- | --- |
| [bmjcode/tkScrolledFrame](https://github.com/bmjcode/tkScrolledFrame) | **MIT** | 滚轮事件绑定方式（逐个控件绑定而非 `bind_all`）+ 按平台处理 `MouseWheel`/`Button-4`/`Button-5` 的 delta + `scrollregion` 用 `winfo_reqwidth/reqheight` 更新 | 改写：约 15 行，重写为 `App._bind_wheel()` 与 `App._on_wheel()`，未引入其类结构 | `app.py` 顶部注释已标注 |

## 二、看过但未采纳

| 来源 | 许可证 | 为什么没用 |
| --- | --- | --- |
| [TomSchimansky/CustomTkinter](https://github.com/TomSchimansky/CustomTkinter) ★13.6k | MIT | 圆角卡片、主题化确实更好看，但要 `pip install`。本项目的卖点是"评委拿到文件夹双击就能跑"，为了美观牺牲零依赖不划算。列为 PPT 里"后续可选升级" |
| [Akascape/CTkXYFrame](https://github.com/Akascape/CTkXYFrame) | MIT | 滚动容器实现思路与上面那条同源，但依赖 CustomTkinter，同上 |
| [Waqas-Khan-CodeCanvas/toastify-ctk](https://github.com/Waqas-Khan-CodeCanvas/toastify-ctk) | MIT | 提示条依赖 CustomTkinter，无法在纯 tkinter 里直接用 |
| [j4321/tkcalendar](https://github.com/j4321/tkcalendar) | **GPL-3.0** | 日历选择器质量不错，但 **GPL 有传染性**：链接进项目就等于整个项目必须 GPL 开源。放弃，改为**自绘月历** `datepicker.py`（见第三节）。`rules.parse_dt` 保留给数据兜底与旧数据兼容，不再作为主要录入方式 |
| [sumqwerty/tkinter-scrollable-frames](https://github.com/sumqwerty/tkinter-scrollable-frames) | **GPL-3.0** | 同上，许可证问题，未参考其代码 |

## 三、自己写、没有可复用实现的部分

| 模块 | 说明 |
| --- | --- |
| `rules.py` 全部分区与排序逻辑 | 没有找到把"无截止时间置顶 + 过期原位标红 + 不急独立区"这套规则写成纯函数的现成实现，按本项目需求自己写，18 个单测覆盖 |
| `CheckCircle` 打勾动画 | tkinter 没有现成的圆勾动画组件（搜到的基本都基于 CustomTkinter 或 PyQt）。用 Canvas 手绘：填充 120ms + 对勾 5 帧描线 |
| `parser.py` 的提示词与 JSON 校验 | 通用 OCR 库（PaddleOCR/Tesseract）产出的是文字行不是结构化日程，仍需二次解析；直接用多模态模型 + 严格 JSON 约束更短 |
| `datepicker.py` 日历选择控件 | 现成方案只有 tkcalendar（GPL）。自己画：`calendar.Calendar(firstweekday=0)` 取月历矩阵 + 7×6 按钮网格 + `ttk.Spinbox` 选时分 + `overrideredirect` 浮层（`-topmost` + `grab_set` + 点击浮层外部关闭）。约 380 行，零依赖 |
| 读图自检小图（`parser._PROBE_PNG`） | 96×56、1-bit、292 字节的 PNG，白底黑字 `42`，用 Pillow 一次性生成后以 base64 内嵌进代码（不再需要 Pillow 运行时）。作用是区分"接口通了"与"模型会看图" |

## 四、结论

- 本项目除 **Pillow（可选，用于图片压缩）** 外无第三方运行时依赖；
- 已采纳的代码仅一处，MIT 协议，来源与改动已写在源码注释里；
- GPL 组件明确排除，避免整个项目被动开源；
- 所有图标/字体均使用系统自带，无外部素材授权问题。
