# -*- coding: utf-8 -*-
"""
rules.py 的边界用例。

这些断言就是策划案里"排序对不对"的证明：不靠肉眼点五分钟，
而是把 5 种状态的边界钉死。运行：

    python -m unittest discover -s tests -v
"""

from __future__ import annotations

import sys
import unittest
from datetime import datetime, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import rules  # noqa: E402

NOW = datetime(2026, 11, 24, 16, 0, 0)   # 周二


def mk(iid, title, due=None, status=rules.STATUS_PENDING, created=None, done_at=None):
    return {
        "id": iid,
        "title": title,
        "due": due,
        "status": status,
        "created_at": created or "2026-11-24T10:00:00",
        "completed_at": done_at,
    }


class TestParse(unittest.TestCase):
    def test_formats(self):
        self.assertEqual(rules.parse_dt("2026-12-04 23:59"), datetime(2026, 12, 4, 23, 59))
        self.assertEqual(rules.parse_dt("2026-12-04T23:59:00"), datetime(2026, 12, 4, 23, 59))
        self.assertEqual(rules.parse_dt("2026/12/04"), datetime(2026, 12, 4, 0, 0))
        self.assertEqual(rules.parse_dt("2026-12-04"), datetime(2026, 12, 4, 0, 0))

    def test_empty_and_garbage(self):
        self.assertIsNone(rules.parse_dt(None))
        self.assertIsNone(rules.parse_dt(""))
        self.assertIsNone(rules.parse_dt("第13周周五"))   # 不猜，交给 due_hint
        self.assertIsNone(rules.parse_dt("下周之前"))

    def test_bare_time_means_today(self):
        dt = rules.parse_dt("23:59")
        self.assertEqual((dt.hour, dt.minute), (23, 59))


class TestResolveText(unittest.TestCase):
    """图片里的时间原文 → 具体日期。

    规则：只写月日按今年算，今年那一天已经过了就顺延到明年；
    写星期取"最近的下一个"；第N周不换算。
    NOW 是 2026-11-24 周二 16:00。
    """

    def r(self, text, now=NOW):
        return rules.resolve_text_due(text, now)

    def test_month_day_this_year(self):
        self.assertEqual(self.r("12月8日上午9:00"), datetime(2026, 12, 8, 9, 0))
        self.assertEqual(self.r("12/20 14:30"), datetime(2026, 12, 20, 14, 30))
        self.assertEqual(self.r("12-04 23:59"), datetime(2026, 12, 4, 23, 59))

    def test_month_day_passed_rolls_to_next_year(self):
        # 11 月贴出来的"1月5日"只能是明年 1 月，不可能是今年那个早就过去的
        self.assertEqual(self.r("1月5日"), datetime(2027, 1, 5, 23, 59))
        self.assertEqual(self.r("3月1日 08:00"), datetime(2027, 3, 1, 8, 0))

    def test_month_day_today_keeps_this_year(self):
        # 只比日期，不比钟点：今天就是今天，哪怕钟点已经过了（会显示成已过期）
        self.assertEqual(self.r("11月24日"), datetime(2026, 11, 24, 23, 59))

    def test_weekday_is_nearest_upcoming(self):
        self.assertEqual(self.r("周五"), datetime(2026, 11, 27, 23, 59))     # 本周五
        self.assertEqual(self.r("星期三之前"), datetime(2026, 11, 25, 23, 59))
        self.assertEqual(self.r("周二"), datetime(2026, 11, 24, 23, 59))     # 就是今天
        # 今天是周六时说"周五"，指的是下一个周五，不是昨天
        sat = datetime(2026, 11, 28, 10, 0)
        self.assertEqual(self.r("周五", sat), datetime(2026, 12, 4, 23, 59))

    def test_next_week_weekday(self):
        self.assertEqual(self.r("下周三"), datetime(2026, 12, 2, 23, 59))
        self.assertEqual(self.r("下周一 9:00"), datetime(2026, 11, 30, 9, 0))
        # 本周五已过，"这周五"仍然指本周（用户自己说清了是哪一周）
        sat = datetime(2026, 11, 28, 10, 0)
        self.assertEqual(self.r("这周五", sat), datetime(2026, 11, 27, 23, 59))

    def test_relative_days(self):
        self.assertEqual(self.r("今天下午3点"), datetime(2026, 11, 24, 15, 0))
        self.assertEqual(self.r("明天 9:00"), datetime(2026, 11, 25, 9, 0))
        self.assertEqual(self.r("后天"), datetime(2026, 11, 26, 23, 59))

    def test_explicit_year_is_respected(self):
        self.assertEqual(self.r("2027年1月5日 10:00"), datetime(2027, 1, 5, 10, 0))
        # 明确写了今年的过去日期，不漂移
        self.assertEqual(self.r("2026年1月5日"), datetime(2026, 1, 5, 23, 59))

    def test_week_number_is_not_converted(self):
        self.assertIsNone(self.r("第13周周五 23:59"))
        self.assertIsNone(self.r("第 5 周交课程设计"))
        self.assertTrue(rules.mentions_week_number("第13周周五"))
        self.assertFalse(rules.mentions_week_number("下周三"))

    def test_unparseable_is_none(self):
        self.assertIsNone(self.r("尽快"))
        self.assertIsNone(self.r(""))
        self.assertIsNone(self.r(None))


