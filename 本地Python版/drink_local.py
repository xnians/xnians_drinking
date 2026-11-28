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
import threading
import datetime
import urllib.request
import tkinter as tk
from tkinter import ttk

# ---------------------------------------------------------------------------
# 可选联网陪聊配置（非核心功能；API_KEY 留空时完全不启用，断网也不影响本地打卡）
# ---------------------------------------------------------------------------
# OpenAI 兼容接口地址，默认 DeepSeek，也可填其他兼容服务
API_BASE_URL = 'https://api.deepseek.com'
# 在这里填你的 API key；留空 = 不启用联网陪聊，界面与离线版完全一致
API_KEY = ''
# 使用的模型名
MODEL = 'deepseek-chat'

# 三套联网陪聊人设的 system prompt（写得具体、彼此区分，避免机械重复催喝水）
CHAT_SYSTEM_PROMPTS = {
    # 学霸同桌：理性鼓励，从记忆效率切入
    "xueba": "你是用户的「学霸同桌」，坐在旁边一起自习的靠谱伙伴。说话平和、有条理，擅长从专注方法、记忆效率、作息状态切入给建议；像真实同学一样自然聊天，会主动关心对方今天的学习和状态。可以在对话里自然地带一句喝水或休息提醒，但不要每句都机械重复“先喝口水”。回复控制在两三句以内，口语化，不说教、不长篇大论。",
    # 吐槽搭子：毒舌暖心带梗
    "tucao": "你是用户的「吐槽搭子」，嘴硬心软、爱开玩笑带点梗，损完一定会给台阶、露出暖心底色。像熟络的室友一样聊天，会吐槽对方久坐、硬撑、拿奶茶当水喝，但落脚点是关心。催喝水要自然、别生硬；语气接地气、有网感，但绝不能真的伤人或贬低对方。回复两三句以内，口语化。",
    # 软萌水精灵：可爱撒娇叠词 emoji
    "shuijing": "你是用户的「软萌水精灵」，一直陪在桌边的小可爱，说话撒娇软糯，爱用叠词和少量 emoji，会闹着要一口水喝、替主人开心或打气。语气软乎乎、亲切自然，像真实陪伴者；催喝水用撒娇的方式表达，不要每句都重复同样的叠词套路。回复两三句以内，简短可爱。",
}

# 聊天上下文记忆：保留最近若干轮 user/assistant，一起发给模型
MEMORY_TURNS = 6

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


def _prune_history(history):
    """只保留最近 7 天（含今天）的杯数记录。"""
    out = {}
    today = datetime.date.today()
    for i in range(6, -1, -1):
        d = today - datetime.timedelta(days=i)
        out[d.isoformat()] = history.get(d.isoformat(), 0)
    return out


