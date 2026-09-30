"""Import private mail settings without ever printing credentials."""
import argparse
import json
from pathlib import Path
import re
import secrets
from email.utils import formataddr


def read_mail(path):
    raw = path.read_text(encoding='utf-8-sig')
    def field(label):
        match = re.search(r'^\s*' + re.escape(label) + r'\s*[:：]\s*([^\r\n]+)', raw, re.M)
        return match.group(1).strip() if match else ''
    address = field('邮箱地址')
    password = field('IMAP/SMTP授权码')
    host = field('SMTP服务器')
    if not address or not password or not host:
        raise ValueError('邮箱文件缺少邮箱地址、IMAP/SMTP授权码或SMTP服务器字段。')
    cc_section = re.split(r'需要抄送的邮箱\s*[:：]', raw, maxsplit=1)
    cc = re.findall(r'[A-Za-z0-9.!#$%&\x27*+/=?^_`{|}~-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}', cc_section[1]) if len(cc_section) == 2 else []
    return {'smtp_host': host, 'smtp_port': 465, 'smtp_ssl': True, 'smtp_tls': False,
            'smtp_username': address, 'smtp_password': password,
            'from_email': formataddr(('HITsz日语社网站', address)),
            'notify_to': [address], 'notify_cc': list(dict.fromkeys(cc))}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--repo', required=True)
    parser.add_argument('--production-config', action='store_true')
    args = parser.parse_args()
    repo = Path(args.repo).resolve()
    private = repo / '.local/community'
    private.mkdir(parents=True, exist_ok=True)
    path = private / ('production-config.json' if args.production_config else 'config.json')
    existing = json.loads(path.read_text(encoding='utf-8')) if path.exists() else {}
    config = {**existing, **read_mail(repo / 'email/emailinfo.txt')}
    config.setdefault('secret_key', secrets.token_urlsafe(64))
    if args.production_config:
        config.update(production=True, email_mode='smtp', base_url='https://hitszjla.club',
                      allowed_hosts=['hitszjla.club', 'www.hitszjla.club', 'localhost', '127.0.0.1'],
                      csrf_trusted_origins=['https://hitszjla.club'],
                      data_dir='/var/lib/jla-community', static_root='/var/www/jla-community-admin-static')
    else:
        config.update(production=False, email_mode='file', base_url='http://127.0.0.1:8790',
                      allowed_hosts=['localhost', '127.0.0.1'],
                      csrf_trusted_origins=[], data_dir=str(private / 'data'), static_root=str(private / 'admin-static'))
    path.write_text(json.dumps(config, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    path.chmod(0o600)
    print('私有配置已生成；' + ('生产环境使用 SMTP。' if args.production_config else '本地邮件保存到文件，不发送到真实邮箱。'))


if __name__ == '__main__':
    main()