class TestBucket(unittest.TestCase):
    def test_five_buckets(self):
        self.assertEqual(rules.bucket_of(mk("1", "a", None), NOW), rules.B_NODUE)
        self.assertEqual(rules.bucket_of(mk("2", "b", "2026-11-25T09:00"), NOW), rules.B_LIVE)
        self.assertEqual(rules.bucket_of(mk("3", "c", "2026-11-24T09:00"), NOW), rules.B_EXPIRED)
        self.assertEqual(rules.bucket_of(mk("4", "d", "2026-11-25T09:00",
                                             rules.STATUS_SOMEDAY), NOW), rules.B_SOMEDAY)
        self.assertEqual(rules.bucket_of(mk("5", "e", "2026-11-25T09:00",
                                            rules.STATUS_DONE), NOW), rules.B_DONE)

    def test_due_equal_now_is_expired(self):
        # 正好到点算过期，否则会出现既不算"进行中"也不算"已过期"的空档
        self.assertEqual(rules.bucket_of(mk("1", "a", "2026-11-24T16:00"), NOW), rules.B_EXPIRED)

    def test_done_wins_over_expired(self):
        it = mk("1", "a", "2020-01-01T00:00", rules.STATUS_DONE)
        self.assertEqual(rules.bucket_of(it, NOW), rules.B_DONE)


class TestSplit(unittest.TestCase):
    def test_no_due_sorted_newest_first(self):
        items = [
            mk("1", "早建的", None, created="2026-11-20T09:00"),
            mk("2", "晚建的", None, created="2026-11-23T09:00"),
        ]
        parts = rules.split(items, NOW)
        self.assertEqual([x["id"] for x in parts[rules.B_NODUE]], ["2", "1"])

    def test_timeline_merges_live_and_expired_sorted_asc(self):
        items = [
            mk("1", "两天后", "2026-11-26T09:00"),
            mk("2", "昨天", "2026-11-23T09:00"),
            mk("3", "一小时后", "2026-11-24T17:00"),
            mk("4", "没时间", None),
        ]
        parts = rules.split(items, NOW)
        self.assertEqual([x["id"] for x in parts["timeline"]], ["2", "3", "1"])

    def test_someday_and_done_are_isolated(self):
        items = [
            mk("1", "缓办", "2026-11-26T09:00", rules.STATUS_SOMEDAY),
            mk("2", "完成", "2026-11-26T09:00", rules.STATUS_DONE),
        ]
        parts = rules.split(items, NOW)
        self.assertEqual(len(parts["timeline"]), 0)
        self.assertEqual(len(parts[rules.B_SOMEDAY]), 1)
        self.assertEqual(len(parts[rules.B_DONE]), 1)

    def test_done_sorted_latest_first(self):
        items = [
            mk("1", "先完成", status=rules.STATUS_DONE, done_at="2026-11-24T09:00"),
            mk("2", "后完成", status=rules.STATUS_DONE, done_at="2026-11-24T15:00"),
        ]
        parts = rules.split(items, NOW)
        self.assertEqual([x["id"] for x in parts[rules.B_DONE]], ["2", "1"])

    def test_all_completed_leaves_main_empty(self):
        items = [mk("1", "a", "2026-11-25T09:00", rules.STATUS_DONE)]
        parts = rules.split(items, NOW)
        self.assertEqual(parts["timeline"], [])
        self.assertEqual(parts[rules.B_NODUE], [])


