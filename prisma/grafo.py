# -*- coding: utf-8 -*-
"""Orquestração dos agentes em LangGraph (grafo de estado explícito, um nó por agente).

Grafo 1 — processar documento:
    recepcionista -> leitor (OCR por página) -> segmentador -> extrator -> verificador -> fim
Grafo 2 — comparar apólices:
    carregar_fichas -> comparador -> conformidade -> relator -> fim

Cada nó registra no rastro (tabela `rastro`) o que fez e quanto tempo levou, para a interface e
para a auditoria. Se o LangGraph não estiver instalado, um executor sequencial de reserva roda os
mesmos nós na mesma ordem (o sistema não depende de biblioteca opcional para funcionar).
"""
from __future__ import annotations

import time
import uuid
from typing import Any, Callable, Optional, TypedDict

from prisma import corpus
from prisma.agentes import comparador, conformidade, extrator, leitor, recepcionista, relator, segmentador
from prisma.armazem import Armazem
from prisma.llm import Cascata
from prisma.modelos import Comparacao, Documento, Ficha


class EstadoDocumento(TypedDict, total=False):
    execucao: str
    nome: str
    conteudo: bytes
    recebido: Any
    documento: Documento
    clausulas: list
    brutos_det: dict
    brutos_llm: dict
    ficha: Ficha
    cache: bool
    progresso: Optional[Callable[[str, str], None]]


class EstadoComparacao(TypedDict, total=False):
    execucao: str
    doc_ids: list[str]
    documentos: list[Documento]
    fichas: dict[str, Ficha]
    comparacao: Comparacao
    pdf: bytes
    comparacao_id: int


def _avisar(estado: dict, agente: str, mensagem: str) -> None:
    cb = estado.get("progresso")
    if cb:
        cb(agente, mensagem)


