# -*- coding: utf-8 -*-
"""
app.py —— 日程表主程序（tkinter，无第三方 UI 依赖）

界面结构（对应策划案 4.2 / 5.6）：

    ┌ 顶栏：+ 新增 ｜ 上传图片 ｜ 设置
    ├ 警示条：N 项未设截止时间（0 项时隐藏）
    ├ 待设时间区（橙底置顶）
    ├ 时间线：已过期 / 今天 / 明天 / 本周内 / 更晚
    ├ 不急区（默认折叠）
    └ 已完成区（默认折叠）

所有分区判定都来自 rules.py，这个文件只负责"画出来 + 接事件"。
"""

from __future__ import annotations

import threading
import tkinter as tk
from datetime import datetime, timedelta
from tkinter import filedialog, messagebox, ttk
from typing import Any, Callable, Dict, List, Optional

import parser as ai_parser
import datepicker
import rules
import store

APP_NAME = "日程表"
VERSION = "0.1.0"

# ---- 配色 ----
BG = "#f4f5f7"
CARD = "#ffffff"
CARD_NODUE = "#fffaf2"
CARD_EXPIRED = "#fff5f5"
CARD_IDLE = "#f8fafc"
TEXT = "#1f2328"
MUTED = "#7d8590"
ORANGE = "#d97706"
ORANGE_DARK = "#7c2d12"
RED = "#dc2626"
GREEN = "#2f7d5d"
SLATE = "#94a3b8"
LINE = "#e5e7eb"

FONT = "Microsoft YaHei UI"
F_TITLE = (FONT, 11)
F_TITLE_DONE = (FONT, 11, "overstrike")
F_META = (FONT, 9)
F_SECTION = (FONT, 10, "bold")
F_BTN = (FONT, 9)
F_H1 = (FONT, 15, "bold")


def _set_dpi_aware() -> None:
    """高分屏下别糊。失败就算了，不影响功能。"""
    try:
        import ctypes

        ctypes.windll.shcore.SetProcessDpiAwareness(1)
    except Exception:
        pass


# --------------------------------------------------------------------------
# 打勾圆圈：Canvas 手绘，120ms 填充 + 5 帧描出对勾
# --------------------------------------------------------------------------
class CheckCircle(tk.Canvas):
    SIZE = 22

    def __init__(self, master: tk.Misc, on_click: Callable[[], None],
                 color: str = GREEN, bg: str = CARD, checked: bool = False):
        super().__init__(master, width=self.SIZE, height=self.SIZE, bg=bg,
                         highlightthickness=0, bd=0)
        self._on_click = on_click
        self._color = color
        self._busy = False
        self._line: Optional[int] = None
        self._oval = self.create_oval(3, 3, self.SIZE - 3, self.SIZE - 3,
                                      outline="#c9ced6", width=2)
        if checked:
            self.itemconfig(self._oval, outline=color, fill=color)
            self.create_line(*self._pts(0), *self._pts(1), *self._pts(2),
                             fill="#ffffff", width=2.4, capstyle="round",
                             joinstyle="round")
        else:
            self.bind("<Button-1>", self._click)
            self.bind("<Enter>", lambda e: self.itemconfig(self._oval, outline=color))
            self.bind("<Leave>", lambda e: self._busy or self.itemconfig(self._oval, outline="#c9ced6"))
        self.configure(cursor="hand2" if not checked else "arrow")

    def _pts(self, i: int) -> tuple:
        k = self.SIZE / 22.0
        pts = ((6.5, 11.5), (9.8, 14.8), (15.8, 7.4))
        return (pts[i][0] * k, pts[i][1] * k)

    def _point_at(self, t: float) -> tuple:
        p0, p1, p2 = self._pts(0), self._pts(1), self._pts(2)
        l1 = ((p1[0] - p0[0]) ** 2 + (p1[1] - p0[1]) ** 2) ** 0.5
        l2 = ((p2[0] - p1[0]) ** 2 + (p2[1] - p1[1]) ** 2) ** 0.5
        d = t * (l1 + l2)
        if d <= l1:
            r = d / l1 if l1 else 0
            return (p0[0] + (p1[0] - p0[0]) * r, p0[1] + (p1[1] - p0[1]) * r)
        r = (d - l1) / l2 if l2 else 0
        return (p1[0] + (p2[0] - p1[0]) * r, p1[1] + (p2[1] - p1[1]) * r)

    def _click(self, _event=None) -> None:
        if self._busy:
            return
        self._busy = True
        self.configure(cursor="arrow")
        self.itemconfig(self._oval, outline=self._color, fill=self._color)
        self.after(60, lambda: self._step(0.0))

    def _step(self, t: float) -> None:
        if not self.winfo_exists():
            return
        x, y = self._point_at(t)
        if self._line is not None:
            self.delete(self._line)
        self._line = self.create_line(*self._pts(0), x, y, fill="#ffffff",
                                      width=2.4, capstyle="round", joinstyle="round")
        if t < 1.0:
            self.after(30, lambda: self._step(min(1.0, t + 0.22)))
        else:
            self.after(140, self._finish)

    def _finish(self) -> None:
        if self.winfo_exists():
            self._on_click()


