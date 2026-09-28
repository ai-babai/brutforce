#!/usr/bin/env python3
"""Restore only the first-PROD Caddy placeholder from publish-prod's backup."""
from pathlib import Path
import subprocess

route=Path('/etc/caddy/sites-enabled/lct-previews.caddy')
backup=Path('/etc/lct-release/pre-prod-caddy.backup')
before=route.read_text()
if 'reverse_proxy 127.0.0.1:8104' in before:
    original=backup.read_text()
    if 'root * /srv/lct/prod/public' not in original or 'reverse_proxy 127.0.0.1:8104' in original:
        raise RuntimeError('Saved PROD placeholder is invalid')
    route.write_text(original)
    try:
        subprocess.run(['caddy','validate','--config','/etc/caddy/Caddyfile'],check=True)
        subprocess.run(['systemctl','reload','caddy'],check=True)
    except Exception:
        route.write_text(before)
        subprocess.run(['systemctl','reload','caddy'],check=True)
        raise
