#!/usr/bin/env python3
"""Small native release controller. Installed read-only; runs as lct-release."""
import datetime, fcntl, hashlib, json, math, os, pathlib, re, shlex, subprocess, sys, tarfile, tempfile, time, urllib.error, urllib.request
ROOT = pathlib.Path('/srv/lct/releases')
CONFIG = pathlib.Path('/etc/lct-release/config.json')
PROD_POLICY = pathlib.Path(__file__).with_name('fast-prod-v1.json')
RECOMMENDATION_PIN = {
    'catalogVersion':'svoe-20260927-alpha-2035-v1',
    'catalogManifestSHA256':'d88c4454a46802490ee2f69e32d2fb28fd8816d23a6d4d554356697632f845ef',
    'sha256':'f05f16c7790782ec3c1b50047bba4e29f1d906217f63846c217d5516e6ef8e7f',
    'indexVersion':'so400m384-owlv2-v2-crops-reference-gated-20260925',
    'modelVersion':'display-text-attributes-winery-review-v2',
}

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
    recommendation_state=ROOT/'environments'/'test-recommendations.json'
    if recommendation_state.exists() and envs.get('test'):
        extra=read(recommendation_state)
        if extra['appCandidateId']==envs['test'].get('candidateId'):
            envs['test']['recommendations']=extra
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
        if manifest['mode']=='real':
            require((unpack/'evidence'/'f8-runtime.json').is_file(), 'Real release lacks pinned F8 runtime assets')
            runtime=read(unpack/'evidence'/'f8-runtime.json')
            require(runtime.get('mode')=='real' and runtime.get('modelVersion')==manifest['modelVersion'] and
                    runtime.get('externalAssets')==manifest.get('externalAssets') and
                    len(runtime['externalAssets'])==6, 'Real release lacks pinned F8 runtime assets')
            require(all(bool(re.fullmatch(r'[a-f0-9]{64}', asset.get('sha256',''))) and
                        pathlib.PurePosixPath(asset.get('path','')).is_absolute()
                        for asset in runtime['externalAssets']), 'Invalid external F8 asset digest or path')
            release=read(unpack/'web'/'release.json')
            require(release.get('revision')==sha and release.get('mode')==manifest['mode'] and
                    release.get('modelVersion')==manifest['modelVersion'], 'Web release metadata differs from package')
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
        if manifest['mode']=='real':
            require(checks.get('mode')=='real' and checks.get('modelVersion')==manifest['modelVersion'],
                    'CI did not attest this real model metadata')
        scope=checks.get('targetScope','all-environments')
        coverage=checks.get('bddCoverageStatus','passed')
        require((scope=='all-environments' and coverage=='passed') or
                (scope=='test-only' and coverage=='partial' and checks.get('coverageExceptions')),
                'Partial BDD coverage is valid only for a named TEST-only policy, not PROD')
        if scope=='test-only':
            policy_file=unpack/'evidence'/'fast-report-exceptions.json'
            gate_file=unpack/'evidence'/'release-gate.json'
            require(policy_file.is_file() and gate_file.is_file(), 'TEST-only coverage policy is missing')
            policy=read(policy_file); gate=read(gate_file)
            require(policy.get('schemaVersion')==1 and policy.get('targetScope')=='test-only' and
                    digest(policy_file)==checks.get('policySHA256')==gate.get('policySHA256') and
                    gate.get('status')=='passed' and gate.get('targetScope')==scope and
                    gate.get('bddCoverageStatus')==coverage and
                    gate.get('coverageExceptions')==checks.get('coverageExceptions'),
                    'TEST-only coverage policy differs from CI evidence')
            named={id for item in policy.get('exceptions',[]) for id in item.get('ids',[])}
            deferred=checks['coverageExceptions']
            require(named=={item.get('id') for item in deferred} and
                    len(named)==len(deferred) and
                    all(item.get('status')=='skipped' and item.get('reason') and item.get('evidence') for item in deferred),
                    'TEST-only coverage has missing or unexpected deferred cases')
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

def http_json(base, path, data=None, timeout=12):
    body=None if data is None else json.dumps(data).encode()
    req=urllib.request.Request(base+path, data=body, headers={'Content-Type':'application/json'})
    with urllib.request.urlopen(req, timeout=timeout) as response: return json.load(response)

