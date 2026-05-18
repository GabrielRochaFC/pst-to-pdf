[🇺🇸 English](README.md) · [🇧🇷 Português](README.pt-BR.md) · [🇪🇸 Español](README.es.md)

> *Esta traducción puede estar desactualizada respecto a la versión en inglés. Para la información más reciente, consulte [README.md](README.md).*

# pst-to-pdf

[![Python 3.10+](https://img.shields.io/badge/python-3.10%2B-blue?logo=python&logoColor=white)](https://www.python.org/)
[![Licencia: MIT](https://img.shields.io/badge/licencia-MIT-green)](LICENSE)
[![Plataforma: Linux](https://img.shields.io/badge/plataforma-Linux-lightgrey?logo=linux&logoColor=white)](https://www.kernel.org/)
[![Motores PDF](https://img.shields.io/badge/PDF-ReportLab%20%C2%B7%20WeasyPrint-blue)](https://www.reportlab.com/)
[![Privacidad: 100% local](https://img.shields.io/badge/privacidad-100%25%20local-brightgreen)](README.es.md)

Pipeline CLI local para convertir archivos PST de Outlook a PDF. Ejecuta `readpst` para extraer archivos EML, los convierte en paralelo y escribe un CSV de manifiesto por PST. Sin servicios en la nube, sin APIs externas, sin internet tras la instalación.

## Características

- Asistente interactivo para configuración de caso y trabajo
- Conversión paralela EML→PDF con workers y timeout configurables
- Dos motores PDF: `fast` (ReportLab, texto plano) y `weasyprint` (HTML con estilo)
- Soporte de reanudación — lee el manifiesto existente y omite archivos ya convertidos
- CSV de manifiesto registra cada EML con estado `ok`, `error` o `timeout`
- Validación cruza archivos EML, PDFs y filas del manifiesto para consistencia
- Reparación segura de manifiesto con copias de seguridad con marca de tiempo y dry-run por defecto
- Los cuerpos de correo nunca se escriben en stdout, stderr ni archivos de log

## Requisitos

- Linux
- Python 3.10+
- `pipx`
- `readpst` de `pst-utils`

```bash
sudo apt update && sudo apt install pipx pst-utils
pipx ensurepath
```

## Instalación

```bash
pipx install pst-to-pdf
```

<details>
<summary>Instalación editable para desarrollo</summary>

```bash
pipx install --editable . --force
```

</details>

## Uso

```bash
pst-to-pdf                  # asistente interactivo
pst-to-pdf --dry-run        # ver comandos sin ejecutar
pst-to-pdf --validate-only  # validar salida existente, sin convertir
```

El asistente recopila: directorio del caso, origen de PSTs (carpeta o rutas separadas por coma), modo PDF, cantidad de workers (por defecto `8`) y timeout (por defecto `60s`). La extracción y la conversión comienzan solo tras confirmación explícita.

### Estructura de salida

```
carpeta-del-caso/
├── input/
├── output/
│   └── <slug>/
│       ├── eml/
│       ├── pdf/
│       └── manifest/<slug>.csv
└── logs/
```

Los slugs se derivan de los nombres de los archivos PST; las colisiones reciben un sufijo SHA-256.

## Modos de PDF

| Modo | Motor | Notas |
|------|-------|-------|
| `fast` *(predeterminado)* | ReportLab | Elimina `<style>`, `<script>`, `<head>`, `<title>`, `<noscript>` y comentarios HTML; sin CSS ni JS en la salida |
| `weasyprint` | WeasyPrint | Renderiza plantilla HTML completa; más lento, mayor fidelidad de layout |

La carga de recursos externos está deshabilitada en ambos modos.

## Uso Avanzado

### Pipeline por scripts

```bash
python3 scripts/process_user_psts.py --case-dir "/mnt/hd/pst-pdf/example-user"

python3 scripts/convert_eml_to_pdf.py \
  --source-pst input/sample.pst \
  --eml-dir output/sample/eml \
  --pdf-dir output/sample/pdf \
  --manifest output/sample/manifest/sample.csv \
  --log-file logs/convert_sample.log \
  --resume

python3 scripts/validate_outputs.py \
  --eml-dir output/sample/eml \
  --pdf-dir output/sample/pdf \
  --manifest output/sample/manifest/sample.csv
```

### Reparación de manifiesto

```bash
# Dry-run (por defecto)
python3 -m pst_to_pdf.repair_manifest \
  --case-dir "/mnt/hd/pst-pdf/example-user" \
  --slug example-user-001 --slug example-user-005

# Aplicar tras revisar la salida del dry-run
python3 -m pst_to_pdf.repair_manifest \
  --case-dir "/mnt/hd/pst-pdf/example-user" \
  --slug example-user-001,example-user-005 \
  --apply
```

### Paquetes opcionales del sistema

```bash
sudo apt install python3 python3-venv python3-pip pff-tools \
  libpango-1.0-0 libpangoft2-1.0-0 libharfbuzz0b libharfbuzz-subset0
```

`pff-tools` (`pffinfo`, `pffexport`) son herramientas de inspección alternativas; `readpst` es el extractor principal.

## Desarrollo

```bash
python3 -m py_compile \
  pst_to_pdf/__init__.py pst_to_pdf/cli.py pst_to_pdf/processor.py \
  pst_to_pdf/converter.py pst_to_pdf/validator.py pst_to_pdf/extraction.py \
  pst_to_pdf/repair_manifest.py scripts/convert_eml_to_pdf.py \
  scripts/process_user_psts.py scripts/validate_outputs.py

bash -n scripts/check_environment.sh scripts/extract_pst.sh scripts/run_test_pipeline.sh

python3 -m pytest tests/
```

## Lista de Verificación para Publicación

- [ ] Reemplazar marcadores de autor y URL en `pyproject.toml`
- [ ] Agregar archivo de licencia
- [ ] Agregar pruebas para prompts CLI, colisión de copia PST y comportamiento de dry-run
- [ ] `python -m build`
- [ ] `twine check dist/*`
- [ ] Publicar en TestPyPI antes de PyPI

## Licencia

[MIT](LICENSE)
