import time
from django.core.management.base import BaseCommand
from django.db import close_old_connections
from submissions.mailer import send_notifications


class Command(BaseCommand):
    help = '发送待处理通知；默认执行一轮，--loop 持续运行。'

    def add_arguments(self, parser):
        parser.add_argument('--loop', action='store_true')
        parser.add_argument('--interval', type=int, default=15)

    def handle(self, *args, **options):
        while True:
            close_old_connections()
            sent, failed = send_notifications()
            if sent or failed or not options['loop']:
                self.stdout.write(f'通知任务：成功 {sent}，等待重试/失败 {failed}。')
            if not options['loop']:
                return
            time.sleep(max(5, options['interval']))