def fast_prod_policy(r):
    policy=read(PROD_POLICY)
    require(policy.get('schemaVersion')==1 and policy.get('policyId')=='fast-prod-v1' and
            policy.get('targetScope')=='prod', 'Wrong PROD release policy')
    named=policy.get('deferredCases')
    deferred=r['gates']['ci'].get('coverageExceptions',[])
    require(isinstance(named,dict) and len(named)==26 and len(deferred)==len(named) and
            {item.get('id') for item in deferred}==set(named) and
            all(item.get('status')=='skipped' for item in deferred) and
            all(item.get('class') in ('superseded','deferred','required-live') and item.get('basis')
                for item in named.values()), 'PROD policy does not classify exact skipped cases')
    require(r['gates']['ci'].get('status')=='passed' and
            r['gates']['ci'].get('bddCoverageStatus')=='partial' and
            r['gates']['ci'].get('targetScope')=='test-only', 'CI evidence is incompatible with fast-prod-v1')
    require(r.get('catalogVersion')==RECOMMENDATION_PIN['catalogVersion'] and
            r.get('catalogManifestSHA256')==RECOMMENDATION_PIN['catalogManifestSHA256'],
            'fast-prod-v1 requires the pinned alpha display catalog')
    return digest(PROD_POLICY)

TEST_VISION_ENV=pathlib.Path('/srv/lct/stage/vision-runtime.env')
TEST_PHOTO=pathlib.Path('/srv/lct/data/vision-retrieval/20260924/organizer-audit/queries/real/92.6_07-09-2026_11-04-40.webp')
TEST_PHOTO_SHA='3c1e06bc461fe048e78dd010f8d990b5387895b02126aa02e01ff8d914582dce'
TEST_PHOTO_SLUG='aratti-kaberne-sovinon-2020-krasnoe-suhoe'

def f8_runtime(target):
    manifest=read(target/'manifest.json')
    require(manifest.get('mode')=='real','F8 switch requires real model mode')
    runtime=read(target/'evidence'/'f8-runtime.json')
    require(runtime['modelVersion']==manifest['modelVersion'],'F8 model version differs from package')
    require(runtime['externalAssets']==manifest['externalAssets'],'F8 assets differ from package')
    proof=subprocess.check_output(['sudo','-n','/usr/local/sbin/lct-release-service','verify-test-f8'],text=True)
    observed={path:sha for sha,path in (line.split(maxsplit=1) for line in proof.splitlines())}
    expected={item['path']:item['sha256'] for item in runtime['externalAssets']}
    require(observed==expected,'F8 external asset bytes differ from CI metadata')
    for path in expected:
        p=pathlib.Path(path)
        require(not p.is_symlink() and p.is_file() and p.resolve()==p,'F8 asset path is missing or symlinked')
    require(digest(TEST_PHOTO)==TEST_PHOTO_SHA,'Known-answer TEST photo bytes changed')
    return runtime

def target_config(envname, cfg):
    require(envname in ('test','prod') and cfg.get('path')==('/srv/lct/stage' if envname=='test' else '/srv/lct/prod') and
            cfg.get('url')==('http://127.0.0.1:8103' if envname=='test' else 'http://127.0.0.1:8104') and
            cfg.get('migrationEnv')==f'/etc/lct-release/{envname}-migration.env',
            'Target environment wiring differs from expected TEST/PROD isolation')
    if envname=='prod':
        require(cfg.get('visionRuntimeEnv','/srv/lct/prod/vision-runtime.env')=='/srv/lct/prod/vision-runtime.env' and
                cfg.get('visionURL','http://127.0.0.1:8126')=='http://127.0.0.1:8126' and
                cfg.get('publicURL')=='https://app.dzap.pw' and
                cfg.get('catalogEnv','/srv/lct/prod/catalog.env')=='/srv/lct/prod/catalog.env',
                'PROD vision wiring differs from pinned shared CPU')
        unit=subprocess.check_output(['systemctl','show','brutforce-prod.service','-p','EnvironmentFiles'],text=True)
        require(all(x in unit for x in ('/etc/lct-release/prod-runtime.env',
                                       '/srv/lct/prod/catalog.env','/srv/lct/prod/vision-runtime.env')) and
                pathlib.Path('/srv/lct/data/prod/feedback').is_dir() and
                pathlib.Path('/srv/lct/data/prod/photos').is_dir() and
                all(os.access(path,os.W_OK|os.X_OK) for path in ('/srv/lct/data/prod/feedback',
                                                                  '/srv/lct/data/prod/photos')),
                'PROD unit or private uploads/feedback paths are not ready')
        route=pathlib.Path('/etc/caddy/sites-enabled/lct-previews.caddy').read_text()
        require('root * /srv/lct/prod/public' in route and 'reverse_proxy 127.0.0.1:8104' not in route,
                'First PROD needs the original Caddy placeholder for reversible publish')

