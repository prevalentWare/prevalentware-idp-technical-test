"""Receipt data extraction module via OpenCode Zen API.

Connects to the OpenCode Zen gateway to extract structured data from receipt
images using vision-capable LLMs.  Two API flavours are supported:

* **Anthropic-compatible** — used for ``claude-sonnet-4-6``.
* **OpenAI-compatible**   — used for open-source models (kimi-k2.5).

Rotation detection and correction is handled upstream by ``orientation.py``;
this module receives already-corrected PIL images.

v2 improvements:
- ``tesseract_pre_ocr`` runs Tesseract OCR on the corrected image before the
  API call and injects the result into the prompt as a cross-validation aid.
- ``EXTRACTION_PROMPT`` includes per-field critical rules to address recurring
  OCR errors: digit/letter confusion in ``numero_recibo``, city ambiguity in
  ``ciudad``, name misreads in ``pagado_a``, concept confusion in ``concepto``,
  and hallucination prevention for ``vendedor``.
- ``_build_prompt`` injects the Tesseract text into the prompt at runtime.
- ``_call_anthropic`` and ``_call_openai_compatible`` accept the prompt as a
  parameter instead of using the global constant directly.
"""

from __future__ import annotations

import base64
import io
import json
import logging
import re
import time

import httpx
import pytesseract
from PIL import Image

# ---------------------------------------------------------------------------
# Module-level constants
# ---------------------------------------------------------------------------

ANTHROPIC_ENDPOINT: str = "https://opencode.ai/zen/v1/messages"
OPENAI_ENDPOINT: str = "https://opencode.ai/zen/v1/chat/completions"

MODELS: dict[str, dict[str, str]] = {
    "sonnet-4.6": {
        "model_id": "claude-sonnet-4-6",
        "endpoint": ANTHROPIC_ENDPOINT,
        "api_type": "anthropic",
    },
    "kimi-k2.5": {
        "model_id": "kimi-k2.5",
        "endpoint": OPENAI_ENDPOINT,
        "api_type": "openai",
    },
}

EXPECTED_FIELDS: list[str] = [
    "ciudad",
    "fecha",
    "numero_recibo",
    "pagado_a",
    "valor",
    "concepto",
    "valor_en_letras",
    "firma_recibido",
    "cc_o_nit",
    "codigo",
    "aprobado",
    "direccion",
    "vendedor",
    "telefono_fax",
    "forma_pago",
    "cantidad",
    "detalle",
    "valor_unitario",
    "valor_total",
    "total_documento",
    "tipo_documento",
    "plantilla_detectada",
]

# Pre-compiled regex to strip markdown code fences from LLM responses.
_FENCE_PATTERN: re.Pattern[str] = re.compile(r"```(?:json)?\s*|\s*```")

# Regex to extract JSON blocks inside code fences (Strategy 2 in parser).
_CODE_FENCE_PATTERN: re.Pattern[str] = re.compile(
    r"```(?:json)?\s*\n?(.*?)\n?\s*```", re.DOTALL
)

# Anchor fields used to validate candidate JSON blocks in the bracket-matching parser.
_JSON_ANCHOR_FIELDS: frozenset[str] = frozenset(
    {"ciudad", "fecha", "numero_recibo", "pagado_a", "valor", "concepto", "tipo_documento"}
)

logger: logging.Logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Extraction prompt (with {ocr_text} placeholder for Tesseract cross-check)
# ---------------------------------------------------------------------------