# --------------------------------------------------------------------------
# 新增 / 编辑对话框
# --------------------------------------------------------------------------
class ItemDialog(tk.Toplevel):
    def __init__(self, master: tk.Misc, item: Optional[Dict[str, Any]] = None):
        super().__init__(master)
        self.result: Optional[Dict[str, Any]] = None
        self._item = dict(item or {})
        self.title("编辑日程" if item else "新增日程")
        self.configure(bg=CARD, padx=18, pady=14)
        self.resizable(False, False)
        self.transient(master)

        self.v_title = tk.StringVar(value=self._item.get("title", ""))
        self.v_hint = tk.StringVar(value=self._item.get("due_hint") or "")
        self.v_notes = tk.StringVar(value=self._item.get("notes", ""))
        self.v_someday = tk.BooleanVar(value=self._item.get("status") == rules.STATUS_SOMEDAY)
        # 新增时不预先勾"不设时间"：默认就能点日历，选不选由人决定；
        # 编辑已有条目则跟随它当前有没有截止时间。
        self.v_nodue = tk.BooleanVar(value=bool(item) and not self._item.get("due"))

        self._row_label("标题")
        e = tk.Entry(self, textvariable=self.v_title, font=F_TITLE, width=34,
                     relief="solid", bd=1)
        e.pack(fill="x", pady=(0, 8))
        e.focus_set()

        self._row_label("截止时间")
        line = tk.Frame(self, bg=CARD)
        line.pack(fill="x")
        self.f_due = datepicker.DueField(line, value=rules.parse_dt(self._item.get("due")))
        self.f_due.pack(side="left")
        tk.Checkbutton(line, text="不设时间", variable=self.v_nodue, font=F_META,
                       bg=CARD, activebackground=CARD, command=self._toggle_due
                       ).pack(side="left", padx=8)
        tk.Label(self, text="点一下选日期和时间；不选也能存，之后进「待设时间」区置顶提醒",
                 font=F_META, fg=MUTED, bg=CARD, wraplength=430, justify="left"
                 ).pack(anchor="w", pady=(3, 8))

        if self._item.get("due_hint"):
            self._row_label("图上原文")
            tk.Entry(self, textvariable=self.v_hint, font=F_META, width=34,
                     relief="solid", bd=1, fg=MUTED).pack(fill="x", pady=(0, 8))

        self._row_label("备注")
        tk.Entry(self, textvariable=self.v_notes, font=F_TITLE, width=34,
                 relief="solid", bd=1).pack(fill="x", pady=(0, 10))

        tk.Checkbutton(self, text="标记为「不急」（移入不急区，不参与时间排序）",
                       variable=self.v_someday, font=F_META, bg=CARD,
                       activebackground=CARD).pack(anchor="w", pady=(0, 12))

        btns = tk.Frame(self, bg=CARD)
        btns.pack(fill="x")
        tk.Button(btns, text="保存", font=F_TITLE, bg=GREEN, fg="white",
                  activebackground="#256b50", activeforeground="white",
                  relief="flat", padx=18, pady=6, cursor="hand2",
                  command=self._save).pack(side="right")
        tk.Button(btns, text="取消", font=F_TITLE, bg="#e5e7eb", fg=TEXT,
                  relief="flat", padx=16, pady=6, cursor="hand2",
                  command=self.destroy).pack(side="right", padx=8)

        self._toggle_due()
        self.bind("<Return>", lambda e: self._save())
        self.bind("<Escape>", lambda e: self.destroy())
        self._center()

    def _row_label(self, text: str) -> None:
        tk.Label(self, text=text, font=F_META, fg=MUTED, bg=CARD).pack(anchor="w", pady=(4, 2))

    def _toggle_due(self) -> None:
        self.f_due.set_enabled(not self.v_nodue.get())

    def _center(self) -> None:
        self.update_idletasks()
        w, h = self.winfo_width(), self.winfo_height()
        x = (self.winfo_screenwidth() - w) // 2
        y = (self.winfo_screenheight() - h) // 3
        self.geometry("+{}+{}".format(x, y))

    def _save(self) -> None:
        title = self.v_title.get().strip()
        if not title:
            messagebox.showwarning("还差一点", "标题不能为空。", parent=self)
            return
        due = None if self.v_nodue.get() else self.f_due.get()
        self.result = {
            "title": title,
            "due": rules.to_iso(due),
            "due_hint": self.v_hint.get().strip() or None,
            "notes": self.v_notes.get().strip(),
            "someday": bool(self.v_someday.get()),
        }
        self.destroy()


