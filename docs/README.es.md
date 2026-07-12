[🇺🇸 English](../README.md) · [🇧🇷 Português](README.pt-BR.md) · [🇪🇸 Español](README.es.md)

> *Esta traducción puede estar desactualizada respecto a la versión en inglés. Para la información más reciente, consulte [README.md](../README.md).*

# pst-to-pdf

[![Python 3.10+](https://img.shields.io/badge/python-3.10%2B-blue?logo=python&logoColor=white)](https://www.python.org/)
[![Licencia: MIT](https://img.shields.io/badge/licencia-MIT-green)](../LICENSE)
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

Clone el repositorio e instale localmente:

```bash
git clone <repo-url>
cd pst-to-pdf-incra
pipx install --editable . --force
```

> [!NOTE]
> `pipx install pst-to-pdf` estará disponible una vez que el paquete sea publicado en PyPI.

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
├── logs/
└── zipped/                  ← creado por `pst-to-pdf zip-pdfs`
    └── <slug>-pdfs.zip
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

### Comprimir los PDFs en ZIP

Una vez procesado un caso, `pst-to-pdf zip-pdfs` recorre `output/` buscando
cada carpeta `<slug>/pdf/` y empaqueta cada una en su propio archivo ZIP,
listo para entregar — sin comprimir carpetas a mano ni recordar qué PST ya
tienen PDFs.

```bash
pst-to-pdf zip-pdfs --case-dir "/mnt/hd/pst-pdf/example-user"

# Vista previa de lo que se comprimiría, sin escribir ningún archivo
pst-to-pdf zip-pdfs --case-dir "/mnt/hd/pst-pdf/example-user" --dry-run
```

Cada `<slug>-pdfs.zip` contiene solo los archivos `.pdf` de esa carpeta
`pdf/` (sin subcarpetas, sin `logs/`, `manifest/`, `eml/` ni ningún otro
archivo del caso). Los ZIP se escriben en `carpeta-del-caso/zipped/` (creada
automáticamente) y se sobrescriben en cada ejecución. Las carpetas sin PDFs
se omiten y se reportan, no se tratan como error.

```
carpeta-del-caso/zipped/
├── example-user-001-pdfs.zip
├── example-user-002-pdfs.zip
└── example-user-003-pdfs.zip
```

Invocación equivalente por módulo: `python3 -m pst_to_pdf.zip_pdfs --case-dir ...`
o `python3 scripts/zip_pdfs.py --case-dir ...`.

### Paquetes opcionales del sistema

```bash
sudo apt install python3 python3-venv python3-pip pff-tools \
  libpango-1.0-0 libpangoft2-1.0-0 libharfbuzz0b libharfbuzz-subset0
```

`pff-tools` (`pffinfo`, `pffexport`) son herramientas de inspección alternativas; `readpst` es el extractor principal.

## Filtrado por participante de correo

De forma predeterminada, cada EML extraído del PST se convierte a PDF. Puede
restringir opcionalmente la generación de PDFs a mensajes cuyos encabezados de
participantes contengan al menos una dirección de correo de una lista.

### Desde el asistente

El paso 4/5 del asistente pregunta:

```
Enable email filter (y/n) [n*]:
```

Responda `y` y proporcione una lista separada por comas:

```
Enter email addresses, separated by commas:
correo1@ejemplo.com, correo2@ejemplo.com
```

El asistente guarda la lista normalizada en `case_dir/config/filter_emails.txt`
y una huella sha256 en `case_dir/config/filter_emails.fingerprint`.

### Desde la línea de comandos (avanzado)

```bash
python3 -m pst_to_pdf.processor --case-dir /ruta/al/caso \
  --filter-email a@x.com --filter-email b@y.com

python3 -m pst_to_pdf.processor --case-dir /ruta/al/caso \
  --filter-emails-file /ruta/a/correos.txt
```

El formato del archivo es un correo por línea; líneas en blanco y comentarios
que empiezan con `#` se ignoran. Ambas opciones pueden combinarse; las
direcciones se deduplican.

### Cómo se comparan las direcciones

Un mensaje coincide si alguna dirección en alguno de estos encabezados está en
el conjunto del filtro:

- `From`, `To`, `Cc`, `Bcc`, `Reply-To`, `Sender`

La comparación es exacta (sin distinguir mayúsculas). El cuerpo, el asunto y
los nombres de archivos adjuntos **no** se revisan.

### Cómo se registran los mensajes no coincidentes

Los EMLs no coincidentes no generan PDFs. En su lugar, el manifiesto registra
una fila con `status=filtered`. Las filas filtradas cuentan como EMLs cubiertos
en la validación y nunca hacen que la validación falle.

### Cambiar el filtro

Si desea usar un filtro diferente, cree un nuevo directorio de caso. Reejecutar
con un filtro distinto en el mismo caso queda bloqueado por una verificación
de huella; use `--force-filter` solo si está seguro de querer sobrescribir el
filtro almacenado del caso.

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

[MIT](../LICENSE)
