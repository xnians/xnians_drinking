# -*- coding: utf-8 -*-
"""
datepicker.py —— 日历式截止时间选择控件

替代原来手输"2026-12-04 23:59"的文本框：点一下弹出月历，选日、选时、确定。

为什么不用现成的 tkcalendar：它是最顺手的方案，但许可证是 **GPL-3.0**，
被 import 进来会让整个项目被迫 GPL（见 CREDITS.md 的拒绝记录）。
月历本身就是一个 7×6 的按钮网格 + 一点日期运算，自己画反而更可控。

对外只暴露一个控件：

    f = DueField(parent, value=datetime(...), small=False)
    f.get()            # -> datetime 或 None
    f.set(dt)          # 程序里改
    f.set_enabled(False)   # 配合"不设时间"勾选框
"""

from __future__ import annotations

import calendar
import tkinter as tk
from tkinter import ttk
from datetime import date, datetime, timedelta
from typing import Callable, Optional

# 配色与 app.py 对齐。这里独立定义而不是反向 import，避免 app ↔ datepicker 循环依赖。
CARD = "#ffffff"
TEXT = "#1f2328"
MUTED = "#7d8590"
LINE = "#e5e7eb"
GREEN = "#2f7d5d"
GREEN_DARK = "#256b50"
HOVER = "#eef2f7"
TODAY_BG = "#eaf5ef"
OTHER = "#b6bcc4"
BORDER = "#c9ced6"
DISABLED_BG = "#f4f5f7"
RED_TEXT = "#b91c1c"

FONT = "Microsoft YaHei UI"
WEEK = ("一", "二", "三", "四", "五", "六", "日")
QUICK_TIMES = (("09:00", 9, 0), ("14:00", 14, 0), ("18:00", 18, 0), ("23:59", 23, 59))


def _fmt(dt: Optional[datetime]) -> str:
    return dt.strftime("%Y-%m-%d %H:%M") if dt else ""


