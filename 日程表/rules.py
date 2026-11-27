# -*- coding: utf-8 -*-
"""
rules.py —— 分区与排序规则

设计原则
--------
1. 纯函数：不读文件、不碰界面、不依赖当前时间（`now` 一律作为参数传入），
   所以可以用固定时间点写断言测试。
2. 存储只认三种状态（pending / someday / done）；界面上看到的五种状态
   （待设时间、进行中、已过期、不急、已完成）全部由 :func:`bucket_of` 推导。
   好处是"过期"不需要定时任务去刷字段，打开程序算一遍就是对的。
3. 规则改了只改这个文件，界面层不用动。
"""

from __future__ import annotations

import re
from datetime import datetime, time as dtime, timedelta
from typing import Any, Dict, Iterable, List, Optional, Tuple

# ---- 存储状态（唯一会被写进 data.json 的值） ----
STATUS_PENDING = "pending"
STATUS_SOMEDAY = "someday"
STATUS_DONE = "done"

# ---- 界面分区（推导值，不落库） ----
B_NODUE = "no_due"        # 无截止时间 → 置顶高亮
B_LIVE = "active"         # 进行中
B_EXPIRED = "expired"     # 已过期 → 原位标红
B_SOMEDAY = "someday"     # 不急 → 独立折叠区（仅人工标记）
B_DONE = "done"           # 已完成 → 独立折叠区灰化

TIMELINE_BUCKETS = (B_LIVE, B_EXPIRED)


# --------------------------------------------------------------------------
# 时间解析：接受用户可能敲进来的几种写法，解析不了就返回 None（绝不猜）
# --------------------------------------------------------------------------
def parse_dt(value: Any) -> Optional[datetime]:
    if value is None or value == "":
        return None
    if isinstance(value, datetime):
        return value
    s = str(value).strip()
    if not s:
        return None
    s = s.replace("/", "-").replace("T", " ").strip()

    for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%d %H:%M", "%Y-%m-%d"):
        try:
            return datetime.strptime(s, fmt)
        except ValueError:
            pass

    now = datetime.now()
    # 不写年份的写法：显式补当前年，避免 strptime 在 3.15 起对缺年份的处理变化
    m = re.fullmatch(r"(\d{1,2})-(\d{1,2})", s)
    if m:
        try:
            return datetime(now.year, int(m.group(1)), int(m.group(2)))
        except ValueError:
            return None
    m = re.fullmatch(r"(\d{1,2})-(\d{1,2})\s+(\d{1,2}):(\d{2})", s)
    if m:
        try:
            return datetime(now.year, int(m.group(1)), int(m.group(2)),
                            int(m.group(3)), int(m.group(4)))
        except ValueError:
            return None

    try:  # 只给时间 → 今天
        t = datetime.strptime(s, "%H:%M")
        return now.replace(hour=t.hour, minute=t.minute, second=0, microsecond=0)
    except ValueError:
        pass

    try:  # 带时区的 ISO
        return datetime.fromisoformat(s).replace(tzinfo=None)
    except ValueError:
        return None


def to_iso(dt: Optional[datetime]) -> Optional[str]:
    return dt.strftime("%Y-%m-%dT%H:%M:%S") if dt else None


# --------------------------------------------------------------------------
# 中文时间表述 → 具体时间
#
# 上面 :func:`parse_dt` 只认"已经把年份写清楚"的字符串。图片里的通知大多不写
# 年份——群里发的"12月8日交报告""下周三之前报名"，年份得靠上下文推。规则：
#
#   只写月日  → 先按今年算；**今年的那一天已经过了，就顺延到明年**
#               （学期跨年很常见：11 月贴出的"1月5日"指的是明年 1 月）
#   写星期    → 取**最近的下一个**该星期几（今天正好是它、钟点还没过，就取今天；
#               今天已经过了它，就往后推到下周的同一天）
#   "下周X"   → 下一周的星期 X；"这周X / 本周X" → 本周那一天（过了就是过去了）
#   写第N周   → 返回 None，不换算（既定规则：周次交人工，见策划案 5.4）
#
# 只给日期不给钟点时统一补 23:59——这些表述都是"截止"语义，不是开始时间。
# --------------------------------------------------------------------------
_CN_WEEKDAY = {
    "一": 1, "二": 2, "三": 3, "四": 4, "五": 5, "六": 6, "日": 7, "天": 7,
    "1": 1, "2": 2, "3": 3, "4": 4, "5": 5, "6": 6, "7": 7,
}