EXTRACTION_PROMPT: str = """Eres un experto en lectura y análisis de documentos contables colombianos, \
especialmente recibos de caja menor, cuentas de cobro, remisiones y recibos de pago.

Analiza la imagen del documento y extrae todos los campos visibles.
Devuelve ÚNICAMENTE un objeto JSON válido, sin bloques de código, sin markdown, \
sin texto adicional antes ni después del JSON.

════════════════════════════════════════
REGLAS CRÍTICAS POR CAMPO
════════════════════════════════════════

▸ NUMERO_RECIBO
  - Leer el número dígito por dígito, de izquierda a derecha. No omitir ningún dígito.
  - Son SIEMPRE dígitos numéricos (0-9), frecuentemente con ceros a la izquierda.
  - NUNCA contienen letras ni puntos. Si hay un punto en el número, eliminarlo conservando TODOS los dígitos.
    Ejemplo: "004.0" → "0040", "003.8" → "0038", "002.0" → "0020".
  - Las confusiones SOLO aplican a caracteres visualmente AMBIGUOS (no a dígitos ya reconocibles):
    0↔O↔Q↔G, 1↔l↔I, 2↔7, 5↔S, 8↔B.
  - Si un carácter es claramente un dígito (0-9), copiarlo tal cual. NO reemplazarlo por otro.
  - El resultado FINAL debe contener ÚNICAMENTE dígitos (0-9), sin ninguna letra.
    Si después de leer el número aún contiene alguna letra, reemplazarla por su dígito correspondiente.
    Ejemplo OBLIGATORIO: "G025" → "0025", "O440" → "0440", "l038" → "1038".
  - Apoyarse SIEMPRE en el texto OCR auxiliar para confirmar el número completo.

▸ CIUDAD
  - Solo escribir el nombre de la ciudad si está CLARAMENTE visible en el documento.
  - Si el campo está vacío o ilegible → null. NUNCA escribir una sola letra suelta.
  - Ciudades colombianas comunes en estos documentos: Medellín, Bogotá, Cali, Barranquilla, Itagüí, Bello, Envigado, Sabaneta, Yopal, Villavicencio, Bucaramanga, Cúcuta, Pereira, Manizales, Ibagué, Armenia, Pasto, Cartagena, Santa Marta, Montería.
  - ADVERTENCIA: la escritura manuscrita de "Itagüí" puede parecerse a "Ibagué", "Yaguí", "Taguí", "Ibaquí" o incluso "Yopal". Leer cada letra con cuidado.
  - Si hay ambigüedad entre dos ciudades y no se puede determinar con certeza → null.
  - Apoyarse en el texto OCR auxiliar para validar el nombre.

▸ PAGADO_A (nombres de personas o empresas)
  - Buscar en el documento los campos etiquetados como "Pagado a:", "Pagado a",
    "Señor(es):", "Señor:", "Sr.", "Beneficiario:". El texto que sigue a esa etiqueta es pagado_a.
  - Si el campo está vacío o en blanco en el documento → null.
  - El valor debe ser SIEMPRE un texto (nombre de persona o empresa), NUNCA un número puro.
    Si lo que sigue a la etiqueta es únicamente un número → null.
  - Leer cada letra con máxima atención. Los apellidos pueden ser manuscritos y difíciles.
  - Apoyarse en el texto OCR auxiliar para validar nombres y apellidos.
  - Apellidos comunes en estos recibos: Restrepo, Gómez, García, López, Martínez, Rodríguez, Herrera, Torres, Vargas, Castillo, Morales, Jiménez, Díaz, Pérez, Muñoz, Ramírez.
  - NUNCA copiar el texto de "firma_recibido" o "vendedor" en este campo.

▸ CONCEPTO
  - Transcribir EXACTAMENTE el texto del concepto tal como aparece en el documento,
    incluyendo cualquier número que forme parte de la descripción del servicio.
  - Los números que aparecen dentro del concepto (ej: NIT de empresa, códigos) NO deben
    copiarse a ningún otro campo ("telefono_fax", "cc_o_nit", "codigo", etc.).
    Cada número debe ir ÚNICAMENTE en el campo al que corresponde por su etiqueta en el documento.
  - NUNCA confundir "mensajería" con "masajería", "masajista" o "masajera".
  - "mensajería" = servicio de envío/transporte de documentos o paquetes.
  - Si hay duda entre dos lecturas, elegir la que tenga más sentido en un contexto empresarial colombiano.

▸ VALOR y VALOR_EN_LETRAS
  - "valor": solo el número puro, sin símbolo "$", sin puntos de miles, sin comas. Ejemplo: 50000.
  - "valor_en_letras": transcribir EXACTAMENTE lo que dice el documento, palabra por palabra.
  - Verificar coherencia: si "valor" es 16000, "valor_en_letras" debe corresponder a "dieciséis mil" o similar.
  - Si hay discrepancia entre imagen y OCR auxiliar, preferir la imagen.

▸ FIRMA_RECIBIDO
  - Examinar el espacio de firma con atención.
  - Si hay CUALQUIER trazo manuscrito, firma, rúbrica o nombre escrito a mano → "Sí".
  - Si hay un nombre impreso (no manuscrito) en el espacio de firma → "Sí".
  - Solo usar null si el espacio está COMPLETAMENTE vacío, sin ningún trazo.
  - NUNCA usar "No" a menos que estés completamente seguro de que no hay ninguna firma.

▸ VENDEDOR
  - Solo extraer si existe un campo EXPLÍCITAMENTE etiquetado "Vendedor:" o "Vendedor" en el documento.
  - NUNCA copiar el nombre de "pagado_a", "aprobado" o "firma_recibido" en este campo.
  - Si no hay campo de vendedor visible → null.

▸ CC_O_NIT
  - Este campo contiene SOLO números (cédula de ciudadanía o NIT).
  - Buscar en el documento las etiquetas: "C.C.", "CC", "NIT", "Nit", "C.C. o NIT",
    "Identificación", "Cédula". El valor numérico que sigue a esas etiquetas es cc_o_nit.
  - NUNCA tomar el número del campo "concepto" para este campo.
  - NUNCA incluir letras, puntos ni guiones — solo los dígitos del número.
  - Si no hay etiqueta explícita de CC o NIT en el documento → null.

▸ TOTAL_DOCUMENTO y VALOR_TOTAL
  - "valor_total" debe tener SIEMPRE el mismo valor numérico que "total_documento".
  - Si el recibo tiene un único valor monetario → ese valor va en "valor", "total_documento" Y "valor_total".
  - Si hay un campo explícito "Total" o "Total a pagar" → usarlo en "total_documento" y en "valor_total".
  - Nunca dejar "valor_total" en null si "total_documento" tiene un valor.

▸ FECHA
  - Formato de salida: DD/MM/YYYY. Convertir si el documento usa otro formato.

▸ TIPO_DOCUMENTO
  - Usar "recibo de caja menor" SOLO si esas palabras aparecen visibles y escritas en el documento.
  - Usar "cuenta de cobro" SOLO si esas palabras aparecen visibles y escritas en el documento.
  - Si el tipo de documento NO está escrito explícitamente en la imagen → null.
  - NO inferir ni adivinar el tipo por el formato visual del documento.

▸ PLANTILLA_DETECTADA
  - Describir el formato visual: "recibo pre-impreso con logo", "recibo manuscrito", "formato tabular con ítems", etc.

▸ CAMPOS MULTI-LÍNEA
  - Concatenar con " | " como separador.

════════════════════════════════════════
TEXTO OCR AUXILIAR (referencia cruzada)
════════════════════════════════════════
El siguiente texto fue extraído automáticamente con Tesseract OCR de la misma imagen.
Úsalo SOLO como referencia cruzada para validar lecturas dudosas.
La imagen siempre tiene PRIORIDAD sobre este texto.
Si el OCR auxiliar es claramente incorrecto o contradice lo visible en la imagen, ignóralo.

--- INICIO OCR AUXILIAR ---
{ocr_text}
--- FIN OCR AUXILIAR ---

════════════════════════════════════════
PRINCIPIO ANTI-ALUCINACIÓN
════════════════════════════════════════
NUNCA inventes, supongas ni completes datos que no puedas leer claramente en la imagen.
Si algo es ilegible o está ausente, usa null.
Extrae EXACTAMENTE lo que dice el documento.

════════════════════════════════════════
SCHEMA JSON DE SALIDA (22 campos, null por defecto)
════════════════════════════════════════
{{
  "ciudad": null,
  "fecha": null,
  "numero_recibo": null,
  "pagado_a": null,
  "valor": null,
  "concepto": null,
  "valor_en_letras": null,
  "firma_recibido": null,
  "cc_o_nit": null,
  "codigo": null,
  "aprobado": null,
  "direccion": null,
  "vendedor": null,
  "telefono_fax": null,
  "forma_pago": null,
  "cantidad": null,
  "detalle": null,
  "valor_unitario": null,
  "valor_total": null,
  "total_documento": null,
  "tipo_documento": null,
  "plantilla_detectada": null
}}"""

