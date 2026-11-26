r"""把一期每周文法排成 PDF 讲义，版式参照 example/ 里的往期文件。

用法（在仓库根目录执行）：
    python .\scripts\make_grammar_pdf.py 2026-10-27

读取 content/grammar/<日期>.md 的标题和 content/grammarpoints/<日期>-*.md 的
内容，渲染成 HTML 后用 Edge 无头模式打印为 example/<标题>.pdf。
首页是刊头加第一个语法点，之后每个语法点单独一页。

依赖：系统自带的 Microsoft Edge；pip install pyyaml pypdf
"""

import argparse
import glob
import os
import re
import subprocess
import sys
import tempfile

import pypdf
import yaml

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT_DIR = os.path.join(ROOT, 'example')
EDGE = r'C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe'

JP_FONT = '"Yu Gothic UI", "Yu Gothic", Meiryo, "MS PGothic", sans-serif'
CN_FONT = '"Microsoft YaHei", "Yu Gothic UI", Meiryo, sans-serif'
KANA = re.compile(r'[\u3040-\u30ff]')
TAGS = re.compile(r'<[^>]+>')

CSS = """
@page { size: A4; margin: 8mm; }
* { box-sizing: border-box; }
body { margin: 0; -webkit-print-color-adjust: exact; print-color-adjust: exact; }
.page {
  background: #f6f7f9; padding: 26px 32px 34px; min-height: 281mm;
  page-break-after: always;
}
.page:last-child { page-break-after: auto; }

.masthead { text-align: center; padding: 30px 0 8px; }
.masthead h1 { font-size: 33px; font-weight: 700; color: #0f1115; margin: 0; letter-spacing: 2px; }
.masthead .issue { font-size: 11px; color: #6b7280; margin: 11px 0 0; }
.masthead .tagline { font-size: 13.5px; color: #1f2430; margin: 11px 0 0; }
.masthead .sep { border-top: 1px solid #d8dade; margin: 22px 0 30px; }

.gp-head {
  background: #dfe6fa; border-left: 7px solid #4a6fd4; border-radius: 10px;
  padding: 16px 24px 14px; margin-bottom: 22px;
}
.gp-head h2 { font-size: 28px; font-weight: 700; color: #16255e; margin: 0; font-family: JPFONT; }
.gp-head .level { font-size: 11px; color: #6b7280; margin: 8px 0 0; }

h3.sec { font-size: 13.5px; font-weight: 700; color: #0f1115; margin: 20px 0 9px; }
.rule { border-top: 1px solid #d8dade; margin-bottom: 12px; }

p { margin: 0; }
.conn { font-size: 11.5px; line-height: 1.95; color: #1f2430; font-family: JPFONT; }
.gloss { font-size: 11.5px; line-height: 1.9; color: #1f2430; margin-bottom: 14px; }
.expl p { font-size: 11.5px; line-height: 1.88; color: #1f2430; }

.ex-box { background: #eceffb; border-radius: 10px; padding: 20px 24px 22px; margin-top: 24px; }
.ex-box h4 { font-size: 13px; font-weight: 700; color: #0f1115; margin: 0 0 10px; }
.ex { margin-top: 14px; }
.ex:first-of-type { margin-top: 0; }
.ex .jp { font-size: 12.5px; line-height: 1.75; color: #1a1f2e; font-family: JPFONT; }
.ex .cn { font-size: 10.5px; line-height: 1.75; color: #4b5563; margin-top: 3px; }
""".replace('JPFONT', JP_FONT)


def level_label(level):
    return 'N4・N5' if level.upper() == 'N4N5' else level.upper()


def font_for(text):
    """讲解正文按实际语言选字体：假名密度高的按日文排，否则按中文排。"""
    plain = TAGS.sub('', text)
    return JP_FONT if plain and len(KANA.findall(plain)) / len(plain) > 0.15 else CN_FONT


