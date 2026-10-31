import { StrictMode } from 'react';
import { createRoot } from 'react-dom/client';
import { App } from './App';
import './v2.css';
import './air.css';
import './production-scanner.css';
import './demo-stand.css';

declare const __DEMO_STAND__: boolean;
createRoot(document.getElementById('root')!).render(<StrictMode><App demoStand={__DEMO_STAND__} /></StrictMode>);