# ---------------------------------------------------------------------------
# Private helpers
# ---------------------------------------------------------------------------


def _empty_record() -> dict[str, object]:
    """Return a dict with all 22 expected fields set to ``None``.

    Returns:
        A dictionary with every field in ``EXPECTED_FIELDS`` mapped to
        ``None``.
    """
    return {field: None for field in EXPECTED_FIELDS}


def _normalize_fields(data: dict[str, object]) -> dict[str, object]:
    """Ensure all 22 expected fields exist in *data*.

    Fields present in ``EXPECTED_FIELDS`` but missing from *data* are
    added with a ``None`` value.  Extra fields returned by the model are
    preserved.

    Args:
        data: The raw dictionary parsed from the model's JSON response.

    Returns:
        The same dictionary, guaranteed to contain every field in
        ``EXPECTED_FIELDS``.
    """
    for field in EXPECTED_FIELDS:
        if field not in data:
            data[field] = None
    return data


def _build_prompt(ocr_text: str) -> str:
    """Inject Tesseract OCR text into ``EXTRACTION_PROMPT``.

    Uses ``str.format`` to replace the ``{ocr_text}`` placeholder with the
    actual OCR output.  The double-brace ``{{}}`` escaping in the prompt
    template ensures the JSON schema braces are preserved.

    Args:
        ocr_text: Text extracted by ``tesseract_pre_ocr``.

    Returns:
        The fully-rendered prompt string ready to be sent to the LLM.
    """
    return EXTRACTION_PROMPT.format(ocr_text=ocr_text)