def load_data():
    today = datetime.date.today().isoformat()
    default = {
        "date": today,
        "cups": 0,
        "goal": 6,
        "logs": [],          # [{"cup": 1, "time": "09:12"}]
        "role": "xueba",
        "interval": 45,     # 提醒间隔（分钟），本地版兜底可配
        "remind_on": True,
        "streak": 0,        # 连续达标天数
        "met_today": False, # 今天是否已达标（避免重复计 streak）
        "evening": False,   # 晚自习时段是否打过卡
        "history": {},      # {"2026-11-22": 4, ...} 近7天杯数
    }
    if os.path.exists(DATA_FILE):
        try:
            with open(DATA_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)
            if data.get("date") != today:   # 新的一天，归档历史并重置今日
                prev_cups = data.get("cups", 0)
                if data.get("date"):
                    data.setdefault("history", {})[data["date"]] = prev_cups
                # 上一天达标则连续天数保留，否则清零
                data["streak"] = max(data.get("streak", 0), 1) if prev_cups >= data.get("goal", 6) else 0
                data["date"] = today
                data["cups"] = 0
                data["logs"] = []
                data["met_today"] = False
                data["evening"] = False
                data["history"] = _prune_history(data.get("history", {}))
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
        self.chat_memory = []   # 联网陪聊的上下文记忆（最近若干轮）

        root.title("咕咚校园 · 本地打卡")
        # 仅在启用联网陪聊时增高窗口以容纳聊天区；API_KEY 为空时保持原尺寸
        root.geometry("420x880" if API_KEY.strip() else "420x760")
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
                                  height=6, relief="flat", bd=1)
        self.log_box.pack(fill="x", **pad)

        # 近 7 天饮水柱状图（tkinter Canvas，仅标准库，无外部依赖）
        tk.Label(self.root, bg="#EAF4FC", fg="#5A7A96",
                 text="近 7 天饮水", font=("微软雅黑", 11)).pack(pady=(10, 2))
        self.chart = tk.Canvas(self.root, height=130, bg="#EAF4FC",
                               highlightthickness=0)
        self.chart.pack(fill="x", **pad)

        # 可选联网陪聊区（仅 API_KEY 非空时构建；留空则不出现，界面与现状一致）
        self._build_chat(pad)

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

    # ---------- 可选联网陪聊 ----------
    def _build_chat(self, pad):
        # API_KEY 为空：不构建任何聊天控件，界面与离线版完全一致
        if not API_KEY.strip():
            return

        chat_frame = tk.Frame(self.root, bg="#EAF4FC")
        chat_frame.pack(**pad, pady=(10, 4))

        tk.Label(chat_frame, bg="#EAF4FC", fg="#5A7A96",
                 text="联网陪聊", font=("微软雅黑", 11)).pack(anchor="w")

        # 只读消息显示区
        self.chat_box = tk.Text(chat_frame, font=("微软雅黑", 11), height=6,
                                wrap="word", relief="flat", bd=1, state="disabled")
        self.chat_box.pack(fill="x", pady=(2, 4))

        row = tk.Frame(chat_frame, bg="#EAF4FC")
        row.pack(fill="x")
        self.chat_entry = tk.Entry(row, font=("微软雅黑", 11))
        self.chat_entry.pack(side="left", fill="x", expand=True)
        self.chat_entry.bind("<Return>", lambda e: self._send_chat())
        tk.Button(row, text="发送", relief="flat", bg="#D6E9F7",
                  font=("微软雅黑", 11),
                  command=self._send_chat).pack(side="right", padx=(6, 0))

    def _append_chat(self, who, text):
        # 仅在聊天区已构建时调用；回到主线程操作控件
        if not getattr(self, "chat_box", None):
            return
        self.chat_box.config(state="normal")
        self.chat_box.insert(tk.END, f"【{who}】{text}\n")
        self.chat_box.see(tk.END)
        self.chat_box.config(state="disabled")

    def _send_chat(self):
        text = self.chat_entry.get().strip()
        if not text:
            return
        self.chat_entry.delete(0, tk.END)
        self._append_chat("我", text)
        # 后台线程请求，不阻塞 tkinter mainloop
        threading.Thread(target=self._chat_worker,
                         args=(text,), daemon=True).start()

    def _chat_worker(self, user_text):
        try:
            system = CHAT_SYSTEM_PROMPTS.get(
                self.data["role"], CHAT_SYSTEM_PROMPTS["xueba"])
            # 带上最近若干轮上下文，接得上前面聊过的内容
            messages = [{"role": "system", "content": system}]
            messages += self.chat_memory[-MEMORY_TURNS * 2:]
            messages.append({"role": "user", "content": user_text})
            payload = {
                "model": MODEL,
                "messages": messages,
                "temperature": 0.8,
                "max_tokens": 200,
            }
            req = urllib.request.Request(
                f"{API_BASE_URL.rstrip('/')}/chat/completions",
                data=json.dumps(payload).encode("utf-8"),
                headers={
                    "Content-Type": "application/json",
                    "Authorization": f"Bearer {API_KEY}",
                },
                method="POST",
            )
            with urllib.request.urlopen(req, timeout=10) as resp:
                body = json.loads(resp.read().decode("utf-8"))
            reply = body["choices"][0]["message"]["content"].strip()
            if not reply:
                raise ValueError("empty reply")
            self.chat_memory.append(
                {"role": "user", "content": user_text},
                {"role": "assistant", "content": reply})
            name = ROLES[self.data["role"]]["name"]
            self.root.after(0, lambda: self._append_chat(name, reply))
        except Exception:
            # 无网 / 超时 / HTTP 错误 / JSON 解析失败 / key 无效等一律静默兜底
            name = ROLES[self.data["role"]]["name"]
            note = "联网陪聊暂时不可用，本地打卡提醒不受影响"
            self.chat_memory.append(
                {"role": "user", "content": user_text},
                {"role": "assistant", "content": note})
            self.root.after(
                0, lambda: self._append_chat(name, note))

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
        # 晚自习时段（19–21 点）打卡
        if 19 <= now.hour < 22:
            self.data["evening"] = True
        # 今日首次达标：连续天数 +1
        if self.data["cups"] >= self.data["goal"] and not self.data["met_today"]:
            self.data["met_today"] = True
            self.data["streak"] += 1
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
        streak = self.data["streak"]
        self.cup_lbl.config(text=f"{cups}")
        self.goal_lbl.config(text=f"今日目标 {goal} 杯 · 连续达标 {streak} 天")
        self.progress["value"] = min(100, round(cups / goal * 100))

        # 记录
        self.log_box.delete(0, tk.END)
        for item in reversed(self.data["logs"]):
            self.log_box.insert(tk.END, f"第 {item['cup']} 杯  {item['time']}")

        self._draw_chart()

        # 完成提示
        if cups >= goal:
            self.done_lbl.config(text="🎉 今日目标达成，今天不再提醒啦！")
            self.drink_btn.config(state="disabled", bg="#BFD8E8")
        else:
            self.done_lbl.config(text="")
            self.drink_btn.config(state="normal", bg="#4AA8E0")

        self._refresh_role()

    def _last7(self):
        """返回最近 7 天 [(星期, 杯数, 是否今天), ...]。"""
        today = datetime.date.today()
        week_names = ["周一", "周二", "周三", "周四", "周五", "周六", "周日"]
        out = []
        for i in range(6, -1, -1):
            d = today - datetime.timedelta(days=i)
            key = d.isoformat()
            cups = self.data["cups"] if i == 0 else self.data["history"].get(key, 0)
            out.append((week_names[d.weekday()], cups, i == 0))
        return out

    def _draw_chart(self):
        """纯 Canvas 绘制近 7 天柱状图，无外部库。"""
        c = self.chart
        c.delete("all")
        width = 360
        height = 130
        base_y = 100
        goal = self.data["goal"]
        data = self._last7()
        slot = width / 7
        for idx, (label, cups, is_today) in enumerate(data):
            x0 = idx * slot + (slot - 22) / 2
            bar_h = round(min(cups, goal) / goal * 70) if goal else 0
            y_top = base_y - bar_h
            color = "#2B7BB8" if is_today else "#5BB6EE"
            if bar_h > 0:
                c.create_rectangle(x0, y_top, x0 + 22, base_y,
                                   fill=color, outline="")
            c.create_text(x0 + 11, y_top - 10, text=str(cups),
                           fill="#7AA9C7", font=("微软雅黑", 9))
            c.create_text(x0 + 11, base_y + 14, text=label,
                           fill="#9CC3D8", font=("微软雅黑", 9))

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
