"""Validações feitas em Python. Não confiamos só no modelo."""
import re
from datetime import date

from modelos import CATEGORIAS, Registro

_PESOS_CNPJ_1 = [5, 4, 3, 2, 9, 8, 7, 6, 5, 4, 3, 2]
_PESOS_CNPJ_2 = [6] + _PESOS_CNPJ_1


# ---------------------------------------------------------------------------
# CNPJ (numérico e o novo alfanumérico, válido a partir de julho/2026)
# ---------------------------------------------------------------------------
def normalizar_cnpj(cnpj: str | None) -> str:
    """Remove pontuação e espaços: '11.222.333/0001-81' -> '11222333000181'."""
    return re.sub(r"[^0-9A-Za-z]", "", cnpj or "").upper()


def _digito_cnpj(base: str, pesos: list[int]) -> str:
    # Cada caractere vale (código ASCII - 48): '0'..'9' -> 0..9, 'A' -> 17, ...
    soma = sum((ord(c) - 48) * p for c, p in zip(base, pesos))
    resto = soma % 11
    return "0" if resto < 2 else str(11 - resto)


def validar_cnpj(cnpj: str | None) -> bool:
    c = normalizar_cnpj(cnpj)
    if not re.fullmatch(r"[0-9A-Z]{12}[0-9]{2}", c):
        return False
    if len(set(c)) == 1:  # 00000000000000, 11111111111111...
        return False
    dv1 = _digito_cnpj(c[:12], _PESOS_CNPJ_1)
    dv2 = _digito_cnpj(c[:12] + dv1, _PESOS_CNPJ_2)
    return c[12:] == dv1 + dv2


def formatar_cnpj(cnpj: str | None) -> str | None:
    """'11222333000181' -> '11.222.333/0001-81'. Mantém como veio se não tiver 14 caracteres."""
    if not cnpj or not cnpj.strip():
        return None
    c = normalizar_cnpj(cnpj)
    if len(c) != 14:
        return cnpj.strip()
    return f"{c[:2]}.{c[2:5]}.{c[5:8]}/{c[8:12]}-{c[12:]}"


# ---------------------------------------------------------------------------
# Chave de acesso NF-e / NFC-e (44 dígitos, DV módulo 11)
# ---------------------------------------------------------------------------
def validar_chave_acesso(chave: str | None) -> bool:
    c = re.sub(r"\D", "", chave or "")
    if len(c) != 44:
        return False
    soma, peso = 0, 2
    for digito in reversed(c[:43]):
        soma += int(digito) * peso
        peso = 2 if peso == 9 else peso + 1
    resto = soma % 11
    dv = 0 if resto < 2 else 11 - resto
    return int(c[43]) == dv


def cnpj_da_chave(chave: str) -> str:
    """CNPJ do emitente: posições 7 a 20 da chave de acesso."""
    return re.sub(r"\D", "", chave)[6:20]


# ---------------------------------------------------------------------------
# Competência e registro completo
# ---------------------------------------------------------------------------
def ler_competencia(competencia: str) -> tuple[int, int]:
    """'2026-10' -> (2026, 10). Lança ValueError se o formato estiver errado."""
    m = re.fullmatch(r"(\d{4})-(\d{2})", (competencia or "").strip())
    if not m or not 1 <= int(m.group(2)) <= 12:
        raise ValueError(f"competência inválida: {competencia!r} (use AAAA-MM, ex.: 2026-10)")
    return int(m.group(1)), int(m.group(2))


def encontrar_problemas(registro: Registro, competencia: str) -> list[str]:
    """Lista os motivos para revisão. Lista vazia = registro ok."""
    ano, mes = ler_competencia(competencia)
    problemas = []

    if registro.valor is None or registro.valor <= 0:
        problemas.append("valor ausente ou não positivo")

    if not isinstance(registro.data, date):
        problemas.append("data ausente ou inválida")
    elif (registro.data.year, registro.data.month) != (ano, mes):
        problemas.append(
            f"data {registro.data:%d/%m/%Y} fora da competência {mes:02d}/{ano}"
        )

    if registro.categoria not in CATEGORIAS:
        problemas.append(f"categoria fora da lista: {registro.categoria!r}")

    entrada = registro.tipo == "pix_recebido" or registro.categoria == "Receita (entrada)"
    if registro.cnpj_contraparte and not validar_cnpj(registro.cnpj_contraparte):
        problemas.append(f"CNPJ {registro.cnpj_contraparte} inválido (dígito verificador)")
    elif not registro.cnpj_contraparte and not entrada:
        # Despesa paga a pessoa física ou sem identificação: conferir dedutibilidade/retenções
        problemas.append("despesa sem CNPJ do fornecedor")

    if registro.tipo in ("nfe", "nfce"):
        if not registro.chave_acesso:
            problemas.append("nota fiscal sem chave de acesso")
        elif not validar_chave_acesso(registro.chave_acesso):
            problemas.append("chave de acesso inválida")
        elif (
            registro.cnpj_contraparte
            and registro.categoria != "Receita (entrada)"
            and normalizar_cnpj(registro.cnpj_contraparte) != cnpj_da_chave(registro.chave_acesso)
        ):
            problemas.append("CNPJ diferente do emitente da chave de acesso")

    if registro.tipo == "pix_recebido" and registro.categoria != "Receita (entrada)":
        problemas.append("Pix recebido com categoria de despesa")

    return problemas


def validar_registro(
    registro: Registro, competencia: str, motivos_extras: list[str] | None = None
) -> Registro:
    """Devolve uma cópia do registro com `revisar` e `motivo_revisao` preenchidos."""
    motivos = list(motivos_extras or []) + encontrar_problemas(registro, competencia)
    return registro.model_copy(
        update={
            "revisar": bool(motivos),
            "motivo_revisao": "; ".join(motivos) if motivos else None,
        }
    )
