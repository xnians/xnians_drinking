#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
💧 喝水提醒  Water Reminder  v1.3.0
=====================================
一个简洁美观的 Windows 喝水提醒小工具（Python + tkinter，无第三方依赖）。

功能一览
--------
* 定时提醒：每 N 分钟弹窗，可暂停/继续；达成当日目标后自动停表，次日恢复。
* 喝水记录：点「喝水」记一杯，带正向反馈小窗 + 3 秒冷却防连点。
* 饮料记录：填容量与「每 100ml 含糖量」g/100ml，自动换算总糖量，并给出健康评级与推荐摄入量。
* 统计：今日 / 本周 / 本月杯数、今日糖分、执行率、连续达标天数，跨天/周/月自动重置。
* 后台常驻：关闭窗口收进系统托盘，托盘右键可暂停/记录/退出；再次启动只唤回原窗口。
* 大字号易读（2 倍），中文字距更舒展。

运行
----
双击 `启动喝水提醒.vbs`（无控制台窗口），或：
    pythonw water_reminder.py
    python  water_reminder.py     # 带控制台，便于排查
"""

from __future__ import annotations

import json
import math
import os
import queue
import random
import sys
import threading
import time
import tkinter as tk
from datetime import date, datetime
from pathlib import Path
from tkinter import font as tkfont

APP_NAME = "喝水提醒"
APP_ID = "WaterReminder"
VERSION = "1.3.0"

BASE_DIR = Path(__file__).resolve().parent
CONFIG_FILE = BASE_DIR / "config.json"

INTERVAL_MIN, INTERVAL_MAX = 1, 480
GOAL_MIN, GOAL_MAX = 1, 24
ML_PER_CUP = 250                 # 默认一杯水按 250ml 估算
DRINK_COOLDOWN = 3.0             # 点「喝水」后的冷却秒数（防连点）
LOG_KEEP_DAYS = 400              # 明细日志保留天数

# ---------------------------------------------------------- 个性化饮水建议 --
# 口径：健康成年人每日基础需水量约 30 ml/kg 体重（公开常见经验值，非医疗标准），
# 再按活动强度、环境温度、身体状态逐项修正。所有数值均为估算，仅供日常参考。
WATER_ML_PER_KG = 30
ACTIVITY_OPTIONS = (
    ("sedentary", "久坐 · 上课自习", 0),
    ("light", "轻度 · 步行通勤", 250),
    ("moderate", "中度 · 体育课健身", 500),
    ("high", "高强度 · 训练体力活", 800),
)
CLIMATE_OPTIONS = (
    ("cool", "凉爽 · 20℃以下", 0),
    ("mild", "常温 · 20-28℃", 200),
    ("hot", "炎热 · 28℃以上", 400),
)
BODY_OPTIONS = (
    ("normal", "平时", 0),
    ("sweaty", "出汗较多 · 熬夜或特殊时期", 250),
)
ADVICE_ML_MIN, ADVICE_ML_MAX = 1000, 4000
ADVICE_DISCLAIMER = ("按公开健康成人经验公式估算，仅供日常饮水参考，不构成医疗建议；"
                     "如有疾病、孕期等特殊情况请遵医嘱。")

# 世界卫生组织（WHO）建议：添加糖摄入应少于总能量的 10%，最好低于 5%。
# 以每日 2000 kcal 为例，约等于 50 g（严格标准 25 g）。
SUGAR_PERCENT_TARGET = 10.0
SUGAR_CLOSE_RATIO = 0.8          # 达到推荐量的 80% 起提示「接近上限」
SUGAR_OVER_RATIO = 1.0

DEFAULT_QUOTES = [
    "工作再忙，也别忘了给自己补补水",
    "喝口水，休息 30 秒，效率更高哦",
    "身体是自己的，记得多喝水",
    "现在起身接杯水，顺便活动一下肩颈吧",
    "一杯水，就是最简单的健康投资",
    "别忘了喝水！你的身体在向你道谢",
    "小口慢饮，让身体慢慢吸收",
    "再忙也要喝口水，这是对自己的温柔",
]

# ---------------------------------------------------------------- 配色 --
# 两套主题；运行时 _THEME 指向其中一套。代码里统一用 P.xxx 取色，
# 切换主题只需重建 UI（状态都在 cfg 里，不丢数据）。

class _Palette:
    def __init__(self, **kw):
        self.__dict__.update(kw)


_LIGHT = dict(
    BG="#F3F7FC",          # 主背景
    CARD="#FFFFFF",        # 卡片
    INK="#17273D",         # 主文字
    MUTED="#8193AB",       # 次要文字
    LINE="#E4ECF6",        # 分割线 / 卡片描边
    PRIMARY="#3E8EF7",     # 主题蓝
    PRIMARY_DARK="#2776DE",
    TEAL="#18B69B",        # 成功
    AMBER="#F0A32C",       # 稍后 / 饮料
    TINT="#F0F6FF",        # 浅蓝底
    SOFT="#F5F9FF",        # 极浅蓝底
    SOFT_EDGE="#D5E5FB",   # 倒计时卡片描边
    FAINT="#A8B6C8",       # 更淡的提示文字
    DIVIDER="#F1F5FB",     # 设置项细分隔线
    TRACK="#E7EEF8",       # 进度条底
    TRACK_SUGAR="#EEF2F8", # 糖分条底
    TICK="#C7D3E3",        # 糖分条刻度
    OFF="#CBD7E5",         # 开关关闭态
    DISABLED_BG="#EEF2F7", # 禁用按钮底
    DISABLED_FG="#A9B6C7", # 禁用按钮字
    BTN_LIGHT="#EDF4FF",   # light 变体按钮
    BTN_LIGHT_HOVER="#DBE9FF",
    BTN_OUTLINE="#FFFFFF", # outline 变体按钮
    BTN_OUTLINE_HOVER="#EAF2FF",
    BTN_SECONDARY="#DCE9FB",
    DANGER="#E5484D",      # 超标红
    DROP_LIGHT="#A9CBFB",  # 水滴高光
    DROP_WHITE="#BCD9FF",  # 白水滴上的浅蓝高光
    DROP_EDGE="#D9EAFF",   # 水滴外圈
    HEAT_0="#E8EFF7",      # 热力图：无记录
    HEAT_1="#CFE9FB",      # 热力图：少于半目标
    HEAT_2="#7FD3EA",      # 热力图：接近达标
    HEAT_3="#18B69B",      # 热力图：已达标
)

_DARK = dict(
    BG="#111827",          # 主背景
    CARD="#1B2636",        # 卡片
    INK="#E8EEF7",         # 主文字
    MUTED="#93A4BC",       # 次要文字
    LINE="#2C3A4E",        # 分割线 / 卡片描边
    PRIMARY="#5AA0FF",     # 主题蓝（深色下提亮）
    PRIMARY_DARK="#82BAFF",
    TEAL="#2FD1AE",        # 成功
    AMBER="#F5B75C",       # 稍后 / 饮料
    TINT="#1E3050",        # 浅蓝底 → 深蓝底
    SOFT="#172438",        # 极浅蓝底 → 深蓝底
    SOFT_EDGE="#2E466B",
    FAINT="#6E8098",
    DIVIDER="#243144",
    TRACK="#2A3A4E",
    TRACK_SUGAR="#2A3A4E",
    TICK="#445158",
    OFF="#3A4A5E",
    DISABLED_BG="#263244",
    DISABLED_FG="#5F7085",
    BTN_LIGHT="#1E3352",
    BTN_LIGHT_HOVER="#27436A",
    BTN_OUTLINE="#1B2636",
    BTN_OUTLINE_HOVER="#243B5C",
    BTN_SECONDARY="#223651",
    DANGER="#FF6B6B",
    DROP_LIGHT="#7FB0F5",
    DROP_WHITE="#9CC6FF",
    DROP_EDGE="#33507A",
    HEAT_0="#243144",
    HEAT_1="#1E4A63",
    HEAT_2="#1B8078",
    HEAT_3="#2FD1AE",
)

THEMES = {"light": _Palette(**_LIGHT), "dark": _Palette(**_DARK)}
_THEME_NAME = "light"
P = THEMES["light"]        # 当前调色板（可变引用）

# 旧代码仍用 BG/CARD/... 这些全局名取色。切换主题时把它们一并重绑定，
# 于是重建 UI 后所有旧函数都能读到新主题色，无需逐行改造。
BG = P.BG
CARD = P.CARD
INK = P.INK
MUTED = P.MUTED
LINE = P.LINE
PRIMARY = P.PRIMARY
PRIMARY_DARK = P.PRIMARY_DARK
TEAL = P.TEAL
AMBER = P.AMBER
TINT = P.TINT
SOFT = P.SOFT


def set_palette(name: str) -> None:
    """切换调色板。控件颜色在建 UI 时固化，调用方需重建 UI 才能生效。"""
    global P, _THEME_NAME
    global BG, CARD, INK, MUTED, LINE, PRIMARY, PRIMARY_DARK
    global TEAL, AMBER, TINT, SOFT
    _THEME_NAME = name if name in THEMES else "light"
    P = THEMES[_THEME_NAME]
    BG, CARD, INK, MUTED, LINE = P.BG, P.CARD, P.INK, P.MUTED, P.LINE
    PRIMARY, PRIMARY_DARK = P.PRIMARY, P.PRIMARY_DARK
    TEAL, AMBER, TINT, SOFT = P.TEAL, P.AMBER, P.TINT, P.SOFT


def theme_name() -> str:
    return _THEME_NAME

# ---------------------------------------------------------------- 配置 --

def _clamp(value, low, high):
    try:
        return max(low, min(high, int(value)))
    except (TypeError, ValueError):
        return low


def _num(value, default=0.0):
    try:
        v = float(value)
    except (TypeError, ValueError):
        return default
    if v != v or v in (float("inf"), float("-inf")):
        return default
    return v


def default_config() -> dict:
    return {
        "interval_min": 45,
        "goal": 8,
        "snooze_min": 5,
        "gentle": True,
        "autostart": False,
        "theme": "light",
        "hotkey": True,
        "kcal_per_day": 2000,
        "sugar_ratio": SUGAR_PERCENT_TARGET,
        "profile": {"sex": "female", "weight": 55.0, "activity": "light",
                    "climate": "mild", "body": "normal", "applied": False},
        "quotes": list(DEFAULT_QUOTES),
        "data": {"log": {}, "water_fix": {}, "day": "", "done": 0, "skipped": 0,
                 "events": [], "history": {}},
    }


def _sanitize_data(data: dict) -> None:
    log = data.get("log")
    if not isinstance(log, dict):
        log = {}
    clean = {}
    for day, rec in list(log.items())[-LOG_KEEP_DAYS * 2:]:
        if not isinstance(rec, dict):
            continue
        drinks = rec.get("drink_list")
        entry = {
            "water": _clamp(rec.get("water", 0), 0, 9999),
            "sugar": max(0.0, _num(rec.get("sugar", 0))),
            "ml": max(0.0, _num(rec.get("ml", 0))),
            "drinks": _clamp(rec.get("drinks", 0), 0, 9999),
            "drink_list": [d for d in drinks if isinstance(d, dict)][-60:]
            if isinstance(drinks, list) else [],
        }
        clean[str(day)] = entry
    data["log"] = dict(list(clean.items())[-LOG_KEEP_DAYS:])
    fix = data.get("water_fix")
    data["water_fix"] = ({str(k): _clamp(v, -9999, 9999) for k, v in fix.items()}
                         if isinstance(fix, dict) else {})


def load_config() -> dict:
    cfg = default_config()
    try:
        raw = json.loads(CONFIG_FILE.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return cfg
    if isinstance(raw, dict):
        for key in ("interval_min", "goal", "snooze_min"):
            if key in raw:
                cfg[key] = raw[key]
        for key in ("gentle", "autostart", "hotkey"):
            if key in raw:
                cfg[key] = bool(raw[key])
        if raw.get("theme") in ("light", "dark"):
            cfg["theme"] = raw["theme"]
        if isinstance(raw.get("quotes"), list) and raw["quotes"]:
            cfg["quotes"] = [str(q) for q in raw["quotes"] if str(q).strip()] or cfg["quotes"]
        if isinstance(raw.get("data"), dict):
            cfg["data"].update(raw["data"])
        if "profile" in raw:
            cfg["profile"] = normalize_profile(raw["profile"])
        if "kcal_per_day" in raw:
            cfg["kcal_per_day"] = raw["kcal_per_day"]
        if "sugar_ratio" in raw:
            cfg["sugar_ratio"] = _num(raw["sugar_ratio"], SUGAR_PERCENT_TARGET)
    cfg["interval_min"] = _clamp(cfg["interval_min"], INTERVAL_MIN, INTERVAL_MAX)
    cfg["goal"] = _clamp(cfg["goal"], GOAL_MIN, GOAL_MAX)
    cfg["snooze_min"] = _clamp(cfg["snooze_min"], 1, 60)
    cfg["kcal_per_day"] = _clamp(cfg["kcal_per_day"], 1200, 4000)
    cfg["sugar_ratio"] = min(20.0, max(5.0, _num(cfg["sugar_ratio"], SUGAR_PERCENT_TARGET)))
    data = cfg["data"]
    data.setdefault("day", "")
    data["done"] = _clamp(data.get("done", 0), 0, 999)
    data["skipped"] = _clamp(data.get("skipped", 0), 0, 999)
    if not isinstance(data.get("events"), list):
        data["events"] = []
    if not isinstance(data.get("history"), dict):
        data["history"] = {}
    _sanitize_data(data)
    return cfg


def save_config(cfg: dict) -> bool:
    try:
        # 临时文件名带 PID，避免多进程/残留进程互相覆盖
        tmp = CONFIG_FILE.with_name(f"{CONFIG_FILE.name}.{os.getpid()}.tmp")
        tmp.write_text(json.dumps(cfg, ensure_ascii=False, indent=2), encoding="utf-8")
        os.replace(tmp, CONFIG_FILE)
        return True
    except (OSError, TypeError, ValueError):
        return False


def _log_error(exc) -> None:
    """把被吞掉的异常写到同目录日志，便于排障。"""
    try:
        line = f"{datetime.now():%Y-%m-%d %H:%M:%S} {type(exc).__name__}: {exc}\n"
        with (BASE_DIR / "water_reminder.log").open("a", encoding="utf-8") as fh:
            fh.write(line)
    except OSError:
        pass


# ------------------------------------------------------------ 个性化饮水建议 --

def _option_delta(options, key, default=0):
    """(值, 文案, 增减ml) 元组表中按 key 取增减量，未知值回退默认。"""
    for value, _label, delta in options:
        if value == key:
            return delta
    return default


def normalize_profile(raw) -> dict:
    """清洗个人档案：类型/范围/枚举都收口，坏数据不进计算。"""
    base = default_config()["profile"]
    if not isinstance(raw, dict):
        return base
    sex = raw.get("sex")
    base["sex"] = sex if sex in ("female", "male") else "female"
    w = _num(raw.get("weight"), 55.0)
    base["weight"] = max(30.0, min(200.0, w))
    for key, table in (("activity", ACTIVITY_OPTIONS),
                       ("climate", CLIMATE_OPTIONS),
                       ("body", BODY_OPTIONS)):
        val = raw.get(key)
        base[key] = val if any(val == item[0] for item in table) else (
            "light" if key == "activity" else "normal" if key == "body" else "mild")
    base["applied"] = bool(raw.get("applied", False))
    return base


def water_advice(profile: dict) -> dict:
    """按身体情况估算每日饮水量。

    返回 ml / cups / 明细，均为估算值；杯数按 ML_PER_CUP 换算并夹在 GOAL 范围内。
    """
    p = normalize_profile(profile)
    weight = p["weight"]
    # 女性基础代谢与体液占比通常略低，按 0.9 系数估算（经验值，非医疗标准）
    sex_factor = 0.9 if p["sex"] == "female" else 1.0
    base = weight * WATER_ML_PER_KG * sex_factor
    parts = [("体重基础", base, f"{weight:g} kg × {WATER_ML_PER_KG} ml"
              + (" × 0.9" if sex_factor != 1.0 else ""))]
    for title, table, key in (("活动量", ACTIVITY_OPTIONS, "activity"),
                              ("环境气温", CLIMATE_OPTIONS, "climate"),
                              ("身体状态", BODY_OPTIONS, "body")):
        delta = _option_delta(table, p[key])
        label = next((lab for val, lab, d in table if val == p[key]), "")
        parts.append((title, delta, label))
    total = base + sum(item[1] for item in parts[1:])
    clamped = total < ADVICE_ML_MIN or total > ADVICE_ML_MAX
    total = _clamp(round(total), ADVICE_ML_MIN, ADVICE_ML_MAX)
    cups = _clamp(int(round(total / ML_PER_CUP)), GOAL_MIN, GOAL_MAX)
    return {"ml": int(total), "cups": cups, "parts": parts, "clamped": clamped}


# ---------------------------------------------------------------- 糖分评估 --

def recommended_sugar(kcal_per_day: float, ratio: float = SUGAR_PERCENT_TARGET) -> float:
    """推荐每日添加糖上限（克）。1 kcal ≈ 0.25 g 糖；WHO 建议 < 总能量 10%。"""
    return round(kcal_per_day * ratio / 100.0 * 0.25, 1)


def sugar_verdict(total_g: float, limit_g: float) -> dict:
    """按摄入量给出健康评估：level 0 良好 / 1 关注 / 2 偏高 / 3 超标。"""
    ratio = total_g / limit_g if limit_g > 0 else 0.0
    if ratio <= SUGAR_CLOSE_RATIO:
        return {"level": 0, "color": TEAL, "tag": "良好",
                "text": "糖摄入在推荐范围内，继续保持"}
    if ratio <= SUGAR_OVER_RATIO:
        return {"level": 1, "color": AMBER, "tag": "接近上限",
                "text": "已接近推荐上限，今天少喝点甜饮"}
    if ratio <= 1.5:
        return {"level": 2, "color": "#F0761F", "tag": "偏高",
                "text": "超过推荐量，建议明天换成无糖饮品"}
    return {"level": 3, "color": "#E5484D", "tag": "明显超标",
            "text": "糖分明显超标，注意控制含糖饮料"}


# ------------------------------------------------------------ 数据看板 --
# 全部数据来自本地 log / water_fix，不联网。这里是纯函数，便于单测。
def day_cups(cfg: dict, key: str) -> int:
    """某天实际杯数 = 日志 water + 手动修正 water_fix（口径与 _today_water 一致）。"""
    rec = cfg.get("data", {}).get("log", {}).get(key)
    base = int(rec.get("water", 0)) if isinstance(rec, dict) else 0
    fix = cfg.get("data", {}).get("water_fix", {})
    return max(0, base + int(fix.get(key, 0) or 0))


def heatmap_weeks(cfg: dict, weeks: int = 12, today: "date | None" = None) -> list:
    """近 N 周日历格：按周一到周日排列，每格 (day_key, cups, goal, in_future)。"""
    today = today or date.today()
    # 以本周周一为终点往前推 weeks-1 周
    this_monday = date.fromordinal(today.toordinal() - today.weekday())
    start = date.fromordinal(this_monday.toordinal() - (weeks - 1) * 7)
    goal = max(1, cfg.get("goal", 8))
    cells = []
    for i in range(weeks * 7):
        d = date.fromordinal(start.toordinal() + i)
        key = d.isoformat()
        cells.append((key, day_cups(cfg, key), goal, d > today))
    return cells


def week_trend(cfg: dict, today: "date | None" = None) -> list:
    """本周 7 天趋势：[(星期序号0-6, 日期, 杯数, 是否今天/未来)]。"""
    today = today or date.today()
    monday = date.fromordinal(today.toordinal() - today.weekday())
    goal = max(1, cfg.get("goal", 8))
    out = []
    for i in range(7):
        d = date.fromordinal(monday.toordinal() + i)
        out.append((i, d.isoformat(), day_cups(cfg, d.isoformat()),
                    goal, d == today, d > today))
    return out


def heat_level(cups: int, goal: int) -> int:
    """0 无记录 / 1 少于半目标 / 2 接近达标 / 3 已达标。"""
    if cups <= 0:
        return 0
    ratio = cups / max(1, goal)
    if ratio >= 1.0:
        return 3
    if ratio >= 0.5:
        return 2
    return 1


# ---------------------------------------------------------------- 缩放 --

_scale = 1.0
FONT_BOOST = 2.0        # 基准字号放大倍数
LAYOUT_BOOST = 1.0


def _boost_layout() -> None:
    global LAYOUT_BOOST
    LAYOUT_BOOST = 2.2 if FONT_BOOST >= 3 else (1.25 if FONT_BOOST > 1.5 else 1.0)


_boost_layout()


def S(value: float) -> int:
    """布局尺寸（随字号同步放大）。"""
    return int(round(value * _scale * LAYOUT_BOOST))


def FS(px: float) -> int:
    """字号像素（2 倍放大，最小 12px）。"""
    return max(12, int(round(px * _scale * FONT_BOOST)))


def detect_scale(win: tk.Tk) -> float:
    try:
        return max(1.0, win.winfo_fpixels("1i") / 96.0)
    except tk.TclError:
        return 1.0


def pick_cn_family() -> str:
    try:
        families = set(tkfont.families())
    except tk.TclError:
        return "Microsoft YaHei UI"
    for name in ("Microsoft YaHei UI", "Microsoft YaHei", "Segoe UI", "Arial"):
        if name in families:
            return name
    return "Helvetica"


def make_fonts(scale: float) -> dict:
    try:
        families = set(tkfont.families())
    except tk.TclError:
        families = set()
    cn = pick_cn_family()
    latin = "Segoe UI" if "Segoe UI" in families else cn

    def f(px, weight="normal", fam=None):
        return tkfont.Font(family=fam or latin, size=-FS(px), weight=weight)

    return {
        "app": f(21, "bold", cn),
        "status": f(11, "normal", cn),
        "small": f(12, "normal", cn),
        "tiny": f(11, "normal", cn),
        "body": f(13, "normal", cn),
        "btn": f(13, "bold", cn),
        "btn_small": f(12, "bold", cn),
        "num_big": f(46, "bold", latin),
        "num": f(21, "bold", latin),
        "num_md": f(18, "bold", latin),
        "section": f(12, "bold", cn),
        "quote": f(19, "bold", cn),
        "sw_title": f(13, "bold", cn),
        "sw_desc": f(11, "normal", cn),
        "glyph_hd": f(12, "bold", cn),
        "unit": f(12, "normal", cn),
    }


# ---------------------------------------------------------------- 字距 --

LETTER_GAP = "\u2009"          # THIN SPACE


def spaced(text: str) -> str:
    """给中文标题加细微字距（只在汉字之间插入，数字/标点保持原样）。"""
    if not text:
        return text

    def is_cjk(ch: str) -> bool:
        return "\u4e00" <= ch <= "\u9fff" or "\u3400" <= ch <= "\u4dbf"

    out, chars = [], list(text)
    for i, ch in enumerate(chars):
        out.append(ch)
        if i + 1 < len(chars) and is_cjk(ch) and is_cjk(chars[i + 1]):
            out.append(LETTER_GAP)
    return "".join(out)


def wrap_paragraph(text: str, width_px: int, f: tkfont.Font,
                   letter_gap: bool = False) -> str:
    """按字体实际宽度折行，兼容中英文混排。"""
    if not text or width_px <= 0:
        return text

    def is_cjk(ch: str) -> bool:
        return "\u4e00" <= ch <= "\u9fff" or "\u3400" <= ch <= "\u4dbf"

    out, line, width, prev = [], "", 0, ""
    for ch in text:
        piece = ch
        if letter_gap and is_cjk(prev) and is_cjk(ch):
            piece = LETTER_GAP + ch
        cw = f.measure(piece)
        if line and width + cw > width_px:
            out.append(line.rstrip())
            line, width = "", 0
            piece, cw = ch, f.measure(ch)
        line += piece
        width += cw
        prev = ch
    if line.strip():
        out.append(line)
    return "\n".join(out)


# ---------------------------------------------------------------- 跟随主界面 --

def follow_main_position(main: tk.Misc, w: int, h: int, gap: int | None = None):
    """弹窗位置：优先贴主界面右侧，其次左侧、下方，最后退回屏幕右下角。"""
    gap = S(12) if gap is None else gap
    try:
        sw, sh = main.winfo_screenwidth(), main.winfo_screenheight()
    except tk.TclError:
        return S(20), S(20)
    try:
        if main.state() == "normal" and main.winfo_viewable():
            mx, my = main.winfo_rootx(), main.winfo_rooty()
            mw, mh = main.winfo_width(), main.winfo_height()
            x = mx + mw + gap
            if x + w <= sw - S(8):
                return x, max(S(8), min(my, sh - h - S(48)))
            x = mx - w - gap
            if x >= S(8):
                return x, max(S(8), min(my, sh - h - S(48)))
            y = my + mh + gap
            if y + h <= sh - S(48):
                return max(S(8), min(mx, sw - w - S(8))), y
    except tk.TclError:
        pass
    return max(S(8), sw - w - S(48)), max(S(8), sh - h - S(80))


def show_window(win: tk.Tk) -> None:
    """把窗口显示并放到前台。"""
    win.deiconify()
    win.lift()
    try:
        win.attributes("-topmost", True)
        win.after(400, lambda: win.attributes("-topmost", False))
    except tk.TclError:
        pass
    try:
        import ctypes
        ctypes.windll.user32.SetForegroundWindow(int(win.wm_frame(), 16))
    except Exception:  # noqa: BLE001
        pass


def flash_taskbar(win: tk.Tk) -> None:
    """温和提醒：只闪烁任务栏图标，不抢焦点。"""
    try:
        import ctypes
        ctypes.windll.user32.FlashWindow(int(win.wm_frame(), 16), True)
    except Exception:  # noqa: BLE001
        pass


def enable_windows_integration(win: tk.Tk) -> None:
    """高 DPI 清晰渲染 + 独立任务栏图标。"""
    if sys.platform != "win32":
        return
    try:
        import ctypes
        try:
            ctypes.windll.shcore.SetProcessDpiAwareness(2)
        except (AttributeError, OSError):
            ctypes.windll.user32.SetProcessDPIAware()
        ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID(APP_ID)
    except Exception:  # noqa: BLE001
        pass


def _shell32():
    """带原型的 shell32（Shell_NotifyIconW 在 shell32，不在 user32）。"""
    import ctypes
    dll = ctypes.WinDLL("shell32", use_last_error=True)
    dll.Shell_NotifyIconW.restype = ctypes.c_bool
    dll.Shell_NotifyIconW.argtypes = [ctypes.c_uint, ctypes.c_void_p]
    return dll


# ---------------------------------------------------------------- 图形 --

def droplet_pieces(cx, cy, half_w, tip_y, bottom_y):
    """水滴由两块几何并集而成：上半部尖角 + 下半部正圆。"""
    r = half_w
    cy_circle = bottom_y - r
    left = []
    p0, p1, p2 = (cx, tip_y), (cx - r * 0.98, cy_circle - r * 0.55), (cx - r, cy_circle)
    for i in range(25):
        t = i / 24
        left.append(((1 - t) ** 2 * p0[0] + 2 * (1 - t) * t * p1[0] + t ** 2 * p2[0],
                     (1 - t) ** 2 * p0[1] + 2 * (1 - t) * t * p1[1] + t ** 2 * p2[1]))
    right = [(2 * cx - x, y) for x, y in reversed(left)]
    return [c for p in left + right for c in p], (cx - r, cy_circle - r, cx + r, cy_circle + r)


def draw_droplet(canvas, cx, cy, size, fill=PRIMARY, light="#A9CBFB"):
    """画一枚水滴（尖角 + 圆 + 高光）。"""
    half = size * 0.33
    cap, oval = droplet_pieces(cx, cy, half, cy - size * 0.50, cy + size * 0.50)
    canvas.create_polygon(cap, fill=fill, outline=fill, smooth=True)
    canvas.create_oval(*oval, fill=fill, outline="")
    canvas.create_oval(cx - half * 0.58, cy - size * 0.02, cx - half * 0.22,
                       cy + size * 0.24, fill=light, outline="")


def draw_droplet_wrapped(canvas, cx, cy, size, outer="#D9EAFF", inner=PRIMARY,
                         light="#9EC8FF"):
    """带浅色描边的水滴插图。"""
    half = size * 0.33
    tip, bottom = cy - size * 0.50, cy + size * 0.50
    cap, oval = droplet_pieces(cx, cy, half, tip, bottom)
    canvas.create_polygon(cap, fill=outer, outline=outer, smooth=True)
    canvas.create_oval(*oval, fill=outer, outline="")
    ih = half * 0.80
    cap2, oval2 = droplet_pieces(cx, cy + size * 0.015, ih,
                                 tip + size * 0.16, bottom - size * 0.09)
    canvas.create_polygon(cap2, fill=inner, outline=inner, smooth=True)
    canvas.create_oval(*oval2, fill=inner, outline="")
    canvas.create_oval(cx - half * 0.56, cy - size * 0.04, cx - half * 0.22,
                       cy + size * 0.22, fill=light, outline="")


def drop_coverage(px, py, size) -> float:
    """水滴覆盖度 0~1（用于光栅化托盘/窗口图标）。"""
    cx, cy = size * 0.5, size * 0.52
    half = size * 0.33
    tip, bottom = cy - size * 0.50, cy + size * 0.50
    cy_circle = bottom - half
    if py <= cy_circle:
        t = py - tip
        if t < 0:
            return 0.0
        edge = half * (t / (cy_circle - tip)) ** 1.35
        d = edge - abs(px - cx)
        if d <= 0:
            return 0.0
        return 1.0 if d > 0.7 else 0.55
    dist = math.hypot(px - cx, py - cy_circle)
    if dist > half:
        return 0.0
    return 1.0 if dist < half - 0.7 else 0.55


def _blur(mask, radius=1):
    h, w = len(mask), len(mask[0])
    out = [[0.0] * w for _ in range(h)]
    for y in range(h):
        for x in range(w):
            total = weight = 0.0
            for dy in (-radius, 0, radius):
                for dx in (-radius, 0, radius):
                    yy, xx = y + dy, x + dx
                    v = mask[yy][xx] if 0 <= yy < h and 0 <= xx < w else 0.0
                    wt_ = 1.0 if dx == 0 and dy == 0 else 0.5
                    total += v * wt_
                    weight += wt_
            out[y][x] = total / weight
    return out


def render_droplet_photo(size: int = 32, color=PRIMARY, highlight="#A9CBFB"):
    """把水滴渲染成 tk.PhotoImage（窗口/任务栏图标）。"""
    mask = _blur([[drop_coverage(x + 0.5, y + 0.5, size) for x in range(size)]
                  for y in range(size)], 1 if size <= 48 else 2)
    img = tk.PhotoImage(width=size, height=size)
    for y, row in enumerate(mask):
        for x, cov in enumerate(row):
            if cov <= 0.02:
                continue
            c = highlight if math.hypot(x + 0.5 - size * 0.40,
                                        y + 0.5 - size * 0.55) < size * 0.11 else color
            r, g, b = int(c[1:3], 16), int(c[3:5], 16), int(c[5:7], 16)
            r = int(r * cov + 255 * (1 - cov))
            g = int(g * cov + 255 * (1 - cov))
            b = int(b * cov + 255 * (1 - cov))
            img.put(f"#{r:02x}{g:02x}{b:02x}", (x, y))
    return img


# ---------------------------------------------------------------- 控件 --

class FitFrame(tk.Frame):
    """固定高度的容器（内部请求尺寸不影响父布局）。"""

    def __init__(self, master, height: int, **kw):
        super().__init__(master, height=height, **kw)
        self.pack_propagate(False)
        self.grid_propagate(False)


class RoundedButton(tk.Canvas):
    """圆角按钮：支持悬停、禁用、回车/空格触发。"""

    def __init__(self, master, text, command, *, variant="primary", height=40,
                 width=None, font=None, padx=None, icon=None, bg=CARD):
        self.variant, self.command = variant, command
        self.height = height
        self.font = font or tkfont.nametofont("TkDefaultFont")
        self.padx = padx if padx is not None else S(30)
        self.icon, self.text = icon, text
        self.bg = bg
        self._enabled = True
        self._hover = False
        self.icon_font = None
        w = width or self._measure() + self.padx * 2
        super().__init__(master, height=height, width=w, bg=bg, highlightthickness=0,
                         bd=0, cursor="hand2", takefocus=1)
        for seq, fn in (("<Enter>", self._enter), ("<Leave>", self._leave),
                        ("<ButtonRelease-1>", self._release),
                        ("<Key-space>", lambda e: self.invoke()),
                        ("<Return>", lambda e: self.invoke())):
            self.bind(seq, fn)
        self._draw()

    def _measure(self) -> int:
        w = self.font.measure(self.text)
        if self.icon:
            w += self.font.measure(self.icon) + S(6)
        return w

    def _draw(self):
        self.delete("all")
        w = max(int(self.cget("width")), self._measure() + self.padx * 2)
        self.configure(width=w)
        h, r = self.height, min(S(12), self.height // 2)
        if not self._enabled:
            fill, fg = P.DISABLED_BG, P.DISABLED_FG
        elif self.variant == "primary":
            fill, fg = (PRIMARY_DARK if self._hover else PRIMARY), "#FFFFFF"
        elif self.variant == "light":
            fill, fg = (P.BTN_LIGHT_HOVER if self._hover else P.BTN_LIGHT), PRIMARY_DARK
        elif self.variant == "amber":
            fill, fg = ("#E0911A" if self._hover else AMBER), "#FFFFFF"
        elif self.variant == "teal":
            fill, fg = ("#149C85" if self._hover else TEAL), "#FFFFFF"
        elif self.variant == "outline":
            fill, fg = (P.BTN_OUTLINE_HOVER if self._hover else P.BTN_OUTLINE), PRIMARY
        else:
            fill, fg = (P.BTN_SECONDARY if self._hover else TINT), PRIMARY
        outline = PRIMARY if (self.variant == "outline" and self._enabled) else fill
        self._round_rect(1, 1, w - 1, h - 1, r, fill, outline)
        cx = w // 2
        if self.icon:
            total = self._measure()
            x = cx - total // 2
            self.create_text(x, h // 2, text=self.icon, anchor="w", fill=fg,
                             font=self.icon_font or self.font)
            self.create_text(x + self.font.measure(self.icon) + S(6), h // 2,
                             text=self.text, anchor="w", fill=fg, font=self.font)
        else:
            self.create_text(cx, h // 2, text=self.text, fill=fg, font=self.font)

    def _round_rect(self, x1, y1, x2, y2, r, fill, outline=None):
        steps = 6
        pts = []
        for cx, cy, start in ((x2 - r, y1 + r, -90), (x2 - r, y2 - r, 0),
                              (x1 + r, y2 - r, 90), (x1 + r, y1 + r, 180)):
            for i in range(steps + 1):
                a = math.radians(start + 90 * i / steps)
                pts += [cx + r * math.cos(a), cy + r * math.sin(a)]
        edge = outline or fill
        self.create_polygon(pts, fill=fill, outline=edge,
                            width=S(2) if outline else 1, smooth=False)

    def _enter(self, _=None):
        self._hover = True
        self._draw()

    def _leave(self, _=None):
        self._hover = False
        self._draw()

    def _release(self, event):
        if self._enabled and 0 <= event.x <= self.winfo_width() and 0 <= event.y <= self.height:
            self.invoke()

    def set_text(self, text, icon=None):
        self.text = text
        if icon is not None:
            self.icon = icon
        self._draw()

    def set_enabled(self, enabled: bool):
        self._enabled = bool(enabled)
        try:
            self.configure(cursor="hand2" if enabled else "arrow")
        except tk.TclError:
            pass
        self._draw()

    def invoke(self):
        if self._enabled and self.command:
            try:
                self.command()
            except tk.TclError:
                pass


class DrinkFeedback(tk.Toplevel):
    """点「喝水」后的正向反馈小窗：绿色对勾 + 今日进度，淡出后消失。"""

    def __init__(self, master, done: int, goal: int):
        super().__init__(master)
        self.withdraw()
        self.overrideredirect(True)
        self.attributes("-topmost", True)
        self.configure(bg=TEAL)

        w, h = S(300), S(150)
        sw, sh = master.winfo_screenwidth(), master.winfo_screenheight()
        try:
            if master.winfo_viewable() and master.state() == "normal":
                x = master.winfo_rootx() + (master.winfo_width() - w) // 2
                y = max(S(20), master.winfo_rooty() + S(28))
            else:
                x, y = (sw - w) // 2, int(sh * 0.32)
        except tk.TclError:
            x, y = (sw - w) // 2, int(sh * 0.32)
        x = max(S(8), min(x, sw - w - S(8)))
        self.geometry(f"{w}x{h}+{x}+{y}")

        shell = tk.Frame(self, bg=CARD, highlightthickness=2, highlightbackground=TEAL)
        shell.pack(fill="both", expand=True)
        body = tk.Frame(shell, bg=CARD)
        body.pack(fill="both", expand=True)

        cn = pick_cn_family()
        f_big = tkfont.Font(family=cn, size=-FS(18), weight="bold")
        f_mid = tkfont.Font(family=cn, size=-FS(11))
        f_small = tkfont.Font(family=cn, size=-FS(9))

        cv = tk.Canvas(body, bg=CARD, height=S(44), highlightthickness=0)
        cv.pack(fill="x", pady=(S(6), 0))
        cx = w // 2
        r = S(18)
        cv.create_oval(cx - r, S(4), cx + r, S(4) + 2 * r, fill=TEAL, outline=TEAL)
        cv.create_line(cx - S(8), S(4) + r, cx - S(2), S(4) + r + S(6),
                       fill="#FFFFFF", width=S(4), capstyle="round")
        cv.create_line(cx - S(2), S(4) + r + S(6), cx + S(9), S(4) + r - S(7),
                       fill="#FFFFFF", width=S(4), capstyle="round")

        tk.Label(body, text=spaced("喝得好，继续保持"), font=f_big, fg=INK,
                 bg=CARD).pack(pady=(S(2), 0))
        tk.Label(body, text=f"今日 {done}/{goal} 杯", font=f_mid, fg=TEAL,
                 bg=CARD).pack(pady=(S(1), 0))
        tk.Label(body, text=("今日目标已达成！" if done >= goal else f"还差 {goal - done} 杯"),
                 font=f_small, fg=PRIMARY if done >= goal else MUTED,
                 bg=CARD).pack()

        self.deiconify()
        self.lift()
        self.after(1700, lambda: self._fade(0.95))

    def _fade(self, alpha: float):
        try:
            if alpha <= 0.05:
                self.destroy()
                return
            self.attributes("-alpha", alpha)
            self.after(40, lambda: self._fade(alpha - 0.12))
        except tk.TclError:
            pass


class Toast:
    """右下角轻提示，数秒后自动消失。"""

    _active = None

    def __init__(self, win: tk.Tk, text: str, kind="info", ms=2600):
        if Toast._active is not None:
            try:
                Toast._active.close()
            except tk.TclError:
                pass
        color = {"ok": TEAL, "warn": AMBER, "info": PRIMARY}.get(kind, PRIMARY)
        f = tkfont.Font(family=pick_cn_family(), size=-FS(12))
        w = min(S(380), f.measure(text) + S(48))
        h = S(52)
        x = win.winfo_screenwidth() - w - S(24)
        y = win.winfo_screenheight() - h - S(72)
        self.top = top = tk.Toplevel(win)
        top.overrideredirect(True)
        top.attributes("-topmost", True)
        top.geometry(f"{w}x{h}+{x}+{y}")
        cv = tk.Canvas(top, width=w, height=h, bg=CARD, highlightthickness=1,
                       highlightbackground=LINE)
        cv.pack()
        cv.create_oval(0, 0, S(8), S(8), fill=color, outline=color)
        cv.create_oval(0, h - S(8), S(8), h, fill=color, outline=color)
        cv.create_rectangle(0, S(4), S(8), h - S(4), fill=color, outline=color)
        cv.create_text(S(20), h // 2, text=text, anchor="w", fill=INK, font=f)
        Toast._active = self
        top.bind("<Button-1>", lambda e: self.close())
        win.after(ms, self.close)

    def close(self):
        try:
            self.top.destroy()
        except tk.TclError:
            pass
        if Toast._active is self:
            Toast._active = None


class Slider(tk.Canvas):
    """设置项滑杆：左侧标签、右侧 −/数值/+ 步进，下方可拖动轨道。"""

    PAD = 14
    LABEL_H = 30
    TRACK_Y = 46
    TICK_Y = 58
    HEIGHT = 78

    def __init__(self, master, label, lo, hi, step, value, on_drag, unit="",
                 on_step=None, step_size=None):
        self.lo, self.hi, self.step, self.unit = lo, hi, step, unit
        self.on_drag, self.on_step = on_drag, on_step
        self.step_size = step_size or step
        self.label = label
        self.width_px = S(330)
        super().__init__(master, width=self.width_px, height=S(self.HEIGHT), bg=CARD,
                         highlightthickness=0, bd=0, cursor="hand2")
        cn = pick_cn_family()
        self.f_label = tkfont.Font(family=cn, size=-FS(12))
        self.f_value = tkfont.Font(family=cn, size=-FS(14), weight="bold")
        self.f_btn = tkfont.Font(family=cn, size=-FS(15), weight="bold")
        self.f_tick = tkfont.Font(family=cn, size=-FS(9))
        self.value = int(value)
        self._drag = False
        self._last_w = 0
        self.bind("<Button-1>", self._press)
        self.bind("<B1-Motion>", self._move)
        self.bind("<ButtonRelease-1>", lambda e: setattr(self, "_drag", False))
        self.bind("<Configure>", self._on_resize)
        self._paint()

    def _on_resize(self, event):
        if event.width > 1 and abs(event.width - self._last_w) > 1:
            self.width_px, self._last_w = event.width, event.width
            self._paint()

    def _bounds(self):
        pad = S(self.PAD)
        return pad, max(pad + S(10), self.width_px - pad)

    def _x_of(self, value):
        x1, x2 = self._bounds()
        return x1 + (value - self.lo) / (self.hi - self.lo) * (x2 - x1)

    def _value_of(self, x):
        x1, x2 = self._bounds()
        ratio = (min(max(x, x1), x2) - x1) / max(1, x2 - x1)
        return int(round((self.lo + ratio * (self.hi - self.lo)) / self.step) * self.step)

    def _boxes(self):
        size = S(28)
        gap = S(10)
        y = S(self.LABEL_H // 2 - 14)
        right = self.width_px - S(self.PAD)
        plus = (right - size, y, right, y + size)
        minus = (plus[0] - gap - size, y, plus[0] - gap, y + size)
        text_x2 = minus[0] - gap
        text_w = max(self.f_value.measure(f"{self.value}{self.unit}"),
                     self.f_value.measure(f"{self.hi}{self.unit}")) + S(8)
        return minus, (text_x2 - text_w, text_x2), plus

    def _press(self, e):
        minus, _text, plus = self._boxes()
        for box, delta in ((minus, -self.step_size), (plus, self.step_size)):
            x1, y1, x2, y2 = box
            if x1 <= e.x <= x2 and y1 <= e.y <= y2:
                self.nudge(delta)
                return
        if e.y < S(self.LABEL_H - 6):
            return
        self._drag = True
        self.set(self._value_of(e.x))
        if self.on_drag:
            self.on_drag(self.value)

    def _move(self, e):
        if not self._drag:
            return
        v = self._value_of(e.x)
        if v != self.value:
            self.value = v
            self._paint()
            if self.on_drag:
                self.on_drag(self.value)

    def nudge(self, delta):
        new = max(self.lo, min(self.hi, self.value + delta))
        if new != self.value:
            self.value = new
            self._paint()
            if self.on_step:
                self.on_step(self.value)
            elif self.on_drag:
                self.on_drag(self.value)

    def set(self, value):
        self.value = max(self.lo, min(self.hi, int(value)))
        self._paint()

    def _paint(self):
        self.delete("all")
        x1, x2 = self._bounds()
        minus, _text, plus = self._boxes()
        text_x2 = minus[0] - S(10)
        self.create_text(x1 - S(4), S(self.LABEL_H // 2), text=self.label, anchor="w",
                         fill=INK, font=self.f_label)
        for box, glyph in ((minus, "−"), (plus, "+")):
            bx1, by1, bx2, by2 = box
            self.create_polygon(self._rr_points(bx1, by1, bx2, by2, S(8)), fill=SOFT,
                                outline="#D7E4F7", smooth=False)
            self.create_text((bx1 + bx2) // 2, (by1 + by2) // 2, text=glyph,
                             fill=PRIMARY_DARK, font=self.f_btn)
        self.create_text(text_x2, S(self.LABEL_H // 2), text=f"{self.value}{self.unit}",
                         anchor="e", fill=PRIMARY, font=self.f_value)
        ty = S(self.TRACK_Y)
        self.create_line(x1, ty, x2, ty, fill="#E7EEF8", width=S(8), capstyle="round")
        xv = self._x_of(self.value)
        if xv > x1 + 1:
            self.create_line(x1, ty, xv, ty, fill=PRIMARY, width=S(8), capstyle="round")
        self.create_text(x1, S(self.TICK_Y), text=str(self.lo), anchor="n",
                         fill=P.FAINT, font=self.f_tick)
        self.create_text(x2, S(self.TICK_Y), text=str(self.hi), anchor="n",
                         fill=P.FAINT, font=self.f_tick)
        r = S(10)
        self.create_oval(xv - r, ty - r, xv + r, ty + r, fill="#FFFFFF", outline=PRIMARY,
                         width=S(3))

    @staticmethod
    def _rr_points(x1, y1, x2, y2, r):
        pts = []
        for cx, cy, start in ((x2 - r, y1 + r, -90), (x2 - r, y2 - r, 0),
                              (x1 + r, y2 - r, 90), (x1 + r, y1 + r, 180)):
            for i in range(5):
                a = math.radians(start + 90 * i / 4)
                pts += [cx + r * math.cos(a), cy + r * math.sin(a)]
        return pts


class Switch(tk.Canvas):
    """iOS 风格开关：左侧标题 + 说明，右侧开关。"""

    def __init__(self, master, value, on_change, *, title, desc="", width=None):
        cn = pick_cn_family()
        self.f_title = tkfont.Font(family=cn, size=-FS(13), weight="bold")
        self.f_desc = tkfont.Font(family=cn, size=-FS(11))
        self.w = width or S(352)
        self.h = S(58) if desc else S(34)
        super().__init__(master, width=self.w, height=self.h, bg=CARD, highlightthickness=0,
                         bd=0, cursor="hand2")
        self.on_change = on_change
        self.title, self.desc = title, desc
        self.value = bool(value)
        self._last_w = 0
        self.bind("<Button-1>", lambda e: self.toggle())
        self.bind("<Configure>", self._on_resize)
        self._paint()

    def _on_resize(self, event):
        if event.width > 1 and abs(event.width - self._last_w) > 1:
            self.w, self._last_w = event.width, event.width
            self._paint()

    @property
    def sw(self):
        return S(72) if self.desc else S(68)

    def _paint(self):
        self.delete("all")
        usable = max(S(80), self.w - self.sw - S(14))
        if self.desc:
            title_h = self.f_title.metrics("linespace")
            self.create_text(0, S(2), text=self.title, anchor="nw", fill=INK,
                             font=self.f_title)
            lines = wrap_paragraph(self.desc, usable, self.f_desc).split("\n")[:2]
            self.create_text(0, S(2) + title_h + S(4), anchor="nw", fill=MUTED,
                             font=self.f_desc, text="\n".join(lines))
        else:
            self.create_text(0, self.h // 2, text=self.title, anchor="w", fill=INK,
                             font=self.f_title)
        tw, th = S(46), S(24)
        x1 = self.w - tw
        y1 = (self.h - th) // 2
        track = PRIMARY if self.value else P.OFF
        self.create_oval(x1, y1, x1 + th, y1 + th, fill=track, outline=track)
        self.create_oval(x1 + tw - th, y1, x1 + tw, y1 + th, fill=track, outline=track)
        self.create_rectangle(x1 + th / 2, y1, x1 + tw - th / 2, y1 + th, fill=track,
                              outline="")
        kr = S(20)
        kx = x1 + tw - kr - S(2) if self.value else x1 + S(2)
        self.create_oval(kx, y1 + S(2), kx + kr, y1 + kr + S(2), fill="#FFFFFF", outline="")

    def toggle(self):
        self.value = not self.value
        self._paint()
        if self.on_change:
            self.on_change(self.value)

    def set_value(self, value):
        self.value = bool(value)
        self._paint()


# ---------------------------------------------------------------- 主程序 --

class WaterReminderApp:
    def __init__(self):
        self.cfg = load_config()
        set_palette(self.cfg.get("theme", "light"))
        self.paused_left = self.cfg["interval_min"] * 60
        self.next_due = time.time() + self.cfg["interval_min"] * 60
        self.popup = None
        self.drink_dialog = None
        self.profile_dialog = None
        self.tray = None
        self.hotkeys = None
        self.minimized = False
        self._tray_hinted = False
        self._goal_done_ui = False
        self._goal_forced = False
        self._last_sec = None
        self._last_drink_ts = 0.0
        # 托盘等后台线程只往队列投递 UI 动作，由主线程在 _tick 中执行
        self.ui_queue: "queue.Queue" = queue.Queue()

        self.win = tk.Tk()
        enable_windows_integration(self.win)
        global _scale
        _scale = detect_scale(self.win)
        self.F = make_fonts(_scale)
        tkfont.nametofont("TkDefaultFont").configure(family=pick_cn_family(), size=-FS(12))

        self.win.title(APP_NAME)
        self.win.configure(bg=BG)
        sw, sh = self.win.winfo_screenwidth(), self.win.winfo_screenheight()
        self.size_w = max(S(500), int(sw * 0.46))
        self.size_h = max(S(700), int(sh * 0.86))
        x = max(S(20), (sw - self.size_w) // 2)
        y = max(S(20), (sh - self.size_h) // 2 - S(24))
        self.win.geometry(f"{self.size_w}x{self.size_h}+{x}+{y}")
        self.win.minsize(S(430), S(520))
        self.win.protocol("WM_DELETE_WINDOW", self.on_close)
        self.win.bind("<Unmap>", self._on_unmap)
        self.win.bind("<Map>", self._on_map)
        self._set_icon()

        self._roll_day()
        self._build_ui()
        if self.cfg.get("hotkey", True):
            self.hotkeys = GlobalHotkeys(self)
        self._tick()

    # ------------------------------------------------------------ 构建 --
    def _set_icon(self):
        try:
            self._icon_ref = render_droplet_photo(32)
            self.win.iconphoto(True, self._icon_ref)
        except tk.TclError:
            pass

    def _on_wheel(self, event):
        """主窗口滚轮。"""
        first, last = self.canvas.yview()
        if (first <= 0.0 and event.delta > 0) or (last >= 1.0 and event.delta < 0):
            return
        self.canvas.yview_scroll(-1 if event.delta > 0 else 1, "units")

    def _section(self, parent, text, pady=(S(12), S(5))):
        tk.Label(parent, text=spaced(text), font=self.F["section"], fg=MUTED,
                 bg=BG).pack(anchor="w", padx=S(22), pady=pady)

    def _card(self, parent):
        outer = tk.Frame(parent, bg=LINE)
        outer.pack(fill="x", padx=S(18), pady=(0, S(2)))
        inner = tk.Frame(outer, bg=CARD)
        inner.pack(fill="both", expand=True, padx=1, pady=1)
        return inner

    def _soft_card(self, parent):
        outer = tk.Frame(parent, bg=P.SOFT_EDGE)
        outer.pack(fill="x", padx=S(18), pady=(0, S(2)))
        inner = tk.Frame(outer, bg=SOFT)
        inner.pack(fill="both", expand=True, padx=1, pady=1)
        return inner

    def _build_ui(self):
        F = self.F
        page = tk.Frame(self.win, bg=BG)
        page.pack(fill="both", expand=True)
        self.page = page

        # ---- 顶部横幅 ----
        banner = FitFrame(page, height=S(78), bg=PRIMARY)
        banner.pack(fill="x")
        left = tk.Frame(banner, bg=PRIMARY)
        left.pack(side="left", padx=(S(20), 0))
        logo = tk.Canvas(left, width=S(40), height=S(48), bg=PRIMARY, highlightthickness=0)
        logo.pack(side="left")
        draw_droplet(logo, S(20), S(24), S(34), fill="#FFFFFF", light="#BCD9FF")
        titles = tk.Frame(left, bg=PRIMARY)
        titles.pack(side="left", padx=(S(6), 0))
        tk.Label(titles, text=spaced(APP_NAME), font=F["app"], fg="#FFFFFF",
                 bg=PRIMARY).pack(anchor="w")
        self.status_label = tk.Label(titles, text="", font=F["status"], fg="#D5E6FF",
                                     bg=PRIMARY)
        self.status_label.pack(anchor="w", pady=(S(1), 0))

        right = FitFrame(banner, width=S(120), height=S(78), bg=PRIMARY)
        right.pack(side="right", padx=(0, S(18)))
        actions = tk.Frame(right, bg=PRIMARY)
        actions.pack(side="right", pady=(S(23), 0))
        self.btn_toggle = RoundedButton(actions, "暂停", self.toggle_run, variant="light",
                                        height=S(32), padx=S(22), font=F["btn_small"],
                                        bg=PRIMARY)
        self.btn_toggle.pack()

        # ---- 可滚动区域 ----
        holder = tk.Frame(page, bg=BG)
        holder.pack(fill="both", expand=True)
        self.canvas = tk.Canvas(holder, bg=BG, highlightthickness=0, bd=0)
        self.canvas.pack(fill="both", expand=True, padx=1)
        content = tk.Frame(self.canvas, bg=BG)
        self._content_id = self.canvas.create_window((0, 0), window=content, anchor="nw")
        content.bind("<Configure>",
                     lambda e: self.canvas.configure(scrollregion=self.canvas.bbox("all")))
        self.canvas.bind("<Configure>",
                         lambda e: self.canvas.itemconfigure(self._content_id, width=e.width))
        # 滚轮只在主窗口范围内生效（不用 bind_all，避免被其它窗口覆盖）
        self.win.bind("<MouseWheel>", self._on_wheel, add="+")
        self.canvas.bind("<MouseWheel>", self._on_wheel, add="+")
        content.bind("<MouseWheel>", self._on_wheel, add="+")

        # ---- 倒计时卡片 ----
        self._section(content, "下一次提醒", pady=(S(10), S(5)))
        card = self._soft_card(content)
        body = tk.Frame(card, bg=SOFT)
        body.pack(fill="x", padx=S(18), pady=(S(12), S(12)))
        self.time_label = tk.Label(body, text="--:--", font=F["num_big"], fg=INK, bg=SOFT)
        self.time_label.pack()
        self.time_sub = tk.Label(body, text="", font=F["small"], fg=MUTED, bg=SOFT)
        self.time_sub.pack(pady=(S(2), 0))
        self.progress = tk.Canvas(card, height=S(10), bg=SOFT, highlightthickness=0, bd=0)
        self.progress.pack(fill="x", padx=S(18), pady=(S(6), 0))
        self.progress.bind("<Configure>", lambda e: self._draw_progress())
        self.goal_line = tk.Label(card, text="", font=F["small"], fg=MUTED, bg=SOFT)
        self.goal_line.pack(pady=(S(10), 0))
        row = tk.Frame(card, bg=SOFT)
        row.pack(pady=(S(14), S(16)))
        self.btn_drink_main = RoundedButton(row, "喝水", self.drink, variant="primary",
                                            height=S(46), padx=S(26), icon="💧",
                                            font=F["btn"], bg=SOFT)
        self.btn_drink_main.pack(side="left", padx=S(4))
        RoundedButton(row, "喝饮料", self.open_drink_dialog, variant="amber", height=S(46),
                      padx=S(24), icon="🥤", font=F["btn"], bg=SOFT).pack(side="left", padx=S(4))
        RoundedButton(row, "稍后", self.snooze, variant="outline", height=S(46),
                      padx=S(20), font=F["btn"], bg=SOFT).pack(side="left", padx=S(4))

        # ---- 今日数据 ----
        self._section(content, "今日数据")
        stats = self._card(content)
        grid = tk.Frame(stats, bg=CARD)
        grid.pack(fill="x", pady=S(8))
        self.stat_values = {}
        cells = (("cups", "喝水 / 目标"), ("sugar", "今日糖分"), ("rate", "执行率"),
                 ("streak", "连续达标"))
        for i, (key, text) in enumerate(cells):
            row_i, col = divmod(i, 2)
            cell = tk.Frame(grid, bg=CARD)
            cell.grid(row=row_i, column=col, sticky="nsew", pady=S(7))
            grid.columnconfigure(col, weight=1, uniform="stat")
            num = tk.Label(cell, text="–", font=F["num_md"], fg=INK, bg=CARD)
            num.pack()
            tk.Label(cell, text=text, font=F["small"], fg=MUTED, bg=CARD).pack(
                pady=(S(1), 0))
            self.stat_values[key] = num
        tk.Frame(grid, bg=LINE, width=1).grid(row=0, column=0, columnspan=2, sticky="e",
                                              pady=S(6))
        tk.Frame(grid, bg=LINE, width=1).grid(row=1, column=0, columnspan=2, sticky="e",
                                              pady=S(6))
        tk.Frame(grid, bg=LINE, height=1).grid(row=0, column=0, columnspan=2, sticky="sw",
                                               padx=S(14))
        # 手动修正
        tk.Frame(stats, bg=LINE, height=1).pack(fill="x")
        tools = tk.Frame(stats, bg=CARD)
        tools.pack(fill="x", padx=S(12), pady=S(6))
        tk.Label(tools, text="记录有误？", font=F["tiny"], fg=MUTED, bg=CARD).pack(side="left")
        RoundedButton(tools, "重置今日", self.reset_water, variant="secondary",
                      height=S(30), padx=S(12), font=F["tiny"]).pack(side="right")
        self.btn_minus = RoundedButton(tools, "现在不喝 (−1)", self.minus_water,
                                       variant="secondary", height=S(30), padx=S(10),
                                       font=F["tiny"])
        self.btn_minus.pack(side="right", padx=S(6))

        # ---- 专属饮水建议 ----
        self._section(content, "专属饮水建议")
        advice_card = self._card(content)
        a_head = tk.Frame(advice_card, bg=CARD)
        a_head.pack(fill="x", padx=S(16), pady=(S(12), S(2)))
        self.advice_badge = tk.Label(a_head, text="", font=F["tiny"], fg="#FFFFFF", bg=TEAL)
        self.advice_badge.pack(side="right")
        self.advice_num = tk.Label(a_head, text="", font=F["num"], fg=PRIMARY, bg=CARD)
        self.advice_num.pack(anchor="w")
        self.advice_cups = tk.Label(advice_card, text="", font=F["small"], fg=MUTED, bg=CARD)
        self.advice_cups.pack(anchor="w", padx=S(16))
        self.advice_detail = tk.Label(advice_card, text="", font=F["tiny"], fg=MUTED,
                                      bg=CARD, justify="left", anchor="w")
        self.advice_detail.pack(fill="x", padx=S(16), pady=(S(8), 0))
        self.advice_note = tk.Label(advice_card, text=ADVICE_DISCLAIMER, font=F["tiny"],
                                    fg=P.FAINT, bg=CARD, justify="left", anchor="w")
        self.advice_note.pack(fill="x", padx=S(16), pady=(S(4), 0))
        self.advice_detail.bind("<Configure>", self._wrap_advice)
        self.advice_note.bind("<Configure>", self._wrap_advice)
        a_row = tk.Frame(advice_card, bg=CARD)
        a_row.pack(fill="x", padx=S(16), pady=(S(10), S(13)))
        RoundedButton(a_row, "填写身体情况", self.open_profile_dialog, variant="secondary",
                      height=S(38), padx=S(14), font=F["small"]).pack(side="left")
        self.btn_apply_advice = RoundedButton(a_row, "应用为目标", self.apply_advice,
                                              variant="teal", height=S(38), padx=S(16),
                                              font=F["small"])
        self.btn_apply_advice.pack(side="right")

        # ---- 周 / 月累计 ----
        self._section(content, "累计喝水")
        period = self._card(content)
        pgrid = tk.Frame(period, bg=CARD)
        pgrid.pack(fill="x", pady=S(10))
        self.period_values = {}
        for i, (key, title, hint) in enumerate((("week", "本周", "周一至今"),
                                                ("month", "本月", "本月 1 号至今"))):
            if i:
                tk.Frame(pgrid, bg=LINE, width=1).grid(row=0, column=1, sticky="ns", pady=S(4))
            cell = tk.Frame(pgrid, bg=CARD)
            cell.grid(row=0, column=i * 2, sticky="nsew")
            pgrid.columnconfigure(i * 2, weight=1)
            tk.Label(cell, text=title, font=F["small"], fg=MUTED, bg=CARD).pack()
            num = tk.Label(cell, text="0 杯", font=F["num"], fg=INK, bg=CARD)
            num.pack(pady=(S(1), 0))
            tk.Label(cell, text=hint, font=F["tiny"], fg=P.FAINT, bg=CARD).pack()
            self.period_values[key] = num
        tk.Label(period, text="每周一 / 每月 1 号自动重新统计，无需手动清零",
                 font=F["tiny"], fg=P.FAINT, bg=CARD).pack(pady=(0, S(10)))

        # ---- 数据看板（热力图 + 周趋势）----
        self._section(content, "数据看板")
        dash = self._card(content)
        dhead = tk.Frame(dash, bg=CARD)
        dhead.pack(fill="x", padx=S(16), pady=(S(12), S(2)))
        tk.Label(dhead, text="近 12 周饮水热力图", font=F["sw_title"], fg=INK,
                 bg=CARD).pack(side="left")
        self.heat_summary = tk.Label(dhead, text="", font=F["tiny"], fg=P.FAINT, bg=CARD)
        self.heat_summary.pack(side="right")
        self.heat_canvas = tk.Canvas(dash, height=S(128), bg=CARD, highlightthickness=0,
                                     bd=0)
        self.heat_canvas.pack(fill="x", padx=S(16), pady=(S(4), 0))
        self.heat_canvas.bind("<Configure>", lambda e: self._draw_heatmap())
        # 图例
        legend = tk.Frame(dash, bg=CARD)
        legend.pack(fill="x", padx=S(16), pady=(S(2), S(6)))
        tk.Label(legend, text="少", font=F["tiny"], fg=P.FAINT, bg=CARD).pack(side="left")
        for lvl in range(4):
            box = tk.Frame(legend, bg=(P.HEAT_0, P.HEAT_1, P.HEAT_2, P.HEAT_3)[lvl],
                           width=S(13), height=S(13))
            box.pack(side="left", padx=1)
            box.pack_propagate(False)
        tk.Label(legend, text="多 / 达标", font=F["tiny"], fg=P.FAINT, bg=CARD).pack(
            side="left", padx=(S(3), 0))
        tk.Frame(dash, bg=P.LINE, height=1).pack(fill="x", padx=S(16), pady=(S(4), S(4)))
        self.trend_canvas = tk.Canvas(dash, height=S(132), bg=CARD, highlightthickness=0,
                                      bd=0)
        self.trend_canvas.pack(fill="x", padx=S(16), pady=(0, S(6)))
        self.trend_canvas.bind("<Configure>", lambda e: self._draw_trend())
        self.trend_note = tk.Label(dash, text="", font=F["tiny"], fg=P.FAINT, bg=CARD,
                                   anchor="w", justify="left")
        self.trend_note.pack(fill="x", padx=S(16), pady=(0, S(12)))

        # ---- 饮料与糖分 ----
        self._section(content, "饮料与糖分")
        sugar_card = self._card(content)
        head = tk.Frame(sugar_card, bg=CARD)
        head.pack(fill="x", padx=S(16), pady=(S(12), S(4)))
        tk.Label(head, text="昨日饮料糖分", font=F["sw_title"], fg=INK,
                 bg=CARD).pack(side="left")
        self.sugar_tag = tk.Label(head, text="", font=F["tiny"], bg=TEAL, fg="#FFFFFF")
        self.sugar_tag.pack(side="right")
        self.sugar_value = tk.Label(sugar_card, text="", font=F["num"], fg=INK, bg=CARD)
        self.sugar_value.pack(anchor="w", padx=S(16))
        self.sugar_bar = tk.Canvas(sugar_card, height=S(10), bg=CARD, highlightthickness=0,
                                   bd=0)
        self.sugar_bar.pack(fill="x", padx=S(16), pady=(S(2), 0))
        self.sugar_bar.bind("<Configure>", lambda e: self._draw_sugar_bar())
        self.sugar_advice = tk.Label(sugar_card, text="", font=F["small"], fg=MUTED,
                                     bg=CARD, justify="left", anchor="w")
        self.sugar_advice.pack(fill="x", padx=S(16), pady=(S(10), S(5)))
        self.sugar_meta = tk.Label(sugar_card, text="", font=F["tiny"], fg=P.FAINT,
                                   bg=CARD, justify="left", anchor="w")
        self.sugar_meta.pack(fill="x", padx=S(16), pady=(0, S(13)))
        self.sugar_advice.bind("<Configure>", self._wrap_sugar_labels)
        self.sugar_meta.bind("<Configure>", self._wrap_sugar_labels)

        # ---- 今日记录 ----
        self._section(content, "今日记录")
        tl_card = self._card(content)
        self.timeline = tk.Frame(tl_card, bg=CARD)
        self.timeline.pack(fill="x", padx=S(16), pady=S(10))

        # ---- 提醒设置 ----
        self._section(content, "提醒设置")
        set_card = self._card(content)
        sbody = tk.Frame(set_card, bg=CARD)
        sbody.pack(fill="x", padx=S(16), pady=(S(8), S(10)))
        self.sl_interval = Slider(sbody, "提醒间隔", INTERVAL_MIN, INTERVAL_MAX, 5,
                                  self.cfg["interval_min"], self.on_interval, " 分钟",
                                  on_step=self.on_interval, step_size=5)
        self.sl_interval.pack(fill="x")
        tk.Frame(sbody, bg=LINE, height=1).pack(fill="x", pady=(S(4), S(4)))
        self.sl_goal = Slider(sbody, "每日目标", GOAL_MIN, GOAL_MAX, 1, self.cfg["goal"],
                              self.on_goal, " 杯", on_step=self.on_goal, step_size=1)
        self.sl_goal.pack(fill="x")
        tk.Frame(sbody, bg=LINE, height=1).pack(fill="x", pady=(S(6), S(10)))
        self.sw_gentle = Switch(sbody, self.cfg["gentle"], self.on_gentle, title="温和提醒",
                                desc="到点只闪烁任务栏，不打断你手上的工作")
        self.sw_gentle.pack(fill="x", pady=(0, S(10)))
        tk.Frame(sbody, bg=P.DIVIDER, height=1).pack(fill="x", pady=(0, S(10)))
        self.sw_autostart = Switch(sbody, self.cfg["autostart"], self.on_autostart,
                                   title="开机自动启动",
                                   desc="登录 Windows 后自动在后台开始提醒")
        self.sw_autostart.pack(fill="x")
        tk.Frame(sbody, bg=P.DIVIDER, height=1).pack(fill="x", pady=(S(6), S(6)))
        self.sw_dark = Switch(sbody, self.cfg.get("theme") == "dark", self.on_theme,
                              title="深色模式",
                              desc="夜间或低光环境下更护眼")
        self.sw_dark.pack(fill="x", pady=(0, S(10)))
        self.sw_hotkey = Switch(sbody, self.cfg.get("hotkey", True), self.on_hotkey,
                                title="全局快捷键",
                                desc="Ctrl+Alt+W 记一杯 · Ctrl+Alt+P 暂停/继续")
        self.sw_hotkey.pack(fill="x")

        # ---- 提醒语 ----
        self._section(content, "提醒语")
        quote_card = self._card(content)
        self.quote_box = tk.Entry(quote_card, font=F["body"], fg=INK, bg=SOFT, relief="flat",
                                  bd=0, insertbackground=PRIMARY, highlightthickness=1,
                                  highlightbackground=LINE, highlightcolor=PRIMARY)
        self.quote_box.pack(fill="x", padx=S(12), pady=(S(10), S(8)), ipady=S(7))
        self.quote_box.insert(0, random.choice(self.cfg["quotes"]))
        self.quote_box.bind("<Return>", lambda e: self.add_quote())
        qrow = tk.Frame(quote_card, bg=CARD)
        qrow.pack(fill="x", padx=S(12), pady=(0, S(10)))
        tk.Label(qrow, text="换一条看看", font=F["tiny"], fg=MUTED, bg=CARD).pack(side="left")
        RoundedButton(qrow, "换一条", self.shuffle_quote, variant="secondary", height=S(30),
                      padx=S(14), font=F["small"]).pack(side="right", padx=(S(6), 0))
        RoundedButton(qrow, "加入轮播", self.add_quote, variant="secondary", height=S(30),
                      padx=S(14), font=F["small"]).pack(side="right")
        self.quotes_label = tk.Label(quote_card, text="", font=F["tiny"], fg=MUTED, bg=CARD,
                                     justify="left", anchor="w")
        self.quotes_label.pack(fill="x", padx=S(12), pady=(S(4), S(13)))

        tk.Label(content, text=f"{APP_NAME} v{VERSION} · 设置与数据保存在同目录 config.json",
                 font=F["tiny"], fg=P.FAINT, bg=BG).pack(pady=(S(10), S(14)))

        self.refresh_all()

    # ------------------------------------------------------------ 数据 --
    @staticmethod
    def _day_key(d: "date | None" = None) -> str:
        return (d or date.today()).isoformat()

    def _log(self) -> dict:
        return self.cfg["data"]["log"]

    def _get_day(self, key: str, create=False) -> dict:
        rec = self._log().get(key)
        if rec is None:
            rec = {"water": 0, "sugar": 0.0, "ml": 0.0, "drinks": 0, "drink_list": []}
            if create:
                self._log()[key] = rec
        rec.setdefault("drink_list", [])
        return rec

    def _today_water(self) -> int:
        day = self._day_key()
        base = int(self._get_day(day).get("water", 0))
        return max(0, base + int(self.cfg["data"]["water_fix"].get(day, 0)))

    def _today_done(self) -> int:
        return self._today_water()

    def _week_keys(self) -> list:
        today = date.today()
        monday = date.fromordinal(today.toordinal() - today.weekday())
        return [self._day_key(date.fromordinal(monday.toordinal() + i)) for i in range(7)]

    def _month_keys(self) -> list:
        first = date.today().replace(day=1)
        nxt = date.fromordinal(first.toordinal() + 31).replace(day=1)
        days = (nxt - first).days
        return [self._day_key(date.fromordinal(first.toordinal() + i)) for i in range(days)]

    def _sum_metric(self, keys, field) -> float:
        log = self._log()
        fix = self.cfg["data"].get("water_fix", {})
        total = 0.0
        for k in keys:
            rec = log.get(k)
            if rec:
                total += float(rec.get(field, 0) or 0)
            if field == "water":
                total += float(fix.get(k, 0) or 0)
        return total

    def week_cups(self) -> int:
        return int(max(0, round(self._sum_metric(self._week_keys(), "water"))))

    def month_cups(self) -> int:
        return int(max(0, round(self._sum_metric(self._month_keys(), "water"))))

    def yesterday_key(self) -> str:
        return self._day_key(date.fromordinal(date.today().toordinal() - 1))

    def yesterday_sugar(self) -> float:
        return round(float(self._get_day(self.yesterday_key()).get("sugar", 0) or 0), 1)

    def sugar_limit(self) -> float:
        return recommended_sugar(self.cfg["kcal_per_day"], self.cfg["sugar_ratio"])

    def _roll_day(self):
        """新的一天：归档旧日、清理过期明细，并重置计时与达标状态。"""
        today = self._day_key()
        data = self.cfg["data"]
        if data.get("day") == today:
            return
        old_day = data.get("day")
        if old_day:
            # 以当天明细 + 修正量为准，避免 done 字段与日志不一致时归档错数
            rec = self._get_day(old_day)
            fix = data.get("water_fix", {})
            done = max(0, int(rec.get("water", 0))
                       + int(fix.get(old_day, 0) if isinstance(fix, dict) else 0))
            data["history"][old_day] = {
                "done": done, "goal": self.cfg["goal"],
                "achieved": done >= self.cfg["goal"]}
            for old in sorted(data["history"])[:-LOG_KEEP_DAYS]:
                data["history"].pop(old, None)
        data.update({"day": today, "done": 0, "skipped": 0, "events": []})
        keep = {self._day_key(date.fromordinal(date.today().toordinal() - i))
                for i in range(LOG_KEEP_DAYS)}
        for key in [k for k in self._log() if k not in keep]:
            self._log().pop(key, None)
        for key in [k for k in data["water_fix"] if k not in keep]:
            data["water_fix"].pop(key, None)
        # 「重新开始」的强制状态不能跨天残留，否则次日达标后不再停表
        self._goal_forced = False
        self._goal_done_ui = False
        # 午夜后重新排定下一次提醒，避免用过期的 next_due 立刻弹窗
        if self.next_due is not None:
            self._schedule_next()
        else:
            self.paused_left = self.cfg["interval_min"] * 60
            self._last_sec = None
        self._save()

    def record_water(self, cups: int = 1, log_cup: bool = True) -> None:
        """记录喝水：今日 / 本周 / 本月同时 +cups。

        同时在 cup_log 里追加「水」记录（含糖量 0），
        这样「现在不喝」能按顺序准确回退每一杯及其糖分。
        log_cup=False 供「喝饮料」调用：饮料自己会写一条带糖的杯记录。
        """
        self._roll_day()
        rec = self._get_day(self._day_key(), create=True)
        cups = max(0, int(cups))
        rec["water"] = int(rec.get("water", 0)) + cups
        rec["ml"] = float(rec.get("ml", 0) or 0) + cups * ML_PER_CUP
        if log_cup:
            for _ in range(cups):
                rec.setdefault("cup_log", []).append(
                    {"k": "water", "t": datetime.now().strftime("%H:%M"), "sugar": 0.0,
                     "ml": ML_PER_CUP})
            del rec["cup_log"][:-120]
        self.cfg["data"]["done"] = self._today_water()

    def add_drink(self, name: str, volume_ml: float, sugar_g: float,
                  sugar_per_100: float | None = None) -> None:
        """记录一杯饮料（实际摄入糖量 + 每 100ml 含糖量用于展示）。"""
        self._roll_day()
        rec = self._get_day(self._day_key(), create=True)
        rec["sugar"] = round(float(rec.get("sugar", 0) or 0) + max(0.0, sugar_g), 1)
        rec["ml"] = float(rec.get("ml", 0) or 0) + max(0.0, volume_ml)
        rec["drinks"] = int(rec.get("drinks", 0)) + 1
        per100 = (sugar_per_100 if sugar_per_100 is not None
                  else (sugar_g / volume_ml * 100.0 if volume_ml > 0 else 0.0))
        rec["drink_list"].append({"t": datetime.now().strftime("%H:%M"),
                                  "name": (name or "饮料")[:20],
                                  "ml": round(volume_ml, 1),
                                  "sugar": round(sugar_g, 1),
                                  "per100": round(per100, 1)})
        del rec["drink_list"][:-60]
        # 同步记入「杯」日志（这是减杯时用来回退糖分的依据）
        rec.setdefault("cup_log", []).append(
            {"k": "drink", "t": datetime.now().strftime("%H:%M"),
             "sugar": round(sugar_g, 1), "ml": round(volume_ml, 1),
             "name": (name or "饮料")[:20]})
        del rec["cup_log"][:-120]

    def last_cup_sugar(self) -> float:
        """最近一杯对应的含糖量（水为 0；饮料为其糖克数）。

        没有 cup_log 的旧数据时，退回「今天有饮料且杯数>0 就取最后一杯饮料的糖」。
        """
        rec = self._get_day(self._day_key())
        cup_log = rec.get("cup_log") or []
        if cup_log:
            return float(cup_log[-1].get("sugar", 0) or 0)
        drink_list = rec.get("drink_list") or []
        if drink_list and self._today_water() > 0:
            return float(drink_list[-1].get("sugar", 0) or 0)
        return 0.0

    def today_sugar(self) -> float:
        return round(float(self._get_day(self._day_key()).get("sugar", 0) or 0), 1)

    def today_drinks(self) -> int:
        return int(self._get_day(self._day_key()).get("drinks", 0))

    def adjust_water(self, delta: int) -> float:
        """手动修正今天杯数（只影响今天）。减杯时一并扣掉该杯的糖分，返回扣掉的糖。"""
        self._roll_day()
        day = self._day_key()
        rec = self._get_day(day, create=True)
        base = int(rec.get("water", 0))
        # 先记录修正前的「有效杯数」，减杯会在下面把日志里的杯数一起扣掉
        before = self._today_water()
        removed_sugar = 0.0
        if delta < 0:
            for _ in range(min(-int(delta), before)):
                removed_sugar += self._pop_last_cup(rec)
        target = max(0, before + int(delta))
        fix = self.cfg["data"]["water_fix"]
        if target == int(rec.get("water", 0)):
            fix.pop(day, None)
        else:
            fix[day] = target - int(rec.get("water", 0))
        self.cfg["data"]["done"] = self._today_water()
        return round(removed_sugar, 1)

    def _pop_last_cup(self, rec: dict) -> float:
        """从今日日志里撤销最后一杯，扣掉它对应杯数与糖分，返回糖分。"""
        cup_log = rec.setdefault("cup_log", [])
        water = int(rec.get("water", 0))
        if water <= 0:
            return 0.0
        if cup_log:
            entry = cup_log.pop()
            sugar = float(entry.get("sugar", 0) or 0)
            if entry.get("k") == "drink":
                # 同步撤销对应的饮料记录（糖分 / 杯数 / 毫升 / 明细）
                rec["sugar"] = round(max(0.0, float(rec.get("sugar", 0) or 0) - sugar), 1)
                rec["drinks"] = max(0, int(rec.get("drinks", 0)) - 1)
                rec["ml"] = max(0.0, float(rec.get("ml", 0) or 0)
                                - float(entry.get("ml", 0) or 0))
                drinks = rec.get("drink_list") or []
                for i in range(len(drinks) - 1, -1, -1):
                    if abs(float(drinks[i].get("sugar", 0) or 0) - sugar) < 0.05:
                        drinks.pop(i)
                        break
        else:
            sugar = 0.0
        rec["water"] = water - 1
        rec["ml"] = max(0.0, float(rec.get("ml", 0) or 0) - ML_PER_CUP)
        return sugar

    def reset_today_water(self) -> None:
        """把今天的杯数**和糖分**一起清零（今日记录也清空）。"""
        self._roll_day()
        rec = self._get_day(self._day_key(), create=True)
        rec["water"] = 0
        rec["ml"] = 0.0
        rec["sugar"] = 0.0
        rec["drinks"] = 0
        rec["drink_list"] = []
        rec["cup_log"] = []
        self.cfg["data"]["water_fix"].pop(self._day_key(), None)
        self.cfg["data"]["done"] = 0
        self.cfg["data"]["skipped"] = 0
        self.cfg["data"]["events"] = []

    def _streak_days(self) -> int:
        """连续达标天数（今天达标从今天算，否则从昨天往前数）。"""
        history = self.cfg["data"].get("history", {})
        goal = self.cfg["goal"]
        streak = 0
        day = date.fromordinal(date.today().toordinal() - 1)
        if self._today_water() >= goal:
            streak = 1
        while streak <= 365:
            rec = history.get(day.isoformat())
            if not rec:
                break
            achieved = rec.get("achieved")
            if achieved is None:
                achieved = int(rec.get("done", 0)) >= int(rec.get("goal", goal))
            if not achieved:
                break
            streak += 1
            day = date.fromordinal(day.toordinal() - 1)
        return streak

    def _record_event(self, kind):
        events = self.cfg["data"]["events"]
        events.append({"t": datetime.now().strftime("%H:%M"), "k": kind})
        del events[:-40]

    def _save(self):
        save_config(self.cfg)

    def _rate(self) -> int:
        done = self._today_water()
        total = done + self.cfg["data"]["skipped"]
        return int(round(done / total * 100)) if total else 100

    # ------------------------------------------------------------ 运行 --
    @property
    def running(self):
        return self.next_due is not None

    @property
    def goal_reached(self) -> bool:
        return self._today_water() >= self.cfg["goal"]

    @property
    def goal_mode(self) -> bool:
        """已达标且仍在计时：显示「已完成」不再提醒（除非用户点「重新开始」）。"""
        return (self.goal_reached and self.running
                and not getattr(self, "_goal_forced", False))

    def toggle_run(self):
        if self.running and self.goal_mode:
            self._goal_forced = True
            self._goal_done_ui = False
            self._schedule_next()
            Toast(self.win, "已重新开始计时", "ok")
            self._last_sec = None
            self.refresh_all()
            return
        if self.running:
            self.paused_left = max(0.0, self.next_due - time.time())
            self.next_due = None
            Toast(self.win, "已暂停提醒，点「继续」恢复", "info")
        else:
            left = self.paused_left or self.cfg["interval_min"] * 60
            self.paused_left = left
            self.next_due = time.time() + left
            Toast(self.win, f"已继续，{max(1, round(left / 60))} 分钟后再提醒你", "ok")
        self._last_sec = None
        self.refresh_all()

    def drink(self):
        """点「喝水」：+1 杯，带正向反馈与 3 秒冷却。"""
        now = time.time()
        remain = DRINK_COOLDOWN - (now - self._last_drink_ts)
        if remain > 0:
            Toast(self.win, f"刚记过一杯啦，{remain:.0f} 秒后可再次记录", "warn", 1600)
            return
        self._last_drink_ts = now
        if self.popup is not None:
            self.popup.close()
        self.record_water(1)
        self._record_event("done")
        self._after_intake()
        self._save()
        done = self._today_water()
        self.refresh_all()
        try:
            DrinkFeedback(self.win, done, self.cfg["goal"])
        except tk.TclError:
            pass
        self._play_chime()
        self._set_drink_enabled(False)
        self.win.after(int(DRINK_COOLDOWN * 1000), lambda: self._set_drink_enabled(True))

    @staticmethod
    def _play_chime():
        try:
            import winsound
            winsound.MessageBeep(-1)
        except Exception:  # noqa: BLE001
            pass

    def _set_drink_enabled(self, enabled: bool):
        btn = getattr(self, "btn_drink_main", None)
        if btn is not None:
            try:
                btn.set_enabled(enabled)
            except tk.TclError:
                pass

    def minus_water(self):
        """「现在不喝 (−1)」：减去最后一杯，并扣掉这一杯对应的含糖量。"""
        if self._today_water() <= 0:
            Toast(self.win, "今天还没有喝水记录", "warn")
            return
        removed_sugar = self.adjust_water(-1)
        self._resume_after_goal_lost()
        self._save()
        self.refresh_all()
        if removed_sugar > 0:
            Toast(self.win,
                  f"已减去 1 杯（含糖 {removed_sugar:.1f}g），今日 "
                  f"{self._today_water()} 杯 · 糖 {self.today_sugar():.0f}g", "info", 3000)
        else:
            Toast(self.win, f"已减去 1 杯，今日 {self._today_water()} 杯", "info")

    def reset_water(self):
        """「重置今日」：杯数与今日糖分一起清零。"""
        had_sugar = self.today_sugar()
        self.reset_today_water()
        self._resume_after_goal_lost()
        self._save()
        self.refresh_all()
        if had_sugar > 0:
            Toast(self.win, f"今日已重置：杯数清零、糖分清零（-{had_sugar:.0f}g）", "info",
                  3000)
        else:
            Toast(self.win, "今日饮水杯数已重置为 0", "info")

    def _resume_after_goal_lost(self):
        if not self.goal_reached:
            self._goal_done_ui = False
            self._goal_forced = False
            if self.running:
                self._schedule_next()

    def open_drink_dialog(self):
        dlg = getattr(self, "drink_dialog", None)
        if dlg is not None:
            try:
                if dlg.top.winfo_exists():
                    dlg.focus()
                    return
            except tk.TclError:
                pass
            self.drink_dialog = None
        self.drink_dialog = DrinkDialog(self)

    def drink_dialog_closed(self):
        self.drink_dialog = None

    def record_drink(self, name: str, volume_ml: float, sugar_g: float,
                     sugar_per_100: float | None = None):
        """记录一杯饮料：同时计入糖分和喝水杯数。"""
        self.add_drink(name, volume_ml, sugar_g, sugar_per_100)
        self.record_water(1, log_cup=False)   # 饮料已自带一条带糖的杯记录
        self._after_intake()
        self._save()
        self.refresh_all()
        limit = self.sugar_limit()
        today = self.today_sugar()
        verdict = sugar_verdict(today, limit)
        Toast(self.win,
              f"已记录 {name}（{volume_ml:.0f}ml · 糖 {sugar_g:.1f}g），"
              f"今日糖分 {today:.0f}g / 建议 {limit:.0f}g 以内",
              "ok" if verdict["level"] == 0 else "warn", 3400)
        if verdict["level"] >= 2:
            self.win.after(1400, lambda: Toast(self.win, verdict["text"], "warn", 3600))

    def _after_intake(self):
        """每次喝下去之后统一处理计时：达标停表，否则重新计时。"""
        if self.goal_reached:
            self._goal_done_ui = True
            self._last_sec = None
        else:
            self._goal_done_ui = False
            self._schedule_next()

    def snooze(self, minutes=None):
        minutes = minutes or self.cfg["snooze_min"]
        if self.popup is not None:
            self.popup.close()
        self._record_event("snooze")
        self._save()
        self.next_due = time.time() + minutes * 60
        self._last_sec = None
        Toast(self.win, f"好，{minutes} 分钟后再提醒你", "warn")
        self.refresh_all()

    def skip(self):
        if self.popup is not None:
            self.popup.close()
        self.cfg["data"]["skipped"] = int(self.cfg["data"].get("skipped", 0)) + 1
        self._record_event("skip")
        self._schedule_next()
        self._save()
        Toast(self.win, "已跳过这一杯，下次照常提醒", "warn")
        self.refresh_all()

    def _schedule_next(self):
        self.next_due = time.time() + self.cfg["interval_min"] * 60
        self.paused_left = self.cfg["interval_min"] * 60
        self._last_sec = None

    def after(self, ms, func):
        """线程安全投递：托盘线程只入队，UI 动作由主线程 _tick 执行。

        参数 ms 仅为兼容旧调用签名保留，动作会在下一个 tick（≤1 秒）内执行。
        """
        if callable(func):
            self.ui_queue.put(func)

    # ------------------------------------------------------------ 定时 --
    def _tick(self):
        try:
            # 先排空后台线程投递的动作，全部在主线程执行
            while True:
                try:
                    action = self.ui_queue.get_nowait()
                except queue.Empty:
                    break
                try:
                    action()
                except Exception as exc:
                    _log_error(exc)
            self._roll_day()
            now = time.time()
            goal_paused = self.goal_reached and not self._goal_forced
            if self.running and goal_paused:
                if not self._goal_done_ui:
                    self._goal_done_ui = True
                    self._last_sec = None
                    self.refresh_all()
            elif self.running and now >= self.next_due:
                self._show_reminder()
                self._schedule_next()
                self._save()
            if self.goal_mode:
                text, sub = "已完成", f"今日目标 {self.cfg['goal']} 杯已达成，明天继续"
            elif self.running:
                left = max(0, self.next_due - now)
                sub = "后提醒你喝水，先忙手上的事吧" if left >= 60 else "马上就该喝水啦"
                text = f"{int(left // 60):02d}:{int(left % 60):02d}"
            else:
                left = self.paused_left
                sub = "已暂停 · 点「继续」恢复倒计时"
                text = f"{int(left // 60):02d}:{int(left % 60):02d}"
            key = (text, sub)
            if key != self._last_sec:
                self._last_sec = key
                fg = TEAL if self.goal_mode else (INK if self.running else "#9AAABB")
                self.time_label.configure(text=text, fg=fg)
                self.time_sub.configure(text=sub)
        except tk.TclError:
            pass
        except Exception as exc:
            _log_error(exc)
        finally:
            # 任何异常都不能让定时器永久停摆
            try:
                self.win.after(1000, self._tick)
            except (tk.TclError, RuntimeError):
                pass

    # ------------------------------------------------------------ 刷新 --
    def _draw_progress(self):
        self.progress.delete("all")
        w = self.progress.winfo_width()
        if w <= 1:
            return
        h = S(10)
        goal = max(1, self.cfg["goal"])
        ratio = min(1.0, self._today_done() / goal)
        self.progress.create_line(0, h // 2, w, h // 2, fill=P.TRACK, width=h,
                                  capstyle="round")
        if ratio > 0:
            self.progress.create_line(0, h // 2, max(h, int(w * ratio)), h // 2,
                                      fill=TEAL if ratio >= 1 else PRIMARY, width=h,
                                      capstyle="round")

    def _draw_sugar_bar(self):
        bar = self.sugar_bar
        bar.delete("all")
        w = bar.winfo_width()
        if w <= 1:
            return
        h = S(10)
        limit = max(1.0, self.sugar_limit())
        yesterday = self.yesterday_sugar()
        verdict = sugar_verdict(yesterday, limit)
        bar.create_line(0, h // 2, w, h // 2, fill=P.TRACK_SUGAR, width=h, capstyle="round")
        ratio = min(1.0, yesterday / limit)
        if ratio > 0:
            bar.create_line(0, h // 2, max(h, int(w * ratio)), h // 2, fill=verdict["color"],
                            width=h, capstyle="round")
        bar.create_line(w - S(2), S(1), w - S(2), h - S(1), fill=P.TICK, width=S(2))

    def _draw_heatmap(self):
        """近 12 周热力图：列=周(12)，行=周一到周日(7)。"""
        cv = getattr(self, "heat_canvas", None)
        if cv is None:
            return
        cv.delete("all")
        w = cv.winfo_width()
        if w <= 1:
            return
        cells = heatmap_weeks(self.cfg)
        pad_x = S(10)
        top = S(20)
        gap = S(2)
        cols, rows = 12, 7
        cell = min(S(16), (w - pad_x * 2 - gap * (cols - 1)) / cols)
        if cell < 3:
            return
        f_tick = self.F["tiny"]
        # 月份标签（每周第一列那周的周一）
        last_month = None
        for c in range(cols):
            key = cells[c * rows][0]
            month = int(key[5:7])
            if month != last_month:
                x = pad_x + c * (cell + gap)
                cv.create_text(x, S(9), text=f"{month}月", anchor="w",
                               fill=P.FAINT, font=f_tick)
                last_month = month
        colors = (P.HEAT_0, P.HEAT_1, P.HEAT_2, P.HEAT_3)
        achieved = 0
        for i, (key, cups, goal, future) in enumerate(cells):
            c, r = divmod(i, rows)
            x = pad_x + c * (cell + gap)
            y = top + r * (cell + gap)
            lvl = heat_level(cups, goal)
            if future:
                lvl = -1  # 未来日期留空描边
            if lvl < 0:
                cv.create_rectangle(x, y, x + cell, y + cell, outline=P.LINE,
                                    fill=P.CARD, width=1)
            else:
                cv.create_rectangle(x, y, x + cell, y + cell, fill=colors[lvl],
                                    outline="", tags=f"cell_{i}")
                if lvl == 3:
                    achieved += 1
        # 达标统计
        if hasattr(self, "heat_summary"):
            self.heat_summary.configure(text=f"近 12 周达标 {achieved} 天")

    def _draw_trend(self):
        """本周 7 天杯数柱状图 + 目标虚线。"""
        cv = getattr(self, "trend_canvas", None)
        if cv is None:
            return
        cv.delete("all")
        w = cv.winfo_width()
        if w <= 1:
            return
        data = week_trend(self.cfg)
        pad_x = S(14)
        top = S(12)
        base = S(100)
        chart_h = base - top
        f_tick = self.F["tiny"]
        goal = data[0][3]
        peak = max([d[2] for d in data] + [goal])
        scale_h = max(1, peak) * 1.15
        slot = (w - pad_x * 2) / 7
        bar_w = min(S(26), slot * 0.62)
        # 目标虚线
        gy = base - chart_h * (goal / scale_h)
        for x in range(int(pad_x), int(w - pad_x), S(10)):
            cv.create_line(x, gy, x + S(5), gy, fill=P.MUTED, width=1)
        cv.create_text(w - pad_x - S(2), gy - S(7), text=f"目标 {goal}杯", anchor="e",
                       fill=P.MUTED, font=f_tick)
        weekday = "一二三四五六日"
        for i, _key, cups, _goal, is_today, future in data:
            cx = pad_x + slot * (i + 0.5)
            h = chart_h * (cups / scale_h) if cups > 0 else 0
            color = (P.TEAL if cups >= goal else P.PRIMARY) if not future else P.LINE
            if h > 0:
                cv.create_rectangle(cx - bar_w / 2, base - h, cx + bar_w / 2, base,
                                    fill=color, outline="")
                cv.create_text(cx, base - h - S(7), text=str(cups), fill=P.INK, font=f_tick)
            label = weekday[i]
            cv.create_text(cx, base + S(11), text=label,
                           fill=P.PRIMARY if is_today else P.FAINT,
                           font=f_tick)
        if hasattr(self, "trend_note"):
            total = sum(d[2] for d in data)
            met = sum(1 for d in data if d[2] >= goal and not d[5])
            self.trend_note.configure(
                text=f"本周累计 {total} 杯 · 达标 {met}/7 天 · 每格按当日杯数/目标着色")

    def _wrap_sugar_labels(self, _event=None):
        width = max(S(240), self.sugar_advice.winfo_width() or S(330))
        f_adv = tkfont.Font(font=self.sugar_advice.cget("font"))
        f_meta = tkfont.Font(font=self.sugar_meta.cget("font"))
        self.sugar_advice.configure(
            wraplength=width,
            text=wrap_paragraph(self._sugar_advice_text, width, f_adv, letter_gap=True))
        self.sugar_meta.configure(
            wraplength=width,
            text=wrap_paragraph(self._sugar_meta_text, width, f_meta))

    def _refresh_timeline(self):
        for child in self.timeline.winfo_children():
            child.destroy()
        entries = []
        for ev in self.cfg["data"]["events"][-6:]:
            if ev.get("k") != "drink":
                entries.append((ev.get("t", "--:--"), ev.get("k", ""), None))
        for d in self._get_day(self._day_key()).get("drink_list", [])[-4:]:
            entries.append((d.get("t", "--:--"), "drink", d))
        entries = entries[-5:]
        if not entries:
            tk.Label(self.timeline, text="今天还没有记录，点上面的「喝水」或「喝饮料」开始吧",
                     font=self.F["small"], fg=P.FAINT, bg=CARD).pack(anchor="w")
            return
        meta = {"done": ("✓", "喝了一杯水", TEAL), "skip": ("⇥", "已跳过", MUTED),
                "snooze": ("◷", "稍后提醒", AMBER), "water": ("✓", "喝了一杯水", TEAL)}
        for t, kind, extra in entries:
            if kind == "drink" and extra:
                per100 = extra.get("per100")
                detail = f"{float(extra.get('ml', 0)):.0f}ml"
                if per100 is not None:
                    detail += f" · {float(per100):g}g/100ml"
                detail += f" · 糖 {float(extra.get('sugar', 0)):.0f}g"
                glyph, text, color = "🥤", f"{extra.get('name', '饮料')} {detail}", AMBER
            else:
                glyph, text, color = meta.get(kind, ("•", "提醒", MUTED))
            row = tk.Frame(self.timeline, bg=CARD)
            row.pack(fill="x", pady=S(2))
            tk.Label(row, text=t, font=self.F["small"], fg=MUTED, bg=CARD, width=5,
                     anchor="w").pack(side="left")
            tk.Label(row, text=glyph, font=self.F["small"], fg=color, bg=CARD).pack(
                side="left", padx=(S(2), S(6)))
            tk.Label(row, text=text, font=self.F["small"], fg=INK, bg=CARD).pack(side="left")

    def _wrap_advice(self, _event=None):
        width = max(S(240), int((self.advice_detail.winfo_width() or S(330)) * 0.98))
        f = tkfont.Font(font=self.advice_detail.cget("font"))
        self.advice_detail.configure(
            wraplength=width,
            text=wrap_paragraph(getattr(self, "_advice_detail_text", ""), width, f))
        self.advice_note.configure(wraplength=width)

    def refresh_all(self):
        goal = self.cfg["goal"]
        today = self._today_water()
        today_sugar = self.today_sugar()
        limit = self.sugar_limit()

        # 专属饮水建议
        advice = water_advice(self.cfg.get("profile"))
        applied = bool(self.cfg.get("profile", {}).get("applied"))
        self.advice_num.configure(text=f"≈ {advice['ml']} ml / 天")
        self.advice_cups.configure(
            text=f"按每杯 {ML_PER_CUP} ml 约 {advice['cups']} 杯"
                 + (" · 已同步为每日目标" if applied else " · 尚未应用到目标"))
        self.advice_badge.configure(text=" 估算 · 已应用 " if applied else " 估算 · 待应用 ",
                                    bg=TEAL if applied else MUTED)
        detail = "；".join(f"{name} {int(value):+d} ml" if i else f"{name} {int(value)} ml"
                          for i, (name, value, _desc) in enumerate(advice["parts"]))
        if advice["clamped"]:
            detail += f"（已收敛到 {ADVICE_ML_MIN}–{ADVICE_ML_MAX} ml 区间）"
        self._advice_detail_text = "计算：" + detail + "。"
        self._wrap_advice()
        if getattr(self, "btn_apply_advice", None) is not None:
            self.btn_apply_advice.set_enabled(not applied or self.cfg["goal"] != advice["cups"])

        self.stat_values["cups"].configure(text=f"{today}/{goal}")
        self.stat_values["sugar"].configure(text=f"{today_sugar:.0f}g",
                                            fg=INK if today_sugar <= limit else P.DANGER)
        self.stat_values["rate"].configure(text=f"{self._rate()}%")
        self.stat_values["streak"].configure(text=f"{self._streak_days()} 天")
        skipped = f" · 跳过 {self.cfg['data']['skipped']} 次" if self.cfg["data"]["skipped"] else ""
        self.goal_line.configure(
            text=f"今日喝水 {today}/{goal} 杯 · 完成率 {self._rate()}%{skipped}")

        self.period_values["week"].configure(text=f"{self.week_cups()} 杯")
        self.period_values["month"].configure(text=f"{self.month_cups()} 杯")

        yesterday = self.yesterday_sugar()
        verdict = sugar_verdict(yesterday, limit)
        self.sugar_value.configure(text=f"{yesterday:.1f} g", fg=verdict["color"])
        self.sugar_tag.configure(text=f"  {verdict['tag']}  ", bg=verdict["color"])
        pct = (yesterday / limit * 100) if limit else 0
        self._sugar_advice_text = (
            f"{verdict['text']}。推荐每日添加糖摄入量：{limit:.0f} g 以内"
            f"（约 {SUGAR_PERCENT_TARGET:.0f}% 总能量，按 {self.cfg['kcal_per_day']} kcal 估算）。")
        drinks_yday = self._get_day(self.yesterday_key()).get("drinks", 0)
        self._sugar_meta_text = (
            f"昨日占推荐量 {pct:.0f}% · 含糖饮料 {drinks_yday} 杯 · "
            f"今日已摄入 {today_sugar:.1f} g（饮料 {self.today_drinks()} 杯）"
            + ("　｜　严格标准建议 25 g 以内" if self.cfg["sugar_ratio"] > 6 else ""))
        self._draw_sugar_bar()
        self._wrap_sugar_labels()

        if self.goal_mode:
            self.status_label.configure(
                text=f"今日目标已完成（{today}/{goal} 杯）· 明天继续")
            self.btn_toggle.set_text("重新开始")
            self.time_label.configure(text="已完成", fg=TEAL)
            self.time_sub.configure(text=f"今日目标 {goal} 杯已达成，明天继续")
            self._last_sec = ("已完成", self.time_sub.cget("text"))
        elif self.running:
            self.status_label.configure(
                text=f"运行中 · 每 {self.cfg['interval_min']} 分钟提醒一次")
            self.btn_toggle.set_text("暂停")
        else:
            self.status_label.configure(text="已暂停")
            self.btn_toggle.set_text("继续")
        # 「现在不喝」只在今天已喝过水时可点
        if getattr(self, "btn_minus", None) is not None:
            self.btn_minus.set_enabled(today > 0)
        self._draw_progress()
        self._refresh_timeline()
        self._draw_heatmap()
        self._draw_trend()
        quotes = self.cfg["quotes"]
        tkfont_f = tkfont.Font(font=self.quotes_label.cget("font"))
        preview = " ｜ ".join(quotes[:5]) + (" …" if len(quotes) > 5 else "")
        self.quotes_label.configure(
            text=wrap_paragraph(f"轮播中（{len(quotes)} 条）：{preview}", S(330), tkfont_f))
        if self.tray is not None:
            self.tray.update_tip()

    # ------------------------------------------------------------ 设置回调 --
    def on_interval(self, value):
        self.cfg["interval_min"] = _clamp(value, INTERVAL_MIN, INTERVAL_MAX)
        if self.running:
            self.next_due = time.time() + self.cfg["interval_min"] * 60
        self.paused_left = self.cfg["interval_min"] * 60
        self._last_sec = None
        if getattr(self, "sl_interval", None) is not None:
            if self.sl_interval.value != self.cfg["interval_min"]:
                self.sl_interval.set(self.cfg["interval_min"])
        self._save()
        self.refresh_all()

    def on_goal(self, value):
        self.cfg["goal"] = _clamp(value, GOAL_MIN, GOAL_MAX)
        if getattr(self, "sl_goal", None) is not None:
            if self.sl_goal.value != self.cfg["goal"]:
                self.sl_goal.set(self.cfg["goal"])
        self._save()
        self.refresh_all()

    # ------------------------------------------------------------ 外观 --
    def on_theme(self, value):
        self.cfg["theme"] = "dark" if value else "light"
        self._save()
        self._rebuild_ui()

    def _rebuild_ui(self):
        """切换主题后重建整套 UI：控件颜色在建时固化，重建最彻底且状态都在 cfg 里。"""
        set_palette(self.cfg["theme"])
        # 关掉可能打开的浮层，避免它们引用即将销毁的控件
        for dialog in (self.popup, self.drink_dialog, self.profile_dialog):
            if dialog is not None:
                try:
                    dialog.close()
                except (tk.TclError, Exception):  # noqa: BLE001
                    pass
        self.popup = self.drink_dialog = self.profile_dialog = None
        try:
            if getattr(self, "page", None) is not None:
                self.page.destroy()
        except tk.TclError:
            pass
        self.win.configure(bg=BG)
        self._last_sec = None
        self._build_ui()

    def on_hotkey(self, value):
        self.cfg["hotkey"] = bool(value)
        self._save()
        if value:
            if self.hotkeys is None:
                self.hotkeys = GlobalHotkeys(self)
            state = "已启用" if self.hotkeys.ok else "注册失败，可能被其它软件占用"
        else:
            if self.hotkeys is not None:
                self.hotkeys.close()
                self.hotkeys = None
            state = "已关闭"
        Toast(self.win, f"全局快捷键{state}", "ok" if value and self.hotkeys and self.hotkeys.ok
              else "info")

    # -------------------------------------------------------- 个性化建议 --
    def open_profile_dialog(self):
        if getattr(self, "profile_dialog", None) is not None:
            self.profile_dialog.focus()
            return
        self.profile_dialog = ProfileDialog(self)

    def profile_dialog_closed(self):
        self.profile_dialog = None

    def apply_advice(self):
        advice = water_advice(self.cfg.get("profile"))
        profile = normalize_profile(self.cfg.get("profile"))
        profile["applied"] = True
        self.cfg["profile"] = profile
        self.on_goal(advice["cups"])          # 复用已有回调：校验/保存/刷新一步到位
        Toast(self.win, f"已按身体情况设置每日目标：{advice['cups']} 杯（约 {advice['ml']} ml）",
              "ok")

    def on_gentle(self, value):
        self.cfg["gentle"] = bool(value)
        self._save()

    def on_autostart(self, value):
        ok = self._set_autostart(bool(value))
        self.cfg["autostart"] = bool(value) if ok else self._autostart_exists()
        self.sw_autostart.set_value(self.cfg["autostart"])
        self._save()
        Toast(self.win, "已开启开机自动启动" if value else "已关闭开机自动启动",
              "ok" if ok else "warn")

    def shuffle_quote(self):
        self.quote_box.delete(0, "end")
        self.quote_box.insert(0, random.choice(self.cfg["quotes"]))

    def add_quote(self):
        text = self.quote_box.get().strip()
        if not text:
            Toast(self.win, "先写一句想看到的提醒语吧", "warn")
            return
        if len(self.cfg["quotes"]) >= 40:
            Toast(self.win, "提醒语最多 40 条，先删掉一些吧", "warn")
            return
        if text in self.cfg["quotes"]:
            Toast(self.win, "这条提醒语已经在轮播里了", "warn")
            return
        self.cfg["quotes"].append(text)
        self._save()
        self.refresh_all()
        Toast(self.win, "已加入提醒语轮播", "ok")
        self.shuffle_quote()

    # ------------------------------------------------------------ 开机自启 --
    def _startup_file(self) -> Path:
        appdata = os.environ.get("APPDATA") or str(Path.home() / "AppData" / "Roaming")
        return (Path(appdata) / "Microsoft" / "Windows" / "Start Menu" / "Programs"
                / "Startup" / f"{APP_NAME}.vbs")

    def _autostart_exists(self) -> bool:
        try:
            return self._startup_file().exists()
        except OSError:
            return False

    def _set_autostart(self, enabled: bool) -> bool:
        try:
            target = self._startup_file()
            if enabled:
                target.parent.mkdir(parents=True, exist_ok=True)
                write_vbs(target, launch_script())
            elif target.exists():
                target.unlink()
            return True
        except OSError:
            return False

    # ------------------------------------------------------------ 提醒 --
    def _show_reminder(self):
        if self.goal_reached and not self._goal_forced:
            return
        if self.popup is not None:
            try:
                self.popup.close()
            except tk.TclError:
                pass
        self.popup = ReminderPopup(self)

    def on_reminder_done(self, minutes):
        if minutes is None:
            self.drink()
        else:
            self.snooze(minutes)

    def popup_closed(self):
        self.popup = None

    # ------------------------------------------------------------ 窗口/托盘 --
    def on_close(self):
        """点 × → 收进系统托盘，程序继续在后台计时。"""
        self._save()
        self.hide_to_tray()

    def minimize(self):
        self.win.iconify()

    def _ensure_tray(self):
        if self.tray is None or not getattr(self.tray, "ok", False):
            self.tray = TrayIcon(self)
        return bool(getattr(self.tray, "ok", False))

    def hide_to_tray(self):
        if not self._ensure_tray():
            self.win.iconify()
            Toast(self.win, "系统托盘不可用，已最小化到任务栏（程序仍在后台运行）",
                  "warn", 3600)
            return
        self.win.withdraw()
        self.minimized = True
        self.tray.update_tip()
        if not self._tray_hinted:
            self._tray_hinted = True
            self.tray.notify(f"{APP_NAME}已收进系统托盘，仍在后台提醒",
                             f"每 {self.cfg['interval_min']} 分钟提醒一次。"
                             "单击托盘图标恢复窗口，右键可暂停 / 记录 / 关闭程序")

    def restore(self):
        self.minimized = False
        show_window(self.win)

    def _on_unmap(self, event):
        if event.widget is not self.win:
            return
        if self.win.state() != "iconic":
            return
        self.minimized = True
        if self._ensure_tray():
            self.tray.update_tip()

    def _on_map(self, event):
        if event.widget is self.win:
            self.minimized = False

    def quit(self):
        self._save()
        if self.popup is not None:
            try:
                self.popup.close()
            except tk.TclError:
                pass
        if self.tray is not None:
            self.tray.close()
        if self.hotkeys is not None:
            self.hotkeys.close()
        try:
            self.win.destroy()
        except tk.TclError:
            pass

    def run(self):
        self.win.mainloop()


# ---------------------------------------------------------------- 喝饮料 --

# 常见饮品：(名称, 容量 ml, 每 100ml 含糖量 g)
PRESETS = (("可乐 330ml", 330, 10.6), ("奶茶 500ml", 500, 10.0), ("果汁 250ml", 250, 10.0),
           ("无糖茶 500ml", 500, 0.0), ("咖啡（加糖）360ml", 360, 3.3))


class DrinkDialog:
    """记录一杯饮料。

    刻意使用**普通窗口**（保留系统标题栏）而不是 overrideredirect 的无边框窗：
    无边框窗口在 Windows 上常常拿不到前台焦点，输入框收不到键盘输入
    （这正是「喝饮料无法编辑」的根因）。普通窗口可被正常激活、自由输入。
    """

    W, H = 448, 508

    def __init__(self, app: WaterReminderApp):
        self.app = app
        F = app.F
        self.top = top = tk.Toplevel(app.win)
        top.withdraw()
        top.title("记录一杯饮料")
        top.transient(app.win)
        top.configure(bg=BG)
        top.resizable(False, False)
        self._position_near_main()
        top.bind("<Escape>", lambda e: self.close())
        top.protocol("WM_DELETE_WINDOW", self.close)

        shell = tk.Frame(top, bg=CARD, highlightthickness=1, highlightbackground=LINE)
        shell.pack(fill="both", expand=True)

        head = tk.Frame(shell, bg=AMBER, height=S(50))
        head.pack(fill="x")
        head.pack_propagate(False)
        tk.Label(head, text="填写这杯饮料的信息", font=F["sw_title"], fg="#FFFFFF",
                 bg=AMBER).pack(side="left", padx=S(18))

        # 表单区可滚动，底部按钮固定
        scroll_holder = tk.Frame(shell, bg=CARD)
        scroll_holder.pack(fill="both", expand=True)
        self._dcanvas = tk.Canvas(scroll_holder, bg=CARD, highlightthickness=0, bd=0)
        vbar = tk.Scrollbar(scroll_holder, orient="vertical", command=self._dcanvas.yview)
        self._dcanvas.configure(yscrollcommand=vbar.set)
        vbar.pack(side="right", fill="y")
        self._dcanvas.pack(side="left", fill="both", expand=True)
        body = tk.Frame(self._dcanvas, bg=CARD)
        body_id = self._dcanvas.create_window((0, 0), window=body, anchor="nw")
        body.bind("<Configure>", lambda e: self._dcanvas.configure(
            scrollregion=self._dcanvas.bbox("all")))
        self._dcanvas.bind("<Configure>", lambda e: self._dcanvas.itemconfigure(
            body_id, width=e.width))
        pad = tk.Frame(body, bg=CARD)
        pad.pack(fill="both", expand=True, padx=S(6), pady=(S(6), 0))

        # 快捷预设
        tk.Label(pad, text="常见饮品（点一下自动填入）", font=F["tiny"], fg=MUTED,
                 bg=CARD).pack(anchor="w")
        presets = tk.Frame(pad, bg=CARD)
        presets.pack(fill="x", pady=(S(4), S(10)))
        x_pos = y_pos = 0
        max_w = max(S(200), self._w - S(80))
        for name, ml, sugar in PRESETS:
            b = RoundedButton(presets, name, lambda n=name, m=ml, s=sugar: self.fill(n, m, s),
                              variant="secondary", height=S(30), padx=S(10), font=F["tiny"])
            width = b.winfo_reqwidth()
            if x_pos and x_pos + width > max_w:
                x_pos, y_pos = 0, y_pos + S(34)
            b.place(x=x_pos, y=y_pos)
            x_pos += width + S(4)
        presets.config(height=y_pos + S(30))
        presets.pack_propagate(False)

        self.name_var = tk.StringVar(value="可乐")
        self.ml_var = tk.StringVar(value="330")
        self.sugar_var = tk.StringVar(value="10.6")
        tk.Label(pad, text="饮料名称", font=F["small"], fg=MUTED, bg=CARD,
                 anchor="w").pack(fill="x")
        self.name_entry = self._entry(pad, self.name_var)
        self.name_entry.pack(fill="x", ipady=S(7), pady=(0, S(8)))
        tk.Label(pad, text="容量（ml）", font=F["small"], fg=MUTED, bg=CARD,
                 anchor="w").pack(fill="x")
        self.ml_entry = self._entry(pad, self.ml_var, lambda: self.sugar_entry.focus_set())
        self.ml_entry.pack(fill="x", ipady=S(7), pady=(0, S(8)))
        tk.Label(pad, text="含糖量（g / 100ml）", font=F["small"], fg=MUTED, bg=CARD,
                 anchor="w").pack(fill="x")
        self.sugar_entry = self._entry(pad, self.sugar_var, self.save)
        self.sugar_entry.pack(fill="x", ipady=S(7), pady=(0, S(4)))
        self.hint = tk.Label(pad, text="不知道含糖量？看包装上的「碳水化合物」或「糖」那一栏",
                             font=F["tiny"], fg=P.FAINT, bg=CARD, anchor="w",
                             justify="left", wraplength=max(S(200), self._w - S(90)))
        self.hint.pack(fill="x", pady=(S(2), S(10)))

        # 昨日糖分概况
        summary = tk.Frame(pad, bg=SOFT, highlightthickness=1, highlightbackground=LINE)
        summary.pack(fill="x", pady=(0, S(10)))
        yesterday, limit = app.yesterday_sugar(), app.sugar_limit()
        verdict = sugar_verdict(yesterday, limit)
        inner = tk.Frame(summary, bg=SOFT)
        inner.pack(fill="x", padx=S(12), pady=S(8))
        line = tk.Frame(inner, bg=SOFT)
        line.pack(fill="x")
        tk.Label(line, text="昨日饮料糖分", font=F["body"], fg=INK, bg=SOFT).pack(side="left")
        tk.Label(line, text=f"{yesterday:.1f} g", font=F["body"], fg=verdict["color"],
                 bg=SOFT).pack(side="left", padx=(S(6), S(8)))
        tk.Label(line, text=verdict["tag"], font=F["tiny"], fg="#FFFFFF",
                 bg=verdict["color"]).pack(side="left")
        wrap_w = max(S(200), self._w - S(120))
        tk.Label(inner, text=f"推荐摄入：{limit:.0f} g 以内（WHO：少于总能量 10%）",
                 font=F["tiny"], fg=MUTED, bg=SOFT, anchor="w", justify="left",
                 wraplength=wrap_w).pack(fill="x", pady=(S(2), 0))
        self.verdict_label = tk.Label(inner, text=verdict["text"], font=F["tiny"],
                                      fg=verdict["color"], bg=SOFT, anchor="w",
                                      justify="left", wraplength=wrap_w)
        self.verdict_label.pack(fill="x")

        self.calc_label = tk.Label(pad, text="", font=F["small"], fg=MUTED, bg=CARD,
                                   justify="left", anchor="w")
        self.calc_label.pack(fill="x", pady=(0, S(8)))
        self.calc_label.bind("<Configure>", lambda e: self._wrap_calc(e.width))
        for var in (self.ml_var, self.sugar_var):
            var.trace_add("write", lambda *_: self.update_preview())

        # 底部按钮
        foot = tk.Frame(shell, bg=CARD)
        foot.pack(side="bottom", fill="x", padx=S(16), pady=(S(6), S(12)))
        RoundedButton(foot, "取消", self.close, variant="secondary", height=S(42),
                      padx=S(24), font=F["btn"]).pack(side="right", padx=(S(8), 0))
        self.save_btn = RoundedButton(foot, "记录这杯饮料", self.save, variant="amber",
                                      height=S(42), padx=S(22), font=F["btn"])
        self.save_btn.pack(side="right")

        self.update_preview()
        self._bind_local_wheel(top, self._dcanvas)
        self._show_and_focus()

    # ---- 定位 / 焦点 ----
    def _position_near_main(self):
        app = self.app
        sw, sh = app.win.winfo_screenwidth(), app.win.winfo_screenheight()
        w = max(S(self.W), int(sw * 0.38))
        h = max(S(self.H), int(sh * 0.80))
        self._w = w
        try:
            mx, my = app.win.winfo_rootx(), app.win.winfo_rooty()
            mw = app.win.winfo_width()
            x = mx + mw + S(12)
            if x + w > sw - S(8):
                x = max(S(8), mx - w - S(12))
            if x < S(8) or x + w > sw - S(8):
                x = max(S(8), (sw - w) // 2)
            y = max(S(8), min(my, sh - h - S(48)))
        except tk.TclError:
            x, y = max(S(8), (sw - w) // 2), max(S(8), (sh - h) // 2 - S(30))
        self.top.geometry(f"{w}x{h}+{x}+{y}")

    def _show_and_focus(self):
        """显示并确保拿到键盘焦点（普通窗口才能稳定成为前台窗口）。"""
        self.top.deiconify()
        self.top.lift()
        try:
            self.top.focus_force()
        except tk.TclError:
            pass
        try:
            import ctypes
            user32 = ctypes.windll.user32
            hwnd = int(self.top.wm_frame(), 16)
            user32.ShowWindow(hwnd, 5)
            user32.BringWindowToTop(hwnd)
            user32.SetForegroundWindow(hwnd)
        except Exception:  # noqa: BLE001
            pass
        try:
            self.name_entry.focus_set()
            self.name_entry.select_range(0, "end")
        except tk.TclError:
            pass

    def _bind_local_wheel(self, root, canvas):
        """滚轮只作用于本对话框（不能用 bind_all，否则会覆盖主窗口）。"""
        def on_wheel(event):
            first, _last = canvas.yview()
            if first <= 0.0 and event.delta > 0:
                return
            canvas.yview_scroll(-1 if event.delta > 0 else 1, "units")

        def walk(widget):
            widget.bind("<MouseWheel>", on_wheel, add="+")
            for child in widget.winfo_children():
                walk(child)

        walk(root)

    def _entry(self, parent, var, on_enter=None):
        e = tk.Entry(parent, textvariable=var, font=self.app.F["body"], fg=INK, bg=SOFT,
                     relief="flat", bd=0, insertbackground=AMBER, highlightthickness=1,
                     highlightbackground=LINE, highlightcolor=AMBER, takefocus=1)
        if on_enter:
            e.bind("<Return>", lambda _e: on_enter())
        return e

    def fill(self, name, ml, sugar_per_100):
        self.name_var.set(name.split(" ")[0])
        self.ml_var.set(str(ml))
        self.sugar_var.set(str(sugar_per_100))
        self.sugar_entry.focus_set()

    def _values(self):
        """返回 (名称, 容量ml, 每100ml含糖量, 实际摄入糖克数)。"""
        name = self.name_var.get().strip() or "饮料"
        # _num 会拦截 nan/inf，避免记录出 5000ml / 5000g 的荒谬数据
        ml = max(0.0, min(5000.0, _num(self.ml_var.get(), 0.0)))
        per100 = max(0.0, min(100.0, _num(self.sugar_var.get(), 0.0)))
        return name, ml, per100, per100 * ml / 100.0

    def _wrap_calc(self, width):
        if width > S(40):
            self.calc_label.configure(wraplength=width - S(8))
            self.update_preview()

    def update_preview(self):
        _n, ml, per100, sugar = self._values()
        limit = self.app.sugar_limit()
        today_after = self.app.today_sugar() + sugar
        verdict = sugar_verdict(today_after, limit)
        self.calc_label.configure(
            text=f"按 {per100:g} g/100ml × {ml:.0f}ml 计算，这杯约 {sugar:.0f} g 糖。"
                 f"记录后今日糖分 {today_after:.0f} g，"
                 f"占推荐量的 {today_after / limit * 100 if limit else 0:.0f}%，"
                 f"{verdict['tag']}。",
            fg=verdict["color"] if verdict["level"] else MUTED)

    def save(self):
        name, ml, per100, sugar = self._values()
        if ml <= 0:
            Toast(self.app.win, "请填写这杯饮料的容量（ml）", "warn")
            return
        self.close()          # 先关窗，再记录
        self.app.record_drink(name, ml, sugar, sugar_per_100=per100)

    def focus(self):
        self._show_and_focus()

    def close(self):
        """先 withdraw 再 destroy，避免残留窗口挡住新窗口。"""
        try:
            self.top.withdraw()
        except tk.TclError:
            pass
        try:
            self.top.destroy()
        except tk.TclError:
            pass
        self.app.drink_dialog_closed()


# ------------------------------------------------------------ 身体情况档案 --

class ProfileDialog:
    """填写身体情况，实时预览估算结果并保存。

    与 DrinkDialog 一致使用普通窗口，保证输入框能稳定获得键盘焦点。
    """

    W, H = 460, 620

    def __init__(self, app: WaterReminderApp):
        self.app = app
        F = app.F
        self.top = top = tk.Toplevel(app.win)
        top.withdraw()
        top.title("填写身体情况")
        top.transient(app.win)
        top.configure(bg=BG)
        top.resizable(False, False)
        self._position_near_main()
        top.bind("<Escape>", lambda e: self.close())
        top.protocol("WM_DELETE_WINDOW", self.close)

        shell = tk.Frame(top, bg=CARD, highlightthickness=1, highlightbackground=LINE)
        shell.pack(fill="both", expand=True)
        head = tk.Frame(shell, bg=TEAL, height=S(50))
        head.pack(fill="x")
        head.pack_propagate(False)
        tk.Label(head, text="定制你的专属饮水建议", font=F["sw_title"], fg="#FFFFFF",
                 bg=TEAL).pack(side="left", padx=S(18))

        scroll_holder = tk.Frame(shell, bg=CARD)
        scroll_holder.pack(fill="both", expand=True)
        self._dcanvas = tk.Canvas(scroll_holder, bg=CARD, highlightthickness=0, bd=0)
        vbar = tk.Scrollbar(scroll_holder, orient="vertical", command=self._dcanvas.yview)
        self._dcanvas.configure(yscrollcommand=vbar.set)
        vbar.pack(side="right", fill="y")
        self._dcanvas.pack(side="left", fill="both", expand=True)
        body = tk.Frame(self._dcanvas, bg=CARD)
        body_id = self._dcanvas.create_window((0, 0), window=body, anchor="nw")
        body.bind("<Configure>", lambda e: self._dcanvas.configure(
            scrollregion=self._dcanvas.bbox("all")))
        self._dcanvas.bind("<Configure>", lambda e: self._dcanvas.itemconfigure(
            body_id, width=e.width))
        pad = tk.Frame(body, bg=CARD)
        pad.pack(fill="both", expand=True, padx=S(16), pady=(S(12), 0))

        p = normalize_profile(app.cfg.get("profile"))
        wrap_w = max(S(200), self._w - S(80))

        # 性别
        tk.Label(pad, text="生理性别（影响基础系数）", font=F["small"], fg=MUTED, bg=CARD,
                 anchor="w").pack(fill="x")
        self.sex_var = tk.StringVar(value=p["sex"])
        sexes = tk.Frame(pad, bg=CARD)
        sexes.pack(fill="x", pady=(S(4), S(10)))
        for val, text in (("female", "女"), ("male", "男")):
            tk.Radiobutton(sexes, text=text, value=val, variable=self.sex_var,
                           command=self.update_preview, font=F["small"], fg=INK, bg=CARD,
                           selectcolor=TINT, activebackground=CARD,
                           highlightthickness=0).pack(side="left", padx=(0, S(16)))

        # 体重
        tk.Label(pad, text="体重（kg）", font=F["small"], fg=MUTED, bg=CARD,
                 anchor="w").pack(fill="x")
        self.weight_var = tk.StringVar(value=f"{p['weight']:g}")
        wrow = tk.Frame(pad, bg=CARD)
        wrow.pack(fill="x", pady=(S(4), S(12)))
        self.weight_entry = tk.Entry(wrow, textvariable=self.weight_var, font=F["body"],
                                     fg=INK, bg=SOFT, relief="flat", bd=0,
                                     insertbackground=TEAL, highlightthickness=1,
                                     highlightbackground=LINE, highlightcolor=TEAL,
                                     takefocus=1)
        self.weight_entry.pack(fill="x", ipady=S(7))

        # 三个单选组
        self._radio_group(pad, "日常活动强度", "activity", ACTIVITY_OPTIONS,
                          p["activity"], wrap_w)
        self._radio_group(pad, "所处环境温度", "climate", CLIMATE_OPTIONS,
                          p["climate"], wrap_w)
        self._radio_group(pad, "身体状态", "body", BODY_OPTIONS, p["body"], wrap_w)

        # 预览
        summary = tk.Frame(pad, bg=SOFT, highlightthickness=1, highlightbackground=LINE)
        summary.pack(fill="x", pady=(S(10), S(6)))
        inner = tk.Frame(summary, bg=SOFT)
        inner.pack(fill="x", padx=S(12), pady=S(10))
        line = tk.Frame(inner, bg=SOFT)
        line.pack(fill="x")
        tk.Label(line, text="建议每日饮水", font=F["body"], fg=INK, bg=SOFT).pack(side="left")
        self.preview_ml = tk.Label(line, text="", font=F["body"], fg=PRIMARY, bg=SOFT)
        self.preview_ml.pack(side="left", padx=(S(6), 0))
        self.preview_cups = tk.Label(line, text="", font=F["tiny"], fg=MUTED, bg=SOFT)
        self.preview_cups.pack(side="right")
        self.preview_detail = tk.Label(inner, text="", font=F["tiny"], fg=MUTED, bg=SOFT,
                                       anchor="w", justify="left", wraplength=wrap_w)
        self.preview_detail.pack(fill="x", pady=(S(5), 0))
        tk.Label(inner, text=ADVICE_DISCLAIMER, font=F["tiny"], fg=P.FAINT, bg=SOFT,
                 anchor="w", justify="left", wraplength=wrap_w).pack(fill="x", pady=(S(5), 0))

        foot = tk.Frame(shell, bg=CARD)
        foot.pack(side="bottom", fill="x", padx=S(16), pady=(S(6), S(12)))
        RoundedButton(foot, "取消", self.close, variant="secondary", height=S(42),
                      padx=S(24), font=F["btn"]).pack(side="right", padx=(S(8), 0))
        RoundedButton(foot, "保存身体情况", self.save, variant="teal", height=S(42),
                      padx=S(20), font=F["btn"]).pack(side="right")

        self.weight_var.trace_add("write", lambda *_: self.update_preview())
        self.update_preview()
        DrinkDialog._bind_local_wheel(self, top, self._dcanvas)
        self._show_and_focus()

    def _radio_group(self, parent, title, key, options, current, wrap_w):
        F = self.app.F
        tk.Label(parent, text=title, font=F["small"], fg=MUTED, bg=CARD,
                 anchor="w").pack(fill="x", pady=(S(2), 0))
        var = tk.StringVar(value=current)
        setattr(self, f"var_{key}", var)
        group = tk.Frame(parent, bg=CARD)
        group.pack(fill="x", pady=(S(3), S(8)))
        for value, label, delta in options:
            tk.Radiobutton(group, text=f"{label}（{delta:+d} ml）" if delta else f"{label}（基准）",
                           value=value, variable=var, command=self.update_preview,
                           font=F["tiny"], fg=INK, bg=CARD, selectcolor=TINT,
                           activebackground=CARD, highlightthickness=0,
                           anchor="w", justify="left", wraplength=wrap_w).pack(fill="x")

    def _position_near_main(self):
        app = self.app
        sw, sh = app.win.winfo_screenwidth(), app.win.winfo_screenheight()
        w = max(S(self.W), int(sw * 0.38))
        h = min(max(S(self.H), int(sh * 0.82)), sh - S(40))
        self._w = w
        try:
            mx, my = app.win.winfo_rootx(), app.win.winfo_rooty()
            mw = app.win.winfo_width()
            x = mx + mw + S(12)
            if x + w > sw - S(8):
                x = max(S(8), mx - w - S(12))
            if x < S(8) or x + w > sw - S(8):
                x = max(S(8), (sw - w) // 2)
            y = max(S(8), min(my, sh - h - S(40)))
        except tk.TclError:
            x, y = max(S(8), (sw - w) // 2), max(S(8), (sh - h) // 2 - S(30))
        self.top.geometry(f"{w}x{h}+{x}+{y}")

    def _show_and_focus(self):
        self.top.deiconify()
        self.top.lift()
        try:
            self.top.focus_force()
        except tk.TclError:
            pass
        try:
            self.weight_entry.focus_set()
            self.weight_entry.select_range(0, "end")
        except tk.TclError:
            pass

    def _values(self) -> dict:
        return {"sex": self.sex_var.get(),
                "weight": _num(self.weight_var.get(), 55.0),
                "activity": self.var_activity.get(),
                "climate": self.var_climate.get(),
                "body": self.var_body.get(),
                "applied": bool(self.app.cfg.get("profile", {}).get("applied"))}

    def update_preview(self):
        advice = water_advice(self._values())
        self.preview_ml.configure(text=f"{advice['ml']} ml")
        self.preview_cups.configure(text=f"约 {advice['cups']} 杯 / 天")
        detail = "；".join(
            f"{name} {int(val):+d} ml" if i else f"{name} {int(val)} ml"
            for i, (name, val, _desc) in enumerate(advice["parts"]))
        if advice["clamped"]:
            detail += f"（已收敛到 {ADVICE_ML_MIN}–{ADVICE_ML_MAX} ml）"
        self.preview_detail.configure(text="计算：" + detail + "。")

    def save(self):
        values = normalize_profile(self._values())
        self.app.cfg["profile"] = values
        self.app._save()
        self.close()
        self.app.refresh_all()
        Toast(self.app.win, "身体情况已保存，建议已更新；点「应用为目标」即可同步", "ok")

    def focus(self):
        self._show_and_focus()

    def close(self):
        try:
            self.top.withdraw()
        except tk.TclError:
            pass
        try:
            self.top.destroy()
        except tk.TclError:
            pass
        self.app.profile_dialog_closed()


# ---------------------------------------------------------------- 提醒弹窗 --

class ReminderPopup:
    """到点提醒弹窗：卡片式小窗，紧挨主界面显示并跟随其移动。"""

    W = 392

    def __init__(self, app: WaterReminderApp):
        self.app = app
        win = app.win
        F = app.F
        self.top = top = tk.Toplevel(win)
        top.withdraw()
        top.overrideredirect(True)
        top.attributes("-topmost", True)
        top.configure(bg=BG)

        ratio = 0.34 if FONT_BOOST > 1.5 else 0.3
        w = max(S(self.W), int(win.winfo_screenwidth() * ratio))
        self._w = w
        top.geometry(f"{w}x{S(500)}+0+0")
        top.protocol("WM_DELETE_WINDOW", self.close)
        top.bind("<Escape>", lambda e: self.close())

        shell = tk.Frame(top, bg=CARD, highlightthickness=1, highlightbackground=LINE)
        shell.pack(fill="both", expand=True)

        head = tk.Frame(shell, bg=PRIMARY, height=S(46))
        head.pack(fill="x")
        head.pack_propagate(False)
        tk.Label(head, text="该喝水啦", font=F["btn"], fg="#FFFFFF", bg=PRIMARY).pack(
            side="left", padx=(S(20), 0))
        self.head_time = tk.Label(head, text=datetime.now().strftime("%H:%M"),
                                  font=F["btn_small"], fg="#DCEBFF", bg=PRIMARY)
        self.head_time.pack(side="right", padx=(0, S(10)))
        close_btn = tk.Label(head, text="✕", font=F["glyph_hd"], fg="#DCEBFF", bg=PRIMARY,
                             cursor="hand2")
        close_btn.pack(side="right", padx=(0, S(6)))
        close_btn.bind("<Button-1>", lambda e: self.close())

        body = tk.Frame(shell, bg=CARD)
        body.pack(fill="both", expand=True)

        # 水滴 + “+1” 气泡
        self.cx = w // 2
        self.visual = tk.Canvas(body, bg=CARD, height=S(92), highlightthickness=0)
        self.visual.pack(fill="x", pady=(S(14), 0))
        draw_droplet_wrapped(self.visual, self.cx, S(44), S(78))
        self.bubble = self.visual.create_oval(0, 0, 0, 0, fill=TINT, outline="")
        self.bubble_text = self.visual.create_text(0, 0, text="+1", fill=PRIMARY,
                                                   font=F["btn_small"])

        self.quote = tk.Label(body, text="", font=F["quote"], fg=INK, bg=CARD,
                              justify="center")
        self.quote.pack(fill="x", padx=S(24), pady=(S(4), 0))

        # 今日进度
        n = app._today_done()
        goal = max(1, app.cfg["goal"])
        self.progress = tk.Canvas(body, bg=CARD, height=S(10), highlightthickness=0)
        self.progress.pack(fill="x", padx=S(24), pady=(S(12), 0))
        self._draw_progress(n, goal)
        self.detail = tk.Label(
            body, fg=MUTED, bg=CARD, font=F["small"],
            text=f"今日已喝 {n}/{goal} 杯 · 糖分 {app.today_sugar():.0f}/{app.sugar_limit():.0f}g")
        self.detail.pack(pady=(S(7), 0))

        # 按钮区
        foot = tk.Frame(body, bg=CARD)
        foot.pack(side="bottom", fill="x", padx=S(22), pady=(S(8), S(14)))
        hint = tk.Label(foot, fg=P.FAINT, bg=CARD, font=F["tiny"], justify="center",
                        text=f"「稍后」{app.cfg['snooze_min']} 分钟后再提醒 · 双击也能稍后 · Esc 关闭")
        hint.pack(side="bottom", pady=(S(10), 0))
        btns = tk.Frame(foot, bg=CARD)
        btns.pack(side="bottom", fill="x")
        third = (w - S(44) - S(16)) // 3
        self.btn_done = RoundedButton(btns, "喝水", self.done, variant="primary",
                                      height=S(44), width=third, icon="✓", font=F["btn"])
        self.btn_done.pack(side="left")
        self.btn_drink = RoundedButton(btns, "喝饮料", self.open_drink, variant="amber",
                                       height=S(44), width=third, icon="▸", font=F["btn"])
        self.btn_drink.pack(side="left", padx=S(8))
        self.btn_snooze = RoundedButton(btns, "稍后", self.snoozle, variant="secondary",
                                        height=S(44), width=third, icon="◷", font=F["btn"])
        self.btn_snooze.pack(side="right")

        for wdg in (self.visual, self.quote, self.detail):
            wdg.bind("<Double-Button-1>", lambda e: self.snoozle())

        self._pick_quote()
        self._fit_geometry()
        self._pulse(0)
        top.deiconify()

        if app.cfg["gentle"]:
            flash_taskbar(top)
        else:
            show_window(top)

    def _draw_progress(self, done: int, goal: int):
        cv = self.progress
        cv.delete("all")
        cv.update_idletasks()
        w = cv.winfo_width()
        if w <= 1:
            w = max(S(120), self._w - S(48))
        h = S(10)
        ratio = min(1.0, done / max(1, goal))
        cv.create_line(0, h // 2, w, h // 2, fill="#E7EEF8", width=h, capstyle="round")
        if ratio > 0:
            cv.create_line(0, h // 2, max(h, int(w * ratio)), h // 2,
                           fill=TEAL if ratio >= 1 else PRIMARY, width=h, capstyle="round")

    def _fit_geometry(self):
        """按内容定尺寸，并紧挨主界面显示；主界面移动时跟随。"""
        top = self.top
        top.update_idletasks()
        w = min(max(self._w, top.winfo_reqwidth()), int(top.winfo_screenwidth() * 0.96))
        h = min(top.winfo_reqheight(), int(top.winfo_screenheight() * 0.9))
        x, y = follow_main_position(self.app.win, w, h)
        top.geometry(f"{w}x{h}+{x}+{y}")
        top.update_idletasks()
        self._bind_follow()

    def _bind_follow(self):
        try:
            self._follow_id = self.app.win.bind("<Configure>",
                                                self._on_main_configure, add="+")
        except tk.TclError:
            self._follow_id = None

    def _on_main_configure(self, event):
        if event.widget is not self.app.win:
            return
        try:
            if not self.top.winfo_exists():
                return
            self.top.update_idletasks()
            x, y = follow_main_position(self.app.win, self.top.winfo_width(),
                                        self.top.winfo_height())
            self.top.geometry(f"+{x}+{y}")
        except tk.TclError:
            pass

    def _unbind_follow(self):
        if getattr(self, "_follow_id", None):
            try:
                self.app.win.unbind("<Configure>", self._follow_id)
            except tk.TclError:
                pass
            self._follow_id = None

    def _pick_quote(self):
        text = random.choice(self.app.cfg["quotes"])
        f = tkfont.Font(font=self.quote.cget("font"))
        width = max(S(200), self._w - S(56))
        self.quote.configure(text=wrap_paragraph(text, width, f, letter_gap=True),
                             wraplength=width)

    def _pulse(self, i):
        try:
            t = (i % 30) / 30.0
            cy = S(26) - t * S(16)
            r = S(14)
            bx = self.cx + S(40)
            self.visual.coords(self.bubble, bx - r, cy - r, bx + r, cy + r)
            self.visual.coords(self.bubble_text, bx, cy)
        except tk.TclError:
            return
        self.top.after(70, lambda: self._pulse(i + 1))

    def done(self):
        self.app.on_reminder_done(None)

    def open_drink(self):
        self.close()
        self.app.open_drink_dialog()

    def snoozle(self):
        self.app.on_reminder_done(self.app.cfg["snooze_min"])

    def close(self):
        self._unbind_follow()
        try:
            self.top.destroy()
        except tk.TclError:
            pass
        self.app.popup_closed()


# ---------------------------------------------------------------- 系统托盘 --

class TrayIcon:
    """系统托盘图标（Win32 Shell_NotifyIcon）。失败只让 ok=False，不影响主功能。"""

    WM_TRAY = 0x0400 + 20
    WM_TRAY_CMD = 0x0400 + 21
    NIM_ADD, NIM_MODIFY, NIM_DELETE = 0, 1, 2
    NIF_MESSAGE, NIF_ICON, NIF_TIP, NIF_INFO = 0x1, 0x2, 0x4, 0x10
    NIIF_INFO = 0x1
    PM_REMOVE = 0x0001

    def __init__(self, app: "WaterReminderApp"):
        self.app = app
        self.ok = False
        self.hwnd = None
        self._alive = True
        self._thread = None
        self._nid = None
        self._nid_type = None
        self._hicon = None
        self._wndproc_ref = None
        self._msg_type = None
        self._error = ""
        self._installed = False
        if sys.platform != "win32":
            return
        ready = threading.Event()
        try:
            self._thread = threading.Thread(target=self._run, args=(ready,), daemon=True,
                                            name="tray-icon")
            self._thread.start()
            ready.wait(3.0)
            self.ok = bool(self._installed)
        except Exception:  # noqa: BLE001
            self.ok = False

    # ---- 图标绘制 ----
    def _make_icon(self, ctypes, size=32):
        class ICONINFO(ctypes.Structure):
            _fields_ = [("fIcon", ctypes.c_int), ("xHotspot", ctypes.c_uint),
                        ("yHotspot", ctypes.c_uint), ("hbmMask", ctypes.c_void_p),
                        ("hbmColor", ctypes.c_void_p)]

        class BITMAPINFOHEADER(ctypes.Structure):
            _fields_ = [("biSize", ctypes.c_uint), ("biWidth", ctypes.c_long),
                        ("biHeight", ctypes.c_long), ("biPlanes", ctypes.c_ushort),
                        ("biBitCount", ctypes.c_ushort), ("biCompression", ctypes.c_uint),
                        ("biSizeImage", ctypes.c_uint), ("biXPelsPerMeter", ctypes.c_long),
                        ("biYPelsPerMeter", ctypes.c_long), ("biClrUsed", ctypes.c_uint),
                        ("biClrImportant", ctypes.c_uint)]

        gdi = ctypes.windll.gdi32
        user32 = ctypes.windll.user32
        # 显式原型，否则 64 位下指针会被截断
        gdi.CreateDIBSection.restype = ctypes.c_void_p
        gdi.CreateDIBSection.argtypes = [ctypes.c_void_p, ctypes.c_void_p, ctypes.c_uint,
                                         ctypes.POINTER(ctypes.c_void_p), ctypes.c_void_p,
                                         ctypes.c_uint]
        gdi.CreateBitmap.restype = ctypes.c_void_p
        gdi.CreateBitmap.argtypes = [ctypes.c_void_p, ctypes.c_int, ctypes.c_int,
                                     ctypes.c_uint, ctypes.c_void_p]
        gdi.DeleteObject.argtypes = [ctypes.c_void_p]
        user32.GetDC.restype = ctypes.c_void_p
        user32.GetDC.argtypes = [ctypes.c_void_p]
        user32.ReleaseDC.argtypes = [ctypes.c_void_p, ctypes.c_void_p]
        user32.CreateIconIndirect.restype = ctypes.c_void_p
        user32.CreateIconIndirect.argtypes = [ctypes.c_void_p]

        hheader = BITMAPINFOHEADER(ctypes.sizeof(BITMAPINFOHEADER), size, -size, 1, 32, 0,
                                   size * size * 4, 0, 0, 0, 0)
        bits = ctypes.c_void_p()
        hdc = user32.GetDC(None)
        hbm = gdi.CreateDIBSection(hdc, ctypes.byref(hheader), 0, ctypes.byref(bits), None, 0)
        if not hbm or not bits.value:
            if hbm:
                gdi.DeleteObject(ctypes.c_void_p(hbm))
            user32.ReleaseDC(None, ctypes.c_void_p(hdc))
            raise OSError("CreateDIBSection failed")
        buf = (ctypes.c_ubyte * (size * size * 4)).from_address(bits.value)
        for y in range(size):
            for x in range(size):
                cov = drop_coverage(x + 0.5, y + 0.5, size)
                if cov <= 0:
                    continue
                i = (y * size + x) * 4
                hi = math.hypot(x + 0.5 - size * 0.40, y + 0.5 - size * 0.55) < size * 0.11
                r_, g_, b_ = (0xB8, 0xD6, 0xFF) if hi else (0x3E, 0x8E, 0xF7)
                buf[i], buf[i + 1], buf[i + 2], buf[i + 3] = b_, g_, r_, int(255 * cov)
        mask = gdi.CreateBitmap(size, size, 1, 1, None)
        info = ICONINFO(1, 0, 0, mask, hbm)
        hicon = user32.CreateIconIndirect(ctypes.byref(info))
        gdi.DeleteObject(ctypes.c_void_p(mask))
        gdi.DeleteObject(ctypes.c_void_p(hbm))
        if not hicon:
            raise OSError("CreateIconIndirect failed")
        return hicon

    # ---- 窗口与消息 ----
    def _run(self, ready):
        import ctypes
        from ctypes import wintypes as wt

        DWORD = wt.DWORD
        WNDPROC = ctypes.WINFUNCTYPE(ctypes.c_void_p, wt.HWND, wt.UINT, ctypes.c_size_t,
                                     ctypes.c_size_t)

        class WNDCLASSW(ctypes.Structure):
            _fields_ = [("style", wt.UINT), ("lpfnWndProc", WNDPROC),
                        ("cbClsExtra", ctypes.c_int), ("cbWndExtra", ctypes.c_int),
                        ("hInstance", wt.HINSTANCE), ("hIcon", wt.HICON),
                        ("hCursor", wt.HANDLE), ("hbrBackground", wt.HBRUSH),
                        ("lpszMenuName", wt.LPCWSTR), ("lpszClassName", wt.LPCWSTR)]

        class NOTIFYICONDATAW(ctypes.Structure):
            _fields_ = [("cbSize", DWORD), ("hWnd", wt.HWND), ("uID", wt.UINT),
                        ("uFlags", wt.UINT), ("uCallbackMessage", wt.UINT),
                        ("hIcon", wt.HICON), ("szTip", wt.WCHAR * 128),
                        ("dwState", DWORD), ("dwStateMask", DWORD),
                        ("szInfo", wt.WCHAR * 256), ("uVersion", wt.UINT),
                        ("szInfoTitle", wt.WCHAR * 64), ("dwInfoFlags", DWORD),
                        ("guidItem", ctypes.c_byte * 16), ("hBalloonIcon", wt.HICON)]

        class MSG(ctypes.Structure):
            _fields_ = [("hwnd", wt.HWND), ("message", wt.UINT), ("wParam", ctypes.c_size_t),
                        ("lParam", ctypes.c_size_t), ("time", DWORD), ("pt", wt.POINT)]

        try:
            user32 = ctypes.windll.user32
            kernel32 = ctypes.windll.kernel32
            wndproc = WNDPROC(self._wndproc)
            self._wndproc_ref = wndproc
            hinst = kernel32.GetModuleHandleW(None)
            cls = WNDCLASSW()
            cls.lpfnWndProc = wndproc
            cls.hInstance = hinst
            cls.lpszClassName = APP_ID
            if not user32.RegisterClassW(ctypes.byref(cls)):
                raise OSError("RegisterClassW failed")
            self.hwnd = user32.CreateWindowExW(0, APP_ID, APP_ID, 0, 0, 0, 0, 0,
                                               None, None, hinst, None)
            if not self.hwnd:
                raise OSError("CreateWindowExW failed")
            self._hicon = self._make_icon(ctypes)
            nid = NOTIFYICONDATAW()
            nid.cbSize = ctypes.sizeof(NOTIFYICONDATAW)
            nid.hWnd = self.hwnd
            nid.uID = 1
            nid.uFlags = self.NIF_MESSAGE | self.NIF_ICON | self.NIF_TIP
            nid.uCallbackMessage = self.WM_TRAY
            nid.hIcon = self._hicon
            nid.szTip = f"{APP_NAME} · 每 {self.app.cfg['interval_min']} 分钟提醒"
            if not _shell32().Shell_NotifyIconW(self.NIM_ADD, ctypes.byref(nid)):
                raise OSError("Shell_NotifyIconW(NIM_ADD) failed")
            self._nid, self._nid_type, self._msg_type = nid, NOTIFYICONDATAW, MSG
            self._installed = True
        except Exception as exc:  # noqa: BLE001
            self._error = f"{type(exc).__name__}: {exc}"
            self._installed = False
            ready.set()
            return
        ready.set()

        msg = MSG()
        while self._alive:
            try:
                while user32.PeekMessageW(ctypes.byref(msg), None, 0, 0, self.PM_REMOVE):
                    user32.TranslateMessage(ctypes.byref(msg))
                    user32.DispatchMessageW(ctypes.byref(msg))
            except Exception:  # noqa: BLE001
                pass
            time.sleep(0.05)

    def _wndproc(self, hwnd, msg, wparam, lparam):
        import ctypes
        try:
            if msg == self.WM_TRAY:
                event = int(lparam) & 0xFFFF
                if event in (0x0201, 0x0202):
                    self.app.after(0, self.app.restore)
                elif event == 0x0205:
                    self._menu()
            elif msg == self.WM_TRAY_CMD:
                self._command(int(wparam) & 0xFFFF)
        except Exception:  # noqa: BLE001
            pass
        return ctypes.windll.user32.DefWindowProcW(ctypes.c_void_p(hwnd), msg,
                                                   ctypes.c_size_t(wparam),
                                                   ctypes.c_void_p(lparam))

    def _command(self, cmd):
        actions = {1: self.app.restore, 2: self.app.toggle_run,
                   3: self.app.drink, 4: self.app.quit}
        action = actions.get(cmd)
        if action is not None:
            self.app.after(0, action)

    def _menu(self):
        import ctypes
        user32 = ctypes.windll.user32
        hmenu = user32.CreatePopupMenu()
        user32.AppendMenuW(hmenu, 0, 1, "打开主界面")
        user32.AppendMenuW(hmenu, 0, 2, "暂停提醒" if self.app.running else "继续提醒")
        user32.AppendMenuW(hmenu, 0, 3, "记录一杯水")
        user32.AppendMenuW(hmenu, 0x800, 0, None)
        user32.AppendMenuW(hmenu, 0, 4, "关闭程序")
        pt = ctypes.wintypes.POINT()
        user32.GetCursorPos(ctypes.byref(pt))
        user32.SetForegroundWindow(self.hwnd)
        cmd = user32.TrackPopupMenu(hmenu, 0x0180, pt.x, pt.y, 0, self.hwnd, None)
        user32.PostMessageW(self.hwnd, 0x0000, 0, 0)
        user32.DestroyMenu(hmenu)
        if cmd:
            self._command(cmd)

    # ---- 气泡 / 提示 ----
    def notify(self, title, text):
        if not self.ok or self._nid is None:
            return
        try:
            import ctypes
            self._nid.uFlags = self.NIF_INFO
            self._nid.szInfo = text[:250]
            self._nid.szInfoTitle = title[:60]
            self._nid.dwInfoFlags = self.NIIF_INFO
            _shell32().Shell_NotifyIconW(self.NIM_MODIFY, ctypes.byref(self._nid))
        except Exception:  # noqa: BLE001
            pass

    def update_tip(self):
        if not self.ok or self._nid is None:
            return
        try:
            import ctypes
            state = "运行中" if self.app.running else "已暂停"
            self._nid.uFlags = self.NIF_TIP
            self._nid.szTip = f"{APP_NAME} · {state} · 每 {self.app.cfg['interval_min']} 分钟"
            _shell32().Shell_NotifyIconW(self.NIM_MODIFY, ctypes.byref(self._nid))
        except Exception:  # noqa: BLE001
            pass

    def close(self):
        self._alive = False
        try:
            if self._nid is not None:
                import ctypes
                _shell32().Shell_NotifyIconW(self.NIM_DELETE, ctypes.byref(self._nid))
        except Exception:  # noqa: BLE001
            pass
        self.ok = False


# ------------------------------------------------------------ 全局快捷键 --
class GlobalHotkeys:
    """Windows 全局热键：Ctrl+Alt+W 记一杯水 / Ctrl+Alt+P 暂停或继续。

    用独立的隐藏窗口 + 消息循环线程接收 WM_HOTKEY，回调通过 app.after 投递
    到主线程执行（不在后台线程碰 tkinter）。注册失败只降级、不影响主功能。
    """

    WM_HOTKEY = 0x0312
    WM_EXIT = 0x0400 + 55
    MOD_ALT, MOD_CONTROL, MOD_NOREPEAT = 0x0001, 0x0002, 0x4000
    VK_W, VK_P = 0x57, 0x50
    CLASS = "WaterReminderHotkey"

    def __init__(self, app: "WaterReminderApp"):
        self.app = app
        self.ok = False
        self.hwnd = None
        self._alive = True
        self._thread = None
        self._wndproc_ref = None
        self._error = ""
        self._hinst = None
        self._class_registered = False
        if sys.platform != "win32":
            return
        try:
            import ctypes
            from ctypes import wintypes as wt
            self._ctypes, self._wt = ctypes, wt
            ready = threading.Event()
            self._thread = threading.Thread(target=self._run, args=(ready,), daemon=True,
                                            name="global-hotkey")
            self._thread.start()
            ready.wait(3.0)
            self.ok = bool(self.hwnd)
        except Exception as exc:  # noqa: BLE001
            self.ok = False
            self._error = f"{type(exc).__name__}: {exc}"

    def _wndproc(self, hwnd, msg, wparam, lparam):
        ctypes = self._ctypes
        try:
            if msg == self.WM_HOTKEY:
                action = self.app.drink if int(wparam) == 1 else self.app.toggle_run
                self.app.after(0, action)
            elif msg == self.WM_EXIT:
                self._alive = False
        except Exception:  # noqa: BLE001
            pass
        return ctypes.windll.user32.DefWindowProcW(ctypes.c_void_p(hwnd), msg,
                                                   ctypes.c_size_t(wparam),
                                                   ctypes.c_void_p(lparam))

    def _run(self, ready):
        ctypes = self._ctypes
        wt = self._wt
        WNDPROC = ctypes.WINFUNCTYPE(ctypes.c_void_p, wt.HWND, wt.UINT, ctypes.c_size_t,
                                     ctypes.c_size_t)

        class WNDCLASSW(ctypes.Structure):
            _fields_ = [("style", wt.UINT), ("lpfnWndProc", WNDPROC),
                        ("cbClsExtra", ctypes.c_int), ("cbWndExtra", ctypes.c_int),
                        ("hInstance", wt.HINSTANCE), ("hIcon", wt.HICON),
                        ("hCursor", wt.HANDLE), ("hbrBackground", wt.HBRUSH),
                        ("lpszMenuName", wt.LPCWSTR), ("lpszClassName", wt.LPCWSTR)]

        class MSG(ctypes.Structure):
            _fields_ = [("hwnd", wt.HWND), ("message", wt.UINT),
                        ("wParam", ctypes.c_size_t), ("lParam", ctypes.c_size_t),
                        ("time", wt.DWORD), ("pt", wt.POINT)]

        user32 = ctypes.windll.user32
        kernel32 = ctypes.windll.kernel32
        registered = []
        try:
            wndproc = WNDPROC(self._wndproc)
            self._wndproc_ref = wndproc
            hinst = kernel32.GetModuleHandleW(None)
            cls = WNDCLASSW()
            cls.lpfnWndProc = wndproc
            cls.hInstance = hinst
            cls.lpszClassName = self.CLASS
            if not user32.RegisterClassW(ctypes.byref(cls)):
                raise OSError("RegisterClassW failed")
            self._class_registered = True
            self._hinst = hinst
            hwnd = user32.CreateWindowExW(0, self.CLASS, self.CLASS, 0, 0, 0, 0, 0,
                                          None, None, hinst, None)
            if not hwnd:
                raise OSError("CreateWindowExW failed")
            self.hwnd = hwnd
            mods = self.MOD_CONTROL | self.MOD_ALT | self.MOD_NOREPEAT
            for hid, vk in ((1, self.VK_W), (2, self.VK_P)):
                if user32.RegisterHotKey(hwnd, hid, mods, vk):
                    registered.append(hid)
        except Exception as exc:  # noqa: BLE001
            self._error = f"{type(exc).__name__}: {exc}"
            self.hwnd = None
        ready.set()
        if not self.hwnd:
            return

        msg = MSG()
        while self._alive:
            try:
                while user32.PeekMessageW(ctypes.byref(msg), None, 0, 0, 0x0001):
                    user32.TranslateMessage(ctypes.byref(msg))
                    user32.DispatchMessageW(ctypes.byref(msg))
            except Exception:  # noqa: BLE001
                pass
            time.sleep(0.05)
        for hid in registered:
            try:
                user32.UnregisterHotKey(hwnd, hid)
            except Exception:  # noqa: BLE001
                pass
        try:
            user32.DestroyWindow(hwnd)
        except Exception:  # noqa: BLE001
            pass

    def close(self):
        self._alive = False
        if self.hwnd is not None:
            try:
                self._ctypes.windll.user32.PostMessageW(
                    ctypes_void_p(self.hwnd), self.WM_EXIT, 0, 0)
            except Exception:  # noqa: BLE001
                pass
        # 等消息循环线程真正退出后再反注册窗口类，否则下次开启 RegisterClassW 会失败
        if self._thread is not None and self._thread.is_alive():
            self._thread.join(timeout=2.0)
        if self._class_registered and self._hinst is not None:
            try:
                self._ctypes.windll.user32.UnregisterClassW(self.CLASS,
                                                            ctypes_void_p(self._hinst))
            except Exception:  # noqa: BLE001
                pass
            self._class_registered = False
        self.hwnd = None
        self.ok = False


def ctypes_void_p(value):
    import ctypes
    return ctypes.c_void_p(value)


# ---------------------------------------------------------------- 启动脚本 --

def _pythonw_candidates() -> list:
    found = []
    pyw = Path(sys.executable).with_name("pythonw.exe")
    if pyw.exists():
        found.append(str(pyw))
    found.append("pythonw.exe")
    try:
        import glob
        pattern = str(Path(os.environ.get("LOCALAPPDATA", "")) / "Programs" / "Python"
                      / "Python3*" / "pythonw.exe")
        found.extend(sorted(glob.glob(pattern), reverse=True))
        for base in (os.environ.get("PROGRAMFILES", ""), os.environ.get("PROGRAMFILES(X86)", "")):
            if base:
                found.extend(sorted(glob.glob(str(Path(base) / "Python3*" / "pythonw.exe")),
                                    reverse=True))
    except OSError:
        pass
    return found


def launch_script() -> str:
    """无黑框启动脚本（用于开机自启）。"""
    def q(value) -> str:
        # VBScript 字符串里的双引号要写成两个双引号
        return str(value).replace('"', '""')

    target = q(BASE_DIR)
    script = q(Path(BASE_DIR) / "water_reminder.py")
    attempts = "\n".join(
        f'    Err.Clear\n    sh.Run """{q(exe)}"" ""{script}""", 0, False\n'
        f"    If Err.Number = 0 Then WScript.Quit 0\n"
        for exe in _pythonw_candidates())
    return (
        "' 喝水提醒 · 后台启动（不显示控制台窗口）\n"
        "Option Explicit\n"
        "Dim fso, sh\n"
        "Set fso = CreateObject(\"Scripting.FileSystemObject\")\n"
        "Set sh = CreateObject(\"WScript.Shell\")\n"
        f"sh.CurrentDirectory = \"{target}\"\n"
        f"{attempts}"
        "MsgBox \"没有找到 pythonw.exe，请先安装 Python 3，或改用「启动喝水提醒.bat」。\", "
        "vbExclamation, \"喝水提醒\"\n"
    )


def write_vbs(path: Path, content: str) -> None:
    """VBS 以 UTF-16LE + BOM 写盘（WScript 只认 ANSI 或带 BOM 的 UTF-16）。"""
    path.write_bytes(b"\xff\xfe" + content.replace("\n", "\r\n").encode("utf-16-le"))


def write_launch_files() -> None:
    try:
        write_vbs(BASE_DIR / "启动喝水提醒.vbs", launch_script())
        # 用 bytes 写入，避免文本模式把 \r\n 再转成 \r\r\n
        (BASE_DIR / "启动喝水提醒.bat").write_bytes(
            ("@echo off\r\n"
             "cd /d \"%~dp0\"\r\n"
             "start \"\" pythonw water_reminder.py\r\n").encode("gbk", errors="replace"))
    except OSError:
        pass


# ---------------------------------------------------------------- 入口 --

_MUTEX_HANDLE = None


def already_running() -> bool:
    """单实例检测（Windows 命名互斥量）。

    必须用 use_last_error=True 的 WinDLL 读错误码；ACCESS_DENIED(5) 也说明同名对象已存在。
    """
    global _MUTEX_HANDLE
    if sys.platform != "win32":
        return False
    ERROR_ALREADY_EXISTS, ERROR_ACCESS_DENIED = 183, 5
    try:
        import ctypes
        kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
        kernel32.CreateMutexW.restype = ctypes.c_void_p
        kernel32.CreateMutexW.argtypes = [ctypes.c_void_p, ctypes.c_bool, ctypes.c_wchar_p]
        handle = kernel32.CreateMutexW(None, True, f"Local\\{APP_ID}_single_instance")
        err = ctypes.get_last_error()
        if err == ERROR_ALREADY_EXISTS:
            if handle:
                kernel32.CloseHandle(ctypes.c_void_p(handle))
            return True
        if not handle:
            return err == ERROR_ACCESS_DENIED
        _MUTEX_HANDLE = handle
    except Exception:  # noqa: BLE001
        return False
    return False


def restore_running_instance() -> bool:
    """找到已在运行的实例窗口并唤到前台。

    收进托盘时窗口是 withdraw（不可见）状态，所以不能只认可见窗口；
    用 PID 是否存活区分「真实例」与崩溃残留窗口。
    """
    if sys.platform != "win32":
        return False
    try:
        import ctypes
        from ctypes import wintypes as wt

        user32 = ctypes.windll.user32
        kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
        kernel32.OpenProcess.restype = ctypes.c_void_p
        kernel32.OpenProcess.argtypes = [ctypes.c_uint, ctypes.c_bool, ctypes.c_uint]
        kernel32.CloseHandle.argtypes = [ctypes.c_void_p]
        PROCESS_QUERY_LIMITED_INFORMATION = 0x1000

        def pid_alive(pid: int) -> bool:
            handle = kernel32.OpenProcess(PROCESS_QUERY_LIMITED_INFORMATION, False, pid)
            if not handle:
                return False
            try:
                buf = ctypes.create_unicode_buffer(32768)
                size = wt.DWORD(32768)
                ok_ = kernel32.QueryFullProcessImageNameW(ctypes.c_void_p(handle), 0, buf,
                                                          ctypes.byref(size))
                return bool(ok_ and buf.value)
            finally:
                kernel32.CloseHandle(ctypes.c_void_p(handle))

        found = []

        @ctypes.WINFUNCTYPE(wt.BOOL, wt.HWND, wt.LPARAM)
        def _enum(hwnd, _lparam):
            if user32.GetWindowTextLengthW(hwnd) <= 0:
                return True
            buf = ctypes.create_unicode_buffer(256)
            user32.GetWindowTextW(hwnd, buf, 256)
            if buf.value != APP_NAME:
                return True
            pid = wt.DWORD()
            user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
            if pid.value == os.getpid():
                return True
            if pid_alive(pid.value):
                found.append(hwnd)
            return True

        user32.EnumWindows(_enum, 0)
        if not found:
            return False
        hwnd = found[0]
        if user32.IsIconic(hwnd):
            user32.ShowWindow(hwnd, 9)       # SW_RESTORE
        else:
            user32.ShowWindow(hwnd, 5)       # SW_SHOW
        user32.SetForegroundWindow(hwnd)
        user32.BringWindowToTop(hwnd)
        return True
    except Exception:  # noqa: BLE001
        return False


def main():
    # 有实例（含收在托盘的）→ 唤回原窗口；由互斥量判定，避免残留窗口让程序打不开。
    if already_running():
        for _ in range(10):
            if restore_running_instance():
                break
            time.sleep(0.4)
        return
    app = WaterReminderApp()
    write_launch_files()
    if app.cfg["autostart"] and not app._autostart_exists():
        app._set_autostart(True)
    app.run()


if __name__ == "__main__":
    main()
