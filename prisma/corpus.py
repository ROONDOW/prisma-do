# -*- coding: utf-8 -*-
"""Corpus de demonstração: condições gerais públicas (baixadas das URLs oficiais, com SHA-256
conferido) + especificações fictícias geradas localmente."""
from __future__ import annotations

import hashlib
from pathlib import Path
from typing import Optional

import yaml

from prisma import config


def fontes() -> dict:
    return yaml.safe_load((config.REAIS / "fontes.yaml").read_text(encoding="utf-8"))


def metadados_por_sha(sha256: str) -> Optional[dict]:
    dados = fontes()
    for item in dados.get("documentos", []) + dados.get("holdout", []) + dados.get("normas", []):
        if item.get("sha256") == sha256:
            return {k: v for k, v in item.items() if k not in ("sha256",)}
    return None


def baixar(forcar: bool = False, avisar=print) -> list[Path]:
    """Baixa cada documento de `fontes.yaml` e confere o hash. Hash diferente = a seguradora
    publicou nova versão: o arquivo é mantido com sufixo `.novo` e o aviso é emitido, porque o
    gabarito foi anotado sobre a versão registrada."""
    import requests

    baixados = []
    dados = fontes()
    for item in dados.get("documentos", []) + dados.get("holdout", []) + dados.get("normas", []):
        pasta = config.HOLDOUT if item.get("pasta") == "holdout" else config.REAIS
        pasta.mkdir(parents=True, exist_ok=True)
        destino = pasta / item["arquivo"]
        if destino.exists() and not forcar and hashlib.sha256(destino.read_bytes()).hexdigest() == item["sha256"]:
            avisar(f"já existe  {item['arquivo']}")
            baixados.append(destino)
            continue
        try:
            r = requests.get(item["url"], timeout=60, headers={"User-Agent": "Mozilla/5.0 (PRISMA D&O; academico)"})
            r.raise_for_status()
        except Exception as erro:
            avisar(f"FALHOU     {item['arquivo']}: {erro.__class__.__name__}")
            continue
        sha = hashlib.sha256(r.content).hexdigest()
        if not r.content.startswith(b"%PDF"):
            avisar(f"FALHOU     {item['arquivo']}: a URL não devolveu PDF (site mudou?)")
            continue
        if sha != item["sha256"]:
            (destino.with_suffix(".pdf.novo")).write_bytes(r.content)
            avisar(f"VERSÃO NOVA {item['arquivo']}: hash difere do registrado; salvo como .pdf.novo")
            continue
        destino.write_bytes(r.content)
        avisar(f"baixado   {item['arquivo']}")
        baixados.append(destino)
    return baixados


def arquivos_demo() -> list[Path]:
    """Documentos usados na demonstração, na ordem de exibição."""
    nomes_reais = [d["arquivo"] for d in fontes()["documentos"]]
    reais = [config.REAIS / n for n in nomes_reais if (config.REAIS / n).exists()]
    sinteticas = [config.SINTETICAS / n for n in ("especificacao_aurora.pdf", "especificacao_boreal_escaneada.pdf",
                                                  "especificacao_cruzeiro.png")
                  if (config.SINTETICAS / n).exists()]
    return sinteticas + reais
