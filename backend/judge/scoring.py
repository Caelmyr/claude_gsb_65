"""测试点归一化校验与子任务（subtask）评分。

支持两种计分口径（由配置自动决定，互不影响旧题）：

1. 按测试点给分（默认，兼容历史题目）：
   每个测试点自带 points，通过即得该点分值；
   全部通过时取测试点分值之和，和为 0 时回落到题目总分。

2. 按子任务给分：
   管理员把测试点划分为若干子任务并给每组单独赋分，
   组内所有测试点全部通过才得到该组分值，否则该组 0 分；
   总分 = 各子任务得分之和。
"""


def normalize_cases(raw_cases):
    """把前端提交的测试点列表归一化。"""
    if raw_cases is None:
        return []
    if not isinstance(raw_cases, list):
        raise ValueError("测试用例格式不正确")
    normalized = []
    for i, c in enumerate(raw_cases):
        if not isinstance(c, dict):
            raise ValueError(f"第 {i + 1} 个测试点格式不正确")
        normalized.append({
            "id": i + 1,
            "input": c.get("input", "") or "",
            "output": c.get("output", "") or "",
            "points": _to_int(c.get("points", 0), f"第 {i + 1} 个测试点的分值"),
        })
    return normalized


def normalize_subtasks(raw_subtasks, cases):
    """归一化并校验子任务配置。

    cases 必须已经过 normalize_cases 处理（id 从 1 递增）。
    启用子任务时要求测试点构成一个划分：每个测试点恰好属于一个子任务，
    每个子任务至少包含一个测试点，且引用的测试点必须存在。
    """
    if not raw_subtasks:
        return []
    if not isinstance(raw_subtasks, list):
        raise ValueError("子任务格式不正确")

    valid_ids = {c["id"] for c in cases}
    normalized = []
    for i, g in enumerate(raw_subtasks):
        label = f"第 {i + 1} 个子任务"
        if not isinstance(g, dict):
            raise ValueError(f"{label}格式不正确")
        points = _to_int(g.get("points", 0), f"{label}的分值")
        if points < 0:
            raise ValueError(f"{label}的分值不能为负")

        raw_ids = g.get("case_ids", [])
        if not isinstance(raw_ids, list):
            raise ValueError(f"{label}包含的测试点格式不正确")
        case_ids = []
        for cid in raw_ids:
            try:
                cid = int(cid)
            except (TypeError, ValueError):
                raise ValueError(f"{label}引用了不存在的测试点")
            if cid not in valid_ids:
                raise ValueError(f"{label}引用了不存在的测试点 #{cid}")
            if cid not in case_ids:
                case_ids.append(cid)
        if not case_ids:
            raise ValueError(f"{label}至少需要包含一个测试点")

        name = (g.get("name") or "").strip() or f"子任务 {i + 1}"
        normalized.append({
            "id": i + 1,
            "name": name,
            "points": points,
            "case_ids": case_ids,
        })

    # 覆盖性校验：每个测试点恰好属于一个子任务
    membership = {}
    for g in normalized:
        for cid in g["case_ids"]:
            if cid in membership:
                raise ValueError(
                    f"测试点 #{cid} 同时属于「{membership[cid]}」和「{g['name']}」，"
                    "每个测试点只能归入一个子任务"
                )
            membership[cid] = g["name"]
    missing = sorted(valid_ids - set(membership))
    if missing:
        shown = "、".join(f"#{cid}" for cid in missing[:10])
        more = " 等" if len(missing) > 10 else ""
        raise ValueError(f"测试点 {shown}{more} 未归入任何子任务；"
                         "划分子任务后每个测试点都必须属于某个子任务")
    return normalized


def normalize_testcases(raw_cases, raw_subtasks):
    """一次性归一化测试点与子任务，返回 (cases, subtasks)。"""
    cases = normalize_cases(raw_cases)
    subtasks = normalize_subtasks(raw_subtasks, cases)
    return cases, subtasks


def subtask_total_points(subtasks):
    """子任务分值合计（即题目总分口径）。"""
    return sum(int(g.get("points", 0)) for g in subtasks or [])


def build_group_results(subtasks, details):
    """根据逐测试点评测明细计算各子任务结果。

    组内所有引用测试点均为 AC 时该组通过、得到整组分值，否则得 0 分。
    返回 (总分, 组结果列表)，组结果形如：
      {id, name, points, score, passed, case_ids}
    """
    by_case = {}
    for d in details or []:
        cid = d.get("case_id")
        if cid is not None:
            by_case[cid] = d

    results = []
    total = 0
    for g in subtasks or []:
        case_ids = list(g.get("case_ids", []))
        passed = bool(case_ids) and all(
            (by_case.get(cid) or {}).get("status") == "AC" for cid in case_ids
        )
        points = int(g.get("points", 0))
        score = points if passed else 0
        total += score
        results.append({
            "id": g.get("id"),
            "name": g.get("name", ""),
            "points": points,
            "score": score,
            "passed": passed,
            "case_ids": case_ids,
        })
    return total, results


def _to_int(value, label):
    try:
        v = int(value)
    except (TypeError, ValueError):
        raise ValueError(f"{label}必须是整数")
    if v < 0:
        raise ValueError(f"{label}不能为负")
    return v
