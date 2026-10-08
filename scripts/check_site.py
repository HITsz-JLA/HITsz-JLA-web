"""Read-only validation of the production Hugo output. Python standard library only."""
import argparse
import json
import re
from collections import Counter
from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import unquote, urljoin, urlsplit

parser = argparse.ArgumentParser()
parser.add_argument('directory', type=Path)
args = parser.parse_args()
root = args.directory.resolve()
files = {p.relative_to(root).as_posix(): p for p in root.rglob('*') if p.is_file()}
errors = []
references = 0
residue = re.compile(r'homepage_draft|data-local-form|data-local-preview|data-save-draft|data-official-form|jla-preview-draft|jla-homepage-draft|本地设计预览|本机预览|公开留言快照|原站正式提交|全部分页设计导览|127\.0\.0\.1:4173')

class Canonical(HTMLParser):
    base = 'https://hitszjla.club/'
    def handle_starttag(self, tag, attributes):
        attributes = dict(attributes)
        if tag == 'link' and attributes.get('rel') == 'canonical':
            self.base = attributes['href']

canonical = Canonical()
canonical.feed(files['index.html'].read_text(encoding='utf-8'))
site_url = urlsplit(canonical.base)
site_prefix = site_url.path.rstrip('/') + '/'

def check(url, source):
    global references
    if not url or url.startswith(('#', 'mailto:', 'tel:', 'data:', 'javascript:')):
        return
    resolved = urlsplit(urljoin(canonical.base + source, url))
    if resolved.netloc != site_url.netloc:
        return
    if resolved.path.startswith(('/community/', '/quiz-release/')):
        return  # Existing independently hosted applications.
    pathname = resolved.path
    if pathname.startswith(site_prefix):
        pathname = pathname[len(site_prefix):]
    name = unquote(pathname).lstrip('/')
    if not name or name.endswith('/'):
        name += 'index.html'
    if name not in files:
        errors.append(f'{source}: missing target {name}')
    references += 1

class Page(HTMLParser):
    def __init__(self, name):
        super().__init__(convert_charrefs=True)
        self.name = name
        self.ids = []
        self.tracks = []
        self.forms = []
    def handle_starttag(self, tag, attributes):
        attributes = dict(attributes)
        if 'id' in attributes:
            self.ids.append(attributes['id'])
        if 'data-title' in attributes and 'data-src' in attributes:
            self.tracks.append(attributes)
        if 'data-community-form' in attributes:
            self.forms.append(attributes.get('data-kind'))
        for key in ('href', 'src', 'data-audio', 'data-src', 'data-cover', 'poster', 'data-search-index'):
            if key in attributes:
                check(attributes[key], self.name)
        if tag == 'meta' and attributes.get('http-equiv', '').lower() == 'refresh':
            check(attributes.get('content', '').split('url=')[-1], self.name)

pages = {}
for name, file in files.items():
    if re.search(r'\.(?:save|bak|ps1|py|zip|gz|sqlite3?|env)$', name) or name.startswith(('tools/', 'source/', 'preview/', 'design/', 'email/', '.local/')):
        errors.append('Private, backup or design-only file in output: ' + name)
    if file.suffix not in ('.html', '.js', '.css', '.json'):
        continue
    text = file.read_text(encoding='utf-8-sig')
    if residue.search(text):
        errors.append('Design-only content in output: ' + name)
    if file.suffix == '.html':
        page = Page(name)
        page.feed(text)
        pages[name] = page
        duplicates = [key for key, count in Counter(page.ids).items() if count > 1]
        if duplicates:
            errors.append(f'{name}: duplicate IDs {duplicates}')
    if file.suffix == '.css':
        for match in re.finditer(r'url\([\'"]?([^\)\'"\s]+)[\'"]?\)', text):
            check(match[1], name)

for route in ('index.html', 'about/index.html', 'news/index.html', 'events/index.html', 'lyrics/index.html',
              'readings/index.html', 'grammar/index.html', 'participate/index.html', 'search/index.html', '404.html'):
    if route not in pages:
        errors.append('Missing main route: ' + route)
for route in ('index.html', 'participate/index.html'):
    if route in pages:
        page = pages[route]
        if sorted(page.forms) != ['feedback', 'song']:
            errors.append('Missing real submission forms: ' + route)
        for needed in ('community-notice', 'feedback-list', 'public-count', 'load-more', 'retry-list'):
            if needed not in page.ids:
                errors.append(route + ': missing community element ' + needed)

search = json.loads(files['search-data.json'].read_text(encoding='utf-8'))
for entry in search:
    check(entry['url'], 'search-data.json')
tracks = pages['index.html'].tracks
if len(tracks) != len([entry for entry in search if entry['section'] == 'lyrics']):
    errors.append('Homepage playlist differs from published song count')
if not all(track.get('data-src') and track.get('data-cover') for track in tracks):
    errors.append('Incomplete playlist metadata')
report = {'html_pages': len(pages), 'references_checked': references, 'songs': len(tracks),
          'search_entries': len(search), 'errors': errors}
print(json.dumps(report, ensure_ascii=False, indent=2))
raise SystemExit(1 if errors else 0)
