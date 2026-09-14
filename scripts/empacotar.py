# -*- coding: utf-8 -*-
"""Gera o ZIP de entrega a partir do que está versionado no Git (git archive).

Só entra o que o repositório público tem: nada de .env, banco, saída, cache ou PDF de seguradora.
Uso: python scripts/empacotar.py  →  ../InsurMinds_Projeto_Final_PRISMA_DO.zip
"""
from __future__ import annotations

import subprocess
import sys
import zipfile
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
PROIBIDOS = (".env", ".sqlite", "__pycache__", "saida/", "apolices/reais/", "apolices/holdout/")


def main() -> int:
    destino = RAIZ.parent / "InsurMinds_Projeto_Final_PRISMA_DO.zip"
    subprocess.run(["git", "archive", "--format=zip", "--prefix=prisma_do/", "-o", str(destino), "HEAD"],
                   cwd=RAIZ, check=True)
    with zipfile.ZipFile(destino) as z:
        nomes = z.namelist()
    vazados = [n for n in nomes if any(p in n and not n.endswith((".gitkeep", ".example", "fontes.yaml"))
                                       for p in PROIBIDOS)]
    if vazados:
        print("ERRO: arquivos que não podem ir no ZIP:", vazados)
        return 1
    obrigatorios = ["prisma_do/README.md", "prisma_do/LICENSE",
                    "prisma_do/Projeto_Final_Artefatos/Relatorio_Tecnico_PRISMA_DO.pdf",
                    "prisma_do/Projeto_Final_Artefatos/InsurMinds_Projeto_Final.pptx"]
    faltando = [o for o in obrigatorios if o not in nomes]
    if faltando:
        print("ERRO: faltando no ZIP:", faltando)
        return 1
    print(f"ok {destino} ({destino.stat().st_size / 1e6:.1f} MB, {len(nomes)} entradas)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
