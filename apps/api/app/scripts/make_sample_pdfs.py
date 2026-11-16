"""Genera PDFs de ejemplo en samples/: python -m app.scripts.make_sample_pdfs

- manual_convivencia_demo.pdf -> texto nativo, 3 páginas, capítulos y artículos
- acta_asamblea_escaneada_demo.pdf -> SOLO imágenes (simula un escaneo) para probar OCR
"""

from pathlib import Path

import pymupdf

OUT = Path(__file__).resolve().parents[2] / "samples"

MANUAL = [
    [
        "MANUAL DE CONVIVENCIA",
        "Conjunto Residencial Los Pinos - Propiedad Horizontal (Ley 675 de 2001)",
        "CAPÍTULO I - DISPOSICIONES GENERALES",
        "Artículo 1. Objeto. El presente manual establece las normas de convivencia que deben "
        "observar los propietarios, residentes y visitantes del conjunto, con el fin de garantizar "
        "la seguridad, la tranquilidad y el buen uso de los bienes comunes.",
        "Artículo 2. Ámbito de aplicación. Las disposiciones aquí contenidas son de obligatorio "
        "cumplimiento para todas las personas que habiten o visiten el conjunto residencial.",
    ],
    [
        "CAPÍTULO II - TENENCIA DE MASCOTAS",
        "Artículo 8. Se permite la tenencia de perros y gatos siempre que el propietario los "
        "registre en la administración y presente el carné de vacunación vigente.",
        "Artículo 9. En las zonas comunes las mascotas deberán circular con correa y, en el caso "
        "de razas potencialmente peligrosas, con bozal. Los excrementos deben ser recogidos de "
        "inmediato por el tenedor. El incumplimiento acarreará una multa de medio salario mínimo "
        "diario legal vigente.",
        "CAPÍTULO III - USO DE LA PISCINA",
        "Artículo 15. El horario de la piscina es de martes a domingo de 8:00 a.m. a 8:00 p.m. Los "
        "lunes permanece cerrada por mantenimiento. Los menores de 12 años deben estar acompañados "
        "por un adulto responsable.",
    ],
    [
        "CAPÍTULO IV - RUIDO Y HORARIOS DE DESCANSO",
        "Artículo 20. Entre las 10:00 p.m. y las 7:00 a.m. de domingo a jueves, y entre la 1:00 "
        "a.m. y las 8:00 a.m. los viernes y sábados, se debe mantener un nivel de ruido que no "
        "perturbe el descanso de los vecinos.",
        "Artículo 21. Las obras o remodelaciones dentro de las unidades privadas solo podrán "
        "realizarse de lunes a viernes de 8:00 a.m. a 5:00 p.m. y los sábados de 9:00 a.m. a 1:00 "
        "p.m., previa notificación escrita a la administración.",
    ],
]

ACTA = [
    "ACTA No. 012 - ASAMBLEA GENERAL ORDINARIA DE COPROPIETARIOS",
    "Fecha: 15 de marzo de 2026. Lugar: salón comunal. Hora de inicio: 9:00 a.m.",
    "Quórum: asistieron propietarios que representan el 68,5% de los coeficientes de copropiedad.",
    "1. Aprobación de estados financieros 2025: aprobados con el 92% de los votos.",
    "2. Presupuesto 2026: se aprueba un incremento de la cuota de administración del 7%.",
    "3. Impermeabilización de la cubierta de la torre 2: se aprueba contratar a la empresa "
    "Cubiertas Andinas S.A.S. por un valor de $48.500.000. Responsable: consejo de administración. "
    "Plazo: 30 de junio de 2026.",
    "4. Póliza de áreas comunes: se renueva con Seguros Bolívar, vigente hasta el 31 de marzo de 2027.",
]


POLIZA = [
    "PÓLIZA DE SEGURO DE ÁREAS COMUNES - COPROPIEDADES",
    "Aseguradora: Seguros Bolívar S.A. - Póliza No. 1002-3345-07",
    "Tomador y asegurado: Conjunto Residencial Los Pinos - Propiedad Horizontal, NIT 900123456-1.",
    "Vigencia: desde las 00:00 horas del 1 de abril de 2026 hasta las 24:00 horas del 31 de marzo de 2027.",
    "Amparos: incendio y terremoto sobre bienes comunes, responsabilidad civil extracontractual, "
    "daños por agua y rotura de maquinaria (ascensores y equipos de bombeo).",
    "Valor asegurado: $8.450.000.000. Prima anual: $18.750.000 más IVA, pagadera en una cuota.",
    "La renovación deberá solicitarse con al menos quince (15) días de anticipación al fin de la vigencia.",
]

