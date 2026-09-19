(() => {
  const params = new URLSearchParams(location.search);
  if (params.get('mascotPreview') !== '1') return;

  const allowedModes = new Set(['off', 'quiet', 'hero']);
  const allowedScenes = new Set([
    'start', 'camera', 'loading', 'waiting', 'candidates', 'result',
    'missing', 'offline', 'gallery', 'preview', 'cancelled', 'badphoto',
    'permission', 'settings', 'search', 'catalog'
  ]);
  const mode = allowedModes.has(params.get('mode')) ? params.get('mode') : 'quiet';
  const requestedScene = allowedScenes.has(params.get('scene')) ? params.get('scene') : 'start';
  const scenarioForScene = {
    waiting: 'slow',
    candidates: 'vintage',
    missing: 'missing',
    offline: 'network'
  };

  document.body.classList.add('mascot-preview');
  document.body.dataset.mascotMode = mode;

  const mascotImage = (name, className, alt) => {
    const image = document.createElement('img');
    image.src = `assets/mascot/${name}.png`;
    image.className = className;
    image.alt = alt;
    image.decoding = 'async';
    return image;
  };

  const decoratePreview = () => {
    if (mode === 'off') return;

    if (screen === 'start' && mode === 'quiet') {
      const icon = document.querySelector('#flows .start-tip > span');
      if (icon) {
        icon.classList.add('mascot-start-tip');
        icon.replaceChildren(mascotImage('guide', 'mascot-tip-image', 'Пёс-детектив показывает, как расположить бутылку'));
      }
    }

    if (screen === 'start' && mode === 'hero') {
      const bottle = document.querySelector('#flows .start-hero .hero-bottle');
      if (bottle) bottle.replaceWith(mascotImage('guide', 'mascot-hero-image', 'Пёс-детектив с лупой'));
    }

    if (screen === 'loading' || screen === 'waiting') {
      const status = document.querySelector('#flows .recognition-status');
      if (status) {
        status.classList.add('mascot-search-status');
        status.prepend(mascotImage('search', 'mascot-search-image', 'Пёс-детектив ищет совпадение'));
      }
    }

    if (screen === 'missing') {
      const symbol = document.querySelector('#flows .state-symbol');
      if (symbol) {
        symbol.classList.add('mascot-missing-symbol');
        symbol.replaceChildren(mascotImage('guide', 'mascot-missing-image', 'Пёс-детектив предлагает продолжить поиск'));
      }
    }
  };

  const reportScreen = () => {
    if (parent === window) return;
    parent.postMessage({ type: 'mascot-screen', screen, mode, selectedYear, detailTab, searched, photoReturn }, location.origin);
  };

  const originalRenderPhone = renderPhone;
  renderPhone = function mascotPreviewRenderPhone() {
    originalRenderPhone();
    decoratePreview();
    reportScreen();
  };

  const scenarioId = scenarioForScene[requestedScene];
  if (scenarioId && typeof scenarios !== 'undefined') {
    const match = scenarios.find(item => item.id === scenarioId);
    if (match) scenario = match;
  }

  selectedYear = params.get('year') === '2022' ? '2022' : '2023';
  if (['overview', 'description', 'source'].includes(params.get('detail'))) detailTab = params.get('detail');
  searched = params.get('searched') === '1';
  if (['result', 'catalog', 'candidates', 'cancelled'].includes(params.get('return'))) photoReturn = params.get('return');
  screen = requestedScene;
  renderPhone();
  if (typeof renderScenario === 'function') renderScenario();
})();
