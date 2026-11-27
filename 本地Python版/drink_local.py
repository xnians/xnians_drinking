# -*- coding: utf-8 -*-
"""
咕咚校园 · 本地离线打卡提醒（Python / tkinter）
------------------------------------------------
- 无需联网、无需安装任何第三方库，Python 3.8+ 自带 tkinter 即可运行。
- 功能：今日打卡杯数 / 目标 6 杯、三个人设切换、打卡鼓励语、
        定时提醒弹窗、本地记录（data.json，跨天自动清零）。
- 答辩演示：双击「启动本地版.vbs」即可，断网也能用。

作者：豆包协作线（AIGC）
"""

import json
import os
import random
import datetime
import tkinter as tk
from tkinter import ttk

# ---------------------------------------------------------------------------
# 一、人设与话术（取自 AIGC 文案库，{cups} 会替换成当前杯数）
# ---------------------------------------------------------------------------
ROLES = {
    "xueba": {
        "name": "学霸同桌",
        "color": "#4AA8E0",
        # 打卡后说的鼓励语
        "drink": [
            "早八先喝一杯温水，大脑开机更快。",
            "自习 50 分钟记得补一口，专注力会回来。",
            "今天已经喝了 {cups} 杯，保持节奏，别断档。",
            "水分充足，记忆力和状态都会在线。",
            "这一杯喝得很值，继续保持这个节奏。",
            "身体补水到位，刷题效率才不会掉线。",
        ],
        # 到点提醒说的话
        "remind": [
            "专注一段时间了，起来接杯水，眼睛也歇一下。",
            "现在补一口温水，比下课猛灌一瓶更舒服。",
            "水杯就在手边，看到就喝一口，不用等口渴。",
            "大脑含水量够，记忆提取更快，来一杯。",
            "把这杯当成下一段专注的开机水。",
        ],
    },
    "tucao": {
        "name": "吐槽搭子",
        "color": "#F0915B",
        "drink": [
            "又想靠奶茶续命？先把这杯温水喝了再说。",
            "你都坐一上午了，水杯是落宿舍了吗？",
            "别等嗓子冒烟才想起来喝水，那是透支。",
            "{cups} 杯了，再坚持一下，别半途而废啊。",
            "行啊你，这杯喝得算你有觉悟。",
            "别光卷题不喝水，脱水了可没人替你考。",
        ],
        "remind": [
            "你都坐这儿多久没挪窝了？起来，接水，现在。",
            "渴了才喝就晚了，趁没人排队去，现在。",
            "别一到点就低头刷手机，先把这杯水解决了。",
            "笔没停过嘴没动过，你是来修仙的还是来自习的？",
            "别硬撑，接个水回来思路反而更顺。",
        ],
    },
    "shuijing": {
        "name": "软萌水精灵",
        "color": "#7EC8E3",
        "drink": [
            "咕嘟咕嘟～喝一口水，我就变圆一点点。",
            "宝宝，水杯就在手边，抬抬手就喝啦。",
            "已经 {cups} 杯啦，你对我真好，么么哒。",
            "不喝水我会蔫掉的，快喂我一口嘛～",
            "谢谢主人，这一口我记住啦。",
            "你喝水的样子最好看了，再来一杯好不好。",
        ],
        "remind": [
            "主人～我肚子空啦，快去给我续上。",
            "课间到啦，带我去接杯水好不好。",
            "我就安安静静坐你桌边，渴了喂我一口呀。",
            "坐久啦，起来走一走，顺便带我去接水。",
            "喝口水再继续嘛，我陪着你哦。",
        ],
    },
}

ROLE_ORDER = ["xueba", "tucao", "shuijing"]

# ---------------------------------------------------------------------------
# 二、本地数据（同目录 data.json，跨天自动清零）
# ---------------------------------------------------------------------------
DATA_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data.json")


def load_data():
    today = datetime.date.today().isoformat()
    default = {
        "date": today,
        "cups": 0,
        "goal": 6,
        "logs": [],          # [{"cup": 1, "time": "09:12"}]
        "role": "xueba",
        "interval": 45,     # 提醒间隔（分钟）
        "remind_on": True,
    }
    if os.path.exists(DATA_FILE):
        try:
            with open(DATA_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)
            if data.get("date") != today:   # 新的一天，清零
                data["date"] = today
                data["cups"] = 0
                data["logs"] = []
            for k, v in default.items():
                data.setdefault(k, v)
            return data
        except Exception:
            return default
    return default


