#!/usr/bin/env node
// Runs the real Go and Vitest suites, preserves their machine output, then
// creates one immutable normalized snapshot for the static report.
import { createHash, randomUUID } from 'node:crypto';
import { spawn } from 'node:child_process';
import { performance } from 'node:perf_hooks';
import { mkdir, readFile, writeFile, access } from 'node:fs/promises';
import { resolve, basename, isAbsolute } from 'node:path';

const root=resolve(import.meta.dirname,'..');
const now=new Date();
const runStarted=performance.now();
const stamp=now.toISOString().replace(/[-:]/g,'').replace(/\.\d{3}Z$/,'Z');
const id=`${stamp}-fast-${randomUUID().slice(0,8)}`;
const label=process.env.RUN_LABEL||'Быстрые проверки API и состояний UI';
const runsDir=resolve(root,'reports/site/data/runs');
await mkdir(runsDir,{recursive:true});
const webFile=resolve(runsDir,`${id}.web-vitest.json`);
const goFile=resolve(runsDir,`${id}.api-go.jsonl`);
const evalFile=resolve(runsDir,`${id}.eval-go.jsonl`);
const dbFile=resolve(runsDir,`${id}.db-go.jsonl`);
const dbMetadataFile=resolve(runsDir,`${id}.db-metadata.json`);
const revision=process.env.GIT_REVISION||'working-tree';
const catalog=JSON.parse(await readFile(resolve(root,'cases/cases.json'),'utf8')).cases;
const sourceDir=resolve(runsDir,`${id}.sources`);await mkdir(sourceDir);
const snapshotName=source=>source.startsWith('apps/api/cmd/roman-conformance/')?'roman-conformance-'+basename(source):source.startsWith('apps/api/cmd/reference-engine/')?'reference-engine-'+basename(source):source==='reports/site/index.html'?'report-index.html':source==='apps/api/cmd/catalog-migrate/main.go'?'catalog-migrate-main.go':basename(source);
const sourceFiles=['apps/api/model_services_regression_test.go','apps/api/model_services.go','apps/api/model_services_test.go','apps/api/internal/referenceengine/referenceengine.go','apps/api/internal/referenceengine/decode.go','apps/api/internal/referenceengine/decode_test.go','apps/api/cmd/roman-conformance/main.go','apps/api/cmd/roman-conformance/main_test.go','apps/api/cmd/reference-engine/main.go','contracts/wine-services.md','contracts/wine-services.openapi.json','docs/agent-guide/ROMAN-SERVICES.md','apps/web/src/recommendations.test.tsx','apps/web/vite.config.ts','apps/web/src/proxy.test.ts','apps/web/assets-v2-provenance.md','apps/web/public/assets/v2/PlayfairDisplay-VariableFont_wght.woff2','apps/api/go.mod','apps/api/go.sum','scripts/run-fast-checks.mjs','reports/README.md','reports/site/index.html','apps/web/src/report.test.ts','contracts/eval-predict.md','contracts/database.md','apps/api/eval_predict.go','apps/api/eval_predict_test.go','cases/cases.json','docs/product/behavior-spec.md','docs/product/security-spec.md','contracts/demo-catalog.md','contracts/demo-search.schema.json','contracts/api-versioning.md','apps/api/main.go','apps/api/docs.go','apps/api/security.go','apps/api/uploads.go','apps/api/catalog_store.go','apps/api/catalog_store_test.go','apps/api/internal/catalogdb/migrate.go','apps/api/migrations/seeds/demo_catalog.sql','apps/api/migrations/00001_demo_catalog.sql','apps/api/catalog.json','apps/api/docs/openapi.json','apps/api/main_test.go','apps/api/docs_test.go','apps/api/security_test.go','apps/api/request_security_test.go','deploy/brutforce-demo.service','apps/web/src/App.tsx','apps/web/src/api.ts','apps/web/src/api.test.ts','apps/web/src/types.ts','apps/web/src/styles.css','apps/web/src/overrides.css','apps/web/src/v2.css','apps/web/src/V2Visual.tsx','apps/web/src/App.test.tsx','apps/web/src/design.test.tsx','apps/web/src/navigation.test.tsx','apps/web/design-specs.md','apps/web/src/AtlasIcons.tsx','apps/web/src/InstallApp.tsx','apps/web/src/pwa.test.tsx','apps/web/public/manifest.webmanifest','apps/web/public/assets/v2/mascot-hold-2d-alpha.webp','apps/web/public/assets/v2/mascot-walk-2d-alpha.webp','apps/web/public/assets/v2/mascot-counter-thoughtful-2d-alpha.webp','apps/web/public/assets/v2/mascot-cellar-2d-alpha.webp','apps/web/public/assets/v2/mascot-offline-2d-alpha.webp','apps/web/public/assets/v2/svoe-vino-logo.svg','apps/web/index.html'];
for(const source of ['apps/api/database_integration_test.go','apps/api/database_test.go','apps/api/cmd/catalog-migrate/main.go'])try{await access(resolve(root,source));sourceFiles.push(source);}catch{}
for(const source of sourceFiles)await writeFile(resolve(sourceDir,snapshotName(source)),await readFile(resolve(root,source)));
const gwt={
"SR-001":["несколько фото-кандидатов", "принять ответ с selectedId", "сохранить порядок и предоставить выбор"],
"SR-002":["разные ID/годы", "открыть не первого", "карточка выбранной записи"],
"SR-003":["карточка из списка", "экранный возврат", "контекст и scroll без нового поиска"],
"SR-004":["карточка из списка", "системный Back", "вернуться к списку"],
"SR-005":["ноль или один кандидат", "принять ответ", "без фиктивных альтернатив"],
"SR-006":["неподходящие кандидаты", "отказаться", "ручной поиск или пересъёмка"],
"SR-007":["неполные поля и фото", "отобразить результат", "не выдумывать факты и не обрезать название"],
"SR-008":["текстовая выдача", "отобразить список", "нет бейджа фото"],
"SR-009":["мобильная выдача", "читать и выбирать", "полные названия, геометрия и фокус"],
"SVC-001":["ranked IDs", "enrich provider response", "preserved order and catalog fields"],
"SVC-002":["invalid response", "validate provider", "502 without false result"],
"SVC-003":["separate URLs", "request alternatives", "correct service; unconfigured503"],
"SVC-004":["local reference", "HTTP request", "synthetic compatible response"],
"SVC-005":["stored photo", "delegate image search", "bytes sent, no public URL"],
"SVC-006":["configured search", "invalid input or URL", "fail closed"],
"SVC-007":["redirect or unknown source", "call endpoint", "redirect not followed; unknown source rejected"],
"SVC-008":["wire response", "validate required fields", "missing/null rejected, additive fields allowed"],
"SVC-009":["canceled or expired request", "call provider", "cancellation/deadline respected"],
"SVC-010":["two reference addresses", "run conformance", "success and negative contracts checked"],

 'REC-001':['открыта карточка','получить альтернативы выбранному ID','показан отдельный блок рекомендаций'],
 'REC-002':['сервис возвращает пустой список','загрузить рекомендации','карточка доступна и показано пустое состояние'],
 'REC-003':['сервис рекомендаций упал','открыть карточку и нажать повтор','карточка не исчезает, повтор восстанавливает рекомендации'],
 'REC-004':['запрос в полёте','уйти с карточки до ответа','отмена передана; поздний ответ игнорируется'],
 'REC-005':['есть рекомендуемое вино','явно нажать на него','открывается его карточка и один новый запрос рекомендаций'],

 'DB-001':['пустая зарегистрированная тестовая схема','применить миграции Goose повторно','создана рабочая схема; повторное применение безопасно и сохраняет записи'],
 'DB-002':['малый синтетический seed','применить начальное наполнение повторно','по одному экземпляру каждого ID; изменённые значения не перезаписаны'],
 'DB-003':['каталог в PostgreSQL','прочитать и найти вино через реальный Go API','стабильные ID и поля, пустой результат корректен; SQL-подобный ввод остаётся данными'],
 'DB-004':['данные записаны','закрыть клиента и подключиться заново','данные сохранились вне памяти процесса'],
 'DB-005':['подключение runtime-роли','прочитать каталог и попытаться выполнить DDL','чтение разрешено, изменение схемы запрещено'],
 'DB-006':['БД недоступна при запросе','клиент читает каталог или ищет вино','структурированный HTTP 503 без DSN/пароля и ложного успешного fallback'],
 'SEC-009':['contest WebP decoder registered','upload WebP through demo photo endpoint','existing JPEG/PNG/GIF allowlist still rejects WebP'],
 "EVAL-007":["bounded input", "oversized or truncated image", "rejected before recognition"],
 "EVAL-008":["multiple sequential images", "more than four requests", "no stored originals or demo-rate429"],
 "EVAL-009":["occupied recognition slots", "additional request", "429 until capacity available"],
 "REPORT-001":["wide report matrix", "horizontal scrolling", "scenario column and every section label remain anchored with opaque background"],
 "REPORT-002":["unordered run index", "render report", "newest runs first"],
 "REPORT-003":["historical errors and latest partial run", "render summary", "latest counts only; skipped is not passed"],

 "EVAL-001":["valid photo and injected recognizer", "POST multipart image", "JSON200 exact slug, no synthetic card"],
 "EVAL-002":["WebP named jpg", "POST image", "decoder accepts actual format"],
 "EVAL-003":["malformed multipart or invalid/oversized image", "POST request", "JSON error; recognizer not called"],
 "EVAL-004":["contest API", "wrong method or unknown path", "JSON405/404, never SPA HTML"],
 "EVAL-005":["no recognizer configured", "POST valid photo", "JSON503 recognition_unavailable, no invented slug"],
 "EVAL-006":["time-limited request", "deadline or client cancellation", "context cancelled, bounded request"],

 'API-019':['server with web root','call v1 and retired API paths','v1 responds; retired and unknown API paths return JSON404'],
 'UI-025':['API client','catalog, photo upload and receipt search','only v1 endpoints are used with preserved payloads'],
 'UI-024':['непустой поисковый запрос','нажать лупу либо Enter','запускается поиск того же запроса'],
 'DESIGN-020':['экран поиска','ввести текст или перейти к кнопке клавиатурой','цельная округлая рамка и видимый фокус, список отделён от формы'],
 'DESIGN-022':['экран v2 и mascot component','показать допустимые семантические сцены','выбранный ассет, alt и адаптивная центральная home-panel присутствуют; camera/photo/candidates/result не получают маскота'],
 'UI-023':['карточка вина','нажать закладку, затем повторно','состояние и сохранённый список переключаются согласованно'],
 'DESIGN-019':['узкая карточка','показать действие сохранения','кнопка в шапке, без широкой рамки, доступная область нажатия'],
 'UI-022':['поиск или сохранённое','нажать Главная, затем явную кнопку съёмки','Главная показывает старт без getUserMedia; CTA открывает камеру с fallback при запрете'],
 'DESIGN-015':['широкий или узкий экран','открыть приложение','рамка только от1024px'], 'DESIGN-016':['десктопная рамка','открыть камеру','высота ограничена внутренним экраном, затвор доступен'],
 'DESIGN-013':['утверждённые SVG макета','рендер welcome','геометрия scanner совпадает'], 'DESIGN-014':['welcome','показана подсказка','согласованная короткая подсказка центрирована, переносится естественно'],
 'DESIGN-012':['открыта камера','показаны рамка и подсказка','текст в отдельной строке, без пересечения рамки'],
 'UI-012':['обычная вкладка','открыть приложение без установки','основные действия доступны'], 'UI-013':['браузер предлагает установку','нажать и отменить либо получить отказ','обычный путь остаётся доступен'], 'UI-014':['standalone','открыть приложение','тот же путь без предложения установки'], 'UI-015':['manifest','проверить маршрут и файлы','standalone / и PNG192/512'], 'DESIGN-010':['низкий viewport','открыть камеру','превью сжимается, действия внутри экрана'], 'DESIGN-011':['короткий экран','повернуть устройство','подсказки и затвор не обрезаются'],
 'API-001':['сценарий exact','POST /v1/search','выбран первый synthetic candidate'], 'API-002':['сценарий uncertain','POST /v1/search','есть кандидаты, selectedId отсутствует'], 'API-003':['сценарий none','POST /v1/search','candidates равен []'], 'API-004':['сценарий error','POST /v1/search','HTTP 503 содержит structured error'], 'API-005':['текст названия или винодельни','POST /v1/search','поиск без учёта регистра'], 'API-006':['некорректный JSON или scenario','POST /v1/search','HTTP 400 JSON error'], 'API-007':['неверный method или API path','запрос к API','JSON HTTP 405 либо 404'], 'API-008':['сервер доступен','GET /v1/health','ok и demo равны true'], 'API-009':['задан WEB_ROOT','GET file или client route','файл либо index.html отданы'], 'API-010':['валидный PNG upload','POST upload, затем search по receipt','байты и metadata сохранены, receipt принимается'], 'API-011':['некорректное либо >10 MiB фото','POST upload','400 без записи'], 'API-012':['UPLOAD_DIR не задан','POST upload','503 storage_unavailable'], 'API-013':['неизвестный photoId','POST search','404 photo_not_found'], 'API-014':['хранилище заполнено','POST upload','503 storage_full'], 'API-015':['embedded catalog','GET /v1/catalog','ровно восемь уникальных synthetic записей'], 'API-016':['название, винодельня или год','POST search','фильтрация по тому же embedded catalog'], 'API-017':['GET /api/docs','запросить Swagger UI, OpenAPI и локальные assets','документация доступна без CDN, её ошибки остаются JSON API errors'], 'API-018':['OpenAPI и canonical schema','прочитать спецификацию и вызвать четыре метода','в документе только реальные методы, schema и error shape совпадают с контрактом'],
 'SEC-001':['ZIP или SVG-байты под видом изображения','POST multipart photo','HTTP 400 invalid_photo, приватные файлы не создаются'], 'SEC-002':['обрезанный PNG с корректным IHDR/DecodeConfig; валидные JPEG, GIF и PNG','POST multipart photo','обрезанное изображение получает HTTP 400 invalid_photo после полной декодировки, валидные форматы принимаются'], 'SEC-003':['PNG IHDR 5001×5001 (>25 млн пикселей) либо 12001×1 (выше лимита стороны)','POST multipart photo','HTTP 400 invalid_photo, файлы не создаются'], 'SEC-004':['лишняя часть, два photo, photo без файла или файл 10 MiB+1','POST multipart photo','HTTP 400, файлы не создаются'], 'SEC-005':['два валидных upload удерживают слоты обработчика','начать третий multipart upload','HTTP 429 upload_busy, Retry-After: 1 и body не читается; после освобождения первые два получают 201'], 'SEC-006':['query длиннее 256 Unicode-символов, control-символ, неверный UTF-8, лишние поля или слишком большое тело','POST /v1/search','HTTP 400; ограниченный текст остаётся данными и не отражается в ответе'], 'SEC-007':['POST API с неверным Content-Type, сжатым телом или чужим Origin; затем допустимые записи','выполнить запросы в одно окно бюджета','ранние запросы отклоняются 415/403 до handler; search: burst 10, refill 1/с (60/мин); upload: burst 4, refill 1/5 с (12/мин); 429 содержит Retry-After'], 'SEC-008':['WEB_ROOT и приватный файл upload','запросить API/файловые пути и передать traversal photoId','приватные байты не выдаются, traversal отклоняется 400, ответы имеют nosniff и DENY'],
 'UI-001':['стартовый экран','пользователь начинает путь','есть вход в сканирование'], 'UI-002':['пользователь выбрал сканирование','переход UI','есть камера/выбор файла'], 'UI-003':['камера запрещена','пользователь начинает путь','доступны fallback действия'], 'UI-004':['поиск по фото не завершился','пользователь отменяет','главная показывает явные действия продолжения или удаления фото'], 'UI-005':['поиск отменён','поздний ответ завершает старый запрос','главная и retained context не меняются без явного продолжения'], 'UI-006':['API вернул кандидатов','пользователь исправляет ответ','можно выбрать другой результат'], 'UI-007':['mocked API вернул exact shape','React применяет ответ','видны synthetic details'], 'UI-008':['пользователь ищет вручную','отправлен scenario none','доступен экран no-match'], 'UI-009':['API вернул пустых кандидатов после фото либо ручного запроса','пользователь выбирает дальнейшее действие','фото ведёт к названию/пересъёмке, ручной поиск сохраняет query; чужие фото и случайные кандидаты не появляются'], 'UI-010':['selectedId отсутствует в candidates','React валидирует ответ','видна recoverable error'], 'UI-016':['навигация приложения','открыт поиск и введён query','каталог фильтруется, активный раздел выделен'], 'UI-017':['каталожная карточка','сохранить и перезагрузить','один local snapshot восстановлен'], 'UI-018':['сохранённое вино','удалить последнюю запись','показано полезное пустое состояние'], 'UI-019':['повреждённый либо duplicate storage','открыть приложение','запуск не падает, записи очищены'], 'UI-020':['поиск каталога в ожидании','уйти в другой раздел','запрос отменён, поздний ответ игнорирован'], 'UI-021':['browser storage бросает ошибку','сохранить карточку','ошибка видна, успех не заявлен'], 'UI-026':['открыт preview исходного фото','асинхронный поиск завершён до закрытия preview','возврат идёт на актуальный результат, не на stale loading'], 'UI-027':['ручной запрос и кандидаты уже известны','открыть карточку, исправление и вернуться назад','сохраняются карточка, год, кандидаты и исходный query'], 'UI-028':['есть принятый photo receipt','сеть или сервер возвращают ошибку, затем повтор','типы ошибок различимы, receipt используется без второго upload']
};

