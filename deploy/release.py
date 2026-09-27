#!/usr/bin/env python3
"""Small native release controller. Installed read-only; runs as lct-release."""
import datetime, fcntl, hashlib, json, os, pathlib, re, shlex, subprocess, sys, tarfile, tempfile, time, urllib.error, urllib.request
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
def sha256(value):
    require(bool(re.fullmatch('[a-f0-9]{64}', value)), 'Expected SHA-256'); return value
def candidate_id(rev, manifest_sha, mode, model):
    return hashlib.sha256(('\0'.join((rev,manifest_sha,mode,model))).encode()).hexdigest()

def record(candidate): return ROOT/'records'/f'{candidate}.json'
def load(candidate):
    direct=record(candidate)
    if direct.exists(): return read(direct)
    matches=[read(p) for p in (ROOT/'records').glob('*.json') if read(p).get('revision')==candidate]
    require(len(matches)==1, 'Candidate is missing or Git SHA is ambiguous; use candidate ID')
    return matches[0]
def save(candidate, r):
    r['updatedAt']=stamp(); write(record(candidate), r); publish()
def publish():
    records = sorted((read(p) for p in (ROOT/'records').glob('*.json')), key=lambda x:x['updatedAt'], reverse=True)
    envs={}
    for name, cfg in read(CONFIG)['environments'].items():
        current=pathlib.Path(cfg['path'])/'current'
        state=ROOT/'environments'/f'{name}.json'
        envs[name] = read(state) if state.exists() else ({'revision':current.resolve().name} if current.is_symlink() else None)
    def public_record(r):
        out={k:v for k,v in r.items() if k not in ('dataReport','manifest')}
        if 'data' in out.get('gates',{}):
            source=r.get('dataReport',{})
            out['gates']['data']={'status':out['gates']['data']['status'],
              'reusedFrom':out['gates']['data'].get('reusedFrom'),'lastReusedAt':out['gates']['data'].get('lastReusedAt'),'report':{
                k:source.get(k) for k in ('kind','status','catalogVersion','manifestSHA256','validatorVersion','startedAt','completedAt','durationMs','counts','cases')
            }}
        return out
    write(ROOT/'public'/'status.json', {'updatedAt':stamp(), 'environments':envs, 'releases':[public_record(r) for r in records[:30]]})
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
        require(manifest.get('mode') in ('reference','real'), 'Unsupported model mode')
        require(isinstance(manifest.get('modelVersion'),str) and manifest['modelVersion'], 'Missing model version')
        names=[f['path'] for f in manifest['files']]
        actual={str(p.relative_to(unpack)) for p in unpack.rglob('*') if p.is_file() and p!=unpack/'manifest.json'}
        require(len(names)==len(set(names)) and set(names)==actual,'Manifest must cover every file exactly once')
        require({'brutforce-api','reference-engine','roman-conformance','catalog-migrate','catalog-import','REVISION','web/index.html','web/release.json','evidence/checks.json'}<=actual, 'Incomplete release')
        for f in manifest['files']:
            p=pathlib.PurePosixPath(f['path'])
            require(not p.is_absolute() and '..' not in p.parts, 'Invalid manifest path')
            require(digest(unpack/p)==f['sha256'], 'Package file checksum mismatch')
        checks=read(unpack/'evidence'/'checks.json')
        require(checks['status']=='passed' and checks['revision']==sha, 'Required CI checks did not pass')
        require(checks.get('bddCoverageStatus', 'passed') == 'passed' and
                checks.get('targetScope', 'all-environments') == 'all-environments',
                'Partial BDD coverage is valid only for Maks demo, not TEST/PROD')
        unpack.rename(target)
    # The embedded demo remains a valid rollback candidate. Real catalog data is
    # registered separately and can bind to this same immutable app package.
    r={'candidateId':sha,'revision':sha,'catalogVersion':manifest.get('catalogVersion','demo-v1'),
       'catalogManifestSHA256':None,'mode':manifest['mode'],'modelVersion':manifest['modelVersion'],
       'synthetic':manifest.get('synthetic',False),'modelQuality':'not_measured', 'archiveSHA256':checksum,
       'ciURL':f'https://github.com/ai-babai/brutforce/actions/runs/{run_id}', 'manifest':manifest,
       'gates':{'ci':checks,'test':{'status':'pending'},'browser':{'status':'pending'}},'history':[]}
    save(sha,r)

