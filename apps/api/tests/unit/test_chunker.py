from app.services.ingestion.chunker import PageText, chunk_pages, count_tokens, is_heading
from app.services.ingestion.extract import clean_block

PARA = (
    "Las mascotas deberán circular con correa en las zonas comunes y el tenedor debe recoger "
    "los excrementos de inmediato, so pena de multa conforme al reglamento de propiedad horizontal."
)


def _pages() -> list[PageText]:
    return [
        PageText(1, ["CAPÍTULO I - DISPOSICIONES GENERALES", PARA, PARA]),
        PageText(2, [PARA, "CAPÍTULO II - MASCOTAS", PARA, PARA]),
        PageText(3, [PARA, PARA]),
    ]


def test_respeta_el_limite_de_tokens() -> None:
    chunks = chunk_pages(_pages(), max_tokens=120, overlap_tokens=30)
    assert len(chunks) > 1
    assert all(c.token_count <= 120 for c in chunks)


def test_conserva_rango_de_paginas_para_las_citas() -> None:
    chunks = chunk_pages(_pages(), max_tokens=120, overlap_tokens=60)
    assert chunks[0].page_number == 1
    assert chunks[-1].page_end == 3
    assert all(c.page_end >= c.page_number for c in chunks)
    # Hay al menos un chunk que cruza de una página a otra
    assert any(c.page_end > c.page_number for c in chunks)


def test_indices_consecutivos() -> None:
    chunks = chunk_pages(_pages(), max_tokens=120, overlap_tokens=30)
    assert [c.index for c in chunks] == list(range(len(chunks)))


def test_asigna_la_seccion_vigente() -> None:
    chunks = chunk_pages(_pages(), max_tokens=120, overlap_tokens=30)
    assert chunks[0].section_title == "CAPÍTULO I - DISPOSICIONES GENERALES"
    assert chunks[-1].section_title == "CAPÍTULO II - MASCOTAS"


def test_solapamiento_entre_chunks_consecutivos() -> None:
    chunks = chunk_pages(_pages(), max_tokens=120, overlap_tokens=60)
    a, b = chunks[0], chunks[1]
    assert a.content.split("\n\n")[-1] == b.content.split("\n\n")[0]


def test_corta_en_cambio_de_seccion_aunque_quepa_en_el_limite() -> None:
    pages = [
        PageText(1, ["CAPÍTULO I - GENERALIDADES", PARA]),
        PageText(2, ["CAPÍTULO II - MASCOTAS", PARA]),
        PageText(3, ["CAPÍTULO III - RUIDO", PARA]),
    ]
    chunks = chunk_pages(pages, max_tokens=600, overlap_tokens=80)
    assert [(c.page_number, c.page_end) for c in chunks] == [(1, 1), (2, 2), (3, 3)]
    assert [c.section_title for c in chunks] == [
        "CAPÍTULO I - GENERALIDADES",
        "CAPÍTULO II - MASCOTAS",
        "CAPÍTULO III - RUIDO",
    ]


def test_no_corta_si_la_seccion_anterior_es_muy_corta() -> None:
    # Título del documento seguido inmediatamente de un capítulo: no se crea un
    # chunk con solo el título
    pages = [PageText(1, ["MANUAL DE CONVIVENCIA", "CAPÍTULO I - GENERALIDADES", PARA])]
    chunks = chunk_pages(pages, max_tokens=600, overlap_tokens=80)
    assert len(chunks) == 1


def test_divide_parrafos_mas_largos_que_el_limite() -> None:
    giant = " ".join([PARA] * 15)
    chunks = chunk_pages([PageText(1, [giant])], max_tokens=100, overlap_tokens=10)
    assert len(chunks) >= count_tokens(giant) // 100
    assert all(c.token_count <= 100 for c in chunks)


def test_documento_vacio_no_genera_chunks() -> None:
    assert chunk_pages([PageText(1, [])]) == []


def test_detecta_encabezados() -> None:
    assert is_heading("CAPÍTULO III - USO DE LA PISCINA")
    assert is_heading("MANUAL DE CONVIVENCIA")
    assert not is_heading("Artículo 15. El horario de la piscina es de martes a domingo.")


def test_limpieza_de_bloques() -> None:
    assert clean_block("el manteni-\nmiento de\n  ascensores\x00") == "el mantenimiento de ascensores"