# 长的写在前，否则"下周三"会被后面的"周"抢走
_WEEKDAY_RE = re.compile(
    r"(下周|下星期|下礼拜|这周|这个星期|本周|本星期|周|星期|礼拜)\s*([一二三四五六日天1-7])")
_WEEK_NUMBER_RE = re.compile(r"第\s*[0-9一二三四五六七八九十百]+\s*周")
_FULL_DATE_RE = re.compile(r"(\d{4})\s*[年\-/.]\s*(\d{1,2})\s*[月\-/.]\s*(\d{1,2})")
_MONTH_DAY_RE = re.compile(r"(?<!\d)(\d{1,2})\s*[月\-/.]\s*(\d{1,2})(?!\d)")
_CLOCK_COLON_RE = re.compile(r"(上午|下午|中午|晚上|傍晚|早上|凌晨)?\s*(\d{1,2})\s*[:：]\s*(\d{1,2})")
_CLOCK_CN_RE = re.compile(r"(上午|下午|中午|晚上|傍晚|早上|凌晨)?\s*(\d{1,2})\s*[点时](?:\s*(\d{1,2})\s*分)?")
_RELATIVE_DAYS = (("大后天", 3), ("后天", 2), ("明天", 1), ("明日", 1), ("今天", 0), ("今日", 0))

DEFAULT_HOUR = 23
DEFAULT_MINUTE = 59


def mentions_week_number(text: Any) -> bool:
    """是否含"第13周"这类周次表述——含则一律不换算。"""
    return bool(text) and bool(_WEEK_NUMBER_RE.search(str(text)))


def _clock(text: str) -> Optional[Tuple[int, int]]:
    """抠出钟点，认 `9:00` `9点` `9点半` `下午2:30` 这几种写法。"""
    for pattern in (_CLOCK_COLON_RE, _CLOCK_CN_RE):
        m = pattern.search(text)
        if not m:
            continue
        mark = m.group(1) or ""
        hh, mm = int(m.group(2)), int(m.group(3) or 0)
        if mark in ("下午", "晚上", "傍晚", "中午") and hh < 12:
            hh += 12
        elif mark == "凌晨" and hh == 12:
            hh = 0
        if 0 <= hh <= 23 and 0 <= mm <= 59:
            return hh, mm
    return None


def _with_clock(day: datetime, clock: Optional[Tuple[int, int]]) -> datetime:
    hh, mm = clock if clock else (DEFAULT_HOUR, DEFAULT_MINUTE)
    return day.replace(hour=hh, minute=mm, second=0, microsecond=0)