# --------------------------------------------------------------------------
# 设置对话框：AI 接口人工输入（策划案 5.7）
# --------------------------------------------------------------------------
class SettingsDialog(tk.Toplevel):
    def __init__(self, master: "App"):
        super().__init__(master)
        self.app = master
        self.title("设置")
        self.configure(bg=CARD, padx=18, pady=14)
        self.resizable(False, False)
        self.transient(master)

        cfg = master.data["ai"]
        self.v_base = tk.StringVar(value=cfg.get("base_url", ""))
        self.v_model = tk.StringVar(value=cfg.get("model", ""))
        self.v_key = tk.StringVar(value=cfg.get("api_key", ""))
        self.v_show = tk.BooleanVar(value=False)

        tk.Label(self, text="AI 接口", font=F_H1, bg=CARD, fg=TEXT).pack(anchor="w")
        tk.Label(self, text="接口信息只存在本地 data.json，不写进代码。兼容 OpenAI Chat Completions 协议的都能用。",
                 font=F_META, fg=MUTED, bg=CARD, wraplength=430, justify="left"
                 ).pack(anchor="w", pady=(2, 10))

        self._field("接口地址 Base URL", self.v_base, 46,
                    "例：https://dashscope.aliyuncs.com/compatible-mode/v1")
        self._field("模型名", self.v_model, 46,
                    "必须是能看图的模型：qwen3-vl-plus ／ qwen-vl-max ／ glm-4.6v ／ doubao-vision。\n"
                    "纯文本模型（deepseek-chat、qwen-plus 等）收到图片会直接忽略，识别结果恒为空。")

        tk.Label(self, text="API Key", font=F_META, fg=MUTED, bg=CARD).pack(anchor="w", pady=(6, 2))
        keyline = tk.Frame(self, bg=CARD)
        keyline.pack(fill="x")
        self.e_key = tk.Entry(keyline, textvariable=self.v_key, font=F_TITLE, width=36,
                              relief="solid", bd=1, show="*")
        self.e_key.pack(side="left", fill="x", expand=True)
        tk.Checkbutton(keyline, text="显示", variable=self.v_show, font=F_META, bg=CARD,
                       activebackground=CARD, command=self._toggle_key).pack(side="left", padx=6)

        status = tk.Frame(self, bg=CARD)
        status.pack(fill="x", pady=(10, 12))
        self.lb_status = tk.Label(status, text="● 未测试", font=F_META, fg=MUTED, bg=CARD,
                                  wraplength=300, justify="left", anchor="w")
        self.lb_status.pack(side="left", fill="x", expand=True)
        self.btn_test = tk.Button(status, text="测试连接", font=F_BTN, bg="#eef2f7", fg=TEXT,
                                  relief="flat", padx=12, pady=4, cursor="hand2",
                                  command=self._test)
        self.btn_test.pack(side="right")

        btns = tk.Frame(self, bg=CARD)
        btns.pack(fill="x")
        tk.Button(btns, text="保存", font=F_TITLE, bg=GREEN, fg="white", relief="flat",
                  padx=18, pady=6, cursor="hand2", command=self._save).pack(side="right")
        tk.Button(btns, text="取消", font=F_TITLE, bg="#e5e7eb", fg=TEXT, relief="flat",
                  padx=16, pady=6, cursor="hand2", command=self.destroy).pack(side="right", padx=8)

        self.bind("<Escape>", lambda e: self.destroy())
        self.update_idletasks()
        x = master.winfo_rootx() + 60
        y = master.winfo_rooty() + 60
        self.geometry("+{}+{}".format(x, y))

    def _field(self, label: str, var: tk.StringVar, width: int, hint: str) -> None:
        tk.Label(self, text=label, font=F_META, fg=MUTED, bg=CARD).pack(anchor="w", pady=(6, 2))
        tk.Entry(self, textvariable=var, font=F_TITLE, width=width, relief="solid", bd=1).pack(fill="x")
        tk.Label(self, text=hint, font=(FONT, 8), fg="#a0a7b0", bg=CARD,
                 wraplength=440, justify="left").pack(anchor="w")

    def _toggle_key(self) -> None:
        self.e_key.configure(show="" if self.v_show.get() else "*")

    def _cfg(self) -> Dict[str, str]:
        return {
            "base_url": self.v_base.get().strip(),
            "model": self.v_model.get().strip(),
            "api_key": self.v_key.get().strip(),
        }

    def _test(self) -> None:
        cfg = self._cfg()
        if not store.ai_ready(cfg):
            self.lb_status.configure(text="● 三项都要填才能测试", fg=ORANGE)
            return
        self.btn_test.configure(state="disabled")
        self.lb_status.configure(text="● 正在测试…", fg=MUTED)

        def work() -> None:
            ok, msg, cost = ai_parser.test_connection(cfg)
            self.after(0, lambda: self._tested(ok, msg, cost))

        threading.Thread(target=work, daemon=True).start()

    def _tested(self, ok: bool, msg: str, cost: float) -> None:
        if not self.winfo_exists():
            return
        self.btn_test.configure(state="normal")
        if ok:
            self.lb_status.configure(text="● {}（{:.1f}s）".format(msg, cost), fg=GREEN)
        else:
            self.lb_status.configure(text="● " + msg, fg=RED)

    def _save(self) -> None:
        self.app.data["ai"] = self._cfg()
        store.save(self.app.data)
        self.app.refresh()
        self.destroy()


