'''Cram Engine 公共工具函数。

统一提供：路径工具、JSON原子读写、文本清洗、YAML解析（含范围格式支持）、
SM-2间隔重复算法、SM-2质量评分辅助函数、日期时间工具。
'''

import re
import json
import hashlib
import unicodedata
from pathlib import Path
from datetime import datetime, timezone, timedelta

# ============================================================
#  路径工具
# ============================================================

def skill_dir() -> Path:
    return Path(__file__).resolve().parent.parent

def config_path(course: str) -> Path:
    return skill_dir() / 'configs' / f'{course}.yaml'

def index_path(course: str) -> Path:
    return skill_dir() / 'knowledge' / course / 'index.json'

def progress_path(course: str) -> Path:
    return skill_dir() / 'progress' / f'{course}.json'

def progress_backup_path(course: str) -> Path:
    return skill_dir() / 'progress' / f'{course}.json.bak'

def knowledge_raw_dir(course: str) -> Path:
    return skill_dir() / 'knowledge' / course / 'raw'

def knowledge_extracted_dir(course: str) -> Path:
    return skill_dir() / 'knowledge' / course / 'extracted'

def ensure_dirs(*paths: Path) -> None:
    for p in paths:
        p.mkdir(parents=True, exist_ok=True)

# ============================================================
#  JSON 原子读写
# ============================================================

def atomic_write_json(filepath: Path, data) -> None:
    filepath.parent.mkdir(parents=True, exist_ok=True)
    if filepath.exists():
        backup = Path(str(filepath) + '.bak')
        try:
            filepath.replace(backup)
        except Exception:
            pass
    tmp = Path(str(filepath) + '.tmp')
    tmp.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding='utf-8')
    tmp.replace(filepath)

def read_json(filepath: Path):
    if not filepath.exists():
        return None
    return json.loads(filepath.read_text(encoding='utf-8'))

# ============================================================
#  文本清洗
# ============================================================

def clean_text(text: str) -> str:
    text = text.replace('\r\n', '\n').replace('\r', '\n')
    text = re.sub(r'[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]', '', text)
    text = re.sub(r'\n{3,}', '\n\n', text)
    text = re.sub(r'[ \t]+', ' ', text)
    text = re.sub(r' \n', '\n', text)
    text = re.sub(r'\n ', '\n', text)
    return text.strip()

def has_formula(text: str) -> bool:
    latex_patterns = [r'\$[^\$]+\$', r'\$\$[^\$]+\$\$', r'\\[\w{]+', r'\\frac', r'\\sum', r'\\int']
    for pat in latex_patterns:
        if re.search(pat, text):
            return True
    unicode_math = re.findall(r'[\u2200-\u22FF\u0300-\u036F]', text)
    return len(unicode_math) > 2

# ============================================================
#  ID 与 Slug 工具
# ============================================================

def slugify(text: str) -> str:
    text = unicodedata.normalize('NFKD', text)
    text = re.sub(r'[^\w\s-]', '', text).strip().lower()
    text = re.sub(r'[-\s]+', '-', text)
    return text[:80]

def node_id_from_label(label: str) -> str:
    sid = slugify(label)
    return sid if sid else hashlib.md5(label.encode()).hexdigest()[:12]

# ============================================================
#  YAML 解析（统一入口，支持 must_know_ids 范围格式如 "3-5"）
# ============================================================

def read_yaml(filepath: Path) -> dict:
    if not filepath.exists():
        raise FileNotFoundError(f'配置文件不存在: {filepath}')
    text = filepath.read_text(encoding='utf-8')
    return _parse_yaml(text)

def write_yaml(filepath: Path, data: dict) -> None:
    filepath.parent.mkdir(parents=True, exist_ok=True)
    content = _dump_yaml(data)
    filepath.write_text(content, encoding='utf-8')