def validate_data_report(report):
    require(report.get('schemaVersion')==1 and report.get('kind')=='catalog-data-quality','Unsupported data report')
    manifest_sha=sha256(report.get('manifestSHA256',''))
    validator=sha256(report.get('validatorVersion',''))
    require(report.get('status')=='passed','Data quality report did not pass')
    require(isinstance(report.get('catalogVersion'),str) and report['catalogVersion'],'Missing catalog version')
    cases={c.get('id'):c for c in report.get('cases',[]) if isinstance(c,dict)}
    required={f'DQ{i:03d}' for i in range(1,9)}|{'DQ011'}
    require(required<=cases.keys(),'Required data-quality cases missing')
    require(all(cases[x].get('status')=='passed' for x in required),'Required data-quality case did not pass')
    require(all(report.get(x) for x in ('startedAt','completedAt')) and isinstance(report.get('durationMs'),(int,float)), 'Incomplete report timing')
    return manifest_sha,validator

def validate_catalog_bytes(report):
    cfg=read(CONFIG); version=report['catalogVersion']
    require(bool(re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9._-]{0,127}',version)),'Unsafe catalog version')
    package=pathlib.Path(cfg.get('catalogDataRoot','/srv/lct/data/catalog/releases'))/version
    media_root=pathlib.Path(cfg.get('catalogMediaRoot','/srv/lct/data/catalog/media'))
    manifest_path=package/'manifest.json'; require(manifest_path.is_file(),'Catalog manifest is not installed')
    require(digest(manifest_path)==report['manifestSHA256'],'Catalog manifest bytes differ from report')
    manifest=read(manifest_path); require(manifest.get('schema_version')=='catalog-release-1','Unsupported catalog manifest schema')
    require(manifest.get('catalog_version')==version,'Catalog version differs from manifest')
    for group,root in (('files',package),('media',media_root)):
        require(root.resolve()==root.absolute(),'Catalog root must not be symlinked')
        for entry in manifest.get(group,[]):
            rel=pathlib.PurePosixPath(entry.get('path',''))
            require(not rel.is_absolute() and '..' not in rel.parts,'Unsafe catalog path')
            path=root/rel
            require(path.resolve().is_relative_to(root.resolve()),'Catalog path escapes root')
            require(path.is_file() and not any(p.is_symlink() for p in (path,*path.parents) if p!=root.parent),'Catalog file missing or symlinked')
            require(path.stat().st_size==entry.get('bytes') and digest(path)==entry.get('sha256'),'Catalog installed bytes differ from manifest')
    return package,media_root

def validate_removal_approval(path,candidate,r):
    if not path.exists(): return None
    value=read(path); ids=value.get('ids')
    require(value.get('candidateId')==candidate,'Removal approval belongs to another candidate')
    require(value.get('manifestSHA256')==r['catalogManifestSHA256'],'Removal approval belongs to another manifest')
    require(isinstance(ids,list) and ids and len(ids)==len(set(ids)) and all(isinstance(x,str) and x for x in ids),'Removal approval IDs are invalid')
    require(isinstance(value.get('reason'),str) and value['reason'].strip(),'Removal approval reason is required')
    require(isinstance(value.get('approvalRef'),str) and value['approvalRef'].strip(),'Removal approval reference is required')
    return path

def register_data(sha):
    package=ROOT/'packages'/sha; require(package.is_dir(),'App package must be installed first')
    report=json.loads(sys.stdin.read(8*1024*1024)); manifest_sha,validator=validate_data_report(report)
    package_dir,media_root=validate_catalog_bytes(report)
    require(validator==digest(package/'catalog-import'),'Report validatorVersion differs from installed catalog-import')
    for path in (ROOT/'records').glob('*.json'):
        existing=read(path)
        if existing.get('catalogVersion')==report['catalogVersion'] and existing.get('catalogManifestSHA256') not in (None,manifest_sha):
            raise RuntimeError('Catalog version is already bound to another manifest SHA')
    app=read(package/'manifest.json'); mode=app['mode']; model=app['modelVersion']
    cid=candidate_id(sha,manifest_sha,mode,model); path=record(cid)
    if path.exists():
        old=read(path); require(old['dataReport']['manifestSHA256']==manifest_sha,'Candidate collision')
        if old['dataReport']['validatorVersion']==validator:
            old['gates']['data']['reusedFrom']=old['dataReport']['completedAt']; old['gates']['data']['lastReusedAt']=stamp(); save(cid,old)
            print(json.dumps({'ok':True,'command':'register-data','candidateId':cid,'reused':True})); return
        old['validatorVersion']=validator; old['dataReport']=report; old['gates']['data']={'status':'passed','report':report}
        for gate in ('test','browser','placement'): old['gates'][gate]={'status':'pending'}
        old.pop('approval',None); save(cid,old)
        print(json.dumps({'ok':True,'command':'register-data','candidateId':cid,'reused':False,'validatorChanged':True})); return
    r={'candidateId':cid,'revision':sha,'catalogVersion':report['catalogVersion'],'catalogManifestSHA256':manifest_sha,
       'validatorVersion':validator,'mode':mode,'modelVersion':model,'synthetic':False,'modelQuality':'not_measured',
       'archiveSHA256':load(sha)['archiveSHA256'],'ciURL':load(sha)['ciURL'],'manifest':app,'dataReport':report,
       'catalogPackage':str(package_dir),'catalogMediaRoot':str(media_root),
       'gates':{'ci':load(sha)['gates']['ci'],'data':{'status':'passed','report':report},'test':{'status':'pending'},
       'browser':{'status':'pending'},'placement':{'status':'pending'}},'history':[]}
    save(cid,r); print(json.dumps({'ok':True,'command':'register-data','candidateId':cid,'reused':False}))

def http_json(base, path, data=None):
    body=None if data is None else json.dumps(data).encode()
    req=urllib.request.Request(base+path, data=body, headers={'Content-Type':'application/json'})
    with urllib.request.urlopen(req, timeout=12) as response: return json.load(response)

def smoke(cfg, r):
    base=cfg['url']; samples=[]
    for _ in range(20):
        try:
            require(http_json(base,'/v1/health')['ok'], 'Health failed'); break
        except Exception: time.sleep(.5)
    else: raise RuntimeError('Health did not become ready')
    sha=r['revision']; require(http_json(base,'/release.json')['revision']==sha, 'Runtime release differs from candidate')
    for path, body in [('/v2/catalog?limit=1',None)]:
        start=time.monotonic(); result=http_json(base,path,body); samples.append(round((time.monotonic()-start)*1000,2))
        require(result.get('candidates'), 'Catalog HTTP smoke failed')
        require(result.get('catalogVersion')==r['catalogVersion'], 'Catalog version mismatch')
    return {'status':'passed','at':stamp(),'revision':sha,'candidateId':r.get('candidateId',sha),'requestMs':samples,'note':'HTTP placement smoke; not ML quality measurement'}

def placement(cfg,target,r,candidate,previous_snapshot,allow_removed,accepted_report):
    with tempfile.TemporaryDirectory(dir=ROOT) as tmp:
        report_path=pathlib.Path(tmp)/'db-verify.json'
        args=[str(target/'catalog-import'),'--verify-db','--package',r['catalogPackage'],'--media-root',r['catalogMediaRoot'],
              '--version',r['catalogVersion'],'--report-out',str(report_path),'--validator-version',r['validatorVersion'],
              '--previous-snapshot',str(previous_snapshot),'--accepted-report',str(accepted_report)]
        if allow_removed and allow_removed.exists(): args.extend(('--allow-removed',str(allow_removed)))
        command(*args,env=envfile(cfg['migrationEnv']),stdout=subprocess.DEVNULL)
        db_report=read(report_path)
    db_cases={c.get('id'):c for c in db_report.get('cases',[]) if isinstance(c,dict)}
    require(db_cases.get('DQ009',{}).get('status')=='passed','DQ009 target DB verification failed')
    manifest=read(pathlib.Path(r['catalogPackage'])/'manifest.json'); media=manifest.get('media',[])
    require(media,'DQ010 requires manifest media')
    samples=[]
    for folder in ('400','800','original'):
        samples.append(next((m for m in media if pathlib.PurePosixPath(m['path']).parts[0]==folder),None))
    require(all(samples),'DQ010 requires media in every public role folder')
    public=cfg.get('publicURL',cfg['url']).rstrip('/')
    for sample in samples:
        rel=pathlib.PurePosixPath(sample['path']); req=urllib.request.Request(public+'/media/catalog/'+str(rel))
        with urllib.request.urlopen(req,timeout=20) as response:
            body=response.read(); mime=response.headers.get_content_type(); cache=response.headers.get('Cache-Control','')
        require(hashlib.sha256(body).hexdigest()==sample['sha256'] and mime=='image/webp','DQ010 media bytes or MIME mismatch')
        require('immutable' in cache,'DQ010 immutable cache header missing')
    try: urllib.request.urlopen(public+'/media/catalog/internal/display-policy.json',timeout=12)
    except urllib.error.HTTPError as exc: require(exc.code in (403,404),'DQ010 internal path returned unexpected status')
    else: raise RuntimeError('DQ010 internal path is public')
    return {'status':'passed','at':stamp(),'candidateId':candidate,'environment':cfg.get('name'),
      'cases':[db_cases['DQ009'],{'id':'DQ010','title':'Target HTTP media delivery','section':'Placement','status':'passed',
      'summary':f'All manifest files were checked locally; {len(samples)} role samples passed public bytes/MIME/cache and internal-path denial.'}]}

def switch(envname, candidate, action='deploy'):
    cfg=read(CONFIG)['environments'][envname]; r=load(candidate); candidate=r.get('candidateId',candidate); sha=r['revision']; target=ROOT/'packages'/sha
    require(target.is_dir(), 'Missing package')
    manifest=read(target/'manifest.json')
    require(manifest==r['manifest'], 'Installed manifest changed')
    for f in manifest['files']:
        require(digest(target/f['path'])==f['sha256'],'Installed release changed after CI')
    if r.get('catalogManifestSHA256') is not None:
        validate_data_report(r['dataReport']); validate_catalog_bytes(r['dataReport'])
        require(r['validatorVersion']==digest(target/'catalog-import'),'Installed validator differs from accepted report')
    if envname=='prod':
        require(r['gates']['test']['status']=='passed' and r['gates']['browser']['status']=='passed', 'TEST gates required')
        if r.get('catalogManifestSHA256') is not None:
            require(r['gates'].get('placement',{}).get('status')=='passed','TEST placement gates required')
        require(r.get('approval',{}).get('candidateId')==candidate, 'Explicit approval for this exact candidate required')
    current=pathlib.Path(cfg['path'])/'current'; previous=str(current.resolve()) if current.is_symlink() else None
    state_path=ROOT/'environments'/f'{envname}.json'; previous_state=read(state_path) if state_path.exists() else None
    migration_files=lambda folder: {str(p.relative_to(folder/'migrations')):digest(p) for p in (folder/'migrations').rglob('*.sql')}
    if action=='rollback' and previous:
        require(migration_files(pathlib.Path(previous))==migration_files(target), 'Schema differs; operator must establish compatible rollback')
    if envname=='prod': command('sudo','-n','/usr/local/sbin/lct-release-service','backup-prod')
    auto_code_rollback=not previous or migration_files(pathlib.Path(previous))==migration_files(target)
    snapshot=None
    allow=None
    accepted_report=None
    if r.get('catalogManifestSHA256') is not None:
        backup_root=pathlib.Path(read(CONFIG).get('catalogBackupRoot','/srv/lct/backups/catalog'))/envname
        backup_root.mkdir(parents=True,exist_ok=True)
        first_real=not previous_state or previous_state.get('catalogManifestSHA256') is None
        snapshot=backup_root/('before-real-catalog.json' if first_real else f'{candidate}-{datetime.datetime.now(datetime.timezone.utc).strftime("%Y%m%dT%H%M%SZ")}.json')
        # Export through the importer before any target DB mutation. A schema
        # mismatch stops here for operator attention; it is not an auto-revert.
        export_target=snapshot if not snapshot.exists() else snapshot.with_suffix('.current.tmp')
        export_target.unlink(missing_ok=True)
        command(str(target/'catalog-import'),'--export-snapshot',str(export_target),env=envfile(cfg['migrationEnv']),stdout=subprocess.DEVNULL)
        if export_target!=snapshot:
            require(read(export_target)==read(snapshot),'Preserved initial snapshot differs from current target DB; operator review required')
            export_target.unlink()
        allow=validate_removal_approval(backup_root/'approvals'/f'{candidate}.json',candidate,r)
        accepted_report=ROOT/'evidence'/f'{candidate}.data-quality.json'; write(accepted_report,r['dataReport'])
        preflight=backup_root/f'.{candidate}.preflight.json'
        args=[str(target/'catalog-import'),'--package',r['catalogPackage'],'--media-root',r['catalogMediaRoot'],'--version',r['catalogVersion'],
              '--compare-ids','--accepted-report',str(accepted_report),'--report-out',str(preflight),
              '--validator-version',r['validatorVersion'],'--previous-snapshot',str(snapshot)]
        if allow is not None: args.extend(('--allow-removed',str(allow)))
        command(*args,env=envfile(cfg['migrationEnv']),stdout=subprocess.DEVNULL)
        fresh=read(preflight); preflight.unlink(missing_ok=True)
        fresh_manifest,fresh_validator=validate_data_report(fresh)
        require(fresh_manifest==r['catalogManifestSHA256'] and fresh_validator==r['validatorVersion'],'Fresh target preflight differs from candidate')
    # DDL uses only the dedicated migration role, never runtime credentials.
    try:
        command(str(target/'catalog-migrate'),cwd=target, env=envfile(cfg['migrationEnv']), stdout=subprocess.DEVNULL)
        if r.get('catalogManifestSHA256') is not None:
            command(str(target/'catalog-import'),'--package',r['catalogPackage'],'--media-root',r['catalogMediaRoot'],
                    '--version',r['catalogVersion'],'--snapshot-out',str(snapshot)+'.pre-import',
                    '--accepted-report',str(accepted_report),'--validator-version',r['validatorVersion'],
                    env=envfile(cfg['migrationEnv']),stdout=subprocess.DEVNULL)
    except Exception:
        r['gates'][envname]={'status':'failed','at':stamp(),'summary':'Миграция не завершилась; приложение не переключали. Схему проверить отдельно.'}
        save(candidate,r); raise
    temp=current.with_name('next'); temp.unlink(missing_ok=True); temp.symlink_to(target); temp.replace(current)
    catalog_env=pathlib.Path(cfg.get('catalogEnv',f'/srv/lct/{envname}/catalog.env'))
    previous_catalog_env=catalog_env.read_text() if catalog_env.exists() else None
    catalog_env_tmp=catalog_env.with_suffix('.tmp'); catalog_env_tmp.write_text('CATALOG_VERSION='+r['catalogVersion']+'\n'); catalog_env_tmp.replace(catalog_env)
    try:
        command('sudo','-n','/usr/local/sbin/lct-release-service','restart-'+envname)
        result=smoke(cfg,r)
        placement_result=placement(cfg,target,r,candidate,snapshot,allow,accepted_report) if r.get('catalogManifestSHA256') is not None else None
        if envname=='prod': command('sudo','-n','/usr/local/sbin/lct-release-service','publish-prod')
    except Exception:
        summary='Проверка после выкатки не прошла.'
        try:
            if previous and auto_code_rollback:
                if snapshot is not None:
                    command(str(target/'catalog-import'),'--restore',str(snapshot),env=envfile(cfg['migrationEnv']),stdout=subprocess.DEVNULL)
                temp.symlink_to(previous); temp.replace(current)
                if previous_catalog_env is not None: catalog_env.write_text(previous_catalog_env)
                command('sudo','-n','/usr/local/sbin/lct-release-service','restart-'+envname)
                summary+=' Прежний current возвращён; проверьте доступность.'
                if previous_state is not None: write(state_path,previous_state)
            elif previous:
                summary+=' Схема миграций отличается; автоматический возврат к старому коду небезопасен. Требуется оператор.'
            else:
                current.unlink(missing_ok=True)
                command('sudo','-n','/usr/local/sbin/lct-release-service','stop-'+envname)
                summary+=' Первый неудачный выпуск остановлен.'
        except Exception:
            summary+=' Автоматический возврат тоже не завершился; требуется оператор.'
        r['gates'][envname]={'status':'failed','at':stamp(),'summary':summary}
        save(candidate,r); raise
    r['gates'][envname]=result
    if r.get('catalogManifestSHA256') is not None: r['gates']['placement']=placement_result
    if envname=='test':
        r['gates']['browser']={'status':'pending'}; r.pop('approval',None)
    r['history'].append({'action':action,'environment':envname,'at':stamp(),'previous':pathlib.Path(previous).name if previous else None})
    write(state_path,{'candidateId':candidate,'revision':sha,'catalogVersion':r['catalogVersion'],
                      'catalogManifestSHA256':r.get('catalogManifestSHA256'),'mode':r['mode'],'modelVersion':r['modelVersion'],'at':stamp()})
    save(candidate,r)

def safe_switch(envname,candidate,action='deploy'):
    before=load(candidate); before_gate=json.dumps(before.get('gates',{}).get(envname),sort_keys=True)
    try: return switch(envname,candidate,action)
    except Exception as exc:
        r=load(candidate); cid=r.get('candidateId',candidate)
        if json.dumps(r.get('gates',{}).get(envname),sort_keys=True)==before_gate:
            reason=str(exc) if isinstance(exc,RuntimeError) else type(exc).__name__
            r.setdefault('gates',{})[envname]={'status':'failed','at':stamp(),
              'summary':'Попытка заблокирована до завершения выкатки. Причина: '+reason}
        r.setdefault('history',[]).append({'action':action+'-failed','environment':envname,'at':stamp(),
          'reason':str(exc) if isinstance(exc,RuntimeError) else type(exc).__name__})
        save(cid,r); raise

def main(args):
    arity={'status':1,'install':4,'register-data':2,'deploy-test':2,'promote':2,'rollback':3,'browser-result':2,'approve':4}
    require(bool(args) and args[0] in arity and len(args)==arity[args[0]],'Invalid command or argument count')
    require(not ('SSH_ORIGINAL_COMMAND' in os.environ and args[0]=='approve'), 'SSH deploy key cannot approve production')
    ROOT.mkdir(exist_ok=True)
    with (ROOT/'controller.lock').open('w') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX|fcntl.LOCK_NB)
        cmd=args[0]
        if cmd=='status':
            publish(); print((ROOT/'public'/'status.json').read_text()); return
        token=args[1]; require(bool(re.fullmatch('[a-f0-9]{40}|[a-f0-9]{64}',token)),'Invalid revision or candidate ID')
        if cmd=='install': install(revision(token),args[2],args[3])
        elif cmd=='register-data': register_data(revision(token)); return
        elif cmd=='deploy-test': safe_switch('test',token)
        elif cmd=='promote': safe_switch('prod',token)
        elif cmd=='rollback':
            require(args[2] in ('test','prod'),'Invalid environment'); safe_switch(args[2],token,'rollback')
        elif cmd=='browser-result':
            result=json.loads(sys.stdin.read(1024*1024)); r=load(token); candidate=r.get('candidateId',token); sha=r['revision']
            require(result['revision']==sha and result['status'] in ('passed','failed'),'Invalid browser evidence')
            require(pathlib.Path(read(CONFIG)['environments']['test']['path'],'current').resolve().name==sha,'TEST app has changed')
            state=read(ROOT/'environments'/'test.json')
            require(state.get('candidateId')==candidate and result.get('candidateId')==candidate,'Browser evidence candidate mismatch')
            require(r['gates']['test']['status']=='passed','HTTP smoke required')
            require(datetime.datetime.fromisoformat(result['at'].replace('Z','+00:00')) >= datetime.datetime.fromisoformat(r['gates']['test']['at']), 'Browser evidence predates this deployment')
            if result['status']=='passed':
                expected={'release revision','desktop text search, card, recommendations','mobile demo text search, photo upload, card, recommendations'} if r.get('catalogManifestSHA256') is None else {
                    'release revision','active catalog version and bounded first page',
                    'desktop real catalog, pagination, search, image and source',
                    'mobile real catalog, pagination, search, image and source',
                    'narrow real catalog, pagination, search, image and source',
                    'real photo upload, recognition, card and recommendations'}
                require(expected <= {c['name'] for c in result.get('checks',[]) if c['status']=='passed'}, 'Incomplete browser evidence')
                require(result.get('observedRevision')==sha,'Browser observed another release')
                require(result.get('catalogVersion')==r['catalogVersion'],'Browser observed another catalog version')
            r['gates']['browser']=result; save(candidate,r)
        elif cmd=='approve':
            r=load(token); candidate=r.get('candidateId',token); actor=args[2]; reference=args[3]
            require(actor in ('maks','roman'),'Only named human acceptance')
            require(3<=len(reference)<=500,'Provide Telegram message or explicit request reference')
            required=('ci','test','browser') if r.get('catalogManifestSHA256') is None else ('ci','data','test','browser','placement')
            require(all(r['gates'][g]['status']=='passed' for g in required),'Required gates incomplete')
            r['approval']={'candidateId':candidate,'revision':r['revision'],'catalogManifestSHA256':r.get('catalogManifestSHA256'),'actor':actor,'reference':reference,'recordedBy':os.environ.get('SUDO_USER',os.environ.get('USER','unknown')),'at':stamp()}; save(candidate,r)
        else: raise RuntimeError('Unknown command')
        print(json.dumps({'ok':True,'command':cmd,'candidateId':token}))

if __name__=='__main__':
    try:
        args=shlex.split(os.environ['SSH_ORIGINAL_COMMAND']) if 'SSH_ORIGINAL_COMMAND' in os.environ else sys.argv[1:]
        main(args)
    except Exception as exc:
        # Do not print subprocess arguments/environments, which may contain credentials.
        print('Release command failed: '+(str(exc) if isinstance(exc,RuntimeError) else type(exc).__name__),file=sys.stderr)
        sys.exit(1)
