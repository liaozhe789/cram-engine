'''Cram Engine 进度持久化与查询。

提供 init / status / update 三个子命令。
每次写入采用原子替换 + 自动备份。
所有共享逻辑统一从 utils 导入。
'''

import json
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent))

from utils import (
    progress_path, index_path, atomic_write_json, read_json, now_iso, now_date,
)


def cmd_init(course: str) -> dict:
    index = read_json(index_path(course))
    if not index:
        print(f'ERROR: index.json not found for course "{course}"')
        sys.exit(1)

    nodes = {}
    for node in index.get('nodes', []):
        nodes[node['id']] = {
            'stage1_done': True,
            'stage2_done': False,
            'stage3_passed': None,
            'stage3_wrong_answers': [],
            'stage4_done': False,
            'stage4_retry_count': 0,
            'stubborn': False,
            'mastery': 'untouched',
            'sm2': {
                'interval': 0,
                'ease': 2.5,
                'repetitions': 0,
                'next_review': None,
            },
            'last_updated': now_iso(),
        }

    topo = index.get('topo_order', [])
    progress = {
        'course': course,
        'current_stage': 0,  # ???0??????
        'current_node_id': topo[0] if topo else None,
        'user_level': 'unknown',
        'user_level_source': '',
        'knowledge_map': {},
        'stage2_pace': 'normal',
        'stage2_position': 0,
        'stage3_position': 0,
        'stage3_current_submode': None,
        'nodes': nodes,
        'completed_nodes': [],
        'error_nodes': [],
        'stubborn_nodes': [],
        'session_history': [],
    }

    atomic_write_json(progress_path(course), progress)
    return progress


def cmd_status(course: str) -> dict:
    progress = read_json(progress_path(course))
    if not progress:
        print(f'ERROR: No progress file for course "{course}". Run init first.')
        sys.exit(1)
    index = read_json(index_path(course))

    total = len(progress['nodes'])
    stage2_done = sum(1 for n in progress['nodes'].values() if n['stage2_done'])
    stage3_passed = sum(1 for n in progress['nodes'].values() if n['stage3_passed'])
    error_count = len(progress.get('error_nodes', []))
    stubborn_count = len(progress.get('stubborn_nodes', []))

    must_ids = []
    if index:
        must_ids = [n['id'] for n in index.get('nodes', []) if n.get('weight') == 'must_know']
    must_total = len(must_ids)
    must_mastered = sum(
        1 for mid in must_ids
        if mid in progress['nodes']
        and progress['nodes'][mid].get('mastery') == 'mastered'
    )

    # SM-2 到期复习列表
    today = now_date()
    sm2_due = []
    for nid, n in progress['nodes'].items():
        sm2 = n.get('sm2', {})
        next_review = sm2.get('next_review')
        if next_review and next_review <= today:
            sm2_due.append(nid)

    result = {
        'course': course,
        'current_stage': progress['current_stage'],
        'current_node': progress.get('current_node_id'),
        'user_level': progress.get('user_level', 'unknown'),
        'user_level_source': progress.get('user_level_source', ''),
        'knowledge_map_summary': _km_summary(progress),
        'total_nodes': total,
        'stage2_done': stage2_done,
        'stage3_passed': stage3_passed,
        'error_count': error_count,
        'stubborn_count': stubborn_count,
        'sm2_due_count': len(sm2_due),
        'must_know_total': must_total,
        'must_know_mastered': must_mastered,
        'must_know_rate': f'{must_mastered}/{must_total}' if must_total > 0 else 'N/A',
    }

    print(f'===== {course} =====')
    print(f"Stage: {progress["current_stage"]}  |  Node: {progress.get("current_node_id", "-")}")
    print(f"Level: {progress.get("user_level", "unknown")}")
    print(f'Learned: {stage2_done}/{total}  |  Tested: {stage3_passed}/{total}')
    print(f'Must-know: {must_mastered}/{must_total}')
    print(f'Errors: {error_count}  |  Stubborn: {stubborn_count}')
    print(f'SM-2 due: {len(sm2_due)}')
    if sm2_due:
        print('  Due for review:')
        for sid in sm2_due[:5]:
            label = sid
            if index:
                for n in index.get('nodes', []):
                    if n['id'] == sid:
                        label = n.get('label', sid)
                        break
            sm2_info = progress['nodes'].get(sid, {}).get('sm2', {})
            print(f'  - {label}  (interval: {sm2_info.get("interval", 0)}d, ease: {sm2_info.get("ease", 2.5)})')
    if progress.get('stubborn_nodes'):
        print('Stubborn nodes:')
        for sid in progress['stubborn_nodes']:
            label = sid
            if index:
                for n in index.get('nodes', []):
                    if n['id'] == sid:
                        label = n.get('label', sid)
                        break
            print(f'  ! {label} ({sid})')
    return result


