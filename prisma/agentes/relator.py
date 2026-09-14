# -*- coding: utf-8 -*-
"""Agente Relator — resumo executivo e relatório comparativo em PDF.

O resumo por LLM é ANCORADO: recebe só o quadro verificado, e todo valor monetário, data ou prazo
que ele escrever precisa existir no quadro; frase de recomendação de compra é proibida (Lei do
Apoio, não do Conselho). Falhou a checagem -> resumo determinístico.
"""
from __future__ import annotations

import io
import json
import re
from datetime import datetime
from typing import Optional

from prisma import normalizar
from prisma.agentes import comparador
from prisma.llm import Cascata, extrair_json
from prisma.modelos import Comparacao, Documento, Favorabilidade, StatusEvidencia, carregar_esquema

AVISO = ("Apoio à decisão: o quadro compara o TEXTO das apólices campo a campo com regras declaradas. "
         "Não é recomendação de contratação nem análise de cobertura de sinistro concreto.")

_RE_RECOMENDACAO = re.compile(r"recomend|contrate|deve(m)? contratar|melhor op[cç][aã]o|escolha a|sugerimos|aconselh", re.I)
_RE_NUMEROS = re.compile(r"R\$\s*[0-9][0-9.,]*(?:\s*(?:mil(?:h(?:ão|ões|oes|ao))?|mi|bi))?|\b\d{2}/\d{2}/\d{4}\b|\b\d{1,3}\s+(?:meses|mês|anos?|dias)\b", re.I)


def _rotulo(doc: Documento) -> str:
    return doc.rotulo


def resumo_deterministico(comp: Comparacao, docs: list[Documento]) -> str:
    por_id = {d.id: d for d in docs}
    placar = comparador.placar(comp)
    linhas = []
    for d in docs:
        p = placar[d.id]
        linhas.append(f"- {_rotulo(d)}: {p['mais_favoravel']} campo(s) mais favoráveis e "
                      f"{p['menos_favoravel']} menos favoráveis ao segurado.")
    destaques = [l for l in comp.linhas if l.diferente and any(
        f in (Favorabilidade.MAIS_FAVORAVEL, Favorabilidade.MENOS_FAVORAVEL) for f in l.classificacao.values())]
    for l in destaques[:6]:
        melhores = [por_id[k].rotulo for k, f in l.classificacao.items() if f == Favorabilidade.MAIS_FAVORAVEL]
        valores = "; ".join(f"{por_id[k].rotulo}: {v.valor_texto if v and v.status == StatusEvidencia.VERIFICADO else 'não localizado'}"
                            for k, v in l.valores.items())
        linhas.append(f"- {l.rotulo}: mais favorável em {', '.join(melhores)} ({valores}).")
    atencao = [a for a in comp.alertas if a.severidade == "atencao"]
    if atencao:
        linhas.append(f"- Conformidade: {len(atencao)} ponto(s) de atenção para revisão humana.")
    return "\n".join(linhas)


def _quadro_para_llm(comp: Comparacao, docs: list[Documento]) -> tuple[str, set[str]]:
    por_id = {d.id: d for d in docs}
    permitidos: set[str] = set()
    tabela = []
    for l in comp.linhas:
        valores = {}
        for k, v in l.valores.items():
            if v and v.status == StatusEvidencia.VERIFICADO:
                valores[por_id[k].rotulo] = v.valor_texto
                permitidos.update(normalizar.texto_busca(m.group(0)) for m in _RE_NUMEROS.finditer(v.valor_texto))
        if not valores:
            continue
        tabela.append({"campo": l.rotulo, "valores": valores,
                       "favorabilidade": {por_id[k].rotulo: f.value for k, f in l.classificacao.items()},
                       "regra": l.motivo[:200]})
    alertas = [{"documento": por_id[a.doc_id].rotulo, "artigo": a.artigo, "mensagem": a.mensagem} for a in comp.alertas]
    return json.dumps({"quadro": tabela, "alertas": alertas}, ensure_ascii=False), permitidos


SISTEMA_RESUMO = """Você escreve o resumo executivo de uma comparação de apólices D&O para um corretor.
Use SOMENTE os dados do JSON. Regras:
1. 5 a 7 tópicos curtos, em português, começando com "- ".
2. Todo valor em reais, data ou prazo que você citar deve aparecer exatamente como está no JSON.
3. Não recomende contratar nenhuma apólice e não diga qual é "a melhor": descreva diferenças e onde cada
   documento é mais ou menos favorável ao segurado, segundo a coluna favorabilidade.
4. Mencione os alertas de conformidade, se houver.
Responda apenas JSON: {"topicos": ["- ...", "- ..."]}"""


