/* Static UX controller. Deliberately simulates responses; not application/API code. */
let scanPending=false,scanEpoch=0,searchScroll=0,searchPageScroll=0,correctionOrigin=null;
let lastPhotoId=null,photoSequence=0;
function invalidateSearch(){clearTimeout(loadTimer);scanEpoch++;scanPending=false;pendingPreviewOutcome=null;}
const priorResetDemo=resetDemoContext;
resetDemoContext=function(id='start'){priorResetDemo(id);correctionOrigin=null;searchScroll=0;searchPageScroll=0;lastPhotoId=hasPhoto?'demo-photo-reference':null;};
function rememberSearchPosition(){searchScroll=$('#phone-content').scrollTop;searchPageScroll=window.scrollY;}
function setScreen(next){
 if(next==='cancelled')next='start';
 if(screen==='search'&&next!=='search')rememberSearchPosition();
 if(next==='preview'){
  if(!hasPhoto){next='start';}else{photoReturn=screen;pendingPreviewOutcome=null;}
 }
 screen=next;if(['start','search','saved'].includes(next))sectionContext=next;renderPhone();renderScenario();
 const content=$('#phone-content');content.scrollTop=0;
 if(next==='search')requestAnimationFrame(()=>{content.scrollTop=searchScroll;if(!document.body.classList.contains('mascot-preview'))window.scrollTo(0,searchPageScroll);});
};
function completeDemoSearch(outcome){
 if(!scanPending)return;
 clearTimeout(loadTimer);scanPending=false;
 resultReturn='start';candidateReturn='start';missingOrigin='photo';resultPhotoLinked=true;candidatePhotoLinked=true;selectedYear='2023';
 if(screen==='preview'&&['loading','waiting'].includes(photoReturn)){pendingPreviewOutcome=outcome;renderPhone();return;}
 setScreen(outcome);
}
function resumeScan(){
 clearTimeout(loadTimer);pendingPreviewOutcome=null;scanPending=true;const epoch=++scanEpoch;
 setScreen('loading');loadTimer=setTimeout(()=>{if(epoch===scanEpoch)completeDemoSearch(scanOutcome)},1200);
};
function beginScan(retry=false){
 invalidateSearch();correctionOrigin=null;
 if(scenario.id==='unreadable'&&!retry&&!retryAfterBadPhoto){hasPhoto=false;lastPhotoId=null;setScreen('unreadable');return;}
 if(!retry||!lastPhotoId)lastPhotoId='demo-photo-'+(++photoSequence);
 hasPhoto=true;showResume=false;selectedYear='2023';detailTab='overview';sectionContext='start';
 scanOutcome=retry||retryAfterBadPhoto?'result':({slow:'waiting',vintage:'candidates',missing:'missing',badphoto:'badphoto',network:'offline',server:'servererror'})[scenario.id]||'result';
 retryAfterBadPhoto=false;resumeScan();
};
function cancelToHome(){invalidateSearch();showResume=hasPhoto;sectionContext='start';setScreen('start');}
function submitManualSearch(query){
 manualQuery=query;if(!query){$('#wine-query').focus();return;}
 searchScroll=0;searchPageScroll=0;manualCatalog=false;
 if(!query.toLowerCase().includes('демо')){missingOrigin='manual';searched=false;setScreen('missing');return;}
 searched=true;renderPhone();$('#phone-content').scrollTop=0;
}
function openWine(year){
 if(screen==='search')rememberSearchPosition();
 resultReturn=screen==='saved'?'saved':screen==='search'?'search':'candidates';
 resultPhotoLinked=screen==='candidates'&&candidatePhotoLinked&&hasPhoto;
 selectedYear=year;detailTab='overview';setScreen('result');
}
function navigateProduct(next){
 if(next==='photo-back'){
  const target=pendingPreviewOutcome||photoReturn;pendingPreviewOutcome=null;setScreen(target);return;
 }
 if(next==='delete-photo'){
  invalidateSearch();hasPhoto=false;showResume=false;lastPhotoId=null;resultPhotoLinked=false;candidatePhotoLinked=false;setScreen('start');return;
 }
 if(next==='cancel'){cancelToHome();return;}
 if(next==='complete-search'){
  if(!scanPending)scanPending=true;completeDemoSearch('result');return;
 }
 if(next==='scan'){beginScan();return;}
 if(next==='galleryscan'){beginScan(retryAfterBadPhoto);return;}
 if(next==='retry'){if(hasPhoto)beginScan(true);else setScreen('gallery');return;}
 if(next==='browse-catalog'){manualCatalog=true;searched=true;manualQuery='';searchScroll=0;renderPhone();return;}
 if(next==='correction-back'){
  if(correctionOrigin){selectedYear=correctionOrigin.year;detailTab=correctionOrigin.tab;resultReturn=correctionOrigin.returnTo;resultPhotoLinked=correctionOrigin.linked;sectionContext=correctionOrigin.section;}
  setScreen('result');return;
 }
 if(next.startsWith('section-')){
  if(scanPending){invalidateSearch();showResume=hasPhoto;}
  const target=next.slice(8);sectionContext=target;
  if(target==='search'){searchReturn='start';correctionOrigin=null;}
  setScreen(target);return;
 }
 if(next==='preview'){setScreen(next);return;}
 if(screen==='preview'&&next===photoReturn){navigateProduct('photo-back');return;}
 if(next==='camera'||next==='gallery'){
  invalidateSearch();if(['badphoto','unreadable'].includes(screen))retryAfterBadPhoto=true;
  if(screen==='settings')cameraAllowed=true;
 }
 if(next==='correct-wine'&&screen==='result'){next='candidates';
  correctionOrigin={year:selectedYear,tab:detailTab,returnTo:resultReturn,linked:resultPhotoLinked,section:sectionContext};
  candidateReturn='correction-back';candidatePhotoLinked=resultPhotoLinked;
  // A saved/catalog card has no candidates belonging to the retained scan.
  if(!resultPhotoLinked){next='search';searchReturn='correction-back';}
 }
 if(next==='search'&&screen!=='result'&&screen!=='missing')searchReturn=correctionOrigin?'correction-back':'start';
 if(next==='start'&&scanPending){cancelToHome();return;}
 setScreen(next);
}
// Deep-linked demo state represents an already captured mock photo where appropriate.
lastPhotoId=hasPhoto?'demo-photo-reference':null;
renderPhone();renderScenario();
