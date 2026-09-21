MINIO_URL = "http://localhost:9000/remains"
CURRENT_USER_ID = 999

icons = {
    "carbon": f"{MINIO_URL}/flask.png",
    "analysis_time": f"{MINIO_URL}/watch.png",
    "folder": f"{MINIO_URL}/folder.png.webp",
}

remains = [
    {
        "id": 1,
        "status": "published",
        "title": "Уголь",
        "description": (
            "AMS-анализ древесины, угля и растительных остатков "
            "из археологического слоя. Перед измерением уголь отделяют от грунта "
            "и очищают от загрязнений, которые могут повлиять на датировку."
        ),
        "analysis_time_days": 14,
        "carbon_14_pmc": 1.385,
        "carbon_14_sample": "OxA X-2698-45, Castelcivita",
        "carbon_14_source": "https://doi.org/10.1038/s41467-024-51546-9",
        "image": f"{MINIO_URL}/charcoal.png",
        "video": f"{MINIO_URL}/charcoal-video.mov",
        "likes": [
            {"user_id": 1},
            {"user_id": 2},
            {"user_id": 3},
            {"user_id": 4},
            {"user_id": 5},
            {"user_id": 6},
            {"user_id": 7},
            {"user_id": 8},
            {"user_id": 9},
            {"user_id": 10},
            {"user_id": 11},
            {"user_id": 12},
        ],
    },
    {
        "id": 2,
        "status": "published",
        "title": "Кости",
        "description": (
            "Датирование костной ткани по сохраненному коллагену "
            "с контролем качества образца. Лаборатория выделяет коллаген из необожжённой "
            "кости и при достаточном количестве материала дополнительно определяет δ13C и δ15N."
        ),
        "analysis_time_days": 14,
        "carbon_14_pmc": 34.45,
        "carbon_14_sample": "VIRI I, KIA 30536",
        "carbon_14_source": "https://doi.org/10.13140/RG.2.1.4201.6248",
        "image": f"{MINIO_URL}/bones.jpg",
        "video": f"{MINIO_URL}/bones-video.mov",
        "likes": [
            {"user_id": 1},
            {"user_id": 2},
            {"user_id": 3},
            {"user_id": 4},
            {"user_id": 5},
            {"user_id": 6},
            {"user_id": 7},
            {"user_id": 8},
            {"user_id": 9},
            {"user_id": 10},
            {"user_id": 11},
            {"user_id": 12},
            {"user_id": 13},
            {"user_id": 14},
            {"user_id": 15},
            {"user_id": 16},
            {"user_id": 17},
            {"user_id": 18},
            {"user_id": 19},
            {"user_id": 20},
            {"user_id": 21},
            {"user_id": 22},
            {"user_id": 23},
        ],
    },
    {
        "id": 3,
        "status": "published",
        "title": "Ракушки",
        "description": (
            "AMS-датирование раковин и других карбонатных образцов после очистки поверхности. "
            "При интерпретации морских образцов учитывают место сбора и резервуарный эффект, "
            "а при достаточной массе дополнительно измеряют δ13C и δ18O."
        ),
        "analysis_time_days": 14,
        "carbon_14_pmc": 73.338,
        "carbon_14_sample": "VIRI R, Murex shell",
        "carbon_14_source": "https://www.geochronometria.com/pdf-184439-105187?filename=Set-up--optimization-and-.pdf",
        "image": f"{MINIO_URL}/shells.jpg",
        "video": f"{MINIO_URL}/shells-video.mov",
        "likes": [
            {"user_id": 1},
            {"user_id": 2},
            {"user_id": 3},
            {"user_id": 4},
            {"user_id": 5},
            {"user_id": 6},
            {"user_id": 7},
            {"user_id": 8},
            {"user_id": 9},
            {"user_id": 10},
            {"user_id": 11},
            {"user_id": 12},
            {"user_id": 13},
            {"user_id": 14},
            {"user_id": 15},
            {"user_id": 16},
            {"user_id": 17},
            {"user_id": 18},
            {"user_id": 19},
            {"user_id": 20},
            {"user_id": 21},
            {"user_id": 22},
            {"user_id": 23},
            {"user_id": 24},
            {"user_id": 25},
            {"user_id": 26},
            {"user_id": 27},
            {"user_id": 28},
            {"user_id": 29},
            {"user_id": 30},
        ],
    },
    {
        "id": 4,
        "status": "draft",
        "title": "Дерево",
        "description": (
            "Радиоуглеродное датирование древесины после очистки от посторонних веществ. "
            "Для образцов с выделением целлюлозы требуется 50-100 мг материала, "
            "а обработанную консервантами древесину заранее согласуют с лабораторией."
        ),
        "analysis_time_days": 14,
        "carbon_14_pmc": 23.05,
        "carbon_14_sample": "IAEA-C5, Two Creeks Wood",
        "carbon_14_source": "https://analytical-reference-materials.iaea.org/iaea-c-5",
        "image": f"{MINIO_URL}/wood.jpg",
        "video": f"{MINIO_URL}/wood-video.mp4",
        "likes": [],
    },
    {
        "id": 5,
        "status": "deleted",
        "title": "Торф",
        "description": (
            "Радиоуглеродное датирование торфа по органическим фракциям. "
            "Перед анализом выбирают растительные остатки или мелкодисперсную фракцию "
            "с учётом исследовательской задачи и возможной примеси гуминовых веществ."
        ),
        "analysis_time_days": 14,
        "carbon_14_pmc": 24.85,
        "carbon_14_sample": "FIRI M, KIA 11818",
        "carbon_14_source": "https://doi.org/10.13140/RG.2.1.4201.6248",
        "image": f"{MINIO_URL}/charcoal.png",
        "video": f"{MINIO_URL}/charcoal-video.mov",
        "likes": [],
    },
]
