"""Gold-blind original-Conv3d check for rows changed by the runtime-linear judge."""
import argparse
import json
import time
from pathlib import Path

import torch
from peft import PeftModel
from transformers import AutoProcessor, BitsAndBytesConfig, Qwen3_5ForConditionalGeneration

from run import PROMPT, load_query, load_reference, read_rows, rerank, task


def main():
    p = argparse.ArgumentParser()
    p.add_argument('--root', type=Path, required=True)
    p.add_argument('--cases', type=Path, required=True)
    a = p.parse_args()
    root = a.root.resolve()
    wanted = json.loads(a.cases.read_text())
    saved = {r['case_id']: r for r in read_rows(root / 'raw-five.jsonl')}
    requests = {r['case_id']: r for r in read_rows(root / 'input-v1/requests.jsonl')}
    refs = {r['slug']: r for r in read_rows(root / 'input-v1/references.jsonl')}
    cards = {r['slug']: r for r in read_rows(root / 'input-v1/cards.jsonl')}
    if len(wanted) != len(set(wanted)) or not all(c in requests for c in wanted):
        raise ValueError('Invalid case list')
    if not all(saved[c].get('adapter5') for c in wanted):
        raise ValueError('Case missing saved adapter output')
    torch.set_num_threads(6)
    processor = AutoProcessor.from_pretrained(root/'base', min_pixels=65536,
        max_pixels=524288, trust_remote_code=False)
    digits = torch.tensor([processor.tokenizer.encode(str(i), add_special_tokens=False)[0]
        for i in range(6)], device='cuda')
    model = Qwen3_5ForConditionalGeneration.from_pretrained(root/'base',
        quantization_config=BitsAndBytesConfig(load_in_4bit=True,bnb_4bit_quant_type='nf4',
            bnb_4bit_use_double_quant=True,bnb_4bit_compute_dtype=torch.bfloat16,
            llm_int8_skip_modules=['visual','lm_head']), device_map={'':'cuda:0'},
        dtype=torch.bfloat16, attn_implementation='sdpa', trust_remote_code=False)
    model = PeftModel.from_pretrained(model, str(root/'adapter'), is_trainable=False).eval()
    output = root / 'conv3d-decision-check.jsonl'
    done = {r['case_id'] for r in read_rows(output)} if output.exists() else set()
    with torch.inference_mode(), output.open('a',encoding='utf-8') as stream:
        for case_id in wanted:
            if case_id in done:
                continue
            row = requests[case_id]
            ordered, payload = task(row['query_sha256'], row['ranked_slugs'][:5], cards)
            query_path = root/'input-stage'/Path(row['query_path']).relative_to(
                '/Users/skif/ml-data/brutforce/integration-20260925-1700/model/input-stage')
            query = load_query(query_path, row['query_sha256'])
            images = [query]
            try:
                images.extend(load_reference(root/'refs'/(refs[s]['sha256']+'.webp'),
                    refs[s]['sha256']) for s in ordered)
                content = [dict(type='text',text=PROMPT),dict(type='image')]
                for card in payload:
                    content.extend([dict(type='text',text=json.dumps(card,ensure_ascii=False)),dict(type='image')])
                chat = processor.apply_chat_template([dict(role='user',content=content)],
                    tokenize=False,add_generation_prompt=True,enable_thinking=False)
                inputs = processor(text=[chat],images=images,return_tensors='pt').to('cuda')
                t0 = time.perf_counter()
                logits = model(**inputs,use_cache=False,logits_to_keep=1).logits[0,-1,digits].float()
                torch.cuda.synchronize()
                probs = torch.softmax(logits,dim=-1).cpu().tolist()
                rank = rerank(row,ordered,probs,.7,.025)
                saved_rank = saved[case_id]['roman5_ranked']
                result = dict(case_id=case_id, basket=row['basket'], original_conv3d_logits=logits.cpu().tolist(),
                    original_conv3d_probabilities=probs, original_conv3d_winner_digit=int(logits.argmax()),
                    original_conv3d_ranked=rank, runtime_linear_ranked=saved_rank,
                    same_top1=rank[0]==saved_rank[0], elapsed_ms=round((time.perf_counter()-t0)*1000,3))
                stream.write(json.dumps(result,ensure_ascii=False)+'\n');stream.flush()
                print(f'{case_id} same_top1={result["same_top1"]} {result["elapsed_ms"]}ms',flush=True)
            finally:
                for image in images:
                    image.close()


if __name__ == '__main__':
    main()
