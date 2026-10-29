r"""生成每周文法例句的日语语音。

用法（在仓库根目录执行）：
    python .\scripts\make_grammar_audio.py 2026-10-27

会读取 content/grammarpoints/<日期>-*.md 的 examples[].jp，去掉 HTML 标签后
用 edge-tts 合成日语语音，按既有命名写入 static/audio/grammar/，
例如 2026-10-27 的 N1 第 1 句 -> static/audio/grammar/261027-n1-1.mp3。
已存在的文件默认跳过，加 --force 覆盖。

依赖：pip install edge-tts
"""

import argparse
import asyncio
import glob
import os
import re
import sys

import edge_tts
import yaml

VOICE = 'ja-JP-NanamiNeural'
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT_DIR = os.path.join(ROOT, 'static', 'audio', 'grammar')
TAGS = re.compile(r'<[^>]+>')


def plain(jp):
    """去掉 <strong> 等标签和括号里的中文注记，只留要朗读的日文。"""
    text = TAGS.sub('', jp)
    text = re.sub(r'[（(][^）)]*[）)]', '', text)
    return text.strip()


def collect(date):
    """返回 [(输出文件名, 朗读文本), ...]。"""
    short = date.replace('-', '')[2:]
    jobs = []
    pattern = os.path.join(ROOT, 'content', 'grammarpoints', date + '-*.md')
    for path in sorted(glob.glob(pattern)):
        level = os.path.basename(path)[len(date) + 1:-3].lower()
        front = open(path, encoding='utf-8').read().split('---')[1]
        examples = yaml.safe_load(front).get('examples') or []
        for index, example in enumerate(examples, 1):
            name = '%s-%s-%d.mp3' % (short, level, index)
            jobs.append((name, plain(example['jp'])))
    return jobs


async def speak(name, text, force):
    target = os.path.join(OUT_DIR, name)
    if os.path.exists(target) and not force:
        print('skip  ' + name)
        return
    await edge_tts.Communicate(text, VOICE).save(target)
    print('write %s  %6d bytes  %s' % (name, os.path.getsize(target), text))


async def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('date', help='文法期号日期，如 2026-10-27')
    parser.add_argument('--force', action='store_true', help='覆盖已存在的音频')
    args = parser.parse_args()

    jobs = collect(args.date)
    if not jobs:
        sys.exit('没有找到 ' + args.date + ' 的文法例句')
    os.makedirs(OUT_DIR, exist_ok=True)
    for name, text in jobs:
        await speak(name, text, args.force)
    print('共 %d 句' % len(jobs))


asyncio.run(main())