def resumo(comp: Comparacao, docs: list[Documento], cascata: Optional[Cascata]) -> tuple[str, str]:
    """Devolve (texto, modo)."""
    base = resumo_deterministico(comp, docs)
    if cascata is None:
        return base, "deterministico"
    dados, permitidos = _quadro_para_llm(comp, docs)
    try:
        texto, provedor = cascata.perguntar(SISTEMA_RESUMO, dados)
        topicos = (extrair_json(texto) or {}).get("topicos") or []
    except Exception:
        return base, "deterministico (LLM indisponível)"
    corpo = "\n".join(str(t).strip() for t in topicos if str(t).strip())
    if not corpo:
        return base, "deterministico (resposta vazia do LLM)"
    if _RE_RECOMENDACAO.search(corpo):
        return base, "deterministico (LLM recomendou contratação; descartado)"
    citados = {normalizar.texto_busca(m.group(0)) for m in _RE_NUMEROS.finditer(corpo)}
    fora = [c for c in citados if c not in permitidos]
    if fora:
        return base, f"deterministico (LLM citou valor fora do quadro: {fora[0]})"
    return corpo, f"llm:{provedor}"


# ============================================================================ PDF
def _seguro(texto: str) -> str:
    """Helvetica (WinAnsi) não tem todos os símbolos; e o texto vem de PDF de terceiros."""
    texto = (texto or "").replace("≥", ">=").replace("≤", "<=").replace("→", "->").replace("✓", "v")
    texto = texto.encode("cp1252", errors="replace").decode("cp1252")
    return texto.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


CORES = {"mais_favoravel": "#d8f0dc", "menos_favoravel": "#f8d9d6", "intermediaria": "#fdf1d0",
         "equivalente": "#e8eef7", "nao_comparavel": "#ffffff"}
ROTULO_FAV = {"mais_favoravel": "mais favorável", "menos_favoravel": "menos favorável", "intermediaria": "intermediária",
              "equivalente": "equivalente", "nao_comparavel": ""}


