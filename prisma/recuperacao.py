# -*- coding: utf-8 -*-
"""Recuperação local de cláusulas (BM25), sem embeddings pagos nem serviço externo.

Cada campo do esquema vira uma consulta (rótulo + pistas). O título da cláusula pesa mais que
o corpo, porque em apólice o título costuma dizer exatamente do que a cláusula trata
("COBERTURA ADICIONAL DE MULTAS E PENALIDADES").
"""
from __future__ import annotations

import re

from rank_bm25 import BM25Okapi

from prisma.agentes.segmentador import Bloco
from prisma.modelos import CampoDef
from prisma.normalizar import texto_busca

_STOP = set("a o e de da do das dos em no na nos nas para por com sem ao aos as os um uma que se ou "
            "sua seu suas seus este esta estes estas pelo pela pelos pelas qualquer quaisquer sera serao "
            "ser sob apolice seguro segurado seguradora".split())


def tokens(texto: str) -> list[str]:
    # radical grosseiro (6 letras) aproxima plural e flexão: reclamação/reclamações, doloso/dolosos
    return [t[:6] for t in re.findall(r"[a-z0-9]+", texto_busca(texto)) if t not in _STOP and len(t) > 1]


class Indice:
    def __init__(self, blocos: list[Bloco], peso_titulo: int = 3):
        self.blocos = blocos
        corpus = [tokens(" ".join([b.titulo] * peso_titulo) + " " + b.texto) for b in blocos]
        self._bm25 = BM25Okapi(corpus) if corpus else None

    def buscar(self, consulta: str, k: int = 6) -> list[tuple[Bloco, float]]:
        if not self._bm25:
            return []
        q = tokens(consulta)
        if not q:
            return []
        notas = self._bm25.get_scores(q)
        ordem = sorted(range(len(notas)), key=lambda i: notas[i], reverse=True)[:k]
        return [(self.blocos[i], float(notas[i])) for i in ordem if notas[i] > 0]

    def para_campo(self, campo: CampoDef, k: int = 6) -> list[Bloco]:
        consulta = " ".join([campo.rotulo] + campo.pistas + campo.rotulos_espec)
        return [b for b, _ in self.buscar(consulta, k)]
