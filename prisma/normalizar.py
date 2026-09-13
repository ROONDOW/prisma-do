# -*- coding: utf-8 -*-
"""Normalizadores determinísticos (Lei do Cérebro-Músculo: o LLM lê, o código normaliza).

- `texto_busca`: forma canônica de texto para comparar trechos (sem acento, caixa, hifenização).
- `dinheiro`: "R$ 10.000.000,00", "R$ 10 milhões", "10 mi" -> 10000000.0
- `duracao_dias`: "12 (doze) meses", "60 dias", "5 anos" -> dias
- `data`: "01/03/2019", "1º de março de 2019", "ilimitada" -> "2019-03-01" | "ilimitada"
"""
from __future__ import annotations

import re
import unicodedata
from datetime import date
from typing import Optional

_MESES = {
    "janeiro": 1, "fevereiro": 2, "marco": 3, "abril": 4, "maio": 5, "junho": 6,
    "julho": 7, "agosto": 8, "setembro": 9, "outubro": 10, "novembro": 11, "dezembro": 12,
}


def sem_acento(s: str) -> str:
    return "".join(c for c in unicodedata.normalize("NFD", s) if unicodedata.category(c) != "Mn")


def texto_busca(s: str) -> str:
    """Canoniza para busca de trecho: junta hifenização de fim de linha, tira acento,
    minúsculas, troca aspas/traços tipográficos e colapsa todo espaço em branco."""
    if not s:
        return ""
    s = re.sub(r"(\w)-\s*\n\s*(\w)", r"\1\2", s)  # respon-\nsabilidade
    s = s.replace("­", "")  # hífen suave
    s = s.translate(str.maketrans({"“": '"', "”": '"', "‘": "'", "’": "'", "–": "-", "—": "-", "º": "o", "ª": "a", "°": "o"}))
    s = sem_acento(s).lower()
    s = re.sub(r"[^\w%$/.,;:()\"'\-]+", " ", s)
    return re.sub(r"\s+", " ", s).strip()


# ---------------------------------------------------------------------------- dinheiro
_RE_DINHEIRO = re.compile(
    r"R\$\s*([0-9]{1,3}(?:\.[0-9]{3})+(?:,[0-9]{1,2})?|[0-9]+(?:,[0-9]{1,2})?)\s*"
    r"(mil(?:h(?:ão|ao|ões|oes))?|mi\b|bi(?:lh(?:ão|ao|ões|oes))?|k\b)?",
    re.IGNORECASE,
)


def dinheiro(s: str) -> Optional[float]:
    """Primeiro valor monetário em reais encontrado no texto."""
    if s is None:
        return None
    if isinstance(s, (int, float)):
        return float(s)
    m = _RE_DINHEIRO.search(str(s))
    if not m:
        # aceita número puro ("10000000" ou "10.000.000,00") quando o texto é só o número
        puro = str(s).strip()
        if re.fullmatch(r"[0-9]{1,3}(?:\.[0-9]{3})*(?:,[0-9]{1,2})?|[0-9]+(?:\.[0-9]+)?", puro):
            if "," in puro or re.search(r"\.[0-9]{3}(\.|$)", puro):
                return float(puro.replace(".", "").replace(",", "."))
            return float(puro)
        return None
    numero = float(m.group(1).replace(".", "").replace(",", "."))
    escala = (m.group(2) or "").lower()
    escala = sem_acento(escala)
    if escala.startswith("milh") or escala == "mi":
        numero *= 1_000_000
    elif escala.startswith("bi"):
        numero *= 1_000_000_000
    elif escala in ("mil", "k"):
        numero *= 1_000
    return numero


def formatar_reais(v: Optional[float]) -> str:
    if v is None:
        return "—"
    inteiro, frac = f"{v:,.2f}".split(".")
    return "R$ " + inteiro.replace(",", ".") + "," + frac


