# Night CPU experiments

Read `README.md` before running a benchmark. This directory contains isolated,
gold-blind experiment code. Do not edit the shared `tools/vision-retrieval/`
implementation as part of a CPU timing run.

- Keep TEST and PROD processes, ports, source, model cache, and virtualenv intact.
- Bind experimental HTTP services to `127.0.0.1` on an unused port. Use transient
  units with explicit CPU and memory ceilings, and run one Sigma CPU benchmark
  at a time. Wait for a timed-out request to release the inference slot.
- The frozen v2 and organizer public manifests identify inputs; they contain no
  private answers. Never import `score_frozen.py`, `score_organizer.py`, private
  gold, or organizer diagnostic labels into an inference process or Pod.
- Record full raw HTTP rows including failures. Count a response after 10,000 ms
  as a deadline failure even if its HTTP status is 200. Do not silently retry.
- Preserve exact catalog/index/model revision and excluded-reference mask;
  report finite versus unavailable rows separately.
- Keep generated reports and private scoring material under the separate
  `/Users/skif/ml-data/brutforce/night-20260925/cpu/` artifact tree.
- Stop only experiment-owned units at closeout. Do not stage or commit without
  an explicit instruction from the coordinator.
