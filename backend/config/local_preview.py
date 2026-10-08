"""Only registered by urls.py for explicitly enabled, non-production previews."""
import mimetypes
import os
import re
from pathlib import Path
from django.conf import settings
from django.http import FileResponse, Http404, HttpResponse, StreamingHttpResponse


def file_chunks(candidate, start, length):
    with candidate.open('rb') as stream:
        stream.seek(start)
        while length:
            chunk = stream.read(min(length, 64 * 1024))
            if not chunk:
                break
            length -= len(chunk)
            yield chunk


def serve_file(base, path, request):
    base = Path(base).resolve()
    candidate = (base / path).resolve()
    if not candidate.is_relative_to(base):
        raise Http404
    if candidate.is_dir():
        candidate = candidate / 'index.html'
    if not candidate.is_file():
        raise Http404
    content_type = mimetypes.guess_type(str(candidate))[0] or 'application/octet-stream'
    size = candidate.stat().st_size
    # Audio players request byte ranges when loading metadata or seeking.
    # Ignore unsupported/malformed ranges and If-Range without a validator.
    match = re.fullmatch(r'bytes=([0-9]{0,20})-([0-9]{0,20})', request.headers.get('Range', ''))
    if request.method == 'GET' and match and any(match.groups()) and not request.headers.get('If-Range'):
        first, last = match.groups()
        start = int(first) if first else max(0, size - int(last))
        end = min(int(last), size - 1) if first and last else size - 1
        if start >= size or start > end:
            response = HttpResponse(status=416)
            response['Content-Range'] = f'bytes */{size}'
        else:
            response = StreamingHttpResponse(file_chunks(candidate, start, end - start + 1),
                                             status=206, content_type=content_type)
            response['Content-Range'] = f'bytes {start}-{end}/{size}'
            response['Content-Length'] = str(end - start + 1)
    else:
        response = FileResponse(candidate.open('rb'), content_type=content_type)
    response['Accept-Ranges'] = 'bytes'
    response['Cache-Control'] = 'no-store'
    return response


def site(request, path=''):
    if path.startswith('community/'):
        raise Http404
    return serve_file(os.environ['JLA_LOCAL_SITE'], path, request)


def admin_static(request, path):
    return serve_file(settings.STATIC_ROOT, path, request)
