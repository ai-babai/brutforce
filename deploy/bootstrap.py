#!/usr/bin/env python3
"""Run once as root on Sigma. Does not deploy PROD or alter personal previews."""
import json, os, pathlib, pwd, secrets, shlex, subprocess
BASE=pathlib.Path(__file__).resolve().parent

def run(*args,input=None): return subprocess.run(args,input=input,text=True,check=True,stdout=subprocess.DEVNULL)
def file(path,text,mode=0o644,owner=None):
    p=pathlib.Path(path); p.parent.mkdir(parents=True,exist_ok=True); p.write_text(text); p.chmod(mode)
    if owner: u=pwd.getpwnam(owner); os.chown(p,u.pw_uid,u.pw_gid)
def sql(text): run('runuser','-u','postgres','--','psql','-X','-v','ON_ERROR_STOP=1',input=text)
try: pwd.getpwnam('lct-release')
except KeyError: run('useradd','--system','--create-home','--shell','/bin/bash','lct-release')
u=pwd.getpwnam('lct-release')
for p in ['/srv/lct/releases/packages','/srv/lct/releases/records','/srv/lct/releases/public','/srv/lct/stage','/srv/lct/data/stage/photos','/srv/lct/data/prod/photos']:
    pathlib.Path(p).mkdir(parents=True,exist_ok=True); os.chown(p,u.pw_uid,u.pw_gid); os.chmod(p,0o750)
# Existing /srv/lct/prod/public placeholder remains untouched.
run('setfacl','-m','u:lct-release:rwx','/srv/lct/prod')
for p in ['/srv/lct','/srv/lct/data','/srv/lct/data/stage','/srv/lct/data/prod']:
    run('setfacl','-m','u:lct-release:--x',p)
os.chown('/srv/lct/releases',u.pw_uid,u.pw_gid)
run('setfacl','-m','u:caddy:--x','/srv/lct/releases')
run('setfacl','-m','u:caddy:r-x,d:u:caddy:r-x','/srv/lct/releases/public')
# Create new production roles only once; never rotate existing credentials.
prod=pathlib.Path('/etc/lct-release/prod-runtime.env')
if not prod.exists():
    exists=subprocess.check_output(['runuser','-u','postgres','--','psql','-Atqc',"SELECT count(*) FROM pg_database WHERE datname='lct_prod'"]).decode().strip()
    if exists!='0': raise RuntimeError('Existing lct_prod needs manual mapping; no credentials changed')
    runtime=secrets.token_urlsafe(32); migration=secrets.token_urlsafe(32)
    sql(f"CREATE ROLE lct_prod_migrate LOGIN PASSWORD '{migration}'; CREATE ROLE lct_prod_runtime LOGIN PASSWORD '{runtime}'; CREATE DATABASE lct_prod OWNER lct_prod_migrate; REVOKE ALL ON DATABASE lct_prod FROM PUBLIC; GRANT CONNECT ON DATABASE lct_prod TO lct_prod_runtime;")
    run('runuser','-u','postgres','--','psql','-X','-v','ON_ERROR_STOP=1','-d','lct_prod',input="REVOKE ALL ON SCHEMA public FROM PUBLIC; ALTER SCHEMA public OWNER TO lct_prod_migrate; GRANT USAGE ON SCHEMA public TO lct_prod_runtime; ALTER DEFAULT PRIVILEGES FOR ROLE lct_prod_migrate IN SCHEMA public GRANT SELECT,INSERT,UPDATE,DELETE ON TABLES TO lct_prod_runtime; ALTER DEFAULT PRIVILEGES FOR ROLE lct_prod_migrate IN SCHEMA public GRANT USAGE,SELECT ON SEQUENCES TO lct_prod_runtime;")
    for role,password,key in [('runtime',runtime,'DATABASE_URL'),('migrate',migration,'MIGRATION_DATABASE_URL')]:
        filename='prod-runtime.env' if role=='runtime' else 'prod-migration.env'
        file('/etc/lct-release/'+filename,f'{key}=postgresql://lct_prod_{role}:{password}@/lct_prod?host=/var/run/postgresql\n',0o600,'lct-release')
# Copy only narrowly needed shared credentials, not full zone env.
values={}
for line in pathlib.Path('/etc/lct-db/shared.env').read_text().splitlines():
    if line.strip() and not line.startswith('#'):
        k,v=line.split('=',1); values[k]=shlex.split(v)[0]
for role,key in [('runtime','DATABASE_URL'),('migration','MIGRATION_DATABASE_URL')]:
    file('/etc/lct-release/test-'+role+'.env',key+'='+values['LCT_SHARED_'+role.upper()+'_DATABASE_URL']+'\n',0o600,'lct-release')
hba=pathlib.Path('/etc/postgresql/18/main/pg_hba.conf')
line='local   lct_prod lct_prod_migrate,lct_prod_runtime scram-sha-256\n'
if line not in hba.read_text():
    hba.write_text(line+hba.read_text())
    run('systemctl','reload','postgresql@18-main')
