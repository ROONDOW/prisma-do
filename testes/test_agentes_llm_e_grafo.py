# -*- coding: utf-8 -*-
"""Fusão, coerência valor × trecho, âncoras do Consultor e do Relator, e o grafo de ponta a ponta."""
import json

from prisma import config, grafo
from prisma.agentes import consultor, extrator, relator, verificador
from prisma.armazem import Armazem
from prisma.modelos import Comparacao, Documento, Evidencia, Pagina, StatusEvidencia, ValorCampo, carregar_esquema

ESQ = carregar_esquema()


class LLMFalso:
    def __init__(self, resposta: dict):
        self.resposta = json.dumps(resposta, ensure_ascii=False)
        self.ultimo_provedor, self.chamadas, self.descricao, self.orcamento_s = "falso", 0, "falso", None

    def perguntar(self, sistema, usuario):
        self.chamadas += 1
        return self.resposta, "falso"


def _v(campo, valor, status=StatusEvidencia.VERIFICADO, metodo="deterministico"):
    return ValorCampo(campo_id=campo, valor=valor, status=status, metodo=metodo,
                      evidencia=Evidencia(trecho="x" * 20, pagina=1))


# ---------------------------------------------------------------- fusão e coerência
def test_fusao_regra_verificada_prevalece_e_conflito_fica_registrado():
    det = {"cobertura_c": _v("cobertura_c", "adicional"), "penhora_online": ValorCampo(campo_id="penhora_online")}
    llm = {"cobertura_c": _v("cobertura_c", "excluida", metodo="llm:x"),
           "penhora_online": _v("penhora_online", "adicional", metodo="llm:x")}
    final = extrator.fundir(llm, det)
    assert final["cobertura_c"].valor == "adicional" and "LLM leu" in final["cobertura_c"].observacao
    assert final["penhora_online"].valor == "adicional"  # o LLM preenche a lacuna das regras


def test_coerencia_exige_sinal_do_valor_no_trecho():
    campo = ESQ.campo("dano_ambiental")
    assert verificador.valor_coerente(campo, "adicional", "COBERTURA ADICIONAL DE DANO AMBIENTAL")
    assert not verificador.valor_coerente(campo, "excluida", "COBERTURA ADICIONAL DE DANO AMBIENTAL")
    sub = ESQ.campo("subrogacao_segurados")
    assert not verificador.valor_coerente(sub, "renuncia_salvo_dolo",
                                          "Salvo dolo, a Sub-rogação não será admitida se o prejuízo tiver sido causado pelo cônjuge")
    assert verificador.valor_coerente(sub, "renuncia_salvo_dolo",
                                      "A Seguradora não deverá exercer seus direitos de Sub-rogação contra os Segurados")


def test_item_de_lista_de_exclusoes_usa_o_titulo_anterior():
    doc = Documento(id="e", nome="e", sha256="0" * 64, tipo_arquivo="pdf", paginas=[
        Pagina(numero=1, texto="CLÁUSULA 4ª - RISCOS EXCLUÍDOS\n4.1. Esta Apólice não cobre:\n" + "a) item\n" * 30),
        Pagina(numero=2, texto="p.1) vírus, infestações de computadores ou danos similares ou maliciosos"),
    ])
    v = ValorCampo(campo_id="exclusao_cibernetica", valor="excluido", status=StatusEvidencia.NAO_VERIFICADO,
                   evidencia=Evidencia(trecho="p.1) vírus, infestações de computadores ou danos similares", pagina=2))
    assert verificador.verificar(doc, ESQ.campo("exclusao_cibernetica"), v).status == StatusEvidencia.VERIFICADO


def test_ausencia_nao_e_citavel():
    doc = Documento(id="a", nome="a", sha256="0" * 64, tipo_arquivo="pdf",
                    paginas=[Pagina(numero=1, texto="Exclusões gerais da apólice sem nada sobre tributos aqui")])
    v = ValorCampo(campo_id="exclusao_tributaria", valor="nao_excluido", status=StatusEvidencia.NAO_VERIFICADO,
                   evidencia=Evidencia(trecho="Exclusões gerais da apólice", pagina=1))
    r = verificador.verificar(doc, ESQ.campo("exclusao_tributaria"), v)
    assert r.status == StatusEvidencia.NAO_LOCALIZADO and r.valor is None


