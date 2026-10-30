import { StrictMode } from 'react';
import { createRoot } from 'react-dom/client';
import { App } from './App';
import './v2.css';
import './air.css';
import './production-scanner.css';

createRoot(document.getElementById('root')!).render(<StrictMode><App /></StrictMode>);