# ---------------------------------------------------------------------------
# Tesseract pre-OCR (cross-validation aid)
# ---------------------------------------------------------------------------


def tesseract_pre_ocr(image: Image.Image) -> str:
    """Extract raw text from an image using Tesseract as a cross-check aid.

    Runs ``pytesseract.image_to_string`` with Spanish language data and
    ``--psm 6`` (assumes a single uniform block of text) on the
    orientation-corrected image.  The result is cleaned by stripping blank
    lines and extra whitespace before being injected into the LLM prompt.

    The LLM uses this text only as a secondary reference; the image always
    takes priority.

    Args:
        image: An orientation-corrected PIL ``Image.Image``.

    Returns:
        A cleaned, newline-separated string of OCR-extracted text, or a
        placeholder message if Tesseract fails.
    """
    try:
        raw: str = pytesseract.image_to_string(image, lang="spa", config="--psm 6")
        lines: list[str] = [ln.strip() for ln in raw.splitlines() if ln.strip()]
        cleaned: str = "\n".join(lines)
        logger.debug("Tesseract pre-OCR extracted %d chars (%d lines)", len(cleaned), len(lines))
        return cleaned if cleaned else "[OCR auxiliar: texto no detectado]"
    except Exception as exc:  # noqa: BLE001
        logger.warning("tesseract_pre_ocr failed: %s", exc)
        return "[OCR auxiliar no disponible]"


# ---------------------------------------------------------------------------
# Image encoding
# ---------------------------------------------------------------------------


