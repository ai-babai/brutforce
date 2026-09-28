#!/usr/bin/env python3
"""Publish the first PROD route, preserving the exact Caddy placeholder."""
from pathlib import Path
import subprocess

route=Path('/etc/caddy/sites-enabled/lct-previews.caddy')
backup=Path('/etc/lct-release/pre-prod-caddy.backup')
old=route.read_text()
placeholder='root * /srv/lct/prod/public\n\tfile_server'
replacement='import lct_catalog_media\n\treverse_proxy 127.0.0.1:8104'
if old.count(placeholder)!=1 or 'reverse_proxy 127.0.0.1:8104' in old:
    raise RuntimeError('Expected exactly one unpublished PROD placeholder')
new=old.replace(placeholder,replacement,1)
backup.write_text(old)
route.write_text(new)
try:
    subprocess.run(['caddy','validate','--config','/etc/caddy/Caddyfile'],check=True)
    subprocess.run(['systemctl','reload','caddy'],check=True)
except Exception:
    route.write_text(old)
    subprocess.run(['systemctl','reload','caddy'],check=True)
    raise
