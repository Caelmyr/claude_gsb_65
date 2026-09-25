"""子任务（Subtask）分组评分。

数据约定（存放在 data/testcases/{problem_id}.json 的顶层 "subtasks"）：
    [
      {"id": 1, "name": "简单数据", "points": 40, "case_ids": [1, 2]},
      {"id": 2, "name": "困难数据", "points": 60, "case_ids": [3, 4, 5]}
    ]

规则：
  - 一个子任务内引用的所有测试点全部通过（AC）才得到该子任务的满分，否则 0 分；
  - 不属于任何子任务的“散点”沿用按测试点给分（points）的老规则；
  - 没有配置子任务时（subtasks 缺省 / 为空 / 非法）完全走旧判分路径，保持兼容；
  - 子任务引用了不存在的测试点时该子任务视为未通过（配置层会拦截这种数据）。
"""
from backend.utils import truncate


class SubtaskConfigError(ValueError):
    """子任务配置非法（保存测试点时抛出，由 API 层转成 400）。"""


def normalize_subtasks(raw_subtasks, case_ids):
    """校验并规范化管理员提交的子任务配置。

    case_ids 为当前全部测试点 id 的集合（已转为可哈希值）。
    返回规范化后的列表；raw_subtasks 为空时返回 []。
    """
    if raw_subtasks is None:
        return []
    if not isinstance(raw_subtasks, (list, tuple)):
        raise SubtaskConfigError("子任务配置格式不正确，应为数组")

    valid_ids = set(case_ids)
    normalized = []
    seen_case_ids = set()

    for i, st in enumerate(raw_subtasks):
        if not isinstance(st, dict):
            raise SubtaskConfigError(f"第 {i + 1} 个子任务格式不正确")
        name = str(st.get("name") or f"子任务 {i + 1}").strip()
        try:
            points = int(st.get("points", 0))
        except (TypeError, ValueError):
            raise SubtaskConfigError(f"子任务「{name}」分值必须是整数")
        if points < 0:
            raise SubtaskConfigError(f"子任务「{name}」分值不能为负")

        raw_refs = st.get("case_ids") or []
        if not isinstance(raw_refs, (list, tuple)):
            raise SubtaskConfigError(f"子任务「{name}」的测试点列表格式不正确")
        refs = []
        for ref in raw_refs:
            try:
                cid = int(ref)
            except (TypeError, ValueError):
                raise SubtaskConfigError(f"子任务「{name}」中存在非法测试点编号")
            if cid not in valid_ids:
                raise SubtaskConfigError(f"子任务「{name}」引用了不存在的测试点 #{cid}")
            if cid in seen_case_ids:
                raise SubtaskConfigError(f"测试点 #{cid} 被重复归入多个子任务")
            seen_case_ids.add(cid)
            refs.append(cid)
        if not refs:
            raise SubtaskConfigError(f"子任务「{name}」至少要包含一个测试点")

        normalized.append({
            "id": i + 1,
            "name": truncate(name, 100),
            "points": points,
            "case_ids": refs,
        })
    return normalized


def is_enabled(subtasks):
    """是否启用了子任务评分（非法/空配置一律视为未启用，保证老题不受影响）。"""
    return isinstance(subtasks, (list, tuple)) and len(subtasks) > 0


def grouped_case_ids(subtasks):
    """返回已被某个子任务收纳的测试点 id 集合。"""
    ids = set()
    if is_enabled(subtasks):
        for st in subtasks:
            ids.update(st.get("case_ids") or [])
    return ids


def summarize(subtasks, case_results):
    """根据各测试点的判定结果汇总子任务得分。

    case_results: {case_id: {"status": "AC"/"WA"/..., "points": 散点得分}}
    返回 (subtask_results, subtask_total)：
      subtask_results = [
        {"id", "name", "points", "score", "passed",
         "total_cases", "passed_cases", "case_ids"}
      ]
    """
    results = []
    total = 0
    for st in (subtasks or []):
        if not isinstance(st, dict):
            continue
        refs = list(st.get("case_ids") or [])
        points = int(st.get("points", 0))
        passed_cases = sum(
            1 for cid in refs
            if (case_results.get(cid) or {}).get("status") == "AC"
        )
        passed = bool(refs) and passed_cases == len(refs)
        score = points if passed else 0
        total += score
        results.append({
            "id": st.get("id"),
            "name": st.get("name") or f"子任务 {st.get('id')}",
            "points": points,
            "score": score,
            "passed": passed,
            "total_cases": len(refs),
            "passed_cases": passed_cases,
            "case_ids": refs,
        })
    return results, total
