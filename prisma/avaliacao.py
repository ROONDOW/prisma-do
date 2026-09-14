# -*- coding: utf-8 -*-
"""Avaliação da extração contra o gabarito (`gabarito/*.yaml`). Pilar "Medido, não prometido".

Regras de pontuação (declaradas aqui e repetidas no relatório):
- Só conta como resposta do sistema o valor VERIFICADO (o que o usuário veria na tela).
- Gabarito de ausência (null, false, "nao_prevista", "nao_excluido") é acertado por "não localizado".
- Dinheiro: diferença < R$ 0,01. Duração: dias iguais. Período: início e fim iguais.
- Texto: acerta se contém (sem acento, minúsculo) algum dos termos aceitos.
- `{aceita: [...]}`: redação ambígua anotada com mais de uma leitura válida (nota no YAML).
- Campos que só existem na especificação não são pontuados em condições gerais.
"""
from __future__ import annotations

import hashlib
from collections import defaultdict
from pathlib import Path
from typing import Optional

import yaml

from prisma import config, normalizar
from prisma.modelos import Ficha, StatusEvidencia, carregar_esquema

AUSENCIA = {None, False, "nao_prevista", "nao_excluido"}


def carregar_gabaritos() -> list[dict]:
    arquivos = sorted(config.GABARITO.glob("*.yaml")) + sorted((config.GABARITO / "holdout").glob("*.yaml"))
    return [yaml.safe_load(p.read_text(encoding="utf-8")) | {"arquivo_gabarito": p.name} for p in arquivos]


def caminho_documento(nome: str) -> Optional[Path]:
    for pasta in (config.SINTETICAS, config.REAIS, config.HOLDOUT):
        if (pasta / nome).exists():
            return pasta / nome
    return None


def doc_id_de(nome: str) -> Optional[str]:
    p = caminho_documento(nome)
    return hashlib.sha256(p.read_bytes()).hexdigest()[:12] if p else None


def _aceitos(ouro) -> tuple[list, str]:
    if isinstance(ouro, dict) and "aceita" in ouro:
        return list(ouro["aceita"]), ouro.get("nota", "")
    return [ouro], ""


def acertou(tipo: str, previsto, ouro) -> bool:
    aceitos, _ = _aceitos(ouro)
    for a in aceitos:
        if previsto is None and a in AUSENCIA:
            return True
        if previsto is None:
            continue
        if tipo == "dinheiro" and isinstance(a, (int, float)) and not isinstance(a, bool):
            if abs(float(previsto) - float(a)) < 0.01:
                return True
        elif tipo == "texto" and isinstance(a, str):
            if normalizar.sem_acento(a).lower() in normalizar.sem_acento(str(previsto)).lower():
                return True
        elif tipo == "duracao" and a is not None and not isinstance(a, str):
            if previsto != "conforme_especificacao" and int(previsto) == int(a):
                return True
        elif previsto == a:
            return True
    return False


def avaliar_fichas(fichas: dict[str, Ficha]) -> dict:
    """`fichas`: doc_id -> Ficha. Devolve métricas agregadas e o detalhe campo a campo."""
    esq = carregar_esquema()
    detalhe = []
    for gab in carregar_gabaritos():
        did = doc_id_de(gab["documento"])
        ficha = fichas.get(did) if did else None
        for cid, ouro in gab["campos"].items():
            campo = esq.campo(cid)
            v = ficha.valores.get(cid) if ficha else None
            verificado = v is not None and v.status == StatusEvidencia.VERIFICADO
            previsto = v.valor if verificado else None
            detalhe.append({
                "documento": gab["documento"], "ficticio": gab.get("ficticio", False),
                "holdout": gab.get("holdout", False), "campo": cid,
                "grupo": campo.grupo, "tipo": campo.tipo, "ouro": ouro, "previsto": previsto,
                "status": v.status.value if v else "sem_ficha", "metodo": v.metodo if v else "",
                "acerto": acertou(campo.tipo, previsto, ouro),
                "valor_errado_exibido": verificado and not acertou(campo.tipo, previsto, ouro),
                "pagina": v.evidencia.pagina if (verificado and v.evidencia) else None,
            })
    return {"resumo": resumir(detalhe), "detalhe": detalhe}


def _taxa(itens: list[dict]) -> dict:
    n = len(itens)
    return {"campos": n, "acertos": sum(i["acerto"] for i in itens),
            "acuracia": round(sum(i["acerto"] for i in itens) / n, 4) if n else None,
            "valores_errados_exibidos": sum(i["valor_errado_exibido"] for i in itens)}


def resumir(detalhe: list[dict]) -> dict:
    por_doc, por_grupo = defaultdict(list), defaultdict(list)
    for i in detalhe:
        por_doc[i["documento"]].append(i)
        por_grupo[i["grupo"]].append(i)
    return {
        "geral": _taxa(detalhe),
        "desenvolvimento": _taxa([i for i in detalhe if not i["holdout"]]),
        "holdout": _taxa([i for i in detalhe if i["holdout"]]),
        "especificacoes": _taxa([i for i in detalhe if i["ficticio"]]),
        "condicoes_gerais": _taxa([i for i in detalhe if not i["ficticio"] and not i["holdout"]]),
        "por_documento": {k: _taxa(v) for k, v in por_doc.items()},
        "por_grupo": {k: _taxa(v) for k, v in por_grupo.items()},
    }
