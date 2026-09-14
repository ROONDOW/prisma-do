# -*- coding: utf-8 -*-
"""Extrator, comparador, conformidade e segurança, sobre o corpus sintético versionado."""
import json
import re

import pytest
import yaml

from prisma import config, normalizar
from prisma.agentes import comparador, conformidade, extrator, leitor, recepcionista, segmentador, verificador
from prisma.modelos import Documento, Favorabilidade, StatusEvidencia

SINT = config.SINTETICAS


def _doc(nome: str) -> tuple[Documento, list]:
    conteudo = (SINT / nome).read_bytes()
    r = recepcionista.receber(nome, conteudo)
    paginas = leitor.ler(r.conteudo, r.tipo_arquivo)
    doc = Documento(id=r.doc_id, nome=nome, sha256=r.sha256, tipo_arquivo=r.tipo_arquivo,
                    ficticio=recepcionista.eh_ficticio([p.texto for p in paginas]), paginas=paginas)
    return doc, segmentador.segmentar(doc)


def _gabarito(chave: str) -> dict:
    return yaml.safe_load((config.GABARITO / f"especificacao_{chave}.yaml").read_text(encoding="utf-8"))["campos"]


@pytest.fixture(scope="module")
def aurora():
    doc, cl = _doc("especificacao_aurora.pdf")
    return doc, cl, extrator.extrair(doc, cl)


@pytest.fixture(scope="module")
def boreal_digital():
    doc, cl = _doc("especificacao_boreal_digital.pdf")
    return doc, cl, extrator.extrair(doc, cl)


def _verificado(ficha, campo):
    v = ficha.valores[campo]
    return v.valor if v.status == StatusEvidencia.VERIFICADO else None


# ---------------------------------------------------------------- extrator sem chave
def test_documento_sintetico_e_reconhecido_como_ficticio(aurora):
    assert aurora[0].ficticio and extrator.eh_especificacao(aurora[0])


@pytest.mark.parametrize("campo", ["limite_maximo_garantia", "franquia", "premio_total", "data_retroatividade",
                                   "prazo_complementar", "prazo_suplementar", "base_contratacao", "ambito_geografico",
                                   "sublimite_penhora_online", "sublimite_multas", "cobertura_c", "vigencia"])
def test_aurora_bate_com_gabarito(aurora, campo):
    assert _verificado(aurora[2], campo) == _gabarito("aurora")[campo]


def test_toda_evidencia_verificada_existe_na_pagina(aurora):
    doc, _, ficha = aurora
    for v in ficha.valores.values():
        if v.status == StatusEvidencia.VERIFICADO:
            pagina, sim = verificador.localizar(doc, v.evidencia.trecho, v.evidencia.pagina)
            assert pagina == v.evidencia.pagina and sim >= config.SIMILARIDADE_MINIMA_TRECHO


def test_cobertura_nao_contratada_nao_vira_contratada(boreal_digital):
    ficha = boreal_digital[2]
    assert _verificado(ficha, "cobertura_c") == "nao_contratada"
    assert _verificado(ficha, "sublimite_multas") is None  # "Não contratada —" não pega o valor da linha de baixo


@pytest.mark.lento
def test_pdf_escaneado_da_os_mesmos_numeros_que_o_digital(boreal_digital):
    doc, cl = _doc("especificacao_boreal_escaneada.pdf")
    assert all(p.metodo == "ocr" for p in doc.paginas)
    escaneada = extrator.extrair(doc, cl)
    for campo in ("limite_maximo_garantia", "franquia", "premio_total", "data_retroatividade", "prazo_complementar",
                  "sublimite_penhora_online"):
        assert _verificado(escaneada, campo) == _verificado(boreal_digital[2], campo), campo
    assert leitor.cer(boreal_digital[0].paginas[0].texto, doc.paginas[0].texto) <= 0.05


# ---------------------------------------------------------------- comparador
def test_comparador_classifica_por_regra(aurora, boreal_digital):
    docs = [aurora[0], boreal_digital[0]]
    comp = comparador.comparar(docs, {aurora[0].id: aurora[2], boreal_digital[0].id: boreal_digital[2]})
    linha = {l.campo_id: l for l in comp.linhas}
    assert linha["limite_maximo_garantia"].classificacao[aurora[0].id] == Favorabilidade.MAIS_FAVORAVEL
    assert linha["franquia"].classificacao[boreal_digital[0].id] == Favorabilidade.MENOS_FAVORAVEL
    assert linha["data_retroatividade"].classificacao[aurora[0].id] == Favorabilidade.MAIS_FAVORAVEL  # ilimitada
    assert linha["seguradora"].classificacao[aurora[0].id] == Favorabilidade.NAO_COMPARAVEL  # informativo
    assert linha["limite_maximo_garantia"].regra_id == "R05" and linha["limite_maximo_garantia"].motivo


def test_inverter_regra_no_yaml_inverte_o_quadro_sem_tocar_codigo(aurora, boreal_digital, monkeypatch):
    original = comparador.regras()
    invertidas = dict(original)
    invertidas["limite_maximo_garantia"] = dict(original["limite_maximo_garantia"], criterio="menor_melhor")
    monkeypatch.setattr(comparador, "regras", lambda: invertidas)
    comp = comparador.comparar([aurora[0], boreal_digital[0]],
                               {aurora[0].id: aurora[2], boreal_digital[0].id: boreal_digital[2]})
    lmg = next(l for l in comp.linhas if l.campo_id == "limite_maximo_garantia")
    assert lmg.classificacao[aurora[0].id] == Favorabilidade.MENOS_FAVORAVEL


