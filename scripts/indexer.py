'''Cram Engine 知识图谱索引构建器。

输入：课程配置 YAML + 摄入的文本资料
输出：index.json（含权重、前置依赖、拓扑排序）

构建策略：
1. 从 config 读取知识点列表和 must_know_ids（支持范围格式）
2. 分析知识点之间的概念依赖关系
3. 生成拓扑排序（must_know 优先）
4. 从摄入资料中提取每个知识点的内容摘要
'''

import json
import sys
import re
from pathlib import Path
from collections import defaultdict, deque

sys.path.insert(0, str(Path(__file__).resolve().parent))

from utils import (
    skill_dir, config_path, read_json, clean_text, slugify,
    expand_must_know_ids, read_yaml,
)


def build_index(course: str) -> dict:
    config = read_yaml(config_path(course))
    key_points = config.get('key_points', [])
    raw_must = config.get('must_know_ids', [])
    must_know_ids = expand_must_know_ids(raw_must)
    extracted_texts = _load_extracted(course)

    if not key_points:
        print('WARNING: No key_points in config. Index will be minimal.')

    nodes = []
    for i, kp in enumerate(key_points):
        label = kp.strip()
        node_id = slugify(label) or f'node-{i:03d}'
        raw_id = str(i + 1)          # 1-based index for matching
        weight = 'must_know' if (raw_id in must_know_ids or node_id in must_know_ids) else 'key_point'
        content_summary = _find_content(label, extracted_texts)
        hooks = _infer_hooks(label, content_summary, config.get('language', 'zh'))
        prereqs, parent = _infer_prerequisites_and_parent(i, nodes, label, config)
        exam_types = config.get('exam_types', [])
        exam_types_map = {et: True for et in exam_types}

        nodes.append({
            'id': node_id,
            'label': label,
            'parent': parent,
            'weight': weight,
            'prerequisites': prereqs,
            'hooks': hooks,
            'exam_types_map': exam_types_map,
            'content_summary': content_summary[:800] if content_summary else '',
            'source_materials': [],
            'order_index': i,
        })

    topo_order = _topological_sort(nodes)

    return {
        'course': course,
        'version': 2,
        'nodes': nodes,
        'topo_order': topo_order,
    }


def _load_extracted(course: str) -> dict:
    extracted_dir = skill_dir() / 'knowledge' / course / 'extracted'
    texts = {}
    if extracted_dir.exists():
        for f in sorted(extracted_dir.glob('*.txt')):
            texts[f.stem] = f.read_text(encoding='utf-8')
    return texts


def _find_content(label: str, extracted_texts: dict) -> str:
    snippets = []
    for source, text in extracted_texts.items():
        keywords = label.replace('(', ' ').replace(')', ' ').replace('/', ' ').split()
        for kw in keywords:
            if len(kw) >= 2 and kw.lower() in text.lower():
                idx = text.lower().find(kw.lower())
                start = max(0, idx - 200)
                end = min(len(text), idx + len(kw) + 200)
                snippet = text[start:end].strip()
                if snippet:
                    snippets.append(snippet)
                break
    return ' ... '.join(snippets[:3]) if snippets else ''


def _infer_hooks(label: str, content_summary: str, language: str = 'zh') -> list:
    """推断适合的记忆钩子类型。支持中英文关键词。"""
    hooks = []
    keywords = {
        'contrast': {
            'zh': ['区别', '对比', '比较', '差异', '不同', 'vs', '不同于', '相反', '优缺点'],
            'en': ['difference', 'compare', 'contrast', 'versus', 'pros and cons', 'advantages', 'disadvantages', 'unlike', 'however'],
        },
        'absurd': {
            'zh': ['抽象', '原理', '定理', '定律', '公理', '协议'],
            'en': ['abstract', 'principle', 'theorem', 'axiom', 'protocol', 'theory'],
        },
        'acronym': {
            'zh': ['步骤', '流程', '阶段', '层次', '分类', '类型', '层', '种'],
            'en': ['step', 'process', 'stage', 'layer', 'classification', 'type', 'category', 'phase', 'level'],
        },
    }
    contrast_keywords = keywords['contrast'].get(language, keywords['contrast']['zh'])
    absurd_keywords = keywords['absurd'].get(language, keywords['absurd']['zh'])
    acronym_keywords = keywords['acronym'].get(language, keywords['acronym']['zh'])
    # Also check other language as fallback
    other_lang = 'en' if language == 'zh' else 'zh'
    contrast_keywords += keywords['contrast'].get(other_lang, [])
    absurd_keywords += keywords['absurd'].get(other_lang, [])
    acronym_keywords += keywords['acronym'].get(other_lang, [])

    combined = label + (content_summary or '')
    if any(kw in combined for kw in contrast_keywords):
        hooks.append('contrast')
    if any(kw in combined for kw in absurd_keywords):
        hooks.append('absurd')
    if any(kw in combined for kw in acronym_keywords):
        hooks.append('acronym')
    return hooks if hooks else ['none']


