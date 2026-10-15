"""Modelos de dados, lista de categorias e configuração central.

Para trocar de modelo ou de servidor, altere SOMENTE as constantes abaixo.
"""
from datetime import date
from typing import Literal, Optional

from pydantic import BaseModel, Field

# ---------------------------------------------------------------------------
# Configuração (único lugar)
# ---------------------------------------------------------------------------
OLLAMA_HOST = "http://localhost:11434"  # só localhost: nada sai da máquina
MODELO_TEXTO = "qwen2.5:3b"
MODELO_VISAO = "qwen2.5vl:7b"

MIN_CARACTERES_PDF_TEXTO = 50  # acima disso o PDF é tratado como "pdf_texto"
LADO_MAXIMO_IMAGEM = 1280      # px; imagens maiores são reduzidas (mais rápido)
MAX_CARACTERES_TEXTO = 6000    # texto enviado ao LLM é cortado aqui
CONTEXTO_LLM = 8192            # num_ctx do Ollama

# ---------------------------------------------------------------------------
# Listas fixas
# ---------------------------------------------------------------------------
CATEGORIAS = [
    "Aluguel",
    "Energia, água e telefone",
    "Combustível e transporte",
    "Matéria-prima e insumos",
    "Material de escritório e limpeza",
    "Manutenção e reparos",
    "Serviços de terceiros",
    "Alimentação",
    "Impostos e taxas",
    "Equipamentos",
    "Receita (entrada)",
    "Outros",
]

# Dicas curtas que vão no prompt para o modelo pequeno acertar a categoria
DICAS_CATEGORIAS = {
    "Aluguel": "aluguel de sala, loja, galpão, condomínio",
    "Energia, água e telefone": "conta de luz, água, internet, celular",
    "Combustível e transporte": "posto de gasolina, Uber, frete, estacionamento, pedágio",
    "Matéria-prima e insumos": "usado para FABRICAR o produto ou PRESTAR o serviço da empresa: tecido, linha, "
                               "ingredientes, cremes e óleos de estética, embalagens, mercadoria para revenda",
    "Material de escritório e limpeza": "papel, caneta, toner, pastas, desinfetante, papel toalha, produtos de "
                                        "limpeza (papelaria é sempre esta categoria)",
    "Manutenção e reparos": "conserto, limpeza ou recarga de máquina e ar-condicionado, reforma, pintura, "
                            "eletricista, encanador",
    "Serviços de terceiros": "contador, gráfica e impressão, designer, marketing, advogado, serviço prestado "
                             "por empresa",
    "Alimentação": "restaurante, lanche, mercado para consumo",
    "Impostos e taxas": "DAS, guia de imposto, tarifa bancária, taxa de prefeitura",
    "Equipamentos": "máquina, computador, ferramenta, móvel (bem durável)",
    "Receita (entrada)": "dinheiro que a empresa RECEBEU",
    "Outros": "quando nada acima serve",
}

TIPOS = ["nfe", "nfce", "pix_enviado", "pix_recebido", "recibo", "outro"]
CAMINHOS = ["pdf_texto", "imagem_visao"]

TipoDocumento = Literal["nfe", "nfce", "pix_enviado", "pix_recebido", "recibo", "outro"]
Caminho = Literal["pdf_texto", "imagem_visao"]


# O que pedimos ao modelo. Vai como JSON Schema no parâmetro `format` do Ollama.
# - `data` é texto de propósito: se o modelo errar o formato, o Python marca
#   para revisão em vez de quebrar.
# - O modelo só COPIA quem recebeu e quem pagou; quem é a contraparte o Python decide
#   (modelos pequenos erram mais quando precisam raciocinar sobre papéis).
# - A categoria NÃO vem daqui: é uma segunda chamada curta (classificar_categoria),
#   que acerta bem mais que pedir tudo num prompt só.
class ExtracaoLLM(BaseModel):
    tipo: TipoDocumento
    data: Optional[str] = Field(description="Data no formato AAAA-MM-DD")
    valor: Optional[float] = Field(description="Valor total, ex.: 1234.56")
    quem_recebeu_nome: str = Field(description="Emitente da nota / recebedor do Pix / quem assinou o recibo")
    quem_recebeu_cnpj: Optional[str]
    quem_pagou_nome: str = Field(description="Destinatário da nota / pagador do Pix")
    quem_pagou_cnpj: Optional[str]
    chave_acesso: Optional[str]
    descricao: str


class Registro(BaseModel):
    """Um registro por documento (linha da planilha final)."""

    arquivo: str
    tipo: TipoDocumento = "outro"
    data: Optional[date] = None
    valor: Optional[float] = None
    contraparte: str = ""
    cnpj_contraparte: Optional[str] = None
    chave_acesso: Optional[str] = None
    descricao: str = ""
    categoria: str = "Outros"  # str: pode vir editada da interface; validacao.py confere
    caminho: Optional[Caminho] = None
    revisar: bool = False
    motivo_revisao: Optional[str] = None
    tempo_processamento_s: float = 0.0
