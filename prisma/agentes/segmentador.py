# -*- coding: utf-8 -*-
"""Agente Segmentador — transforma páginas em cláusulas com título, numeração e faixa de páginas.

Apólices D&O brasileiras usam pelo menos quatro estilos de título, às vezes no mesmo documento:
  "4. DEFINIÇÕES"                          numerado + caixa alta
  "CLÁUSULA 10ª - LIMITE MÁXIMO DE GARANTIA" cláusula ordinal
  "COBERTURA ADICIONAL DE MULTAS E ..."    caixa alta com palavra-chave (pode quebrar em 2-3 linhas)
  "9.1. Prazo Adicional"                   numerado curto em caixa mista
O índice (linhas com pontilhado "......  34") é ignorado. Linhas numeradas que são frases
("3.1. O presente seguro é contratado...") são corpo de texto, não título.
"""
from __future__ import annotations

import re
from dataclasses import dataclass

from prisma.modelos import Clausula, Documento

PALAVRAS_TITULO = (
    "COBERTURA", "COBERTURAS", "CLÁUSULA", "CLAUSULA", "EXTENSÃO", "EXTENSÕES", "CONDIÇÕES", "CONDIÇÃO",
    "GARANTIA", "GARANTIAS", "ANEXO", "SEÇÃO", "CAPÍTULO", "EXCLUSÃO", "EXCLUSÕES", "ESPECIFICAÇÃO",
    "DEFINIÇÕES", "OBJETO", "LIMITE", "LIMITES", "FRANQUIA", "PRAZO", "VIGÊNCIA", "ÂMBITO", "SUB-ROGAÇÃO",
    "SINISTRO", "SINISTROS", "RETROATIVIDADE", "QUADRO", "RESUMO", "DADOS", "CARACTERÍSTICAS",
)

_RE_INDICE = re.compile(r"\.{4,}\s*\d{0,3}\s*$|\s{2,}\d{1,3}\s*$")
_RE_NUMERADO = re.compile(r"^\s*(\d{1,2}(?:\.\d{1,2}){0,3})\.?\s*[-–—)]?\s+(\S.*?)\s*$")
_RE_CLAUSULA_ORDINAL = re.compile(r"^\s*CL[ÁA]USULA\s+(\d{1,2})\s*[ªºa°]?\s*[-–—:.]?\s*(.*?)\s*$", re.IGNORECASE)
_RE_SECAO = re.compile(r"^\s*CONDI[ÇC][ÕO]ES\s+(GERAIS|ESPECIAIS|PARTICULARES)\b", re.IGNORECASE)


def _fracao_maiusculas(s: str) -> float:
    letras = [c for c in s if c.isalpha()]
    if not letras:
        return 0.0
    return sum(1 for c in letras if c.isupper()) / len(letras)


def _eh_caixa_alta(s: str, minimo: float = 0.85) -> bool:
    return _fracao_maiusculas(s) >= minimo and sum(c.isalpha() for c in s) >= 4


@dataclass
class _Titulo:
    numero: str | None
    titulo: str
    nivel: int


