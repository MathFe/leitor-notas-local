"""Pipeline: detecta o tipo do arquivo, extrai com o modelo certo e valida.

Uso no terminal:
    python pipeline.py ../amostras-mariana/documentos --competencia 2026-10
"""
import argparse
import json
import re
import sys
import time
from datetime import date, datetime
from pathlib import Path
from typing import Callable

from extratores import (
    carregar_imagem,
    classificar_categoria,
    extrair_imagem,
    extrair_pdf_texto,
    ler_texto_pdf,
    renderizar_pdf,
    verificar_ollama,
)
from modelos import MIN_CARACTERES_PDF_TEXTO, ExtracaoLLM, Registro
from validacao import (
    cnpj_da_chave,
    formatar_cnpj,
    ler_competencia,
    normalizar_cnpj,
    validar_chave_acesso,
    validar_registro,
)

EXTENSOES_IMAGEM = {".jpg", ".jpeg", ".png"}
EXTENSOES_ACEITAS = EXTENSOES_IMAGEM | {".pdf"}


def detectar_tipo(caminho: Path) -> tuple[str, str | None]:
    """Decide o caminho do documento. Devolve (caminho, texto_do_pdf_ou_None)."""
    extensao = caminho.suffix.lower()
    if extensao == ".pdf":
        texto = ler_texto_pdf(caminho)
        if len(texto.strip()) > MIN_CARACTERES_PDF_TEXTO:
            return "pdf_texto", texto
        return "imagem_visao", None  # PDF escaneado
    if extensao in EXTENSOES_IMAGEM:
        return "imagem_visao", None
    raise ValueError(f"formato não suportado: {extensao or 'sem extensão'}")


def interpretar_data(texto: str | None) -> date | None:
    for formato in ("%Y-%m-%d", "%d/%m/%Y", "%d-%m-%Y"):
        try:
            return datetime.strptime((texto or "").strip()[:10], formato).date()
        except ValueError:
            pass
    return None


def _limpar(texto: str | None) -> str | None:
    """Modelos às vezes devolvem a palavra "null" em vez de null."""
    texto = (texto or "").strip()
    return None if texto.lower() in ("", "null", "none", "n/a", "-") else texto


def _so_cnpj(texto: str | None) -> str | None:
    """Descarta CPF (11 dígitos ou mascarado, ex.: ***.482.917-**) que o modelo pôs no lugar do CNPJ."""
    texto = _limpar(texto)
    if texto is None or "*" in texto or len(normalizar_cnpj(texto)) == 11:
        return None
    return texto


def procurar_chave_acesso(texto: str) -> str | None:
    """Acha a chave de 44 dígitos no texto do PDF (mais confiável que o LLM copiar)."""
    for linha in texto.splitlines():
        for candidata in re.findall(r"\d{44}", re.sub(r"[\s.]", "", linha)):
            if validar_chave_acesso(candidata):
                return candidata
    return None


def eh_entrada(extracao: ExtracaoLLM, cnpj_recebeu: str | None, cnpj_pagou: str | None,
               cliente: str | None) -> bool:
    """Dinheiro entrou na empresa? Se o CNPJ do cliente aparece no documento, ele decide."""
    achado = re.search(r"[0-9A-Za-z]{2}\.?[0-9A-Za-z]{3}\.?[0-9A-Za-z]{3}/?[0-9A-Za-z]{4}-?\d{2}", cliente or "")
    if achado:
        cnpj_cliente = normalizar_cnpj(achado.group())
        if normalizar_cnpj(cnpj_recebeu) == cnpj_cliente:
            return True
        if normalizar_cnpj(cnpj_pagou) == cnpj_cliente:
            return False
    return extracao.tipo == "pix_recebido"


def montar_registro(arquivo: str, caminho: str, extracao: ExtracaoLLM, texto: str | None,
                    cliente: str | None = None) -> Registro:
    """Converte a resposta do modelo em Registro. A categoria das despesas fica como
    "Outros" aqui e é preenchida depois por classificar_categoria()."""
    chave = None
    if extracao.tipo in ("nfe", "nfce"):
        chave = re.sub(r"\D", "", extracao.chave_acesso or "") or None
        if texto:
            chave = procurar_chave_acesso(texto) or chave

    recebeu = (_limpar(extracao.quem_recebeu_nome), _so_cnpj(extracao.quem_recebeu_cnpj))
    pagou = (_limpar(extracao.quem_pagou_nome), _so_cnpj(extracao.quem_pagou_cnpj))

    # Na nota, quem recebeu é o emitente, e o CNPJ do emitente está dentro da chave.
    # Se o modelo trocou os papéis, a chave mostra e nós destrocamos.
    if chave and validar_chave_acesso(chave):
        emitente = cnpj_da_chave(chave)
        if normalizar_cnpj(pagou[1]) == emitente != normalizar_cnpj(recebeu[1]):
            recebeu, pagou = pagou, recebeu
        if not recebeu[1]:
            recebeu = (recebeu[0], emitente)

    # Entrada de dinheiro: a contraparte é quem pagou. Saída: quem recebeu.
    entrada = eh_entrada(extracao, recebeu[1], pagou[1], cliente)
    contraparte, cnpj = pagou if entrada else recebeu

    return Registro(
        arquivo=arquivo,
        tipo=extracao.tipo,
        data=interpretar_data(extracao.data),
        valor=extracao.valor,
        contraparte=contraparte or "",
        cnpj_contraparte=formatar_cnpj(cnpj),
        chave_acesso=chave,
        descricao=extracao.descricao.strip(),
        categoria="Receita (entrada)" if entrada else "Outros",
        caminho=caminho,
    )


