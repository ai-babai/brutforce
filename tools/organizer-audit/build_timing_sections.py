"""Build public, aggregate-only latency sections from recorded HTTP runs.

The adjacent timing audit contains provenance and checks only. Neither output
contains case-level predictions, private answers, input paths, or credentials.
"""

import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path


MODELS = (
    ("yoloe26s", "YOLOE-26s"),
    ("yolo26n-geometric", "YOLO26n + геометрия"),
    ("yolo26n", "YOLO26n + OWLv2"),
    ("rtdetr-r18", "RT-DETR R18 + OWLv2"),
    ("owlv2", "OWLv2 · v2"),
)
MANIFEST_SHA = "8f5755e3dc426a4b1fffafbe82e10435ed7cf1367dafa2f9087cfcc2289d7412"


def read(path):
    return json.loads(path.read_text())


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def percentile(values, percent):
    values = sorted(values)
    if not values:
        return None
    index = (len(values) - 1) * percent / 100
    lower = int(index)
    upper = min(lower + 1, len(values) - 1)
    return values[lower] + (values[upper] - values[lower]) * (index - lower)


def seconds(ms):
    return "—" if ms is None else f"{ms / 1000:.2f}"


def table(title, columns, rows, note=""):
    return {"title": title, "columns": [{"key": k, "label": v} for k, v in columns], "rows": rows, "note": note}


def cpu_run(path, expected_hashes):
    data = read(path)
    assert data["device"] == data["healthz"]["device"] == "cpu", path
    assert data["manifest_sha256"] == MANIFEST_SHA, path
    assert data["cases_total"] == data["distinct_image_sha256"] == 24, path
    rows = data["results"]
    hashes = [r["image_sha256"] for r in rows]
    assert len(rows) == 24 and hashes == expected_hashes, path
    assert all(r["response_image_sha256"] == r["image_sha256"] for r in rows if r["http_status"] == 200), path
    assert all(r["track"] == "service" for r in rows), path
    assert rows[0]["phase"] == "first_request_after_ready", path
    warm = rows[1:]
    succeeded = [r for r in warm if r["http_status"] == 200 and not r["error"]]
    full = [r for r in succeeded if r["ocr_executed"] and not r["ocr_error"]
            and r["server_timings_ms"].get("whole_embedding_ms", 0) > 0
            and r["server_timings_ms"].get("label_embedding_ms", 0) > 0]
    assert len(succeeded) == data["warm_successes"] and len(full) == data["full_pipeline_warm_successes"], path
    assert abs(percentile([r["elapsed_ms"] for r in succeeded], 50) - data["warm_p50_ms"]) < .02, path
    assert abs(percentile([r["elapsed_ms"] for r in succeeded], 95) - data["warm_p95_ms"]) < .02, path
    assert abs(percentile([r["elapsed_ms"] for r in full], 50) - data["full_pipeline_warm_p50_ms"]) < .02, path
    assert abs(percentile([r["elapsed_ms"] for r in full], 95) - data["full_pipeline_warm_p95_ms"]) < .02, path
    return data, succeeded, full


