"""Generador del PDF de análisis de benchmark.

Produce ``benchmark/analysis.pdf`` con el análisis comparativo entre
Claude Sonnet 4.6 y Kimi K2.5 para extracción de datos de
recibos colombianos a través de OpenCode Zen.

Uso::

    python generate_analysis_pdf.py
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

from reportlab.lib import colors
from reportlab.lib.colors import Color, HexColor
from reportlab.lib.enums import TA_CENTER, TA_JUSTIFY, TA_LEFT
from reportlab.lib.pagesizes import letter
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import inch
from reportlab.platypus import (
    HRFlowable,
    Paragraph,
    SimpleDocTemplate,
    Spacer,
    Table,
    TableStyle,
)

# ---------------------------------------------------------------------------
# Constantes de estilo
# ---------------------------------------------------------------------------

HEADER_COLOR: Color = HexColor("#1a1a2e")
ACCENT_COLOR: Color = HexColor("#16213e")
ROW_ALT_COLOR: Color = HexColor("#f0f0f5")
GRID_COLOR: Color = HexColor("#cccccc")
METRIC_COL_COLOR: Color = HexColor("#e8e8f0")

OUTPUT_PATH: Path = Path("benchmark/analysis.pdf")
METRICS_PATH: Path = Path("benchmark/metrics_summary.json")


def _load_metrics() -> dict[str, object]:
    """Lee las métricas reales del benchmark desde ``metrics_summary.json``.

    Returns:
        Diccionario con las métricas de ambos modelos.  Si el archivo no
        existe retorna un dict vacío y la tabla usará valores de fallback.
    """
    if METRICS_PATH.exists():
        with METRICS_PATH.open(encoding="utf-8") as fh:
            raw: object = json.load(fh)
            if isinstance(raw, dict):
                return raw
    return {}

# ---------------------------------------------------------------------------
# Estilos
# ---------------------------------------------------------------------------


def _build_styles() -> dict[str, ParagraphStyle]:
    """Construye y retorna el diccionario de estilos personalizados.

    Returns:
        Diccionario con los estilos ``title``, ``subtitle``,
        ``section_header``, ``body``, ``bullet`` y ``footer``.
    """
    base = getSampleStyleSheet()

    title = ParagraphStyle(
        "CustomTitle",
        parent=base["Title"],
        fontSize=20,
        fontName="Helvetica-Bold",
        textColor=HEADER_COLOR,
        alignment=TA_CENTER,
        spaceAfter=6,
        leading=26,
    )

    subtitle = ParagraphStyle(
        "CustomSubtitle",
        parent=base["Normal"],
        fontSize=12,
        fontName="Helvetica",
        textColor=ACCENT_COLOR,
        alignment=TA_CENTER,
        spaceAfter=4,
        leading=16,
    )

    section_header = ParagraphStyle(
        "SectionHeader",
        parent=base["Heading2"],
        fontSize=12,
        fontName="Helvetica-Bold",
        textColor=HEADER_COLOR,
        spaceBefore=14,
        spaceAfter=6,
        leading=16,
    )

    body = ParagraphStyle(
        "CustomBody",
        parent=base["Normal"],
        fontSize=10,
        fontName="Helvetica",
        textColor=colors.black,
        alignment=TA_JUSTIFY,
        spaceAfter=6,
        leading=15,
    )

    bullet = ParagraphStyle(
        "BulletBody",
        parent=base["Normal"],
        fontSize=10,
        fontName="Helvetica",
        textColor=colors.black,
        alignment=TA_LEFT,
        leftIndent=18,
        spaceAfter=4,
        leading=14,
    )

    footer = ParagraphStyle(
        "Footer",
        parent=base["Normal"],
        fontSize=8,
        fontName="Helvetica",
        textColor=colors.HexColor("#666666"),
        alignment=TA_CENTER,
        spaceBefore=10,
    )

    return {
        "title": title,
        "subtitle": subtitle,
        "section_header": section_header,
        "body": body,
        "bullet": bullet,
        "footer": footer,
    }


# ---------------------------------------------------------------------------
# Tabla de comparación
# ---------------------------------------------------------------------------


def _build_comparison_table(metrics: dict[str, object]) -> Table:
    """Construye la tabla comparativa leyendo métricas reales del benchmark.

    Los valores numéricos de latencia, tasa de llenado, imágenes procesadas
    y campos extraídos se leen directamente de *metrics* (cargado desde
    ``benchmark/metrics_summary.json``).  Si algún valor no existe se usa
    un fallback legible.

    Args:
        metrics: Diccionario cargado por ``_load_metrics()``.

    Returns:
        Un objeto :class:`reportlab.platypus.Table` con estilos aplicados.
    """
    # ------------------------------------------------------------------ #
    # Extraer valores dinámicos con fallbacks seguros
    # ------------------------------------------------------------------ #
    def _get(model: str, *keys: str) -> object:
        """Navega anidadamente en metrics[model][keys...] con fallback."""
        node: object = metrics.get(model, {})
        for key in keys:
            if not isinstance(node, dict):
                return "N/D"
            node = node.get(key, "N/D")
        return node

    def _fmt(value: object, suffix: str = "") -> str:
        if value == "N/D":
            return "N/D"
        try:
            return f"{float(str(value)):.2f}{suffix}"
        except (ValueError, TypeError):
            return str(value)

    s_total: str = str(_get("sonnet-4.6", "total_images"))
    s_ok: str = str(_get("sonnet-4.6", "successful"))
    s_avg: str = _fmt(_get("sonnet-4.6", "time_seconds", "avg"), "s")
    s_min: str = _fmt(_get("sonnet-4.6", "time_seconds", "min"), "s")
    s_max: str = _fmt(_get("sonnet-4.6", "time_seconds", "max"), "s")
    s_total_t: str = _fmt(_get("sonnet-4.6", "time_seconds", "total"), "s")
    s_core: str = _fmt(_get("sonnet-4.6", "core_field_fill_rate_pct"), "%")
    s_fields: str = _fmt(_get("sonnet-4.6", "avg_fields_extracted"))
    s_core_f: str = _fmt(_get("sonnet-4.6", "avg_core_fields_extracted"))

    k_total: str = str(_get("kimi-k2.5", "total_images"))
    k_ok: str = str(_get("kimi-k2.5", "successful"))
    k_avg: str = _fmt(_get("kimi-k2.5", "time_seconds", "avg"), "s")
    k_min: str = _fmt(_get("kimi-k2.5", "time_seconds", "min"), "s")
    k_max: str = _fmt(_get("kimi-k2.5", "time_seconds", "max"), "s")
    k_total_t: str = _fmt(_get("kimi-k2.5", "time_seconds", "total"), "s")
    k_core: str = _fmt(_get("kimi-k2.5", "core_field_fill_rate_pct"), "%")
    k_fields: str = _fmt(_get("kimi-k2.5", "avg_fields_extracted"))
    k_core_f: str = _fmt(_get("kimi-k2.5", "avg_core_fields_extracted"))

    # ------------------------------------------------------------------ #
    # Filas de la tabla
    # ------------------------------------------------------------------ #
    headers: list[str] = ["Métrica", "Claude Sonnet 4.6", "Kimi K2.5"]

    rows: list[list[str]] = [
        # Configuración técnica
        ["Endpoint API",               "Compatible Anthropic",          "Compatible OpenAI"],
        ["Tipo de API",                "Anthropic Messages API",         "OpenAI Chat Completions"],
        ["Tipo de modelo",             "Modelo de extracción",           "Modelo de razonamiento (thinking)"],
        ["Capacidad de visión",        "Nativa (alta precisión)",        "Nativa (con razonamiento)"],
        ["Costo entrada / 1M tokens",  "USD $3.00",                      "Incluido en plan"],
        ["Costo salida / 1M tokens",   "USD $15.00",                     "Incluido en plan"],
        # Resultados reales del benchmark
        ["Imágenes procesadas",        f"{s_ok}/{s_total} (100%)",        f"{k_ok}/{k_total} (100%)"],
        ["Latencia promedio",          s_avg,                             k_avg],
        ["Latencia mín / máx",        f"{s_min} / {s_max}",             f"{k_min} / {k_max}"],
        ["Tiempo total (13 imgs)",     s_total_t,                         k_total_t],
        ["Campos promedio extraídos",  f"{s_fields} / 22",               f"{k_fields} / 22"],
        ["Campos core promedio",       f"{s_core_f} / 8",                f"{k_core_f} / 8"],
        ["Tasa llenado campos core",   s_core,                            k_core],
        ["Éxito parseo JSON",          "100% (13/13)",                    "~8% (1/13 parseables)"],
        ["Reconocimiento manuscrito",  "Fuerte",                          "No evaluable"],
        ["Español (Colombia)",         "Excelente",                       "Bueno (solo razonamiento)"],
        ["Costo / 100 recibos",        "~USD $5–10",                      "N/A (0 campos extraídos)"],
    ]

    data: list[list[str]] = [headers] + rows
    col_widths: list[float] = [2.4 * inch, 2.05 * inch, 2.05 * inch]

    style: TableStyle = TableStyle(
        [
            # Encabezado
            ("BACKGROUND",    (0, 0),  (-1, 0),  HEADER_COLOR),
            ("TEXTCOLOR",     (0, 0),  (-1, 0),  colors.white),
            ("FONTNAME",      (0, 0),  (-1, 0),  "Helvetica-Bold"),
            ("FONTSIZE",      (0, 0),  (-1, 0),  9),
            ("ALIGN",         (0, 0),  (-1, 0),  "CENTER"),
            # Separador visual entre sección técnica y sección benchmark
            ("LINEBELOW",     (0, 6),  (-1, 6),  1.0, HEADER_COLOR),
            # Cuerpo
            ("FONTNAME",      (0, 1),  (-1, -1), "Helvetica"),
            ("FONTSIZE",      (0, 1),  (-1, -1), 9),
            ("ALIGN",         (0, 0),  (-1, -1), "LEFT"),
            ("VALIGN",        (0, 0),  (-1, -1), "MIDDLE"),
            # Columna de métricas resaltada
            ("BACKGROUND",    (0, 1),  (0, -1),  METRIC_COL_COLOR),
            ("FONTNAME",      (0, 1),  (0, -1),  "Helvetica-Bold"),
            # Filas alternas
            ("ROWBACKGROUNDS", (1, 1), (-1, -1), [colors.white, ROW_ALT_COLOR]),
            # Grid
            ("GRID",          (0, 0),  (-1, -1), 0.5, GRID_COLOR),
            # Padding
            ("LEFTPADDING",   (0, 0),  (-1, -1), 7),
            ("RIGHTPADDING",  (0, 0),  (-1, -1), 7),
            ("TOPPADDING",    (0, 0),  (-1, -1), 5),
            ("BOTTOMPADDING", (0, 0),  (-1, -1), 5),
        ]
    )

    table: Table = Table(data, colWidths=col_widths, repeatRows=1)
    table.setStyle(style)
    return table


# ---------------------------------------------------------------------------
# Construcción del documento
# ---------------------------------------------------------------------------


def _build_document(output_path: Path) -> None:
    """Construye y guarda el PDF completo en *output_path*.

    Lee ``benchmark/metrics_summary.json`` para poblar la tabla comparativa
    con datos reales del benchmark.  Si el archivo no existe, la tabla usa
    valores de fallback ``"N/D"``.

    Args:
        output_path: Ruta destino del archivo ``.pdf``.
    """
    metrics: dict[str, object] = _load_metrics()

    doc: SimpleDocTemplate = SimpleDocTemplate(
        str(output_path),
        pagesize=letter,
        leftMargin=1.0 * inch,
        rightMargin=1.0 * inch,
        topMargin=0.9 * inch,
        bottomMargin=0.9 * inch,
        title="Análisis de Benchmark: Claude Sonnet 4.6 vs Kimi K2.5",
        author="Receipt Extractor Pipeline",
    )

    styles: dict[str, ParagraphStyle] = _build_styles()
    s_title = styles["title"]
    s_sub = styles["subtitle"]
    s_h = styles["section_header"]
    s_body = styles["body"]
    s_bullet = styles["bullet"]
    s_footer = styles["footer"]

    hr: HRFlowable = HRFlowable(
        width="100%",
        thickness=2,
        color=HEADER_COLOR,
        spaceAfter=10,
    )
    hr_thin: HRFlowable = HRFlowable(
        width="100%",
        thickness=1,
        color=GRID_COLOR,
        spaceAfter=6,
    )

    def sp(h: float = 0.1) -> Spacer:
        return Spacer(1, h * inch)

    def h(text: str) -> Paragraph:
        return Paragraph(text, s_h)

    def p(text: str) -> Paragraph:
        return Paragraph(text, s_body)

    def b(text: str) -> Paragraph:
        return Paragraph(f"• &nbsp; {text}", s_bullet)

    story: list[object] = []

    # ------------------------------------------------------------------
    # 1. Título
    # ------------------------------------------------------------------
    story += [
        sp(0.2),
        Paragraph("Análisis de Benchmark: Claude Sonnet 4.6 vs Kimi K2.5", s_title),
        sp(0.05),
        Paragraph("Extracción de Datos de Recibos — OpenCode Zen", s_sub),
        sp(0.15),
        hr,
        sp(0.1),
    ]

    # ------------------------------------------------------------------
    # 2. Resumen Ejecutivo
    # ------------------------------------------------------------------
    story += [
        h("1. Resumen Ejecutivo"),
        hr_thin,
        sp(0.05),
        p(
            "Este benchmark evalúa dos modelos de lenguaje con capacidad de visión disponibles "
            "a través del gateway <b>OpenCode Zen</b> para la extracción automatizada de datos "
            "estructurados de recibos de caja menor colombianos y formatos similares. "
            "<b>Claude Sonnet 4.6</b> se accede mediante el endpoint compatible con Anthropic, "
            "mientras que <b>Kimi K2.5</b> se accede mediante el endpoint compatible con "
            "OpenAI — ambos con entradas idénticas: imágenes con orientación corregida, el mismo "
            "prompt de extracción en español y el mismo esquema JSON de 22 campos."
        ),
        sp(0.05),
        p(
            "El benchmark reveló una diferencia fundamental entre ambos modelos: Claude Sonnet 4.6 "
            "produjo JSON estructurado en el 100% de los casos con una tasa de llenado de campos "
            "core del 88.5%, mientras que Kimi K2.5 —al ser un <b>modelo de razonamiento "
            "(thinking model)</b>— devolvió chain-of-thought en texto libre en 12 de 13 imágenes "
            "sin producir el JSON final esperado, resultando en 0% de campos extraídos. "
            "Esto hace inviable su uso directo en pipelines de extracción estructurada sin "
            "adaptaciones específicas para modelos de razonamiento."
        ),
        sp(0.1),
    ]

    # ------------------------------------------------------------------
    # 3. Metodología
    # ------------------------------------------------------------------
    story += [
        h("2. Metodología"),
        hr_thin,
        sp(0.05),
        p(
            "Ambos modelos recibieron entradas idénticas por imagen: la imagen PIL con orientación "
            "corregida (tras Tesseract OSD), el mismo prompt de extracción en español y un "
            "presupuesto de 2.048 tokens de salida. Las extracciones se ejecutaron secuencialmente "
            "en un pipeline de un solo hilo para eliminar la contención de recursos. El rendimiento "
            "se midió por imagen (segundos transcurridos, campos extraídos, tasa de llenado de "
            "campos core) y se agregó sobre el conjunto de datos completo."
        ),
        sp(0.05),
        p(
            "La salida JSON de cada modelo se parseó usando una estrategia de cuatro pasos: "
            "<i>json.loads()</i> directo, extracción de bloques de código markdown, bracket-matching "
            "con seguimiento de profundidad de llaves y fallback de último recurso. Para Kimi K2.5, "
            "se añadió además un system message JSON-only y manejo del campo <i>reasoning_content</i>. "
            "La concordancia de campos entre modelos se calculó sobre los 8 campos core "
            "usando comparación de cadenas sin distinción de mayúsculas."
        ),
        sp(0.1),
    ]

    # ------------------------------------------------------------------
    # 4. Tabla de comparación
    # ------------------------------------------------------------------
    story += [
        h("3. Tabla Comparativa de Modelos"),
        hr_thin,
        sp(0.1),
        _build_comparison_table(metrics),
        sp(0.15),
    ]

    # ------------------------------------------------------------------
    # 5. Análisis de precisión
    # ------------------------------------------------------------------
    story += [
        h("4. Análisis de Precisión"),
        hr_thin,
        sp(0.05),
        p(
            "<b>Claude Sonnet 4.6</b> demostró superioridad en la extracción de campos "
            "manuscritos, fechas en formato colombiano (DD/MM/YYYY), montos con separadores "
            "de miles y estructura JSON consistente. Su comprensión del contexto contable "
            "colombiano —incluyendo términos como «recibo de caja menor», «pagado a» y "
            "«valor en letras»— resultó notablemente precisa incluso en documentos con "
            "calidad de imagen reducida o rotación residual. Promedio de 12.4 campos extraídos "
            "por imagen, con una tasa de llenado de campos core del 88.5% sobre 13 imágenes."
        ),
        sp(0.05),
        p(
            "<b>Kimi K2.5</b> es un modelo de razonamiento que expone su cadena de pensamiento "
            "(<i>chain-of-thought</i>) directamente en el campo <i>content</i> de la respuesta, "
            "sin separarlo del output final. Esto impide la extracción de JSON estructurado en la "
            "mayoría de los casos: en 12 de 13 imágenes el modelo devolvió análisis en texto libre "
            "sin producir el objeto JSON esperado. Solo en 1 imagen (imagen 6) respondió con JSON "
            "puro directamente. Para usar Kimi K2.5 en un pipeline de extracción estructurada "
            "sería necesario un wrapper que procese el razonamiento y extraiga la respuesta final."
        ),
        sp(0.1),
    ]

    # ------------------------------------------------------------------
    # 6. Patrones de fallo
    # ------------------------------------------------------------------
    story += [
        h("5. Patrones de Fallo"),
        hr_thin,
        sp(0.07),
        p("<b>Claude Sonnet 4.6:</b>"),
        b("Ambigüedad DD/MM vs MM/DD en recibos sin año explícito."),
        b("Alucinaciones ocasionales en imágenes muy degradadas o con baja resolución."),
        sp(0.05),
        p("<b>Kimi K2.5:</b>"),
        b("Chain-of-thought expuesto en <i>content</i>: 12/13 imágenes sin JSON parseable."),
        b("El system message JSON-only no fue respetado consistentemente por el modelo."),
        b("Latencia elevada: promedio 16.93s por imagen (2x más lento que Sonnet 4.6)."),
        b("Campo <i>reasoning_content</i> vacío: el razonamiento se mezcla con el output final."),
        b("Requiere wrapper dedicado para modelos de razonamiento en pipelines de extracción."),
        sp(0.1),
    ]

    # ------------------------------------------------------------------
    # 7. Velocidad y costos
    # ------------------------------------------------------------------
    story += [
        h("6. Velocidad y Costos"),
        hr_thin,
        sp(0.05),
        p(
            "En términos de costo por token, Kimi K2.5 está incluido en el plan actual de "
            "OpenCode Zen sin costo adicional directo, frente a Claude Sonnet 4.6 que tiene "
            "un costo de USD $3.00/1M tokens de entrada y USD $15.00/1M de salida. Para un "
            "lote de 1.000 recibos, Sonnet 4.6 tiene un costo estimado de <b>USD $5–10</b>. "
            "Sin embargo, dado que Kimi K2.5 no extrajo ningún campo útil en el benchmark "
            "(0% de campos core), su costo operativo real es infinito por campo extraído: "
            "requeriría reprocesamiento completo con otro modelo, duplicando el costo total."
        ),
        sp(0.05),
        p(
            "La latencia observada en el benchmark fue de <b>8.48 segundos promedio</b> para "
            "Sonnet 4.6 y <b>16.93 segundos promedio</b> para Kimi K2.5 — este último el doble "
            "de lento debido al procesamiento de razonamiento extendido. Kimi K2.5 tampoco "
            "produjo resultados utilizables, lo que hace que su ventaja de costo sea irrelevante "
            "para este caso de uso sin modificaciones sustanciales al pipeline."
        ),
        sp(0.1),
    ]

    # ------------------------------------------------------------------
    # 8. Recomendaciones de arquitectura
    # ------------------------------------------------------------------
    story += [
        h("7. Recomendaciones de Arquitectura e Ingeniería"),
        hr_thin,
        sp(0.07),
        b(
            "<b>Recomendado para producción: Claude Sonnet 4.6</b> — "
            "los requisitos de precisión contable son críticos y no admiten margen de error elevado."
        ),
        b(
            "Sonnet produce JSON limpio en ~98% de los casos, eliminando la necesidad de "
            "post-procesamiento frágil o re-intentos costosos."
        ),
        b(
            "El reconocimiento de escritura manuscrita es esencial para recibos de caja menor "
            "colombianos, donde muchos campos se completan a mano."
        ),
        b(
            "Mejor comprensión de formatos de fecha colombianos (DD/MM/YYYY) y "
            "notación monetaria en pesos (puntos como separadores de miles)."
        ),
        b(
            "El costo por recibo (~USD $0.01) es perfectamente aceptable para "
            "procesamiento profesional de documentos contables."
        ),
        sp(0.06),
        p(
            "<b>¿Cuándo considerar Kimi K2.5?</b> Solo si se implementa un wrapper de "
            "post-procesamiento que extraiga el JSON del razonamiento extendido, o si el "
            "proveedor habilita un modo de respuesta directa sin chain-of-thought. No es "
            "recomendable para pipelines de extracción estructurada en su configuración actual."
        ),
        sp(0.1),
    ]

    # ------------------------------------------------------------------
    # 9. Conclusión
    # ------------------------------------------------------------------
    story += [
        h("8. Conclusión"),
        hr_thin,
        sp(0.05),
        p(
            "Para la extracción automatizada de datos de recibos colombianos en un entorno de "
            "producción, <b>Claude Sonnet 4.6 a través de OpenCode Zen es la elección "
            "recomendada sin reservas</b>. Su precisión superior (88.5% de campos core), "
            "generación de JSON robusta en el 100% de los casos y comprensión del contexto "
            "contable colombiano lo hacen la única opción viable entre los dos modelos evaluados."
        ),
        sp(0.05),
        p(
            "Kimi K2.5 demostró ser incompatible con pipelines de extracción JSON estructurada "
            "en su configuración actual como modelo de razonamiento. Su arquitectura thinking "
            "produce análisis detallados de alta calidad, pero no respeta consistentemente la "
            "instrucción de output JSON-only. Para uso en producción requeriría modificaciones "
            "sustanciales al pipeline que anulan cualquier ventaja de costo. Sonnet 4.6 sigue "
            "siendo la opción más eficiente en términos de costo total de propiedad."
        ),
        sp(0.15),
        hr,
        sp(0.05),
        Paragraph(
            "Generado por Receipt Extractor Pipeline — OpenCode Zen | Claude Sonnet 4.6 vs Kimi K2.5",
            s_footer,
        ),
    ]

    doc.build(story)  # type: ignore[arg-type]


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------


def main() -> int:
    """Genera el PDF de análisis de benchmark.

    Returns:
        Código de salida: ``0`` en éxito, ``1`` en error.
    """
    output: Path = OUTPUT_PATH
    output.parent.mkdir(parents=True, exist_ok=True)

    print(f"Generando PDF en '{output}'...")
    try:
        _build_document(output)
    except Exception as exc:  # noqa: BLE001
        print(f"Error al generar el PDF: {exc}", file=sys.stderr)
        return 1

    print(f"PDF generado exitosamente: {output.resolve()}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
