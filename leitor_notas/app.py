"""Interface Streamlit. Rode com: streamlit run app.py"""
import io
import tempfile
from datetime import date
from pathlib import Path

import pandas as pd
import streamlit as st

from extratores import verificar_ollama
from modelos import CATEGORIAS, MODELO_TEXTO, MODELO_VISAO, TIPOS, Registro
from pipeline import processar_arquivo
from validacao import ler_competencia, validar_registro

st.set_page_config(page_title="Leitor de notas", page_icon="🧾", layout="wide")

CAMPOS = list(Registro.model_fields)

CONFIG_COLUNAS = {
    "status": st.column_config.TextColumn("", disabled=True, width="small"),
    "arquivo": st.column_config.TextColumn("Arquivo", disabled=True),
    "tipo": st.column_config.SelectboxColumn("Tipo", options=TIPOS, required=True),
    "data": st.column_config.DateColumn("Data", format="DD/MM/YYYY"),
    "valor": st.column_config.NumberColumn("Valor", format="R$ %.2f", min_value=0.0, step=0.01),
    "contraparte": st.column_config.TextColumn("Contraparte"),
    "cnpj_contraparte": st.column_config.TextColumn("CNPJ"),
    "chave_acesso": st.column_config.TextColumn("Chave de acesso"),
    "descricao": st.column_config.TextColumn("Descrição"),
    "categoria": st.column_config.SelectboxColumn("Categoria", options=CATEGORIAS, required=True),
    "caminho": st.column_config.TextColumn("Caminho", disabled=True),
    "revisar": st.column_config.CheckboxColumn("Revisar?"),
    "motivo_revisao": st.column_config.TextColumn("Motivo da revisão", width="large"),
    "tempo_processamento_s": st.column_config.NumberColumn("Tempo (s)", format="%.1f", disabled=True),
}

NOMES_EXCEL = {
    "arquivo": "Arquivo", "tipo": "Tipo", "data": "Data", "valor": "Valor (R$)",
    "contraparte": "Contraparte", "cnpj_contraparte": "CNPJ", "chave_acesso": "Chave de acesso",
    "descricao": "Descrição", "categoria": "Categoria", "caminho": "Caminho",
    "revisar": "Revisar", "motivo_revisao": "Motivo da revisão",
    "tempo_processamento_s": "Tempo (s)",
}


# ---------------------------------------------------------------------------
# Conversões tabela <-> registros
# ---------------------------------------------------------------------------
def registros_para_tabela(registros: list[Registro]) -> pd.DataFrame:
    registros = sorted(registros, key=lambda r: (not r.revisar, r.arquivo))  # revisar primeiro
    tabela = pd.DataFrame([r.model_dump() for r in registros], columns=CAMPOS)
    tabela.insert(0, "status", ["🔴 revisar" if r.revisar else "🟢 ok" for r in registros])
    return tabela


def _vazio_para_none(valor):
    if valor is None or (not isinstance(valor, str) and pd.isna(valor)):
        return None
    if isinstance(valor, pd.Timestamp):
        return valor.date()
    return valor


def tabela_para_registros(tabela: pd.DataFrame) -> list[Registro]:
    return [
        Registro(**{campo: _vazio_para_none(linha[campo]) for campo in CAMPOS})
        for linha in tabela.to_dict("records")
    ]


def gerar_excel(tabela: pd.DataFrame) -> bytes:
    planilha = tabela.drop(columns="status").rename(columns=NOMES_EXCEL)
    planilha["Data"] = pd.to_datetime(planilha["Data"], errors="coerce")
    resumo = (
        planilha.groupby("Categoria", as_index=False)["Valor (R$)"].sum()
        .sort_values("Valor (R$)", ascending=False)
    )

    buffer = io.BytesIO()
    with pd.ExcelWriter(buffer, engine="openpyxl", date_format="DD/MM/YYYY",
                        datetime_format="DD/MM/YYYY") as excel:
        planilha.to_excel(excel, sheet_name="Lançamentos", index=False)
        resumo.to_excel(excel, sheet_name="Resumo por categoria", index=False)
        for nome, dados in (("Lançamentos", planilha), ("Resumo por categoria", resumo)):
            folha = excel.sheets[nome]
            folha.freeze_panes = "A2"
            folha.auto_filter.ref = folha.dimensions
            for i, coluna in enumerate(dados.columns, start=1):
                letra = folha.cell(row=1, column=i).column_letter
                largura = max([len(str(coluna))] + [len(str(v)) for v in dados[coluna].head(200)])
                folha.column_dimensions[letra].width = min(largura + 2, 60)
                if coluna == "Valor (R$)":
                    for celula in folha[letra][1:]:
                        celula.number_format = '"R$" #,##0.00'
    return buffer.getvalue()