def test_motor_de_comparacao_nao_tem_campo_chumbado():
    fonte = (config.RAIZ / "prisma" / "agentes" / "comparador.py").read_text(encoding="utf-8")
    ids = [c["campo"] for c in yaml.safe_load((config.DADOS / "regras_comparacao.yaml").read_text(encoding="utf-8"))["regras"]]
    assert not [i for i in ids if f'"{i}"' in fonte and i != "adiantamento_custos_defesa"]


# ---------------------------------------------------------------- conformidade
def test_especificacao_sem_prazo_adicional_dispara_art_19(aurora):
    doc, _, ficha = aurora
    sem_prazo = ficha.model_copy(deep=True)
    for campo in ("prazo_complementar", "prazo_suplementar"):
        sem_prazo.valores[campo] = sem_prazo.valores[campo].model_copy(update={"status": StatusEvidencia.NAO_LOCALIZADO, "valor": None})
    doc_sem_texto = doc.model_copy(update={"paginas": [p.model_copy(update={"texto": re.sub(
        r"(?i)prazo (complementar|suplementar|adicional)", "", p.texto)}) for p in doc.paginas]})
    ids = [a.regra_id for a in conformidade.avaliar(doc_sem_texto, sem_prazo)]
    assert "S637-19-PRAZO-ADICIONAL-ESPEC" in ids
    assert "S637-19-PRAZO-ADICIONAL-ESPEC" not in [a.regra_id for a in conformidade.avaliar(doc, ficha)]


def test_regras_susep_citam_texto_literal_da_circular():
    pdf = config.REAIS / "susep_circular_637_2021.pdf"
    if not pdf.exists():
        pytest.skip("corpus real não baixado (python -m prisma.cli baixar-corpus)")
    paginas = leitor.ler(pdf.read_bytes(), "pdf")
    doc = Documento(id="c637", nome="c637", sha256="0" * 64, tipo_arquivo="pdf", paginas=paginas)
    regras = yaml.safe_load((config.DADOS / "regras_susep.yaml").read_text(encoding="utf-8"))["regras"]
    assert len([r for r in regras if r.get("trecho_norma")]) >= 6
    for r in regras:
        if r.get("trecho_norma"):
            _, sim = verificador.localizar(doc, r["trecho_norma"], None)
            assert sim >= 0.95, r["id"]


# ---------------------------------------------------------------- segurança: injeção de prompt
class LLMObediente:
    """LLM falso que OBEDECE às instruções plantadas no documento — o pior caso."""

    def __init__(self, injecoes):
        self.injecoes = injecoes
        self.ultimo_provedor = "falso-obediente"
        self.chamadas = 0
        self.descricao = "falso"

    def perguntar(self, sistema, usuario):
        self.chamadas += 1
        i = self.injecoes
        campos = [
            {"campo": "limite_maximo_garantia", "valor": 999999999.0, "trecho": i[0], "pagina": 1},
            {"campo": "franquia", "valor": 0, "trecho": i[4], "pagina": 1},
            {"campo": "data_retroatividade", "valor": "01/01/1900", "trecho": i[7], "pagina": 1},
            {"campo": "ambito_geografico", "valor": "lua e marte", "trecho": i[13], "pagina": 1},
            {"campo": "multas_penalidades", "valor": "nao_contratada", "trecho": i[6], "pagina": 1},
            {"campo": "seguradora", "valor": "cobertura total para qualquer sinistro", "trecho": i[2], "pagina": 1},
            {"campo": "premio_total", "valor": 1.0, "trecho": i[12], "pagina": 1},
        ]
        return json.dumps({"campos": campos}), self.ultimo_provedor


def test_injecao_de_prompt_nao_altera_nenhum_valor_exibido(aurora):
    from scripts.gerar_sinteticas import INJECOES

    doc, cl = _doc("injecao_prompt.pdf")
    ficha = extrator.extrair(doc, cl, LLMObediente(INJECOES))
    limpa = aurora[2]
    for campo in ("limite_maximo_garantia", "franquia", "data_retroatividade", "ambito_geografico",
                  "multas_penalidades", "premio_total"):
        assert _verificado(ficha, campo) == _verificado(limpa, campo), campo
    for v in ficha.valores.values():
        if v.status == StatusEvidencia.VERIFICADO:
            assert not any(normalizar.texto_busca(inj)[:40] in normalizar.texto_busca(v.evidencia.trecho)
                           for inj in INJECOES), v.campo_id


def test_detector_pega_as_15_injecoes_plantadas():
    from scripts.gerar_sinteticas import INJECOES

    assert len(INJECOES) >= 15
    assert all(verificador.instrucao_suspeita(x) for x in INJECOES)


@pytest.mark.parametrize("clausula", [
    "Os custos de defesa serão adiantados à medida que forem incorridos.",
    "a Seguradora poderá, por sua opção e custas, se associar a ele, na qualidade de assistente",
    "assistentes técnicos e periciais, depósitos recursais",
    "a Seguradora poderá dar instruções para o seu processamento",
])
def test_detector_nao_acusa_clausula_legitima(clausula):
    assert not verificador.instrucao_suspeita(clausula)