def pdf_comparativo(comp: Comparacao, docs: list[Documento], modo_extracao: str) -> bytes:
    from reportlab.lib import colors
    from reportlab.lib.pagesizes import A4, landscape
    from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
    from reportlab.lib.units import mm
    from reportlab.platypus import PageBreak, Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

    esq = carregar_esquema()
    por_id = {d.id: d for d in docs}
    buf = io.BytesIO()
    doc_pdf = SimpleDocTemplate(buf, pagesize=landscape(A4), leftMargin=12 * mm, rightMargin=12 * mm,
                                topMargin=12 * mm, bottomMargin=12 * mm, title="PRISMA D&O — Relatório comparativo")
    base = getSampleStyleSheet()
    st = {
        "t": ParagraphStyle("t", parent=base["Title"], fontName="Helvetica-Bold", fontSize=18, textColor=colors.HexColor("#1f2a44")),
        "h": ParagraphStyle("h", parent=base["Heading2"], fontName="Helvetica-Bold", fontSize=12, textColor=colors.HexColor("#1f2a44")),
        "p": ParagraphStyle("p", parent=base["Normal"], fontName="Helvetica", fontSize=8.5, leading=11),
        "c": ParagraphStyle("c", parent=base["Normal"], fontName="Helvetica", fontSize=7.5, leading=9.5),
        "aviso": ParagraphStyle("a", parent=base["Normal"], fontName="Helvetica-Oblique", fontSize=8, textColor=colors.HexColor("#555555")),
        "ficticio": ParagraphStyle("f", parent=base["Normal"], fontName="Helvetica-Bold", fontSize=9, textColor=colors.HexColor("#b00020")),
    }
    e = []
    e.append(Paragraph("PRISMA D&amp;O — Relatório comparativo de apólices", st["t"]))
    e.append(Paragraph(_seguro(f"Gerado em {datetime.now():%d/%m/%Y %H:%M} · extração: {modo_extracao} · resumo: {comp.modo_resumo}"), st["p"]))
    e.append(Paragraph(_seguro(AVISO), st["aviso"]))
    if any(d.ficticio for d in docs):
        e.append(Paragraph("Contém DOCUMENTO FICTÍCIO (demonstração acadêmica): valores e seguradoras inventados.", st["ficticio"]))
    e.append(Spacer(1, 6))
    e.append(Paragraph("Documentos comparados", st["h"]))
    linhas_docs = [["Documento", "Tipo", "Páginas", "Origem"]]
    for d in docs:
        origem = "fictício" if d.ficticio else (d.metadados.get("url", "enviado pelo usuário") or "")
        linhas_docs.append([Paragraph(_seguro(d.rotulo), st["c"]), "especificação" if d.ficticio else "condições",
                            str(len(d.paginas)), Paragraph(_seguro(origem[:110]), st["c"])])
    t = Table(linhas_docs, colWidths=[80 * mm, 30 * mm, 18 * mm, 140 * mm])
    t.setStyle(TableStyle([("GRID", (0, 0), (-1, -1), 0.3, colors.grey), ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#1f2a44")),
                           ("TEXTCOLOR", (0, 0), (-1, 0), colors.white), ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
                           ("FONTSIZE", (0, 0), (-1, -1), 8), ("VALIGN", (0, 0), (-1, -1), "TOP")]))
    e += [t, Spacer(1, 6), Paragraph("Resumo executivo", st["h"])]
    for linha in (comp.resumo or "").splitlines():
        if linha.strip():
            e.append(Paragraph(_seguro(linha), st["p"]))

    e += [Spacer(1, 6), Paragraph("Quadro comparativo (valores com evidência verificada)", st["h"])]
    largura_campo = 55 * mm
    largura_doc = (273 * mm - largura_campo) / max(1, len(docs))
    for grupo_id, grupo_nome in esq.grupos.items():
        linhas = [l for l in comp.linhas if l.grupo == grupo_id]
        cab = [Paragraph(f"<b>{_seguro(grupo_nome)}</b>", st["c"])] + [Paragraph(f"<b>{_seguro(d.rotulo)}</b>", st["c"]) for d in docs]
        dados, estilos = [cab], [("GRID", (0, 0), (-1, -1), 0.3, colors.grey), ("VALIGN", (0, 0), (-1, -1), "TOP"),
                                 ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#dde3ee"))]
        for i, l in enumerate(linhas, start=1):
            linha = [Paragraph(_seguro(l.rotulo), st["c"])]
            for j, d in enumerate(docs, start=1):
                v = l.valores.get(d.id)
                fav = l.classificacao.get(d.id, Favorabilidade.NAO_COMPARAVEL).value
                if v and v.status == StatusEvidencia.VERIFICADO:
                    celula = f"{_seguro(v.valor_texto)}<br/><font size=6 color='#555555'>pág. {v.evidencia.pagina}" \
                             f"{' · ' + ROTULO_FAV[fav] if ROTULO_FAV[fav] else ''}</font>"
                elif v and v.status == StatusEvidencia.NA_ESPECIFICACAO:
                    celula = "<font color='#777777'>definido na especificação</font>"
                else:
                    celula = "<font color='#999999'>não localizado</font>"
                linha.append(Paragraph(celula, st["c"]))
                estilos.append(("BACKGROUND", (j, i), (j, i), colors.HexColor(CORES[fav])))
            dados.append(linha)
        tab = Table(dados, colWidths=[largura_campo] + [largura_doc] * len(docs), repeatRows=1)
        tab.setStyle(TableStyle(estilos))
        e += [tab, Spacer(1, 5)]

    e += [PageBreak(), Paragraph("Conformidade regulatória (indícios para revisão humana)", st["h"])]
    if not comp.alertas:
        e.append(Paragraph("Nenhum alerta disparado pelas regras declaradas.", st["p"]))
    for a in comp.alertas:
        evid = f" Evidência: pág. {a.evidencia.pagina} — \"{a.evidencia.trecho[:200]}\"" if a.evidencia else ""
        e.append(Paragraph(_seguro(f"[{a.severidade.upper()}] {por_id[a.doc_id].rotulo} — {a.artigo}: {a.mensagem}{evid}"), st["p"]))
        e.append(Paragraph(_seguro(f"Fundamento: {a.fundamento}"), st["aviso"]))
        e.append(Spacer(1, 3))

    e += [Spacer(1, 6), Paragraph("Anexo — evidências (trecho literal e página de cada valor)", st["h"])]
    ev = [["Campo", "Documento", "Pág.", "Trecho"]]
    for l in comp.linhas:
        for d in docs:
            v = l.valores.get(d.id)
            if v and v.status == StatusEvidencia.VERIFICADO:
                ev.append([Paragraph(_seguro(l.rotulo), st["c"]), Paragraph(_seguro(d.rotulo), st["c"]),
                           str(v.evidencia.pagina), Paragraph(_seguro(v.evidencia.trecho[:320]), st["c"])])
    t = Table(ev, colWidths=[50 * mm, 45 * mm, 12 * mm, 166 * mm], repeatRows=1)
    t.setStyle(TableStyle([("GRID", (0, 0), (-1, -1), 0.3, colors.grey), ("VALIGN", (0, 0), (-1, -1), "TOP"),
                           ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#dde3ee")), ("FONTSIZE", (0, 0), (-1, -1), 7.5)]))
    e.append(t)
    doc_pdf.build(e)
    return buf.getvalue()