function exec(command,args,cwd){const started=performance.now();return new Promise(resolveRun=>{const done=x=>resolveRun({...x,wallMs:Math.round(performance.now()-started)});const child=spawn(command,args,{cwd,stdio:['ignore','pipe','pipe']});let out='',err='';child.stdout.on('data',b=>out+=b);child.stderr.on('data',b=>err+=b);child.on('error',e=>done({code:null,out,err:String(e)}));child.on('close',code=>done({code,out,err}));});}
function ids(text,prefix){const found=new Set();for(const m of text.matchAll(new RegExp(`${prefix}[- ]?(\\d{3}[A-Z]?)`,'g')))found.add(`${prefix}-${m[1]}`);return found;}
const severity={passed:1,skipped:2,failed:3,error:4};
function saveWorst(map,id,value){const previous=map.get(id),tests=[...(previous?.tests||[]),...(value.tests||[])],winner=!previous||severity[value.status]>=severity[previous.status]?value:previous;map.set(id,{...winner,tests,...(tests.length>1?{durationMs:undefined,durationText:'несколько проверок — см. детали'}:{})});}
function goCases(output){const byId=new Map();for(const line of output.split('\n')){try{const e=JSON.parse(line);if(!e.Test)continue;const m=e.Test.match(/^Test(API|DESIGN|SEC|EVAL|DB|SVC)(\d{3})/);const id=m?`${m[1]}-${m[2]}`:e.Test==='TestSPAHandlerServesFilesAndFallsBackToIndex'?'API-009':null;if(!id||!['pass','fail','skip'].includes(e.Action))continue;const status=e.Action==='pass'?'passed':e.Action==='skip'?'skipped':'failed',durationMs=e.Elapsed==null?undefined:Math.round(e.Elapsed*1000),durationText=e.Elapsed===0?'<1 мс (разрешение Go)':durationMs==null?'недоступно':`${durationMs} мс`;saveWorst(byId,id,{status,durationMs,durationText,reason:`Go-проверка ${e.Test}: ${status==='passed'?'пройдена':status==='skipped'?'пропущена':'не пройдена'}`,tests:[{name:e.Test,status,durationMs,durationText}]});}catch{}}return byId;}
function webCases(report,exitCode){const byId=new Map(),tests=report?.testResults?.flatMap(r=>r.assertionResults||[])||[];for(const test of tests){const status=test.status==='passed'?'passed':test.status==='pending'?'skipped':'failed',durationMs=test.duration==null?undefined:test.duration,testData={name:test.fullName||test.title,status,durationMs,durationText:durationMs==null?'недоступно':`${durationMs.toFixed(2)} мс`,output:test.failureMessages?.join('\n')},evidence=`${test.fullName||''} ${test.title||''}`;for(const prefix of ['UI','DESIGN','REPORT','REC','SR'])for(const id of ids(evidence,prefix))saveWorst(byId,id,{status,durationMs,durationText:testData.durationText,reason:`Vitest-проверка: ${status==='passed'?'пройдена':status==='skipped'?'пропущена':'не пройдена'} (${testData.name})`,output:testData.output,tests:[testData]});}if(!tests.length&&exitCode!==0)byId.set('UI-RUNNER',{status:'error',reason:'Vitest не создал читаемый JSON-отчёт.'});return byId;}
function goTests(output){const tests=[];let reportedMs=null;for(const line of output.split('\n'))try{const e=JSON.parse(line);if(e.Test&&['pass','fail','skip'].includes(e.Action)){const ms=e.Elapsed==null?null:Math.round(e.Elapsed*1000);tests.push({name:e.Test,status:e.Action==='pass'?'passed':e.Action==='skip'?'skipped':'failed',durationMs:ms,durationText:e.Elapsed===0?'<1 мс (разрешение Go)':ms==null?'недоступно':`${ms} мс`});}if(!e.Test&&e.Package&&['pass','fail'].includes(e.Action)&&e.Elapsed!=null)reportedMs=Math.round(e.Elapsed*1000);}catch{}return {tests,reportedMs};}
function webTests(report){return (report?.testResults?.flatMap(r=>r.assertionResults||[])||[]).map(t=>({name:t.fullName||t.title,status:t.status==='passed'?'passed':t.status==='pending'?'skipped':'failed',durationMs:t.duration==null?null:t.duration,durationText:t.duration==null?'недоступно':`${t.duration.toFixed(2)} мс`}));}
function packagePassed(output){let finalAction=null;for(const line of output.split('\n'))try{const e=JSON.parse(line);if(e.Package&&!e.Test&&['pass','fail'].includes(e.Action))finalAction=e.Action;}catch{}return finalAction==='pass';}
const dbIds=['DB-001','DB-002','DB-003','DB-004','DB-005'];
async function loadDbEvidence(){const resultsPath=process.env.DB_TEST_RESULTS_FILE,metadataPath=process.env.DB_TEST_METADATA_FILE,wallOverride=process.env.DB_TEST_WALL_MS;
  const supplied=Boolean(resultsPath||metadataPath||wallOverride);if(!supplied)return {supplied:false,valid:false,reason:'Внешнее DB-свидетельство не предоставлено.'};
  if(!resultsPath||!metadataPath)return {supplied:true,valid:false,reason:'Для внешнего DB-свидетельства нужны DB_TEST_RESULTS_FILE и DB_TEST_METADATA_FILE.'};
  if(!isAbsolute(resultsPath)||!isAbsolute(metadataPath))return {supplied:true,valid:false,reason:'Пути DB_TEST_RESULTS_FILE и DB_TEST_METADATA_FILE должны быть абсолютными.'};
  let raw,metadata;try{[raw,metadata]=await Promise.all([readFile(resultsPath,'utf8'),readFile(metadataPath,'utf8').then(JSON.parse)]);}catch(e){return {supplied:true,valid:false,reason:`Не удалось прочитать DB-свидетельство: ${e.message}`};}
  await Promise.all([writeFile(dbFile,raw),writeFile(dbMetadataFile,JSON.stringify(metadata,null,2)+'\n')]);
  if(!metadata||typeof metadata!=='object'||metadata.revision!==revision)return {supplied:true,copied:true,valid:false,reason:`Revision DB-свидетельства (${metadata?.revision||'отсутствует'}) не совпадает с GIT_REVISION (${revision}).`,metadata};
  if(typeof metadata.command!=='string'||!metadata.command.trim())return {supplied:true,copied:true,valid:false,reason:'В metadata DB-свидетельства отсутствует фактическая command.',metadata};
  const wallMs=metadata.wallMs??(wallOverride==null?null:Number(wallOverride));
  if(wallMs!=null&&(!Number.isFinite(wallMs)||wallMs<0))return {supplied:true,copied:true,valid:false,reason:'DB wallMs должен быть неотрицательным числом.',metadata};
  const found=goCases(raw),complete=dbIds.every(id=>found.has(id))&&packagePassed(raw)&&![...found.values()].some(v=>v.status!=='passed');
  if(!complete)return {supplied:true,copied:true,usable:true,valid:false,reason:'DB-свидетельство неполно или содержит непройденную проверку DB-001…DB-005.',metadata,raw,found,wallMs};
  return {supplied:true,copied:true,usable:true,valid:true,reason:'Внешнее DB-свидетельство подтверждено revision и полным JSONL.',metadata,raw,found,wallMs};
}

