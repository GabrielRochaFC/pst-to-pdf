[🇺🇸 English](README.md) · [🇧🇷 Português](README.pt-BR.md) · [🇪🇸 Español](README.es.md)

> *Esta tradução pode estar desatualizada em relação à versão em inglês. Para as informações mais recentes, consulte [README.md](README.md).*

# pst-to-pdf

[![Python 3.10+](https://img.shields.io/badge/python-3.10%2B-blue?logo=python&logoColor=white)](https://www.python.org/)
[![Licença: MIT](https://img.shields.io/badge/licen%C3%A7a-MIT-green)](LICENSE)
[![Plataforma: Linux](https://img.shields.io/badge/plataforma-Linux-lightgrey?logo=linux&logoColor=white)](https://www.kernel.org/)
[![Motores PDF](https://img.shields.io/badge/PDF-ReportLab%20%C2%B7%20WeasyPrint-blue)](https://www.reportlab.com/)
[![Privacidade: 100% local](https://img.shields.io/badge/privacidade-100%25%20local-brightgreen)](README.pt-BR.md)

Pipeline local de CLI para converter arquivos PST do Outlook em PDF. Executa `readpst` para extrair arquivos EML, converte-os em paralelo e grava um CSV de manifesto por PST. Sem serviços em nuvem, sem APIs externas, sem internet após a instalação.

## Funcionalidades

- Assistente interativo para configuração de caso e trabalho
- Conversão paralela EML→PDF com workers e timeout configuráveis
- Dois motores de PDF: `fast` (ReportLab, texto simples) e `weasyprint` (HTML estilizado)
- Suporte a retomada — lê o manifesto existente e pula arquivos já convertidos
- CSV de manifesto registra cada EML com status `ok`, `error` ou `timeout`
- Validação cruza arquivos EML, PDFs e linhas do manifesto para consistência
- Reparo seguro de manifesto com backups com timestamp e dry-run por padrão
- Corpos de email nunca são gravados em stdout, stderr ou arquivos de log

## Requisitos

- Linux
- Python 3.10+
- `pipx`
- `readpst` do `pst-utils`

```bash
sudo apt update && sudo apt install pipx pst-utils
pipx ensurepath
```

## Instalação

```bash
pipx install pst-to-pdf
```

<details>
<summary>Instalação editável para desenvolvimento</summary>

```bash
pipx install --editable . --force
```

</details>

## Uso

```bash
pst-to-pdf                  # assistente interativo
pst-to-pdf --dry-run        # visualizar comandos sem executar
pst-to-pdf --validate-only  # validar saída existente, sem converter
```

O assistente coleta: diretório do caso, origem dos PSTs (pasta ou caminhos separados por vírgula), modo PDF, quantidade de workers (padrão `8`) e timeout (padrão `60s`). A extração e a conversão começam apenas após confirmação explícita.

### Estrutura de saída

```
pasta-do-caso/
├── input/
├── output/
│   └── <slug>/
│       ├── eml/
│       ├── pdf/
│       └── manifest/<slug>.csv
└── logs/
```

Os slugs são derivados dos nomes dos arquivos PST; colisões recebem um sufixo SHA-256.

## Modos de PDF

| Modo | Motor | Notas |
|------|-------|-------|
| `fast` *(padrão)* | ReportLab | Remove `<style>`, `<script>`, `<head>`, `<title>`, `<noscript>` e comentários HTML; sem CSS ou JS na saída |
| `weasyprint` | WeasyPrint | Renderiza template HTML completo; mais lento, maior fidelidade de layout |

O carregamento de recursos externos está desabilitado em ambos os modos.

## Uso Avançado

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

### Reparo de manifesto

```bash
# Dry-run (padrão)
python3 -m pst_to_pdf.repair_manifest \
  --case-dir "/mnt/hd/pst-pdf/example-user" \
  --slug example-user-001 --slug example-user-005

# Aplicar após revisar a saída do dry-run
python3 -m pst_to_pdf.repair_manifest \
  --case-dir "/mnt/hd/pst-pdf/example-user" \
  --slug example-user-001,example-user-005 \
  --apply
```

### Pacotes opcionais do sistema

```bash
sudo apt install python3 python3-venv python3-pip pff-tools \
  libpango-1.0-0 libpangoft2-1.0-0 libharfbuzz0b libharfbuzz-subset0
```

`pff-tools` (`pffinfo`, `pffexport`) são ferramentas de inspeção alternativas; `readpst` é o extrator principal.

## Desenvolvimento

```bash
python3 -m py_compile \
  pst_to_pdf/__init__.py pst_to_pdf/cli.py pst_to_pdf/processor.py \
  pst_to_pdf/converter.py pst_to_pdf/validator.py pst_to_pdf/extraction.py \
  pst_to_pdf/repair_manifest.py scripts/convert_eml_to_pdf.py \
  scripts/process_user_psts.py scripts/validate_outputs.py

bash -n scripts/check_environment.sh scripts/extract_pst.sh scripts/run_test_pipeline.sh

python3 -m pytest tests/
```

## Checklist de Publicação

- [ ] Substituir placeholders de autor e URL em `pyproject.toml`
- [ ] Adicionar arquivo de licença
- [ ] Adicionar testes para prompts CLI, colisão de cópia PST e comportamento de dry-run
- [ ] `python -m build`
- [ ] `twine check dist/*`
- [ ] Publicar no TestPyPI antes do PyPI

## Licença

[MIT](LICENSE)