def verified_recommendations(state, runtime, r=None):
    require(state.get('appCandidateId') and state.get('catalogVersion') and state.get('sha256'),
            'Recommendation override has no complete TEST receipt')
    wanted=sha256(state['sha256'])
    path=ROOT/'recommendations'/f'{wanted}.json'
    require(state.get('file')==str(path) and path.is_file() and not path.is_symlink() and
            path.stat().st_size<=16*1024*1024 and path.stat().st_mode & 0o222==0 and
            digest(path)==wanted, 'Recommendation asset changed or is not immutable')
    index=read(path)
    require(set(index)=={'catalogVersion','indexVersion','modelVersion','neighbors'} and
            index['catalogVersion']==state['catalogVersion'] and
            index['indexVersion']==runtime['visionIndexVersion'] and
            index['modelVersion']==state['modelVersion'] and
            index['indexVersion']==state['indexVersion'], 'Recommendation mapping metadata is incompatible')
    slugs=next((item for item in runtime['externalAssets'] if item['path'].endswith('/organizer-slugs.json')),None)
    require(slugs is not None, 'Vision slug mapping is missing')
    require(digest(slugs['path'])==slugs['sha256'], 'Vision slug mapping changed')
    allowed=read(slugs['path'])
    require(allowed.get('catalog_version')==runtime['visionCatalogVersion'] and
            isinstance(allowed.get('slugs'),list) and len(set(allowed['slugs']))==len(allowed['slugs']),
            'Vision slug mapping is invalid')
    known=set(allowed['slugs'])
    # Organizer allowlist contains query slugs, not the display-card ID set.
    # Four display IDs are absent from it in the pinned catalog; compare the
    # recommendation graph to display IDs, not to a differently scoped list.
    require(isinstance(index['neighbors'],dict) and TEST_PHOTO_SLUG in known,
            'Recommendation mapping or known answer differs from pinned vision mapping')
    if r is not None:
        catalog=pathlib.Path(r['catalogPackage'])
        display=[json.loads(line) for line in (catalog/'wines.jsonl').read_text().splitlines()]
        ids={wine['id'] for wine in display}
        require(len(ids)==len(display) and all(wine['id']==wine['slug'] for wine in display) and
                set(index['neighbors'])==ids and TEST_PHOTO_SLUG in ids,
                'Recommendation IDs or recognized slug do not map to active display catalog')
        aliases=read(catalog/'aliases.json')['aliases']
        require(all(row['canonical_slug'] in ids for row in aliases), 'Alias points outside active display catalog')
    for source, rows in index['neighbors'].items():
        require(isinstance(rows,list) and len(rows)<=100, 'Invalid recommendation rows')
        seen=set(); last=1.0
        for row in rows:
            require(isinstance(row,dict) and set(row)=={'id','score'} and row['id'] in index['neighbors'] and
                    row['id']!=source and row['id'] not in seen and type(row['score']) in (int,float) and
                    math.isfinite(row['score']) and 0<=row['score']<=last, 'Invalid recommendation neighbor')
            seen.add(row['id']); last=row['score']
    return path,index

def require_recommendation_pin(state, r):
    require(r.get('catalogVersion')==RECOMMENDATION_PIN['catalogVersion'] and
            r.get('catalogManifestSHA256')==RECOMMENDATION_PIN['catalogManifestSHA256'] and
            all(state.get(k)==RECOMMENDATION_PIN[k] for k in ('catalogVersion','sha256','indexVersion','modelVersion')),
            'This real release requires exact cleaned recommendation index and alpha catalog')

def recommendation_receipt(candidate, r, runtime):
    state_path=ROOT/'environments'/'test-recommendations.json'
    require(state_path.is_file(), 'TEST recommendation override is not active')
    state=read(state_path)
    require(state['appCandidateId']==candidate and state['catalogVersion']==r['catalogVersion'],
            'Recommendation override belongs to another candidate or catalog')
    verified_recommendations(state,runtime,r)
    require_recommendation_pin(state,r)
    return state

def f8_health(runtime, base='http://127.0.0.1:8126'):
    for _ in range(90):
        try:
            result=http_json(base,'/healthz')
            require(result.get('status')=='ready' and
                    result.get('model_version')==runtime['modelVersion'] and
                    result.get('catalog_version')==runtime['visionCatalogVersion'] and
                    result.get('index_version')==runtime['visionIndexVersion'] and
                    result.get('serving_profile')=='so400m-onnx640','F8 health metadata differs from candidate')
            return
        except (urllib.error.URLError,TimeoutError): time.sleep(1)
    raise RuntimeError('Pinned F8 did not become ready')