def gpu_subset(path, expected_hashes):
    rows = [json.loads(line) for line in path.read_text().splitlines() if line.strip()]
    matching = [r for r in rows if r["query_sha256"] in set(expected_hashes)]
    assert len(matching) == 24 and {r["query_sha256"] for r in matching} == set(expected_hashes), path
    assert len({r["run_id"] for r in matching}) == 1, path
    assert all(r["device"] == "cuda" and r["track"] == "service" and r["phase"] == "full-http" for r in matching), path
    assert all(r["http_status"] == 200 and r["result"]["image_sha256"] == r["query_sha256"] for r in matching), path
    full = [r for r in matching if r["result"]["timings_ms"].get("ocr_ms", 0) > 0
            and not r["result"].get("ocr_error")
            and r["result"]["timings_ms"].get("whole_embedding_ms", 0) > 0
            and r["result"]["timings_ms"].get("label_embedding_ms", 0) > 0]
    return rows, matching, full


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, required=True)
    parser.add_argument("--previous", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    manifest = args.previous / "organizer-audit/benchmark-queries.json"
    cases = read(manifest)["cases"]
    expected_hashes = [r["sha256"] for r in cases]
    assert len(expected_hashes) == len(set(expected_hashes)) == 24
    assert digest(manifest) == MANIFEST_SHA

    audit = {"version": 1, "generated_at_utc": datetime.now(timezone.utc).isoformat(),
             "manifest_sha256": MANIFEST_SHA, "case_count": 24, "sources": {}, "checks": []}
    cpu_rows, startup_rows, gpu_rows, stage_rows = [], [], [], []
    complete = True
    cpu_index = set()
    cpu_codes = set()
    cpu_hosts = set()
    cpu_thread_settings = set()
    cpu_count = 0
    for key, label in MODELS:
        cpu_path = args.root / "detectors/cpu24" / f"{key}.json"
        if not cpu_path.exists():
            complete = False
            cpu_rows.append({"model": label, "warm_n": "ожидается", "warm_p50": "—", "warm_p95": "—",
                             "full_n": "—", "full_p50": "—", "full_p95": "—", "within_3s": "—"})
            startup_rows.append({"model": label, "cold_load": "—", "first": "—"})
        else:
            data, warm, full = cpu_run(cpu_path, expected_hashes)
            cpu_count += 1
            audit["sources"]["cpu24:" + key] = digest(cpu_path)
            audit["checks"].append({"id": "cpu24:" + key, "cases": len(data["results"]),
                                     "matched_input_and_response_hashes": len(data["results"]),
                                     "warm_successes": len(warm), "full_pipeline_warm_successes": len(full),
                                     "ocr_errors": data["ocr_error_count"],
                                     "code_sha256": data["code_sha256"], "index_sha256": data["index_sha256"]})
            cpu_index.add(data["index_sha256"])
            cpu_codes.add(data["code_sha256"])
            cpu_hosts.add((data["hardware_label"], data["host_platform"]))
            cpu_thread_settings.add((data["omp_threads"], data["ocr_cpu_threads"]))
            cpu_rows.append({"model": label, "warm_n": len(warm), "warm_p50": seconds(percentile([r["elapsed_ms"] for r in warm], 50)),
                             "warm_p95": seconds(percentile([r["elapsed_ms"] for r in warm], 95)),
                             "full_n": f"{len(full)}/{len(warm)}", "full_p50": seconds(percentile([r["elapsed_ms"] for r in full], 50)),
                             "full_p95": seconds(percentile([r["elapsed_ms"] for r in full], 95)),
                             "within_3s": f"{sum(r['elapsed_ms'] <= 3000 for r in warm)}/{len(warm)}"})
            startup_rows.append({"model": label, "cold_load": seconds(data["healthz"]["cold_load_ms"]),
                                 "first": seconds(data["first_request_ms"])})
            stages = data["server_stage_p50_ms"]
            stage_rows.append({"model": label, "detect": seconds(stages["detect_ms"]),
                               "class": seconds(stages["class_ms"]), "label": seconds(stages["label_detect_ms"]),
                               "ocr": seconds(stages["ocr_ms"])})
        # The available new OWLv2 raw run uses a reference-gated index. Its
        # latency belongs to a different configuration, so use the dedicated
        # original-index OWLv2 benchmark in the historical table below.
        gpu_path = args.root / "detectors" / key / "full-organizer.jsonl" if key != "owlv2" else None
        if gpu_path and gpu_path.exists():
            all_rows, subset, full = gpu_subset(gpu_path, expected_hashes)
            audit["sources"]["gpu-organizer:" + key] = digest(gpu_path)
            audit["checks"].append({"id": "gpu-organizer:" + key, "source_run_cases": len(all_rows),
                                     "matched_input_and_response_hashes": len(subset), "full_pipeline_subset": len(full),
                                     "run_ids": sorted({r["run_id"] for r in subset})})
            gpu_rows.append({"model": label, "n": len(subset), "p50": seconds(percentile([r["elapsed_ms"] for r in subset], 50)),
                             "p95": seconds(percentile([r["elapsed_ms"] for r in subset], 95)),
                             "full_n": len(full), "full_p50": seconds(percentile([r["elapsed_ms"] for r in full], 50)),
                             "full_p95": seconds(percentile([r["elapsed_ms"] for r in full], 95))})
        elif key != "owlv2":
            complete = False
    assert len(cpu_index) <= 1 and len(cpu_codes) <= 1 and len(cpu_hosts) <= 1 and len(cpu_thread_settings) <= 1
    if cpu_thread_settings:
        assert cpu_thread_settings == {(4, 2)}
    if cpu_index:
        assert cpu_index == {"8f4db8aeb1d0dad35eeef327a2121739e61b1234d8e7bdeed9117cd8dfb99ef9"}

    old_4090 = read(args.previous / "benchmark-rtx4090-v2-context.json")
    old_ada = read(args.previous / "organizer-audit/benchmark-rtx4000ada-v2-context.json")
    old_cpu = read(args.previous / "organizer-audit/benchmark-cpu4.json")
    historical = []
    for name, data, path in (
        ("RTX 4090, OWLv2 v2", old_4090, args.previous / "benchmark-rtx4090-v2-context.json"),
        ("RTX 4000 Ada, OWLv2 v2", old_ada, args.previous / "organizer-audit/benchmark-rtx4000ada-v2-context.json"),
        ("CPU 4 потока, OWLv2 v1", old_cpu, args.previous / "organizer-audit/benchmark-cpu4.json"),
    ):
        expected = expected_hashes if data["cases_total"] == 24 else expected_hashes[:20]
        assert data["manifest_sha256"] == MANIFEST_SHA and [r["image_sha256"] for r in data["results"]] == expected
        assert all(r["response_image_sha256"] == r["image_sha256"] for r in data["results"] if r["http_status"] == 200)
        audit["sources"]["historical:" + name] = digest(path)
        historical.append({"run": name, "images": data["cases_total"],
                           "warm_n": data["warm_successes"], "p50": seconds(data["warm_p50_ms"]),
                           "p95": seconds(data["warm_p95_ms"]), "cold": seconds(data["healthz"]["cold_load_ms"]),
                           "first": seconds(data["first_request_ms"])})

    sections = [
        {"id": "latency-current", "title": "Скорость полного HTTP-распознавания", "status": "ready" if complete else "partial",
         "summary": "24 исходных фото организаторов, один и тот же набор SHA-256. Новые CPU-замеры сделаны на хосте RTX 4090 с принудительным исполнением на CPU; GPU-таблица четырёх новых детекторов взята по тем же фото из ранее записанных полных HTTP-прогонов. Исходный OWLv2 GPU показан отдельно ниже.",
         "tables": [
             table("CPU: 23 следующих запроса после готовности сервера, секунды",
                   [("model", "Детектор"), ("warm_n", "Успешных"), ("warm_p50", "p50"), ("warm_p95", "p95"),
                    ("full_n", "OCR + embeddings"), ("full_p50", "Полный p50"), ("full_p95", "Полный p95"),
                    ("within_3s", "≤3 с")], cpu_rows,
                   "«Полный» означает, что OCR и обе embedding-ветви действительно исполнились без ошибки. Общие p50/p95 и доля ≤3 с включают ранние выходы; доля ≤3 с не относится только к полному поднабору."),
             table("GPU RTX 4090: четыре новых детектора, те же 24 фото, секунды",
                   [("model", "Детектор"), ("n", "HTTP фото"), ("p50", "p50"), ("p95", "p95"),
                    ("full_n", "OCR + embeddings"), ("full_p50", "Полный p50"), ("full_p95", "Полный p95")], gpu_rows,
                   "Эти строки отобраны по SHA из каждого прогона на 103 организаторских фото. Это не отдельный упорядоченный warm-бенчмарк; распределения CPU и GPU не следует считать парным испытанием запрос за запросом."),
             table("Загрузка и первый запрос CPU, секунды",
                   [("model", "Детектор"), ("cold_load", "Загрузка модели/индекса"), ("first", "Первый HTTP после ready")], startup_rows,
                   "Загрузка взята из /healthz. Первый HTTP-запрос не входит в 23 warm-запроса; сумма этих двух величин не является измеренным временем запуска сервиса."),
         ],
         "notes": [
             "Клиент отправлял исходные байты по одному через локальный HTTP 127.0.0.1. Время включает декодирование, детектор, классификацию, фрагмент этикетки, визуальные embeddings, OCR и ранжирование; не включает внешний сетевой путь, конкурентную очередь или загрузку модели.",
             "CPU: AMD EPYC 75F3 на общем RunPod-хосте RTX 4090, OMP_NUM_THREADS=4, OCR=2 потока, device=cpu. Это не измерение отдельной 4-vCPU VPS. GPU-прогоны использовали тот же тип GPU, но были записаны ранее; точное совпадение байтов изображений подтверждено SHA.",
             "p95 CPU основан максимум на 23 тёплых запросах, а поднабор «полный» меньше при раннем выходе. p99, нагрузочная пропускная способность и SLA для одновременных клиентов не измерялись.",
             "Манифест исходных 24 фото: SHA-256 " + MANIFEST_SHA + ". Стоимость экспериментального RunPod: $0.74/час; это цена аренды во время опыта, а не расчёт себестоимости запроса или постоянного сервиса.",
         ]},
        {"id": "latency-interpretation", "title": "Почему различается время и что означает старый замер", "status": "ready" if len(stage_rows) == len(MODELS) else "partial",
         "summary": "CPU-время зависит от конкретной ветви детекции этикетки. У YOLO26n + OWLv2 и RT-DETR + OWLv2 именно её проход занимает несколько секунд; у геометрической ветви такого прохода нет. Это объяснение задержки, но не выбор модели по качеству.",
         "tables": [
             table("Медианы стадий внутри сервера на CPU, секунды",
                   [("model", "Детектор"), ("detect", "Цель"), ("class", "Проверка вина"),
                    ("label", "Этикетка"), ("ocr", "OCR")], stage_rows,
                   "Медианы стадий рассчитаны по общей тёплой серии, включая ранние выходы. Медианы отдельных стадий не складываются в медиану полного запроса."),
             table("Предыдущий опыт OWLv2: отдельные хосты и версии",
                   [("run", "Хост / версия"), ("images", "Фото"), ("warm_n", "Warm"),
                    ("p50", "p50, с"), ("p95", "p95, с"), ("cold", "Загрузка, с"), ("first", "Первый, с")], historical,
                   "RTX 4000 Ada — другой хост. Старый CPU-20 выполнен на EPYC 7352 с OWLv2 v1 и OCR=4; его нельзя приравнивать к новому CPU-24 на EPYC 75F3 с v2 и OCR=2."),
         ],
         "notes": [
             "Для вывода о внедрении нужны вместе качество на подтверждённых реальных фото, поведение на отказах, лицензия, стоимость и замеры при ожидаемой конкурентной нагрузке. Минимальная задержка одного запроса сама по себе не определяет победителя.",
             "Старые OWLv2 GPU v2-серии — отдельные последовательные бенчмарки по 24 фото; старый CPU v1 охватил первые 20. Они показаны как контекст и не смешаны со свежими сериями CPU-24.",
         ]},
    ]
    output = {"sections": sections}
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(output, ensure_ascii=False, indent=2) + "\n")
    qa_path = args.root / "detectors/timing-audit.json"
    qa_path.write_text(json.dumps(audit, ensure_ascii=False, indent=2) + "\n")
    print(json.dumps({"status": sections[0]["status"], "cpu_runs": cpu_count,
                      "gpu_subsets": len(gpu_rows), "public": str(args.out), "qa": str(qa_path)}))


if __name__ == "__main__":
    main()
