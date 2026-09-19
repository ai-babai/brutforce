#!/usr/bin/env node
// Runs the real Go and Vitest suites, preserves their machine output, then
// creates one immutable normalized snapshot for the static report.
import { createHash, randomUUID } from 'node:crypto';
import { spawn } from 'node:child_process';
import { mkdir, readFile, writeFile, access } from 'node:fs/promises';
import { resolve, basename } from 'node:path';

const root=resolve(import.meta.dirname,'..');
const now=new Date();
const stamp=now.toISOString().replace(/[-:]/g,'').replace(/\.\d{3}Z$/,'Z');
const id=`${stamp}-fast-${randomUUID().slice(0,8)}`;
const label=process.env.RUN_LABEL||'Быстрые проверки API и состояний UI';
const runsDir=resolve(root,'reports/site/data/runs');
await mkdir(runsDir,{recursive:true});
const webFile=resolve(runsDir,`${id}.web-vitest.json`);
const goFile=resolve(runsDir,`${id}.api-go.jsonl`);
const catalog=JSON.parse(await readFile(resolve(root,'cases/cases.json'),'utf8')).cases;
const sourceDir=resolve(runsDir,`${id}.sources`);await mkdir(sourceDir);
const sourceFiles=['cases/cases.json','docs/product/behavior-spec.md','apps/api/main.go','apps/api/main_test.go','apps/web/src/App.tsx','apps/web/src/api.ts','apps/web/src/types.ts','apps/web/src/styles.css','apps/web/src/App.test.tsx'];
for(const source of sourceFiles)await writeFile(resolve(sourceDir,basename(source)),await readFile(resolve(root,source)));
const gwt={
 'API-001':['сценарий exact','POST /api/search','выбран первый synthetic candidate'], 'API-002':['сценарий uncertain','POST /api/search','есть кандидаты, selectedId отсутствует'], 'API-003':['сценарий none','POST /api/search','candidates равен []'], 'API-004':['сценарий error','POST /api/search','HTTP 503 содержит structured error'], 'API-005':['текст названия или винодельни','POST /api/search','поиск без учёта регистра'], 'API-006':['некорректный JSON или scenario','POST /api/search','HTTP 400 JSON error'], 'API-007':['неверный method или API path','запрос к API','JSON HTTP 405 либо 404'], 'API-008':['сервер доступен','GET /api/health','ok и demo равны true'], 'API-009':['задан WEB_ROOT','GET file или client route','файл либо index.html отданы'],
 'UI-001':['стартовый экран','пользователь начинает путь','есть вход в сканирование'], 'UI-002':['пользователь выбрал сканирование','переход UI','есть камера/выбор файла'], 'UI-003':['камера запрещена','пользователь начинает путь','доступны fallback действия'], 'UI-004':['поиск не завершился','пользователь отменяет','видно отменённое состояние'], 'UI-005':['поиск отменён','пользователь повторяет','сценарий и query сохранены'], 'UI-006':['API вернул кандидатов','пользователь исправляет ответ','можно выбрать другой результат'], 'UI-007':['mocked API вернул exact shape','React применяет ответ','видны synthetic details'], 'UI-008':['пользователь ищет вручную','отправлен scenario none','доступен экран no-match'], 'UI-009':['API вернул пустых кандидатов','React применяет ответ','доступно восстановление'], 'UI-010':['selectedId отсутствует в candidates','React валидирует ответ','видна recoverable error']
};

function exec(command,args,cwd){return new Promise(resolveRun=>{const child=spawn(command,args,{cwd,stdio:['ignore','pipe','pipe']});let out='',err='';child.stdout.on('data',b=>out+=b);child.stderr.on('data',b=>err+=b);child.on('error',e=>resolveRun({code:null,out,err:String(e)}));child.on('close',code=>resolveRun({code,out,err}));});}
function ids(text,prefix){const found=new Set();for(const m of text.matchAll(new RegExp(`${prefix}[- ]?(\\d{3})`,'g')))found.add(`${prefix}-${m[1]}`);return found;}
const severity={passed:1,skipped:2,failed:3,error:4};
function saveWorst(map,id,value){const previous=map.get(id);if(!previous||severity[value.status]>=severity[previous.status])map.set(id,value);}
function goCases(output,exitCode){const byId=new Map();for(const line of output.split('\n')){try{const e=JSON.parse(line);if(!e.Test)continue;const m=e.Test.match(/^Test(API)(\d{3})/);const id=m?`${m[1]}-${m[2]}`:e.Test==='TestSPAHandlerServesFilesAndFallsBackToIndex'?'API-009':null;if(!id||!['pass','fail'].includes(e.Action))continue;saveWorst(byId,id,{status:e.Action==='pass'?'passed':'failed',durationMs:e.Elapsed==null?undefined:Math.round(e.Elapsed*1000),reason:`Go-проверка ${e.Test}: ${e.Action==='pass'?'пройдена':'не пройдена'}`});}catch{}}return byId;}
function webCases(report,exitCode){const byId=new Map();const tests=report?.testResults?.flatMap(r=>r.assertionResults||[])||[];for(const test of tests){const state=test.status==='passed'?'passed':test.status==='pending'?'skipped':'failed';const evidence=`${test.fullName||''} ${test.title||''}`;const found=ids(evidence,'UI');for(const id of found)saveWorst(byId,id,{status:state,durationMs:test.duration==null?undefined:Math.round(test.duration),reason:`Vitest-проверка: ${state==='passed'?'пройдена':state==='skipped'?'пропущена':'не пройдена'} (${test.fullName||test.title})`,output:test.failureMessages?.join('\n')});if(evidence.includes('UI-004 can cancel and retry'))saveWorst(byId,'UI-005',{status:state,durationMs:test.duration==null?undefined:Math.round(test.duration),reason:`Vitest-проверка: ${state==='passed'?'пройдена':'не пройдена'}; утверждение проверяет состояние UI-005.`,output:test.failureMessages?.join('\n')});}if(!tests.length&&exitCode!==0)byId.set('UI-RUNNER',{status:'error',reason:'Vitest не создал читаемый JSON-отчёт.'});return byId;}

