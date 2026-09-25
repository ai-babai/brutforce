INSERT INTO demo_catalog (id, slug, name, winery, year, image, description, display_order) VALUES
    ('demo-cabernet-sauvignon-2023', 'demo-cabernet-sauvignon-2023', 'Каберне Совиньон', 'Демо-винодельня', 2023, '/assets/concept-bottle.png', 'Синтетическая карточка DEMO: красное сухое вино для интерфейсного прототипа.', 1),
    ('demo-merlot-2022', 'demo-merlot-2022', 'Мерло', 'Демо-винодельня', 2022, '', 'Синтетическая карточка DEMO: красное сухое вино без фотографии для интерфейсного прототипа.', 2),
    ('demo-saperavi-2021', 'demo-saperavi-2021', 'Саперави', 'Северная долина DEMO', 2021, '/assets/catalog/demo-saperavi-2021.svg', 'Синтетическая карточка DEMO: красное сухое вино для проверки списка кандидатов.', 3),
    ('demo-pinot-noir-2020', 'demo-pinot-noir-2020', 'Пино Нуар', 'Линия холмов DEMO', 2020, '/assets/catalog/demo-pinot-noir-2020.svg', 'Синтетическая карточка DEMO: красное сухое вино для проверки поиска по названию.', 4),
    ('demo-krasnostop-2022', 'demo-krasnostop-2022', 'Красностоп', 'Донские террасы DEMO', 2022, '/assets/catalog/demo-krasnostop-2022.svg', 'Синтетическая карточка DEMO: красное сухое вино для проверки поиска по винодельне.', 5),
    ('demo-shiraz-2021', 'demo-shiraz-2021', 'Шираз', 'Степной берег DEMO', 2021, '/assets/catalog/demo-shiraz-2021.svg', 'Синтетическая карточка DEMO: красное сухое вино для проверки карточки результата.', 6),
    ('demo-cabernet-franc-2019', 'demo-cabernet-franc-2019', 'Каберне Фран', 'Каменный сад DEMO', 2019, '/assets/catalog/demo-cabernet-franc-2019.svg', 'Синтетическая карточка DEMO: красное сухое вино для проверки неоднозначного поиска.', 7),
    ('demo-tsimlyansky-black-2023', 'demo-tsimlyansky-black-2023', 'Цимлянский чёрный', 'Речная долина DEMO', 2023, '/assets/catalog/demo-tsimlyansky-black-2023.svg', 'Синтетическая карточка DEMO: красное сухое вино для проверки поиска по году.', 8)
ON CONFLICT (id) DO NOTHING;

INSERT INTO catalog_versions (version) VALUES ('demo-v1') ON CONFLICT DO NOTHING;
INSERT INTO catalog_state (singleton, version) VALUES (true, 'demo-v1')
ON CONFLICT (singleton) DO NOTHING;
