# Leitor local de notas fiscais e comprovantes de Pix

Ferramenta para uma contadora autônoma que recebe cerca de 100 documentos por semana (NF-e,
cupons NFC-e, comprovantes de Pix, recibos) e hoje digita tudo à mão. Ela lê cada documento
com modelos de IA **open-source rodando localmente** no Ollama, valida o resultado em Python
e entrega uma planilha Excel pronta para conferência.

**Privacidade (LGPD):** nenhum dado sai da máquina. A única conexão de rede é com o Ollama em
`localhost:11434`, e a telemetria do Streamlit fica desligada em `.streamlit/config.toml`.

## Como funciona

```
arquivo ──► detectar_tipo()
             ├─ PDF com texto (> 50 caracteres) ─► pdfplumber ─► qwen2.5:3b    ─┐
             ├─ PDF escaneado ─► renderiza página ─────────────► qwen2.5vl:7b ─┤─► JSON (schema forçado)
             └─ JPG / PNG ─────────────────────────────────────► qwen2.5vl:7b ─┘        │
                                                                                         ▼
                        validação em Python: CNPJ (DV), chave de acesso (DV), valor > 0,
                        data dentro da competência, categoria na lista ─► revisar = True/False
```

- A saída do modelo é travada com o parâmetro `format` do Ollama, que recebe o JSON Schema
  do modelo pydantic `ExtracaoLLM`. Assim, `tipo` só pode sair da lista fixa.
- O modelo só **copia** quem recebeu e quem pagou. Quem é a contraparte o Python decide, pelo
  tipo e pelo CNPJ da empresa cliente. Se o modelo trocar emitente e destinatário de uma NF-e,
  o CNPJ do emitente, que fica dentro da chave de acesso, mostra a troca e o Python desfaz.
- A categoria vem de uma **segunda chamada curta** ao modelo de texto, só com fornecedor, tipo e
  descrição, que escolhe entre as categorias de despesa. Entradas são sempre "Receita (entrada)".
  Separar essa decisão subiu a categoria de 70% para 100% nas amostras.
- Nos PDFs com texto, a chave de acesso de 44 dígitos é procurada direto no texto com regex e
  conferida pelo dígito verificador, o que é mais confiável que pedir para o LLM copiar.
- Despesa sem CNPJ do fornecedor (recibo de pessoa física, por exemplo) vai para revisão.
- Se um documento der erro, o lote continua: ele aparece com `revisar = True` e o erro no motivo.
- O CNPJ alfanumérico (em vigor desde julho de 2026) também é validado.

## Instalação (Windows)

1. Instale o Python 3.11 ou mais novo (`winget install Python.Python.3.12`) e o Ollama.
2. Baixe os modelos:
   ```
   ollama pull qwen2.5:3b
   ollama pull qwen2.5vl:7b
   ```
3. Instale as dependências:
   ```
   cd leitor_notas
   python -m venv .venv
   .venv\Scripts\activate
   pip install -r requirements.txt
   ```

Os nomes dos modelos e os outros ajustes ficam todos no topo de `modelos.py`.

## Uso

```
python test_validacao.py                                              # testes de CNPJ e validação
python pipeline.py ..\amostras-mariana\documentos --competencia 2026-10 --saida resultado.json
python avaliar.py                                                     # acurácia contra o gabarito
streamlit run app.py                                                  # interface
```

Na interface: escolha a competência, envie os arquivos e clique em **Processar**. As linhas que
precisam de revisão aparecem primeiro, marcadas com 🔴. Corrija o que precisar direto na tabela,
clique em **Revalidar edições** e depois em **Exportar Excel**. A planilha sai com uma aba de
lançamentos e outra com o resumo por categoria.

O campo opcional "Empresa cliente" diz ao modelo quem é a empresa, para ele separar Pix enviado
de Pix recebido.

## Avaliação

`avaliar.py` processa `amostras-mariana/documentos/` e compara com `amostras-mariana/gabarito.json`.
Para cada documento e no total, ele mostra se acertou data, valor (tolerância de R$ 0,01), CNPJ,
categoria, caminho e `revisar`, além do tempo médio por caminho. Os documentos `09*` e `10*`
precisam terminar com `revisar = True`. Se não terminarem, o script sai com código 1.

O gabarito pode ser uma lista `[{"arquivo": ..., "data": ..., ...}]`, um dicionário
`{arquivo: {...}}` ou `{"competencia": "2026-10", "cliente": {...}, "documentos": [...]}`.
`caminho_esperado` e `deve_revisar` são aceitos como nomes alternativos de `caminho` e `revisar`.

Para gerar as amostras fictícias: `cd ..\amostras-mariana && python gerar_amostras.py`
(precisa de `pip install reportlab numpy qrcode`).

### Resultado nas amostras (RX 9060 XT, Ollama/Vulkan)

| campo | data | valor | CNPJ | categoria | caminho | revisar | total |
|---|---|---|---|---|---|---|---|
| acertos | 9/10 | 9/10 | 9/10 | 10/10 | 10/10 | 10/10 | **95%** |

Os três erros são todos do documento 10, a foto propositalmente ilegível. Mesmo assim ele caiu
em revisão, por data fora da competência, CNPJ inválido e falta da chave de acesso, que é o
comportamento esperado. Tempo médio: 2,2 s por PDF com texto e 4,0 s por imagem, com os modelos
já carregados.

## Estrutura

| Arquivo | Conteúdo |
|---|---|
| `modelos.py` | configuração (modelos, limites), categorias, modelos pydantic |
| `validacao.py` | `validar_cnpj()`, `validar_chave_acesso()`, `validar_registro()` |
| `extratores.py` | leitura de PDF e imagem, `extrair_pdf_texto()`, `extrair_imagem()` |
| `pipeline.py` | `detectar_tipo()`, `processar_arquivo()`, CLI |
| `avaliar.py` | comparação com o gabarito |
| `app.py` | interface Streamlit com exportação para Excel |
