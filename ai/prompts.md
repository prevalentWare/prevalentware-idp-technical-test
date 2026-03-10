# AI Prompts — Receipt Data Extraction Pipeline

Documentación de todos los prompts utilizados durante el desarrollo del proyecto en esta sesión de OpenCode, incluyendo el proceso iterativo de mejora. Cada prompt está registrado en el orden cronológico exacto en que fue enviado.

---

## 1. Configuración inicial del repositorio

```
Crea una carpeta llamada receipt_extractor, despues de crearla accede a ella y realiza un fork al siguiente repositorio de github https://github.com/prevalentWare/prevalentware-idp-technical-test.git
```

```
clona el sigiente repositorio https://github.com/HancyToro/prevalentware-idp-technical-test.git
```

---

## 2. Creación de la estructura del proyecto

```
Crea EXACTAMENTE esta estructura de directorios y archivos vacíos:

receipt_extractor/
├── main.py
├── benchmark.py
├── requirements.txt
├── .env.example
├── .gitignore
├── README.md
├── src/
│   ├── __init__.py
│   ├── orientation.py
│   ├── extractor.py
│   └── excel_writer.py
├── images/
├── output/
├── benchmark/
├── docs/
└── ai/
    ├── prompts.md
    └── conversations/

Para el archivo requirements.txt incluye estas dependencias:
python-dotenv>=1.0.0
Pillow>=10.0.0
pytesseract>=0.3.10
httpx>=0.27.0
openpyxl>=3.1.0
pandas>=2.0.0
reportlab>=4.0.0

Para .env.example incluye:
OPENCODE_API_KEY=your_api_key_here
```

---

## 3. Módulo src/orientation.py

```
Escribe el módulo src/orientation.py que maneja la detección y corrección de orientación de imágenes usando EXCLUSIVAMENTE Tesseract OSD. Esto es un requisito eliminatorio de la prueba: la rotación NO puede delegarse a un LLM.

El módulo debe contener estas funciones:

1. detect_rotation_angle(image: Image.Image) -> int
2. correct_orientation(image: Image.Image, angle: int) -> Image.Image
3. process_image_orientation(image_path: str | Path) -> tuple[Image.Image, int]
4. get_image_files(input_dir: str | Path) -> list[Path]

Usa logging estándar de Python en todo el módulo. Incluye docstrings completos. Importa Path de pathlib.
```

```
Una cosa a mas a tener en cuenta, el codigo debe cumplir con las reglas de "standard" de pylance asi que modifica el codigo para que cumpla con estas espcificaciones
```

---

## 4. Módulo src/extractor.py

```
Escribe el módulo src/extractor.py que se conecta a la API de OpenCode Zen para extraer datos de recibos usando modelos LLM con visión.

CONTEXTO TÉCNICO CRÍTICO sobre OpenCode Zen:
- Claude Sonnet 4.6 usa el endpoint Anthropic-compatible: https://opencode.ai/zen/v1/messages
  - Header de auth: "x-api-key": <api_key>
  - Header requerido: "anthropic-version": "2023-06-01"
  - Model ID: "claude-sonnet-4-6"
- Los modelos OSS usan el endpoint OpenAI-compatible: https://opencode.ai/zen/v1/chat/completions
  - Header de auth: "Authorization": "Bearer <api_key>"
  - Modelos OSS disponibles: "qwen3-coder", "glm-5", "kimi-k2.5"

El módulo debe contener:
1. Constantes: ANTHROPIC_ENDPOINT, OPENAI_ENDPOINT, MODELS
2. EXTRACTION_PROMPT optimizado para recibos colombianos
3. image_to_base64(), _call_anthropic(), _call_openai_compatible()
4. extract_receipt_data(), parse_extraction_response()
5. _normalize_fields(), _empty_record()

Usa httpx para las llamadas HTTP (NO requests). Usa logging estándar.
```

---

## 5. Módulo src/excel_writer.py

```
Escribe el módulo src/excel_writer.py que genera el archivo Excel consolidado con los datos extraídos.

El módulo debe contener:
1. COLUMN_ORDER: Lista con el orden estable de columnas para el output
2. generate_excel(records: list[dict], output_path: str | Path) -> Path
   - Crea el directorio padre si no existe
   - Convierte la lista de dicts a DataFrame de pandas
   - Reordena las columnas
   - Escribe a Excel con pd.ExcelWriter engine="openpyxl"
   - Sheet name: "Receipts"
   - Auto-ajusta el ancho de columnas basado en el contenido (max 50 caracteres)
   - Retorna el Path del archivo generado

Usa pandas y openpyxl. Incluye logging y docstrings.
```

