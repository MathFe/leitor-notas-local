"""Testes simples. Rode com `python test_validacao.py` ou `pytest`."""
from datetime import date

from modelos import Registro
from validacao import (
    formatar_cnpj,
    validar_chave_acesso,
    validar_cnpj,
    validar_registro,
)


def test_cnpj_validos():
    assert validar_cnpj("11.222.333/0001-81")
    assert validar_cnpj("11222333000181")
    assert validar_cnpj("00.000.000/0001-91")  # Banco do Brasil
    assert validar_cnpj("12.ABC.345/01DE-35")  # exemplo alfanumérico da Receita


def test_cnpj_invalidos():
    assert not validar_cnpj("11.222.333/0001-82")  # DV errado
    assert not validar_cnpj("11.111.111/1111-11")  # todos iguais
    assert not validar_cnpj("1122233300018")       # 13 dígitos
    assert not validar_cnpj("")
    assert not validar_cnpj(None)


def test_formatar_cnpj():
    assert formatar_cnpj("11222333000181") == "11.222.333/0001-81"
    assert formatar_cnpj("  ") is None


def test_chave_acesso():
    # Monta uma chave com DV correto a partir de 43 dígitos quaisquer
    base = "3526101122233300018155001000000123100000123"
    chave = next(base + str(dv) for dv in range(10) if validar_chave_acesso(base + str(dv)))
    assert validar_chave_acesso(chave)
    assert validar_chave_acesso(" ".join(chave[i:i + 4] for i in range(0, 44, 4)))
    errada = chave[:-1] + str((int(chave[-1]) + 1) % 10)
    assert not validar_chave_acesso(errada)
    assert not validar_chave_acesso("123")


def test_registro_ok_e_fora_da_competencia():
    base = dict(arquivo="x.pdf", tipo="recibo", valor=100.0, categoria="Aluguel",
                cnpj_contraparte="11.222.333/0001-81")
    ok = validar_registro(Registro(**base, data=date(2026, 10, 5)), "2026-10")
    assert not ok.revisar and ok.motivo_revisao is None

    fora = validar_registro(Registro(**base, data=date(2026, 9, 30)), "2026-10")
    assert fora.revisar and "fora da competência" in fora.motivo_revisao


def test_registro_com_varios_problemas():
    r = validar_registro(
        Registro(arquivo="y.jpg", valor=0, categoria="Viagem", cnpj_contraparte="11.222.333/0001-80"),
        "2026-10",
        ["erro no processamento: teste"],
    )
    assert r.revisar
    for trecho in ("erro no processamento", "valor", "data", "categoria", "CNPJ"):
        assert trecho in r.motivo_revisao


if __name__ == "__main__":
    for nome, funcao in list(globals().items()):
        if nome.startswith("test_"):
            funcao()
            print(f"ok  {nome}")
    print("Todos os testes passaram.")
