# Conversation Logs

Este directorio contiene los logs y transcripciones de las conversaciones de IA utilizadas durante el desarrollo del proyecto.

## Fuentes de las conversaciones

### Claude (claude.ai)
- **Conversación principal de desarrollo**: Análisis de requisitos, diseño de arquitectura, construcción de todos los módulos, debugging iterativo del prompt de extracción, selección de modelo OSS, generación de PDFs.
- **Formato**: Exportado desde la interfaz web de Claude.

### OpenCode (terminal)
- **Sesiones de implementación**: Ejecución de los prompts de construcción dentro de OpenCode para generar y modificar el código directamente en el repositorio.
- **Formato**: Logs de terminal / sesiones compartidas con `/share`.

## Cómo se usó la IA en este proyecto

El proyecto fue construido 100% con asistencia de IA, siguiendo un flujo de vibe coding:

1. **Análisis y planificación** (Claude): Desglose de requisitos, identificación de entregables, diseño de arquitectura modular.
2. **Investigación de APIs** (Claude): Consulta de documentación de OpenCode Zen para entender endpoints, modelos y pricing.
3. **Generación de código** (OpenCode + Claude): Cada módulo fue construido con un prompt específico que incluía la firma de funciones, tipos de retorno y restricciones técnicas.
4. **Testing y debugging** (OpenCode): Ejecución del pipeline, análisis de errores, iteración sobre el prompt de extracción.
5. **Prompt engineering iterativo** (Claude): 3 versiones del prompt de extracción, cada una corrigiendo errores detectados en ejecución real.
6. **Documentación** (Claude + OpenCode): READMEs, prompts.md, PDFs con reportlab.

## Nota sobre la evidencia

Los prompts detallados y las decisiones técnicas están documentados en `ai/prompts.md`. Las conversaciones completas están disponibles para revisión en la entrevista de seguimiento.