const goBin=process.env.GO_BIN||'go';
const go=await exec(goBin,['test','-count=1','-json','./...'],resolve(root,'apps/api'));
await writeFile(goFile,go.out+(go.err?`\n[stderr]\n${go.err}`:''));
const web=await exec('npm',['--prefix','apps/web','test','--','--reporter=json',`--outputFile=${webFile}`],root);
let webReport;try{webReport=JSON.parse(await readFile(webFile,'utf8'));}catch{webReport=null;await writeFile(webFile,JSON.stringify({runner:'vitest',parseError:true,stdout:web.out,stderr:web.err},null,2)+'\n');}

const found=new Map([...goCases(go.out,go.code),...webCases(webReport,web.code)]);
const cases=catalog.map(c=>{const [given,when,then]=gwt[c.id]||[];const v=found.get(c.id);if(v)return {...c,given,when,then,...v};const runner=c.area==='api'?'Go':'Vitest';const crashed=c.area==='api'?go.code!==0:web.code!==0;return {...c,given,when,then,status:crashed?'error':'skipped',reason:crashed?`${runner} suite ended with code ${c.area==='api'?go.code:web.code}; this case has no individual result.`:`No dedicated ${runner} assertion currently reports this case.`};});
const status=go.code!==0||web.code!==0||cases.some(c=>c.status==='failed'||c.status==='error')?'failed':cases.some(c=>c.status==='skipped')?'partial':'passed';
const sources=sourceFiles.map(source=>`data/runs/${basename(sourceDir)}/${basename(source)}`);
const run={schemaVersion:1,id,label,createdAt:now.toISOString(),elapsedMs:Date.now()-now.getTime(),revision:process.env.GIT_REVISION||'working-tree',status,command:`${goBin} test -count=1 -json ./...; npm --prefix apps/web test -- --reporter=json`,caveat:'Синтетический контракт demo и проверки состояний UI. Это не benchmark OCR, визуального поиска или конкурсного качества.',cases,artifacts:[`data/runs/${basename(goFile)}`,`data/runs/${basename(webFile)}`],sources};
const runFile=resolve(runsDir,`${id}.json`);try{await access(runFile);throw new Error(`Refusing to overwrite ${runFile}`)}catch(e){if(e.code!=='ENOENT')throw e;}await writeFile(runFile,JSON.stringify(run,null,2)+'\n');
const digest=async file=>createHash('sha256').update(await readFile(file)).digest('hex');
const manifestFiles=[runFile,goFile,webFile,...sourceFiles.map(source=>resolve(sourceDir,basename(source)))];
const manifest={schemaVersion:1,runId:id,recordedAt:new Date().toISOString(),files:await Promise.all(manifestFiles.map(async file=>({path:file.startsWith(sourceDir)?`data/runs/${basename(sourceDir)}/${basename(file)}`:`data/runs/${basename(file)}`,sha256:await digest(file)})))};
await writeFile(resolve(runsDir,`${id}.manifest.json`),JSON.stringify(manifest,null,2)+'\n');
const indexPath=resolve(root,'reports/site/data/index.json');const index=JSON.parse(await readFile(indexPath,'utf8'));index.generatedAt=new Date().toISOString();index.runs.push(`runs/${basename(runFile)}`);await writeFile(indexPath,JSON.stringify(index,null,2)+'\n');
console.log(JSON.stringify({run:id,status,goExit:go.code,webExit:web.code,report:`reports/site/data/runs/${basename(runFile)}`},null,2));
process.exitCode=status==='failed'?1:0;