def image_to_base64(image: Image.Image, max_size: int = 1568) -> tuple[str, str]:
    """Encode a PIL image to a base64 JPEG string suitable for API payloads.

    If either dimension exceeds *max_size*, the image is proportionally
    downscaled so the longest side equals *max_size*.  Images with an alpha
    channel or palette mode (``RGBA``, ``P``) are converted to ``RGB`` before
    encoding to avoid JPEG incompatibility.

    Args:
        image: The PIL ``Image.Image`` to encode.
        max_size: Maximum pixel count for the longest side.  Defaults to
            ``1568``, which is within the safe range for Anthropic and
            OpenAI vision endpoints.

    Returns:
        A tuple ``(base64_string, media_type)`` where ``base64_string`` is
        the UTF-8 base64-encoded JPEG and ``media_type`` is always
        ``"image/jpeg"``.
    """
    img: Image.Image = image

    # Convert modes incompatible with JPEG
    if img.mode in ("RGBA", "P"):
        img = img.convert("RGB")
    elif img.mode not in ("RGB", "L"):
        img = img.convert("RGB")

    # Downscale if the image is too large
    width: int
    height: int
    width, height = img.size
    longest: int = max(width, height)
    if longest > max_size:
        scale: float = max_size / longest
        new_width: int = int(width * scale)
        new_height: int = int(height * scale)
        img = img.resize((new_width, new_height), Image.Resampling.LANCZOS)
        logger.debug(
            "Image resized from %dx%d to %dx%d for API upload",
            width,
            height,
            new_width,
            new_height,
        )

    buffer: io.BytesIO = io.BytesIO()
    img.save(buffer, format="JPEG", quality=92)
    raw_bytes: bytes = buffer.getvalue()
    encoded: str = base64.b64encode(raw_bytes).decode("utf-8")
    logger.debug("Image encoded to base64 (%d bytes JPEG)", len(raw_bytes))
    return encoded, "image/jpeg"


# ---------------------------------------------------------------------------
# Response parsing
# ---------------------------------------------------------------------------


