# -*- coding: utf-8 -*-
"""Caminhos e limites do sistema. Nenhum limiar de negócio mora aqui: esses ficam nos YAML
de `dados/`. Aqui só há parâmetros técnicos (tamanho de upload, dpi do OCR etc.)."""
from __future__ import annotations

import os
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
DADOS = RAIZ / "dados"
APOLICES = RAIZ / "apolices"
REAIS = APOLICES / "reais"
SINTETICAS = APOLICES / "sinteticas"
HOLDOUT = APOLICES / "holdout"
GABARITO = RAIZ / "gabarito"
SAIDA = Path(os.environ.get("PRISMA_SAIDA", RAIZ / "saida"))
BANCO = Path(os.environ.get("PRISMA_BANCO", SAIDA / "prisma.sqlite"))

# --- Upload (portão do PRD de Segurança de Aplicações) ---------------------------------
TAMANHO_MAXIMO_BYTES = 25 * 1024 * 1024
PAGINAS_MAXIMAS = 150
TIPOS_ACEITOS = ("pdf", "png", "jpg")

# --- Leitura ---------------------------------------------------------------------------
# Página com menos caracteres "úteis" que isto no texto nativo vai para o OCR (Lei da Página Mista).
MIN_CARACTERES_TEXTO_NATIVO = 80
DPI_OCR = 200

# --- Verificação de evidência ----------------------------------------------------------
SIMILARIDADE_MINIMA_TRECHO = 0.90

# --- Recuperação ------------------------------------------------------------------------
CLAUSULAS_POR_CAMPO = 6


def carregar_env() -> None:
    """Carrega `.env` se existir. Nunca falha: o sistema roda sem chave nenhuma."""
    arquivo = RAIZ / ".env"
    if not arquivo.exists():
        return
    try:
        from dotenv import load_dotenv

        load_dotenv(arquivo, override=False)
    except ImportError:  # python-dotenv é opcional
        for linha in arquivo.read_text(encoding="utf-8").splitlines():
            linha = linha.strip()
            if linha and not linha.startswith("#") and "=" in linha:
                chave, valor = linha.split("=", 1)
                os.environ.setdefault(chave.strip(), valor.strip())