def cmd_update(course: str, updates_json: str):
    progress = read_json(progress_path(course))
    if not progress:
        print(f'ERROR: No progress file for course "{course}"')
        sys.exit(1)

    try:
        updates = json.loads(updates_json)
    except json.JSONDecodeError as e:
        print(f'ERROR: Invalid JSON: {e}')
        sys.exit(1)

    def deep_merge(base, patch):
        for key, value in patch.items():
            if isinstance(value, dict) and isinstance(base.get(key), dict):
                deep_merge(base[key], value)
            else:
                base[key] = value

    deep_merge(progress, updates)
    _auto_mastery_check(progress)

    progress['session_history'].append({
        'timestamp': now_iso(),
        'updates': {k: v for k, v in updates.items() if k != 'session_history'},
    })

    atomic_write_json(progress_path(course), progress)
    print(f'Progress updated: stage={progress['current_stage']}')


def _km_summary(progress: dict) -> dict:
    km = progress.get('knowledge_map', {})
    if not km:
        return {}
    return {
        'strong': sum(1 for v in km.values() if v.get('level') == 'strong'),
        'developing': sum(1 for v in km.values() if v.get('level') == 'developing'),
        'weak': sum(1 for v in km.values() if v.get('level') == 'weak'),
        'unknown': sum(1 for v in km.values() if v.get('level') == 'unknown'),
    }


def _auto_mastery_check(progress: dict):
    for node_id, node in progress.get('nodes', {}).items():
        if node.get('stubborn'):
            node['mastery'] = 'stubborn'
        elif node.get('stage2_done') and node.get('stage3_passed'):
            # stage3 ??? mastered ???????????? stage4?
            node['mastery'] = 'mastered'
        elif node.get('stage4_done'):
            # ? stage4_done ? stage3_passed ?? True??????????? learning
            node['mastery'] = 'learning'
        elif node.get('stage2_done') and node.get('stage3_passed') is False:
            node['mastery'] = 'weak'
        elif node.get('stage2_done') and node.get('stage3_passed') is None:
            node['mastery'] = 'learning'
        else:
            node['mastery'] = node.get('mastery', 'untouched')


if __name__ == '__main__':
    import argparse
    parser = argparse.ArgumentParser(description='Cram Engine Progress Manager')
    sub = parser.add_subparsers(dest='command')

    p_init = sub.add_parser('init')
    p_init.add_argument('--course', required=True)

    p_status = sub.add_parser('status')
    p_status.add_argument('--course', required=True)

    p_update = sub.add_parser('update')
    p_update.add_argument('--course', required=True)
    p_update.add_argument('--data', required=True, help='JSON merge data')

    args = parser.parse_args()
    if args.command == 'init':
        cmd_init(args.course)
    elif args.command == 'status':
        cmd_status(args.course)
    elif args.command == 'update':
        cmd_update(args.course, args.data)
    else:
        parser.print_help()