def parse_extraction_response(raw_text: str) -> dict[str, object]:
    """Parse a JSON extraction response from the model using 4 strategies.

    Attempts four strategies in order, designed to handle both clean JSON
    output (Sonnet 4.6) and reasoning-model output (Kimi K2.5) that may
    include chain-of-thought text before or after the JSON:

    1. **Direct parse** — strip markdown fences and call ``json.loads``.
    2. **Code fence extraction** — regex ``r"```(?:json)?\\s*\\n?(.*?)\\n?\\s*```"``
       with ``re.DOTALL``; tries every fenced block found.
    3. **Bracket matching** — walks the text character-by-character tracking
       brace depth while respecting string literals.  Collects every
       complete ``{…}`` block; keeps the longest one that contains at
       least one anchor field from ``_JSON_ANCHOR_FIELDS``.
    4. **Last resort** — slices from ``text.find("{")`` to
       ``text.rfind("}") + 1`` and attempts a final ``json.loads``.

    Args:
        raw_text: The raw text content returned by the LLM.

    Returns:
        A dictionary of extracted fields.  Falls back to
        ``_empty_record()`` if all four strategies fail.
    """
    # ------------------------------------------------------------------ #
    # Strategy 1 — direct parse after stripping code fences
    # ------------------------------------------------------------------ #
    cleaned: str = _FENCE_PATTERN.sub("", raw_text).strip()
    try:
        result: object = json.loads(cleaned)
        if isinstance(result, dict):
            return result
    except json.JSONDecodeError:
        pass

    # ------------------------------------------------------------------ #
    # Strategy 2 — extract blocks inside ``` … ``` fences
    # ------------------------------------------------------------------ #
    for block in _CODE_FENCE_PATTERN.findall(raw_text):
        block_stripped: str = block.strip()
        try:
            fenced: object = json.loads(block_stripped)
            if isinstance(fenced, dict):
                logger.debug("JSON extracted via code-fence regex")
                return fenced
        except json.JSONDecodeError:
            continue

    # ------------------------------------------------------------------ #
    # Strategy 3 — bracket-matching with depth tracking (string-aware)
    # ------------------------------------------------------------------ #
    best: dict[str, object] | None = None
    best_len: int = 0
    idx: int = 0
    text_len: int = len(cleaned)

    while idx < text_len:
        if cleaned[idx] == "{":
            depth: int = 0
            in_string: bool = False
            escaped: bool = False
            j: int = idx

            while j < text_len:
                ch: str = cleaned[j]
                if escaped:
                    escaped = False
                elif ch == "\\" and in_string:
                    escaped = True
                elif ch == '"':
                    in_string = not in_string
                elif not in_string:
                    if ch == "{":
                        depth += 1
                    elif ch == "}":
                        depth -= 1
                        if depth == 0:
                            candidate: str = cleaned[idx : j + 1]
                            try:
                                obj: object = json.loads(candidate)
                                if isinstance(obj, dict):
                                    has_anchor: bool = bool(
                                        _JSON_ANCHOR_FIELDS & set(obj.keys())
                                    )
                                    if has_anchor and len(candidate) > best_len:
                                        best = obj
                                        best_len = len(candidate)
                            except json.JSONDecodeError:
                                pass
                            break
                j += 1
        idx += 1

    if best is not None:
        logger.debug(
            "JSON extracted via bracket-matching (block_len=%d)", best_len
        )
        return best

    # ------------------------------------------------------------------ #
    # Strategy 4 — last resort: slice first { … last }
    # ------------------------------------------------------------------ #
    start: int = cleaned.find("{")
    end: int = cleaned.rfind("}")
    if start != -1 and end != -1 and end > start:
        try:
            last_try: object = json.loads(cleaned[start : end + 1])
            if isinstance(last_try, dict):
                logger.debug("JSON extracted via last-resort slice")
                return last_try
        except json.JSONDecodeError:
            pass

    logger.error(
        "Failed to parse JSON from model response. Raw text (first 300 chars): %s",
        raw_text[:300],
    )
    return _empty_record()


# ---------------------------------------------------------------------------
# API call helpers
# ---------------------------------------------------------------------------


def _call_anthropic(
    api_key: str,
    model_id: str,
    endpoint: str,
    image_b64: str,
    media_type: str,
    prompt: str,
    timeout: float = 120.0,
) -> tuple[str, float]:
    """Send a vision request to an Anthropic-compatible endpoint.

    Builds a ``/messages`` payload with the image and the rendered extraction
    prompt (including injected OCR text), posts it using ``httpx.Client``,
    and measures elapsed time.

    Args:
        api_key: OpenCode Zen API key.
        model_id: Anthropic model identifier (e.g. ``"claude-sonnet-4-6"``).
        endpoint: Full URL of the Anthropic-compatible messages endpoint.
        image_b64: Base64-encoded JPEG string.
        media_type: MIME type of the image (e.g. ``"image/jpeg"``).
        prompt: Fully-rendered extraction prompt (with OCR text injected).
        timeout: HTTP request timeout in seconds.

    Returns:
        A tuple ``(response_text, elapsed_seconds)``.

    Raises:
        httpx.HTTPStatusError: If the server returns a 4xx or 5xx status.
        httpx.RequestError: If a network-level error occurs.
    """
    headers: dict[str, str] = {
        "x-api-key": api_key,
        "anthropic-version": "2023-06-01",
        "content-type": "application/json",
    }

    payload: dict[str, object] = {
        "model": model_id,
        "max_tokens": 2048,
        "messages": [
            {
                "role": "user",
                "content": [
                    {
                        "type": "image",
                        "source": {
                            "type": "base64",
                            "media_type": media_type,
                            "data": image_b64,
                        },
                    },
                    {
                        "type": "text",
                        "text": prompt,
                    },
                ],
            }
        ],
    }

    t_start: float = time.time()
    with httpx.Client(timeout=timeout) as client:
        response: httpx.Response = client.post(endpoint, headers=headers, json=payload)
        response.raise_for_status()

    elapsed: float = time.time() - t_start

    body: object = response.json()
    if not isinstance(body, dict):
        raise ValueError(f"Unexpected Anthropic response type: {type(body)}")

    content: object = body.get("content")
    if not isinstance(content, list) or not content:
        raise ValueError(f"Unexpected 'content' in Anthropic response: {content}")

    first_block: object = content[0]
    if not isinstance(first_block, dict):
        raise ValueError(f"Unexpected content block type: {type(first_block)}")

    text: object = first_block.get("text")
    if not isinstance(text, str):
        raise ValueError(f"No 'text' field in Anthropic content block: {first_block}")

    logger.debug("Anthropic call completed in %.2fs", elapsed)
    return text, elapsed