# ---------------------------------------------------------------------------- duração
_EXTENSO = {
    "um": 1, "uma": 1, "dois": 2, "duas": 2, "tres": 3, "quatro": 4, "cinco": 5, "seis": 6,
    "sete": 7, "oito": 8, "nove": 9, "dez": 10, "onze": 11, "doze": 12, "dezoito": 18,
    "vinte e quatro": 24, "trinta": 30, "trinta e seis": 36, "sessenta": 60, "noventa": 90,
}
_RE_DURACAO = re.compile(r"(\d{1,4})\s*(?:\([^)]{1,30}\)\s*)?(dias?|mes(?:es)?|anos?)\b", re.IGNORECASE)


def duracao_dias(s: str) -> Optional[int]:
    """Primeira duração do texto em dias (mês = 30, ano = 365)."""
    if s is None:
        return None
    if isinstance(s, (int, float)):
        return int(s)
    t = sem_acento(str(s)).lower()
    m = _RE_DURACAO.search(t)
    if m:
        n, unidade = int(m.group(1)), m.group(2)
    else:
        m2 = re.search(r"\b(" + "|".join(sorted(_EXTENSO, key=len, reverse=True)) + r")\s+(dias?|mes(?:es)?|anos?)\b", t)
        if not m2:
            return None
        n, unidade = _EXTENSO[m2.group(1)], m2.group(2)
    if unidade.startswith("dia"):
        return n
    if unidade.startswith("mes"):
        return n * 30
    return n * 365


def formatar_duracao(dias: Optional[int]) -> str:
    if dias is None:
        return "—"
    if dias % 365 == 0:
        anos = dias // 365
        return f"{anos} ano" + ("s" if anos > 1 else "")
    if dias % 30 == 0:
        meses = dias // 30
        return f"{meses} " + ("meses" if meses > 1 else "mês")
    return f"{dias} dias"


# ---------------------------------------------------------------------------- datas
_RE_DATA_NUM = re.compile(r"\b(\d{1,2})[/.-](\d{1,2})[/.-](\d{4})\b")
_RE_DATA_EXT = re.compile(r"\b(\d{1,2})o?\s+de\s+([a-z]+)\s+de\s+(\d{4})\b")


def data(s: str) -> Optional[str]:
    """ISO 'AAAA-MM-DD', 'ilimitada' ou None."""
    if s is None:
        return None
    t = sem_acento(str(s)).lower().replace("º", "o").replace("°", "o").replace("ª", "a")
    if re.search(r"ilimitad|sem limite de retroatividade|irrestrit", t):
        return "ilimitada"
    for rx, conv in ((_RE_DATA_NUM, lambda m: (int(m[3]), int(m[2]), int(m[1]))),
                     (_RE_DATA_EXT, lambda m: (int(m[3]), _MESES.get(m[2], 0), int(m[1])))):
        m = rx.search(t)
        if m:
            try:
                return date(*conv(m)).isoformat()
            except ValueError:
                continue
    m = re.search(r"\b(\d{4})-(\d{2})-(\d{2})\b", t)
    if m:
        return m.group(0)
    return None


def datas(s: str) -> list[str]:
    achadas = []
    t = sem_acento(str(s)).lower()
    for m in _RE_DATA_NUM.finditer(t):
        try:
            achadas.append(date(int(m[3]), int(m[2]), int(m[1])).isoformat())
        except ValueError:
            pass
    return achadas


def formatar_data(iso: Optional[str]) -> str:
    if not iso:
        return "—"
    if iso == "ilimitada":
        return "ilimitada"
    a, m, d = iso.split("-")
    return f"{d}/{m}/{a}"


def booleano(s) -> Optional[bool]:
    if isinstance(s, bool):
        return s
    if s is None:
        return None
    t = sem_acento(str(s)).strip().lower()
    if t in ("true", "sim", "verdadeiro", "yes", "1"):
        return True
    if t in ("false", "nao", "falso", "no", "0"):
        return False
    return None
