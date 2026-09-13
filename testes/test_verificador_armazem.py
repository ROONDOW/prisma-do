# -*- coding: utf-8 -*-
from prisma.agentes import verificador
from prisma.armazem import Armazem
from prisma.modelos import Documento, Evidencia, Ficha, Pagina, StatusEvidencia, ValorCampo, carregar_esquema

DOC = Documento(id="d1", nome="teste", sha256="1" * 64, tipo_arquivo="pdf", paginas=[
    Pagina(numero=1, texto="Seguradora: Aurora Seguros S.A.\nLimite Máximo de Garantia: R$ 50.000.000,00\n"),
    Pagina(numero=2, texto="7.1.1. Atos ilícitos dolosos. A presente exclusão somente aplicar-se-á na hipótese de "
                           "decisão judicial transitada\nem julgado.\nPenhora Online e Bloqueio de Bens Contratada R$ 5.000.000,00"),
])
ESQ = carregar_esquema()


def _v(campo, valor, trecho, pagina):
    return verificador.verificar(DOC, ESQ.campo(campo), ValorCampo(
        campo_id=campo, valor=valor, status=StatusEvidencia.NAO_VERIFICADO,
        evidencia=Evidencia(trecho=trecho, pagina=pagina)))


def test_trecho_existente_e_numero_ancorado_verifica():
    r = _v("limite_maximo_garantia", 50_000_000.0, "Limite Máximo de Garantia: R$ 50.000.000,00", 1)
    assert r.status == StatusEvidencia.VERIFICADO and r.exibivel


def test_trecho_inventado_nao_verifica_e_apaga_valor():
    r = _v("limite_maximo_garantia", 999_999_999.0, "Limite Máximo de Garantia: R$ 999.999.999,00", 1)
    assert r.status == StatusEvidencia.NAO_VERIFICADO and r.valor is None and not r.exibivel


def test_numero_diferente_do_trecho_nao_verifica():
    r = _v("limite_maximo_garantia", 10_000_000.0, "Limite Máximo de Garantia: R$ 50.000.000,00", 1)
    assert r.status == StatusEvidencia.NAO_VERIFICADO
    assert "número" in r.observacao


def test_pagina_errada_e_corrigida_com_registro():
    r = _v("sublimite_penhora_online", 5_000_000.0, "Penhora Online e Bloqueio de Bens Contratada R$ 5.000.000,00", 1)
    assert r.status == StatusEvidencia.VERIFICADO and r.evidencia.pagina == 2
    assert "corrigida" in r.observacao


def test_trecho_que_atravessa_quebra_de_linha():
    r = _v("exclusao_dolo_gatilho", "decisao_final", "decisão judicial transitada em julgado", 2)
    assert r.status == StatusEvidencia.VERIFICADO


def test_trecho_fora_do_assunto_nao_verifica():
    r = _v("exclusao_dolo_gatilho", "decisao_final", "Seguradora: Aurora Seguros S.A.", 1)
    assert r.status == StatusEvidencia.NAO_VERIFICADO


def test_trecho_curto_demais_nao_prova():
    r = _v("penhora_online", "contratada", "Contratada", 2)
    assert r.status == StatusEvidencia.NAO_VERIFICADO


def test_armazem_persiste_documento_ficha_e_busca(tmp_path):
    a = Armazem(tmp_path / "t.sqlite")
    a.salvar_documento(DOC, b"%PDF-1.7 teste", [])
    assert a.existe("d1") and a.documento("d1").paginas[1].numero == 2
    hits = a.buscar_texto('penhora "OR" bloqueio; DROP TABLE documentos')
    assert hits and hits[0]["pagina"] == 2
    assert a.existe("d1")  # consulta com sintaxe maliciosa não quebra nem apaga nada
    f = Ficha(doc_id="d1", modo="deterministico", valores={"x": ValorCampo(campo_id="x")})
    a.salvar_ficha(f)
    assert a.ficha("d1").valores["x"].campo_id == "x"
    a.registrar("exec1", "leitor", "d1", 0.0, {"paginas": 2})
    assert a.rastro("exec1")[0]["agente"] == "leitor"
