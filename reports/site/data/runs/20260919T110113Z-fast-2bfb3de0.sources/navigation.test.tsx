import { cleanup, render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { afterEach, describe, expect, it, vi } from 'vitest';
import { App } from './App';

const cabernet={id:'cabernet',name:'Каберне Совиньон',winery:'Долина',year:2023,image:'/assets/concept-bottle.png',description:'Красное вино.'};
const merlot={id:'merlot',name:'Мерло',winery:'Берег',year:2022,image:'',description:'Мягкое вино.'};
const catalog={demo:true,candidates:[cabernet,merlot]};
const response=(data:unknown)=>({ok:true,json:async()=>data});

afterEach(()=>{cleanup();localStorage.clear();vi.restoreAllMocks();vi.unstubAllGlobals()});
const mockCatalog=()=>vi.stubGlobal('fetch',vi.fn().mockResolvedValue(response(catalog)));

describe('catalog navigation and saved wines',()=>{
  it('UI-016 bottom navigation opens the catalog, filters it, and resets section scroll',async()=>{mockCatalog();render(<App/>);const nav=screen.getByRole('navigation',{name:'Основная навигация'});const content=document.querySelector('.app-content') as HTMLDivElement;expect(screen.getByRole('button',{name:'Сканер'})).toHaveAttribute('aria-current','page');await userEvent.click(screen.getByRole('button',{name:'Поиск'}));expect(screen.getByRole('button',{name:'Поиск'})).toHaveAttribute('aria-current','page');expect(await screen.findByRole('button',{name:/Каберне Совиньон/i})).toBeVisible();expect(screen.getByRole('button',{name:/Мерло/i})).toBeVisible();await userEvent.type(screen.getByLabelText(/Название вина/i),'мерло');expect(screen.queryByRole('button',{name:/Каберне Совиньон/i})).not.toBeInTheDocument();expect(screen.getByRole('button',{name:/Мерло/i})).toBeVisible();content.scrollTop=480;await userEvent.click(screen.getByRole('button',{name:'Сканер'}));expect(content.scrollTop).toBe(0);expect(nav).toBeVisible()});

  it('UI-017 saves one validated catalog snapshot and restores it after reload',async()=>{mockCatalog();const first=render(<App/>);await userEvent.click(screen.getByRole('button',{name:'Поиск'}));await userEvent.click(await screen.findByRole('button',{name:/Каберне Совиньон/i}));await userEvent.click(screen.getByRole('button',{name:'Сохранить вино'}));expect(JSON.parse(localStorage.getItem('wine-demo-saved-v1')!)).toEqual([cabernet]);first.unmount();render(<App/>);await userEvent.click(screen.getByRole('button',{name:'Сохранённое'}));expect(screen.getByRole('button',{name:/Каберне Совиньон/i})).toBeVisible();await userEvent.click(screen.getByRole('button',{name:/Каберне Совиньон/i}));expect(screen.getByRole('heading',{name:'Каберне Совиньон'})).toBeVisible()});

  it('UI-018 removes a saved wine and returns to the useful empty state',async()=>{localStorage.setItem('wine-demo-saved-v1',JSON.stringify([cabernet]));render(<App/>);await userEvent.click(screen.getByRole('button',{name:'Сохранённое'}));await userEvent.click(screen.getByRole('button',{name:/Каберне Совиньон/i}));await userEvent.click(screen.getByRole('button',{name:'Удалить из сохранённых'}));await userEvent.click(screen.getByRole('button',{name:'Сохранённое'}));expect(screen.getByRole('heading',{name:'Пока ничего не сохранено'})).toBeVisible();expect(JSON.parse(localStorage.getItem('wine-demo-saved-v1')!)).toEqual([])});

  it('UI-019 clears corrupt or duplicate saved snapshots without crashing',async()=>{localStorage.setItem('wine-demo-saved-v1',JSON.stringify([cabernet,cabernet]));render(<App/>);await userEvent.click(screen.getByRole('button',{name:'Сохранённое'}));expect(screen.getByRole('status')).toHaveTextContent(/повреждён и очищен/i);expect(screen.getByRole('heading',{name:'Пока ничего не сохранено'})).toBeVisible();expect(localStorage.getItem('wine-demo-saved-v1')).toBeNull()});

  it('UI-020 leaving catalog aborts the request and a late response cannot change section',async()=>{let resolve!:(value:ReturnType<typeof response>)=>void;vi.stubGlobal('fetch',vi.fn(()=>new Promise(done=>{resolve=done})));render(<App/>);await userEvent.click(screen.getByRole('button',{name:'Поиск'}));await userEvent.click(screen.getByRole('button',{name:'Сохранённое'}));resolve(response(catalog));await waitFor(()=>expect(screen.getByRole('heading',{name:'Пока ничего не сохранено'})).toBeVisible());expect(screen.getByRole('button',{name:'Сохранённое'})).toHaveAttribute('aria-current','page');expect(screen.queryByRole('button',{name:/Каберне Совиньон/i})).not.toBeInTheDocument()});

  it('UI-021 reports storage failure and does not claim the wine was saved',async()=>{mockCatalog();vi.spyOn(localStorage,'setItem').mockImplementation(()=>{throw new Error('quota')});render(<App/>);await userEvent.click(screen.getByRole('button',{name:'Поиск'}));await userEvent.click(await screen.findByRole('button',{name:/Каберне Совиньон/i}));await userEvent.click(screen.getByRole('button',{name:'Сохранить вино'}));expect(screen.getByRole('status')).toHaveTextContent(/Не удалось сохранить/i);expect(screen.getByRole('button',{name:'Сохранить вино'})).toHaveAttribute('aria-pressed','false')});
});