# ---------------------------------------------------------------------------
# Barra lateral
# ---------------------------------------------------------------------------
with st.sidebar:
    st.header("Configuração")
    competencia = st.text_input("Competência (AAAA-MM)", value=date.today().strftime("%Y-%m"))
    cliente = st.text_input(
        "Empresa cliente (opcional)",
        help="Nome ou CNPJ. Ajuda o modelo a saber se o Pix foi enviado ou recebido.",
    )
    st.divider()
    try:
        faltando = verificar_ollama()
        if faltando:
            st.warning("Modelos não baixados:\n\n" + "\n\n".join(f"`ollama pull {m}`" for m in faltando))
        else:
            st.success(f"Ollama ok\n\n{MODELO_TEXTO} · {MODELO_VISAO}")
    except Exception:
        st.error("Ollama não está rodando em localhost:11434.")
    st.caption("🔒 Tudo roda nesta máquina. Nenhum documento sai do computador.")

# ---------------------------------------------------------------------------
# Página principal
# ---------------------------------------------------------------------------
st.title("🧾 Leitor de notas e comprovantes")

if "versao" not in st.session_state:
    st.session_state.versao = 0

arquivos = st.file_uploader(
    "Notas fiscais, cupons, comprovantes de Pix e recibos",
    type=["pdf", "jpg", "jpeg", "png"],
    accept_multiple_files=True,
)

if st.button("Processar", type="primary", disabled=not arquivos):
    try:
        ler_competencia(competencia)
    except ValueError as erro:
        st.error(str(erro))
        st.stop()

    barra = st.progress(0.0)
    registros = []
    with tempfile.TemporaryDirectory() as pasta:
        for i, enviado in enumerate(arquivos):
            barra.progress(i / len(arquivos), text=f"Lendo {enviado.name} ({i + 1}/{len(arquivos)})")
            destino = Path(pasta) / Path(enviado.name).name
            destino.write_bytes(enviado.getvalue())
            registros.append(processar_arquivo(destino, competencia, cliente.strip() or None))
    barra.progress(1.0, text=f"{len(registros)} documentos processados")

    st.session_state.tabela = registros_para_tabela(registros)
    st.session_state.versao += 1

if "tabela" in st.session_state:
    tabela = st.session_state.tabela

    despesas = tabela.loc[tabela["categoria"] != "Receita (entrada)", "valor"].sum()
    receitas = tabela.loc[tabela["categoria"] == "Receita (entrada)", "valor"].sum()
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Documentos", len(tabela))
    c2.metric("Para revisar", int(tabela["revisar"].sum()))
    c3.metric("Despesas", f"R$ {despesas:,.2f}".replace(",", "X").replace(".", ",").replace("X", "."))
    c4.metric("Receitas", f"R$ {receitas:,.2f}".replace(",", "X").replace(".", ",").replace("X", "."))

    editada = st.data_editor(
        tabela,
        key=f"editor_{st.session_state.versao}",
        column_config=CONFIG_COLUNAS,
        hide_index=True,
        num_rows="fixed",
        width="stretch",
    )

    b1, b2, _ = st.columns([1, 1, 3])
    if b1.button("Revalidar edições", help="Roda as validações de novo depois de corrigir a tabela."):
        try:
            registros = [validar_registro(r, competencia) for r in tabela_para_registros(editada)]
        except ValueError as erro:
            st.error(str(erro))
        else:
            st.session_state.tabela = registros_para_tabela(registros)
            st.session_state.versao += 1
            st.rerun()

    b2.download_button(
        "Exportar Excel",
        data=gerar_excel(editada),
        file_name=f"lancamentos_{competencia}.xlsx",
        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        type="primary",
    )