---

## 6. Pipeline principal main.py

```
Escribe main.py, el punto de entrada CLI del pipeline de extracción de recibos.

Debe usar argparse con estos argumentos:
- --input-dir (default: "./images")
- --output-file (default: "./output/receipts_extracted.xlsx")
- --model (default: "sonnet-4.6", choices de MODELS.keys())
- --verbose / -v (flag)
- --timeout (default: 120.0)

Flujo de main():
1. Cargar variables de entorno con load_dotenv()
2. Validar que OPENCODE_API_KEY existe. Si no, error y salir con código 1.
3. Obtener lista de imágenes con get_image_files()
4. Para cada imagen: Tesseract OSD → extracción con LLM → metadata → agregar a records
5. Generar Excel con generate_excel()
6. Imprimir resumen

Logging format: "%(asctime)s [%(levelname)s] %(name)s: %(message)s"
```

---

## 7. Benchmark benchmark.py

```
Escribe benchmark.py que ejecuta una comparación entre Claude Sonnet 4.6 y un modelo OSS de OpenCode Zen.

CLI con argparse:
- --input-dir (default: "./images")
- --oss-model (default: "qwen3-coder")
- --output-dir (default: "./benchmark")

Flujo:
1. Cargar API key del entorno
2. Obtener lista de imágenes
3. Ejecutar extracción con sonnet-4.6 en TODAS las imágenes
4. Ejecutar extracción con el modelo OSS en TODAS las imágenes
5. Computar métricas por modelo
6. Generar archivos de reporte

CORE_FIELDS = ["ciudad", "fecha", "numero_recibo", "pagado_a", "valor", "concepto", "valor_en_letras", "tipo_documento"]

Función run_extraction(), compute_metrics(), generate_benchmark_report()
Genera: results.csv, metrics_summary.json, results_{model}.json
```

---

## 8. Generación de PDFs

```
Escribe un script Python generate_analysis_pdf.py que genera el archivo benchmark/analysis.pdf usando reportlab.

Estructura del documento:
1. TÍTULO: "Benchmark Analysis: Claude Sonnet 4.6 vs Qwen3 Coder 480B"
2. EXECUTIVE SUMMARY
3. METHODOLOGY
4. COMPARISON TABLE con datos reales de costos de OpenCode Zen:
   - Sonnet 4.6: input $3.00/1M, output $15.00/1M
   - Qwen3 Coder: input $0.45/1M, output $1.50/1M
5. ACCURACY ANALYSIS
6. FAILURE PATTERNS
7. SPEED AND COST TRADEOFFS
8. ARCHITECTURE AND ENGINEERING RECOMMENDATIONS
9. CONCLUSION

Estilo visual: headers con color #1a1a2e, tablas con grid gris y filas alternas, tamaño carta (letter).
```

```
Escribe un script Python generate_ollama_plan_pdf.py que genera docs/local-ollama-ocr-plan.pdf usando reportlab.

Estructura:
1. TÍTULO: "Local OCR Pipeline Plan with Ollama"
2. OVERVIEW
3. ARCHITECTURE (9 pasos)
4. MODEL SELECTION (tabla comparativa: LLaVA 1.6 34B, LLaVA 1.6 13B, Moondream 2, Llama 3.2 Vision 11B, Llama 3.2 Vision 90B)
5. PREPROCESSING STEPS (8 pasos con OpenCV)
6. EXTRACTION STRATEGY (Ollama HTTP API)
7. VALIDATION STRATEGY (6 capas)
8. INFRASTRUCTURE REQUIREMENTS (tabla mínimos/recomendados)
9. RISKS AND MITIGATIONS (tabla 6 riesgos)
10. ROLLOUT PLAN (4 fases)
11. CONCLUSION
```

```
el texto debe estar en español
```

---

## 9. README.md

```
Escribe el README.md del proyecto receipt-extractor. Debe estar en español y ser claro para el evaluador.

Incluir estas secciones:
1. TÍTULO Y DESCRIPCIÓN
2. REQUISITOS DEL SISTEMA (Python 3.10+, Tesseract OCR con comandos para Ubuntu/macOS/Windows, OpenCode Zen API Key)
3. INSTALACIÓN (git clone, venv, pip install, cp .env.example)
4. USO (comando principal, opciones, benchmark)
5. FLUJO DE PROCESAMIENTO (5 pasos numerados)
6. CAMPOS EXTRAÍDOS (principales, adicionales, metadata)
7. ESTRUCTURA DEL PROYECTO
8. NOTAS TÉCNICAS
```

