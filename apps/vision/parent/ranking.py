"""Catalog-only rankers and fixed rank fusion. No test answers are inputs."""
from __future__ import annotations
import re, math, unicodedata
from collections import Counter
import numpy as np

RU=str.maketrans({'а':'a','б':'b','в':'v','г':'g','д':'d','е':'e','ё':'e','ж':'zh','з':'z','и':'i','й':'i','к':'k','л':'l','м':'m','н':'n','о':'o','п':'p','р':'r','с':'s','т':'t','у':'u','ф':'f','х':'h','ц':'ts','ч':'ch','ш':'sh','щ':'sch','ы':'y','э':'e','ю':'yu','я':'ya','ь':'','ъ':''})
def norm(s):return ' '.join(re.findall('[a-z0-9]+',unicodedata.normalize('NFKC',str(s or '')).lower().translate(RU)))
def grams(s):
 s='  '+norm(s)+'  ';return Counter(s[i:i+3] for i in range(len(s)-2))
class Lexical:
 def __init__(self,catalog):
  self.docs=[];df=Counter()
  for item in catalog:
   g=grams(' '.join([item.get('producer','')]*2+[item.get('title','')]*2+[item['slug']]))
   self.docs.append(g);df.update(g.keys())
  self.idf={k:math.log(1+len(catalog)/(1+n)) for k,n in df.items()}
  self.norms=[math.sqrt(sum((v*self.idf.get(k,1))**2 for k,v in g.items())) or 1 for g in self.docs]
 def scores(self,text):
  q=grams(text)
  if len(norm(text))<4:return np.zeros(len(self.docs),dtype=np.float32)
  qnorm=math.sqrt(sum((v*self.idf.get(k,1))**2 for k,v in q.items())) or 1
  return np.array([sum(v*g.get(k,0)*self.idf.get(k,1)**2 for k,v in q.items())/(qnorm*n) for g,n in zip(self.docs,self.norms)],dtype=np.float32)

def top(scores,slugs,n=20):
 return [{'slug':slugs[int(i)],'score':round(float(scores[int(i)]),6)} for i in np.argsort(-scores) if np.isfinite(scores[int(i)])][:n]
def rrf(branches,weights,slugs,k=60):
 fused=np.zeros(len(slugs),dtype=np.float32)
 for name,score in branches.items():
  if score is None:continue
  valid=np.flatnonzero(np.isfinite(score))
  ordered=valid[np.argsort(-score[valid])]
  fused[ordered]+=float(weights.get(name,0))/(k+np.arange(1,len(ordered)+1))
 return fused