backup=pathlib.Path('/usr/local/sbin/lct-db-backup')
text=backup.read_text().replace('lct_shared lct_maks lct_roman;', 'lct_shared lct_maks lct_roman lct_prod;')
text=text.replace("-name 'lct_roman-*.dump' ", "-name 'lct_roman-*.dump' -o -name 'lct_prod-*.dump' ")
backup.write_text(text)
config={'environments':{}}
for name,folder,port,engine in [('test','stage',8103,8113),('prod','prod',8104,8114)]:
    root=f'/srv/lct/{folder}/current'
    config['environments'][name]={'path':f'/srv/lct/{folder}','url':f'http://127.0.0.1:{port}','migrationEnv':f'/etc/lct-release/{name}-migration.env'}
    common=f'User=lct-release\nGroup=lct-release\nWorkingDirectory={root}\nNoNewPrivileges=true\nPrivateTmp=true\nProtectSystem=strict\nProtectHome=true\nRestart=on-failure\nMemoryMax=512M\nCPUQuota=100%\nTasksMax=64\n'
    file(f'/etc/systemd/system/brutforce-{name}-reference.service',f'[Unit]\nDescription=BrutForce {name} SYNTHETIC reference engine\nAfter=network.target\n[Service]\n{common}Environment=ADDRESS=127.0.0.1:{engine}\nExecStart={root}/reference-engine\n[Install]\nWantedBy=multi-user.target\n')
    file(f'/etc/systemd/system/brutforce-{name}.service',f'[Unit]\nDescription=BrutForce {name} application\nAfter=network.target postgresql.service brutforce-{name}-reference.service\nRequires=brutforce-{name}-reference.service\n[Service]\n{common}EnvironmentFile=/etc/lct-release/{name}-runtime.env\nEnvironment=ADDRESS=127.0.0.1:{port}\nEnvironment=WEB_ROOT={root}/web\nEnvironment=UPLOAD_DIR=/srv/lct/data/{folder}/photos\nEnvironment=UPLOAD_MAX_BYTES=209715200\nEnvironment=SEARCH_SERVICE_URL=http://127.0.0.1:{engine}\nEnvironment=RECOMMENDATION_SERVICE_URL=http://127.0.0.1:{engine}\nEnvironment=CATALOG_VERSION=demo-v1\nReadWritePaths=/srv/lct/data/{folder}/photos\nExecStart={root}/brutforce-api\n[Install]\nWantedBy=multi-user.target\n')
file('/etc/lct-release/config.json',json.dumps(config,indent=2)+'\n')
file('/usr/local/lib/lct-release/release.py',(BASE/'release.py').read_text(),0o755)
file('/usr/local/bin/lct-release','#!/bin/sh\nexec /usr/bin/python3 /usr/local/lib/lct-release/release.py "$@"\n',0o755)
file('/usr/local/sbin/lct-release-service',r'''#!/bin/sh
set -eu
case "${1-}" in
 restart-test|restart-prod)
  zone=${1#restart-}
  systemctl restart "brutforce-$zone-reference.service" "brutforce-$zone.service"
  systemctl enable "brutforce-$zone-reference.service" "brutforce-$zone.service" >/dev/null ;;
 stop-test|stop-prod)
  zone=${1#stop-}; systemctl stop "brutforce-$zone.service" "brutforce-$zone-reference.service" ;;
 backup-prod)
  stamp=$(date -u +%Y%m%dT%H%M%SZ)
  dir=/srv/lct/data/backups/postgres
  umask 077
  runuser -u postgres -- pg_dump -Fc lct_prod > "$dir/lct_prod-$stamp.dump.partial"
  pg_restore --list "$dir/lct_prod-$stamp.dump.partial" >/dev/null
  mv "$dir/lct_prod-$stamp.dump.partial" "$dir/lct_prod-$stamp.dump" ;;
 publish-prod)
  python3 /usr/local/lib/lct-release/publish-prod.py ;;
 *) exit 2 ;;
esac
''',0o755)
file('/usr/local/lib/lct-release/publish-prod.py',r'''from pathlib import Path
import subprocess
p=Path('/etc/caddy/sites-enabled/lct-previews.caddy')
old=p.read_text()
placeholder='root * /srv/lct/prod/public\n\tfile_server'
new=old.replace(placeholder,'reverse_proxy 127.0.0.1:8104')
if new==old and 'reverse_proxy 127.0.0.1:8104' not in old: raise SystemExit('Unexpected app route; no edit')
if new!=old:
    Path('/etc/lct-release/pre-prod-caddy.backup').write_text(old)
    p.write_text(new)
    try:
        subprocess.run(['caddy','validate','--config','/etc/caddy/Caddyfile'],check=True)
        subprocess.run(['systemctl','reload','caddy'],check=True)
    except Exception:
        p.write_text(old)
        subprocess.run(['systemctl','reload','caddy'],check=True)
        raise
''',0o755)
file('/etc/sudoers.d/lct-release','lct-release ALL=(root) NOPASSWD: /usr/local/sbin/lct-release-service *\nsigma-ops ALL=(lct-release) NOPASSWD: /usr/local/bin/lct-release *\n',0o440)
run('visudo','-cf','/etc/sudoers.d/lct-release')
run('systemctl','daemon-reload')
print('Prepared units and isolated credentials. No PROD deployed.')
