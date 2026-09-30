#!/usr/bin/env bash
# Run on the server from an uploaded backend directory. Does not edit Nginx.
set -euo pipefail
if [[ $(id -u) -ne 0 ]]; then echo 'Run as root.' >&2; exit 1; fi
exec 9>/run/lock/jla-community-install.lock
flock -n 9 || { echo 'Another backend installation is running.' >&2; exit 1; }
source_dir=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)
if [[ ! -f /etc/jla-community/config.json ]]; then
  echo 'Install the private production config at /etc/jla-community/config.json first.' >&2
  exit 1
fi
command -v python3 >/dev/null
if ! python3 -c 'import venv, ensurepip' 2>/dev/null; then
  echo 'Install python3-venv first: apt-get install python3-venv' >&2
  exit 1
fi
id jla-community >/dev/null 2>&1 || useradd --system --user-group --home-dir /var/lib/jla-community --shell /usr/sbin/nologin jla-community
install -d -m 0750 -o jla-community -g jla-community /var/lib/jla-community /var/backups/jla-community
install -d -m 0755 /opt/jla-community/releases
install -d -m 0755 -o jla-community -g jla-community /var/www/jla-community-admin-static
chown root:jla-community /etc/jla-community /etc/jla-community/config.json
chmod 0750 /etc/jla-community
chmod 0640 /etc/jla-community/config.json
release="/opt/jla-community/releases/$(date -u +%Y%m%d-%H%M%S)-$$"
mkdir -m 0755 "$release"
cp -R "$source_dir" "$release/backend"
find "$release/backend" -type d -name __pycache__ -prune -exec rm -rf -- {} +
python3 -m venv "$release/.venv"
"$release/.venv/bin/pip" install -r "$release/backend/requirements.txt"
export JLA_CONFIG_FILE=/etc/jla-community/config.json
export PYTHONUTF8=1
old=$(readlink -f /opt/jla-community/current || true)
if [[ -n "$old" && -f "$old/backend/manage.py" && -f /var/lib/jla-community/community.sqlite3 ]]; then
  "$old/.venv/bin/python" "$old/backend/manage.py" backup_database --directory /var/backups/jla-community
fi
"$release/.venv/bin/python" "$release/backend/manage.py" check --deploy --fail-level WARNING
"$release/.venv/bin/python" "$release/backend/manage.py" migrate --noinput
"$release/.venv/bin/python" "$release/backend/manage.py" collectstatic --noinput
chown -R jla-community:jla-community /var/lib/jla-community /var/backups/jla-community
find /var/www/jla-community-admin-static -type d -exec chmod 0755 {} +
find /var/www/jla-community-admin-static -type f -exec chmod 0644 {} +
install -m 0644 "$release/backend/deploy/"*.service "$release/backend/deploy/"*.timer /etc/systemd/system/
install -d -m 0755 /etc/nginx/snippets
install -m 0644 "$release/backend/deploy/nginx-community.conf" /etc/nginx/snippets/jla-community.conf
ln -s "$release" /opt/jla-community/current.next
mv -Tf /opt/jla-community/current.next /opt/jla-community/current
systemctl daemon-reload
systemctl enable jla-community jla-community-mail jla-community-backup.timer
systemctl restart jla-community jla-community-mail || true
systemctl start jla-community-backup.timer
healthy=0
for attempt in 1 2 3 4 5; do
  if systemctl is-active --quiet jla-community && systemctl is-active --quiet jla-community-mail && \
      curl --fail --silent -H 'Host: hitszjla.club' -H 'X-Forwarded-Proto: https' \
      http://127.0.0.1:8790/community/api/health/ >/dev/null; then healthy=1; break; fi
  sleep 2
done
if [[ "$healthy" != 1 ]]; then
  if [[ -n "$old" && -d "$old" ]]; then
    ln -s "$old" /opt/jla-community/current.rollback
    mv -Tf /opt/jla-community/current.rollback /opt/jla-community/current
    systemctl restart jla-community jla-community-mail
  else
    systemctl stop jla-community jla-community-mail
  fi
  echo 'Backend health check failed. Inspect journalctl. Database migrations were not reversed.' >&2
  exit 1
fi
printf 'Backend installed: %s\n' "$release"
echo 'Add include /etc/nginx/snippets/jla-community.conf; inside the HTTPS server block, then nginx -t and reload.'
echo 'Create a moderator with init_moderator or createsuperuser before publishing the Hugo frontend.'
