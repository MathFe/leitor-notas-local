"""Compara a saída do pipeline com o gabarito e mostra a acurácia por campo.

Uso:
    python avaliar.py                       # procura ../amostras-mariana
    python avaliar.py --amostras CAMINHO --competencia 2026-10

Formato aceito para gabarito.json (qualquer um destes):
    [{"arquivo": "01_x.pdf", "data": "2026-10-03", "valor": 150.0, ...}, ...]
    {"01_x.pdf": {"data": ...}, ...}
    {"competencia": "2026-10", "documentos": [...]}
Campos comparados (os ausentes no gabarito são ignorados):
    data, valor (tolerância R$ 0,01), cnpj_contraparte (ou "cnpj"), categoria, caminho, revisar
"""
import argparse
import json
import sys
from collections import Counter
from pathlib import Path

from modelos import Registro
from pipeline import checar_ollama_ou_sair, imprimir_registro, listar_documentos, processar_arquivo
from validacao import normalizar_cnpj

DOCUMENTOS_QUE_DEVEM_REVISAR = ("09", "10")  # prefixo do nome do arquivo


def localizar_amostras() -> Path:
    for candidato in (Path("amostras-mariana"), Path(__file__).resolve().parent.parent / "amostras-mariana"):
        if candidato.is_dir():
            return candidato
    sys.exit("Pasta amostras-mariana não encontrada. Use --amostras CAMINHO.")


def carregar_gabarito(caminho: Path) -> tuple[dict[str, dict], str | None, str | None]:
    """Devolve (documentos por arquivo, competência, cliente)."""
    dados = json.loads(caminho.read_text(encoding="utf-8"))
    competencia = cliente = None
    if isinstance(dados, dict) and "documentos" in dados:
        competencia = dados.get("competencia")
        cliente = dados.get("cliente")
        if isinstance(cliente, dict):
            cliente = f"{cliente.get('nome', '')} (CNPJ {cliente.get('cnpj', '')})"
        dados = dados["documentos"]
    if isinstance(dados, list):
        dados = {d["arquivo"]: d for d in dados}
    return dados, competencia, cliente


def deduzir_competencia(gabarito: dict[str, dict]) -> str:
    meses = Counter(str(d["data"])[:7] for d in gabarito.values() if d.get("data"))
    if not meses:
        sys.exit("Não deu para deduzir a competência. Use --competencia AAAA-MM.")
    return meses.most_common(1)[0][0]


# Cada comparador recebe (registro, valor_esperado) e devolve (acertou, valor_obtido)
COMPARADORES = {
    "data": lambda r, e: (str(r.data) == str(e)[:10], r.data),
    "valor": lambda r, e: (
        r.valor is None if e is None else r.valor is not None and abs(r.valor - float(e)) <= 0.01,
        r.valor,
    ),
    "cnpj": lambda r, e: (normalizar_cnpj(r.cnpj_contraparte) == normalizar_cnpj(e), r.cnpj_contraparte),
    "categoria": lambda r, e: (r.categoria.strip().casefold() == str(e).strip().casefold(), r.categoria),
    "caminho": lambda r, e: (r.caminho == e, r.caminho),
    "revisar": lambda r, e: (r.revisar == bool(e), r.revisar),
}


# Nomes alternativos aceitos no gabarito
APELIDOS = {
    "cnpj": ("cnpj_contraparte", "cnpj"),
    "caminho": ("caminho", "caminho_esperado"),
    "revisar": ("revisar", "deve_revisar"),
}


def esperado(gabarito_doc: dict, campo: str):
    """Devolve (tem_o_campo, valor)."""
    for chave in APELIDOS.get(campo, (campo,)):
        if chave in gabarito_doc:
            return True, gabarito_doc[chave]
    return False, None