def save_data(data):
    try:
        with open(DATA_FILE, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
    except Exception:
        pass


# ---------------------------------------------------------------------------
# 三、主程序
# ---------------------------------------------------------------------------
class DrinkApp:
    def __init__(self, root):
        self.root = root
        self.data = load_data()
        self.after_id = None

        root.title("咕咚校园 · 本地打卡")
        root.geometry("420x620")
        root.resizable(False, False)
        root.configure(bg="#EAF4FC")

        self._build_ui()
        self._refresh()
        self._schedule_reminder()

    # ---------- 界面 ----------
    def _build_ui(self):
        pad = {"padx": 18}

        # 日期
        now = datetime.datetime.now()
        week = ["周日", "周一", "周二", "周三", "周四", "周五", "周六"][now.weekday()]
        self.date_lbl = tk.Label(
            self.root, bg="#EAF4FC", fg="#5A7A96",
            text=f"{now.month}月{now.day}日 {week}", font=("微软雅黑", 13))
        self.date_lbl.pack(pady=(16, 4))

        # 杯数大数字
        self.cup_lbl = tk.Label(
            self.root, bg="#EAF4FC", fg="#2B7BB9",
            font=("微软雅黑", 46, "bold"))
        self.cup_lbl.pack(pady=(6, 2))

        self.goal_lbl = tk.Label(
            self.root, bg="#EAF4FC", fg="#5A7A96",
            text="", font=("微软雅黑", 12))
        self.goal_lbl.pack()

        # 进度条
        self.progress = ttk.Progressbar(self.root, length=320, maximum=100)
        self.progress.pack(pady=10)

        # 人设切换
        role_frame = tk.Frame(self.root, bg="#EAF4FC")
        role_frame.pack(**pad, pady=6)
        self.role_btns = {}
        for key in ROLE_ORDER:
            b = tk.Button(
                role_frame, text=ROLES[key]["name"],
                font=("微软雅黑", 11), width=9, relief="flat",
                command=lambda k=key: self.switch_role(k))
            b.pack(side="left", padx=6)
            self.role_btns[key] = b

        # 人设气泡
        self.bubble = tk.Label(
            self.root, bg="#FFFFFF", fg="#333333",
            font=("微软雅黑", 13), wraplength=360, justify="center",
            height=4, relief="solid", bd=1)
        self.bubble.pack(fill="x", **pad, pady=10)

        # 打卡大按钮
        self.drink_btn = tk.Button(
            self.root, text="我喝了一杯 💧", font=("微软雅黑", 18, "bold"),
            bg="#4AA8E0", fg="white", relief="flat", height=2,
            activebackground="#3A95D0", command=self.drink)
        self.drink_btn.pack(fill="x", **pad, pady=8)

        # 完成提示
        self.done_lbl = tk.Label(self.root, bg="#EAF4FC", fg="#2E9E5B",
                                 font=("微软雅黑", 12, "bold"), text="")
        self.done_lbl.pack()

        # 记录列表
        tk.Label(self.root, bg="#EAF4FC", fg="#5A7A96",
                 text="今日记录", font=("微软雅黑", 11)).pack(pady=(10, 2))
        self.log_box = tk.Listbox(self.root, font=("微软雅黑", 11),
                                  height=7, relief="flat", bd=1)
        self.log_box.pack(fill="x", **pad)

        # 设置区
        set_frame = tk.Frame(self.root, bg="#EAF4FC")
        set_frame.pack(**pad, pady=12)

        tk.Label(set_frame, bg="#EAF4FC", text="目标(杯):",
                 font=("微软雅黑", 11)).grid(row=0, column=0, padx=4)
        self.goal_var = tk.StringVar(value=str(self.data["goal"]))
        tk.Entry(set_frame, textvariable=self.goal_var, width=5,
                 font=("微软雅黑", 11)).grid(row=0, column=1, padx=4)

        tk.Label(set_frame, bg="#EAF4FC", text="提醒间隔(分):",
                 font=("微软雅黑", 11)).grid(row=0, column=2, padx=4)
        self.interval_var = tk.StringVar(value=str(self.data["interval"]))
        tk.Entry(set_frame, textvariable=self.interval_var, width=5,
                 font=("微软雅黑", 11)).grid(row=0, column=3, padx=4)

        self.remind_var = tk.BooleanVar(value=self.data["remind_on"])
        tk.Checkbutton(set_frame, text="定时提醒", variable=self.remind_var,
                       bg="#EAF4FC", font=("微软雅黑", 11),
                       command=self.toggle_remind).grid(row=0, column=4, padx=8)

        tk.Button(set_frame, text="保存设置", relief="flat",
                  bg="#D6E9F7", font=("微软雅黑", 11),
                  command=self.save_settings).grid(row=0, column=5, padx=4)

    # ---------- 行为 ----------
    def random_talk(self, kind):
        key = self.data["role"]
        arr = ROLES[key][kind]
        t = random.choice(arr).replace("{cups}", str(self.data["cups"]))
        return ROLES[key]["name"], t

    def switch_role(self, key):
        self.data["role"] = key
        save_data(self.data)
        self._refresh_role()

    def drink(self):
        if self.data["cups"] >= self.data["goal"]:
            self._refresh()
            return
        self.data["cups"] += 1
        now = datetime.datetime.now()
        self.data["logs"].append(
            {"cup": self.data["cups"],
             "time": f"{now:%H:%M}"})
        save_data(self.data)
        self._refresh()

    def save_settings(self):
        try:
            self.data["goal"] = max(1, int(self.goal_var.get()))
            self.data["interval"] = max(1, int(self.interval_var.get()))
        except ValueError:
            pass
        save_data(self.data)
        self._restart_timer()
        self._refresh()

    def toggle_remind(self):
        self.data["remind_on"] = self.remind_var.get()
        save_data(self.data)
        self._restart_timer()

    # ---------- 刷新 ----------
    def _refresh(self):
        cups = self.data["cups"]
        goal = self.data["goal"]
        self.cup_lbl.config(text=f"{cups}")
        self.goal_lbl.config(text=f"今日目标 {goal} 杯")
        self.progress["value"] = min(100, round(cups / goal * 100))

        # 记录
        self.log_box.delete(0, tk.END)
        for item in reversed(self.data["logs"]):
            self.log_box.insert(tk.END, f"第 {item['cup']} 杯  {item['time']}")

        # 完成提示
        if cups >= goal:
            self.done_lbl.config(text="🎉 今日目标达成，今天不再提醒啦！")
            self.drink_btn.config(state="disabled", bg="#BFD8E8")
        else:
            self.done_lbl.config(text="")
            self.drink_btn.config(state="normal", bg="#4AA8E0")

        self._refresh_role()

    def _refresh_role(self):
        for key, btn in self.role_btns.items():
            if key == self.data["role"]:
                btn.config(bg=ROLES[key]["color"], fg="white",
                           font=("微软雅黑", 11, "bold"))
            else:
                btn.config(bg="#FFFFFF", fg="#333333",
                           font=("微软雅黑", 11))
        name, talk = self.random_talk("drink")
        self.bubble.config(text=f"【{name}】{talk}")

    # ---------- 定时提醒 ----------
    def _restart_timer(self):
        if self.after_id:
            self.root.after_cancel(self.after_id)
            self.after_id = None
        self._schedule_reminder()

    def _schedule_reminder(self):
        if not self.data["remind_on"]:
            return
        ms = max(1, self.data["interval"]) * 60 * 1000
        self.after_id = self.root.after(ms, self._popup_remind)

    def _popup_remind(self):
        self._schedule_reminder()  # 排下一次
        if self.data["cups"] >= self.data["goal"]:
            return
        name, talk = self.random_talk("remind")
        win = tk.Toplevel(self.root)
        win.title("喝水提醒")
        win.geometry("360x220")
        win.resizable(False, False)
        win.configure(bg="#EAF4FC")
        tk.Label(win, bg="#EAF4FC", fg=ROLES[self.data["role"]]["color"],
                 text=name, font=("微软雅黑", 14, "bold")).pack(pady=(18, 6))
        tk.Label(win, bg="#EAF4FC", fg="#333333", wraplength=310,
                 justify="center", text=talk, font=("微软雅黑", 13)).pack(pady=6)
        tk.Button(win, text="我喝了一杯", bg="#4AA8E0", fg="white",
                  relief="flat", font=("微软雅黑", 13, "bold"),
                  command=lambda: (self.drink(), win.destroy())).pack(
            fill="x", padx=40, pady=8)
        tk.Button(win, text="稍后再说", relief="flat", bg="#D6E9F7",
                  font=("微软雅黑", 12), command=win.destroy).pack(
            fill="x", padx=40)


def main():
    root = tk.Tk()
    DrinkApp(root)
    root.mainloop()


if __name__ == "__main__":
    main()
