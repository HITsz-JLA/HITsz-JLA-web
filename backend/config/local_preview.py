"""Only registered by urls.py for explicitly enabled, non-production previews."""
import mimetypes
import os
from pathlib import Path
from django.conf import settings
from django.http import FileResponse, Http404


def serve_file(base, path):
    base = Path(base).resolve()
    candidate = (base / path).resolve()
    if not candidate.is_relative_to(base):
        raise Http404
    if candidate.is_dir():
        candidate = candidate / 'index.html'
    if not candidate.is_file():
        raise Http404
    response = FileResponse(candidate.open('rb'), content_type=mimetypes.guess_type(str(candidate))[0] or 'application/octet-stream')
    response['Cache-Control'] = 'no-store'
    return response


def site(request, path=''):
    if path.startswith('community/'):
        raise Http404
    return serve_file(os.environ['JLA_LOCAL_SITE'], path)


def admin_static(request, path):
    return serve_file(settings.STATIC_ROOT, path)
