import { useEffect, useState } from 'react';
type InstallEvent = Event & { prompt: () => Promise<void>; userChoice: Promise<{ outcome: string }> };

// Enhancement only: installation never gates the ordinary web journey.
export function InstallApp() {
  const [offer,setOffer]=useState<InstallEvent>();
  const [installed,setInstalled]=useState(()=>window.matchMedia?.('(display-mode: standalone)').matches ?? false);
  const [busy,setBusy]=useState(false);
  useEffect(()=>{
    const ready=(event:Event)=>{event.preventDefault();setOffer(event as InstallEvent)};
    const done=()=>{setInstalled(true);setOffer(undefined)};
    window.addEventListener('beforeinstallprompt',ready);
    window.addEventListener('appinstalled',done);
    return ()=>{window.removeEventListener('beforeinstallprompt',ready);window.removeEventListener('appinstalled',done)};
  },[]);
  if(installed||!offer)return null;
  return <button className="text-button" disabled={busy} onClick={async()=>{
    setBusy(true);
    try { await offer.prompt(); const choice=await offer.userChoice; if(choice.outcome==='accepted')setInstalled(true); }
    catch { /* Browser refused; the ordinary website remains usable. */ }
    finally {setOffer(undefined);setBusy(false)}
  }}>Установить приложение</button>;
}
