"""Catalog title contexts, separate from unchanged C08 visual families."""
from collections import defaultdict
from pathlib import Path
from candidate_policy import canonical_norm,contradicted,KEYS,query_attributes

class TitleCatalog:
    def __init__(self,references,families):
        self.families=families;self.references=references;self.rows=families.attributes.rows
        self.title=[canonical_norm(r.get('title','')) for r in references]
        self.context=[]
        for i,title in enumerate(self.title):
            grapes=self.rows[i]['grape'];parts=[]
            raw_grapes=query_attributes(families.attributes,title)['grape']
            if len(grapes)==1 and raw_grapes==grapes:
                grape=next(iter(grapes));tokens=title.split();g=grape.split()
                # Catalog title order provides a positive role contract. A bare
                # varietal or title not starting with the whole known variety
                # has no certified following product-line context.
                if tokens[:len(g)]==g and len(tokens)>len(g):parts=tokens[len(g):]
            self.context.append(' '.join(parts))
        self.vocab=set(' '.join(self.families.attributes.vocab).split())|set(' '.join(self.context).split())
    def contenders(self,head,base_order,query=None):
        head=int(head);producer=self.families.producer[head];grapes=self.rows[head]['grape'];query=query or {}
        known=[];unknown=[];rejected=[]
        for j in map(int,base_order[:20]):
            if not producer or self.families.producer[j]!=producer:continue
            row=self.rows[j]
            if contradicted(row,query):rejected.append(j);continue
            if row['grape'] and len(grapes)==1 and not (row['grape'] & grapes):rejected.append(j);continue
            if len(grapes)!=1 or row['grape']!=grapes or not self.context[j] or any(query.get(k) and not row[k] for k in KEYS):unknown.append(j)
            else:known.append(j)
        return {'known':known,'unknown':unknown,'rejected':rejected}
    def ambiguity(self,head,base_order):
        c=self.contenders(head,base_order)
        # Distinct title contexts nominate acquisition even when correlated
        # whole-bottle visual views all agree. They never select a candidate.
        return len({self.context[i] for i in c['known']})>=2
