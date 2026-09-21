#!/usr/bin/env python3
"""Small native release controller. Installed read-only; runs as lct-release."""
import datetime, fcntl, hashlib, json, os, pathlib, re, shlex, subprocess, sys, tarfile, tempfile, time, urllib.request
ROOT = pathlib.Path('/srv/lct/releases')
CONFIG = pathlib.Path('/etc/lct-release/config.json')

def require(ok, message):
    if not ok: raise RuntimeError(message)
def stamp(): return datetime.datetime.now(datetime.timezone.utc).isoformat()
def read(p): return json.loads(pathlib.Path(p).read_text())
def write(p, value):
    p = pathlib.Path(p); p.parent.mkdir(parents=True, exist_ok=True)
    tmp = p.with_suffix('.tmp'); tmp.write_text(json.dumps(value, ensure_ascii=False, indent=2)+'\n'); tmp.replace(p)
def digest(p):
    with open(p,'rb') as f: return hashlib.file_digest(f, 'sha256').hexdigest()
def revision(value):
    require(bool(re.fullmatch('[a-f0-9]{40}', value)), 'Expected full Git SHA'); return value

def record(sha): return ROOT/'records'/f'{sha}.json'
def load(sha): return read(record(sha))
def save(sha, r):
    r['updatedAt']=stamp(); write(record(sha), r); publish()
def publish():
    records = sorted((read(p) for p in (ROOT/'records').glob('*.json')), key=lambda x:x['updatedAt'], reverse=True)
    envs={}
    for name, cfg in read(CONFIG)['environments'].items():
        current=pathlib.Path(cfg['path'])/'current'
        envs[name] = current.resolve().name if current.is_symlink() else None
    write(ROOT/'public'/'status.json', {'updatedAt':stamp(), 'environments':envs, 'releases':records[:30]})
def command(*args, **kwargs): return subprocess.run(args, check=True, **kwargs)
def envfile(path):
    env=os.environ.copy()
    for line in pathlib.Path(path).read_text().splitlines():
        if line.strip() and not line.lstrip().startswith('#'):
            k,v=line.split('=',1); env[k]=shlex.split(v)[0]
    return env

def install(sha, checksum, run_id):
    require(bool(re.fullmatch('[a-f0-9]{64}', checksum)), 'Invalid checksum')
    require(run_id.isdigit(), 'Expected GitHub run ID')
    target=ROOT/'packages'/sha
    require(not target.exists(), 'Release already installed; use existing immutable release')
    with tempfile.TemporaryDirectory(dir=ROOT) as tmp:
        tmp=pathlib.Path(tmp); archive=tmp/'release.tar.gz'
        with archive.open('wb') as out:
            total=0
            while chunk:=sys.stdin.buffer.read(1024*1024):
                total+=len(chunk); require(total<=300*1024*1024, 'Package too large'); out.write(chunk)
        require(digest(archive)==checksum, 'Archive checksum mismatch')
        unpack=tmp/'unpack'; unpack.mkdir()
        with tarfile.open(archive) as tar:
            members=tar.getmembers()
            require(sum(x.size for x in members)<1024*1024*1024, 'Expanded package too large')
            for m in members:
                path=pathlib.PurePosixPath(m.name)
                require(not path.is_absolute() and '..' not in path.parts and (m.isfile() or m.isdir()), 'Unsafe archive member')
            tar.extractall(unpack, filter='data')
        manifest=read(unpack/'manifest.json')
        require(manifest['revision']==sha and (unpack/'REVISION').read_text().strip()==sha, 'Revision mismatch')
        require(manifest['mode']=='reference' and manifest['synthetic'] is True, 'Only approved demo mode supported')
        require(manifest['catalogVersion']=='demo-v1' and manifest['modelVersion']=='reference-demo-v1', 'Unexpected model/catalog version')
        names=[f['path'] for f in manifest['files']]
        actual={str(p.relative_to(unpack)) for p in unpack.rglob('*') if p.is_file() and p!=unpack/'manifest.json'}
        require(len(names)==len(set(names)) and set(names)==actual,'Manifest must cover every file exactly once')
        require({'brutforce-api','reference-engine','roman-conformance','catalog-migrate','REVISION','web/index.html','web/release.json','evidence/checks.json'}<=actual, 'Incomplete release')
        for f in manifest['files']:
            p=pathlib.PurePosixPath(f['path'])
            require(not p.is_absolute() and '..' not in p.parts, 'Invalid manifest path')
            require(digest(unpack/p)==f['sha256'], 'Package file checksum mismatch')
        checks=read(unpack/'evidence'/'checks.json')
        require(checks['status']=='passed' and checks['revision']==sha, 'Required CI checks did not pass')
        unpack.rename(target)
    r={'revision':sha,'mode':'reference','synthetic':True,'modelQuality':'not_measured', 'archiveSHA256':checksum,
       'ciURL':f'https://github.com/ai-babai/brutforce/actions/runs/{run_id}', 'manifest':manifest,
       'gates':{'ci':checks,'test':{'status':'pending'},'browser':{'status':'pending'}},'history':[]}
    save(sha,r)

