# -*- coding: utf-8 -*-
"""Agente Leitor — texto de cada página, com OCR só onde precisa (Lei da Página Mista).

- PDF: PyMuPDF extrai o texto nativo página a página. Página com pouco texto útil (escaneada,
  foto, frontispício em imagem) é renderizada e passa pelo RapidOCR.
- PNG/JPG: sempre OCR.
- Depois: remove cabeçalhos e rodapés que se repetem em muitas páginas (numeração, nome do
  produto, processo SUSEP), porque atrapalham a segmentação e a recuperação.

O RapidOCR roda local (ONNX Runtime), gratuito, sem binário de sistema. É carregado sob demanda
e reaproveitado entre páginas.
"""
from __future__ import annotations

import io
import re
from collections import Counter
from typing import Callable, Optional

from prisma import config
from prisma.modelos import MetodoLeitura, Pagina

_OCR = None


def _motor_ocr():
    global _OCR
    if _OCR is None:
        import logging

        from rapidocr import RapidOCR

        logging.getLogger("RapidOCR").setLevel(logging.WARNING)
        _OCR = RapidOCR(params={"Global.log_level": "warning"})
    return _OCR


def _caracteres_uteis(texto: str) -> int:
    return len(re.findall(r"[A-Za-zÀ-ÿ0-9]", texto or ""))


def _agrupar_linhas(caixas, textos, scores) -> tuple[str, float]:
    """Reconstrói linhas a partir das caixas do OCR: agrupa por altura e ordena por x."""
    itens = []
    for caixa, txt, sc in zip(caixas, textos, scores):
        ys = [p[1] for p in caixa]
        xs = [p[0] for p in caixa]
        itens.append((sum(ys) / len(ys), min(xs), max(ys) - min(ys), txt, sc))
    itens.sort(key=lambda i: (i[0], i[1]))
    linhas: list[list] = []
    for it in itens:
        if linhas and abs(it[0] - linhas[-1][0][0]) < max(6.0, 0.5 * it[2]):
            linhas[-1].append(it)
        else:
            linhas.append([it])
    texto = "\n".join(" ".join(i[3] for i in sorted(l, key=lambda i: i[1])) for l in linhas)
    confianca = sum(i[4] for i in itens) / len(itens) if itens else 0.0
    return texto, confianca


def ocr_imagem(imagem_bytes: bytes) -> tuple[str, float]:
    resultado = _motor_ocr()(imagem_bytes)
    if resultado is None or resultado.txts is None or len(resultado.txts) == 0:
        return "", 0.0
    return _agrupar_linhas(resultado.boxes, resultado.txts, resultado.scores)


def ler(conteudo: bytes, tipo_arquivo: str, forcar_ocr: bool = False,
        progresso: Optional[Callable[[int, int, str], None]] = None) -> list[Pagina]:
    if tipo_arquivo in ("png", "jpg"):
        texto, conf = ocr_imagem(conteudo)
        return [Pagina(numero=1, texto=texto, metodo=MetodoLeitura.OCR, confianca_ocr=round(conf, 3))]

    import pymupdf

    paginas: list[Pagina] = []
    with pymupdf.open(stream=conteudo, filetype="pdf") as doc:
        total = doc.page_count
        for i, pg in enumerate(doc):
            texto = pg.get_text("text", sort=False)
            if forcar_ocr or _caracteres_uteis(texto) < config.MIN_CARACTERES_TEXTO_NATIVO:
                png = pg.get_pixmap(dpi=config.DPI_OCR).tobytes("png")
                texto_ocr, conf = ocr_imagem(png)
                paginas.append(Pagina(numero=i + 1, texto=texto_ocr, metodo=MetodoLeitura.OCR,
                                      confianca_ocr=round(conf, 3)))
                metodo = "ocr"
            else:
                paginas.append(Pagina(numero=i + 1, texto=texto))
                metodo = "nativo"
            if progresso:
                progresso(i + 1, total, metodo)
    return remover_cabecalhos_rodapes(paginas)


_RE_NUMERO_PAGINA = re.compile(r"^\s*(p[áa]g(ina)?\.?\s*)?\d{1,3}(\s*(de|/)\s*\d{1,3})?\s*$", re.IGNORECASE)


def _chave_linha(linha: str) -> str:
    # "Página 3 de 72" e "Página 4 de 72" viram a mesma chave
    return re.sub(r"\d+", "#", re.sub(r"\s+", " ", linha.strip().lower()))


def remover_cabecalhos_rodapes(paginas: list[Pagina], fracao_minima: float = 0.5) -> list[Pagina]:
    """Remove linhas que aparecem (com números normalizados) nas 6 primeiras ou 4 últimas
    posições de mais da metade das páginas. Duas passadas, porque cabeçalhos longos só
    "sobem" para a janela depois que a primeira camada sai. Documentos com menos de 4 páginas
    passam intactos."""
    if len(paginas) < 4:
        return paginas
    for _ in range(2):
        paginas = _uma_passada(paginas, fracao_minima)
    return paginas


def _uma_passada(paginas: list[Pagina], fracao_minima: float) -> list[Pagina]:
    contagem: Counter[str] = Counter()
    for p in paginas:
        linhas = [l for l in p.texto.splitlines() if l.strip()]
        bordas = set(_chave_linha(l) for l in linhas[:6] + linhas[-4:])
        contagem.update(bordas)
    limite = fracao_minima * len(paginas)
    repetidas = {k for k, n in contagem.items() if n >= limite and k != "#"}
    limpas = []
    for p in paginas:
        if p.numero == 1:  # a 1ª página guarda o cabeçalho: é onde mora o Processo SUSEP
            limpas.append(p)
            continue
        linhas = p.texto.splitlines()
        nao_vazias = [i for i, l in enumerate(linhas) if l.strip()]
        bordas = set(nao_vazias[:6] + nao_vazias[-4:])
        manter = []
        for i, l in enumerate(linhas):
            if i in bordas and (_chave_linha(l) in repetidas or _RE_NUMERO_PAGINA.match(l)):
                continue
            manter.append(l)
        limpas.append(p.model_copy(update={"texto": "\n".join(manter)}))
    return limpas


def cer(referencia: str, hipotese: str) -> float:
    """Character Error Rate (distância de Levenshtein / tamanho da referência), sobre texto
    normalizado (espaços colapsados). Usado para medir o OCR contra a camada de texto do PDF."""
    ref = re.sub(r"\s+", " ", referencia).strip()
    hip = re.sub(r"\s+", " ", hipotese).strip()
    if not ref:
        return 0.0 if not hip else 1.0
    anterior = list(range(len(hip) + 1))
    for i, cr in enumerate(ref, 1):
        atual = [i] + [0] * len(hip)
        for j, ch in enumerate(hip, 1):
            atual[j] = min(anterior[j] + 1, atual[j - 1] + 1, anterior[j - 1] + (cr != ch))
        anterior = atual
    return anterior[-1] / len(ref)


def imagem_para_png(conteudo: bytes) -> bytes:
    """Garante PNG (usado pela interface ao exibir a página de origem)."""
    import pymupdf

    pix = pymupdf.Pixmap(io.BytesIO(conteudo))
    return pix.tobytes("png")