const goBin=process.env.GO_BIN||'go';
const go=await exec(goBin,['test','-count=1','-json','-skip','^TestEVAL','./...'],resolve(root,'apps/api'));
await writeFile(goFile,go.out+(go.err?`\n[stderr]\n${go.err}`:''));
const evaluation=await exec(goBin,['test','-count=1','-json','-run','^TestEVAL','./...'],resolve(root,'apps/api'));
await writeFile(evalFile,evaluation.out+(evaluation.err?`\n[stderr]\n${evaluation.err}`:''));
const web=await exec('npm',['--prefix','apps/web','test','--','--reporter=json',`--outputFile=${webFile}`],root);
let webReport;try{webReport=JSON.parse(await readFile(webFile,'utf8'));}catch{webReport=null;await writeFile(webFile,JSON.stringify({runner:'vitest',parseError:true,stdout:web.out,stderr:web.err},null,2)+'\n');}
const dbEvidence=await loadDbEvidence();

const found=new Map([...goCases(go.out),...goCases(evaluation.out),...(dbEvidence.usable?[...dbEvidence.found]:[]),...webCases(webReport,web.code)]);
const goDetail=goTests(go.out),evalDetail=goTests(evaluation.out),webDetail=webTests(webReport);
const cases=catalog.map(c=>{const [given,when,then]=gwt[c.id]||[];const v=found.get(c.id);if(v)return {...c,given,when,then,...v};if(dbIds.includes(c.id))return {...c,given,when,then,status:'not_run',reason:dbEvidence.supplied?dbEvidence.reason:'Внешняя DB-проверка не запускалась в обычном fast run.'};const runnerGo=['api','security','eval','database'].includes(c.area),runner=runnerGo?'Go':'Vitest';const goCode=c.area==='eval'?evaluation.code:go.code;const crashed=runnerGo?goCode!==0:web.code!==0;return {...c,given,when,then,status:crashed?'error':'skipped',reason:crashed?`${runner} suite ended with code ${runnerGo?goCode:web.code}; this case has no individual result.`:`No dedicated ${runner} assertion currently reports this case.`};});
const status=!dbEvidence.valid&&dbEvidence.supplied||go.code!==0||evaluation.code!==0||web.code!==0||cases.some(c=>c.status==='failed'||c.status==='error')?'failed':cases.some(c=>c.status==='skipped')?'partial':'passed';
const sources=sourceFiles.map(source=>`data/runs/${basename(sourceDir)}/${snapshotName(source)}`);
const measuredSum=tests=>tests.filter(t=>!t.name.includes('/')).reduce((sum,t)=>sum+(t.durationMs||0),0);
const dbArtifacts=dbEvidence.copied?[`data/runs/${basename(dbFile)}`,`data/runs/${basename(dbMetadataFile)}`]:[];
const dbSuite=dbEvidence.supplied?{id:'database',label:'Database integration suite (external evidence; not included in local wall time)',processWallMs:null,reportedMs:dbEvidence.wallMs??null,testMeasuredSumMs:dbEvidence.usable?measuredSum(goTests(dbEvidence.raw).tests):null,external:true,status:dbEvidence.valid?'passed':'error',reason:dbEvidence.reason}:null;
const run={schemaVersion:2,id,label,createdAt:now.toISOString(),revision,status,timing:{wallMs:Math.round(performance.now()-runStarted),suites:[{id:'api',label:'Go API suite',processWallMs:go.wallMs,reportedMs:goDetail.reportedMs,testMeasuredSumMs:measuredSum(goDetail.tests)},{id:'eval',label:'Contest HTTP contract (injected recognizer, no quality claim)',processWallMs:evaluation.wallMs,reportedMs:evalDetail.reportedMs,testMeasuredSumMs:measuredSum(evalDetail.tests)},{id:'ui',label:'Vitest UI suite',processWallMs:web.wallMs,reportedMs:webReport?.startTime!=null&&webReport?.endTime!=null?Math.round(webReport.endTime-webReport.startTime):null,testMeasuredSumMs:measuredSum(webDetail)},...(dbSuite?[dbSuite]:[])]},tests:[...goDetail.tests.map(t=>({...t,suite:'api'})),...evalDetail.tests.map(t=>({...t,suite:'eval'})),...webDetail.map(t=>({...t,suite:'ui'})),...(dbEvidence.usable?goTests(dbEvidence.raw).tests.map(t=>({...t,suite:'database'})):[])],command:`${goBin} test -count=1 -json -skip '^TestEVAL' ./...; ${goBin} test -count=1 -json -run '^TestEVAL' ./...; npm --prefix apps/web test -- --reporter=json`,caveat:`Синтетический контракт demo и проверки состояний UI. Это не benchmark OCR, визуального поиска или конкурсного качества.${dbEvidence.supplied?` ${dbEvidence.reason}`:''}`,databaseEvidence:{supplied:dbEvidence.supplied,valid:dbEvidence.valid,reason:dbEvidence.reason,revision:dbEvidence.metadata?.revision??null,command:dbEvidence.metadata?.command??null,wallMs:dbEvidence.wallMs??null},cases,artifacts:[`data/runs/${basename(goFile)}`,`data/runs/${basename(evalFile)}`,`data/runs/${basename(webFile)}`,...dbArtifacts],sources};
const runFile=resolve(runsDir,`${id}.json`);try{await access(runFile);throw new Error(`Refusing to overwrite ${runFile}`)}catch(e){if(e.code!=='ENOENT')throw e;}await writeFile(runFile,JSON.stringify(run,null,2)+'\n');
const digest=async file=>createHash('sha256').update(await readFile(file)).digest('hex');
const manifestFiles=[runFile,goFile,evalFile,webFile,...(dbEvidence.copied?[dbFile,dbMetadataFile]:[]),...sourceFiles.map(source=>resolve(sourceDir,snapshotName(source)))];
const manifest={schemaVersion:1,runId:id,recordedAt:new Date().toISOString(),files:await Promise.all(manifestFiles.map(async file=>({path:file.startsWith(sourceDir)?`data/runs/${basename(sourceDir)}/${basename(file)}`:`data/runs/${basename(file)}`,sha256:await digest(file)})))};
await writeFile(resolve(runsDir,`${id}.manifest.json`),JSON.stringify(manifest,null,2)+'\n');
const indexPath=resolve(root,'reports/site/data/index.json');const index=JSON.parse(await readFile(indexPath,'utf8'));index.generatedAt=new Date().toISOString();index.runs.push(`runs/${basename(runFile)}`);await writeFile(indexPath,JSON.stringify(index,null,2)+'\n');
console.log(JSON.stringify({run:id,status,goExit:go.code,evalExit:evaluation.code,webExit:web.code,databaseEvidence:dbEvidence.valid?'accepted':dbEvidence.supplied?'invalid':'not_supplied',report:`reports/site/data/runs/${basename(runFile)}`},null,2));
process.exitCode=status==='failed'?1:0;
