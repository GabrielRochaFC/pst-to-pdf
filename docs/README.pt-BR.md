[🇺🇸 English](../README.md) · [🇧🇷 Português](README.pt-BR.md) · [🇪🇸 Español](README.es.md)

> *Esta tradução pode estar desatualizada em relação à versão em inglês. Para as informações mais recentes, consulte [README.md](../README.md).*

# pst-to-pdf

[![Python 3.10+](https://img.shields.io/badge/python-3.10%2B-blue?logo=python&logoColor=white)](https://www.python.org/)
[![Licença: MIT](https://img.shields.io/badge/licen%C3%A7a-MIT-green)](../LICENSE)
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

Clone o repositório e instale localmente:

```bash
git clone <repo-url>
cd pst-to-pdf-incra
pipx install --editable . --force
```

> [!NOTE]
> `pipx install pst-to-pdf` estará disponível após a publicação do pacote no PyPI.

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

## Filtragem por participante de e-mail

Por padrão, todo EML extraído do PST é convertido em PDF. Você pode,
opcionalmente, restringir a geração de PDFs a mensagens cujos cabeçalhos de
participantes contenham pelo menos um endereço de uma lista.

### Pelo assistente

O passo 4/5 do assistente pergunta:

```
Enable email filter (y/n) [n*]:
```

Responda `y` e forneça uma lista separada por vírgulas:

```
Enter email addresses, separated by commas:
email1@exemplo.com, email2@exemplo.com
```

O assistente salva a lista normalizada em `case_dir/config/filter_emails.txt`
e uma impressão sha256 em `case_dir/config/filter_emails.fingerprint`.

### Pela linha de comando (avançado)

```bash
python3 -m pst_to_pdf.processor --case-dir /caminho/para/o/caso \
  --filter-email a@x.com --filter-email b@y.com

python3 -m pst_to_pdf.processor --case-dir /caminho/para/o/caso \
  --filter-emails-file /caminho/para/emails.txt
```

O formato do arquivo é um e-mail por linha; linhas em branco e linhas iniciadas
com `#` são ignoradas. As duas opções podem ser combinadas; endereços são
deduplicados.

### Como a correspondência é feita

Uma mensagem corresponde se qualquer endereço em qualquer destes cabeçalhos
estiver no conjunto do filtro:

- `From`, `To`, `Cc`, `Bcc`, `Reply-To`, `Sender`

A comparação é exata (sem diferenciar maiúsculas). O corpo, o assunto e os
nomes de anexos **não** são verificados.

### Como mensagens não correspondentes são registradas

EMLs sem correspondência não geram PDFs. Em vez disso, o manifesto registra
uma linha com `status=filtered`. Linhas filtradas contam como EMLs cobertos na
validação e nunca fazem a validação falhar.

### Trocar o filtro

Para usar um filtro diferente, crie um novo diretório de caso. Reexecutar com
filtro diferente sobre o mesmo caso é bloqueado por uma verificação de
impressão; use `--force-filter` apenas se realmente quiser sobrescrever o
filtro armazenado do caso.

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

[MIT](../LICENSE)
