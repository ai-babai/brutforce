"""Gold-free coverage and timing summary for frozen raw outputs."""
import argparse,json,statistics
from pathlib import Path

def rows(path):return [json.loads(x) for x in Path(path).read_text().splitlines() if x.strip()]
def pct(values,p):
 if not values:return None
 ordered=sorted(values);i=(len(ordered)-1)*p/100;lo=int(i);hi=min(len(ordered)-1,lo+1)
 return round(ordered[lo]+(ordered[hi]-ordered[lo])*(i-lo),1)
def stats(values):
 return {'n':len(values),'p50_ms':pct(values,50),'p95_ms':pct(values,95),'max_ms':max(values) if values else None}
def main():
 p=argparse.ArgumentParser();p.add_argument('--fused',type=Path,required=True);p.add_argument('--out',type=Path,required=True)
 a=p.parse_args();data=rows(a.fused);summary={}
 for track in ('service','retrieval'):
  subset=[x for x in data if x['track']==track]
  # Distinct input bytes within a track. The same bytes across tracks require different processing.
  unique={(x['query_sha256'],x['track']):x for x in subset if not x.get('reused_from')}
  cases=list(unique.values())
  reasons={};labels={}
  for x in cases:
   key=x['selection']['selection_reason'];reasons[key]=reasons.get(key,0)+1
   choice=x.get('label_selection') or {}
   src=choice.get('source','none');labels[src]=labels.get(src,0)+1
  summary[track]={'manifest_cases':len(subset),'independent_input_images':len(cases),
                  'selection_reasons':reasons,'label_region_sources':labels,
                  'ocr_nonempty':sum(bool(x['ocr_text']) for x in cases),
                  'visual_batch_total':stats([x['timings_ms']['total_ms'] for x in cases]),
                  'detector':stats([x['timings_ms']['detect_ms'] for x in cases]),
                  'label_detector':stats([x['timings_ms'].get('label_detect_ms',0) for x in cases]),
                  'whole_embedding':stats([x['timings_ms']['whole_embedding_ms'] for x in cases]),
                  'label_embedding':stats([x['timings_ms']['label_embedding_ms'] for x in cases]),
                  'ocr':stats([x['timings_ms']['ocr_ms'] for x in cases]),
                  'all_cached_stage_sum':stats([x['variant_cached_stage_sum_ms']['all'] for x in cases]),
                  'all_diagnostic_batch_plus_ocr':stats([x['timings_ms']['sequential_total_ms'] for x in cases])}
 a.out.write_text(json.dumps({'latency_note':'Batch/cache measurements, no live HTTP; stage sums exclude diagnostic crop saving.',
                              'tracks':summary},ensure_ascii=False,indent=2)+'\n')
 print(json.dumps({k:{'cases':v['manifest_cases'],'unique':v['independent_input_images'],
                      'cached_p50_ms':v['all_cached_stage_sum']['p50_ms']} for k,v in summary.items()}))
if __name__=='__main__':main()