---

## 10. Archivo ai/prompts.md

```
Crea el archivo ai/prompts.md que documenta todos los prompts usados durante el desarrollo.

Estructura:
1. INITIAL ANALYSIS PROMPT
2. ARCHITECTURE PLANNING PROMPT
3. EXTRACTION PROMPT (PRODUCTION) con explicación de por qué cada parte está diseñada así
4. PROMPT ENGINEERING ITERATIONS (3 versiones)
5. BENCHMARK ANALYSIS PROMPTS
6. OLLAMA LOCAL PIPELINE PLANNING PROMPTS
```

---

## 11. Entorno virtual y dependencias

```
Crear el venv, ademas si ves que se necesita agregar librerias a requirements.txt hazlo, despues de tener el archivo actualizado con todas las librerias instala las librerias. cuando crees este entorno realizo con python 3.10 que tengo en el sistema
```

```
Revisa el codigo entero ya que se estan presentado unos problemas como "Import dotenv could not be resolved" como estos hay varios conflitos de librerias que se estan presentando resuelvelos
```

---

## 12. Ejecución y verificación del pipeline

```
Ejecuta el pipeline con una sola imagen para verificar que funciona end-to-end:
python main.py --input-dir ./images --output-file ./output/test_single.xlsx --verbose
```

```
ya instale el tesseract, agrega las lineas anteriores al documento src/orientation.py y despues ejecuta lo siguiente:
python main.py --input-dir ./images --output-file ./output/test_single.xlsx --verbose
```

```
Ejecuta el pipeline completo de extracción con todas las imágenes en ./images:
python main.py --input-dir ./images --output-file ./output/receipts_extracted.xlsx --verbose
```

---

## 13. Mejoras al prompt de extracción (v2 → v3)

```
Contexto del problema. Ejecuté el pipeline de extracción con las 13 imágenes y el modelo sonnet-4.6 tiene errores recurrentes:

numero_recibo: Confunde el dígito "0" con letras como "G" o "O". Ejemplo: sacó "G025" en vez de "0025".
ciudad: Confunde "Itagüí" con "Ibagué", "Yaguí", "Bogotá", "Yopal".
pagado_a (nombres): Confunde apellidos. Puso "Pastrano" y "Pacheco" cuando el correcto era "Restrepo".
concepto: Confunde "mensajería" con "masajista" o "masajera".
valor_en_letras: Mal lectura. Puso "Doce y Seismil" cuando el documento dice "Diez y seis mil".
vendedor: Inventó un nombre "Juan Eduardo Rastro" que no existe en el documento.
firma_recibido: En un documento con firma visible, sacó "No".

Tu tarea: Reescribe completamente src/extractor.py con estas mejoras:
Mejora 1: Agregar Tesseract pre-OCR como herramienta auxiliar (tesseract_pre_ocr())
Mejora 2: Reescribir EXTRACTION_PROMPT con reglas críticas por campo
Mejora 3: Actualizar extract_receipt_data() para ejecutar pre-OCR antes de la llamada al API
```

---

## 14. Correcciones adicionales al prompt

```
Hay algunos cambios que hay que realizar en el documento src/extractor.py:
- En el archivo WhatsApp Image 2026-03-02 at 18.16.55 (1) el numero de recibo es 0040 y escribio 0440
- En las imagenes en el campo concepto aparecen unos numeros, esos no van en el fax
- En la columna cc_o_nit van solo numeros, agrega que este valor esta siempre donde se dice cc o nit
- En la imagen WhatsApp Image 2026-03-02 at 18.17.16 si va el numero 0038 pero se coloco 0030
- Agrega también en el prompt que si no aparece recibo de caja menor o cuenta de cobro en la imagen este campo debe ir vacio
```

```
Unos errores a corregir en el prompt:
1. Se debe colocar en la instruccion de extraccion del numero de recibo que solo se acepta numeros no letras. G025 debe ser 0025.
2. Copia lo que esta en total_documento en valor_total.
3. en las imagenes esta el campo "pagado a" o "Señor(es)" si el campo no trae nada debe ir null, solo debe aceptar strings no numeros.
```

---

## 15. Corrección de orientación de imágenes

```
Revisa las imagenes y el resultado que se obtuvo hay algunos problemas aun por resolver. Las imagenes se estan rotando hacia la derecha, las imagenes estan quedando volteadas. Seria de rotarla en -90° o en 270° para que quede de manera correcta. Corrige esto en el archivo src/orientation.py
```