CONTRATO_P1 = [
    "CONTRATO DE PRESTACIÓN DE SERVICIOS DE VIGILANCIA Y SEGURIDAD PRIVADA No. CV-2026-004",
    "Entre el CONJUNTO RESIDENCIAL LOS PINOS - PROPIEDAD HORIZONTAL, representado por su administradora, "
    "y SEGURIDAD ATLAS LTDA., NIT 860.123.456-7, con licencia de la Superintendencia de Vigilancia, se "
    "celebra el presente contrato, que se regirá por las siguientes cláusulas:",
    "CLÁUSULA PRIMERA - OBJETO. El contratista prestará el servicio de vigilancia con tres (3) puestos de "
    "24 horas en portería principal, parqueaderos y zona perimetral.",
    "CLÁUSULA SEGUNDA - VALOR. El valor mensual del contrato es de $14.200.000 IVA incluido, pagadero "
    "dentro de los diez primeros días de cada mes.",
]
CONTRATO_P2 = [
    "CLÁUSULA TERCERA - PLAZO. El presente contrato tendrá una duración de doce (12) meses contados a partir "
    "del primero (1) de febrero de dos mil veintiséis (2026), es decir, hasta el 31 de enero de 2027.",
    "CLÁUSULA CUARTA - RENOVACIÓN. El contrato se renovará automáticamente por periodos iguales, salvo que "
    "alguna de las partes manifieste por escrito su intención de no renovarlo con una antelación mínima de "
    "treinta (30) días calendario a la fecha de terminación.",
    "CLÁUSULA QUINTA - GARANTÍAS. El contratista mantendrá vigente durante todo el contrato una póliza de "
    "responsabilidad civil extracontractual y de cumplimiento.",
    "Para constancia se firma en Bogotá D.C., el 20 de enero de 2026.",
]

LAVADO_TANQUES = [
    "CERTIFICADO DE LAVADO Y DESINFECCIÓN DE TANQUES DE ALMACENAMIENTO DE AGUA POTABLE",
    "Empresa: AguaLimpia Servicios Sanitarios S.A.S. - Certificado No. ALS-2026-0918",
    "Cliente: Conjunto Residencial Los Pinos. Tanques intervenidos: dos (2) subterráneos de 40 m3 y uno (1) "
    "elevado de 12 m3.",
    "Fecha del servicio: 10 de septiembre de 2026. Se realizó vaciado, limpieza mecánica, desinfección con "
    "hipoclorito y toma de muestras para análisis fisicoquímico y microbiológico.",
    "De acuerdo con la normativa sanitaria vigente, el próximo lavado deberá realizarse a más tardar el "
    "10 de marzo de 2027 (periodicidad semestral).",
]


COT_ANDINAS = [
    "CUBIERTAS ANDINAS S.A.S. - NIT 901.234.567-8",
    "COTIZACIÓN No. CA-2026-118 - Bogotá, 2 de noviembre de 2026",
    "Señores: Conjunto Residencial Los Pinos. Asunto: impermeabilización de la cubierta de la torre 2 (420 m2).",
    "Alcance: limpieza y preparación de superficie, imprimante asfáltico, manto asfáltico de 4 mm con foil de "
    "aluminio, sellado de juntas y bajantes, retiro de escombros y andamios certificados incluidos.",
    "Valor antes de IVA: $40.756.303. IVA (19%): $7.743.697. VALOR TOTAL: $48.500.000.",
    "Garantía: cinco (5) años sobre materiales y mano de obra, con visitas de revisión anuales.",
    "Plazo de ejecución: veinticinco (25) días hábiles a partir del pago del anticipo.",
    "Forma de pago: 50% de anticipo a la firma del contrato y 50% contra entrega a satisfacción.",
    "Validez de la oferta: treinta (30) días calendario.",
]

COT_IMPERTEC_P1 = [
    "IMPERTEC LTDA. - Soluciones en impermeabilización - NIT 830.555.222-1",
    "PROPUESTA COMERCIAL PC-0457 - 5 de noviembre de 2026",
    "Cliente: Conjunto Residencial Los Pinos - Cubierta torre 2.",
    "Ítem 1. Limpieza de cubierta con hidrolavadora: $2.100.000",
    "Ítem 2. Suministro e instalación de membrana líquida acrílica (420 m2): $33.950.000",
    "Ítem 3. Sellado de juntas y remates: $6.850.000",
    "Valor total de la propuesta: $42.900.000 IVA incluido.",
]
COT_IMPERTEC_P2 = [
    "CONDICIONES COMERCIALES",
    "Garantía de tres (3) años sobre la impermeabilización.",
    "Tiempo de ejecución: treinta y cinco (35) días calendario.",
    "Forma de pago: 30% de anticipo, 40% al avance del 50% de la obra y 30% a la entrega.",
    "No incluye: retiro de escombros ni alquiler de andamios, que corren por cuenta del conjunto.",
    "Oferta válida por quince (15) días.",
]

COT_TECHOS_PRO = [
    "SOLUCIONES TECHOS PRO S.A.S. - NIT 900.777.888-3",
    "Cotización TP-2026-031 - Fecha: 6 de noviembre de 2026",
    "Obra: impermeabilización cubierta torre 2, Conjunto Residencial Los Pinos.",
    "Sistema propuesto: membrana de poliurea de alta resistencia aplicada en caliente, incluye retiro de "
    "escombros y andamios.",
    "Valor de la obra: $44.700.000 más IVA del 19%.",
    "Garantía de diez (10) años sobre la membrana.",
    "Plazo: veinte (20) días hábiles.",
    "Pago: 40% de anticipo y 60% a la entrega final.",
    "Esta oferta tiene una validez de 20 días.",
]