def render_point(data):
    explanation = data.get('explanation', '').strip()
    chunks = re.split(r'<br\s*/?>\s*<br\s*/?>', explanation, maxsplit=1)
    gloss = chunks[0]
    body = chunks[1] if len(chunks) > 1 else ''

    parts = ['<div class="gp-head"><h2>%s</h2><p class="level">语法等级：%s</p></div>'
             % (data['title'], level_label(data.get('grammarlevel', '')))]

    parts.append('<h3 class="sec">接続</h3><div class="rule"></div>')
    parts.append('<p class="conn">%s</p>' % data.get('connection', '').strip())

    parts.append('<h3 class="sec">讲解</h3><div class="rule"></div>')
    parts.append('<p class="gloss">%s</p>' % gloss)
    if body:
        lines = [line for line in re.split(r'<br\s*/?>', body) if line.strip()]
        parts.append('<div class="expl" style="font-family:%s">%s</div>'
                     % (font_for(body), ''.join('<p>%s</p>' % l.strip() for l in lines)))

    parts.append('<div class="ex-box"><h4>例句</h4><div class="rule"></div>')
    for example in data.get('examples') or []:
        parts.append('<div class="ex"><p class="jp">%s</p><p class="cn">%s</p></div>'
                     % (example['jp'], example.get('cn', '')))
    parts.append('</div>')
    return ''.join(parts)


def front_matter(path):
    return yaml.safe_load(open(path, encoding='utf-8').read().split('---')[1])


def build_html(date):
    issue_path = os.path.join(ROOT, 'content', 'grammar', date + '.md')
    title = front_matter(issue_path)['title']
    number = re.search(r'第(.+?)次', title).group(1)

    paths = sorted(glob.glob(os.path.join(ROOT, 'content', 'grammarpoints', date + '-*.md')),
                   key=lambda p: front_matter(p).get('level_sort', 99))
    if not paths:
        sys.exit('没有找到 ' + date + ' 的文法点')

    masthead = (
        '<div class="masthead"><h1>毎週文法</h1>'
        '<p class="issue">%s 第%d週</p>'
        '<p class="tagline">毎週少しずつ、文法を身につけよう！</p>'
        '<div class="sep"></div></div>' % (date, cn_number(number)))

    pages = []
    for index, path in enumerate(paths):
        head = masthead if index == 0 else ''
        pages.append('<div class="page">%s%s</div>' % (head, render_point(front_matter(path))))

    html = ('<!DOCTYPE html><html lang="zh"><head><meta charset="utf-8">'
            '<style>body{font-family:%s}%s</style></head><body>%s</body></html>'
            % (CN_FONT, CSS, ''.join(pages)))
    return title, html, len(paths)


DIGITS = '零一二三四五六七八九'


def cn_number(text):
    """把“十六”这样的中文数字转成 16，用于刊头的“第16週”。"""
    if '十' not in text:
        return DIGITS.index(text)
    left, _, right = text.partition('十')
    return (DIGITS.index(left) if left else 1) * 10 + (DIGITS.index(right) if right else 0)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('date', help='文法期号日期，如 2026-10-27')
    args = parser.parse_args()

    title, html, points = build_html(args.date)
    os.makedirs(OUT_DIR, exist_ok=True)
    target = os.path.join(OUT_DIR, title.replace('每週文法', '每周文法') + '.pdf')

    handle, source = tempfile.mkstemp(suffix='.html')
    os.close(handle)
    open(source, 'w', encoding='utf-8').write(html)
    try:
        subprocess.run([EDGE, '--headless', '--disable-gpu', '--no-pdf-header-footer',
                        '--print-to-pdf=' + target, source],
                       check=True, capture_output=True, timeout=180)
    finally:
        os.remove(source)
    print('write %s  %d bytes' % (target, os.path.getsize(target)))

    # 每个语法点占一页；多出来的页说明某页排不下，需要再调版面。
    pages = len(pypdf.PdfReader(target).pages)
    print('pages %d (语法点 %d 个)' % (pages, points))
    if pages != points:
        sys.exit('页数与语法点数量不符，有内容溢出到了次页')


main()