def f8_photo(base,runtime, product=False):
    boundary='brutforce-f8-test-smoke'
    body=(f'--{boundary}\r\nContent-Disposition: form-data; name="image"; filename="control.webp"\r\n'
          'Content-Type: image/webp\r\n\r\n').encode()+TEST_PHOTO.read_bytes()+f'\r\n--{boundary}--\r\n'.encode()
    req=urllib.request.Request(base+'/v1/eval/predict',body,{'Content-Type':f'multipart/form-data; boundary={boundary}'})
    started=time.monotonic()
    with urllib.request.urlopen(req,timeout=9.5) as response: result=json.load(response)
    require(result.get('slug')==TEST_PHOTO_SLUG and result.get('model_version',runtime['modelVersion'])==runtime['modelVersion'],
            'F8 known-answer photo did not match the pinned model')
    require(time.monotonic()-started<10, 'Contest photo smoke exceeded 10 seconds')
    if product:
        started=time.monotonic()
        upload=urllib.request.Request(base+'/v1/photos',body.replace(b'name="image"',b'name="photo"'),
                                   {'Content-Type':f'multipart/form-data; boundary={boundary}'})
        with urllib.request.urlopen(upload,timeout=9.5) as response: receipt=json.load(response)
        remaining=10-(time.monotonic()-started)
        require(remaining>0, 'Product photo smoke exceeded 10 seconds')
        found=http_json(base,'/v1/search',{'photoId':receipt['id']},timeout=remaining)
        require(found.get('demo') is False and found.get('recognizedSlug')==TEST_PHOTO_SLUG and
                found.get('modelVersion')==runtime['modelVersion'],
                'Public API photo result did not come from pinned F8')
        require(time.monotonic()-started<10, 'Product photo smoke exceeded 10 seconds')
        card=http_json(base,'/v2/catalog/'+TEST_PHOTO_SLUG)
        require(card.get('canonicalId')==TEST_PHOTO_SLUG and card.get('candidate',{}).get('slug')==TEST_PHOTO_SLUG,
                'Recognized slug does not open the matching catalog card')

def test_vision_env(runtime, recommendations=None):
    root='/srv/lct/maks/vision-service/releases/cpu-f8-text-rescue-20260927'
    slugs=next(item for item in runtime['externalAssets'] if item['path']==root+'/organizer-slugs.json')
    neighbors=next(item for item in runtime['externalAssets'] if item['path']==root+'/visual-neighbors.json')
    rec_path,rec_sha=(recommendations['file'],recommendations['sha256']) if recommendations else (neighbors['path'],neighbors['sha256'])
    return (f'VISION_SERVICE_URL=http://127.0.0.1:8126\n'
            f'VISION_CATALOG_VERSION={runtime["visionCatalogVersion"]}\n'
            f'VISION_INDEX_VERSION={runtime["visionIndexVersion"]}\n'
            f'VISION_SLUGS_FILE={slugs["path"]}\nVISION_SLUGS_SHA256={slugs["sha256"]}\n'
            f'RECOMMENDATION_INDEX_FILE={rec_path}\nRECOMMENDATION_INDEX_SHA256={rec_sha}\n')

def write_vision_env(text):
    temp=TEST_VISION_ENV.with_suffix('.tmp')
    temp.write_text(text); temp.chmod(0o600); temp.replace(TEST_VISION_ENV)

