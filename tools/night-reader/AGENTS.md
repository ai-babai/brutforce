# Target-only reader experiment

Start with README.md, then root AGENTS.md and `apps/eval/AGENTS.md`.
Use only public manifest fields and B's selected crop during inference.
Never send B candidate lists, catalog cards, or gold to the model prompt.
Save complete raw text and timing before scoring. Keep photos, model weights,
private annotations, and scoring files outside Git. Record any partial run,
missing target, decode failure, timeout, or unsupported model case in output.
