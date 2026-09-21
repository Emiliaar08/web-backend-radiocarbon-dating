BEGIN;

INSERT INTO researchers (id, username, full_name)
SELECT value, 'researcher_' || value, 'Исследователь ' || value
FROM generate_series(1, 30) AS value
ON CONFLICT DO NOTHING;

INSERT INTO researchers (id, username, full_name)
VALUES (999, 'emilia', 'Эмилия')
ON CONFLICT DO NOTHING;

INSERT INTO remains (id, title, description, status, image_url, video_url, analysis_time_days, carbon_14_pmc, carbon_14_sample, carbon_14_source, creator_id, created_at, published_at)
VALUES
    (1, 'Уголь', 'AMS-анализ древесины, угля и растительных остатков из археологического слоя. Перед измерением уголь отделяют от грунта и очищают от загрязнений, которые могут повлиять на датировку.', 'published', 'http://localhost:9000/remains/charcoal.png', 'http://localhost:9000/remains/charcoal-video.mov', 14, 1.385, 'OxA X-2698-45, Castelcivita', 'https://doi.org/10.1038/s41467-024-51546-9', 999, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP),
    (2, 'Кости', 'Датирование костной ткани по сохраненному коллагену с контролем качества образца. Лаборатория выделяет коллаген из необожжённой кости и при достаточном количестве материала дополнительно определяет δ13C и δ15N.', 'published', 'http://localhost:9000/remains/bones.jpg', 'http://localhost:9000/remains/bones-video.mov', 14, 34.45, 'VIRI I, KIA 30536', 'https://doi.org/10.13140/RG.2.1.4201.6248', 999, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP),
    (3, 'Ракушки', 'AMS-датирование раковин и других карбонатных образцов после очистки поверхности. При интерпретации морских образцов учитывают место сбора и резервуарный эффект, а при достаточной массе дополнительно измеряют δ13C и δ18O.', 'published', 'http://localhost:9000/remains/shells.jpg', 'http://localhost:9000/remains/shells-video.mov', 14, 73.338, 'VIRI R, Murex shell', 'https://www.geochronometria.com/pdf-184439-105187?filename=Set-up--optimization-and-.pdf', 999, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP),
    (4, 'Дерево', 'Радиоуглеродное датирование древесины после очистки от посторонних веществ. Для образцов с выделением целлюлозы требуется 50-100 мг материала, а обработанную консервантами древесину заранее согласуют с лабораторией.', 'draft', 'http://localhost:9000/remains/wood.jpg', 'http://localhost:9000/remains/wood-video.mp4', 14, 23.05, 'IAEA-C5, Two Creeks Wood', 'https://analytical-reference-materials.iaea.org/iaea-c-5', 999, CURRENT_TIMESTAMP, NULL),
    (5, 'Торф', 'Радиоуглеродное датирование торфа по органическим фракциям. Перед анализом выбирают растительные остатки или мелкодисперсную фракцию с учётом исследовательской задачи и возможной примеси гуминовых веществ.', 'deleted', 'http://localhost:9000/remains/charcoal.png', 'http://localhost:9000/remains/charcoal-video.mov', 14, 24.85, 'FIRI M, KIA 11818', 'https://doi.org/10.13140/RG.2.1.4201.6248', 999, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)
ON CONFLICT DO NOTHING;

INSERT INTO remains_likes (researcher_id, remains_id)
SELECT value, 1 FROM generate_series(1, 12) AS value
UNION ALL
SELECT value, 2 FROM generate_series(1, 23) AS value
UNION ALL
SELECT value, 3 FROM generate_series(1, 30) AS value
ON CONFLICT DO NOTHING;

SELECT setval(pg_get_serial_sequence('researchers', 'id'), GREATEST((SELECT COALESCE(MAX(id), 1) FROM researchers), (SELECT last_value FROM researchers_id_seq)), true);
SELECT setval(pg_get_serial_sequence('remains', 'id'), GREATEST((SELECT COALESCE(MAX(id), 1) FROM remains), (SELECT last_value FROM remains_id_seq)), true);
SELECT setval(pg_get_serial_sequence('remains_likes', 'id'), GREATEST((SELECT COALESCE(MAX(id), 1) FROM remains_likes), (SELECT last_value FROM remains_likes_id_seq)), true);

COMMIT;
