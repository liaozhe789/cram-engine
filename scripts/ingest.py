'''Cram Engine 资料摄入模块。

支持格式：.txt / .md / .pdf / .png / .jpg
- 文本文件直接读取清洗
- PDF 提取文本（多后端：pdfplumber > PyPDF2 > pdfminer）
- 图片复制到 raw/，生成占位文本（实际OCR由skill层协调Codex Vision）

输出：knowledge/<课程名>/extracted/*.txt
'''

import json
import sys
import re
import shutil
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from utils import (
    skill_dir, knowledge_raw_dir, knowledge_extracted_dir, ensure_dirs, clean_text,
)

SUPPORTED_EXTS = {'.txt', '.md', '.pdf', '.png', '.jpg', '.jpeg'}


def ingest(course: str, input_path: str) -> list:
    src = Path(input_path)
    if not src.exists():
        print(f'ERROR: input not found: {src}')
        sys.exit(1)

    output_dir = knowledge_extracted_dir(course)
    raw_dir = knowledge_raw_dir(course)
    ensure_dirs(output_dir, raw_dir)

    results = []

    if src.is_file():
        results.extend(_process_file(src, raw_dir, output_dir))
    elif src.is_dir():
        for f in sorted(src.iterdir()):
            if f.suffix.lower() in SUPPORTED_EXTS:
                results.extend(_process_file(f, raw_dir, output_dir))
    else:
        print(f'ERROR: not a file or directory: {src}')
        sys.exit(1)

    return results


def _process_file(src: Path, raw_dir: Path, output_dir: Path) -> list:
    ext = src.suffix.lower()
    results = []

    try:
        if ext in {'.txt', '.md'}:
            results.append(_process_text(src, output_dir))
        elif ext == '.pdf':
            results.append(_process_pdf(src, raw_dir, output_dir))
        elif ext in {'.png', '.jpg', '.jpeg'}:
            results.append(_process_image(src, raw_dir, output_dir))
        else:
            print(f'SKIP: unsupported format: {src}')
    except Exception as e:
        print(f'ERROR processing {src.name}: {e}')

    return results


def _process_text(src: Path, output_dir: Path) -> Path:
    text = src.read_text(encoding='utf-8', errors='replace')
    text = clean_text(text)
    out = output_dir / f'{src.stem}.txt'
    out.write_text(text, encoding='utf-8')
    print(f'  TEXT: {src.name} -> {out.name} ({len(text)} chars)')
    return out


def _process_pdf(src: Path, raw_dir: Path, output_dir: Path) -> Path:
    text = None

    try:
        import pdfplumber
        with pdfplumber.open(str(src)) as pdf:
            pages = []
            for page in pdf.pages:
                pt = page.extract_text()
                if pt:
                    pages.append(pt)
            text = '\n\n'.join(pages)
        if text:
            print(f'  PDF(pdfplumber): {src.name} ({len(pdf.pages)} pages)')
    except ImportError:
        pass
    except Exception as e:
        print(f'  pdfplumber failed: {e}')

    if not text:
        try:
            from PyPDF2 import PdfReader
            reader = PdfReader(str(src))
            pages = [page.extract_text() or '' for page in reader.pages]
            text = '\n\n'.join(pages)
            if text.strip():
                print(f'  PDF(PyPDF2): {src.name} ({len(reader.pages)} pages)')
        except ImportError:
            pass
        except Exception as e:
            print(f'  PyPDF2 failed: {e}')

    if not text:
        try:
            from pdfminer.high_level import extract_text
            text = extract_text(str(src))
            if text.strip():
                print(f'  PDF(pdfminer): {src.name}')
        except ImportError:
            pass
        except Exception as e:
            print(f'  pdfminer failed: {e}')

    if not text or not text.strip():
        dest = raw_dir / src.name
        shutil.copy2(str(src), str(dest))
        text = f'[IMAGE_PDF] {src.name} - 需要Vision提取。原始文件: {src.name}'
        print(f'  PDF(IMAGE): {src.name} -> needs Vision (copied to raw/)')

    text = clean_text(text)
    out = output_dir / f'{src.stem}.txt'
    out.write_text(text, encoding='utf-8')
    return out


def _process_image(src: Path, raw_dir: Path, output_dir: Path) -> Path:
    dest = raw_dir / src.name
    shutil.copy2(str(src), str(dest))
    text = f'[IMAGE] {src.name} - 需要Vision提取。原始文件: {src.name}'
    out = output_dir / f'{src.stem}.txt'
    out.write_text(text, encoding='utf-8')
    print(f'  IMAGE: {src.name} -> {out.name} (needs Vision)')
    return out


if __name__ == '__main__':
    import argparse
    parser = argparse.ArgumentParser(description='Cram Engine Material Ingester')
    parser.add_argument('--course', required=True)
    parser.add_argument('--input', required=True)
    args = parser.parse_args()

    results = ingest(args.course, args.input)
    print(f'\nIngested {len(results)} file(s) for course: {args.course}')
    for r in results:
        print(f'  -> {r}')
