import { useEffect, useRef, useState } from 'react';
import { ArrowLeft, Camera, Check, ImageSquare, MagnifyingGlass, Scan, X } from '@phosphor-icons/react';
import { searchWine, uploadPhoto } from './api';
import type { Candidate, PhotoReceipt, Scenario } from './types';

type Screen = 'welcome'|'camera'|'permission'|'loading'|'waiting'|'cancelled'|'result'|'candidates'|'search'|'missing'|'badphoto'|'error';
const fallback = '/assets/concept-bottle.png';

const demoCandidates: Candidate[] = [
  { id:'cabernet-2023', name:'Каберне Совиньон', winery:'Демо-винодельня', year:2023, image:fallback, description:'Красное сухое вино. Демонстрационная карточка без настоящих вкусовых данных.' },
  { id:'merlot-2022', name:'Мерло Резерв', winery:'Южная долина', year:2022, image:fallback, description:'Вымышленный кандидат для проверки неоднозначного результата.' },
];

export function App({initialScenario='exact',simulatePermissionDenied=false}:{initialScenario?:Scenario;simulatePermissionDenied?:boolean}={}) {
  const [screen,setScreen]=useState<Screen>('welcome');
  const [scenario]=useState<Scenario>(initialScenario);
  const [photo,setPhoto]=useState<string>();
  const [photoFile,setPhotoFile]=useState<File>();
  const [receipt,setReceipt]=useState<PhotoReceipt>();
  const [candidates,setCandidates]=useState<Candidate[]>([]);
  const [selected,setSelected]=useState<Candidate>();
  const [tab,setTab]=useState<'overview'|'description'|'source'>('overview');
  const [query,setQuery]=useState('');
  const [permissionDenied]=useState(simulatePermissionDenied);
  const [expandedPhoto,setExpandedPhoto]=useState(false);
  const abort=useRef<AbortController | undefined>(undefined);
  const waitTimer=useRef<ReturnType<typeof setTimeout> | undefined>(undefined);
  const lastRequest=useRef<{scenario:Scenario;query?:string}>({scenario:'exact'});
  const cameraRef=useRef<HTMLInputElement>(null);
  const galleryRef=useRef<HTMLInputElement>(null);
  const videoRef=useRef<HTMLVideoElement>(null);
  const canvasRef=useRef<HTMLCanvasElement>(null);
  const streamRef=useRef<MediaStream | undefined>(undefined);

  const stopCamera=()=>{streamRef.current?.getTracks().forEach(track=>track.stop());streamRef.current=undefined};
  useEffect(()=>()=>{abort.current?.abort();stopCamera();if(waitTimer.current)clearTimeout(waitTimer.current)},[]);
  useEffect(()=>()=>{if(photo?.startsWith('blob:')) URL.revokeObjectURL(photo)},[photo]);
  useEffect(()=>{if(screen!=='camera'||permissionDenied)return;let active=true;(async()=>{try{if(!navigator.mediaDevices?.getUserMedia)throw new Error();const stream=await navigator.mediaDevices.getUserMedia({video:{facingMode:{ideal:'environment'}},audio:false});if(!active){stream.getTracks().forEach(t=>t.stop());return}streamRef.current=stream;if(videoRef.current){videoRef.current.srcObject=stream;await videoRef.current.play()}}catch{if(active)setScreen('permission')}})();return()=>{active=false;stopCamera()}},[screen,permissionDenied]);
  const validPhoto=(file:File)=>['image/jpeg','image/png','image/gif'].includes(file.type)&&file.size<=10*1024*1024;
  const pickPhoto=(file?:File)=>{if(!file)return;if(!validPhoto(file)){setScreen('badphoto');return}stopCamera();setPhotoFile(file);setReceipt(undefined);setPhoto(URL.createObjectURL(file));uploadThenSearch(file,scenario)};
  const uploadThenSearch=async(file:File,next:Scenario,q?:string)=>{
    abort.current?.abort();if(waitTimer.current)clearTimeout(waitTimer.current);const controller=new AbortController();abort.current=controller;lastRequest.current={scenario:next,...(q?{query:q}:{})};setScreen('loading');waitTimer.current=setTimeout(()=>{if(!controller.signal.aborted&&abort.current===controller)setScreen('waiting')},1200);
    try{const saved=await uploadPhoto(file,controller.signal);if(controller.signal.aborted||abort.current!==controller)return;setReceipt(saved);await runSearch(next,q,saved,controller)}catch(e){if(waitTimer.current)clearTimeout(waitTimer.current);if(!controller.signal.aborted&&abort.current===controller&&(e as Error).name!=='AbortError')setScreen('error')}
  };
  const runSearch=async(next:Scenario=scenario, q?:string,knownReceipt:PhotoReceipt|undefined=receipt,existingController?:AbortController)=>{
    if(!existingController)abort.current?.abort(); if(waitTimer.current)clearTimeout(waitTimer.current); const controller=existingController??new AbortController(); abort.current=controller; lastRequest.current={scenario:next,...(q?{query:q}:{})}; setScreen('loading');
    waitTimer.current=setTimeout(()=>{if(!controller.signal.aborted&&abort.current===controller)setScreen('waiting')},1200);
    try { const data=await searchWine(next,q,controller.signal,knownReceipt?.id); if(controller.signal.aborted||abort.current!==controller)return; if(waitTimer.current)clearTimeout(waitTimer.current); const list=data.candidates; setCandidates(list);
      if(next==='none'||!list.length){setScreen('missing');return}
      if(next==='uncertain'||!data.selectedId){setScreen('candidates');return}
      setSelected(list.find(c=>c.id===data.selectedId)??list[0]); setTab('overview'); setScreen('result');
    } catch(e){ if(waitTimer.current)clearTimeout(waitTimer.current); if(!controller.signal.aborted&&abort.current===controller&&(e as Error).name!=='AbortError') setScreen('error'); }
  };
  const retry=()=>receipt?runSearch(lastRequest.current.scenario,lastRequest.current.query,receipt):photoFile?uploadThenSearch(photoFile,lastRequest.current.scenario,lastRequest.current.query):runSearch(lastRequest.current.scenario,lastRequest.current.query);
  const cancel=()=>{abort.current?.abort();if(waitTimer.current)clearTimeout(waitTimer.current);setScreen('cancelled')};
  const openCamera=()=> permissionDenied ? setScreen('permission') : setScreen('camera');
  const back=()=>{stopCamera();setScreen('welcome')};
  const capture=()=>{const video=videoRef.current,canvas=canvasRef.current;if(!video||!canvas||!video.videoWidth){cameraRef.current?.click();return}canvas.width=video.videoWidth;canvas.height=video.videoHeight;canvas.getContext('2d')?.drawImage(video,0,0);canvas.toBlob(blob=>{if(blob)pickPhoto(new File([blob],'camera.jpg',{type:'image/jpeg'}));else cameraRef.current?.click()},'image/jpeg',.9)};
  const choose=(c:Candidate)=>{setSelected(c);setTab('overview');setScreen('result')};
  const shown=selected??demoCandidates[0];

  return <main className="app-shell">
    <section className="app" data-testid="app">
      {screen==='welcome'&&<Page id="UI-001"><header className="brand"><span>своё</span>вино</header><div className="hero"><div><h1>Что за вино<br/>перед вами?</h1><p>Сфотографируйте этикетку. Откроем карточку вина.</p></div><img src={fallback} alt="Вымышленная бутылка вина для демонстрации"/></div><div className="actions"><button className="primary scan-button" onClick={openCamera}><Camera/><span><b>Сканировать вино</b><small>Наведите на этикетку</small></span><Scan/></button><div className="split-actions"><button onClick={()=>galleryRef.current?.click()}><ImageSquare/>Выбрать фото</button><button onClick={()=>setScreen('search')}><MagnifyingGlass/>По названию</button></div></div><Tip/></Page>}
      {screen==='camera'&&<div className="camera-page" id="UI-002"><Top title="Сканировать этикетку" onBack={back}/><p>Наведите на этикетку. Название должно быть читаемым.</p><div className="viewfinder"><video ref={videoRef} playsInline muted aria-label="Изображение с камеры"/><div className="camera-frame"/><span className="neighbor-hint">Нужная бутылка по центру</span></div><canvas ref={canvasRef} hidden/><button className="shutter" aria-label="Снять фото" onClick={capture}><span/></button><button className="text-button" onClick={()=>galleryRef.current?.click()}>Выбрать фото</button></div>}
      {screen==='permission'&&<Page id="UI-003"><Top title="Доступ к камере" onBack={back}/><StateIcon><Camera/></StateIcon><h2>Камера недоступна</h2><p>Можно продолжить с фотографией из галереи или найти вино по названию.</p><button className="primary" onClick={()=>galleryRef.current?.click()}><ImageSquare/>Выбрать фото</button><button className="secondary" onClick={()=>setScreen('search')}>Найти по названию</button></Page>}
      {(screen==='loading'||screen==='waiting')&&<Page id="UI-004"><Top title="Поиск" onBack={cancel}/><h2>{screen==='waiting'?'Нужно чуть больше времени':'Узнаём ваше вино'}</h2><p>{screen==='waiting'?'Поиск продолжается. Запрос можно отменить.':'Ищем вино по этикетке.'}</p>{photo&&<Photo photo={photo} onExpand={()=>setExpandedPhoto(true)}/>}<div className="scan-line"/><p className="status" role="status">{screen==='waiting'?'Продолжаем поиск':'Ищем совпадения'}</p><button className="text-button bottom" onClick={cancel}>Отменить поиск</button></Page>}
      {screen==='cancelled'&&<Page id="UI-005"><Top title="Поиск остановлен" onBack={back}/><h2>{photo?'Фото осталось':'Поиск остановлен'}</h2><p>{photo?'Можно повторить поиск или выбрать новый снимок.':'Можно повторить запрос или вернуться к поиску.'}</p>{photo&&<Photo photo={photo} onExpand={()=>setExpandedPhoto(true)}/>}<button className="primary bottom" onClick={retry}>Повторить поиск</button>{photo&&<button className="text-button" onClick={()=>galleryRef.current?.click()}>Выбрать другое фото</button>}</Page>}
      {screen==='candidates'&&<Page id="UI-006"><Top title="Похожие вина" onBack={back}/><h2>Есть несколько похожих этикеток</h2><p>{photo?'Сравните название и винодельню со своим снимком.':'Сравните название, винодельню и год.'}</p>{photo&&<Photo photo={photo} compact onExpand={()=>setExpandedPhoto(true)}/>}<div className="candidate-list">{(candidates.length?candidates:demoCandidates).map(c=><button key={c.id} onClick={()=>choose(c)}><CandidateImage candidate={c}/><span><small>{c.winery}</small><b>{c.name}</b><small>{c.year}</small></span></button>)}</div><button className="secondary" onClick={()=>setScreen('search')}>Ни одно не подходит</button></Page>}
      {screen==='result'&&<Page id="UI-007"><Top title="Карточка вина" onBack={back}/><div className="result-hero"><CandidateImage candidate={shown}/><div><span className="demo-label"><Check/>Карточка вина</span><small>{shown.winery}</small><h2>{shown.name}</h2><p>Красное сухое<br/>{shown.year}</p></div></div><button className="correction" onClick={()=>setScreen('candidates')}>Не это вино? Исправить</button><div className="tabs" role="tablist">{(['overview','description','source'] as const).map((t,i)=><button key={t} role="tab" aria-selected={tab===t} onClick={()=>setTab(t)}>{['Обзор','Описание','Источник'][i]}</button>)}</div>{tab==='overview'&&<dl><div><dt>Винодельня</dt><dd>{shown.winery}</dd></div><div><dt>Год</dt><dd>{shown.year}</dd></div></dl>}{tab==='description'&&<div className="tab-copy"><h3>Описание вина</h3><p>{shown.description}</p></div>}{tab==='source'&&<div className="tab-copy"><h3>Источник</h3><p>Эта карточка создана для прототипа. После подключения каталога здесь будет ссылка на исходную запись.</p><a href="https://vino-svoe.ru/" target="_blank" rel="noreferrer">Открыть платформу «Своё Вино»</a></div>}</Page>}
      {screen==='search'&&<Page id="UI-008"><Top title="Поиск по названию" onBack={back}/><h2>Найдём вручную</h2><form onSubmit={e=>{e.preventDefault(); if(query.trim())runSearch(scenario,query.trim())}}><label htmlFor="query">Название вина или винодельня</label><div className="search-field"><input id="query" value={query} onChange={e=>setQuery(e.target.value)} placeholder="Например, Каберне"/><button aria-label="Искать"><MagnifyingGlass/></button></div></form></Page>}
      {screen==='missing'&&<Page id="UI-009"><Top title="Результат поиска" onBack={()=>setScreen('search')}/><StateIcon><MagnifyingGlass/></StateIcon><h2>Вино не найдено</h2><p>Попробуйте другое название или новый снимок. Возможно, карточки пока нет в каталоге.</p><button className="primary" onClick={()=>setScreen('search')}>Изменить запрос</button><button className="secondary" onClick={openCamera}>Снять этикетку</button></Page>}
      {screen==='error'&&<Page id="UI-010"><Top title="Ошибка поиска" onBack={back}/><StateIcon><X/></StateIcon><h2>Не удалось выполнить поиск</h2><p>Сервис не ответил. Ваш снимок остаётся на этом устройстве.</p><button className="primary" onClick={retry}>Повторить запрос</button><button className="secondary" onClick={back}>На главную</button></Page>}
      {screen==='badphoto'&&<Page id="UI-011"><Top title="Неподходящий файл" onBack={back}/><StateIcon><ImageSquare/></StateIcon><h2>Нужно изображение</h2><p>Выберите фотографию в формате изображения. Другие типы файлов не отправляются в поиск.</p><button className="primary" onClick={()=>galleryRef.current?.click()}>Выбрать другое фото</button></Page>}
      <input ref={cameraRef} className="visually-hidden" aria-label="Снять фотографию этикетки" type="file" accept="image/*" capture="environment" onChange={e=>pickPhoto(e.target.files?.[0])}/>
      <input ref={galleryRef} className="visually-hidden" aria-label="Загрузить фотографию этикетки" type="file" accept="image/*" onChange={e=>pickPhoto(e.target.files?.[0])}/>
      {expandedPhoto&&<div className="photo-dialog" role="dialog" aria-modal="true" aria-label="Исходная фотография"><button aria-label="Закрыть фотографию" onClick={()=>setExpandedPhoto(false)}><X/></button><img src={photo||fallback} alt="Исходная фотография этикетки крупным планом"/></div>}
    </section>
  </main>;
}

