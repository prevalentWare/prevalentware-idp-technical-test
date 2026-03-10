# Development Log — Receipt Data Extraction Pipeline

Registro cronológico del desarrollo asistido por IA.

---

## Sesión 1 — Análisis y Arquitectura
**Herramienta**: Claude (claude.ai)
**Objetivo**: Entender la prueba técnica y planificar la implementación.

- Analicé el documento de la prueba técnica completo
- Identifiqué 6 entregables: código, Excel, benchmark, plan Ollama, evidencia AI, PDFs
- Diseñé la arquitectura modular: orientation.py, extractor.py, excel_writer.py, main.py, benchmark.py
- Investigué la API de OpenCode Zen: endpoints, modelos, pricing
- Generé los prompts para cada fase de construcción

## Sesión 2 — Construcción del Pipeline
**Herramienta**: OpenCode + Claude
**Objetivo**: Implementar todos los módulos.

- Construí src/orientation.py (Tesseract OSD para rotación)
- Construí src/extractor.py (llamadas a OpenCode Zen API)
- Construí src/excel_writer.py (generación de Excel con pandas)
- Construí main.py (CLI pipeline)
- Construí benchmark.py (comparación entre modelos)
- Generé requirements.txt, .env.example, .gitignore, README.md

## Sesión 3 — Primera Ejecución y Debugging
**Herramienta**: OpenCode
**Objetivo**: Ejecutar con imágenes reales y corregir errores.

- Ejecuté el pipeline con 13 imágenes de recibos de caja menor
- Identifiqué errores sistemáticos en la extracción:
  - Nombres: Restrepo→Pastrano/Pacheco
  - Ciudad: Itagüí→Ibagué/Yaguí/Bogotá
  - Concepto: mensajería→masajista
  - Números: 0025→G025, 0030→003.0
  - Alucinaciones: vendedor inventado
- Analicé las causas raíz de cada error

## Sesión 4 — Mejora del Prompt de Extracción
**Herramienta**: Claude + OpenCode
**Objetivo**: Resolver los errores de extracción.

- Agregué Tesseract pre-OCR como herramienta auxiliar (texto inyectado en el prompt)
- Reescribí EXTRACTION_PROMPT con reglas específicas por campo
- Agregué tabla de confusiones de caracteres (0↔G↔O, 1↔l↔I)
- Agregué lista de ciudades colombianas comunes
- Agregué principio anti-alucinación
- Agregué verificación de coherencia valor↔valor_en_letras

## Sesión 5 — Selección de Modelo OSS
**Herramienta**: Claude + OpenCode
**Objetivo**: Seleccionar y probar el modelo open-source para el benchmark.

- Intento 1: Kimi K2.5 — falló por ser thinking model (chain-of-thought sin JSON)
  - Implementé system message para suprimir reasoning
  - Implementé parser con 4 estrategias de extracción de JSON
  - Implementé manejo de reasoning_content
  - Resultado: solo 1/13 imágenes produjo JSON parseable
- Intento 2: GLM-5 — investigación de capacidades multimodales
  - Confirmado como multimodal nativo pero sin certeza de soporte en OpenCode Zen
- Decisión: probar empíricamente con modelos disponibles que soporten visión

## Sesión 6 — Generación de Entregables
**Herramienta**: Claude + OpenCode
**Objetivo**: Crear PDFs y documentación.

- Generé benchmark/analysis.pdf con reportlab (análisis comparativo)
- Generé docs/local-ollama-ocr-plan.pdf (plan de pipeline local con Ollama)
- Creé ai/prompts.md (documentación de prompts)
- Creé ai/conversations/ (logs de desarrollo)
