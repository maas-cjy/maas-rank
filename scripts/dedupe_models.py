#!/usr/bin/env python3
"""一次性迁移：合并 models.json 中因 LMArena 名称风格变更（空格↔连字符）产生的重复条目。

合并规则：
- 规范键 = 小写、空白/下划线折叠为连字符、压缩重复连字符
- 同规范键的多条合并为一条：优先保留 id 已是规范形（连字符形）的条目；
  字段取并集（缺失字段从重复条目补齐），Elo 取最新（数值较大者）
- 被合并条目的 id 与展示名写入 aliases，前端 model.html 旧链接自动跳转
- 同步处理 history.json / prev.json 快照中的重复模型行

用法：python3 scripts/dedupe_models.py [--dry-run]
"""
import argparse
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

FIELDS = ("elo", "superclue", "priceIn", "priceOut", "context", "speed",
          "bench", "dims", "release", "desc", "provider", "region", "open")


def canon(s: str) -> str:
    s = str(s).lower().strip()
    s = re.sub(r"[\s_]+", "-", s)
    s = re.sub(r"-+", "-", s).strip("-")
    return s


def completeness(m: dict) -> int:
    n = 0
    for f in FIELDS:
        v = m.get(f)
        if v is not None and v != {} and v != "":
            n += 1
    return n


def pick_canonical(group: list[dict]) -> dict:
    def sort_key(m):
        return (m["id"] == canon(m["id"]), completeness(m), m.get("elo") or 0)
    return sorted(group, key=sort_key, reverse=True)[0]


def merge_group(group: list[dict]) -> dict:
    base = pick_canonical(group)
    aliases: list[str] = []
    names: list[str] = []
    for m in group:
        if m is base:
            continue
        for a in [m["id"], m.get("name", "")]:
            if a and a not in aliases and a != base["id"] and a != base.get("name"):
                aliases.append(a)
        for f in FIELDS:
            if base.get(f) in (None, {}, "") and m.get(f) not in (None, {}, ""):
                base[f] = m[f]
        if m.get("elo") is not None and (base.get("elo") or 0) < m["elo"]:
            base["elo"] = m["elo"]
        if m.get("superclue") is not None and (base.get("superclue") or 0) < m["superclue"]:
            base["superclue"] = m["superclue"]
    if aliases:
        prev = base.get("aliases") or []
        base["aliases"] = list(dict.fromkeys(prev + aliases))
    return base


def dedupe_model_list(models: list[dict]) -> tuple[list[dict], list[tuple]]:
    groups: dict[str, list[dict]] = {}
    for m in models:
        groups.setdefault(canon(m["id"]), []).append(m)
    out, merged_pairs = [], []
    for key, g in groups.items():
        if len(g) == 1:
            out.append(g[0])
        else:
            out.append(merge_group(g))
            merged_pairs.append((key, [m["id"] for m in g]))
    # 保持原有相对顺序
    order = {m["id"]: i for i, m in enumerate(models)}
    out.sort(key=lambda m: order.get(m["id"], 10**9))
    return out, merged_pairs


def dedupe_snapshot_models(models: list) -> list:
    """快照里的模型行可能是 dict（含 id）。按规范键去重，保留 Elo 最高者。"""
    if not models or not isinstance(models[0], dict) or "id" not in models[0]:
        return models
    groups: dict[str, list] = {}
    for m in models:
        groups.setdefault(canon(m["id"]), []).append(m)
    out = []
    for g in groups.values():
        best = max(g, key=lambda m: m.get("elo") or 0)
        if best["id"] != canon(best["id"]):
            best = dict(best)
            best["id"] = canon(best["id"])
        out.append(best)
    # 按规范键排序稳定性不敏感——保持首次出现顺序
    seen, ordered = set(), []
    for m in models:
        k = canon(m["id"])
        if k not in seen:
            seen.add(k)
            ordered.append(next(x for x in out if canon(x["id"]) == k))
    return ordered


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    models_path = ROOT / "data" / "models.json"
    data = json.loads(models_path.read_text(encoding="utf-8"))
    models, pairs = dedupe_model_list(data["models"])

    print(f"原始 {len(data['models'])} 个 -> 合并后 {len(models)} 个（消除 {len(data['models']) - len(models)} 个重复）")
    for key, ids in pairs:
        print(f"  {key}: {' + '.join(ids)}")

    # history / prev
    for fname in ("history.json", "prev.json"):
        p = ROOT / "data" / fname
        if not p.exists():
            continue
        d = json.loads(p.read_text(encoding="utf-8"))
        if fname == "history.json":
            snaps = d.get("snapshots", [])
            n0 = sum(len(s.get("models", [])) for s in snaps)
            for s in snaps:
                s["models"] = dedupe_snapshot_models(s.get("models", []))
            n1 = sum(len(s.get("models", [])) for s in snaps)
            print(f"{fname}: 快照模型行 {n0} -> {n1}")
        else:
            ms = d.get("models", [])
            d["models"] = dedupe_snapshot_models(ms)
            print(f"{fname}: 模型行 {len(ms)} -> {len(d['models'])}")
        if not args.dry_run:
            p.write_text(json.dumps(d, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    if not args.dry_run:
        data["models"] = models
        models_path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        print("已写入")
    else:
        print("(dry-run，未写入)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
