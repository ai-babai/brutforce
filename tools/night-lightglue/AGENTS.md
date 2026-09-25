# Night LightGlue experiment

Read `README.md` before changing this module. Follow the root project AGENTS.md
and `apps/eval/AGENTS.md` for data and evaluation rules.

Input: frozen B raw JSONL, matching gold-blind public manifest and query bytes,
SHA-verified B catalog references, and B's gate-v2 availability mask.
Output: reference feature manifest/cache outside Git, complete raw JSONL with
baseline/local/fusion rankings, and service/retrieval submission JSON on the
trusted scoring host. Preserve row-level errors and elapsed time.

Do not put private answers, source query bytes, reference photos, checkpoints,
or pod credentials in Git. Do not tune fixed rerank rules after reading gold;
any new rule is a separately versioned run with an explicit reason.

Dependencies: official cvg/LightGlue at the README commit, PyTorch CUDA,
torchvision, Kornia, OpenCV, Pillow, NumPy. Verify with `python -m py_compile`
and a one-query GPU smoke, then full 213+103 run. Score only saved predictions.
