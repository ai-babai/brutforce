#!/usr/bin/env python3
"""Rebuild the approved text/attribute recommendation JSON from display wines.

This is the portable form of the reviewed 2026-09-28 offline generator. The
indexVersion is a serving compatibility token, not a claim of visual ranking.
"""
import argparse
import hashlib
import json
import re
from pathlib import Path


DISPUTED_CATEGORY = {
    "agrolayn-heritage-dg-skin-contact-rkatsiteli-rkatsiteli-krasnoe-suhoe-12",
    "esse-demi-sec-muscat-nectar-muskat-belyy-beloe-ekstra-bryut-115",
    "belbek-beloe-suhoe-kaberne-sovinon-krasnoe-14",
}
DISPUTED_STRENGTH = {
    "derbent-vino-endemy-shardone-beloe-suhoe-13",
    "novyj-svet-vyderzhannoe-bryut",
    "vinodelnya-byurne-byurne-pino-blan-beloe-suhoe-14",
    "chateau-le-grand-vostock-krasnostop-rezerv-krasnoe-suhoe-145",
    "perovskikh-gevyurcztraminer-oranzh",
    "skalistyy-bereg-shyopot-tsvetov-risling-beloe-suhoe-109",
}
DISPUTED_GRAPES = {"vibes-vermentino-viognier-barrel-fermented-2022"}
STYLE = {
    "citrus": r"цитрус|лимон|лайм|грейпфрут|апельсин",
    "apple": r"яблок|груш|айв",
    "tropical": r"тропичес|манго|ананас|маракуй|персик|абрикос",
    "red_berries": r"малин|клубник|землян|вишн|красн.{0,12}ягод",
    "dark_berries": r"черносмород|ежевик|черник|слив|темн.{0,12}ягод",
    "floral": r"цветоч|цветов|цветк|жасмин|фиалк|розов.{0,7}лепест",
    "herbal": r"травян|трав|мят|шалфе|тимьян",
    "spice": r"прян|спец|перец|гвоздик|кориц",
    "mineral": r"минерал|мокр.{0,7}кам|кремни|сланец|гальк",
    "oak": r"дуб|бочк|баррик|древес|ванил|батонаж",
    "bread": r"дрожж|бриош|хлебн|выпечк",
    "honey": r"медов|мёд|мед|карамел|сухофрукт",
    "tannin": r"танин|терпк|плотн|насыщенн",
    "fresh": r"свеж|кислотност|освеж|легк",
    "soft": r"мягк|нежн|шелковист|округл",
    "skin_contact": r"скин.контакт|skin.contact|мацерац|оранжев",
}
PATTERNS = {key: re.compile(pattern, re.I) for key, pattern in STYLE.items()}


def category(card):
    text = (card.get("category_and_sweetness") or "").lower()
    color = next((c for c in ("красное", "белое", "розовое", "оранжевое") if c in text), None)
    sugar = (card.get("sweetness") or "").lower().strip()
    if sugar not in {"сухое", "полусухое", "полусладкое", "сладкое", "брют", "экстра брют"}:
        return None
    title = (card.get("title") or "").lower()
    if not color and sugar in {"брют", "экстра брют"} and re.search(r"\brose\b|розе", title):
        color = "розовое"
    if not color:
        return None
    sparkling = sugar in {"брют", "экстра брют"} or bool(
        re.search(r"игрист|шампан|просекко|креман|spumante|sparkling|cava\b", title + " " + text)
    )
    fortified = bool(re.search(r"мадер|портвейн|херес|кагор|мускатель", title))
    return ("крепленое" if fortified else "игристое" if sparkling else "тихое", color, sugar)


def strength(card):
    if card["id"] in DISPUTED_STRENGTH:
        return None
    low = card.get("alcohol_min_percent")
    high = card.get("alcohol_max_percent")
    value = card.get("alcohol_percent")
    if low is None:
        low = value
    if low is None:
        return None
    return float(low), float(high if high is not None else value if value is not None else low)


def gap(a, b):
    return max(0.0, a[0] - b[1], b[0] - a[1])


