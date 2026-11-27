# -*- coding: utf-8 -*-
"""
parser.py —— 图片 → 日程草稿

只依赖标准库（urllib），Pillow 是可选的：装了就先压缩再送，没装就原图直送。
接口按 OpenAI Chat Completions 协议拼，所以换供应商只改 地址 + 模型名，
不用改代码（对应策划案 5.7）。

关键设计：不让模型做"第 13 周 → 具体日期"的换算。周次一旦猜错就是错误的
截止时间，比空着更危险；识别不了就 due=None + due_hint 保留原文，交给人补。
"""

from __future__ import annotations

import base64
import io
import json
import re
import time
import urllib.error
import urllib.request
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import rules

PROMPT = """你是日程信息抽取器。只输出 JSON 数组，不要任何解释文字。
每个元素字段：
  title        string  日程标题，动宾结构，不超过20字
  due_hint     string  图上关于时间的原文，**一字不改地照抄**（如"12月8日上午9:00""下周三之前""第13周周五23:59"）
  due          string  仅当你确定完整的"年-月-日"时才填 ISO8601；只写了月日、星期、周次的，填 null
  notes        string  附加要求（如"逾期扣分""需带学生证"），无则 ""
  confidence   number  0~1，你对 due 这个字段的把握
规则：
  - 一张图里若有多个时间节点，拆成多条
  - 时间原文必须完整出现在 due_hint 里，不要自己补年份、不要改写成日期
  - 图上没写年份就不要编年份；只写"第N周"的不要自己推算日期
  - 不要编造图中不存在的信息
  - 图片里没有日程信息时，输出 []"""

# 自检图：96×56 的白底黑字 "42"。文字模型拿到它会返回空或胡猜，
# 多模态模型能直接读出 42——用这个把"接口通了"和"模型会看图"分开报。
# 生成方式见 CREDITS.md，图是 1-bit 单色 PNG，只有 292 字节，直接内嵌。
_PROBE_PNG = base64.b64decode(
    "iVBORw0KGgoAAAANSUhEUgAAAGAAAAA4AQAAAAAqPsAPAAAAoUlEQVR42s2RMQ7CMBAEJzESFEjJCyD8JAX/"
    "Ikh8LLyEJ7i8wvJSxEeCoKBB4MLS+u5mT+tKzKfmV+LCOAAgSSGzl6QaEJk4zyTMRV4CErZLC/QBgBVg0B+9"
    "Ep83aCZPJI1BCm56LbNO06NtHZSa0qYNJKdlwFqfaSF2RaQObn0BGJwGuQ9wXqxT3qY7b1+jmtIxwgywz7KO"
    "byrVf3z9d8QdxBhLmrd4vl0AAAAASUVORK5CYII="
)


class ParseError(Exception):
    """解析失败。消息是给人看的中文，直接可以显示在界面上。"""


# --------------------------------------------------------------------------
# 图片编码
# --------------------------------------------------------------------------
def _encode_image(path: str, max_edge: int = 1600, quality: int = 85) -> str:
    raw = Path(path).read_bytes()
    try:
        from PIL import Image  # 可选依赖

        img = Image.open(io.BytesIO(raw))
        img = img.convert("RGB")
        w, h = img.size
        scale = min(1.0, max_edge / float(max(w, h)))
        if scale < 1.0:
            img = img.resize((int(w * scale), int(h * scale)))
        buf = io.BytesIO()
        img.save(buf, format="JPEG", quality=quality)
        return base64.b64encode(buf.getvalue()).decode("ascii")
    except ImportError:
        # 没装 Pillow：原图直送，模型侧自己会处理
        return base64.b64encode(raw).decode("ascii")
    except Exception as exc:
        raise ParseError("图片读取失败：{}".format(exc))


