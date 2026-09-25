"""子任务（subtask）功能验证：归一化校验 + 评分口径 + 端到端评测。

直接运行：python3 tests_subtasks.py
不依赖 Docker：用桩沙箱按输入返回预置结果。
"""
import os
import sys
import tempfile
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from backend.judge import scoring  # noqa: E402

failures = []


def check(name, cond, extra=""):
    print(("PASS" if cond else "FAIL"), "-", name, extra)
    if not cond:
        failures.append(name)


# ---------- 1. 归一化与校验 ----------
cases_raw = [
    {"input": "1", "output": "1", "points": 10},
    {"input": "2", "output": "2", "points": 10},
    {"input": "3", "output": "3", "points": 10},
    {"input": "4", "output": "4", "points": 10},
]
cases, groups = scoring.normalize_testcases(cases_raw, [
    {"name": "简单数据", "points": 40, "case_ids": [1, 2]},
    {"name": "困难数据", "points": 60, "case_ids": [3, 4]},
])
check("归一化：两组合计 100 分", scoring.subtask_total_points(groups) == 100)
check("归一化：case id 重排为 1..N", [c["id"] for c in cases] == [1, 2, 3, 4])
check("归一化：默认组名", scoring.normalize_testcases(cases_raw, [
    {"points": 100, "case_ids": [1, 2, 3, 4]}])[1][0]["name"] == "子任务 1")

# 未划分 → 兼容旧口径
cases2, groups2 = scoring.normalize_testcases(cases_raw, [])
check("兼容：无子任务时 groups 为空", groups2 == [])

for bad_name, kw in [
    ("引用不存在的测试点", dict(raw_cases=cases_raw, raw_subtasks=[{"points": 100, "case_ids": [1, 9]}])),
    ("空组", dict(raw_cases=cases_raw, raw_subtasks=[{"points": 40, "case_ids": [1]},
                                                     {"points": 60, "case_ids": []}])),
    ("有测试点未分组", dict(raw_cases=cases_raw, raw_subtasks=[{"points": 100, "case_ids": [1, 2, 3]}])),
    ("同一测试点属于多组", dict(raw_cases=cases_raw, raw_subtasks=[
        {"points": 40, "case_ids": [1, 2]}, {"points": 60, "case_ids": [2, 3, 4]}])),
    ("负分值", dict(raw_cases=cases_raw, raw_subtasks=[{"points": -1, "case_ids": [1, 2, 3, 4]}])),
]:
    try:
        scoring.normalize_testcases(**kw)
        check("校验拒绝：" + bad_name, False, "（未抛异常）")
    except ValueError:
        check("校验拒绝：" + bad_name, True)

# ---------- 2. 评分 ----------
def detail(cid, status):
    return {"case_id": cid, "status": status, "score": 0}

subtasks_cfg = [
    {"id": 1, "name": "简单数据", "points": 40, "case_ids": [1, 2]},
    {"id": 2, "name": "困难数据", "points": 60, "case_ids": [3, 4]},
]

total, res = scoring.build_group_results(subtasks_cfg, [
    detail(1, "AC"), detail(2, "AC"), detail(3, "WA"), detail(4, "TLE")])
check("评分：第一组过、第二组挂 → 40 分", total == 40, str(res))
check("评分：组结果逐项通过标记", [r["passed"] for r in res] == [True, False])
check("评分：组得分 40/0", [r["score"] for r in res] == [40, 0])
check("评分：组结果带 case_ids", res[0]["case_ids"] == [1, 2])

total, res = scoring.build_group_results(subtasks_cfg, [
    detail(1, "AC"), detail(2, "WA"), detail(3, "AC"), detail(4, "AC")])
check("评分：第一组挂、第二组过 → 60 分", total == 60, str([r["score"] for r in res]))

total, res = scoring.build_group_results(subtasks_cfg, [
    detail(1, "AC"), detail(2, "AC"), detail(3, "AC"), detail(4, "AC")])
check("评分：全过 → 100 分且各组通过", total == 100 and all(r["passed"] for r in res))

total, res = scoring.build_group_results(subtasks_cfg, [
    detail(1, "TLE"), detail(2, "RE"), detail(3, "WA"), detail(4, "WA")])
check("评分：全挂 → 0 分", total == 0 and not any(r["passed"] for r in res))

# 缺明细的组一律不通过（保守）
total, res = scoring.build_group_results(
    [{"id": 1, "name": "g", "points": 50, "case_ids": [1]}], [])
check("评分：缺少测试点明细的组不通过", total == 0 and res[0]["passed"] is False)

# ---------- 3. 端到端：桩沙箱 + 临时数据目录 ----------
from backend import config  # noqa: E402

tmp = tempfile.mkdtemp(prefix="oj_subtask_test_")
for attr in ("DATA_DIR", "PROBLEMS_DIR", "TESTCASES_DIR", "CONTESTS_DIR",
             "SUBMISSIONS_DIR", "SCORES_DIR", "USERS_DIR", "FORUM_DIR",
             "SETTINGS_DIR", "RUNS_DIR"):
    setattr(config, attr, os.path.join(tmp, os.path.basename(getattr(config, attr))))