def overlap(a, b):
    return len(a & b) / len(a | b) if a and b else 0.0


def profile(card, grape_names):
    text = card.get("description") or ""
    grapes = {g.casefold().strip() for g in card.get("grapes", []) if g.strip()}
    title = (card.get("title") or "").casefold()
    grapes |= {name for name in grape_names if re.search(r"(?<!\w)" + re.escape(name) + r"(?!\w)", title)}
    return {
        "category": category(card),
        "strength": strength(card),
        "grapes": set() if card["id"] in DISPUTED_GRAPES else grapes,
        "style": {key for key, pattern in PATTERNS.items() if pattern.search(text)},
        "region": {s.casefold().strip() for s in card.get("region", [])},
        "food": {s.casefold().strip() for s in card.get("food_pairings", [])},
        "producer": card.get("producer_slug"),
    }


def score(a, b):
    if a["strength"] and b["strength"]:
        diff = gap(a["strength"], b["strength"])
        if diff > 3.0:
            return None
        band = 0 if diff <= 1.5 else 1
        abv = 1 - diff / 3.5
    else:
        band, abv = 2, 0.0
    grape = overlap(a["grapes"], b["grapes"])
    style = overlap(a["style"], b["style"])
    region = overlap(a["region"], b["region"])
    food = overlap(a["food"], b["food"])
    producer = float(bool(a["producer"] and a["producer"] == b["producer"]))
    near_same_winery = producer and band == 0 and grape > 0
    points = .24 * abv + .46 * grape + .17 * style + .07 * region + .04 * producer + .02 * food
    points += .07 * near_same_winery
    return band, round(points, 6)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--wines", type=Path, required=True, help="catalog-package/wines.jsonl")
    parser.add_argument("--index-info", type=Path, required=True, help="f8-bundle/index/index-info.json")
    parser.add_argument("--out", type=Path, required=True, help="new recommendation JSON path")
    args = parser.parse_args()
    if args.out.exists():
        parser.error("output already exists")
    raw = args.wines.read_bytes()
    cards = [json.loads(row) for row in raw.splitlines()]
    by_id = {card["id"]: card for card in cards}
    if len(by_id) != len(cards):
        parser.error("duplicate wine ID")
    grape_names = {g.casefold().strip() for card in cards for g in card.get("grapes", []) if len(g.strip()) >= 5}
    info = json.loads(args.index_info.read_text())
    groups, profiles = {}, {}
    for card in cards:
        identifier = card["id"]
        if identifier in DISPUTED_CATEGORY:
            continue
        p = profile(card, grape_names)
        profiles[identifier] = p
        if p["category"]:
            groups.setdefault(p["category"], []).append(identifier)
    neighbors = {}
    for card in cards:
        identifier = card["id"]
        p = profiles.get(identifier)
        ranked = []
        if p and p["category"]:
            for other_id in groups[p["category"]]:
                if other_id == identifier:
                    continue
                result = score(p, profiles[other_id])
                if result is not None:
                    band, points = result
                    ranked.append((band, -points, other_id))
        ranked.sort()
        neighbors[identifier] = [
            {"id": other_id, "score": max(0.0, round((2-band) / 3 + (-negative) / 3.25, 6))}
            for band, negative, other_id in ranked[:10]
        ]
    payload = {
        "catalogVersion": json.loads((args.wines.parent / "catalog.json").read_text())["catalog_version"],
        "modelVersion": "display-text-attributes-winery-review-v2",
        "indexVersion": info["version"],
        "neighbors": neighbors,
    }
    for source, rows in neighbors.items():
        assert source in by_id
        assert all(row["id"] in by_id and row["id"] != source for row in rows)
        assert all(rows[i]["score"] >= rows[i + 1]["score"] for i in range(len(rows) - 1))
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(payload, ensure_ascii=False, separators=(",", ":")) + "\n")
    print(f"{len(neighbors)} wines; catalog SHA256 {hashlib.sha256(raw).hexdigest()}")
    print(f"index SHA256 {hashlib.sha256(args.out.read_bytes()).hexdigest()}")


if __name__ == "__main__":
    main()