# ============================================================================ grafo 1
def construir_grafo_documento(armazem: Armazem, cascata: Optional[Cascata]):
    def no_recepcionista(e: EstadoDocumento) -> EstadoDocumento:
        t0 = time.time()
        r = recepcionista.receber(e["nome"], e["conteudo"])
        armazem.registrar(e["execucao"], "recepcionista", r.doc_id, t0,
                          {"arquivo": r.nome, "tipo": r.tipo_arquivo, "bytes": len(r.conteudo), "sha256": r.sha256})
        _avisar(e, "Recepcionista", f"{r.nome}: {r.tipo_arquivo.upper()} válido, SHA-256 {r.sha256[:12]}")
        return {"recebido": r}

    def no_leitor(e: EstadoDocumento) -> EstadoDocumento:
        r = e["recebido"]
        t0 = time.time()
        if armazem.existe(r.doc_id):
            doc = armazem.documento(r.doc_id)
            armazem.registrar(e["execucao"], "leitor", doc.id, t0, {"cache": True, "paginas": len(doc.paginas)})
            _avisar(e, "Leitor", f"já processado antes: {len(doc.paginas)} página(s) reaproveitadas")
            return {"documento": doc, "cache": True}

        def progresso_paginas(atual, total, metodo):
            _avisar(e, "Leitor", f"página {atual}/{total} ({'OCR' if metodo == 'ocr' else 'texto nativo'})")

        paginas = leitor.ler(r.conteudo, r.tipo_arquivo, progresso=progresso_paginas)
        ocr = [p.numero for p in paginas if p.metodo == "ocr"]
        doc = Documento(id=r.doc_id, nome=r.nome, sha256=r.sha256, tipo_arquivo=r.tipo_arquivo,
                        ficticio=recepcionista.eh_ficticio([p.texto for p in paginas]),
                        metadados=corpus.metadados_por_sha(r.sha256) or {}, paginas=paginas)
        armazem.registrar(e["execucao"], "leitor", doc.id, t0, {"paginas": len(paginas), "paginas_ocr": ocr})
        return {"documento": doc, "cache": False}

    def no_segmentador(e: EstadoDocumento) -> EstadoDocumento:
        doc, t0 = e["documento"], time.time()
        if e.get("cache"):
            clausulas = armazem.clausulas(doc.id)
        else:
            clausulas = segmentador.segmentar(doc)
            armazem.salvar_documento(doc, e["recebido"].conteudo, clausulas)
        armazem.registrar(e["execucao"], "segmentador", doc.id, t0, {"clausulas": len(clausulas)})
        _avisar(e, "Segmentador", f"{len(clausulas)} cláusulas com página")
        return {"clausulas": clausulas}

    def no_extrator(e: EstadoDocumento) -> EstadoDocumento:
        doc, t0 = e["documento"], time.time()
        det = extrator.extrair_deterministico(doc, e["clausulas"], verificar=False)
        llm = extrator.extrair_llm(doc, e["clausulas"], cascata, verificar=False) if cascata else {}
        armazem.registrar(e["execucao"], "extrator", doc.id, t0,
                          {"modo": "hibrido" if cascata else "deterministico",
                           "provedor": cascata.ultimo_provedor if cascata else None,
                           "candidatos_regras": sum(1 for v in det.values() if v.evidencia),
                           "candidatos_llm": sum(1 for v in llm.values() if v.evidencia)})
        _avisar(e, "Extrator", f"{sum(1 for v in det.values() if v.evidencia)} valores pelas regras"
                + (f", {sum(1 for v in llm.values() if v.evidencia)} pelo LLM ({cascata.ultimo_provedor})" if cascata else ""))
        return {"brutos_det": det, "brutos_llm": llm}

    def no_verificador(e: EstadoDocumento) -> EstadoDocumento:
        doc, t0 = e["documento"], time.time()
        det = extrator.verificar_todos(doc, e["brutos_det"])
        if e.get("brutos_llm"):
            llm = extrator.verificar_todos(doc, e["brutos_llm"])
            ficha = Ficha(doc_id=doc.id, valores=extrator.fundir(llm, det), modo="hibrido")
        else:
            ficha = Ficha(doc_id=doc.id, valores=det, modo="deterministico")
        armazem.salvar_ficha(ficha)
        seguradora = ficha.valores.get("seguradora")
        if not doc.metadados.get("seguradora") and seguradora and seguradora.exibivel:
            # rótulo legível para documento enviado pelo usuário: a seguradora extraída e verificada
            doc = doc.model_copy(update={"metadados": {**doc.metadados, "seguradora": str(seguradora.valor)[:80],
                                                       "seguradora_origem": "extraída"}})
            armazem.atualizar_metadados(doc.id, doc.metadados)
        resumo = extrator.resumo_ficha(ficha)
        reprovados = [v.campo_id for v in list(e["brutos_det"].values()) + list(e.get("brutos_llm", {}).values())
                      if v.evidencia is not None]
        armazem.registrar(e["execucao"], "verificador", doc.id, t0, {**resumo, "candidatos": len(reprovados)})
        _avisar(e, "Verificador", f"{resumo['verificado']} valores com evidência conferida; "
                                  f"{resumo['nao_verificado']} reprovados")
        return {"ficha": ficha, "documento": doc}

    nos = [("recepcionista", no_recepcionista), ("leitor", no_leitor), ("segmentador", no_segmentador),
           ("extrator", no_extrator), ("verificador", no_verificador)]
    return _compilar(EstadoDocumento, nos)