class CalendarPopup(tk.Toplevel):
    """挂在 DueField 下面的月历浮层。"""

    WIDTH = 274

    def __init__(self, anchor: tk.Widget, value: Optional[datetime],
                 on_pick: Callable[[Optional[datetime]], None]):
        super().__init__(anchor, bg=LINE, padx=1, pady=1)   # 1px 边框靠背景色露出来
        self.withdraw()
        self.overrideredirect(True)
        self._anchor = anchor
        self._on_pick = on_pick
        self._done = False

        # 初始值：没设置过就默认"今天 + 下一个整点"，和系统日历的默认行为一致
        if value:
            base = value.replace(second=0, microsecond=0)
        else:
            nxt = datetime.now().replace(second=0, microsecond=0) + timedelta(hours=1)
            base = nxt.replace(minute=0)
        self._sel: date = base.date()
        self._hour, self._minute = base.hour, base.minute
        self._view = date(base.year, base.month, 1)

        self.body = tk.Frame(self, bg=CARD, padx=10, pady=8)
        self.body.pack()

        self._build_header()
        self._build_week()
        self.grid = tk.Frame(self.body, bg=CARD)
        self.grid.pack()
        self._build_time()
        self._build_footer()
        self._render_grid()

        self.bind("<Escape>", lambda e: self.close())
        self.bind("<Button-1>", self._on_background_click)
        self.bind("<FocusOut>", self._on_focus_out)

    # ---------- 构建 ----------
    def _build_header(self) -> None:
        head = tk.Frame(self.body, bg=CARD)
        head.pack(fill="x", pady=(0, 6))
        nav = (("«", -12), ("‹", -1))
        for text, delta in nav:
            self._nav_btn(head, text, delta).pack(side="left")
        self.lb_head = tk.Label(head, text="", font=(FONT, 10, "bold"), bg=CARD, fg=TEXT)
        self.lb_head.pack(side="left", expand=True)
        for text, delta in (("›", 1), ("»", 12)):
            self._nav_btn(head, text, delta).pack(side="right")

    def _nav_btn(self, parent: tk.Misc, text: str, delta: int) -> tk.Button:
        return tk.Button(parent, text=text, font=(FONT, 10), bg=CARD, fg="#5b6470",
                         relief="flat", bd=0, width=2, cursor="hand2",
                         activebackground=HOVER,
                         command=lambda d=delta: self._shift_month(d))

    def _build_week(self) -> None:
        row = tk.Frame(self.body, bg=CARD)
        row.pack(fill="x")
        for i, name in enumerate(WEEK):
            fg = MUTED if i < 5 else "#a07a3a"
            tk.Label(row, text=name, font=(FONT, 8), bg=CARD, fg=fg, width=4
                     ).pack(side="left")

    def _build_time(self) -> None:
        tk.Frame(self.body, bg=LINE, height=1).pack(fill="x", pady=(6, 6))
        line = tk.Frame(self.body, bg=CARD)
        line.pack(fill="x")
        tk.Label(line, text="时间", font=(FONT, 9), bg=CARD, fg=MUTED).pack(side="left")

        self.v_hour = tk.StringVar(value="{:02d}".format(self._hour))
        self.v_min = tk.StringVar(value="{:02d}".format(self._minute))
        self.sp_min = ttk.Spinbox(line, from_=0, to=59, width=3, justify="center",
                                  textvariable=self.v_min, font=(FONT, 9),
                                  command=lambda: self._read_time(normalize=True))
        self.sp_hour = ttk.Spinbox(line, from_=0, to=23, width=3, justify="center",
                                   textvariable=self.v_hour, font=(FONT, 9),
                                   command=lambda: self._read_time(normalize=True))
        self.sp_hour.pack(side="left", padx=(8, 0))
        tk.Label(line, text=":", font=(FONT, 9), bg=CARD, fg=MUTED).pack(side="left")
        self.sp_min.pack(side="left")
        # 手输两位数字也算数：键盘输入只记值，失焦/回车才回写补零，免得打断打字
        for sp in (self.sp_hour, self.sp_min):
            sp.bind("<KeyRelease>", lambda e: self._read_time())
            sp.bind("<Return>", lambda e: self._read_time(normalize=True))
            sp.bind("<FocusOut>", lambda e: self._read_time(normalize=True))

        chips = tk.Frame(self.body, bg=CARD)
        chips.pack(fill="x", pady=(6, 0))
        for label, hh, mm in QUICK_TIMES:
            tk.Button(chips, text=label, font=(FONT, 8), bg="#f1f4f8", fg="#5b6470",
                      relief="flat", bd=0, padx=6, pady=2, cursor="hand2",
                      activebackground=HOVER,
                      command=lambda h=hh, m=mm: self._set_time(h, m)
                      ).pack(side="left", padx=(0, 4))

    def _build_footer(self) -> None:
        tk.Frame(self.body, bg=LINE, height=1).pack(fill="x", pady=(8, 6))
        foot = tk.Frame(self.body, bg=CARD)
        foot.pack(fill="x")
        tk.Button(foot, text="清除", font=(FONT, 9), bg="#f1f4f8", fg=RED_TEXT,
                  relief="flat", bd=0, padx=8, pady=3, cursor="hand2",
                  activebackground=HOVER, command=self._clear).pack(side="left")
        tk.Button(foot, text="确定", font=(FONT, 9, "bold"), bg=GREEN, fg="white",
                  relief="flat", bd=0, padx=14, pady=3, cursor="hand2",
                  activebackground=GREEN_DARK, activeforeground="white",
                  command=self._commit).pack(side="right")
        tk.Button(foot, text="今天", font=(FONT, 9), bg="#f1f4f8", fg="#5b6470",
                  relief="flat", bd=0, padx=8, pady=3, cursor="hand2",
                  activebackground=HOVER, command=self._today
                  ).pack(side="right", padx=6)

    # ---------- 月历网格 ----------
    def _render_grid(self) -> None:
        for ch in self.grid.winfo_children():
            ch.destroy()
        self.lb_head.configure(text="{}年{}月".format(self._view.year, self._view.month))

        today = date.today()
        # 周一为一周起点：monthcalendar 默认周一开头
        weeks = calendar.Calendar(firstweekday=0).monthdatescalendar(
            self._view.year, self._view.month)
        while len(weeks) < 6:            # 固定 6 行，避免切月时浮层高度跳动
            weeks.append([d + timedelta(days=7) for d in weeks[-1]])

        for r, week in enumerate(weeks):
            for c, d in enumerate(week):
                in_month = d.month == self._view.month
                selected = d == self._sel
                if selected:
                    bg, fg, bold = GREEN, "#ffffff", "bold"
                elif d == today:
                    bg, fg, bold = TODAY_BG, GREEN_DARK, "bold"
                else:
                    bg, fg, bold = CARD, TEXT if in_month else OTHER, "normal"
                btn = tk.Button(self.grid, text=str(d.day), width=3, height=1,
                                font=(FONT, 9, bold), bg=bg, fg=fg,
                                relief="flat", bd=0, cursor="hand2",
                                activebackground=HOVER, activeforeground=fg,
                                command=lambda x=d: self._pick_day(x))
                btn.grid(row=r, column=c, padx=1, pady=1)
                if not selected:
                    btn.bind("<Enter>", lambda e, b=btn: b.configure(bg=HOVER))
                    btn.bind("<Leave>", lambda e, b=btn, c0=bg: b.configure(bg=c0))
                btn.bind("<Double-Button-1>", lambda e, x=d: self._pick_day(x, commit=True))

    def _shift_month(self, delta: int) -> None:
        y, m = self._view.year, self._view.month - 1 + delta
        self._view = date(y + m // 12, m % 12 + 1, 1)
        self._render_grid()

    def _pick_day(self, d: date, commit: bool = False) -> None:
        self._sel = d
        if d.month != self._view.month:
            self._view = date(d.year, d.month, 1)
            self._render_grid()
            return
        self._render_grid()
        if commit:
            self._commit()

    def _set_time(self, hh: int, mm: int) -> None:
        self._hour, self._minute = hh, mm
        self.v_hour.set("{:02d}".format(hh))
        self.v_min.set("{:02d}".format(mm))

    def _read_time(self, normalize: bool = False) -> None:
        """Spinbox 里手输的内容也认，越界就夹到合法范围。"""
        try:
            hh = int(str(self.v_hour.get()).strip() or 0)
        except ValueError:
            hh = self._hour
        try:
            mm = int(str(self.v_min.get()).strip() or 0)
        except ValueError:
            mm = self._minute
        self._hour, self._minute = min(23, max(0, hh)), min(59, max(0, mm))
        if normalize:
            self.v_hour.set("{:02d}".format(self._hour))
            self.v_min.set("{:02d}".format(self._minute))

    def _today(self) -> None:
        now = datetime.now()
        self._sel = now.date()
        self._view = date(now.year, now.month, 1)
        self._set_time(18, 0)
        self._render_grid()

    # ---------- 提交 / 关闭 ----------
    def _commit(self) -> None:
        self._read_time()
        value = datetime(self._sel.year, self._sel.month, self._sel.day,
                         self._hour, self._minute)
        self._finish(value)

    def _clear(self) -> None:
        self._finish(None)

    def _finish(self, value: Optional[datetime]) -> None:
        if self._done:
            return
        self._done = True
        try:
            self.grab_release()
        except tk.TclError:
            pass
        self.destroy()
        self._on_pick(value)

    def close(self) -> None:
        if self._done:
            return
        self._done = True
        try:
            self.grab_release()
        except tk.TclError:
            pass
        self.destroy()

    def _on_background_click(self, event) -> None:
        """点浮层外面就关掉（grab 之后外部点击也会送到这里）。"""
        if event.widget is not self:
            return
        px, py = self.winfo_pointerxy()
        x, y = self.winfo_rootx(), self.winfo_rooty()
        if not (x <= px < x + self.winfo_width() and y <= py < y + self.winfo_height()):
            self.close()

    def _on_focus_out(self, _event=None) -> None:
        # 焦点跑出浮层（比如 Alt+Tab 去别的程序）就关，防止 grab 把主界面锁住
        self.after(160, self._check_focus)

    def _check_focus(self) -> None:
        if self._done or not self.winfo_exists():
            return
        try:
            focused = self.focus_get()
        except (KeyError, tk.TclError):
            focused = None
        if focused is None or not str(focused).startswith(str(self)):
            self.close()

    # ---------- 定位 ----------
    def show(self) -> None:
        self._anchor.update_idletasks()
        self.update_idletasks()
        w, h = self.winfo_reqwidth(), self.winfo_reqheight()
        x = self._anchor.winfo_rootx()
        y = self._anchor.winfo_rooty() + self._anchor.winfo_height() + 4
        sw, sh = self.winfo_screenwidth(), self.winfo_screenheight()
        if x + w > sw - 8:
            x = sw - w - 8
        if y + h > sh - 40:                       # 下面放不下就翻到上方
            y = self._anchor.winfo_rooty() - h - 4
        self.geometry("+{}+{}".format(max(0, x), max(0, y)))
        self.deiconify()
        # overrideredirect 的浮层默认压在父对话框下面，必须显式置顶
        try:
            self.attributes("-topmost", True)
        except tk.TclError:
            pass
        self.lift()
        self.grab_set()
        try:
            self.focus_force()
        except tk.TclError:
            pass


class DueField(tk.Frame):
    """一个像输入框的按钮：显示当前截止时间，点开月历。"""

    def __init__(self, master: tk.Misc, value: Optional[datetime] = None,
                 on_change: Optional[Callable[[Optional[datetime]], None]] = None,
                 small: bool = False, bg: str = CARD):
        super().__init__(master, bg=bg)
        self._value = value if isinstance(value, datetime) else None
        self._on_change = on_change
        self._enabled = True
        self._popup: Optional[CalendarPopup] = None

        self.btn = tk.Button(
            self, text="", font=(FONT, 9 if small else 10),
            bg=CARD, fg=TEXT, relief="flat", bd=0, anchor="w",
            padx=6 if small else 9, pady=2 if small else 5,
            cursor="hand2", disabledforeground=OTHER,
            highlightthickness=1, highlightbackground=BORDER,
            activebackground=HOVER, activeforeground=TEXT,
            command=self.open)
        self.btn.pack(fill="x")
        self._sync()

    # ---------- 读写 ----------
    def get(self) -> Optional[datetime]:
        return self._value

    def set(self, value: Optional[datetime], notify: bool = False) -> None:
        self._value = value if isinstance(value, datetime) else None
        self._sync()
        if notify and self._on_change:
            self._on_change(self._value)

    def set_enabled(self, flag: bool) -> None:
        self._enabled = bool(flag)
        self.btn.configure(state="normal" if flag else "disabled",
                           bg=CARD if flag else DISABLED_BG)
        if not flag:
            self.btn.configure(fg=OTHER)
        else:
            self._sync()

    def _sync(self) -> None:
        if self._value:
            self.btn.configure(text="{}  ▾".format(_fmt(self._value)), fg=TEXT)
        else:
            self.btn.configure(text="未设置 · 点此选择", fg=MUTED)

    # ---------- 交互 ----------
    def open(self) -> None:
        if not self._enabled:
            return
        if self._popup is not None and self._popup.winfo_exists():
            self._popup.close()
            return
        self._popup = CalendarPopup(self.btn, self._value, self._picked)
        self._popup.show()

    def _picked(self, value: Optional[datetime]) -> None:
        self._value = value
        self._sync()
        if self._on_change:
            self._on_change(value)