class TestGrouping(unittest.TestCase):
    def test_labels(self):
        self.assertEqual(rules.day_label(datetime(2026, 11, 23, 9), NOW), "已过期")
        self.assertIn("今天", rules.day_label(datetime(2026, 11, 24, 23), NOW))
        self.assertIn("明天", rules.day_label(datetime(2026, 11, 25, 9), NOW))
        self.assertEqual(rules.day_label(datetime(2026, 11, 28, 9), NOW), "本周内")
        self.assertEqual(rules.day_label(datetime(2026, 11, 30, 9), NOW), "更晚")

    def test_group_slices_are_contiguous(self):
        items = [
            mk("1", "过期", "2026-11-23T09:00"),
            mk("2", "今天", "2026-11-24T20:00"),
            mk("3", "明天", "2026-11-25T09:00"),
        ]
        parts = rules.split(items, NOW)
        groups = rules.group_timeline(parts["timeline"], NOW)
        self.assertEqual(len(groups), 3)
        self.assertEqual(groups[0][0], "已过期")
        self.assertEqual([x["id"] for x in groups[2][1]], ["3"])


class TestText(unittest.TestCase):
    def test_remaining(self):
        self.assertEqual(rules.remaining_text(mk("1", "a", None), NOW), "未设时间")
        self.assertEqual(rules.remaining_text(mk("2", "b", "2026-11-26T16:00"), NOW), "剩 2 天")
        self.assertEqual(rules.remaining_text(mk("3", "c", "2026-11-24T18:00"), NOW), "剩 2 小时")
        self.assertEqual(rules.remaining_text(mk("4", "d", "2026-11-24T14:00"), NOW), "已过期 2 小时")

    def test_due_display_falls_back_to_hint(self):
        self.assertEqual(rules.due_display({"due": None, "due_hint": "第13周周五"}), "第13周周五")
        self.assertEqual(rules.due_display({"due": "2026-12-04T23:59"}), "12月4日 23:59")
        self.assertEqual(rules.due_display({"due": "2026-12-04T00:00"}), "12月4日")


class TestTransitions(unittest.TestCase):
    def test_complete_then_undo(self):
        it = mk("1", "a", "2026-11-25T09:00")
        done = rules.complete(it, NOW)
        self.assertEqual(done["status"], rules.STATUS_DONE)
        self.assertEqual(done["completed_at"], "2026-11-24T16:00:00")
        self.assertEqual(it["status"], rules.STATUS_PENDING)   # 原对象不被改

        back = rules.uncomplete(done, NOW)
        self.assertEqual(back["status"], rules.STATUS_PENDING)
        self.assertIsNone(back["completed_at"])
        self.assertEqual(back["due"], "2026-11-25T09:00")      # 撤销后保留原截止时间

    def test_someday_and_restore(self):
        it = mk("1", "a", "2026-11-25T09:00")
        self.assertEqual(rules.set_someday(it, NOW)["status"], rules.STATUS_SOMEDAY)
        self.assertEqual(rules.restore(it, NOW)["status"], rules.STATUS_PENDING)


class TestSummary(unittest.TestCase):
    def test_counts(self):
        items = [
            mk("1", "a", None),
            mk("2", "b", "2026-11-25T09:00"),
            mk("3", "c", "2026-11-20T09:00"),
            mk("4", "d", "2026-11-25T09:00", rules.STATUS_SOMEDAY),
            mk("5", "e", "2026-11-25T09:00", rules.STATUS_DONE),
        ]
        s = rules.summary(items, NOW)
        self.assertEqual((s["no_due"], s["live"], s["expired"], s["someday"], s["done"]), (1, 1, 1, 1, 1))
        self.assertEqual(s["total"], 5)


if __name__ == "__main__":
    unittest.main(verbosity=2)