def http_json(base, path, data=None):
    body=None if data is None else json.dumps(data).encode()
    req=urllib.request.Request(base+path, data=body, headers={'Content-Type':'application/json'})
    with urllib.request.urlopen(req, timeout=12) as response: return json.load(response)

def smoke(cfg, sha):
    base=cfg['url']; samples=[]
    for _ in range(20):
        try:
            require(http_json(base,'/v1/health')['ok'], 'Health failed'); break
        except Exception: time.sleep(.5)
    else: raise RuntimeError('Health did not become ready')
    require(http_json(base,'/release.json')['revision']==sha, 'Runtime release differs from candidate')
    for path, body in [('/v1/search',{'query':'Каберне'}),('/v1/recommendations',{'wineId':'demo-cabernet-sauvignon-2023'})]:
        start=time.monotonic(); result=http_json(base,path,body); samples.append(round((time.monotonic()-start)*1000,2))
        require(result['demo'] is True and result['candidates'], 'Synthetic service smoke failed')
        require(result.get('catalogVersion')=='demo-v1', 'Catalog version mismatch')
    return {'status':'passed','at':stamp(),'revision':sha,'requestMs':samples,'note':'Synthetic HTTP smoke, not load/ML quality measurement'}

def switch(envname, sha, action='deploy'):
    cfg=read(CONFIG)['environments'][envname]; target=ROOT/'packages'/sha; r=load(sha)
    require(target.is_dir(), 'Missing package')
    manifest=read(target/'manifest.json')
    require(manifest==r['manifest'], 'Installed manifest changed')
    for f in manifest['files']:
        require(digest(target/f['path'])==f['sha256'],'Installed release changed after CI')
    if envname=='prod':
        require(r['gates']['test']['status']=='passed' and r['gates']['browser']['status']=='passed', 'TEST gates required')
        require(r.get('approval',{}).get('revision')==sha, 'Explicit approval for this release required')
    current=pathlib.Path(cfg['path'])/'current'; previous=str(current.resolve()) if current.is_symlink() else None
    migration_files=lambda folder: {str(p.relative_to(folder/'migrations')):digest(p) for p in (folder/'migrations').rglob('*.sql')}
    if action=='rollback' and previous:
        require(migration_files(pathlib.Path(previous))==migration_files(target), 'Schema differs; operator must establish compatible rollback')
    if envname=='prod': command('sudo','-n','/usr/local/sbin/lct-release-service','backup-prod')
    # DDL uses only the dedicated migration role, never runtime credentials.
    try:
        command(str(target/'catalog-migrate'),cwd=target, env=envfile(cfg['migrationEnv']), stdout=subprocess.DEVNULL)
    except Exception:
        r['gates'][envname]={'status':'failed','at':stamp(),'summary':'Миграция не завершилась; приложение не переключали. Схему проверить отдельно.'}
        save(sha,r); raise
    temp=current.with_name('next'); temp.unlink(missing_ok=True); temp.symlink_to(target); temp.replace(current)
    try:
        command('sudo','-n','/usr/local/sbin/lct-release-service','restart-'+envname)
        result=smoke(cfg,sha)
        if envname=='prod': command('sudo','-n','/usr/local/sbin/lct-release-service','publish-prod')
    except Exception:
        summary='Проверка после выкатки не прошла.'
        try:
            if previous:
                temp.symlink_to(previous); temp.replace(current)
                command('sudo','-n','/usr/local/sbin/lct-release-service','restart-'+envname)
                summary+=' Прежний current возвращён; проверьте доступность.'
            else:
                current.unlink(missing_ok=True)
                command('sudo','-n','/usr/local/sbin/lct-release-service','stop-'+envname)
                summary+=' Первый неудачный выпуск остановлен.'
        except Exception:
            summary+=' Автоматический возврат тоже не завершился; требуется оператор.'
        r['gates'][envname]={'status':'failed','at':stamp(),'summary':summary}
        save(sha,r); raise
    r['gates'][envname]=result
    if envname=='test':
        r['gates']['browser']={'status':'pending'}; r.pop('approval',None)
    r['history'].append({'action':action,'environment':envname,'at':stamp(),'previous':pathlib.Path(previous).name if previous else None})
    save(sha,r)

