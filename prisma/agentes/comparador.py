# -*- coding: utf-8 -*-
"""Agente Comparador — quadro campo a campo com favorabilidade ao segurado.

Só compara valores VERIFICADOS. A favorabilidade vem de `dados/regras_comparacao.yaml`, nunca do
LLM. Com 3 ou mais documentos: o melhor recebe "mais favorável", o pior "menos favorável", os do
meio "intermediária". Campo de especificação comparado com condições gerais é "não comparável"
(Lei da Condição Geral × Especificação).
"""
from __future__ import annotations

from functools import lru_cache
from typing import Optional

import yaml

from prisma import config
from prisma.agentes.extrator import eh_especificacao
from prisma.modelos import (Comparacao, Documento, Favorabilidade, Ficha, LinhaComparacao, StatusEvidencia,
                            carregar_esquema)


@lru_cache(maxsize=1)
def regras() -> dict[str, dict]:
    dados = yaml.safe_load((config.DADOS / "regras_comparacao.yaml").read_text(encoding="utf-8"))
    return {r["campo"]: r for r in dados["regras"]}


def _pontuacao(regra: dict, valor) -> Optional[float]:
    """Número em que MAIOR = mais favorável. None = não pontuável."""
    criterio = regra["criterio"]
    if valor is None:
        return None
    if criterio == "maior_melhor":
        return None if valor == "conforme_especificacao" else float(valor)
    if criterio == "menor_melhor":
        return -float(valor)
    if criterio == "retroatividade":
        if valor == "ilimitada":
            return float("inf")
        ano, mes, dia = (int(x) for x in str(valor).split("-"))
        return -(ano * 10000 + mes * 100 + dia)  # data mais antiga = maior pontuação
    if criterio == "ordem":
        ordem = regra["ordem"]
        for posicao, grupo in enumerate(ordem):
            if valor in grupo:
                return float(len(ordem) - posicao)
        return None
    return None


def comparar(documentos: list[Documento], fichas: dict[str, Ficha]) -> Comparacao:
    esq = carregar_esquema()
    regras_campo = regras()
    tipos = {d.id: ("espec" if eh_especificacao(d) else "cg") for d in documentos}
    linhas: list[LinhaComparacao] = []
    for campo in esq.campos:
        regra = regras_campo.get(campo.id, {"id": None, "criterio": "informativo"})
        valores, notas = {}, {}
        for d in documentos:
            v = fichas[d.id].valores.get(campo.id)
            valores[d.id] = v
            aplicavel = not (tipos[d.id] == "cg" and campo.onde == "espec") and \
                not (tipos[d.id] == "espec" and campo.onde == "cg" and campo.id != "adiantamento_custos_defesa")
            if not aplicavel:
                notas[d.id] = None
                continue
            valor = v.valor if (v is not None and v.status == StatusEvidencia.VERIFICADO) else regra.get("ausente_como")
            notas[d.id] = _pontuacao(regra, valor) if regra["criterio"] != "informativo" else None

        visiveis = {k: (x.valor if x and x.status == StatusEvidencia.VERIFICADO else None) for k, x in valores.items()}
        diferente = len({repr(x) for x in visiveis.values()}) > 1
        classificacao: dict[str, Favorabilidade] = {}
        pontuaveis = {k: n for k, n in notas.items() if n is not None}
        motivo = ""
        if regra["criterio"] == "informativo" or len(pontuaveis) < 2:
            classificacao = {d.id: Favorabilidade.NAO_COMPARAVEL for d in documentos}
            if regra["criterio"] != "informativo" and len(pontuaveis) < 2:
                motivo = "valor verificado em menos de dois documentos"
        else:
            melhor, pior = max(pontuaveis.values()), min(pontuaveis.values())
            for d in documentos:
                n = notas[d.id]
                if n is None:
                    classificacao[d.id] = Favorabilidade.NAO_COMPARAVEL
                elif melhor == pior:
                    classificacao[d.id] = Favorabilidade.EQUIVALENTE
                elif n == melhor:
                    classificacao[d.id] = Favorabilidade.MAIS_FAVORAVEL
                elif n == pior:
                    classificacao[d.id] = Favorabilidade.MENOS_FAVORAVEL
                else:
                    classificacao[d.id] = Favorabilidade.INTERMEDIARIA
            motivo = regra.get("fundamento", "")
            inferidos = [d.rotulo for d in documentos if notas[d.id] is not None and
                         not (valores[d.id] and valores[d.id].status == StatusEvidencia.VERIFICADO)]
            if inferidos:
                motivo += (" Ausência tratada como '" + str(regra.get("ausente_como")) + "' em: "
                           + ", ".join(inferidos) + ".")
        linhas.append(LinhaComparacao(
            campo_id=campo.id, rotulo=campo.rotulo, grupo=campo.grupo, valores=valores,
            classificacao=classificacao, regra_id=regra.get("id"), motivo=motivo.strip(), diferente=diferente))
    return Comparacao(doc_ids=[d.id for d in documentos], linhas=linhas)


def placar(comp: Comparacao) -> dict[str, dict[str, int]]:
    """Quantos campos cada documento tem como mais/menos favorável (visão rápida, não veredito)."""
    out = {d: {"mais_favoravel": 0, "menos_favoravel": 0, "equivalente": 0} for d in comp.doc_ids}
    for linha in comp.linhas:
        for d, f in linha.classificacao.items():
            if f.value in out[d]:
                out[d][f.value] += 1
    return out