---

## 16. Benchmark comparativo

```
Ejecuta el benchmark comparativo entre Sonnet 4.6 y Qwen3 Coder:
python benchmark.py --input-dir ./images --oss-model qwen3-coder
```

```
Es verdad el modelo de minimax m2.5 no tiene para procesar imagenes pero el que si tiene es el de kimi k2.5 asi que modifica los codigos necesarios para que el benchmark funcione con este modelo
```

```
Sucede que el modelo de minimaz m2.5 no tiene para procesar imagenes pero el que si tiene es el de kimi k2.5 asi que modifica los archivos necesarios para cambiar el de minimax m2.5 por el de kimi k2.5 como modelo opensource y asi correr el benchmark
```

---

## 17. Solución al problema de Kimi K2.5 (thinking model)

```
Problema: Kimi K2.5 devuelve HTTP 200 pero en vez de JSON puro, responde con razonamiento en texto libre tipo "El usuario quiere que analice..." y nunca produce el JSON final. El parser actual no puede extraer campos → 0/22 en todos los registros.

Modifica src/extractor.py con estos 3 cambios:
Cambio 1: Agregar system message en _call_openai_compatible()
Cambio 2: Manejar reasoning_content en la respuesta
Cambio 3: Reescribir parse_extraction_response() con 4 estrategias:
  - Strategy 1: json.loads directo
  - Strategy 2: Code fences con regex
  - Strategy 3: Bracket matching inteligente
  - Strategy 4: Last resort first/last brace
```

---

## 18. Generación de PDFs finales

```
modifica el documento generate_analysis_pdf.py ya que antes estaba hecho con qwen y se debe cambiar por kimi k2.5 y de paso genera el pdf
```

```
Genera los dos PDFs entregables:
python generate_analysis_pdf.py
python generate_ollama_plan_pdf.py

Si los scripts de generación de PDF necesitan datos reales del benchmark (que ahora tenemos en benchmark/metrics_summary.json), actualiza los scripts para que lean esos datos y los incluyan en las tablas del PDF.
```

---

## 19. Revisión final antes del push

```
Haz una revisión final del repositorio completo antes de hacer push:
1. Verifica que NO hay API keys hardcodeadas en ningún archivo
2. Verifica que .env está en .gitignore
3. Verifica que todos los archivos requeridos existen
4. Verifica que el README tiene el comando de ejecución correcto
5. Muéstrame un tree del proyecto final
```

```
listo corre las tareas y procesos e implementa los cambios que sean necesarios
```

---

## 20. Documentación de evidencia AI

```
Crea el archivo ai/prompts.md con el siguiente contenido exacto [estructura de 8 secciones con prompts, versiones iterativas y técnicas de prompting]
```

```
opencode tui --session ses_330b0339effeD72C6Jtlxatlu1al archivo ai/prompts.md deben ir todos los prompts que escribi en esta session cada uno de ellos no dejes ninguno por fuera agregalos todos desde el principio de esta session
```

---

## Técnicas de Prompting Utilizadas en esta Sesión

1. **Requisitos exhaustivos**: Cada prompt de construcción incluía la firma de funciones, tipos de retorno y restricciones técnicas explícitas
2. **Schema-first**: Dar la estructura JSON exacta con los 22 campos antes de pedir la extracción
3. **Negative instructions**: "NUNCA inventes datos", "Sin markdown, sin bloques de código", "La rotación NO puede delegarse a un LLM"
4. **Confusion tables**: Listar explícitamente las confusiones carácter→carácter (0↔G↔O, 1↔l↔I, 2↔7)
5. **Domain context**: Ciudades colombianas, apellidos comunes, terminología contable local
6. **Cross-validation**: Inyectar texto OCR auxiliar (Tesseract) para que el LLM valide su lectura
7. **Iterative refinement**: 3 versiones del prompt de extracción, cada una corrigiendo errores reales observados en ejecución
8. **Anti-hallucination**: "NUNCA inventes, supongas ni completes datos que no puedas leer claramente"
9. **System message**: Para modelos thinking (Kimi K2.5), suprimir chain-of-thought con `role: system`
10. **Pylance compliance**: Requerir explícitamente que el código cumpla con `typeCheckingMode: standard`
11. **Error-driven refinement**: Proporcionar el error exacto observado (G025 en vez de 0025) para correcciones precisas
12. **Verificación empírica**: Ejecutar el pipeline real con las 13 imágenes para detectar errores antes de documentarlos
