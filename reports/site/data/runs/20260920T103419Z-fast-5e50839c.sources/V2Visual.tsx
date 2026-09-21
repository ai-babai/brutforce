type MascotSceneName = 'home' | 'walk' | 'counter' | 'browse' | 'offline';

const mascotAssets: Record<MascotSceneName, { src: string; alt: string }> = {
  home: {
    src: '/assets/v2/mascot-hold-2d.webp',
    alt: 'Пёс-детектив держит бутылку, этикетка обращена к вам',
  },
  walk: {
    src: '/assets/v2/mascot-walk-2d.webp',
    alt: '',
  },
  counter: {
    src: '/assets/v2/mascot-counter-2d.webp',
    alt: '',
  },
  browse: {
    src: '/assets/v2/mascot-cellar-2d.webp',
    alt: '',
  },
  offline: {
    src: '/assets/v2/mascot-offline-2d.webp',
    alt: '',
  },
};

export function V2Logo() {
  return <img className="v2-logo" src="/assets/v2/svoe-vino-logo.svg" alt="Своё Вино" />;
}

export function MascotScene({ scene }: { scene: MascotSceneName }) {
  const asset = mascotAssets[scene];
  return <figure className={`mascot-scene mascot-scene-${scene}`} aria-hidden={asset.alt ? undefined : true}>
    <img src={asset.src} alt={asset.alt} />
  </figure>;
}
