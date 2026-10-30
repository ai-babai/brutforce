"""Nominate bounded title observation; never infer a line from absent words.

Draft only. No models/OCR, no ranking mutation, no identity-specific rules.
Call with current frozen canonical_norm, actual catalog rows and original Top20.
"""
VERSION = "title-specificity-reacquisition-draft-v1"
STRONG = ("semantic_expansion_override", "title_override", "coherent_support_override",
          "local_grape_override", "resource_signature_override", "upper_view_override",
          "upper_artwork_override", "resource_semantic_override", "text_override")


def phrase_prefix(a, b):
    a, b = tuple(a.split()), tuple(b.split())
    return bool(a and len(a) <= len(b) and b[:len(a)] == a)


def grape_relation(left, right):
    """Specificity is nomination uncertainty, not varietal equivalence.

    Distinct blends do not become singleton wines. A literal generic prefix
    cannot verify or contradict a more specific catalogue variety. This helper
    is deliberately not a replacement for the frozen OCR attribute parser.
    """
    left, right = set(left), set(right)
    if not left or not right:
        return "unknown"
    if len(left) != 1 or len(right) != 1:
        return "blend_or_multiple_uncertainty"
    a, b = next(iter(left)), next(iter(right))
    if a == b:
        return "exact"
    if phrase_prefix(a, b) or phrase_prefix(b, a):
        return "specificity_uncertainty"
    return "different_known_variety"


def title_context(title, metadata_grapes, vocabulary, normalize):
    """Catalog identity nominates a literal title anchor; it does not prove OCR.

    A compound metadata variety may have a generic title prefix. Retain that
    specificity discrepancy explicitly. Never treat it as an observed compound
    or silently turn another raw grape token into a product-line token.
    """
    tokens = normalize(title).split()
    matches = [g for g in vocabulary if phrase_prefix(g, " ".join(tokens))]
    if not matches:
        return {"context": "", "reason": "no_whole_catalogue_variety_title_prefix"}
    anchor = max(matches, key=lambda g: len(g.split()))
    remainder = " ".join(tokens[len(anchor.split()):])
    raw_grapes = {g for g in vocabulary if (" " + g + " ") in (" " + " ".join(tokens) + " ")}
    raw_grapes = {g for g in raw_grapes if not any(g != h and phrase_prefix(g, h) for h in raw_grapes)}
    if len(raw_grapes) != 1 or len(set(metadata_grapes)) != 1:
        return {"context": "", "reason": "raw_or_metadata_blend_uncertainty"}
    relation = grape_relation({anchor}, metadata_grapes)
    if relation not in ("exact", "specificity_uncertainty") or not remainder:
        return {"context": "", "reason": "bare_or_incompatible_catalogue_title"}
    return {"context": remainder, "anchor_literal": anchor,
            "metadata_grapes": sorted(metadata_grapes), "relation": relation,
            "proof_contract": "catalogue_identity_title_location_nomination_only",
            "reason": "positive_catalogue_title_context"}


def nominate(base_order, current_order, rows, producers, titles, vocabulary,
             normalize, query=None, flags=None, reference_ready=None):
    """Only returns acquisition plan. Incoming ranking remains unchanged.

    Unknown metadata is an included comparison obligation. Reliable known
    colour/sugar conflicts can exclude; generic/specific grape mismatches cannot.
    All required rows must eventually have source-bound title proof and scores.
    """
    query, flags = query or {}, flags or {}
    plan = {"version": VERSION, "requested": False, "ranking_mutation": False,
            "required_contenders": [], "unknown": [], "specificity_uncertainty": [], "excluded_known": [],
            "catalogue_contexts": {}, "missing_reference_proofs": [],
            "budget_ms": 550, "max_calls": 4, "language": "rus+eng",
            "absence_is_negative_evidence": False,
            "scope": "same_producer_related_variety_originalTop20"}
    def no(reason):
        return dict(plan, reason=reason)
    if len(base_order) == 0 or len(current_order) == 0:
        return no("empty_rankings")
    if any(flags.get(k) for k in STRONG):
        return no("preserve_existing_independently_verified_selection")
    if flags.get("ocr_errors"):
        return no("failed_observation_is_not_semantic_empty")
    if any(len(set(query.get(k, ()))) > 1 for k in ("grape", "color", "sugar")):
        return no("trusted_field_conflict_or_blend_uncertainty")
    head = int(current_order[0])
    producer = producers[head]
    if not producer:
        return no("unknown_producer")
    contexts = set()
    for i in map(int, base_order[:20]):
        if producers[i] != producer:
            continue
        row = rows[i]
        # These exclusions require actual trusted positive semantic evidence.
        conflict = any(query.get(k) and row.get(k) and not set(query[k]) & set(row[k])
                       for k in ("color", "sugar"))
        relation = grape_relation(rows[head].get("grape", ()), row.get("grape", ()))
        query_relation = grape_relation(query.get("grape", ()), row.get("grape", ()))
        if conflict or (query.get("grape") and query_relation == "different_known_variety"):
            plan["excluded_known"].append(i)
            continue
        if relation == "different_known_variety":
            continue  # Outside this nominated variety group; no semantic rejection.
        context = title_context(titles[i], row.get("grape", ()), vocabulary, normalize)
        plan["required_contenders"].append(i)
        if relation == "specificity_uncertainty" or context.get("relation") == "specificity_uncertainty":
            plan["specificity_uncertainty"].append(i)
        plan["catalogue_contexts"][str(i)] = context
        if context["context"]:
            contexts.add(context["context"])
        if (relation not in ("exact", "specificity_uncertainty") or not context["context"]
                or any(query.get(k) and not row.get(k) for k in ("color", "sugar", "grape"))):
            plan["unknown"].append(i)
        if reference_ready is None or not reference_ready(i):
            plan["missing_reference_proofs"].append(i)
    if head not in plan["required_contenders"] or len(contexts) < 2:
        return no("no_positive_distinct_catalogue_title_contexts")
    # Acquisition is permitted before reference readiness; promotion never is.
    plan["requested"] = True
    plan["reference_set_ready"] = not plan["unknown"] and not plan["missing_reference_proofs"]
    plan["promotion_ready"] = False  # Actual query proof, geometry and scores do not exist here.
    return dict(plan, reason="bounded_positive_title_observation_nomination")