def _parse_yaml(text: str) -> dict:
    '''解析简化 YAML，支持 list、dict 嵌套、范围格式 must_know_ids'''
    result = {}
    stack = [(result, -1)]
    current_list_key = None

    for line in text.splitlines():
        stripped = line.rstrip()
        if not stripped or stripped.startswith('#'):
            continue
        indent = len(line) - len(line.lstrip())

        while stack and stack[-1][1] >= indent:
            stack.pop()

        current_dict = stack[-1][0] if stack else result

        if stripped.lstrip().startswith('- '):
            item = stripped.lstrip()[2:].strip().strip('"').strip("'")
            if current_list_key:
                if not isinstance(current_dict.get(current_list_key), list):
                    current_dict[current_list_key] = []
                current_dict[current_list_key].append(item)
            continue

        if ':' in stripped:
            key, _, val = stripped.partition(':')
            key = key.strip()
            val = val.strip()

            if val:
                vl = val.lower()
                if vl == 'true':
                    val = True
                elif vl == 'false':
                    val = False
                elif vl in ('null', '~', ''):
                    val = None
                elif val.startswith('[') and val.endswith(']'):
                    items_str = val[1:-1]
                    items = re.findall(r'"([^"]*)"', items_str) or [i.strip() for i in items_str.split(',') if i.strip()]
                    val = items
                    current_list_key = None
                else:
                    val = val.strip('"').strip("'")
                    # 尝试检测范围格式: "3-5"
                    range_match = re.match(r'^(\d+)\s*-\s*(\d+)$', val)
                    if range_match:
                        start, end = int(range_match.group(1)), int(range_match.group(2))
                        val = [str(i) for i in range(start, end + 1)]
                    # 尝试检测数字列表: "7,11,14,15"
                    elif re.match(r'^[\d,\s]+$', val) and ',' in val:
                        val_list = [x.strip() for x in val.split(',') if x.strip()]
                        val = val_list if len(val_list) > 1 else val
                current_dict[key] = val
                current_list_key = None
            else:
                current_dict[key] = None
                current_list_key = key

    _fix_none_to_list(result)
    return result

def _fix_none_to_list(obj):
    if isinstance(obj, dict):
        for k, v in list(obj.items()):
            if v is None:
                obj[k] = []
            elif isinstance(v, dict):
                _fix_none_to_list(v)
            elif isinstance(v, list):
                for item in v:
                    if isinstance(item, (dict, list)):
                        _fix_none_to_list(item)
    return obj

def _dump_yaml(data, indent: int = 0) -> str:
    prefix = '  ' * indent
    lines = []
    if isinstance(data, dict):
        for k, v in data.items():
            if v is None:
                lines.append(f'{prefix}{k}: ~')
            elif isinstance(v, bool):
                lines.append(f'{prefix}{k}: {str(v).lower()}')
            elif isinstance(v, list):
                if all(isinstance(i, (str, int, float, bool)) for i in v):
                    items = ', '.join(
                        f'"{i}"' if isinstance(i, str) else str(i).lower() if isinstance(i, bool) else str(i)
                        for i in v
                    )
                    lines.append(f'{prefix}{k}: [{items}]')
                else:
                    lines.append(f'{prefix}{k}:')
                    for item in v:
                        if isinstance(item, dict):
                            inner = _dump_yaml(item, indent + 1)
                            for il in inner.splitlines():
                                lines.append(f'{prefix}  {il.lstrip()}' if il.strip() else '')
                        else:
                            lines.append(f'{prefix}  - {item}')
            elif isinstance(v, dict):
                lines.append(f'{prefix}{k}:')
                lines.append(_dump_yaml(v, indent + 1))
            elif isinstance(v, str):
                special = set(':#{}[]#&*!|><\"\'' + '\n')
                if any(c in v for c in special):
                    lines.append(f'{prefix}{k}: "{v}"')
                else:
                    lines.append(f'{prefix}{k}: {v}')
            else:
                lines.append(f'{prefix}{k}: {v}')
    elif isinstance(data, list):
        for item in data:
            if isinstance(item, dict):
                inner = _dump_yaml(item, indent)
                for il in inner.splitlines():
                    lines.append(f'{prefix}- {il.lstrip()}' if il.strip() else '')
            else:
                lines.append(f'{prefix}- {item}')
    return '\n'.join(lines)