def resolve_text_due(text: Any, now: Optional[datetime] = None) -> Optional[datetime]:
    """把一段中文时间表述解析成具体时间；解析不出来返回 None（绝不猜）。

    这是图片识别的兜底：模型只负责照抄原文，日期换算放在这里做——纯函数、
    可单测、换模型也不会变。
    """
    if not text:
        return None
    s = str(text).strip()
    if not s or mentions_week_number(s):
        return None
    now = now or datetime.now()
    clock = _clock(s)
    today = now.date()

    m = _FULL_DATE_RE.search(s)          # 写明年份：原样用，不做任何漂移
    if m:
        try:
            return _with_clock(datetime(int(m.group(1)), int(m.group(2)), int(m.group(3))), clock)
        except ValueError:
            return None

    m = _WEEKDAY_RE.search(s)
    if m:
        target = _CN_WEEKDAY[m.group(2)]
        prefix = m.group(1)
        if prefix.startswith("下"):
            monday = today + timedelta(days=7 - today.weekday())
        elif prefix in ("这周", "这个星期", "本周", "本星期"):
            monday = today - timedelta(days=today.weekday())
        else:
            # 裸"周五"：最近的下一个。今天就是周五 → 取今天；今天已过周五 → 推到下周
            delta = (target - 1 - today.weekday()) % 7
            return _with_clock(datetime.combine(today + timedelta(days=delta), dtime.min), clock)
        return _with_clock(datetime.combine(monday + timedelta(days=target - 1), dtime.min), clock)

    for word, offset in _RELATIVE_DAYS:
        if word in s:
            return _with_clock(datetime.combine(today + timedelta(days=offset), dtime.min), clock)

    m = _MONTH_DAY_RE.search(s)
    if m:
        month, day = int(m.group(1)), int(m.group(2))
        try:
            cand = datetime(now.year, month, day)
        except ValueError:               # 2/29 这类，先看明年有没有
            try:
                cand = datetime(now.year + 1, month, day)
            except ValueError:
                return None
        if cand.date() < today:          # 今年的那一天已经过了 → 明年
            try:
                cand = cand.replace(year=now.year + 1)
            except ValueError:
                return None
        return _with_clock(cand, clock)

    if clock:                            # 只给钟点 → 今天
        return now.replace(hour=clock[0], minute=clock[1], second=0, microsecond=0)
    return None


# --------------------------------------------------------------------------
# 核心：一条日程落在哪个区
# --------------------------------------------------------------------------
def bucket_of(item: Dict[str, Any], now: datetime) -> str:
    status = item.get("status") or STATUS_PENDING
    if status == STATUS_DONE:
        return B_DONE
    if status == STATUS_SOMEDAY:
        return B_SOMEDAY
    due = parse_dt(item.get("due"))
    if due is None:
        return B_NODUE
    # 正好到点算过期（<=），否则会有一瞬间既不算进行中也不算过期的空档
    return B_EXPIRED if due <= now else B_LIVE


def _due_key(item: Dict[str, Any]) -> datetime:
    return parse_dt(item.get("due")) or datetime.max


def _created_key(item: Dict[str, Any]) -> datetime:
    return parse_dt(item.get("created_at")) or datetime.min


def _completed_key(item: Dict[str, Any]) -> datetime:
    return parse_dt(item.get("completed_at")) or datetime.min


def split(items: Iterable[Dict[str, Any]], now: Optional[datetime] = None) -> Dict[str, List[Dict[str, Any]]]:
    """把全部条目分成 5 个区，并给出合并后的时间线。

    返回的字典除 5 个分区外，额外有 ``timeline``：进行中 + 已过期合并、
    按截止时间升序。过期项留在原位是既定规则（见策划案 4.2）。
    """
    now = now or datetime.now()
    out: Dict[str, List[Dict[str, Any]]] = {
        B_NODUE: [], B_LIVE: [], B_EXPIRED: [], B_SOMEDAY: [], B_DONE: [],
    }
    for it in items:
        out[bucket_of(it, now)].append(it)

    out[B_NODUE].sort(key=_created_key, reverse=True)   # 最新录入的在最上
    out[B_DONE].sort(key=_completed_key, reverse=True)  # 最近完成的在最上
    out[B_SOMEDAY].sort(key=_due_key)                   # 有时间的排前面

    timeline = out[B_LIVE] + out[B_EXPIRED]
    timeline.sort(key=_due_key)
    out["timeline"] = timeline
    return out


# --------------------------------------------------------------------------
# 时间线分组标题：已过期 / 今天 / 明天 / 本周内 / 更晚
# --------------------------------------------------------------------------
def day_label(due: datetime, now: datetime) -> str:
    d, today = due.date(), now.date()
    if d < today:
        return "已过期"
    if d == today:
        return "今天 · {}月{}日".format(d.month, d.day)
    if d == today + timedelta(days=1):
        return "明天 · {}月{}日".format(d.month, d.day)
    # 到本周日为止算"本周内"
    days_to_sunday = 6 - today.weekday()
    if d <= today + timedelta(days=days_to_sunday):
        return "本周内"
    return "更晚"