def avaliar_documento(registro: Registro, gabarito_doc: dict) -> dict[str, bool | None]:
    resultado = {}
    for campo, comparar in COMPARADORES.items():
        tem, valor_esperado = esperado(gabarito_doc, campo)
        if not tem:
            resultado[campo] = None
            continue
        acertou, obtido = comparar(registro, valor_esperado)
        resultado[campo] = acertou
        if not acertou:
            print(f"           x {campo}: esperado {valor_esperado!r}, obtido {obtido!r}")
    return resultado


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--amostras", type=Path, help="pasta com documentos/ e gabarito.json")
    parser.add_argument("--competencia", help="AAAA-MM (padrão: deduzida do gabarito)")
    parser.add_argument("--cliente", help="nome ou CNPJ da empresa cliente")
    parser.add_argument("--saida", type=Path, help="salva os registros obtidos em JSON")
    args = parser.parse_args()
    sys.stdout.reconfigure(encoding="utf-8")

    amostras = args.amostras or localizar_amostras()
    pasta_docs = amostras / "documentos"
    arquivo_gabarito = next(
        (p for p in (amostras / "gabarito.json", pasta_docs / "gabarito.json") if p.exists()), None
    )
    if not arquivo_gabarito:
        sys.exit(f"gabarito.json não encontrado em {amostras}")
    gabarito, competencia_gabarito, cliente_gabarito = carregar_gabarito(arquivo_gabarito)
    competencia = args.competencia or competencia_gabarito or deduzir_competencia(gabarito)
    cliente = args.cliente or cliente_gabarito

    documentos = [p for p in listar_documentos(pasta_docs) if p.name in gabarito]
    for nome in sorted(set(gabarito) - {p.name for p in documentos}):
        print(f"aviso: {nome} está no gabarito mas não na pasta")

    checar_ollama_ou_sair()
    print(f"Competência {competencia} | cliente: {cliente or '-'} | {len(documentos)} documentos\n")

    registros, resultados = [], []
    for i, caminho in enumerate(documentos, start=1):
        registro = processar_arquivo(caminho, competencia, cliente)
        imprimir_registro(i, len(documentos), registro)
        registros.append(registro)
        resultados.append(avaliar_documento(registro, gabarito[caminho.name]))

    # ---- Tabela por documento ----
    campos = list(COMPARADORES)
    simbolo = {True: "ok", False: "X", None: "-"}
    print("\n" + f"{'documento':34}" + "".join(f"{c:>10}" for c in campos) + f"{'tempo':>9}")
    for registro, resultado in zip(registros, resultados):
        print(
            f"{registro.arquivo[:34]:34}"
            + "".join(f"{simbolo[resultado[c]]:>10}" for c in campos)
            + f"{registro.tempo_processamento_s:8.1f}s"
        )

    # ---- Totais por campo ----
    print("\nAcurácia por campo:")
    acertos_total = comparados_total = 0
    for campo in campos:
        valores = [r[campo] for r in resultados if r[campo] is not None]
        acertos, n = sum(valores), len(valores)
        acertos_total, comparados_total = acertos_total + acertos, comparados_total + n
        porcentagem = f"{100 * acertos / n:5.1f}%" if n else "  sem dados"
        print(f"  {campo:10} {acertos:>3}/{n:<3} {porcentagem}")
    if comparados_total:
        print(f"  {'TOTAL':10} {acertos_total:>3}/{comparados_total:<3} {100 * acertos_total / comparados_total:5.1f}%")

    for rota in ("pdf_texto", "imagem_visao"):
        tempos = [r.tempo_processamento_s for r in registros if r.caminho == rota]
        if tempos:
            print(f"  tempo médio {rota}: {sum(tempos) / len(tempos):.1f}s ({len(tempos)} docs)")

    # ---- Regra obrigatória: 09 e 10 precisam terminar em revisão ----
    falhou = False
    print("\nDocumentos que DEVEM ir para revisão:")
    for registro in registros:
        if registro.arquivo.startswith(DOCUMENTOS_QUE_DEVEM_REVISAR):
            status = "OK" if registro.revisar else "FALHOU"
            falhou |= not registro.revisar
            print(f"  {status:6} {registro.arquivo} -> {registro.motivo_revisao or 'sem motivo'}")

    if args.saida:
        args.saida.write_text(
            json.dumps([r.model_dump(mode="json") for r in registros], ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        print(f"\nRegistros salvos em {args.saida}")
    return 1 if falhou else 0


if __name__ == "__main__":
    sys.exit(main())