def _call_openai_compatible(
    api_key: str,
    model_id: str,
    endpoint: str,
    image_b64: str,
    media_type: str,
    prompt: str,
    timeout: float = 120.0,
) -> tuple[str, float]:
    """Send a vision request to an OpenAI-compatible endpoint.

    Builds a ``/chat/completions`` payload with the image encoded as a
    data-URL and the rendered extraction prompt (with OCR text injected),
    posts it using ``httpx.Client``, and measures elapsed time.

    Args:
        api_key: OpenCode Zen API key.
        model_id: OSS model identifier (e.g. ``"kimi-k2.5"``).
        endpoint: Full URL of the OpenAI-compatible completions endpoint.
        image_b64: Base64-encoded JPEG string.
        media_type: MIME type of the image (e.g. ``"image/jpeg"``).
        prompt: Fully-rendered extraction prompt (with OCR text injected).
        timeout: HTTP request timeout in seconds.

    Returns:
        A tuple ``(response_text, elapsed_seconds)``.

    Raises:
        httpx.HTTPStatusError: If the server returns a 4xx or 5xx status.
        httpx.RequestError: If a network-level error occurs.
    """
    headers: dict[str, str] = {
        "Authorization": f"Bearer {api_key}",
        "content-type": "application/json",
    }

    data_url: str = f"data:{media_type};base64,{image_b64}"

    # System message instructs reasoning models (e.g. Kimi K2.5) to output
    # JSON only and suppress chain-of-thought in the final response.
    system_message: dict[str, object] = {
        "role": "system",
        "content": (
            "You are a JSON-only data extraction API. "
            "You MUST respond with ONLY a valid JSON object. "
            "Do NOT include any reasoning, thinking, explanations, "
            "markdown, code fences, or any text before or after the JSON. "
            "Your entire response must be parseable by json.loads(). "
            "If you think internally, do NOT output your thinking."
        ),
    }

    user_message: dict[str, object] = {
        "role": "user",
        "content": [
            {
                "type": "image_url",
                "image_url": {"url": data_url},
            },
            {
                "type": "text",
                "text": prompt,
            },
        ],
    }

    payload: dict[str, object] = {
        "model": model_id,
        "max_tokens": 2048,
        "temperature": 0.1,
        "messages": [system_message, user_message],
    }

    t_start: float = time.time()
    with httpx.Client(timeout=timeout) as client:
        response: httpx.Response = client.post(endpoint, headers=headers, json=payload)
        response.raise_for_status()

    elapsed: float = time.time() - t_start

    body: object = response.json()
    if not isinstance(body, dict):
        raise ValueError(f"Unexpected OpenAI response type: {type(body)}")

    choices: object = body.get("choices")
    if not isinstance(choices, list) or not choices:
        raise ValueError(f"Unexpected 'choices' in OpenAI response: {choices}")

    first_choice: object = choices[0]
    if not isinstance(first_choice, dict):
        raise ValueError(f"Unexpected choice type: {type(first_choice)}")

    message: object = first_choice.get("message")
    if not isinstance(message, dict):
        raise ValueError(f"No 'message' in OpenAI choice: {first_choice}")

    # Extract content; fall back to reasoning_content for thinking models
    raw_content: object = message.get("content")
    extracted_text: str = raw_content if isinstance(raw_content, str) else ""

    if not extracted_text.strip():
        reasoning: object = message.get("reasoning_content")
        if isinstance(reasoning, str) and reasoning.strip():
            logger.warning(
                "Model returned reasoning_content but empty content — "
                "falling back to reasoning_content for JSON extraction."
            )
            extracted_text = reasoning
        else:
            raise ValueError(
                f"No usable 'content' or 'reasoning_content' in OpenAI message: {message}"
            )

    logger.debug("OpenAI-compatible call completed in %.2fs", elapsed)
    return extracted_text, elapsed


