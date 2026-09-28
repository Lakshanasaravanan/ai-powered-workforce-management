"""Transparent rank metrics used by the Phase 21 retrieval benchmark."""
from __future__ import annotations

from statistics import mean

KS = (1, 3, 5, 10)


def per_query(ranking: list[str], relevant: set[str]) -> dict:
    if not relevant:
        return {"recall": {k: None for k in KS}, "precision": {k: None for k in KS}, "hit": {k: None for k in KS}, "rr": None, "ap": None}
    values = {"recall": {}, "precision": {}, "hit": {}}
    for k in KS:
        found = len(set(ranking[:k]) & relevant)
        values["recall"][k] = found / len(relevant)
        values["precision"][k] = found / k
        values["hit"][k] = float(found > 0)
    ranks = [index + 1 for index, item in enumerate(ranking) if item in relevant]
    values["rr"] = 1 / ranks[0] if ranks else 0.0
    precision_sum = sum(sum(item in relevant for item in ranking[:rank]) / rank for rank in ranks)
    values["ap"] = precision_sum / len(relevant)
    return values


def aggregate(rows: list[dict]) -> dict:
    answerable = [row for row in rows if row["metrics"]["rr"] is not None]
    out = {"count": len(answerable), "recall": {}, "precision": {}, "hit_rate": {}}
    for k in KS:
        out["recall"][str(k)] = mean(row["metrics"]["recall"][k] for row in answerable)
        out["precision"][str(k)] = mean(row["metrics"]["precision"][k] for row in answerable)
        out["hit_rate"][str(k)] = mean(row["metrics"]["hit"][k] for row in answerable)
    out["mrr"] = mean(row["metrics"]["rr"] for row in answerable)
    out["map"] = mean(row["metrics"]["ap"] for row in answerable)
    return out


def by_field(rows: list[dict], cases_by_id: dict[str, dict], field: str) -> dict[str, dict]:
    """Aggregate exact-chunk metrics by a static benchmark label."""
    groups: dict[str, list[dict]] = {}
    for row in rows:
        value = str(cases_by_id[row["id"]].get(field, "unknown"))
        groups.setdefault(value, []).append(row)
    return {value: aggregate(group) for value, group in sorted(groups.items()) if any(item["metrics"]["rr"] is not None for item in group)}