config.ensure_dirs()

from backend.storage import atomic_write_json  # noqa: E402

PID = "ptest"
atomic_write_json(os.path.join(config.PROBLEMS_DIR, PID + ".json"), {
    "id": PID, "title": "子任务测试题", "points": 100,
    "time_limit_ms": 1000, "memory_limit_kb": 65536,
    "comparison": {"mode": "exact", "ignore_whitespace": True},
})
atomic_write_json(os.path.join(config.TESTCASES_DIR, PID + ".json"), {
    "problem_id": PID,
    "cases": [
        {"id": 1, "input": "1", "output": "1", "points": 0},
        {"id": 2, "input": "2", "output": "2", "points": 0},
        {"id": 3, "input": "3", "output": "3", "points": 0},
        {"id": 4, "input": "4", "output": "4", "points": 0},
    ],
    "subtasks": subtasks_cfg,
})


class FakeSandbox:
    name = "fake"

    def compile(self, code, language, workdir, timeout):
        self._all_ok = code.strip() == "__ALL_OK__"
        return {"status": "CE" if code.strip() == "__CE__" else "OK", "message": ""}

    def run(self, language, workdir, stdin, tl, ml):
        # 默认对输入 3 答错（模拟困难数据失败）；__ALL_OK__ 提交全部正确
        text = stdin.decode().strip()
        ok = self._all_ok or text != "3"
        return {
            "status": "OK", "time_ms": 5, "memory_kb": 1024,
            "stdout": (text if ok else "WRONG") + "\n", "message": "",
        }


import backend.judge as judge_pkg  # noqa: E402
from backend.sandbox import ST_OK  # noqa: E402,F401

eng = judge_pkg.JudgeEngine()
eng.sandbox = FakeSandbox()
eng.start()

user = {"id": "u1", "username": "alice", "nickname": "Alice"}
sub = eng.submit("print(input())", "python", PID, "practice", user)
deadline = time.time() + 15
while time.time() < deadline:
    s = eng.get_submission(sub["id"])
    if s["status"] not in ("PENDING", "JUDGING"):
        break
    time.sleep(0.2)

check("端到端：评测完成", s["status"] not in ("PENDING", "JUDGING"), s["status"])
check("端到端：整体裁决 WA（有测试点失败）", s["status"] == "WA", s["status"])
check("端到端：总分 40（简单组全过、困难组 #3 失败）", s["score"] == 40, str(s["score"]))
check("端到端：写入 groups 结果", len(s.get("groups", [])) == 2)
g_scores = {g["id"]: g["score"] for g in s.get("groups", [])}
check("端到端：组得分 40/0", g_scores == {1: 40, 2: 0}, str(g_scores))
check("端到端：子任务模式下单测试点不显示分值",
      all(d.get("score") == 0 for d in s["details"]))
case_status = {d["case_id"]: d["status"] for d in s["details"]}
check("端到端：#1#2 AC、#3 WA、#4 AC",
      case_status == {1: "AC", 2: "AC", 3: "WA", 4: "AC"}, str(case_status))

# 全对提交
sub2 = eng.submit("__ALL_OK__", "python", PID, "practice", user)
deadline = time.time() + 15
while time.time() < deadline:
    s2 = eng.get_submission(sub2["id"])
    if s2["status"] not in ("PENDING", "JUDGING"):
        break
    time.sleep(0.2)
check("端到端：全对 → AC/100", s2["status"] == "AC" and s2["score"] == 100,
      f"{s2['status']}/{s2['score']}")
check("端到端：全对时两组均通过", all(g["passed"] for g in s2["groups"]))

# ---------- 4. 旧题（无子任务）口径不回归 ----------
atomic_write_json(os.path.join(config.TESTCASES_DIR, "pold.json"), {
    "problem_id": "pold",
    "cases": [
        {"id": 1, "input": "1", "output": "1", "points": 20},
        {"id": 2, "input": "3", "output": "3", "points": 80},
    ],
})
atomic_write_json(os.path.join(config.PROBLEMS_DIR, "pold.json"), {
    "id": "pold", "title": "旧题", "points": 100,
    "time_limit_ms": 1000, "memory_limit_kb": 65536,
    "comparison": {"mode": "exact", "ignore_whitespace": True},
})
sub3 = eng.submit("print(input())", "python", "pold", "practice", user)
deadline = time.time() + 15
while time.time() < deadline:
    s3 = eng.get_submission(sub3["id"])
    if s3["status"] not in ("PENDING", "JUDGING"):
        break
    time.sleep(0.2)
# #1 对 20 分，#3 输入答错 → WA，得 20；groups 为空
check("旧题：按测试点给分仍为 20 分", s3["score"] == 20, str(s3["score"]))
check("旧题：无 groups 字段（兼容前端）", s3.get("groups", []) == [])
check("旧题：测试点明细分值保留",
      {d["case_id"]: d["score"] for d in s3["details"]} == {1: 20, 2: 0})

print()
if failures:
    print("FAILED:", failures)
    sys.exit(1)
print("ALL TESTS PASSED")