# ---------------------------------------------------------------------------
# Public extraction entry point
# ---------------------------------------------------------------------------


def extract_receipt_data(
    api_key: str,
    image: Image.Image,
    model_name: str = "sonnet-4.6",
    timeout: float = 120.0,
) -> tuple[dict[str, object], float]:
    """Extract structured receipt data from an image using the specified model.

    This is the main public entry point of the module.  It orchestrates:

    1. Validation of *model_name* against ``MODELS``.
    2. Tesseract pre-OCR via ``tesseract_pre_ocr`` to obtain auxiliary text.
    3. Prompt construction via ``_build_prompt`` (injects OCR text).
    4. Image encoding via ``image_to_base64``.
    5. API dispatch to ``_call_anthropic`` or ``_call_openai_compatible``
       depending on the model's ``api_type``.
    6. Response parsing via ``parse_extraction_response``.
    7. Field normalisation via ``_normalize_fields``.

    Args:
        api_key: OpenCode Zen API key (value of ``OPENCODE_API_KEY``).
        image: An orientation-corrected PIL ``Image.Image``.
        model_name: Key into the ``MODELS`` dict.  Defaults to
            ``"sonnet-4.6"``.
        timeout: HTTP request timeout in seconds passed to the underlying
            ``httpx.Client``.

    Returns:
        A tuple ``(extracted_data, elapsed_seconds)`` where
        ``extracted_data`` is a normalised dictionary with all 22 expected
        fields and ``elapsed_seconds`` is the total API round-trip time.

    Raises:
        ValueError: If *model_name* is not a key in ``MODELS``.
        httpx.HTTPStatusError: If the API returns a 4xx or 5xx response.
        httpx.RequestError: If a network-level error occurs.
    """
    if model_name not in MODELS:
        raise ValueError(
            f"Unknown model '{model_name}'. "
            f"Available models: {list(MODELS.keys())}"
        )

    model_cfg: dict[str, str] = MODELS[model_name]
    model_id: str = model_cfg["model_id"]
    endpoint: str = model_cfg["endpoint"]
    api_type: str = model_cfg["api_type"]

    logger.info("Extracting receipt data with model '%s' (%s)", model_name, model_id)

    # Step 1 — Tesseract pre-OCR for cross-validation
    ocr_text: str = tesseract_pre_ocr(image)

    # Step 2 — Build prompt with OCR text injected
    prompt: str = _build_prompt(ocr_text)

    # Step 3 — Encode image
    image_b64: str
    media_type: str
    image_b64, media_type = image_to_base64(image)

    # Step 4 — Call API
    raw_text: str
    elapsed: float

    if api_type == "anthropic":
        raw_text, elapsed = _call_anthropic(
            api_key, model_id, endpoint, image_b64, media_type, prompt, timeout
        )
    else:
        raw_text, elapsed = _call_openai_compatible(
            api_key, model_id, endpoint, image_b64, media_type, prompt, timeout
        )

    logger.info("Model '%s' responded in %.2fs", model_name, elapsed)

    # Step 5 — Parse and normalise
    parsed: dict[str, object] = parse_extraction_response(raw_text)
    normalised: dict[str, object] = _normalize_fields(parsed)
    return normalised, elapsed
