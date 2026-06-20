"""Cram Engine ??????

???progress.json + index.json
????????diagnostic / deconstruct / teach / test / remediate / review / done

????????????
1. must_know ????? -> stage 4 ??
2. ?? 0 ?? / ??????user_level ?????????
3. ?? 1 ?????/???????
4. SM-2 ??????? 2 ???????? 3/4 ?????
5. ?? 2 ???must_know ???
6. ?? 3 ???must_know ?????????
7. done
"""

import json
import sys
from pathlib import Path
from datetime import datetime, timedelta

sys.path.insert(0, str(Path(__file__).resolve().parent))

from utils import (
    read_json, now_date,
)


def _km_context(progress: dict, topo_order: list) -> str:
    km = progress.get('knowledge_map', {})
    if not km:
        return '无诊断数据'
    weak_nodes = [nid for nid in topo_order if km.get(nid, {}).get('level') == 'weak']
    strong_nodes = [nid for nid in topo_order if km.get(nid, {}).get('level') == 'strong']
    parts = []
    if weak_nodes:
        parts.append(f'薄弱({len(weak_nodes)}个): {", ".join(weak_nodes[:5])}{"..." if len(weak_nodes) > 5 else ""}')
    if strong_nodes:
        parts.append(f'熟练({len(strong_nodes)}个): {", ".join(strong_nodes[:5])}{"..." if len(strong_nodes) > 5 else ""}')
    return '; '.join(parts) if parts else '全部知识点掌握度未知'


