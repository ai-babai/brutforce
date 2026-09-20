// Standalone mobile mode: V2 always uses the selected 2D artwork.
(()=>{
 const params=new URLSearchParams(location.search);
 if(params.get('mascotPreview')!=='1')return;
 const allowed=['start','camera','loading','waiting','candidates','result','missing','offline','servererror','unreadable','saved','gallery','preview','badphoto','permission','settings','search','catalog'];
 const requested=allowed.includes(params.get('scene'))?params.get('scene'):'start';
 document.body.classList.add('mascot-preview');document.body.dataset.mascotMode='off';
 const matching={waiting:'slow',candidates:'vintage',missing:'missing',offline:'network',servererror:'server',unreadable:'unreadable',badphoto:'badphoto',saved:'saved'}[requested];
 if(matching)scenario=scenarios.find(s=>s.id===matching);
 resetDemoContext(requested);
 selectedYear=params.get('year')==='2022'?'2022':'2023';
 if(['overview','description','source'].includes(params.get('detail')))detailTab=params.get('detail');
 searched=params.get('searched')==='1';
 if(['result','catalog','candidates'].includes(params.get('return')))photoReturn=params.get('return');
 screen=requested;renderPhone();renderScenario();
})();