def _infer_prerequisites_and_parent(
    current_idx: int,
    existing_nodes: list,
    label: str,
    config: dict,
) -> tuple:
    """推断父类目和前置依赖。支持中英文关键词。"""
    # 关键词 -> 父类目映射
    parent_map = {
        '排序': '排序算法',
        '查找': '查找算法',
        '图': '图论',
        '树': '树结构',
        '二叉树': '树结构',
        '遍历': '遍历技术',
        '搜索': '搜索技术',
        '链表': '线性结构',
        '顺序表': '线性结构',
        '栈': '线性结构',
        '队列': '线性结构',
        '串': '线性结构',
        '矩阵': '矩阵与广义表',
        '广义表': '矩阵与广义表',
        '哈夫曼': '树结构',
        '并查集': '树结构',
        '哈希': '查找算法',
        '散列': '查找算法',
        'B-树': '查找算法',
        'B+树': '查找算法',
        '递归': '基础概念',
        '复杂度': '基础概念',
        'KMP': '线性结构',
        '存储结构': '基础概念',
        # English keywords
        'sort': 'Sorting Algorithms', 'search': 'Search Algorithms',
        'graph': 'Graph Theory', 'tree': 'Tree Structures',
        'binary tree': 'Tree Structures', 'traversal': 'Traversal Techniques',
        'linked list': 'Linear Structures', 'array': 'Linear Structures',
        'stack': 'Linear Structures', 'queue': 'Linear Structures',
        'string': 'Linear Structures', 'matrix': 'Matrices & Generalized Lists',
        'huffman': 'Tree Structures', 'disjoint set': 'Tree Structures',
        'union find': 'Tree Structures', 'hash': 'Search Algorithms',
        'B-tree': 'Search Algorithms', 'B+tree': 'Search Algorithms',
        'recursion': 'Fundamentals', 'complexity': 'Fundamentals',
        'big o': 'Fundamentals', 'KMP': 'Linear Structures',
        'database': 'Databases', 'sql': 'Databases',
        'protocol': 'Protocols', 'network': 'Networking',
    }

    # 从 label 中找匹配的父类目
    language = config.get('language', 'zh')
    parent = 'Fundamentals' if language == 'en' else '基础概念'
    for kw, cat in sorted(parent_map.items(), key=lambda x: -len(x[0])):
        if kw.lower() in label.lower():
            parent = cat
            break

    # 如果 config 中指定了章节结构，优先使用
    if config.get('chapters'):
        for ch in config.get('chapters', []):
            if isinstance(ch, dict) and label in ch.get('topics', []):
                parent = ch.get('name', parent)
                break

    # 前置依赖：同一 parent 下的前一个节点（最多 2 个）
    prereqs = []
    same_parent = [n for n in existing_nodes if n.get('parent') == parent]
    if same_parent:
        # 取最近的一个 must_know 节点
        must_candidates = [n['id'] for n in same_parent if n.get('weight') == 'must_know']
        if must_candidates:
            prereqs.append(must_candidates[-1])
        # 再取最近的一个非 must_know（避免重复）
        other_candidates = [n['id'] for n in same_parent if n.get('weight') != 'must_know']
        if other_candidates and (not prereqs or prereqs[-1] != other_candidates[-1]):
            prereqs.append(other_candidates[-1])
        # 最多取 2 个
        prereqs = prereqs[-2:]

    # 如果没有任何前置依赖且不是第一个节点，尝试跨 parent 取前一个节点
    if not prereqs and existing_nodes:
        prereqs.append(existing_nodes[-1]['id'])

    return prereqs, parent


def _topological_sort(nodes: list) -> list:
    adj = defaultdict(list)
    in_degree = defaultdict(int)
    node_ids = {n['id'] for n in nodes}

    for n in nodes:
        for prereq in n.get('prerequisites', []):
            if prereq in node_ids:
                adj[prereq].append(n['id'])
                in_degree[n['id']] += 1

    must_know_q = deque()
    key_point_q = deque()
    for n in nodes:
        if in_degree.get(n['id'], 0) == 0:
            if n.get('weight') == 'must_know':
                must_know_q.append(n['id'])
            else:
                key_point_q.append(n['id'])

    result = []
    while must_know_q or key_point_q:
        if must_know_q:
            nid = must_know_q.popleft()
        elif key_point_q:
            nid = key_point_q.popleft()
        else:
            break
        result.append(nid)
        for neighbor in adj.get(nid, []):
            in_degree[neighbor] -= 1
            if in_degree[neighbor] == 0:
                neighbor_node = next((n for n in nodes if n['id'] == neighbor), None)
                if neighbor_node and neighbor_node.get('weight') == 'must_know':
                    must_know_q.append(neighbor)
                else:
                    key_point_q.append(neighbor)

    remaining = [n['id'] for n in nodes if n['id'] not in result]
    result.extend(remaining)
    return result


if __name__ == '__main__':
    import argparse
    parser = argparse.ArgumentParser(description='Cram Engine Knowledge Index Builder')
    parser.add_argument('--course', required=True)
    parser.add_argument('--output', required=True)
    args = parser.parse_args()

    index = build_index(args.course)
    output_path = Path(args.output)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(index, ensure_ascii=False, indent=2), encoding='utf-8')
    print(f'Index: {output_path}')
    must_count = sum(1 for n in index['nodes'] if n['weight'] == 'must_know')
    print(f'Nodes: {len(index["nodes"])}  |  Must-know: {must_count}')
    print(f'Topo order: {len(index["topo_order"])} nodes')
