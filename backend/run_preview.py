"""Serve Hugo output and Django under one LOCAL origin, including the mail worker."""
import argparse
import os
from pathlib import Path
import subprocess
import sys


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--site', required=True)
    parser.add_argument('--port', type=int, default=8790)
    args = parser.parse_args()
    os.environ['JLA_LOCAL_SITE'] = str(Path(args.site).resolve())
    os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')
    import django
    django.setup()
    from django.conf import settings
    from django.core.wsgi import get_wsgi_application
    from waitress import serve
    if settings.PRODUCTION:
        raise RuntimeError('Local preview cannot use production configuration.')
    worker = subprocess.Popen(
        [sys.executable, str(Path(__file__).parent / 'manage.py'), 'send_notifications', '--loop'],
        creationflags=subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0,
    )
    try:
        print(f'本地网站：http://127.0.0.1:{args.port}/', flush=True)
        print(f'审核后台：http://127.0.0.1:{args.port}/community/admin/', flush=True)
        print(f'邮件模式：{settings.EMAIL_MODE}；Ctrl+C 停止网站及通知进程。', flush=True)
        serve(get_wsgi_application(), host='127.0.0.1', port=args.port, threads=4, clear_untrusted_proxy_headers=True)
    finally:
        worker.terminate()
        try:
            worker.wait(timeout=5)
        except subprocess.TimeoutExpired:
            worker.kill()
            worker.wait()


if __name__ == '__main__':
    main()
