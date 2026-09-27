// The offline schematic is the default. Load the original catalog image only when reachable.
const catalogPhoto=new Image();
catalogPhoto.onload=()=>{
  const bottle=document.querySelector('.bottle');
  bottle.src=catalogPhoto.src;
  bottle.alt='Бутылка Портвейн белый Алушта';
};
catalogPhoto.src='https://demo.maks.dzap.pw/media/catalog/original/1b5a85780b4e1070dcecbc1da24d7d2b2d2b30a9f8a665ccb4a4ccb866e1e72d.webp';
// Air already ships these Phosphor Light paths; only the study state is interactive.
for(const el of document.querySelectorAll('[data-icon]')){
  const path=AIR_ICONS[el.dataset.icon];
  if(path)el.innerHTML=`<svg viewBox="0 0 256 256" fill="currentColor" aria-hidden="true">${path}</svg>`;
}
const buttons=[...document.querySelectorAll('[data-year]')];
const sampleYear=document.querySelector('.sample-year');
const note=document.querySelector('.study-note');
const overviewYear=document.querySelector('.overview-year');
for(const button of buttons)button.addEventListener('click',()=>{
  const known=button.dataset.year==='on';
  for(const item of buttons)item.setAttribute('aria-pressed',String(item===button));
  sampleYear.hidden=!known;
  note.hidden=!known;
  overviewYear.textContent=known?'2021':'Год не указан';
});