def switch_test_recommendations(wanted):
    """TEST-only data switch. F8, catalog, code, and their release gates stay pinned."""
    require(wanted==RECOMMENDATION_PIN['sha256'],
            'Only the pinned cleaned recommendation index may be switched in TEST')
    state=read(ROOT/'environments'/'test.json')
    require(state.get('mode')=='real' and state.get('catalogVersion'), 'Real TEST catalog required')
    release=load(state['candidateId'])
    require(state['catalogVersion']==RECOMMENDATION_PIN['catalogVersion'] and
            state.get('catalogManifestSHA256')==RECOMMENDATION_PIN['catalogManifestSHA256'] and
            release['catalogManifestSHA256']==RECOMMENDATION_PIN['catalogManifestSHA256'],
            'TEST catalog does not match pinned cleaned recommendation index')
    require(release['gates']['test']['status']=='passed', 'Current TEST release has not passed smoke')
    cfg=read(CONFIG)['environments']['test']; base=cfg['url']
    require(http_json(base,'/release.json')['revision']==state['revision'], 'TEST app has changed')
    path=ROOT/'recommendations'/f'{wanted}.json'
    require(path.is_file() and not path.is_symlink() and path.stat().st_size <= 16*1024*1024 and
            path.stat().st_mode & 0o222 == 0,
            'Recommendation asset is absent, linked, writable, or too large')
    require(digest(path)==wanted, 'Recommendation asset checksum mismatch')
    index=read(path)
    visual=pathlib.Path('/srv/lct/maks/vision-service/releases/cpu-f8-text-rescue-20260927/visual-neighbors.json')
    old_visual=read(visual)
    require(set(index)=={'catalogVersion','indexVersion','modelVersion','neighbors'} and
            index['catalogVersion']==state['catalogVersion'] and
            index['indexVersion']==RECOMMENDATION_PIN['indexVersion'] and
            index['modelVersion']==RECOMMENDATION_PIN['modelVersion'] and
            all(isinstance(index[k],str) and 0<len(index[k])<=128 for k in ('indexVersion','modelVersion')),
            'Recommendation metadata differs from current TEST catalog')
    require(index['indexVersion']==old_visual['indexVersion'],
            'Recommendation compatibility token differs from pinned F8 index')
    known=set(old_visual['neighbors'])
    require(isinstance(index['neighbors'],dict) and set(index['neighbors'])==known,
            'Recommendations do not cover the exact active catalog IDs')
    for source, rows in index['neighbors'].items():
        require(isinstance(rows,list) and len(rows)<=100, 'Invalid recommendation list')
        seen=set(); last=1.0
        for row in rows:
            require(isinstance(row,dict) and set(row)=={'id','score'} and row['id'] in known and
                    row['id']!=source and row['id'] not in seen and type(row['score']) in (int,float) and
                    math.isfinite(row['score']) and 0<=row['score']<=last,
                    'Invalid recommendation neighbor')
            seen.add(row['id']); last=row['score']
    before=TEST_VISION_ENV.read_text()
    require(before.count('RECOMMENDATION_INDEX_FILE=')==1 and before.count('RECOMMENDATION_INDEX_SHA256=')==1,
            'Existing recommendation configuration is ambiguous')
    previous={line.split('=',1)[0]:line.split('=',1)[1] for line in before.splitlines()
              if line.startswith(('RECOMMENDATION_INDEX_FILE=','RECOMMENDATION_INDEX_SHA256='))}
    require(previous['RECOMMENDATION_INDEX_SHA256']==digest(previous['RECOMMENDATION_INDEX_FILE']),
            'Existing recommendation asset changed; do not switch')
    updated='\n'.join('RECOMMENDATION_INDEX_FILE='+str(path) if line.startswith('RECOMMENDATION_INDEX_FILE=')
                      else 'RECOMMENDATION_INDEX_SHA256='+wanted if line.startswith('RECOMMENDATION_INDEX_SHA256=')
                      else line for line in before.splitlines())+'\n'
    probe='a-gordienko-m-nikolaev-sira-nuvo-krasnoe-suhoe-115'
    expected=index['neighbors'][probe][0]['id']
    try:
        write_vision_env(updated)
        command('sudo','-n','/usr/local/sbin/lct-release-service','restart-test')
        for _ in range(20):
            try:
                if http_json(base,'/v1/health').get('ok'): break
            except Exception: pass
            time.sleep(.5)
        else: raise RuntimeError('TEST API did not become ready')
        catalog=http_json(base,'/v2/catalog?limit=1')
        require(catalog.get('catalogVersion')==state['catalogVersion'] and catalog.get('candidates'),
                'Active TEST catalog changed during recommendation switch')
        result=http_json(base,'/v1/recommendations',{'wineId':probe,'limit':1})
        require(result.get('catalogVersion')==state['catalogVersion'] and
                result.get('modelVersion')==index['modelVersion'] and
                [x['id'] for x in result.get('candidates',[])]==[expected],
                'New recommendation index failed live smoke')
        require(http_json(base,'/v1/health').get('demo') is False and
                http_json(base,'/release.json')['revision']==state['revision'],
                'App health or revision changed during recommendation switch')
    except Exception:
        write_vision_env(before)
        command('sudo','-n','/usr/local/sbin/lct-release-service','restart-test')
        raise
    write(ROOT/'environments'/'test-recommendations.json', {
        'appCandidateId':state['candidateId'],'catalogVersion':state['catalogVersion'],
        'file':str(path),'sha256':wanted,'modelVersion':index['modelVersion'],
        'indexVersion':index['indexVersion'],'previousFile':previous['RECOMMENDATION_INDEX_FILE'],
        'previousSHA256':previous['RECOMMENDATION_INDEX_SHA256'],'at':stamp()})
    publish()