def group_timeline(timeline: List[Dict[str, Any]], now: datetime) -> List[Tuple[str, List[Dict[str, Any]]]]:
    """按分组标题切段。timeline 已按 due 升序，所以同标签一定是连续的。"""
    groups: List[Tuple[str, List[Dict[str, Any]]]] = []
    for it in timeline:
        label = day_label(_due_key(it), now)
        if groups and groups[-1][0] == label:
            groups[-1][1].append(it)
        else:
            groups.append((label, [it]))
    return groups


# --------------------------------------------------------------------------
# 文案：剩余 / 已过期多少
# --------------------------------------------------------------------------
def human_delta(delta: timedelta) -> str:
    secs = int(delta.total_seconds())
    if secs < 60:
        return "{} 秒".format(max(secs, 0))
    mins = secs // 60
    if mins < 60:
        return "{} 分钟".format(mins)
    hours = mins // 60
    if hours < 24:
        return "{} 小时".format(hours)
    days = hours // 24
    if days < 30:
        return "{} 天".format(days)
    return "{} 个月".format(days // 30)


def remaining_text(item: Dict[str, Any], now: datetime) -> str:
    due = parse_dt(item.get("due"))
    if due is None:
        return "未设时间"
    delta = due - now
    if delta.total_seconds() <= 0:
        return "已过期 " + human_delta(-delta)
    return "剩 " + human_delta(delta)


def due_display(item: Dict[str, Any]) -> str:
    """列表里显示的截止时间。没有 due 就退回原始文字，两者都没有就空。"""
    due = parse_dt(item.get("due"))
    if due:
        if due.hour == 0 and due.minute == 0:
            return "{}月{}日".format(due.month, due.day)
        return "{}月{}日 {:02d}:{:02d}".format(due.month, due.day, due.hour, due.minute)
    return item.get("due_hint") or ""


# --------------------------------------------------------------------------
# 状态迁移：全部返回新字典，不就地修改（UI 层之后统一 save）
# --------------------------------------------------------------------------
def _copy(item: Dict[str, Any]) -> Dict[str, Any]:
    return dict(item)


def complete(item: Dict[str, Any], now: datetime) -> Dict[str, Any]:
    it = _copy(item)
    it["status"] = STATUS_DONE
    it["completed_at"] = to_iso(now)
    it["updated_at"] = to_iso(now)
    return it


def uncomplete(item: Dict[str, Any], now: datetime) -> Dict[str, Any]:
    it = _copy(item)
    it["status"] = STATUS_PENDING
    it["completed_at"] = None
    it["updated_at"] = to_iso(now)
    return it


def set_someday(item: Dict[str, Any], now: datetime) -> Dict[str, Any]:
    it = _copy(item)
    it["status"] = STATUS_SOMEDAY
    it["updated_at"] = to_iso(now)
    return it


def restore(item: Dict[str, Any], now: datetime) -> Dict[str, Any]:
    it = _copy(item)
    it["status"] = STATUS_PENDING
    it["updated_at"] = to_iso(now)
    return it


# --------------------------------------------------------------------------
# 汇总：给顶部横幅和设置页用
# --------------------------------------------------------------------------
def summary(items: Iterable[Dict[str, Any]], now: Optional[datetime] = None) -> Dict[str, Any]:
    now = now or datetime.now()
    parts = split(items, now)
    return {
        "no_due": len(parts[B_NODUE]),
        "live": len(parts[B_LIVE]),
        "expired": len(parts[B_EXPIRED]),
        "someday": len(parts[B_SOMEDAY]),
        "done": len(parts[B_DONE]),
        "total": sum(len(parts[k]) for k in (B_NODUE, B_LIVE, B_EXPIRED, B_SOMEDAY, B_DONE)),
    }
