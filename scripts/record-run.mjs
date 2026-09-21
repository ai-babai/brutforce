#!/usr/bin/env node
// Adds a completed, immutable normalized run snapshot. It never overwrites runs.
import { createHash } from 'node:crypto';
import { mkdir, readFile, writeFile, access } from 'node:fs/promises';
import { resolve, basename } from 'node:path';

const root=resolve(import.meta.dirname,'..');
const input=process.argv[2];
if(!input) throw new Error('Usage: node scripts/record-run.mjs <normalized-run.json>');
const run=JSON.parse(await readFile(resolve(root,input),'utf8'));
if(!run.id||!run.createdAt||!Array.isArray(run.cases)) throw new Error('Run needs id, createdAt and cases.');
const dir=resolve(root,'reports/site/data/runs'); await mkdir(dir,{recursive:true});
const target=resolve(dir,basename(run.id)+'.json');
try { await access(target); throw new Error(`Immutable run already exists: ${target}`); } catch (e) { if(e.code!=='ENOENT') throw e; }
await writeFile(target,JSON.stringify({...run,schemaVersion:1},null,2)+'\n');
const indexPath=resolve(root,'reports/site/data/index.json'); const index=JSON.parse(await readFile(indexPath,'utf8'));
index.generatedAt=new Date().toISOString(); index.runs.push(`runs/${basename(run.id)}.json`);
await writeFile(indexPath,JSON.stringify(index,null,2)+'\n');
const hash=createHash('sha256').update(await readFile(target)).digest('hex');
const manifest={schemaVersion:1,runId:run.id,recordedAt:new Date().toISOString(),files:[{path:`data/runs/${basename(run.id)}.json`,sha256:hash}]};
await writeFile(resolve(dir,basename(run.id)+'.manifest.json'),JSON.stringify(manifest,null,2)+'\n');
console.log(JSON.stringify({recorded:target,sha256:hash},null,2));