def schedule(progress: dict, index: dict) -> dict:
    nodes = {n["id"]: n for n in index.get("nodes", [])}
    prog_nodes = progress.get("nodes", {})
    current_stage = progress.get("current_stage", 1)
    topo_order = index.get("topo_order", [])
    today = now_date()
    user_level = progress.get("user_level")

    # ============================================================
    #  ??? 1?must_know ????? -> ???? 4
    # ============================================================
    error_nodes = progress.get("error_nodes", [])
    for nid in error_nodes:
        node = nodes.get(nid)
        if node and node.get("weight") == "must_know":
            pn = prog_nodes.get(nid, {})
            if not pn.get("stage4_done") and not pn.get("stubborn"):
                return {
                    "action": "remediate",
                    "node_id": nid,
                    "stage": 4,
                    "reason": f"must_know ???: {node.get('label', nid)}",
                    "context": {
                        "node_label": node.get("label", nid),
                        "weight": "must_know",
                        "retry_count": pn.get("stage4_retry_count", 0),
                        "wrong_answers": pn.get("stage3_wrong_answers", []),
                    }
                }

    # ============================================================
    #  ??? 2??? 0 ?? / ?????
    #
    #  - current_stage == 0???????
    #  - current_stage == 2 ? user_level ?????????
    #    ??????????????
    # ============================================================
    any_learned = any(
        prog_nodes.get(nid, {}).get("stage2_done")
        for nid in topo_order
    )

    needs_diagnostic = (
        current_stage == 0
        or (current_stage == 2 and user_level in (None, "unknown") and not any_learned)
    )

    if needs_diagnostic:
        return {
            "action": "diagnostic",
            "node_id": None,
            "stage": 0,
            "reason": "?? 0: ???????????",
            "context": {
                "user_level": user_level or "unknown",
                "compat_mode": current_stage == 2,
            }
        }

    # ============================================================
    #  ??? 3??? 1 ? ??????
    # ============================================================
    if current_stage == 1:
        return {
            "action": "deconstruct",
            "node_id": None,
            "stage": 1,
            "reason": "?? 1: ?????????????",
            "context": {
                "total_nodes": len(topo_order),
                "must_know_count": sum(1 for n in index.get("nodes", []) if n.get("weight") == "must_know"),
                "key_point_count": sum(1 for n in index.get("nodes", []) if n.get("weight") == "key_point"),
            }
        }

    # ============================================================
    #  ??? 4?SM-2 ????
    #
    #  ?? 2 ?????? < 3 ??? 2 ???? -> ????
    #  ?? 3/4/5?????
    # ============================================================
    sm2_due = []
    must_know_review_due = []
    for nid, pn in prog_nodes.items():
        sm2 = pn.get("sm2", {})
        next_review = sm2.get("next_review")
        node = nodes.get(nid, {})
        if next_review and next_review <= today:
            if node.get("weight") == "must_know":
                must_know_review_due.append((nid, sm2))
            else:
                sm2_due.append((nid, sm2))

    all_due = must_know_review_due + sm2_due

    if all_due:
        if current_stage == 2:
            # ?? 2???????? 2 ???????
            max_overdue = 0
            for _, sm2 in all_due:
                nrd = sm2.get("next_review", today)
                try:
                    overdue = (datetime.strptime(today, "%Y-%m-%d")
                               - datetime.strptime(nrd, "%Y-%m-%d")).days
                    max_overdue = max(max_overdue, overdue)
                except (ValueError, TypeError):
                    pass

            if len(all_due) < 3 and max_overdue <= 2:
                pass  # ????
            else:
                all_due.sort(key=lambda x: x[1].get("next_review", ""))
                nid, sm2 = all_due[0]
                node = nodes.get(nid, {})
                return {
                    "action": "review",
                    "node_id": nid,
                    "stage": 5,
                    "reason": f"SM-2 ????: {node.get('label', nid)}",
                    "context": {
                        "node_label": node.get("label", nid),
                        "weight": node.get("weight", "key_point"),
                        "is_must_know": node.get("weight") == "must_know",
                        "sm2_interval": sm2.get("interval", 0),
                        "sm2_ease": sm2.get("ease", 2.5),
                    }
                }
        else:
            all_due.sort(key=lambda x: x[1].get("next_review", ""))
            nid, sm2 = all_due[0]
            node = nodes.get(nid, {})
            return {
                "action": "review",
                "node_id": nid,
                "stage": 5,
                "reason": f"SM-2 ????: {node.get('label', nid)}",
                "context": {
                    "node_label": node.get("label", nid),
                    "weight": node.get("weight", "key_point"),
                    "is_must_know": node.get("weight") == "must_know",
                    "sm2_interval": sm2.get("interval", 0),
                    "sm2_ease": sm2.get("ease", 2.5),
                }
            }

    # ============================================================
    #  ??? 5??? 2 ? ??
    # ============================================================
    if current_stage == 2:
        unlearned_must = []
        unlearned_key = []
        for nid in topo_order:
            pn = prog_nodes.get(nid, {})
            if pn.get("stage2_done"):
                continue
            node = nodes.get(nid, {})
            prereqs_met = all(
                prog_nodes.get(pr, {}).get("stage2_done", False)
                for pr in node.get("prerequisites", [])
            )
            if not prereqs_met:
                continue
            if node.get("weight") == "must_know":
                unlearned_must.append(nid)
            else:
                unlearned_key.append(nid)

        next_nid = None
        if unlearned_must:
            next_nid = unlearned_must[0]
        elif unlearned_key:
            next_nid = unlearned_key[0]

        if next_nid:
            node = nodes.get(next_nid, {})
            return {
                "action": "teach",
                "node_id": next_nid,
                "stage": 2,
                "reason": f"?? 2 ??: {node.get('label', next_nid)}",
                "context": {
                    "node_label": node.get("label", next_nid),
                    "weight": node.get("weight", "key_point"),
                    "prerequisites_met": True,
                    "hooks": node.get("hooks", []),
                    "current_round": 1,
                    "user_level": user_level or "unknown",
                    "node_mastery": prog_nodes.get(next_nid, {}).get("mastery", "unknown") if next_nid else "unknown",
                    "knowledge_map_summary": _km_context(progress, topo_order),
                }
            }

        return {
            "action": "advance_stage",
            "node_id": None,
            "stage": 2,
            "reason": "?? 2 ????????? 3",
            "context": {"next_stage": 3}
        }

    # ============================================================
    #  ??? 6??? 3 ? ???? must_know ?????
    # ============================================================
    if current_stage == 3:
        untested_must = []
        untested_key = []
        for nid in topo_order:
            pn = prog_nodes.get(nid, {})
            node = nodes.get(nid, {})
            if not pn.get("stage2_done"):
                continue
            if pn.get("stage3_passed") is not None:
                continue
            if node.get("weight") == "must_know":
                untested_must.append(nid)
            else:
                untested_key.append(nid)

        next_nid = untested_must[0] if untested_must else (untested_key[0] if untested_key else None)

        if next_nid:
            node = nodes.get(next_nid, {})

            cross_review_candidates = []
            for nid in topo_order:
                pn = prog_nodes.get(nid, {})
                cn = nodes.get(nid, {})
                if (cn.get("weight") == "must_know"
                        and pn.get("stage3_passed")
                        and nid != next_nid
                        and pn.get("sm2", {}).get("next_review")
                        and pn["sm2"]["next_review"] <= today):
                    cross_review_candidates.append(nid)

            return {
                "action": "test",
                "node_id": next_nid,
                "stage": 3,
                "reason": f"?? 3 ??: {node.get('label', next_nid)}",
                "context": {
                    "node_label": node.get("label", next_nid),
                    "weight": node.get("weight", "key_point"),
                    "exam_types": [k for k, v in node.get("exam_types_map", {}).items() if v],
                    "is_must_know": node.get("weight") == "must_know",
                    "cross_review": cross_review_candidates,
                }
            }

        has_errors = bool(progress.get("error_nodes"))
        return {
            "action": "complete_stage3",
            "node_id": None,
            "stage": 3,
            "reason": "?? 3 ????" + ("???? -> ???? 4?" if has_errors else "???????"),
            "context": {
                "has_errors": has_errors,
                "next_stage": 4 if has_errors else None,
            }
        }

    # ============================================================
    #  ??? 7?????
    # ============================================================
    return {
        "action": "done",
        "node_id": None,
        "stage": 99,
        "reason": "???????????",
        "context": {}
    }


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="Cram Engine ?????")
    parser.add_argument("--course", required=True)
    parser.add_argument("--progress", required=True)
    parser.add_argument("--index", required=True)
    args = parser.parse_args()

    progress = read_json(Path(args.progress))
    index = read_json(Path(args.index))
    result = schedule(progress, index)
    print(json.dumps(result, ensure_ascii=False, indent=2))