ACTA_EXTRA_P1 = [
    "ACTA No. 013 - ASAMBLEA GENERAL EXTRAORDINARIA DE COPROPIETARIOS",
    "Conjunto Residencial Los Pinos - Propiedad Horizontal",
    "En Bogotá, el 18 de octubre de 2026, siendo las 10:00 a.m., se reunieron en el salón comunal los "
    "propietarios convocados por la administración. Se verificó la asistencia de propietarios que "
    "representan el 72,3% de los coeficientes de copropiedad, con lo cual hay quórum para deliberar y decidir.",
    "1. CAMBIO DE EMPRESA DE VIGILANCIA. La administradora presentó las quejas recibidas sobre el servicio. "
    "Sometido a votación, el cambio de empresa obtuvo 64,1% a favor, 30,2% en contra y 5,7% de abstenciones. "
    "La propuesta queda APROBADA.",
    "2. CUOTA EXTRAORDINARIA PARA REPARACIÓN DE FACHADA. Se propuso una cuota extraordinaria de $350.000 por "
    "unidad. La votación arrojó 41,5% a favor, 52,8% en contra y 5,7% de abstenciones, por lo que la "
    "propuesta es NEGADA.",
]
ACTA_EXTRA_P2 = [
    "3. MODIFICACIÓN DEL REGLAMENTO DE MASCOTAS. Se aprobó con el 78% de los votos la obligación de usar "
    "bozal para razas potencialmente peligrosas en todas las zonas comunes.",
    "COMPROMISOS",
    "La administradora presentará al consejo tres cotizaciones para la reparación de la fachada a más tardar "
    "el 30 de noviembre de 2026.",
    "El consejo de administración revisará y firmará el nuevo contrato de vigilancia antes del 15 de "
    "diciembre de 2026.",
    "La administración publicará el reglamento de mascotas actualizado en la cartelera y en el grupo de "
    "residentes dentro de los diez (10) días siguientes a esta asamblea.",
    "Siendo las 12:40 p.m. se levanta la sesión. Firman: presidente y secretaria de la asamblea.",
]


def _scanned(blocks: list[str], path: Path) -> None:
    """Dibuja el texto, lo rasteriza y guarda un PDF que solo contiene la imagen."""
    src = pymupdf.open()
    _text_page(src, blocks)
    pix = src[0].get_pixmap(dpi=200, colorspace=pymupdf.csGRAY)
    out = pymupdf.open()
    page = out.new_page(width=595, height=842)
    page.insert_image(page.rect, pixmap=pix)
    out.save(path, deflate=True)


def _text_page(doc: pymupdf.Document, blocks: list[str]) -> None:
    page = doc.new_page(width=595, height=842)  # A4
    y = 60.0
    for block in blocks:
        heading = block.isupper() or block.startswith("CAPÍTULO")
        rect = pymupdf.Rect(60, y, 535, y + 300)
        fontsize = 12 if heading else 10.5
        spare = page.insert_textbox(rect, block, fontsize=fontsize, fontname="helv", align=0)
        used = 300 - spare if spare >= 0 else 300
        y += used + 14


def main() -> None:
    OUT.mkdir(exist_ok=True)

    manual = pymupdf.open()
    for blocks in MANUAL:
        _text_page(manual, blocks)
    manual.save(OUT / "manual_convivencia_demo.pdf")

    # Documentos "escaneados": solo imagen, sin capa de texto (requieren OCR)
    _scanned(ACTA, OUT / "acta_asamblea_escaneada_demo.pdf")
    _scanned(LAVADO_TANQUES, OUT / "certificado_lavado_tanques_escaneado_demo.pdf")

    poliza = pymupdf.open()
    _text_page(poliza, POLIZA)
    poliza.save(OUT / "poliza_areas_comunes_demo.pdf")

    contrato = pymupdf.open()
    _text_page(contrato, CONTRATO_P1)
    _text_page(contrato, CONTRATO_P2)
    contrato.save(OUT / "contrato_vigilancia_demo.pdf")

    # Cotizaciones para el comparador (mismo servicio, tres proveedores)
    andinas = pymupdf.open()
    _text_page(andinas, COT_ANDINAS)
    andinas.save(OUT / "cotizacion_cubiertas_andinas_demo.pdf")
    impertec = pymupdf.open()
    _text_page(impertec, COT_IMPERTEC_P1)
    _text_page(impertec, COT_IMPERTEC_P2)
    impertec.save(OUT / "cotizacion_impertec_demo.pdf")
    _scanned(COT_TECHOS_PRO, OUT / "cotizacion_techos_pro_escaneada_demo.pdf")

    acta = pymupdf.open()
    _text_page(acta, ACTA_EXTRA_P1)
    _text_page(acta, ACTA_EXTRA_P2)
    acta.save(OUT / "acta_asamblea_extraordinaria_demo.pdf")

    print("PDFs de ejemplo en", OUT)


if __name__ == "__main__":
    main()