# --------------------------------------------------------------------------
# HTTP
# --------------------------------------------------------------------------
def _endpoint(cfg: Dict[str, Any]) -> str:
    base = (cfg.get("base_url") or "").strip().rstrip("/")
    if not base:
        raise ParseError("未填写接口地址")
    if base.endswith("/chat/completions"):
        return base
    return base + "/chat/completions"


def _post(cfg: Dict[str, Any], messages: List[Dict[str, Any]], timeout: int = 40) -> str:
    key = (cfg.get("api_key") or "").strip()
    if not key:
        raise ParseError("未填写 API Key")
    payload = {
        "model": (cfg.get("model") or "").strip(),
        "messages": messages,
        "temperature": 0.1,
        "max_tokens": 1500,
    }
    req = urllib.request.Request(
        _endpoint(cfg),
        data=json.dumps(payload).encode("utf-8"),
        headers={
            "Content-Type": "application/json",
            "Authorization": "Bearer " + key,
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            body = resp.read().decode("utf-8", "replace")
    except urllib.error.HTTPError as exc:
        detail = ""
        try:
            detail = exc.read().decode("utf-8", "replace")[:300]
        except Exception:
            pass
        if exc.code in (401, 403):
            raise ParseError("Key 无效或权限不足（HTTP {}）".format(exc.code))
        if exc.code == 404:
            raise ParseError("接口地址或模型名不对（HTTP 404）")
        if exc.code == 429:
            raise ParseError("请求过于频繁或额度用尽（HTTP 429）")
        raise ParseError("接口返回 HTTP {}：{}".format(exc.code, detail or exc.reason))
    except urllib.error.URLError as exc:
        raise ParseError("网络不通或超时：{}".format(exc.reason))
    except TimeoutError:
        raise ParseError("请求超时（{}s）".format(timeout))

    try:
        data = json.loads(body)
        msg = data["choices"][0]["message"]["content"]
    except Exception:
        raise ParseError("接口返回格式无法解析")
    if isinstance(msg, list):   # 少数供应商返回分段内容
        msg = "".join(part.get("text", "") for part in msg if isinstance(part, dict))
    return msg or ""


# --------------------------------------------------------------------------
# JSON 抽取：模型经常裹一层 ```json 或加两句客套话
# --------------------------------------------------------------------------
def _extract_json(text: str) -> List[Dict[str, Any]]:
    s = text.strip()
    fence = re.search(r"```(?:json)?\s*(.*?)```", s, re.S)
    if fence:
        s = fence.group(1).strip()
    start, end = s.find("["), s.rfind("]")
    if start == -1 or end == -1 or end <= start:
        if s.startswith("[]"):
            return []
        raise ParseError("模型没有返回 JSON 数组，原始输出：" + text[:200])
    chunk = s[start:end + 1]
    try:
        data = json.loads(chunk)
    except json.JSONDecodeError:
        # 偶尔会带尾逗号
        try:
            data = json.loads(re.sub(r",\s*([\]}])", r"\1", chunk))
        except json.JSONDecodeError:
            raise ParseError("模型返回的 JSON 不合法，原始输出：" + chunk[:200])
    if not isinstance(data, list):
        raise ParseError("模型返回的不是数组")
    return [x for x in data if isinstance(x, dict)]


# --------------------------------------------------------------------------
# 归一化：把模型输出变成内部结构
# --------------------------------------------------------------------------
def _roll_to_next_year(due: datetime, hint: str, now: datetime) -> datetime:
    """模型给的日期已经过去、而原文里没写年份 → 当作明年。

    学期跨年是常态：11 月贴出来的"1月5日"指的是明年 1 月，不是今年那个早就
    过去的 1 月 5 日。原文里写了四位年份（2026年…）就尊重原文，不漂移。
    """
    if due.date() >= now.date():
        return due
    if re.search(r"(19|20)\d{2}\s*[年\-/.]", hint or ""):
        return due
    try:
        return due.replace(year=due.year + 1)
    except ValueError:      # 2/29 落在平年
        return due


def _normalize(d: Dict[str, Any], now: Optional[datetime] = None) -> Optional[Dict[str, Any]]:
    title = str(d.get("title") or "").strip()
    if not title:
        return None
    now = now or datetime.now()
    hint = str(d.get("due_hint") or "").strip()
    due_raw = d.get("due")
    raw_txt = "" if due_raw is None else str(due_raw).strip()
    if raw_txt.lower() in ("null", "none"):
        raw_txt = ""

    # ① 先按原文在本地换算：月日 / 星期 / 今天明天走同一套规则，结果可测、
    #    换模型也不会变。没写年份的月日已过则顺延到明年（rules.resolve_text_due）。
    due = rules.resolve_text_due(hint, now) if hint else None

    # ② 原文算不出来（"第13周周五"这类）才退回模型给的 ISO。周次明确不换算，
    #    避免模型猜出一个看起来精确其实错误的日期。
    if due is None and raw_txt and not rules.mentions_week_number(hint):
        due = rules.parse_dt(raw_txt)
        if due is not None:
            due = _roll_to_next_year(due, hint, now)

    if due is None and raw_txt and not hint:
        hint = raw_txt

    try:
        conf = float(d.get("confidence", 0.7))
    except (TypeError, ValueError):
        conf = 0.7
    conf = min(1.0, max(0.0, conf))

    return {
        "title": title[:60],
        "due": rules.to_iso(due),
        "due_hint": hint or None,
        "notes": str(d.get("notes") or "").strip()[:200],
        "confidence": conf,
    }


def parse_image(path: str, cfg: Dict[str, Any]) -> List[Dict[str, Any]]:
    """返回草稿列表。识别不出任何日程时返回 []；出错抛 ParseError。"""
    b64 = _encode_image(path)
    suffix = Path(path).suffix.lower().lstrip(".") or "png"
    mime = "image/jpeg" if suffix in ("jpg", "jpeg") else "image/{}".format(suffix)
    messages = [{
        "role": "user",
        "content": [
            {"type": "text", "text": PROMPT},
            {"type": "image_url", "image_url": {"url": "data:{};base64,{}".format(mime, b64)}},
        ],
    }]
    text = _post(cfg, messages)
    now = datetime.now()
    drafts = [x for x in (_normalize(d, now) for d in _extract_json(text)) if x]
    return drafts


# --------------------------------------------------------------------------
# 测试连接：一次最小请求，把网络/Key/模型三类问题分开报
# --------------------------------------------------------------------------
def test_connection(cfg: Dict[str, Any]) -> Tuple[bool, str, float]:
    """一次最小请求，把"网络/Key 错"和"模型不能看图"分开报。

    只用 1×1 像素做 ping 是测不出第二类的：纯文本模型收到图会直接忽略，
    照样回一句"ok"，看起来一切正常，直到真传截图才返回空数组。
    所以这里发的是一张写着 42 的小图，要求复述内容。
    """
    started = time.time()
    b64 = base64.b64encode(_PROBE_PNG).decode("ascii")
    messages = [{
        "role": "user",
        "content": [
            {"type": "text", "text": "图中的数字是多少？只回复数字本身，不要其它文字。"},
            {"type": "image_url", "image_url": {"url": "data:image/png;base64," + b64}},
        ],
    }]
    try:
        reply = _post(cfg, messages, timeout=20)
    except ParseError as exc:
        return False, str(exc), time.time() - started
    cost = time.time() - started
    text = (reply or "").strip()
    if "42" in text:
        return True, "连通，模型能读图", cost
    if not text:
        return False, "接口通了，但模型对图片返回空——多半不支持图片输入。" \
                      "模型名换成 qwen3-vl-plus / qwen-vl-max 这类多模态模型", cost
    return False, "接口通了，但模型没认出图里的数字（回了「{}」）。" \
                  "可能不是多模态模型，换 qwen3-vl-plus 试试".format(text[:30]), cost
