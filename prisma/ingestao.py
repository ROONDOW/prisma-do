# -*- coding: utf-8 -*-
"""Etapas 1-3 do edital (recebimento, extração do conteúdo, organização) como funções puras,
chamadas pelos nós do grafo. Separadas do grafo para poderem ser testadas sozinhas."""
from __future__ import annotations

import time
from typing import Callable, Optional

from prisma import corpus
from prisma.agentes import leitor, recepcionista, segmentador
from prisma.armazem import Armazem
from prisma.modelos import Clausula, Documento


def ingerir(nome: str, conteudo: bytes, armazem: Armazem, execucao: str = "manual",
            progresso: Optional[Callable[[int, int, str], None]] = None,
            reprocessar: bool = False) -> tuple[Documento, list[Clausula]]:
    t0 = time.time()
    recebido = recepcionista.receber(nome, conteudo)
    armazem.registrar(execucao, "recepcionista", recebido.doc_id, t0,
                      {"arquivo": recebido.nome, "tipo": recebido.tipo_arquivo, "bytes": len(conteudo),
                       "sha256": recebido.sha256})
    if armazem.existe(recebido.doc_id) and not reprocessar:
        doc = armazem.documento(recebido.doc_id)
        armazem.registrar(execucao, "leitor", doc.id, time.time(), {"cache": True, "paginas": len(doc.paginas)})
        return doc, armazem.clausulas(doc.id)

    t1 = time.time()
    paginas = leitor.ler(recebido.conteudo, recebido.tipo_arquivo, progresso=progresso)
    ocr = [p.numero for p in paginas if p.metodo == "ocr"]
    armazem.registrar(execucao, "leitor", recebido.doc_id, t1,
                      {"paginas": len(paginas), "paginas_ocr": ocr,
                       "confianca_media_ocr": round(sum(p.confianca_ocr or 0 for p in paginas if p.metodo == "ocr")
                                                    / len(ocr), 3) if ocr else None})
    ficticio = recepcionista.eh_ficticio([p.texto for p in paginas])
    metadados = corpus.metadados_por_sha(recebido.sha256) or {}
    doc = Documento(id=recebido.doc_id, nome=recebido.nome, sha256=recebido.sha256,
                    tipo_arquivo=recebido.tipo_arquivo, ficticio=ficticio, metadados=metadados, paginas=paginas)

    t2 = time.time()
    clausulas = segmentador.segmentar(doc)
    armazem.registrar(execucao, "segmentador", doc.id, t2,
                      {"clausulas": len(clausulas),
                       "titulos_nivel1": sum(1 for c in clausulas if c.nivel == 1)})
    armazem.salvar_documento(doc, recebido.conteudo, clausulas)
    return doc, clausulas
