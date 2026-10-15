"""Leitura de arquivos e chamadas ao Ollama (somente localhost)."""
import io
import json

import ollama
import pdfplumber
from PIL import Image, ImageOps

from modelos import (
    CONTEXTO_LLM,
    DICAS_CATEGORIAS,
    LADO_MAXIMO_IMAGEM,
    MAX_CARACTERES_TEXTO,
    MODELO_TEXTO,
    MODELO_VISAO,
    OLLAMA_HOST,
    ExtracaoLLM,
)

_ollama = ollama.Client(host=OLLAMA_HOST)

INSTRUCOES = f"""Você extrai dados de documentos fiscais brasileiros (nota fiscal, cupom NFC-e,
comprovante de Pix, recibo) de uma pequena empresa, cliente de uma contadora.
Responda SOMENTE com o JSON pedido.

Regras dos campos:
- tipo: "nfe" (NF-e / DANFE), "nfce" (cupom fiscal NFC-e), "pix_enviado" (a empresa pagou alguém),
  "pix_recebido" (a empresa recebeu), "recibo", "outro".
  Comprovante de Pix com "valor pago", "transferência enviada" ou "comprovante de transferência" é
  "pix_enviado". Só use "pix_recebido" se o documento disser "Pix recebido" ou "você recebeu".
- data: data de emissão ou do pagamento, no formato AAAA-MM-DD. No Brasil a data vem como DD/MM/AAAA.
- valor: valor TOTAL pago ou recebido, com ponto decimal. "R$ 1.234,56" vira 1234.56.
- quem_recebeu_nome / quem_recebeu_cnpj: quem VENDEU ou RECEBEU o dinheiro. Na nota fiscal é o
  EMITENTE; no Pix é o recebedor/destino; no recibo é quem assina.
- quem_pagou_nome / quem_pagou_cnpj: quem COMPROU ou PAGOU. Na nota é o DESTINATÁRIO; no Pix é o
  pagador/origem.
- Copie os CNPJs exatamente como aparecem, ou null. Nunca coloque CPF no lugar de CNPJ.
- chave_acesso: os 44 dígitos da chave de acesso (só NF-e/NFC-e), senão null.
- descricao: resumo curto (até 8 palavras) do que foi comprado ou recebido. Use a mensagem/descrição
  do Pix ou os itens da nota.
- Não invente nada: se um dado não aparece no documento, use null."""

CATEGORIAS_DESPESA = [c for c in DICAS_CATEGORIAS if c != "Receita (entrada)"]
DICAS_DESPESA = "\n".join(f'- "{nome}": {DICAS_CATEGORIAS[nome]}' for nome in CATEGORIAS_DESPESA)
SCHEMA_CATEGORIA = {
    "type": "object",
    "properties": {"categoria": {"type": "string", "enum": CATEGORIAS_DESPESA}},
    "required": ["categoria"],
}


# ---------------------------------------------------------------------------
# Leitura de arquivos
# ---------------------------------------------------------------------------
def ler_texto_pdf(caminho, max_paginas: int = 3) -> str:
    with pdfplumber.open(caminho) as pdf:
        return "\n".join((pagina.extract_text() or "") for pagina in pdf.pages[:max_paginas])


def renderizar_pdf(caminho, resolucao: int = 200) -> Image.Image:
    """Primeira página do PDF escaneado como imagem."""
    with pdfplumber.open(caminho) as pdf:
        return pdf.pages[0].to_image(resolution=resolucao).original.convert("RGB")


def carregar_imagem(caminho) -> Image.Image:
    with Image.open(caminho) as imagem:
        # Fotos de celular guardam a rotação no EXIF; aplicamos antes de mandar ao modelo
        return ImageOps.exif_transpose(imagem).convert("RGB")


def _imagem_para_png(imagem: Image.Image) -> bytes:
    imagem = imagem.copy()
    imagem.thumbnail((LADO_MAXIMO_IMAGEM, LADO_MAXIMO_IMAGEM))
    buffer = io.BytesIO()
    imagem.save(buffer, format="PNG")
    return buffer.getvalue()


# ---------------------------------------------------------------------------
# Chamadas ao modelo
# ---------------------------------------------------------------------------
def _instrucoes(cliente: str | None) -> str:
    if not cliente:
        return INSTRUCOES
    return INSTRUCOES + (
        f"\n- A empresa cliente é: {cliente}. Se ela for a pagadora, o Pix é \"pix_enviado\"; "
        "se for a recebedora, é \"pix_recebido\"."
    )


def _chat(modelo: str, mensagem: dict, schema: dict) -> str:
    resposta = _ollama.chat(
        model=modelo,
        messages=[mensagem],
        format=schema,  # saída estruturada forçada
        options={"temperature": 0, "num_ctx": CONTEXTO_LLM},
        keep_alive="30m",  # mantém o modelo na VRAM entre documentos
    )
    return resposta.message.content


def _perguntar(modelo: str, mensagem: dict) -> ExtracaoLLM:
    return ExtracaoLLM.model_validate_json(_chat(modelo, mensagem, ExtracaoLLM.model_json_schema()))


def classificar_categoria(descricao: str, fornecedor: str, tipo: str) -> str:
    """Categoria de uma DESPESA. Chamada curta e separada: o modelo pequeno acerta mais assim."""
    conteudo = (
        "Classifique esta despesa de uma pequena empresa em uma categoria contábil.\n"
        f"Fornecedor: {fornecedor or 'não informado'}\nDocumento: {tipo}\n"
        f"O que foi pago: {descricao or 'não informado'}\n\n"
        "Escolha pelo que foi pago e pelo ramo do fornecedor. Se o fornecedor PRESTOU UM SERVIÇO "
        "(conserto, refrigeração, gráfica, agência), não é material: é manutenção ou serviço.\n"
        f"{DICAS_DESPESA}"
    )
    resposta = _chat(MODELO_TEXTO, {"role": "user", "content": conteudo}, SCHEMA_CATEGORIA)
    return json.loads(resposta)["categoria"]


def extrair_pdf_texto(texto: str, cliente: str | None = None) -> ExtracaoLLM:
    conteudo = (
        f"{_instrucoes(cliente)}\n\nTexto do documento:\n<<<\n"
        f"{texto[:MAX_CARACTERES_TEXTO]}\n>>>"
    )
    return _perguntar(MODELO_TEXTO, {"role": "user", "content": conteudo})


def extrair_imagem(imagem: Image.Image, cliente: str | None = None) -> ExtracaoLLM:
    conteudo = f"{_instrucoes(cliente)}\n\nO documento está na imagem."
    return _perguntar(
        MODELO_VISAO,
        {"role": "user", "content": conteudo, "images": [_imagem_para_png(imagem)]},
    )


def verificar_ollama() -> list[str]:
    """Devolve os modelos configurados que ainda não foram baixados.

    Lança exceção se o Ollama não estiver rodando.
    """
    instalados = {m.model for m in _ollama.list().models}
    return [
        modelo
        for modelo in (MODELO_TEXTO, MODELO_VISAO)
        if modelo not in instalados and f"{modelo}:latest" not in instalados
    ]