def smoke(cfg, r, envname='test'):
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
    if r['mode']=='real':
        runtime=read(ROOT/'packages'/sha/'evidence'/'f8-runtime.json')
        require(http_json(base,'/v1/health').get('demo') is False,'Real catalog is not active')
        found=http_json(base,'/v1/search',{'query':'Каберне'})
        require(found.get('demo') is False and found.get('candidates'),'Real text search failed')
        wine=found['candidates'][0]
        alternatives=http_json(base,'/v1/recommendations',{'wineId':wine['id'],'limit':3})
        require(alternatives.get('demo') is False and alternatives.get('candidates'),'Real recommendations failed')
        if envname=='prod':
            rec=read(ROOT/'environments'/'prod-recommendations.json')
            require(alternatives.get('modelVersion')==rec['modelVersion'] and
                    alternatives.get('catalogVersion')==r['catalogVersion'], 'PROD recommendation version differs from approval')
        f8_health(runtime,cfg.get('visionURL','http://127.0.0.1:8126'))
        f8_photo(base,runtime,product=True)
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
    target_config(envname,cfg)
    require(target.is_dir(), 'Missing package')
    manifest=read(target/'manifest.json')
    require(manifest==r['manifest'], 'Installed manifest changed')
    for f in manifest['files']:
        require(digest(target/f['path'])==f['sha256'],'Installed release changed after CI')
    if r.get('catalogManifestSHA256') is not None:
        validate_data_report(r['dataReport']); validate_catalog_bytes(r['dataReport'])
        require(r['validatorVersion']==digest(target/'catalog-import'),'Installed validator differs from accepted report')
    if envname=='prod':
        require(r.get('mode')=='real', 'PROD must use pinned real CPU')
        policy_sha=fast_prod_policy(r)
        require(r['gates']['test']['status']=='passed', 'TEST HTTP smoke required')
        require(r['gates'].get('browser',{}).get('status') in ('pending','passed'),
                'Failed browser evidence cannot be waived')
        if r.get('catalogManifestSHA256') is not None:
            require(r['gates'].get('placement',{}).get('status')=='passed','TEST placement gates required')
        approval=r.get('approval',{})
        require(approval.get('candidateId')==candidate and approval.get('policySHA256')==policy_sha and
                approval.get('catalogManifestSHA256')==r.get('catalogManifestSHA256') and
                approval.get('revision')==sha and approval.get('archiveSHA256')==r.get('archiveSHA256'),
                'Explicit fast-prod-v1 approval for this exact bundle required')
    runtime=None
    vision_started=False
    previous_vision_env=None
    vision_env=pathlib.Path(cfg.get('visionRuntimeEnv',f'/srv/lct/{"stage" if envname=="test" else "prod"}/vision-runtime.env'))
    previous_vision_env=vision_env.read_text() if vision_env.exists() else None
    if r.get('mode')=='real': runtime=f8_runtime(target)
    recommendations=None
    if envname=='test' and runtime:
        state_path_rec=ROOT/'environments'/'test-recommendations.json'
        require(state_path_rec.exists(), 'Cleaned TEST recommendation receipt is required; no visual fallback')
        recommendations=read(state_path_rec)
        require(recommendations['catalogVersion']==r['catalogVersion'] and
                recommendations['appCandidateId']==read(ROOT/'environments'/'test.json')['candidateId'],
                'TEST recommendation override incompatible with new candidate')
        require_recommendation_pin(recommendations,r)
        verified_recommendations(recommendations,runtime,r)
    if envname=='prod':
        require(pathlib.Path(read(CONFIG)['environments']['test']['path'],'current').resolve()==target.resolve() and
                read(ROOT/'environments'/'test.json')['candidateId']==candidate,
                'Approved candidate is not the current TEST release')
        recommendations=recommendation_receipt(candidate,r,runtime)
        require(approval.get('recommendationSHA256')==recommendations['sha256'] and
                approval.get('modelVersion')==r['modelVersion'], 'Recommendation asset differs from approved bundle')
        require(previous_vision_env is None, 'First PROD has an unexpected existing vision env')
        f8_health(runtime,cfg.get('visionURL','http://127.0.0.1:8126'))
        f8_photo(cfg.get('visionURL','http://127.0.0.1:8126'),runtime)
    else:
        prod=ROOT/'environments'/'prod.json'
        require(not prod.exists() or read(prod).get('mode')!='real',
                'Pinned shared PROD F8 forbids TEST deployments that can stop or change it')
    current=pathlib.Path(cfg['path'])/'current'; previous=str(current.resolve()) if current.is_symlink() else None
    if envname=='prod': require(previous is None, 'fast-prod-v1 supports first PROD rollout only')
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
    if runtime and envname=='test':
        command('sudo','-n','/usr/local/sbin/lct-release-service','start-test-f8')
        vision_started=True
        try:
            f8_health(runtime)
            f8_photo('http://127.0.0.1:8126',runtime)
        except Exception:
            command('sudo','-n','/usr/local/sbin/lct-release-service','stop-test-f8')
            raise
    # DDL uses only the dedicated migration role, never runtime credentials.
    try:
        command(str(target/'catalog-migrate'),cwd=target, env=envfile(cfg['migrationEnv']), stdout=subprocess.DEVNULL)
        if r.get('catalogManifestSHA256') is not None:
            command(str(target/'catalog-import'),'--package',r['catalogPackage'],'--media-root',r['catalogMediaRoot'],
                    '--version',r['catalogVersion'],'--snapshot-out',str(snapshot)+'.pre-import',
                    '--accepted-report',str(accepted_report),'--validator-version',r['validatorVersion'],
                    env=envfile(cfg['migrationEnv']),stdout=subprocess.DEVNULL)
    except Exception:
        if vision_started: command('sudo','-n','/usr/local/sbin/lct-release-service','stop-test-f8')
        r['gates'][envname]={'status':'failed','at':stamp(),'summary':'Миграция не завершилась; приложение не переключали. Схему проверить отдельно.'}
        save(candidate,r); raise
    catalog_env=pathlib.Path(cfg.get('catalogEnv',f'/srv/lct/{"stage" if envname=="test" else "prod"}/catalog.env'))
    previous_catalog_env=catalog_env.read_text() if catalog_env.exists() else None
    prod_rec=ROOT/'environments'/'prod-recommendations.json'
    old_prod_rec=prod_rec.read_text() if prod_rec.exists() else None
    try:
        temp=current.with_name('next'); temp.unlink(missing_ok=True); temp.symlink_to(target); temp.replace(current)
        catalog_env_tmp=catalog_env.with_suffix('.tmp'); catalog_env_tmp.write_text('CATALOG_VERSION='+r['catalogVersion']+'\n'); catalog_env_tmp.replace(catalog_env)
        if runtime:
            text=test_vision_env(runtime,recommendations)
            temp_env=vision_env.with_suffix('.tmp'); temp_env.write_text(text); temp_env.chmod(0o600); temp_env.replace(vision_env)
            if envname=='prod': write(prod_rec, recommendations)
        elif envname=='test' and action=='rollback':
            restored=previous_state.get('previousVisionEnv') if previous_state else None
            if restored is None: vision_env.unlink(missing_ok=True)
            else: write_vision_env(restored)
        command('sudo','-n','/usr/local/sbin/lct-release-service','restart-'+envname)
        result=smoke(cfg,r,envname)
        if envname=='prod':
            command('sudo','-n','/usr/local/sbin/lct-release-service','publish-prod')
            smoke({**cfg,'url':cfg['publicURL']},r,envname)
        placement_result=placement(cfg,target,r,candidate,snapshot,allow,accepted_report) if r.get('catalogManifestSHA256') is not None else None
    except Exception:
        summary='Проверка после выкатки не прошла.'
        try:
            if envname=='prod':
                command('sudo','-n','/usr/local/sbin/lct-release-service','unpublish-prod')
            if previous and auto_code_rollback:
                if snapshot is not None:
                    command(str(target/'catalog-import'),'--restore',str(snapshot),env=envfile(cfg['migrationEnv']),stdout=subprocess.DEVNULL)
                temp.symlink_to(previous); temp.replace(current)
                if previous_catalog_env is not None: catalog_env.write_text(previous_catalog_env)
                if previous_vision_env is None: vision_env.unlink(missing_ok=True)
                else:
                    tmp_env=vision_env.with_suffix('.tmp'); tmp_env.write_text(previous_vision_env); tmp_env.chmod(0o600); tmp_env.replace(vision_env)
                if envname=='prod':
                    if old_prod_rec is None: prod_rec.unlink(missing_ok=True)
                    else: prod_rec.write_text(old_prod_rec)
                command('sudo','-n','/usr/local/sbin/lct-release-service','restart-'+envname)
                summary+=' Прежний current возвращён; проверьте доступность.'
                if previous_state is not None: write(state_path,previous_state)
            elif previous:
                summary+=' Схема миграций отличается; автоматический возврат к старому коду небезопасен. Требуется оператор.'
            else:
                current.unlink(missing_ok=True)
                if previous_vision_env is None: vision_env.unlink(missing_ok=True)
                if envname=='prod': prod_rec.unlink(missing_ok=True)
                command('sudo','-n','/usr/local/sbin/lct-release-service','stop-'+envname)
                summary+=' Первый неудачный выпуск остановлен.'
            if vision_started and (not previous or auto_code_rollback):
                command('sudo','-n','/usr/local/sbin/lct-release-service','stop-test-f8')
        except Exception:
            summary+=' Автоматический возврат тоже не завершился; требуется оператор.'
        r['gates'][envname]={'status':'failed','at':stamp(),'summary':summary}
        save(candidate,r); raise
    r['gates'][envname]=result
    if r.get('catalogManifestSHA256') is not None: r['gates']['placement']=placement_result
    if envname=='test':
        r['gates']['browser']={'status':'pending'}; r.pop('approval',None)
        if action=='rollback' and r['mode']!='real' and previous_state and previous_state.get('mode')=='real':
            command('sudo','-n','/usr/local/sbin/lct-release-service','stop-test-f8')
    r['history'].append({'action':action,'environment':envname,'at':stamp(),'previous':pathlib.Path(previous).name if previous else None})
    write(state_path,{'candidateId':candidate,'revision':sha,'catalogVersion':r['catalogVersion'],
                      'catalogManifestSHA256':r.get('catalogManifestSHA256'),'mode':r['mode'],'modelVersion':r['modelVersion'],
                      **({'policySHA256':approval['policySHA256'],'recommendationSHA256':recommendations['sha256']}
                         if envname=='prod' else {}),
                      **({'previousVisionEnv':previous_vision_env} if runtime else {}),'at':stamp()})
    if envname=='test' and recommendations:
        recommendations['appCandidateId']=candidate
        recommendations['at']=stamp()
        write(ROOT/'environments'/'test-recommendations.json',recommendations)
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
    arity={'status':1,'install':4,'register-data':2,'deploy-test':2,'promote':2,'rollback':3,'browser-result':2,'approve':4,'recommendations-test':2}
    require(bool(args) and args[0] in arity and len(args)==arity[args[0]],'Invalid command or argument count')
    require(not ('SSH_ORIGINAL_COMMAND' in os.environ and args[0]=='approve'), 'SSH deploy key cannot approve production')
    ROOT.mkdir(exist_ok=True)
    with (ROOT/'controller.lock').open('w') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX|fcntl.LOCK_NB)
        cmd=args[0]
        if cmd=='status':
            publish(); print((ROOT/'public'/'status.json').read_text()); return
        token=args[1]; require(bool(re.fullmatch('[a-f0-9]{40}|[a-f0-9]{64}',token)),'Invalid revision or candidate ID')
        if cmd=='recommendations-test': switch_test_recommendations(sha256(token))
        elif cmd=='install': install(revision(token),args[2],args[3])
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
            require(3<=len(reference)<=500,'Provide BB thread message or explicit request reference')
            required=('ci','data','test','placement') if r.get('mode')=='real' else ('ci','test','browser')
            require(all(r['gates'][g]['status']=='passed' for g in required),'Required gates incomplete')
            extra={}
            if r.get('mode')=='real':
                policy_sha=fast_prod_policy(r)
                runtime=f8_runtime(ROOT/'packages'/r['revision'])
                test=read(ROOT/'environments'/'test.json')
                require(test.get('candidateId')==candidate, 'Approval candidate is not deployed in TEST')
                rec=recommendation_receipt(candidate,r,runtime)
                extra={'policyId':'fast-prod-v1','policySHA256':policy_sha,
                       'recommendationSHA256':rec['sha256'],'modelVersion':r['modelVersion'],
                       'archiveSHA256':r['archiveSHA256']}
            r['approval']={'candidateId':candidate,'revision':r['revision'],
                           'catalogManifestSHA256':r.get('catalogManifestSHA256'),
                           'actor':actor,'reference':reference,
                           'recordedBy':os.environ.get('SUDO_USER',os.environ.get('USER','unknown')),
                           'at':stamp(),**extra}; save(candidate,r)
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