# --------------------------------------------------------------------------
# 识别结果确认框：逐条勾选，标题与时间可当场改
# --------------------------------------------------------------------------
class ConfirmDialog(tk.Toplevel):
    def __init__(self, master: "App", drafts: List[Dict[str, Any]], image_path: str):
        super().__init__(master)
        self.result: Optional[List[Dict[str, Any]]] = None
        self._drafts = drafts
        self._image_path = image_path
        self.title("确认识别结果")
        self.configure(bg=CARD, padx=16, pady=14)
        self.transient(master)

        tk.Label(self, text="识别到 {} 条，请逐条确认".format(len(drafts)), font=F_H1,
                 bg=CARD, fg=TEXT).pack(anchor="w")
        tk.Label(self,
                 text="标题可以直接改；时间点一下弹日历选。时间留空会进入「待设时间」区，之后由你补。",
                 font=F_META, fg=MUTED, bg=CARD).pack(anchor="w", pady=(2, 10))

        box = tk.Frame(self, bg=CARD)
        box.pack(fill="both", expand=True)
        self._rows = []
        for d in drafts:
            row = tk.Frame(box, bg=CARD_IDLE, padx=8, pady=6)
            row.pack(fill="x", pady=3)
            var = tk.BooleanVar(value=True)   # 默认全勾：漏掉一条比多一条麻烦得多
            tk.Checkbutton(row, variable=var, bg=CARD_IDLE, activebackground=CARD_IDLE
                           ).pack(side="left", anchor="n")
            mid = tk.Frame(row, bg=CARD_IDLE)
            mid.pack(side="left", fill="x", expand=True)
            v_title = tk.StringVar(value=d["title"])
            tk.Entry(mid, textvariable=v_title, font=F_TITLE, relief="solid", bd=1
                     ).pack(fill="x")
            sub = tk.Frame(mid, bg=CARD_IDLE)
            sub.pack(fill="x", pady=(4, 0))
            f_due = datepicker.DueField(sub, value=rules.parse_dt(d.get("due")), small=True, bg=CARD_IDLE)
            f_due.pack(side="left")
            if d.get("due_hint"):
                tk.Label(sub, text="原文：" + d["due_hint"], font=F_META, fg=ORANGE,
                         bg=CARD_IDLE).pack(side="left", padx=8)
            if d.get("notes"):
                tk.Label(sub, text=d["notes"], font=F_META, fg=MUTED, bg=CARD_IDLE
                         ).pack(side="left", padx=6)
            if d.get("confidence", 1) < 0.6:
                tk.Label(sub, text="把握较低，请核对", font=F_META, fg=RED, bg=CARD_IDLE
                         ).pack(side="left", padx=6)
            self._rows.append((var, v_title, f_due, d))

        btns = tk.Frame(self, bg=CARD)
        btns.pack(fill="x", pady=(12, 0))
        tk.Button(btns, text="全部加入", font=F_TITLE, bg=GREEN, fg="white", relief="flat",
                  padx=18, pady=6, cursor="hand2", command=self._ok).pack(side="right")
        tk.Button(btns, text="取消", font=F_TITLE, bg="#e5e7eb", fg=TEXT, relief="flat",
                  padx=16, pady=6, cursor="hand2", command=self.destroy).pack(side="right", padx=8)

        self.update_idletasks()
        self.geometry("640x{}".format(min(560, 220 + 72 * len(drafts))))
        self.geometry("+{}+{}".format(master.winfo_rootx() + 40, master.winfo_rooty() + 40))

    @staticmethod
    def _fmt(value: Any) -> str:
        dt = rules.parse_dt(value)
        return dt.strftime("%Y-%m-%d %H:%M") if dt else ""

    def _ok(self) -> None:
        picked = []
        for var, v_title, f_due, d in self._rows:
            if not var.get():
                continue
            title = v_title.get().strip()
            if not title:
                continue
            due = f_due.get()
            picked.append({
                "title": title,
                "due": rules.to_iso(due),
                "due_hint": None if due else (d.get("due_hint") or None),
                "notes": d.get("notes", ""),
                "confidence": d.get("confidence", 0.7),
            })
        self.result = picked
        self.destroy()


