"""Separate bounded semantic candidate generation and verified selection.
Frozen visual proposal graph remains supplied by deployed C05/V6.
No IDs, brands, gold, scores tuned from controls, or OCR confidence changes.
"""
import numpy as np
from c05_candidate_policy import CatalogFamilies as C05Families,KEYS,contradicted,reliable_query,raw_query

class ExpansionFamilies(C05Families):
    def same(self,a,b):
        a,b=int(a),int(b)
        if a==b:return True
        if not self.producer[a] or self.producer[a]!=self.producer[b]:return False
        ga,gb=dict(self.group_keys[a]),dict(self.group_keys[b]);shared=set(ga)&set(gb)
        if shared:return all(ga[k]==gb[k] for k in shared)
        # Absence of a title-kind token is unknown, never negative evidence.
        if self.kind[a] and self.kind[b] and self.kind[a]!=self.kind[b]:return False
        if self.line[a] or self.line[b]:return bool(self.line[a] and self.line[a]==self.line[b])
        return bool(self.generic[a] and self.generic[b] and any(self.attributes.rows[a][k] for k in KEYS) and any(self.attributes.rows[b][k] for k in KEYS))
    def candidates(self,head,base_order):
        return [int(i) for i in base_order[:20] if self.same(head,int(i))]

def needs_acquisition(base_order,current_order,pass_words,families):
    if not len(base_order) or not len(current_order):return False
    group=families.candidates(int(base_order[0]),base_order)
    rows=families.attributes.rows
    variation={k for k in KEYS if len({frozenset(rows[i][k]) for i in group if rows[i][k]})>1}
    query=reliable_query(pass_words,families.attributes)
    raw=raw_query(pass_words,families.attributes)
    # Existing exact descriptor words nominate acquisition only; they never
    # filter rows, acquire fabricated confidence, or count as positive proof.
    unresolved={k for k in variation if raw[k] and not query[k]}
    return bool(len(group)>=2 and unresolved)

def expansion_decision(base_order,current_order,query,families,evidence=None):
    """Preserve C05 unless reliable evidence uniquely verifies a candidate.

    Caller supplies actual separately acquired trusted fields/provenance. This
    function must never receive unfiltered raw OCR fields. Unknown metadata is
    retained uncertainty: compatible incompletely-described siblings abstain.
    """
    base=[int(i) for i in base_order[:20]];current=np.asarray(current_order).copy()
    query={k:set(query.get(k,())) for k in KEYS}
    flags=dict(expansion_override=False,original_top20=base,query={k:sorted(v) for k,v in query.items()},evidence=evidence or [])
    def abstain(reason):return current,dict(flags,reason=reason)
    if not base or not len(current):return abstain('empty_order')
    if any(len(v)>1 for v in query.values()):return abstain('conflicting_trusted_fields')
    fields={k for k,v in query.items() if v}
    # A lone color or sugar is insufficient to expand retrieval across sibling
    # variants; an exact grape is already distinguishing catalog evidence.
    if not ('grape' in fields or {'color','sugar'}<=fields):return abstain('insufficient_distinguishing_fields')
    rows=families.attributes.rows;head=int(current[0]);group=families.candidates(base[0],base)
    flags['semantic_candidates']=group
    if head not in group:return abstain('current_head_outside_semantic_family')
    if not contradicted(rows[head],query):return abstain('current_head_not_reliably_contradicted')
    compatible=[i for i in group if not contradicted(rows[i],query)]
    fully_supported=[i for i in compatible if all(rows[i][k] and query[k]&rows[i][k] for k in fields)]
    uncertain=[i for i in compatible if i not in fully_supported]
    flags.update(compatible_candidates=compatible,fully_supported_candidates=fully_supported,unknown_metadata_candidates=uncertain,rejected_candidates=[{'candidate':i,'reason':'known_reliable_semantic_contradiction'} for i in group if i not in compatible])
    if uncertain:return abstain('compatible_unknown_metadata_competitor')
    if len(fully_supported)!=1:return abstain('not_one_verified_semantic_variant')
    winner=fully_supported[0]
    if winner not in [int(i) for i in current]:return abstain('verified_variant_not_in_existing_ranked_output')
    # Select the separately verified winner uniformly within original Top20;
    # otherwise keep deployed C05 order and every original row exactly once.
    result=np.asarray([winner]+[int(i) for i in current if int(i)!=winner])
    membership_changed=set(int(i) for i in result[:5]) != set(base[:5])
    flags.update(expansion_override=True,selected_candidate=winner,reason='unique_reliable_variant_in_original_top20',
                 original_top5_membership_changed=bool(membership_changed),candidate_scope_extended=bool(winner not in base[:5]),
                 verified_scope='original_top5' if winner in base[:5] else 'original_top20_extension')
    return result,flags