def main(args):
    arity={'status':1,'install':4,'deploy-test':2,'promote':2,'rollback':3,'browser-result':2,'approve':4}
    require(bool(args) and args[0] in arity and len(args)==arity[args[0]],'Invalid command or argument count')
    require(not ('SSH_ORIGINAL_COMMAND' in os.environ and args[0]=='approve'), 'SSH deploy key cannot approve production')
    ROOT.mkdir(exist_ok=True)
    with (ROOT/'controller.lock').open('w') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX|fcntl.LOCK_NB)
        cmd=args[0]
        if cmd=='status':
            publish(); print((ROOT/'public'/'status.json').read_text()); return
        sha=revision(args[1])
        if cmd=='install': install(sha,args[2],args[3])
        elif cmd=='deploy-test': switch('test',sha)
        elif cmd=='promote': switch('prod',sha)
        elif cmd=='rollback':
            require(args[2] in ('test','prod'),'Invalid environment'); switch(args[2],sha,'rollback')
        elif cmd=='browser-result':
            result=json.loads(sys.stdin.read(1024*1024)); r=load(sha)
            require(result['revision']==sha and result['status'] in ('passed','failed'),'Invalid browser evidence')
            require(pathlib.Path(read(CONFIG)['environments']['test']['path'],'current').resolve().name==sha,'TEST has changed')
            require(r['gates']['test']['status']=='passed','HTTP smoke required')
            require(datetime.datetime.fromisoformat(result['at'].replace('Z','+00:00')) >= datetime.datetime.fromisoformat(r['gates']['test']['at']), 'Browser evidence predates this deployment')
            if result['status']=='passed':
                expected={'release revision','desktop text search, card, recommendations','mobile text search, upload, card, recommendations'}
                require(expected <= {c['name'] for c in result.get('checks',[]) if c['status']=='passed'}, 'Incomplete browser evidence')
                require(result.get('observedRevision')==sha,'Browser observed another release')
            r['gates']['browser']=result; save(sha,r)
        elif cmd=='approve':
            r=load(sha); actor=args[2]; reference=args[3]
            require(actor in ('maks','roman'),'Only named human acceptance')
            require(3<=len(reference)<=500,'Provide Telegram message or explicit request reference')
            require(all(r['gates'][g]['status']=='passed' for g in ('ci','test','browser')),'Required gates incomplete')
            r['approval']={'revision':sha,'actor':actor,'reference':reference,'recordedBy':os.environ.get('SUDO_USER',os.environ.get('USER','unknown')),'at':stamp()}; save(sha,r)
        else: raise RuntimeError('Unknown command')
        print(json.dumps({'ok':True,'command':cmd,'revision':sha}))

if __name__=='__main__':
    try:
        args=shlex.split(os.environ['SSH_ORIGINAL_COMMAND']) if 'SSH_ORIGINAL_COMMAND' in os.environ else sys.argv[1:]
        main(args)
    except Exception as exc:
        # Do not print subprocess arguments/environments, which may contain credentials.
        print('Release command failed: '+(str(exc) if isinstance(exc,RuntimeError) else type(exc).__name__),file=sys.stderr)
        sys.exit(1)