# --------------------------------------------------------------------------
# 主窗口
# --------------------------------------------------------------------------
class App(tk.Tk):
    def __init__(self) -> None:
        super().__init__()
        self.title("{} v{}".format(APP_NAME, VERSION))
        self.configure(bg=BG)
        self.geometry("760x720")
        self.minsize(620, 480)
        self.data = store.load()
        self.show_done = bool(self.data["settings"].get("show_done"))
        self.show_someday = False
        self._build()
        self.refresh()
        self.after(30000, self._tick)   # 半分钟刷一次"剩 N 分钟"与过期判定

    # ---------- 布局 ----------
    def _build(self) -> None:
        header = tk.Frame(self, bg=CARD, padx=18, pady=10)
        header.pack(fill="x")
        top = tk.Frame(header, bg=CARD)
        top.pack(fill="x")
        tk.Label(top, text="日程表", font=F_H1, bg=CARD, fg=TEXT).pack(side="left")

        # 按钮从右往左打包，视觉顺序为：+ 新增 ｜ 上传图片 ｜ 设置
        for text, cmd, primary in (
            ("设置", self.on_settings, False),
            ("上传图片", self.on_upload, False),
            ("+ 新增", self.on_add, True),
        ):
            bg = GREEN if primary else "#eef2f7"
            fg = "white" if primary else TEXT
            b = tk.Button(top, text=text, font=F_BTN, bg=bg, fg=fg, relief="flat",
                          padx=12, pady=5, cursor="hand2", command=cmd,
                          activebackground="#256b50" if primary else "#e2e8f0",
                          activeforeground="white" if primary else TEXT)
            b.pack(side="right", padx=3)
            if text == "上传图片":
                self.btn_upload = b

        # 统计单独占一行：标题 + 三个按钮在 760px 下会挤爆（实测需要 787px）
        self.lb_stat = tk.Label(header, text="", font=F_META, bg=CARD, fg=MUTED, anchor="w")
        self.lb_stat.pack(fill="x", pady=(3, 0))

        tk.Frame(self, bg=LINE, height=1).pack(fill="x")

        wrap = tk.Frame(self, bg=BG)
        wrap.pack(fill="both", expand=True)
        self.canvas = tk.Canvas(wrap, bg=BG, highlightthickness=0)
        sb = ttk.Scrollbar(wrap, orient="vertical", command=self.canvas.yview)
        self.canvas.configure(yscrollcommand=sb.set)
        sb.pack(side="right", fill="y")
        self.canvas.pack(side="left", fill="both", expand=True)

        self.inner = tk.Frame(self.canvas, bg=BG)
        self._win = self.canvas.create_window((0, 0), window=self.inner, anchor="nw")
        self.inner.bind("<Configure>",
                        lambda e: self.canvas.configure(scrollregion=self.canvas.bbox("all")))
        self.canvas.bind("<Configure>",
                         lambda e: self.canvas.itemconfig(self._win, width=e.width))

    # 滚轮与滚动区域的处理方式参考 tkScrolledFrame（MIT，bmjcode）：
    # https://github.com/bmjcode/tkScrolledFrame —— 把 wheel 事件逐个绑到子控件上，
    # 比 bind_all 更可控（不会在弹窗里误滚动主列表），并兼容 Windows/macOS/Linux 三种 delta。
    def _bind_wheel(self, widget: tk.Misc) -> None:
        widget.bind("<MouseWheel>", self._on_wheel)
        widget.bind("<Button-4>", self._on_wheel)
        widget.bind("<Button-5>", self._on_wheel)
        for child in widget.winfo_children():
            self._bind_wheel(child)

    def _on_wheel(self, event) -> None:
        import sys as _sys

        if _sys.platform.startswith("darwin"):
            self.canvas.yview_scroll(-1 * event.delta, "units")
        elif getattr(event, "num", None) == 4:
            self.canvas.yview_scroll(-1, "units")
        elif getattr(event, "num", None) == 5:
            self.canvas.yview_scroll(1, "units")
        else:
            step = int(event.delta) // 120 or (1 if event.delta > 0 else -1)
            self.canvas.yview_scroll(-1 * step, "units")

    # ---------- 渲染 ----------
    def refresh(self) -> None:
        for child in self.inner.winfo_children():
            child.destroy()
        now = datetime.now()
        items = self.data.get("items", [])
        parts = rules.split(items, now)
        s = rules.summary(items, now)

        self.lb_stat.configure(
            text="待办 {} ｜ 过期 {} ｜ 待设时间 {} ｜ 已完成 {}".format(
                s["live"], s["expired"], s["no_due"], s["done"]))

        ready = store.ai_ready(self.data["ai"])
        self.btn_upload.configure(state="normal" if ready else "disabled",
                                  fg=TEXT if ready else "#b6bcc4")
        if not ready:
            self.btn_upload.configure(text="上传图片（未配置）")

        if s["no_due"]:
            banner = tk.Frame(self.inner, bg="#fef3c7", padx=14, pady=8)
            banner.pack(fill="x", padx=14, pady=(12, 4))
            tk.Label(banner,
                     text="{} 项未设截止时间，请尽快补充".format(s["no_due"]),
                     font=(FONT, 10, "bold"), bg="#fef3c7", fg=ORANGE_DARK
                     ).pack(side="left")
            self._render_section_title("待设时间", s["no_due"], accent=ORANGE, top=6)
            for it in parts[rules.B_NODUE]:
                self._render_row(it, rules.B_NODUE)

        if parts["timeline"]:
            for label, group in rules.group_timeline(parts["timeline"], now):
                self._render_group_title(label)
                for it in group:
                    kind = rules.bucket_of(it, now)
                    self._render_row(it, kind)

        if s["no_due"] == 0 and not parts["timeline"]:
            empty = tk.Frame(self.inner, bg=BG)
            empty.pack(fill="x", pady=60)
            tk.Label(empty, text="还没有日程", font=(FONT, 12), bg=BG, fg=MUTED).pack()
            tk.Label(empty, text="点右上角「+ 新增」，或把通知截图拖进来",
                     font=F_META, bg=BG, fg="#a8b0b8").pack(pady=(4, 0))

        self._render_section_title("不急", s["someday"], collapsible=True,
                                   expanded=self.show_someday, key="someday", top=18)
        if self.show_someday:
            for it in parts[rules.B_SOMEDAY]:
                self._render_row(it, rules.B_SOMEDAY)
            if not parts[rules.B_SOMEDAY]:
                self._render_empty_hint("没有标记为「不急」的日程")

        self._render_section_title("已完成", s["done"], collapsible=True,
                                   expanded=self.show_done, key="done", top=8)
        if self.show_done:
            for it in parts[rules.B_DONE]:
                self._render_row(it, rules.B_DONE)
            if not parts[rules.B_DONE]:
                self._render_empty_hint("还没有完成的日程")

        tk.Frame(self.inner, bg=BG, height=16).pack(fill="x")
        self._bind_wheel(self.inner)   # 新建的每一行都要能滚

    def _render_group_title(self, label: str) -> None:
        f = tk.Frame(self.inner, bg=BG, padx=16)
        f.pack(fill="x", pady=(14, 2))
        tk.Label(f, text=label, font=F_SECTION, bg=BG,
                 fg=RED if label == "已过期" else MUTED).pack(side="left")
        tk.Frame(f, bg="#dfe3e8", height=1).pack(side="left", fill="x", expand=True, padx=(10, 0))

    def _render_section_title(self, text: str, count: int, collapsible: bool = False,
                              expanded: bool = True, key: str = "", accent: str = MUTED,
                              top: int = 14) -> None:
        f = tk.Frame(self.inner, bg=BG, padx=16)
        f.pack(fill="x", pady=(top, 2))
        tk.Label(f, text="{}".format(text), font=F_SECTION, bg=BG, fg=accent).pack(side="left")
        tk.Label(f, text=" ({})".format(count), font=F_META, bg=BG, fg=MUTED).pack(side="left")
        if collapsible:
            tk.Button(f, text="收起 ▴" if expanded else "展开 ▾", font=F_META, bg=BG,
                      fg="#5b6470", relief="flat", bd=0, cursor="hand2",
                      activebackground=BG,
                      command=lambda: self._toggle(key)).pack(side="right")

    def _toggle(self, key: str) -> None:
        if key == "someday":
            self.show_someday = not self.show_someday
        else:
            self.show_done = not self.show_done
            self.data["settings"]["show_done"] = self.show_done
            store.save(self.data)
        self.refresh()

    def _render_empty_hint(self, text: str) -> None:
        tk.Label(self.inner, text=text, font=F_META, bg=BG, fg="#a8b0b8",
                 anchor="w", padx=20).pack(fill="x", pady=6)

    # ---------- 单行 ----------
    def _render_row(self, item: Dict[str, Any], kind: str) -> None:
        now = datetime.now()
        if kind == rules.B_NODUE:
            bg, bar, fg = CARD_NODUE, ORANGE, ORANGE_DARK
        elif kind == rules.B_EXPIRED:
            bg, bar, fg = CARD_EXPIRED, RED, RED
        elif kind == rules.B_SOMEDAY:
            bg, bar, fg = CARD_IDLE, SLATE, MUTED
        elif kind == rules.B_DONE:
            bg, bar, fg = CARD_IDLE, CARD_IDLE, "#9aa1a9"
        else:
            bg, bar, fg = CARD, CARD, TEXT

        card = tk.Frame(self.inner, bg=bg, padx=0, pady=0, highlightbackground=LINE,
                        highlightthickness=1)
        card.pack(fill="x", padx=14, pady=2)

        tk.Frame(card, bg=bar, width=3).pack(side="left", fill="y")

        left = tk.Frame(card, bg=bg)
        left.pack(side="left", padx=(10, 0))
        CheckCircle(left, on_click=lambda i=item: self.on_complete(i),
                    color=GREEN, bg=bg, checked=(kind == rules.B_DONE)).pack()

        right = tk.Frame(card, bg=bg)
        right.pack(side="right", padx=(6, 8))

        mid = tk.Frame(card, bg=bg)
        mid.pack(side="left", fill="both", expand=True, padx=(10, 6), pady=8)

        title = tk.Label(mid, text=item.get("title", "（无标题）"),
                         font=F_TITLE_DONE if kind == rules.B_DONE else F_TITLE,
                         bg=bg, fg=fg, anchor="w", justify="left", wraplength=380)
        title.pack(fill="x")

        meta_bits = []
        if kind == rules.B_NODUE:
            meta_bits.append("未设时间")
            if item.get("due_hint"):
                meta_bits.append("原文：" + str(item["due_hint"]))
        elif kind == rules.B_DONE:
            done_at = rules.parse_dt(item.get("completed_at"))
            meta_bits.append("完成于 " + (done_at.strftime("%m-%d %H:%M") if done_at else "—"))
        else:
            d = rules.due_display(item)
            if d:
                meta_bits.append(d)
            meta_bits.append(rules.remaining_text(item, now))
        if item.get("notes"):
            meta_bits.append(str(item["notes"]))
        if meta_bits:
            tk.Label(mid, text="　·　".join(meta_bits), font=F_META, bg=bg,
                     fg=RED if kind == rules.B_EXPIRED else MUTED,
                     anchor="w", justify="left", wraplength=420).pack(fill="x", pady=(2, 0))

        # 行内按钮
        if kind == rules.B_NODUE:
            self._mini(right, "设置时间", lambda i=item: self.on_edit(i), bg, accent=True)
            self._mini(right, "不急", lambda i=item: self.on_someday(i), bg)
        elif kind == rules.B_DONE:
            self._mini(right, "撤销", lambda i=item: self.on_uncomplete(i), bg)
        elif kind == rules.B_SOMEDAY:
            self._mini(right, "恢复", lambda i=item: self.on_restore(i), bg)
        else:
            self._mini(right, "编辑", lambda i=item: self.on_edit(i), bg)
            self._mini(right, "不急", lambda i=item: self.on_someday(i), bg)
        self._mini(right, "删除", lambda i=item: self.on_delete(i), bg, danger=True)

        for w in (title, mid):
            w.bind("<Double-Button-1>", lambda e, i=item: self.on_edit(i))

    def _mini(self, parent: tk.Misc, text: str, cmd: Callable, bg: str,
              accent: bool = False, danger: bool = False) -> None:
        fg = RED if danger else (GREEN if accent else "#5b6470")
        tk.Button(parent, text=text, font=F_BTN, bg=bg, fg=fg, relief="flat", bd=0,
                  padx=6, pady=2, cursor="hand2", activebackground=bg,
                  command=cmd).pack(side="right", padx=2)

    # ---------- 事件 ----------
    def on_add(self) -> None:
        dlg = ItemDialog(self)
        self.wait_window(dlg)
        if not dlg.result:
            return
        r = dlg.result
        now = datetime.now()
        item = {
            "id": store.new_id(self.data["items"]),
            "title": r["title"],
            "due": r["due"],
            "due_hint": r["due_hint"],
            "status": rules.STATUS_SOMEDAY if r["someday"] else rules.STATUS_PENDING,
            "notes": r["notes"],
            "created_at": rules.to_iso(now),
            "updated_at": rules.to_iso(now),
            "completed_at": None,
            "source": "manual",
            "ai": None,
            "image_ref": None,
        }
        self.data["items"].append(item)
        store.save(self.data)
        self.refresh()

    def on_edit(self, item: Dict[str, Any]) -> None:
        dlg = ItemDialog(self, item)
        self.wait_window(dlg)
        if not dlg.result:
            return
        r = dlg.result
        updated = dict(item)
        updated.update({
            "title": r["title"],
            "due": r["due"],
            "due_hint": r["due_hint"],
            "notes": r["notes"],
            "status": rules.STATUS_SOMEDAY if r["someday"] else (
                item.get("status") if item.get("status") == rules.STATUS_DONE else rules.STATUS_PENDING),
            "updated_at": rules.to_iso(datetime.now()),
        })
        store.replace(self.data, updated)
        store.save(self.data)
        self.refresh()

    def on_complete(self, item: Dict[str, Any]) -> None:
        now = datetime.now()
        store.replace(self.data, rules.complete(item, now))
        store.save(self.data)
        self.refresh()

    def on_uncomplete(self, item: Dict[str, Any]) -> None:
        store.replace(self.data, rules.uncomplete(item, datetime.now()))
        store.save(self.data)
        self.refresh()

    def on_someday(self, item: Dict[str, Any]) -> None:
        store.replace(self.data, rules.set_someday(item, datetime.now()))
        store.save(self.data)
        self.show_someday = True
        self.refresh()

    def on_restore(self, item: Dict[str, Any]) -> None:
        store.replace(self.data, rules.restore(item, datetime.now()))
        store.save(self.data)
        self.refresh()

    def on_delete(self, item: Dict[str, Any]) -> None:
        if not messagebox.askyesno("删除", "删除「{}」？".format(item.get("title", "")), parent=self):
            return
        store.remove(self.data, item.get("id", ""))
        self.refresh()

    def on_settings(self) -> None:
        dlg = SettingsDialog(self)
        self.wait_window(dlg)

    def on_upload(self) -> None:
        if not store.ai_ready(self.data["ai"]):
            if messagebox.askyesno("还没配置 AI 接口",
                                   "图片识别需要在设置里填写接口地址、模型名和 API Key。\n\n现在去设置吗？",
                                   parent=self):
                self.on_settings()
            return
        path = filedialog.askopenfilename(
            parent=self, title="选择包含日程信息的图片",
            filetypes=[("图片", "*.png *.jpg *.jpeg *.webp *.bmp"), ("全部文件", "*.*")])
        if not path:
            return
        self.btn_upload.configure(state="disabled", text="识别中…")
        self.update_idletasks()

        def work() -> None:
            try:
                drafts = ai_parser.parse_image(path, self.data["ai"])
                self.after(0, lambda: self._parsed(drafts, path, None))
            except ai_parser.ParseError as exc:
                self.after(0, lambda: self._parsed([], path, str(exc)))
            except Exception as exc:  # 兜底，别让界面卡在"识别中"
                self.after(0, lambda: self._parsed([], path, "未知错误：{}".format(exc)))

        threading.Thread(target=work, daemon=True).start()

    def _parsed(self, drafts: List[Dict[str, Any]], path: str, error: Optional[str]) -> None:
        self.btn_upload.configure(state="normal", text="上传图片")
        if error:
            messagebox.showerror("识别失败", error + "\n\n可以手动新增这条日程。", parent=self)
            return
        if not drafts:
            messagebox.showinfo(
                "没识别到日程",
                "这张图里没有找到时间和事项信息。\n\n"
                "如果确认图里明明有日程，去「设置 → 测试连接」确认一下模型能不能读图——\n"
                "纯文本模型（如 deepseek 文本版、qwen-plus）收到图片会直接忽略，永远返回空。",
                parent=self)
            return
        dlg = ConfirmDialog(self, drafts, path)
        self.wait_window(dlg)
        if not dlg.result:
            return
        now = datetime.now()
        for r in dlg.result:
            iid = store.new_id(self.data["items"])
            img_ref = store.save_image(path, iid) if self.data["settings"].get("keep_image", True) else None
            self.data["items"].append({
                "id": iid,
                "title": r["title"],
                "due": r["due"],
                "due_hint": r["due_hint"],
                "status": rules.STATUS_PENDING,
                "notes": r.get("notes", ""),
                "created_at": rules.to_iso(now),
                "updated_at": rules.to_iso(now),
                "completed_at": None,
                "source": "image",
                "ai": {"confidence": r.get("confidence", 0.7),
                       "model": self.data["ai"].get("model", ""),
                       "image": path},
                "image_ref": img_ref,
            })
        store.save(self.data)
        self.refresh()

    def _tick(self) -> None:
        """定时重算：让"剩 N 分钟"和过期判定自己走。"""
        try:
            self.refresh()
        finally:
            self.after(30000, self._tick)


def main() -> None:
    _set_dpi_aware()
    app = App()
    app.mainloop()


if __name__ == "__main__":
    main()
