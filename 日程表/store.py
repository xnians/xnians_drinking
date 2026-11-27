# -*- coding: utf-8 -*-
"""
store.py —— 本地数据读写

只用 JSON 一个文件，理由和 `喝水提醒` 的 config.json 一致：单人单机、数据量小、
出问题能直接用记事本打开看。写入走"临时文件 + os.replace"的原子替换，
避免写一半断电把整个文件弄坏。
"""

from __future__ import annotations

import copy
import json
import os
import shutil
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

BASE_DIR = Path(__file__).resolve().parent
DATA_PATH = BASE_DIR / "data.json"
IMAGE_DIR = BASE_DIR / "images"

DEFAULT: Dict[str, Any] = {
    "version": 1,
    "items": [],
    "settings": {
        "lead_times": ["1d", "1h"],   # 提前量：1d / 1h / 0（到点）
        "gentle": True,               # 温和提醒：不抢焦点
        "keep_image": True,           # 是否保留原图供核对
        "show_done": False,           # 已完成区展开状态（记住上次选择）
    },
    "ai": {
        # 与 OpenAI Chat Completions 兼容即可，换供应商只改这几项。
        # 模型必须是能看图的（qwen3-vl-plus / qwen-vl-max / glm-4.6v / doubao-vision 之类），
        # 纯文本模型收到图片会被静默忽略，识别结果恒为空。
        "base_url": "https://dashscope.aliyuncs.com/compatible-mode/v1",
        "model": "qwen3-vl-plus",
        "api_key": "",
    },
}


def _merge_default(raw: Dict[str, Any]) -> Dict[str, Any]:
    """用默认值补齐缺失字段（老版本数据文件也能打开）。"""
    data = copy.deepcopy(DEFAULT)
    data["version"] = raw.get("version", 1)
    data["items"] = raw.get("items", [])
    for section in ("settings", "ai"):
        src = raw.get(section) or {}
        data[section].update({k: v for k, v in src.items() if k in data[section]})
    return data


def load() -> Dict[str, Any]:
    if not DATA_PATH.exists():
        return copy.deepcopy(DEFAULT)
    try:
        raw = json.loads(DATA_PATH.read_text(encoding="utf-8"))
        if not isinstance(raw, dict):
            raise ValueError("data.json 顶层不是对象")
        return _merge_default(raw)
    except Exception:
        # 损坏就备份一份，再回到空数据，绝不静默覆盖掉用户原始文件
        try:
            broken = DATA_PATH.with_name("data.broken-{}.json".format(datetime.now().strftime("%Y%m%d%H%M%S")))
            shutil.copy2(DATA_PATH, broken)
        except Exception:
            pass
        return copy.deepcopy(DEFAULT)


def save(data: Dict[str, Any]) -> None:
    tmp = DATA_PATH.with_suffix(".tmp")
    text = json.dumps(data, ensure_ascii=False, indent=2)
    tmp.write_text(text, encoding="utf-8")
    os.replace(tmp, DATA_PATH)   # 同盘原子替换


def new_id(items: List[Dict[str, Any]]) -> str:
    """形如 20261124-0003，当日流水号。"""
    day = datetime.now().strftime("%Y%m%d")
    used = set()
    for it in items:
        iid = str(it.get("id", ""))
        if iid.startswith(day + "-"):
            try:
                used.add(int(iid.split("-", 1)[1]))
            except ValueError:
                pass
    n = 1
    while n in used:
        n += 1
    return "{}-{:04d}".format(day, n)


def find(data: Dict[str, Any], item_id: str) -> Optional[Dict[str, Any]]:
    for it in data.get("items", []):
        if it.get("id") == item_id:
            return it
    return None


def replace(data: Dict[str, Any], item: Dict[str, Any]) -> bool:
    for i, it in enumerate(data.get("items", [])):
        if it.get("id") == item.get("id"):
            data["items"][i] = item
            return True
    return False


def remove(data: Dict[str, Any], item_id: str) -> bool:
    items = data.get("items", [])
    for i, it in enumerate(items):
        if it.get("id") == item_id:
            del items[i]
            save(data)
            return True
    return False


def save_image(src_path: str, item_id: str) -> Optional[str]:
    """把用户选的图片复制进 images/，返回相对路径。复制失败不影响主流程。"""
    try:
        IMAGE_DIR.mkdir(exist_ok=True)
        suffix = Path(src_path).suffix.lower() or ".png"
        dst = IMAGE_DIR / (item_id + suffix)
        shutil.copy2(src_path, dst)
        return str(dst.relative_to(BASE_DIR)).replace("\\", "/")
    except Exception:
        return None


def ai_ready(cfg: Dict[str, Any]) -> bool:
    return bool((cfg.get("base_url") or "").strip()
                and (cfg.get("model") or "").strip()
                and (cfg.get("api_key") or "").strip())