def processar_arquivo(caminho, competencia: str, cliente: str | None = None) -> Registro:
    """Processa um documento. Nunca lança exceção: erros viram `revisar = True`."""
    caminho = Path(caminho)
    inicio = time.perf_counter()
    rota = None
    try:
        rota, texto = detectar_tipo(caminho)
        if rota == "pdf_texto":
            extracao = extrair_pdf_texto(texto, cliente)
        else:
            imagem = renderizar_pdf(caminho) if caminho.suffix.lower() == ".pdf" else carregar_imagem(caminho)
            extracao = extrair_imagem(imagem, cliente)
        registro = montar_registro(caminho.name, rota, extracao, texto, cliente)
        if registro.categoria != "Receita (entrada)":
            registro.categoria = classificar_categoria(registro.descricao, registro.contraparte, registro.tipo)
        erros = []
    except Exception as erro:  # um documento ruim não derruba o lote
        registro = Registro(arquivo=caminho.name, caminho=rota)
        erros = [f"erro no processamento: {type(erro).__name__}: {erro}"]
    registro.tempo_processamento_s = round(time.perf_counter() - inicio, 2)
    return validar_registro(registro, competencia, erros)


def listar_documentos(pasta) -> list[Path]:
    return sorted(p for p in Path(pasta).iterdir() if p.suffix.lower() in EXTENSOES_ACEITAS)


def processar_pasta(
    pasta,
    competencia: str,
    cliente: str | None = None,
    ao_progredir: Callable[[int, int, Registro], None] | None = None,
) -> list[Registro]:
    ler_competencia(competencia)  # falha cedo se a competência estiver errada
    arquivos = listar_documentos(pasta)
    registros = []
    for i, arquivo in enumerate(arquivos, start=1):
        registro = processar_arquivo(arquivo, competencia, cliente)
        registros.append(registro)
        if ao_progredir:
            ao_progredir(i, len(arquivos), registro)
    return registros


def checar_ollama_ou_sair() -> None:
    try:
        faltando = verificar_ollama()
    except Exception as erro:
        sys.exit(f"Ollama não respondeu em localhost ({erro}). Ele está aberto?")
    if faltando:
        sys.exit("Modelos não encontrados. Rode: " + " && ".join(f"ollama pull {m}" for m in faltando))


def imprimir_registro(i: int, total: int, r: Registro) -> None:
    valor = f"{r.valor:10.2f}" if r.valor is not None else " " * 10
    print(
        f"[{i:>3}/{total}] {r.arquivo[:32]:32} {r.caminho or '-':12} {r.data or '-'!s:10} "
        f"{valor} {r.categoria[:26]:26} {r.tempo_processamento_s:5.1f}s"
    )
    if r.revisar:
        print(f"           REVISAR: {r.motivo_revisao}")


def main() -> None:
    parser = argparse.ArgumentParser(description="Lê notas e comprovantes de uma pasta.")
    parser.add_argument("pasta")
    parser.add_argument("--competencia", required=True, help="AAAA-MM, ex.: 2026-10")
    parser.add_argument("--cliente", help="nome ou CNPJ da empresa cliente (ajuda no Pix)")
    parser.add_argument("--saida", help="salva o resultado em JSON")
    args = parser.parse_args()

    sys.stdout.reconfigure(encoding="utf-8")
    checar_ollama_ou_sair()
    registros = processar_pasta(args.pasta, args.competencia, args.cliente, imprimir_registro)

    revisar = sum(r.revisar for r in registros)
    tempo = sum(r.tempo_processamento_s for r in registros)
    print(f"\n{len(registros)} documentos, {revisar} para revisar, {tempo:.1f}s no total.")
    if args.saida:
        Path(args.saida).write_text(
            json.dumps([r.model_dump(mode="json") for r in registros], ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        print(f"Resultado salvo em {args.saida}")


if __name__ == "__main__":
    main()
