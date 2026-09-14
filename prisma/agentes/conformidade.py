# -*- coding: utf-8 -*-
"""Agente de Conformidade — aplica `dados/regras_susep.yaml` a cada documento.

Aponta indícios para revisão humana (não é parecer jurídico). Condições de presença de texto
trazem a linha encontrada como evidência; condições de ausência não têm evidência possível e o
alerta diz isso com todas as letras.
"""
from __future__ import annotations

import re
from functools import lru_cache

import yaml

from prisma import config, normalizar
from prisma.agentes.extrator import eh_especificacao
from prisma.modelos import AlertaConformidade, Documento, Evidencia, Ficha, StatusEvidencia


@lru_cache(maxsize=1)
def carregar_regras() -> dict:
    return yaml.safe_load((config.DADOS / "regras_susep.yaml").read_text(encoding="utf-8"))


def _linhas_normalizadas(doc: Documento) -> list[tuple[int, str, str]]:
    """Janelas de 2 linhas (frases quebram no PDF), normalizadas para as expressões."""
    brutas = [(p.numero, l.strip()) for p in doc.paginas for l in p.texto.splitlines() if l.strip()]
    janelas = []
    for i, (pag, l) in enumerate(brutas):
        prox = brutas[i + 1][1] if i + 1 < len(brutas) else ""
        original = f"{l} {prox}".strip()
        janelas.append((pag, original, normalizar.texto_busca(original)))
    return janelas


def avaliar(doc: Documento, ficha: Ficha) -> list[AlertaConformidade]:
    dados = carregar_regras()
    tipo = "especificacao" if eh_especificacao(doc) else "condicoes_gerais"
    janelas = _linhas_normalizadas(doc)
    texto_inteiro = normalizar.texto_busca("\n".join(p.texto for p in doc.paginas))
    alertas: list[AlertaConformidade] = []
    for regra in dados["regras"]:
        if regra["aplica_a"] not in ("todos", tipo):
            continue
        dispara, evidencia = True, None
        for cond in regra["condicoes"]:
            if "campo_ausente" in cond:
                v = ficha.valores.get(cond["campo_ausente"])
                ok = v is None or v.status != StatusEvidencia.VERIFICADO or v.valor in (None, False)
            elif "campo_em" in cond:
                v = ficha.valores.get(cond["campo_em"]["campo"])
                ok = v is not None and v.status == StatusEvidencia.VERIFICADO and v.valor in cond["campo_em"]["valores"]
            elif "texto_ausente" in cond:
                ok = re.search(cond["texto_ausente"], texto_inteiro) is None
            elif "texto_presente" in cond:
                ok = False
                for pag, original, norm in janelas:
                    if re.search(cond["texto_presente"], norm):
                        ok, evidencia = True, evidencia or Evidencia(trecho=original[:300], pagina=pag, similaridade=1.0)
                        break
            else:
                ok = False
            if not ok:
                dispara = False
                break
        if dispara:
            fundamento = f'{regra.get("norma", dados["norma_padrao"])}, {regra["artigo"]}'
            if regra.get("trecho_norma"):
                fundamento += f': "{regra["trecho_norma"]}"'
            tem_ausencia = any("texto_ausente" in c or "campo_ausente" in c for c in regra["condicoes"])
            mensagem = regra["mensagem"]
            if tem_ausencia:
                mensagem += " (Indício por ausência: confira se a informação está em outro documento da apólice.)"
            alertas.append(AlertaConformidade(regra_id=regra["id"], doc_id=doc.id, artigo=regra["artigo"],
                                              severidade=regra["severidade"], mensagem=mensagem,
                                              fundamento=fundamento, evidencia=evidencia))
    return alertas
