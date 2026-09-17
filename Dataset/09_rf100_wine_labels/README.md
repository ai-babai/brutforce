# 09 — RF100 Wine Labels

Вспомогательный object-detection набор из 4 643 изображений и 13 объявленных классов
элементов этикетки: maker, country, region/appellation, vintage, alcohol,
sweetness, type, logo и другие. Полезен для crop/OCR/attribute extraction, но
не обучает exact SKU российского каталога.

Статус: скачан, безопасно распакован и проаудирован. Все изображения
декодируются, все 25 034 bbox валидны и имеют class label; один кадр — явный
negative без боксов. Тридцать три same-dHash cross-split группы ждут review.
Заявленная лицензия — CC BY 4.0.
