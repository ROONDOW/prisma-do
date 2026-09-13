# -*- coding: utf-8 -*-
import pytest

from prisma import normalizar as n


@pytest.mark.parametrize("texto,esperado", [
    ("R$ 10.000.000,00", 10_000_000.0),
    ("Limite: R$ 10 milhões", 10_000_000.0),
    ("R$ 2,5 mi", 2_500_000.0),
    ("R$ 50.000", 50_000.0),
    ("franquia de R$ 250 mil por reclamação", 250_000.0),
    ("R$1.234,56", 1234.56),
    ("10.000.000,00", 10_000_000.0),
    ("sem valor", None),
])
def test_dinheiro(texto, esperado):
    assert n.dinheiro(texto) == esperado


@pytest.mark.parametrize("texto,dias", [
    ("12 (doze) meses", 360),
    ("prazo de 60 (sessenta) dias", 60),
    ("5 anos", 1825),
    ("doze meses", 360),
    ("1 mês", 30),
    ("indeterminado", None),
])
def test_duracao(texto, dias):
    assert n.duracao_dias(texto) == dias


@pytest.mark.parametrize("texto,iso", [
    ("01/03/2019", "2019-03-01"),
    ("Retroatividade: 1º de março de 2019", "2019-03-01"),
    ("retroatividade ilimitada", "ilimitada"),
    ("31/02/2020", None),
])
def test_data(texto, iso):
    assert n.data(texto) == iso


def test_texto_busca_junta_hifenizacao_e_tira_acento():
    assert n.texto_busca("Respon-\nsabilidade   CIVIL “D&O”") == 'responsabilidade civil "d o"'


def test_formatadores():
    assert n.formatar_reais(1234567.8) == "R$ 1.234.567,80"
    assert n.formatar_duracao(360) == "12 meses"
    assert n.formatar_duracao(730) == "2 anos"
    assert n.formatar_data("2019-03-01") == "01/03/2019"