# ---------------------------------------------------------------- grafo, consultor e relator (sem chave)
def _armazem_com_aurora(tmp_path):
    a = Armazem(tmp_path / "g.sqlite")
    estado = grafo.processar("especificacao_aurora.pdf", (config.SINTETICAS / "especificacao_aurora.pdf").read_bytes(), a)
    return a, estado


def test_grafo_de_documento_sem_chave_registra_cada_agente(tmp_path):
    a, estado = _armazem_com_aurora(tmp_path)
    assert estado["ficha"].modo == "deterministico"
    agentes = [p["agente"] for p in a.rastro(limite=20)]
    for nome in ("recepcionista", "leitor", "segmentador", "extrator", "verificador"):
        assert nome in agentes
    assert a.ficha(estado["documento"].id).valores["limite_maximo_garantia"].valor == 50_000_000.0


def test_grafo_de_comparacao_gera_pdf_e_alerta(tmp_path):
    a, e1 = _armazem_com_aurora(tmp_path)
    e2 = grafo.processar("especificacao_boreal_digital.pdf",
                         (config.SINTETICAS / "especificacao_boreal_digital.pdf").read_bytes(), a)
    r = grafo.comparar([e1["documento"].id, e2["documento"].id], a)
    assert r["pdf"].startswith(b"%PDF") and r["comparacao"].resumo
    assert r["comparacao_id"] >= 1


def test_consultor_descarta_citacao_inexistente_e_valor_nao_ancorado(tmp_path):
    a, estado = _armazem_com_aurora(tmp_path)
    doc = estado["documento"]
    inventada = LLMFalso({"resposta": "O LMG é R$ 10.000.000,00.",
                          "citacoes": [{"doc_id": doc.id, "pagina": 1, "trecho": "Limite Máximo de Garantia: R$ 10.000.000,00"}]})
    r = consultor.perguntar("Qual o limite máximo de garantia?", [doc], a, inventada)
    assert r.texto == consultor.NAO_LOCALIZADO and r.descartadas == 1
    trecho_real = next(l for l in doc.paginas[0].texto.splitlines() if "50.000.000" in l)
    nao_ancorado = LLMFalso({"resposta": "O LMG é R$ 70.000.000,00.",
                             "citacoes": [{"doc_id": doc.id, "pagina": 1, "trecho": trecho_real}]})
    r2 = consultor.perguntar("Qual o limite máximo de garantia?", [doc], a, nao_ancorado)
    assert "não aparece" in r2.texto and r2.citacoes


def test_relator_descarta_resumo_com_recomendacao_ou_numero_inventado(tmp_path):
    a, e1 = _armazem_com_aurora(tmp_path)
    e2 = grafo.processar("especificacao_boreal_digital.pdf",
                         (config.SINTETICAS / "especificacao_boreal_digital.pdf").read_bytes(), a)
    docs = [a.documento(e1["documento"].id), a.documento(e2["documento"].id)]
    comp = grafo.comparar([d.id for d in docs], a)["comparacao"]
    _, modo = relator.resumo(comp, docs, LLMFalso({"topicos": ["- Recomendamos contratar a Aurora."]}))
    assert modo.startswith("deterministico") and "recomendou" in modo
    _, modo2 = relator.resumo(comp, docs, LLMFalso({"topicos": ["- A Aurora tem LMG de R$ 99.000.000,00."]}))
    assert "fora do quadro" in modo2
    texto, modo3 = relator.resumo(comp, docs, LLMFalso({"topicos": ["- A Aurora tem LMG de R$ 50.000.000,00."]}))
    assert modo3.startswith("llm") and "50.000.000" in texto
