# Роли команды Vino

Исполняемые профили находятся в `.codex/agents/*.toml`.

| Агент | Зона | Основной результат | Передача |
|---|---|---|---|
| `product_analyst` | требования, UX, traceability | критерии и контракт поведения | архитектору, QA |
| `data_curator` | intake, provenance, identity, splits | проверенные манифесты и аудит | retrieval, QA |
| `solution_architect` | границы, API, ADR | архитектурные инварианты | инженерам, QA |
| `retrieval_engineer` | CV, embedding, index, reranking | измеримый search candidate | application, QA |
| `application_engineer` | API, web UI, packaging | end-to-end vertical slice | QA |
| `qa_evaluator` | независимая оценка и безопасность | evidence-backed verdict | владельцам |

## Порядок

1. `data_curator` принимает и описывает данные.
2. `product_analyst` и `qa_evaluator` замораживают evaluation contract.
3. `retrieval_engineer` строит baseline без доступа к private holdout.
4. `solution_architect` фиксирует доказанные решения ADR.
5. `application_engineer` собирает пользовательский срез.
6. `qa_evaluator` независимо проверяет качество, контракт, SLA и безопасность.

Параллельные роли не редактируют один канонический файл. Исполнитель не ставит
финальный verdict собственной работе. Роль не расширяет полномочия на загрузку,
публикацию или удаление данных.