def _classificar_linha(linha: str) -> _Titulo | None:
    s = linha.strip()
    if not s or len(s) > 180 or _RE_INDICE.search(s):
        return None
    m = _RE_CLAUSULA_ORDINAL.match(s)
    if m and (not m.group(2) or _eh_caixa_alta(m.group(2), 0.7)):
        return _Titulo(numero=m.group(1), titulo=s, nivel=1)
    m = _RE_NUMERADO.match(s)
    if m:
        numero, resto = m.group(1), m.group(2)
        nivel = numero.count(".") + 1
        if _eh_caixa_alta(resto, 0.8) and len(resto) >= 4:
            return _Titulo(numero=numero, titulo=resto.strip(" -–—:"), nivel=nivel)
        # título curto em caixa mista: "9.1. Prazo Adicional" (sem ponto final, poucas palavras)
        palavras = resto.split()
        if (len(resto) <= 60 and len(palavras) <= 7 and not resto.endswith((".", ";", ",", ":"))
                and resto[:1].isupper() and nivel >= 2
                and sum(1 for p in palavras if p[:1].isupper()) >= max(1, len(palavras) // 2)):
            return _Titulo(numero=numero, titulo=resto, nivel=nivel)
        return None
    # título em caixa alta pode terminar em vírgula quando quebra em várias linhas
    # ("COBERTURA ADICIONAL PARA HERDEIROS, SUCESSORES, REPRESENTANTES LEGAIS, ESPÓLIO,")
    if _eh_caixa_alta(s) and len(s) >= 8 and not s.endswith((".", ";")):
        primeira = s.split()[0].strip(":-–").upper()
        if primeira in PALAVRAS_TITULO:
            return _Titulo(numero=None, titulo=s, nivel=1)
    return None


def _linhas_com_pagina(doc: Documento) -> list[tuple[int, str]]:
    out = []
    for p in doc.paginas:
        for linha in p.texto.splitlines():
            out.append((p.numero, linha))
    return out


def paginas_de_indice(doc: Documento) -> set[int]:
    """Página com 5+ linhas de índice (pontilhado + número) é índice, não conteúdo."""
    return {p.numero for p in doc.paginas
            if sum(1 for l in p.texto.splitlines() if _RE_INDICE.search(l.strip()) and len(l.strip()) > 8) >= 5}


def _proxima_nao_vazia(linhas: list[tuple[int, str]], i: int) -> str:
    for _, l in linhas[i + 1:i + 6]:
        if l.strip():
            return l.strip()
    return ""


def segmentar(doc: Documento) -> list[Clausula]:
    indice = paginas_de_indice(doc)
    linhas = _linhas_com_pagina(doc)
    clausulas: list[Clausula] = []
    secao = "especificacao" if doc.ficticio else ""
    atual: dict | None = None
    corpo: list[tuple[int, str]] = []

    def fechar(pagina_fim: int):
        nonlocal atual, corpo
        if atual is not None:
            while corpo and not corpo[0][1].strip():
                corpo.pop(0)
            while corpo and not corpo[-1][1].strip():
                corpo.pop()
            texto = "\n".join(l for _, l in corpo)
            if texto or atual["titulo"]:
                idx = len(clausulas)
                clausulas.append(Clausula(
                    id=f"{doc.id}-c{idx:03d}", doc_id=doc.id, numero=atual["numero"],
                    titulo=atual["titulo"], nivel=atual["nivel"], pagina_inicio=atual["pagina"],
                    pagina_fim=max([pg for pg, _ in corpo] + [atual["pagina"]]), texto=texto,
                    secao=atual["secao"], mapa_paginas=[pg for pg, _ in corpo],
                ))
        atual, corpo = None, []

    i = 0
    ultima_pagina = linhas[0][0] if linhas else 1
    while i < len(linhas):
        pagina, linha = linhas[i]
        ultima_pagina = pagina
        m_secao = _RE_SECAO.match(linha.strip())
        if (m_secao and pagina not in indice and not _RE_INDICE.search(linha) and len(linha.strip()) < 120
                and (len(linha.split()) >= 4 or _classificar_linha(_proxima_nao_vazia(linhas, i)) is not None)):
            secao = "condicoes_" + m_secao.group(1).lower()
        t = None if pagina in indice else _classificar_linha(linha)
        if t is None:
            if atual is None:  # texto antes do primeiro título vira preâmbulo (ou índice)
                rotulo = "ÍNDICE" if pagina in indice else "PREÂMBULO"
                atual = {"numero": None, "titulo": rotulo, "nivel": 1, "pagina": pagina, "secao": secao}
            corpo.append((pagina, linha))
            i += 1
            continue
        # título em caixa alta quebrado em várias linhas: junta as continuações
        titulo = t.titulo
        j = i + 1
        while j < len(linhas) and j - i <= 3:
            prox = linhas[j][1].strip()
            if not prox:
                j += 1
                continue
            if (_eh_caixa_alta(prox) and _classificar_linha(prox) is None and len(prox) < 120
                    and not _RE_INDICE.search(prox) and _eh_caixa_alta(titulo, 0.8)):
                titulo = f"{titulo} {prox}"
                j += 1
                continue
            break
        fechar(pagina)
        atual = {"numero": t.numero, "titulo": re.sub(r"\s+", " ", titulo).strip(), "nivel": t.nivel,
                 "pagina": pagina, "secao": secao}
        i = j
    fechar(ultima_pagina)
    return [c for c in clausulas if len(c.texto) > 0 or c.nivel == 1]


# ---------------------------------------------------------------------------- blocos p/ recuperação
@dataclass
class Bloco:
    """Pedaço de cláusula com tamanho controlado, para caber no contexto do LLM."""
    doc_id: str
    clausula_id: str
    titulo: str
    pagina_inicio: int
    texto: str  # já com marcadores [pág. N] onde a página muda


def blocos(doc: Documento, clausulas: list[Clausula], max_chars: int = 2200) -> list[Bloco]:
    """Divide cada cláusula em blocos de até `max_chars`, cortando em fim de linha, com marcadores
    "[pág. N]" sempre que a página muda — assim o LLM consegue citar a página correta."""
    out: list[Bloco] = []
    for c in clausulas:
        cabecalho = f"{c.numero + ' ' if c.numero else ''}{c.titulo}"
        linhas = c.texto.splitlines() if c.texto else []
        mapa = c.mapa_paginas if len(c.mapa_paginas) == len(linhas) else [c.pagina_inicio] * len(linhas)
        atual: list[str] = []
        tamanho, pag_ini, pag_corrente = 0, c.pagina_inicio, None
        for linha, pg in zip(linhas, mapa):
            if atual and tamanho + len(linha) > max_chars:
                out.append(Bloco(doc.id, c.id, cabecalho, pag_ini, "\n".join(atual)))
                atual, tamanho, pag_corrente = [], 0, None
            if pg != pag_corrente:
                if not atual:
                    pag_ini = pg
                atual.append(f"[pág. {pg}]")
                pag_corrente = pg
            atual.append(linha)
            tamanho += len(linha) + 1
        if atual:
            out.append(Bloco(doc.id, c.id, cabecalho, pag_ini, "\n".join(atual)))
        elif not linhas:
            out.append(Bloco(doc.id, c.id, cabecalho, c.pagina_inicio, f"[pág. {c.pagina_inicio}]"))
    return out