# ============================================================================ grafo 2
def construir_grafo_comparacao(armazem: Armazem, cascata: Optional[Cascata]):
    def no_carregar(e: EstadoComparacao) -> EstadoComparacao:
        t0 = time.time()
        docs = [armazem.documento(i) for i in e["doc_ids"]]
        faltando = [i for i, d in zip(e["doc_ids"], docs) if d is None or armazem.ficha(i) is None]
        if faltando:
            raise ValueError(f"documentos sem ficha: {', '.join(faltando)} — processe-os antes de comparar")
        fichas = {d.id: armazem.ficha(d.id) for d in docs}
        armazem.registrar(e["execucao"], "carregar_fichas", None, t0, {"documentos": e["doc_ids"]})
        return {"documentos": docs, "fichas": fichas}

    def no_comparador(e: EstadoComparacao) -> EstadoComparacao:
        t0 = time.time()
        comp = comparador.comparar(e["documentos"], e["fichas"])
        armazem.registrar(e["execucao"], "comparador", None, t0,
                          {"linhas": len(comp.linhas), "diferentes": sum(l.diferente for l in comp.linhas),
                           "placar": comparador.placar(comp)})
        return {"comparacao": comp}

    def no_conformidade(e: EstadoComparacao) -> EstadoComparacao:
        t0 = time.time()
        comp = e["comparacao"]
        alertas = []
        for d in e["documentos"]:
            alertas += conformidade.avaliar(d, e["fichas"][d.id])
        comp = comp.model_copy(update={"alertas": alertas})
        armazem.registrar(e["execucao"], "conformidade", None, t0,
                          {"alertas": [(a.doc_id, a.regra_id, a.severidade) for a in alertas]})
        return {"comparacao": comp}

    def no_relator(e: EstadoComparacao) -> EstadoComparacao:
        t0 = time.time()
        comp = e["comparacao"]
        texto, modo = relator.resumo(comp, e["documentos"], cascata)
        comp = comp.model_copy(update={"resumo": texto, "modo_resumo": modo})
        modos = {f.modo for f in e["fichas"].values()}
        pdf = relator.pdf_comparativo(comp, e["documentos"], " / ".join(sorted(modos)))
        comp_id = armazem.salvar_comparacao(comp)
        armazem.registrar(e["execucao"], "relator", None, t0, {"modo_resumo": modo, "pdf_bytes": len(pdf),
                                                                "comparacao_id": comp_id})
        return {"comparacao": comp, "pdf": pdf, "comparacao_id": comp_id}

    nos = [("carregar_fichas", no_carregar), ("comparador", no_comparador), ("conformidade", no_conformidade),
           ("relator", no_relator)]
    return _compilar(EstadoComparacao, nos)


# ============================================================================ compilação
class _Sequencial:
    """Reserva sem LangGraph: mesmos nós, mesma ordem, mesmo contrato de `invoke`."""

    def __init__(self, nos):
        self.nos = nos

    def invoke(self, estado: dict) -> dict:
        estado = dict(estado)
        for _, fn in self.nos:
            estado.update(fn(estado))
        return estado


def _compilar(tipo_estado, nos):
    try:
        from langgraph.graph import END, START, StateGraph
    except ImportError:
        return _Sequencial(nos)
    g = StateGraph(tipo_estado)
    for nome, fn in nos:
        g.add_node(nome, fn)
    g.add_edge(START, nos[0][0])
    for (a, _), (b, _) in zip(nos, nos[1:]):
        g.add_edge(a, b)
    g.add_edge(nos[-1][0], END)
    return g.compile()


def nova_execucao() -> str:
    return time.strftime("%Y%m%d-%H%M%S-") + uuid.uuid4().hex[:6]


def processar(nome: str, conteudo: bytes, armazem: Armazem, cascata: Optional[Cascata] = None,
              progresso: Optional[Callable[[str, str], None]] = None, execucao: Optional[str] = None) -> EstadoDocumento:
    grafo = construir_grafo_documento(armazem, cascata)
    return grafo.invoke({"execucao": execucao or nova_execucao(), "nome": nome, "conteudo": conteudo,
                         "progresso": progresso})


def comparar(doc_ids: list[str], armazem: Armazem, cascata: Optional[Cascata] = None,
             execucao: Optional[str] = None) -> EstadoComparacao:
    grafo = construir_grafo_comparacao(armazem, cascata)
    return grafo.invoke({"execucao": execucao or nova_execucao(), "doc_ids": doc_ids})


def desenho_mermaid() -> str:
    """Diagrama dos dois grafos (usado no README, no relatório e na interface)."""
    return """flowchart LR
  subgraph G1[Grafo 1 — processar documento]
    A[Recepcionista<br/>tipo, tamanho, SHA-256] --> B[Leitor<br/>texto nativo + OCR por página]
    B --> C[Segmentador<br/>cláusulas com página]
    C --> D[Extrator<br/>regras declaradas + LLM free]
    D --> E[Verificador<br/>trecho, assunto, número, injeção]
    E --> F[(SQLite<br/>fichas + rastro)]
  end
  subgraph G2[Grafo 2 — comparar apólices]
    F --> G[Comparador<br/>regras de favorabilidade]
    G --> H[Conformidade<br/>Circular SUSEP 637]
    H --> I[Relator<br/>resumo ancorado + PDF]
  end
  F --> J[Consultor<br/>perguntas com citação]"""
