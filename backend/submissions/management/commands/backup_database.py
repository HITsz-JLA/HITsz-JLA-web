import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from django.conf import settings
from django.core.management.base import BaseCommand


class Command(BaseCommand):
    help = '使用 SQLite 在线备份接口创建一致性备份（包含 WAL 中已提交数据）。'

    def add_arguments(self, parser):
        parser.add_argument('--directory', required=True)

    def handle(self, *args, **options):
        directory = Path(options['directory']).resolve()
        directory.mkdir(parents=True, exist_ok=True)
        destination = directory / ('community-' + datetime.now(timezone.utc).strftime('%Y%m%d-%H%M%S-%f') + '.sqlite3')
        with sqlite3.connect(settings.DATABASES['default']['NAME']) as source:
            with sqlite3.connect(destination) as target:
                source.backup(target)
        destination.chmod(0o600)
        self.stdout.write(f'备份完成：{destination}')