# ============================================================
#  must_know_ids 范围解析辅助
# ============================================================

def expand_must_know_ids(raw_ids: list) -> set:
    '''将 must_know_ids 展开为字符串集合。

    输入可能是混在列表里的字符串，如 ["7", "11-15", "20"]。
    范围 "11-15" 已在 YAML 解析阶段展开，但如果传入尚未展开的字符串
    （例如直接从旧版 YAML 读取），这里进行二次保障。
    '''
    expanded = set()
    for item in raw_ids:
        if isinstance(item, str) and re.match(r'^\d+\s*-\s*\d+$', item):
            start, end = item.split('-')
            for i in range(int(start.strip()), int(end.strip()) + 1):
                expanded.add(str(i))
        else:
            expanded.add(str(item))
    return expanded

# ============================================================
#  SM-2 间隔重复算法
# ============================================================

def sm2_update(sm2_state: dict, quality: int, review_date: str = None) -> dict:
    '''SM-2 算法核心。

    quality: 0-5
      0-2: 完全错误 / 严重错误 / 勉强正确
        3: 正确但有困难
        4: 正确稍有犹豫
        5: 完美正确

    review_date: YYYY-MM-DD 格式的复习日期，默认今天
    '''
    if review_date is None:
        review_date = datetime.now(timezone.utc).strftime('%Y-%m-%d')

    interval = sm2_state.get('interval', 0)
    ease = sm2_state.get('ease', 2.5)
    repetitions = sm2_state.get('repetitions', 0)

    if quality >= 3:
        if repetitions == 0:
            interval = 1
        elif repetitions == 1:
            interval = 6
        else:
            interval = round(interval * ease)
        repetitions += 1
    else:
        repetitions = 0
        interval = 1

    ease = ease + (0.1 - (5 - quality) * (0.08 + (5 - quality) * 0.02))
    ease = max(1.3, ease)

    review_dt = datetime.strptime(review_date, '%Y-%m-%d')
    next_review_dt = review_dt + timedelta(days=interval)
    next_review = next_review_dt.strftime('%Y-%m-%d')

    return {
        'interval': interval,
        'ease': round(ease, 4),
        'repetitions': repetitions,
        'next_review': next_review,
    }

def sm2_quality_from_accuracy(correct: int, total: int, is_must_know: bool = False) -> int:
    '''根据答题准确率推算 SM-2 quality 值。

    must_know 节点评分更严格：答错任何一道 => quality <= 3
    '''
    if total == 0:
        return 3
    ratio = correct / total

    if is_must_know:
        if ratio == 1.0:
            return 5
        elif ratio >= 0.80:
            return 3
        elif ratio >= 0.60:
            return 2
        else:
            return 1
    else:
        if ratio == 1.0:
            return 5
        elif ratio >= 0.75:
            return 4
        elif ratio >= 0.50:
            return 3
        elif ratio >= 0.25:
            return 2
        else:
            return 1

# ============================================================
#  日期时间工具
# ============================================================

def now_iso() -> str:
    return datetime.now(timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ')

def now_date() -> str:
    return datetime.now(timezone.utc).strftime('%Y-%m-%d')

# ============================================================
#  OCR 响应解析（保留向后兼容）
# ============================================================

def parse_ocr_response(response_text: str) -> str:
    text = response_text.strip()
    noise_prefixes = [
        '以下是图片中的文字：',
        'OCR结果：',
        '识别结果：',
        '图片内容如下：',
        'Here is the text from the image:',
        'The extracted text is:',
        '`',
        '`	ext',
        '`plaintext',
    ]
    for prefix in noise_prefixes:
        if text.startswith(prefix):
            text = text[len(prefix):].strip()
    noise_suffixes = ['`']
    for suffix in noise_suffixes:
        if text.endswith(suffix):
            text = text[:-len(suffix)].strip()
    return text