function Page({children,id}:{children:React.ReactNode;id:string}){return <div className="page" id={id}>{children}</div>}
function Top({title,onBack}:{title:string;onBack:()=>void}){return <header className="top"><button aria-label="Назад" onClick={onBack}><ArrowLeft/></button><b>{title}</b><span/></header>}
function Tip(){return <div className="tip"><Scan/><span><b>Нужная бутылка по центру</b><small>Этикетка целиком, название читается.</small></span></div>}
function StateIcon({children}:{children:React.ReactNode}){return <div className="state-icon">{children}</div>}
function Photo({photo,compact=false,onExpand}:{photo?:string;compact?:boolean;onExpand?:()=>void}){return <button type="button" className={`photo ${compact?'compact':''}`} onClick={onExpand} aria-label={onExpand?'Открыть исходную фотографию':undefined}><img src={photo||fallback} alt={photo?'Загруженная фотография этикетки':'Демонстрационное фото бутылки'}/><span>{photo?'Ваше фото':'Демо-фото'}</span></button>}
function CandidateImage({candidate}:{candidate:Candidate}){return candidate.image?<img src={candidate.image} alt={`Демонстрационное изображение: ${candidate.name}`}/>:<div className="missing-image" role="img" aria-label={`Фото ${candidate.name} отсутствует`}><ImageSquare/><span>Демо-фото<br/>отсутствует</span></div>}
