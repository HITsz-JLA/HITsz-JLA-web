import json
import os
import sys
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
REPO_DIR = BASE_DIR.parent
TESTING = os.environ.get('JLA_TESTING') == '1' or 'test' in sys.argv
CONFIG_FILE = Path(os.environ.get('JLA_CONFIG_FILE', REPO_DIR / '.local/community/config.json'))
CONFIG = json.loads(CONFIG_FILE.read_text(encoding='utf-8-sig')) if CONFIG_FILE.exists() else {}
SECRET_KEY = os.environ.get('JLA_SECRET_KEY') or CONFIG.get('secret_key', '')
if TESTING:
    SECRET_KEY = 'test-only-never-use-in-production'
elif len(SECRET_KEY) < 40:
    raise RuntimeError('请先执行 scripts/community.ps1 -Action Setup，或设置 JLA_CONFIG_FILE。')

DEBUG = False
PRODUCTION = CONFIG.get('production', False) and not TESTING
ALLOWED_HOSTS = CONFIG.get('allowed_hosts', ['localhost', '127.0.0.1', '[::1]'])
if TESTING:
    ALLOWED_HOSTS = ['testserver', 'localhost', '127.0.0.1']
INSTALLED_APPS = [
    'django.contrib.admin', 'django.contrib.auth', 'django.contrib.contenttypes',
    'django.contrib.sessions', 'django.contrib.messages', 'django.contrib.staticfiles',
    'submissions.apps.SubmissionsConfig',
]
MIDDLEWARE = [
    'django.middleware.security.SecurityMiddleware',
    'django.contrib.sessions.middleware.SessionMiddleware',
    'django.middleware.common.CommonMiddleware',
    'django.middleware.csrf.CsrfViewMiddleware',
    'django.contrib.auth.middleware.AuthenticationMiddleware',
    'django.contrib.messages.middleware.MessageMiddleware',
    'django.middleware.clickjacking.XFrameOptionsMiddleware',
    'submissions.middleware.LoginThrottleMiddleware',
]
ROOT_URLCONF = 'config.urls'
WSGI_APPLICATION = 'config.wsgi.application'
TEMPLATES = [{
    'BACKEND': 'django.template.backends.django.DjangoTemplates',
    'DIRS': [BASE_DIR / 'templates'], 'APP_DIRS': True,
    'OPTIONS': {'context_processors': [
        'django.template.context_processors.request',
        'django.contrib.auth.context_processors.auth',
        'django.contrib.messages.context_processors.messages',
    ]},
}]
DATA_DIR = Path(CONFIG.get('data_dir', REPO_DIR / '.local/community/data'))
DATA_DIR.mkdir(parents=True, exist_ok=True)
DATABASES = {'default': {
    'ENGINE': 'django.db.backends.sqlite3', 'NAME': DATA_DIR / 'community.sqlite3',
    'OPTIONS': {'timeout': 20, 'transaction_mode': 'IMMEDIATE'},
}}
DEFAULT_AUTO_FIELD = 'django.db.models.BigAutoField'
AUTH_PASSWORD_VALIDATORS = [
    {'NAME': 'django.contrib.auth.password_validation.UserAttributeSimilarityValidator'},
    {'NAME': 'django.contrib.auth.password_validation.MinimumLengthValidator', 'OPTIONS': {'min_length': 12}},
    {'NAME': 'django.contrib.auth.password_validation.CommonPasswordValidator'},
    {'NAME': 'django.contrib.auth.password_validation.NumericPasswordValidator'},
]
LANGUAGE_CODE = 'zh-hans'
TIME_ZONE = 'Asia/Shanghai'
USE_I18N = True
USE_TZ = True
STATIC_URL = '/community/static/'
STATIC_ROOT = Path(CONFIG.get('static_root', REPO_DIR / '.local/community/admin-static'))
SESSION_COOKIE_NAME = 'jla_community_session'
SESSION_COOKIE_PATH = '/community/'
SESSION_COOKIE_HTTPONLY = True
SESSION_COOKIE_SECURE = PRODUCTION
SESSION_COOKIE_SAMESITE = 'Lax'
SESSION_COOKIE_AGE = 8 * 60 * 60
CSRF_COOKIE_NAME = 'jla_community_csrf'
CSRF_COOKIE_PATH = '/community/'
CSRF_COOKIE_HTTPONLY = True
CSRF_COOKIE_SECURE = PRODUCTION
CSRF_TRUSTED_ORIGINS = CONFIG.get('csrf_trusted_origins', [])
CSRF_FAILURE_VIEW = 'submissions.views.csrf_failure'
SECURE_PROXY_SSL_HEADER = ('HTTP_X_FORWARDED_PROTO', 'https') if PRODUCTION else None
SECURE_SSL_REDIRECT = PRODUCTION
SECURE_HSTS_SECONDS = 31536000 if PRODUCTION else 0
SECURE_HSTS_INCLUDE_SUBDOMAINS = False
# Other subdomains are outside this app's scope; do not opt them into HSTS/preload.
SILENCED_SYSTEM_CHECKS = ['security.W005', 'security.W021']
SECURE_CONTENT_TYPE_NOSNIFF = True
X_FRAME_OPTIONS = 'DENY'
DATA_UPLOAD_MAX_MEMORY_SIZE = 16 * 1024
DATA_UPLOAD_MAX_NUMBER_FIELDS = 30
COMMUNITY_BASE_URL = CONFIG.get('base_url', 'http://127.0.0.1:8790').rstrip('/')
TRUST_LOOPBACK_PROXY = PRODUCTION
FORM_MIN_SECONDS = 2
SUBMISSION_RATE_LIMIT = 5
SUBMISSION_RATE_SECONDS = 600
LOGIN_RATE_LIMIT = 20
LOGIN_RATE_SECONDS = 900

EMAIL_MODE = os.environ.get('JLA_EMAIL_MODE', CONFIG.get('email_mode', 'file'))
EMAIL_BACKEND = ('django.core.mail.backends.smtp.EmailBackend' if EMAIL_MODE == 'smtp'
                 else 'django.core.mail.backends.filebased.EmailBackend')
if TESTING:
    EMAIL_BACKEND = 'django.core.mail.backends.locmem.EmailBackend'
EMAIL_FILE_PATH = str(DATA_DIR / 'mail-preview')
EMAIL_HOST = CONFIG.get('smtp_host', '')
EMAIL_PORT = int(CONFIG.get('smtp_port', 465))
EMAIL_USE_SSL = bool(CONFIG.get('smtp_ssl', True))
EMAIL_USE_TLS = bool(CONFIG.get('smtp_tls', False))
EMAIL_HOST_USER = CONFIG.get('smtp_username', '')
EMAIL_HOST_PASSWORD = CONFIG.get('smtp_password', '')
EMAIL_TIMEOUT = 20
DEFAULT_FROM_EMAIL = CONFIG.get('from_email', EMAIL_HOST_USER)
NOTIFY_TO = CONFIG.get('notify_to', [])
NOTIFY_CC = CONFIG.get('notify_cc', [])
EMAIL_SUBJECT_PREFIX = '[HITsz日语社] '

# No request bodies, SMTP passwords, or raw addresses are logged by this app.
LOGGING = {
    'version': 1, 'disable_existing_loggers': False,
    'handlers': {'console': {'class': 'logging.StreamHandler'}},
    'root': {'handlers': ['console'], 'level': 'WARNING'},
}
