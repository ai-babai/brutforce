# Nightly experiment coordination

Start with README.md and `../../docs/project/PLAN.md`.
Results: `../../docs/project/NIGHT-EXPERIMENT-RESULTS-2026-09-25.md`.

- No new training; Roman adapters are previously trained and labeled as such.
- Frozen v2 images, answers and catalog stay unchanged. Never fix a model by changing a test.
- Inference hosts receive inputs and catalog facts, not private gold or scoring credentials.
- Preserve failures and full denominators; unresolved images are not known-negative examples.
- Check case ID, track, image SHA and candidate provenance before comparing results.
- Cached-stage timings, uncapped diagnostics and strict HTTP deadlines are different measurements.
- Record hardware, threads, model revisions, runtime patches, input views and timing boundaries.
- A fallback must use actual available output, not a cached answer from another run.
- Publish aggregate summaries and append submissions; keep raw predictions outside web-root and Git.
- Export artifacts, verify SHA and delete temporary pods before the approved deadline.
- Do not replace TEST/PROD as part of an experiment without separate deployment scope.

Submodules own their isolated runtimes: night-cpu, night-lightglue, night-reader,
night-qwen-http and night-roman. Check their README before reproducing a profile.
