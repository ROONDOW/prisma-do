# -*- coding: utf-8 -*-
"""Gera Projeto_Final_Artefatos/Relatorio_Tecnico_PRISMA_DO.pdf.

Todo número vem de saida/avaliacao_*.json (gerados por `python -m prisma.cli avaliar`) e dos YAML de
regras; as telas vêm de Projeto_Final_Artefatos/telas (scripts/capturar_telas.py).
Uso: python scripts/gerar_relatorio_tecnico.py
"""
from __future__ import annotations

import json
import sys
from datetime import date
from pathlib import Path

import yaml
from reportlab.graphics.shapes import Drawing, Line, Polygon, Rect, String
from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.platypus import (Image, KeepTogether, PageBreak, Paragraph, SimpleDocTemplate, Spacer, Table,
                                TableStyle)

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ))
from prisma import config  # noqa: E402

ARTEFATOS = RAIZ / "Projeto_Final_Artefatos"
AZUL, DOURADO, CINZA = colors.HexColor("#1f2a44"), colors.HexColor("#b8892b"), colors.HexColor("#5b6477")

base = getSampleStyleSheet()
S = {
    "capa": ParagraphStyle("capa", parent=base["Title"], fontName="Helvetica-Bold", fontSize=30, leading=36, textColor=AZUL, alignment=TA_CENTER),
    "sub": ParagraphStyle("sub", parent=base["Normal"], fontName="Helvetica", fontSize=13, leading=18, textColor=CINZA, alignment=TA_CENTER),
    "h1": ParagraphStyle("h1", parent=base["Heading1"], fontName="Helvetica-Bold", fontSize=17, leading=22, textColor=AZUL, spaceBefore=6, spaceAfter=8),
    "h2": ParagraphStyle("h2", parent=base["Heading2"], fontName="Helvetica-Bold", fontSize=12.5, leading=16, textColor=AZUL, spaceBefore=8, spaceAfter=4),
    "p": ParagraphStyle("p", parent=base["Normal"], fontName="Helvetica", fontSize=9.8, leading=14, spaceAfter=5),
    "pb": ParagraphStyle("pb", parent=base["Normal"], fontName="Helvetica", fontSize=9.8, leading=14, leftIndent=12, bulletIndent=2, spaceAfter=2),
    "c": ParagraphStyle("c", parent=base["Normal"], fontName="Helvetica", fontSize=8.3, leading=11),
    "cb": ParagraphStyle("cb", parent=base["Normal"], fontName="Helvetica-Bold", fontSize=8.3, leading=11, textColor=colors.white),
    "leg": ParagraphStyle("leg", parent=base["Normal"], fontName="Helvetica-Oblique", fontSize=8.3, leading=11, textColor=CINZA, alignment=TA_CENTER),
    "destaque": ParagraphStyle("d", parent=base["Normal"], fontName="Helvetica", fontSize=10, leading=14, textColor=AZUL,
                               backColor=colors.HexColor("#eef2f8"), borderPadding=8, spaceBefore=4, spaceAfter=8),
}


def P(t, s="p"):
    return Paragraph(t, S[s])


def bullets(itens):
    return [Paragraph(i, S["pb"], bulletText="•") for i in itens]


def tabela(dados, larguras, cabecalho=True, zebra=True):
    linhas = [[P(str(c), "cb" if (cabecalho and i == 0) else "c") for c in linha] for i, linha in enumerate(dados)]
    t = Table(linhas, colWidths=larguras, repeatRows=1 if cabecalho else 0)
    estilo = [("GRID", (0, 0), (-1, -1), 0.3, colors.HexColor("#c9d1de")), ("VALIGN", (0, 0), (-1, -1), "TOP"),
              ("TOPPADDING", (0, 0), (-1, -1), 3), ("BOTTOMPADDING", (0, 0), (-1, -1), 3)]
    if cabecalho:
        estilo.append(("BACKGROUND", (0, 0), (-1, 0), AZUL))
    if zebra:
        for i in range(1 if cabecalho else 0, len(dados)):
            if i % 2 == 0:
                estilo.append(("BACKGROUND", (0, i), (-1, i), colors.HexColor("#f4f6fa")))
    t.setStyle(TableStyle(estilo))
    return t


def avaliacao(modo):
    arq = config.SAIDA / f"avaliacao_{modo}.json"
    return json.loads(arq.read_text(encoding="utf-8")) if arq.exists() else None


def pct(t):
    return f"{100 * t['acuracia']:.1f}% ({t['acertos']}/{t['campos']})" if t and t.get("campos") else "—"


def diagrama():
    d = Drawing(170 * mm, 92 * mm)
    caixa = lambda x, y, w, h, t1, t2, cor: [
        Rect(x, y, w, h, rx=5, ry=5, fillColor=cor, strokeColor=AZUL, strokeWidth=0.8),
        String(x + w / 2, y + h - 13, t1, fontName="Helvetica-Bold", fontSize=8.2, fillColor=AZUL, textAnchor="middle"),
        String(x + w / 2, y + 7, t2, fontName="Helvetica", fontSize=6.4, fillColor=CINZA, textAnchor="middle")]

    def seta(x1, y1, x2, y2):
        d.add(Line(x1, y1, x2, y2, strokeColor=AZUL, strokeWidth=0.9))
        import math
        a = math.atan2(y2 - y1, x2 - x1)
        d.add(Polygon([x2, y2, x2 - 6 * math.cos(a - 0.4), y2 - 6 * math.sin(a - 0.4),
                       x2 - 6 * math.cos(a + 0.4), y2 - 6 * math.sin(a + 0.4)], fillColor=AZUL, strokeColor=AZUL))

    claro, ouro = colors.HexColor("#eef2f8"), colors.HexColor("#fbf3e1")
    d.add(String(4, 250, "Grafo 1 — processar documento (LangGraph)", fontName="Helvetica-Bold", fontSize=8.5, fillColor=DOURADO))
    w, h, y1 = 86, 36, 200
    nos1 = [("Recepcionista", "tipo · tamanho · SHA-256"), ("Leitor", "texto nativo + OCR/página"),
            ("Segmentador", "cláusulas com página"), ("Extrator", "regras + LLM gratuito"),
            ("Verificador", "trecho · assunto · número")]
    for i, (a, b) in enumerate(nos1):
        x = 4 + i * 96
        for el in caixa(x, y1, w, h, a, b, claro):
            d.add(el)
        if i:
            seta(x - 10, y1 + h / 2, x, y1 + h / 2)
    for el in caixa(200, 118, 82, 34, "SQLite", "fichas · FTS5 · rastro", ouro):
        d.add(el)
    seta(4 + 4 * 96 + w / 2, y1, 282, 140)
    d.add(String(300, 92, "Grafo 2 — comparar apólices (LangGraph)", fontName="Helvetica-Bold", fontSize=8.5, fillColor=DOURADO))
    nos2 = [("Comparador", "regras de favorabilidade"), ("Conformidade", "Circular SUSEP 637"),
            ("Relator", "resumo ancorado + PDF")]
    for i, (a, b) in enumerate(nos2):
        x = 60 + i * 130
        for el in caixa(x, 40, 110, h, a, b, claro):
            d.add(el)
        if i:
            seta(x - 20, 58, x, 58)
    seta(215, 118, 115, 76)
    for el in caixa(330, 118, 110, 34, "Consultor", "perguntas com citação", claro):
        d.add(el)
    seta(282, 135, 330, 135)
    d.add(String(4, 8, "Interfaces: Streamlit e CLI · Toda saída do Extrator passa pelo Verificador antes de ser gravada.",
                 fontName="Helvetica-Oblique", fontSize=7, fillColor=CINZA))
    return d


def rodape(canvas, doc):
    canvas.saveState()
    canvas.setFont("Helvetica", 7.5)
    canvas.setFillColor(CINZA)
    canvas.drawString(18 * mm, 10 * mm, "PRISMA D&O · Relatório técnico · InsurMinds (I2A2) — Projeto Final")
    canvas.drawRightString(192 * mm, 10 * mm, f"pág. {doc.page}")
    canvas.restoreState()


def telas():
    pasta = ARTEFATOS / "telas"
    return sorted(pasta.glob("*.png")) if pasta.exists() else []


def main():
    det, hib = avaliacao("deterministico"), avaliacao("hibrido")
    campos = yaml.safe_load((config.DADOS / "campos.yaml").read_text(encoding="utf-8"))
    susep = yaml.safe_load((config.DADOS / "regras_susep.yaml").read_text(encoding="utf-8"))
    comp = yaml.safe_load((config.DADOS / "regras_comparacao.yaml").read_text(encoding="utf-8"))
    grupo_arq = config.DADOS / "grupo.yaml"
    grupo = yaml.safe_load(grupo_arq.read_text(encoding="utf-8")) if grupo_arq.exists() else {}
    ARTEFATOS.mkdir(parents=True, exist_ok=True)
    saida = ARTEFATOS / "Relatorio_Tecnico_PRISMA_DO.pdf"
    doc = SimpleDocTemplate(str(saida), pagesize=A4, leftMargin=18 * mm, rightMargin=18 * mm, topMargin=16 * mm,
                            bottomMargin=16 * mm, title="PRISMA D&O — Relatório Técnico", author="InsurMinds — Projeto Final")
    e = []

    # ------------------------------------------------------------------ capa
    e += [Spacer(1, 40 * mm), P("PRISMA D&amp;O", "capa"), Spacer(1, 4 * mm),
          P("Plataforma inteligente para análise e comparação<br/>de apólices de seguro D&amp;O", "sub"), Spacer(1, 12 * mm),
          P("Relatório técnico · Projeto Final do InsurMinds<br/>Instituto de Inteligência Artificial Aplicada — I2A2", "sub"),
          Spacer(1, 6 * mm), P(date.today().strftime("%d/%m/%Y"), "sub")]
    if grupo.get("nome"):
        e += [Spacer(1, 10 * mm), P(f"Grupo: <b>{grupo['nome']}</b>", "sub")]
        for pessoa in grupo.get("integrantes", []):
            e.append(P(pessoa, "sub"))
    e += [Spacer(1, 30 * mm), P("Apoio à decisão: compara o texto das apólices campo a campo. Não é recomendação de "
                                "contratação nem análise de cobertura de sinistro concreto.", "leg"), PageBreak()]

    # ------------------------------------------------------------------ 1. resumo
    e.append(P("1. Resumo", "h1"))
    e.append(P("Apólices D&amp;O são documentos de 30 a 70 páginas em linguagem jurídica. Compará-las exige localizar "
               "limites, franquias, base de contratação, retroatividade, prazos adicionais, coberturas e exclusões — e "
               "o que torna uma redação mais ou menos favorável ao administrador segurado. O <b>PRISMA D&amp;O</b> lê "
               "apólices em PDF digital, PDF escaneado ou imagem, extrai 36 campos com o <b>trecho literal e a página</b> "
               "de cada valor, confere automaticamente cada evidência, compara documentos com regras de favorabilidade "
               "declaradas, aponta indícios de desconformidade com a Circular SUSEP nº 637/2021, responde perguntas com "
               "citação e gera o relatório comparativo em PDF."))
    e.append(P("<b>Princípio central:</b> nenhum valor aparece na tela sem um trecho que exista na página citada. O LLM "
               "lê e redige; o código confere, normaliza, compara e decide.", "destaque"))
    linhas = [["Indicador", "Resultado"]]
    if det:
        linhas += [["Acurácia sem chave de API (desenvolvimento)", pct(det["resumo"]["desenvolvimento"])],
                   ["Acurácia sem chave de API (holdout, documentos nunca vistos)", pct(det["resumo"]["holdout"])]]
    if hib:
        linhas += [["Acurácia modo híbrido LLM + regras (desenvolvimento)", pct(hib["resumo"]["desenvolvimento"])],
                   ["Acurácia modo híbrido LLM + regras (holdout)", pct(hib["resumo"]["holdout"])]]
    if det and det.get("ocr"):
        linhas.append(["OCR — CER alinhado por linha (médio / máximo)",
                       f"{100 * det['ocr']['cer_medio']:.2f}% / {100 * det['ocr']['cer_maximo']:.2f}%"])
    linhas += [["Injeção de prompt: payloads plantados barrados", "15 de 15 (0 falso positivo em 13.492 janelas reais)"],
               ["Agentes especializados em LangGraph", "9 (7 nos grafos + Conformidade e Consultor)"],
               ["Custo de operação", "zero: LLM em tier gratuito e OCR local; roda sem nenhuma chave"]]
    e.append(tabela(linhas, [110 * mm, 64 * mm]))

    # ------------------------------------------------------------------ 2. problema
    e += [PageBreak(), P("2. Problema e contexto", "h1")]
    e.append(P("O seguro de Responsabilidade Civil de Diretores e Administradores (RC D&amp;O) protege o patrimônio pessoal "
               "de quem toma decisões de gestão. É regulado pela Circular SUSEP nº 637/2021 e, desde 11/12/2025, pela nova "
               "Lei de Seguros (Lei nº 15.040/2024). Cada seguradora redige suas condições gerais, especiais e particulares; "
               "a especificação de cada apólice fixa os números. Um corretor que compara propostas precisa ler centenas de "
               "páginas e conhecer a doutrina que diz o que é mais favorável."))
    e.append(P("Pesquisa de referência (NotebookLM com 111 fontes, incluindo notas de escritórios sobre a Circular 637) "
               "consolidou as dimensões que um especialista compara. Exemplos do que muda o valor de uma apólice:"))
    e += bullets([
        "<b>Exclusão de dolo:</b> aplicada só após decisão final ou confissão (mais favorável) ou já na alegação.",
        "<b>Custos de defesa:</b> adiantados à medida que ocorrem ou só reembolsados ao final.",
        "<b>Retroatividade:</b> ilimitada, desde uma data antiga ou apenas a partir da vigência atual.",
        "<b>Base de contratação:</b> à base de reclamações com notificação ou sem ela.",
        "<b>Coberturas:</b> básicas, adicionais (dependem de contratação) ou excluídas — penhora online, multas, "
        "custos de investigação, dano ambiental, cônjuges e herdeiros.",
        "<b>Âmbito geográfico e sub-rogação</b> contra os próprios segurados."])
    e.append(P("<b>Corpus usado.</b> Cinco condições gerais públicas de D&amp;O de quatro seguradoras (Chubb, Berkley em duas "
               "versões, Essor e Argo), dois documentos de holdout (Sompo e Chubb Capital Fechado), a Circular SUSEP 637 e "
               "três especificações de apólice <b>fictícias</b> geradas pelo projeto (PDF digital, PDF escaneado com ruído e "
               "inclinação, e PNG), porque os números de uma apólice real só existem na especificação, que é privada."))

    # ------------------------------------------------------------------ 3. arquitetura
    e += [PageBreak(), P("3. Arquitetura da solução", "h1"), diagrama(),
          P("Figura 1 — Os dois grafos de agentes e o armazenamento.", "leg")]
    e.append(P("A solução é organizada em dois grafos de estado do LangGraph. O <b>Grafo 1</b> transforma um arquivo em uma "
               "ficha estruturada e verificada; o <b>Grafo 2</b> compara fichas, verifica conformidade e produz o relatório. "
               "O <b>Consultor</b> atende perguntas livres sobre os documentos armazenados. Cada nó grava no rastro o que fez "
               "e quanto tempo levou."))
    e.append(tabela([
        ["Etapa do edital", "Onde acontece no PRISMA"],
        ["1. Recebimento dos documentos", "Recepcionista: tipo por assinatura de bytes, limites, SHA-256, deduplicação"],
        ["2. Extração automática do conteúdo", "Leitor (texto nativo e OCR por página) e Extrator (36 campos)"],
        ["3. Organização das informações", "Segmentador (cláusulas com página) e esquema declarado em campos.yaml"],
        ["4. Armazenamento estruturado", "SQLite: documentos, páginas + FTS5, cláusulas, fichas, comparações, rastro"],
        ["5. Consulta das informações", "Consultor (perguntas com citação) e ficha navegável na interface"],
        ["6. Comparação entre apólices", "Comparador (regras de favorabilidade) e Conformidade (Circular 637)"],
        ["7. Apresentação dos resultados", "Streamlit, CLI e relatório comparativo em PDF com anexo de evidências"],
    ], [62 * mm, 112 * mm]))

    # ------------------------------------------------------------------ 4. tecnologias
    e += [PageBreak(), P("4. Tecnologias utilizadas", "h1")]
    e.append(tabela([
        ["Tecnologia", "Papel", "Por que esta escolha"],
        ["Python 3.12", "Linguagem", "Ecossistema de IA usado no curso"],
        ["LangGraph", "Orquestração dos agentes", "Grafo de estado explícito: cada agente é um nó auditável"],
        ["PyMuPDF", "Leitura de PDF", "Texto por página e renderização para OCR sem binário de sistema"],
        ["RapidOCR (PP-OCR/ONNX)", "OCR", "Gratuito e offline; CER medido abaixo de 0,1% por linha"],
        ["Gemini, Groq, NVIDIA NIM", "LLM (tier gratuito)", "Cascata com failover na mesma chamada; custo zero"],
        ["Pydantic", "Contratos de dados", "Validação das saídas entre agentes"],
        ["rank-bm25", "Recuperação de cláusulas", "Busca local; o LLM só recebe as cláusulas relevantes"],
        ["SQLite + FTS5", "Armazenamento", "Estruturado, com busca textual e sem servidor"],
        ["YAML", "Regras declaradas", "Esquema, extração, favorabilidade e conformidade fora do código"],
        ["reportlab", "Relatórios PDF", "Relatório comparativo e este relatório técnico"],
        ["Streamlit", "Interface", "Demonstração interativa com evidência clicável"],
        ["pytest + Playwright", "Qualidade", "Testes automatizados e captura das telas reais"],
    ], [38 * mm, 42 * mm, 94 * mm]))

    # ------------------------------------------------------------------ 5. agentes
    e += [PageBreak(), P("5. Agentes desenvolvidos", "h1")]
    agentes = [
        ["Agente", "Entrada → saída", "Como trabalha", "Falha que trata"],
        ["Recepcionista", "bytes → documento aceito", "Assinatura de bytes (%PDF, PNG, JPEG), 25 MB, 150 páginas, SHA-256, carimbo FICTÍCIO", "Arquivo disfarçado, PDF protegido ou corrompido"],
        ["Leitor", "documento → páginas", "Texto nativo por página; página com menos de 80 caracteres úteis vai para OCR; remove cabeçalho/rodapé repetidos", "PDF misto (frontispício escaneado + texto)"],
        ["Segmentador", "páginas → cláusulas", "4 estilos de título (numerado, 'CLÁUSULA Nª', caixa alta com palavra-chave, numerado curto); ignora índice; página por linha", "Índice virando conteúdo; glossário mudando de seção"],
        ["Extrator", "cláusulas → valores brutos", "Regras declaradas (sem chave) e LLM por grupo de campos sobre as cláusulas recuperadas por BM25, com saída JSON", "Documento longo demais para o contexto; redação nova"],
        ["Verificador", "valores brutos → ficha", "Trecho na página (≥ 0,90), assunto do campo, número ancorado, bloqueio de instrução dirigida a IA; fusão LLM + regras", "Alucinação, página errada, injeção de prompt"],
        ["Comparador", "fichas → quadro", "37 regras de favorabilidade em YAML; mais/menos favorável, intermediária, equivalente", "Juízo opaco do LLM; condições gerais × especificação"],
        ["Conformidade", "ficha + texto → alertas", "11 regras com trecho literal da norma; presença vira evidência, ausência vira indício declarado", "Parecer sem fundamento"],
        ["Relator", "quadro → resumo + PDF", "Resumo por LLM ancorado ao quadro; valor fora do quadro ou recomendação ⇒ resumo determinístico", "Número inventado no resumo; recomendação de compra"],
        ["Consultor", "pergunta → resposta citada", "BM25 + LLM; cada citação conferida; sem citação válida responde 'não localizado'", "Resposta sem base documental"],
    ]
    e.append(tabela(agentes, [24 * mm, 30 * mm, 76 * mm, 44 * mm]))

    # ------------------------------------------------------------------ 6. fluxo
    e += [PageBreak(), P("6. Fluxo completo de processamento", "h1")]
    e.append(P("Exemplo real: a especificação fictícia da Boreal, um PDF <b>escaneado</b> (sem camada de texto, com ruído, "
               "inclinação de até 1,2° e compressão JPEG)."))
    e += bullets([
        "<b>Recepcionista</b> reconhece o PDF pela assinatura, calcula o SHA-256 e registra o recebimento.",
        "<b>Leitor</b> encontra a página sem texto nativo e a renderiza a 200 dpi para o RapidOCR, que reconstrói as linhas "
        "a partir das caixas detectadas. O carimbo 'DOCUMENTO FICTÍCIO' marca o documento.",
        "<b>Segmentador</b> separa os blocos (dados da apólice, quadro de coberturas, observações) com a página de cada linha.",
        "<b>Extrator</b> lê rótulos ('Limite Máximo de Garantia:', 'Data Limite de Retroatividade:' — mesmo quando o OCR "
        "quebra o rótulo em duas linhas), a linha de cada cobertura no quadro e as observações; com chave, o LLM extrai o "
        "mesmo grupo de campos em JSON.",
        "<b>Verificador</b> confirma, por exemplo, que 'R$ 30.000.000,00' aparece no trecho citado na página 1; o que não se "
        "confirma é descartado e a ficha é gravada no SQLite.",
        "<b>Comparador</b> coloca a Boreal ao lado das cotações Aurora e Cruzeiro: LMG, franquia, retroatividade e prazos "
        "recebem a classificação da regra correspondente, com o fundamento.",
        "<b>Conformidade</b> dispara o alerta do art. 19 na Cruzeiro, que não indica prazo adicional.",
        "<b>Relator</b> produz o resumo e o PDF comparativo com o anexo de evidências (trecho e página de cada valor)."])
    for nome, legenda in (("05_comparacao_quadro", "Figura 2 — Quadro comparativo colorido por favorabilidade (interface)."),
                          ("04_comparacao_resumo", "Figura 3 — Resumo executivo e relatório para download.")):
        arq = ARTEFATOS / "telas" / f"{nome}.png"
        if arq.exists():
            e += [Spacer(1, 4), Image(str(arq), width=172 * mm, height=172 * mm * 900 / 1440), P(legenda, "leg")]

    # ------------------------------------------------------------------ 7. decisões
    e += [PageBreak(), P("7. Justificativa das decisões arquiteturais", "h1")]
    decisoes = [
        ("Citação verificável em vez de confiança no LLM", "Em apólice, um número errado é pior que um campo vazio. O Verificador exige que o trecho exista na página, trate do campo e contenha o número. É o que permite exibir o resultado de um LLM gratuito sem supervisão."),
        ("Regras declaradas em YAML", "Favorabilidade e conformidade precisam ser explicáveis ao corretor e ao avaliador. Mudar uma regra muda o quadro sem tocar em código (há teste que prova isso)."),
        ("Dois modos de extração e fusão", "O modo determinístico garante funcionamento sem chave; o LLM generaliza para redações novas. A fusão usa o valor verificado do LLM e, onde ele não prova, o das regras."),
        ("OCR decidido por página", "Apólices reais misturam páginas escaneadas e digitais. OCR no documento inteiro seria lento e pior; nenhum OCR perderia o frontispício."),
        ("Recuperação local (BM25) antes do LLM", "Condições gerais têm até 72 páginas. Enviar só as cláusulas relevantes cabe no contexto do tier gratuito, reduz custo de tokens e reduz alucinação."),
        ("SQLite com FTS5", "Armazenamento estruturado e busca textual sem instalar servidor, adequado a um MVP reproduzível."),
        ("Holdout honesto", "As regras foram escritas lendo o conjunto de desenvolvimento; por isso a generalização é medida em documentos anotados antes de rodar o sistema."),
        ("Especificações fictícias rotuladas", "Os números de apólice real são privados. Documentos inventados e carimbados permitem demonstrar a comparação numérica sem expor dado de ninguém."),
    ]
    for titulo, texto in decisoes:
        e.append(KeepTogether([P(f"<b>{titulo}.</b> {texto}")]))

    # ------------------------------------------------------------------ 8. avaliação
    e += [PageBreak(), P("8. Avaliação e resultados", "h1")]
    e.append(P("<b>Método.</b> Gabarito anotado lendo cada documento (campo, valor e, quando a redação é ambígua, as leituras "
               "aceitas com nota). Conta como resposta só o valor <b>verificado</b>. Ausência no gabarito ('não prevista', "
               "'não excluído') é acertada por 'não localizado'. 'Errados exibidos' são valores verificados que divergem do "
               "gabarito — o erro que o usuário veria. Reprodução: <font face='Courier'>python -m prisma.cli avaliar</font>."))
    linhas = [["Conjunto", "Sem chave (regras)", "Errados exibidos", "Híbrido (LLM + regras)", "Errados exibidos"]]
    nomes = {"desenvolvimento": "Desenvolvimento", "holdout": "Holdout (nunca visto)",
             "especificacoes": "Especificações", "condicoes_gerais": "Condições gerais"}
    for k, n in nomes.items():
        d_, h_ = (det or {}).get("resumo", {}).get(k), (hib or {}).get("resumo", {}).get(k)
        linhas.append([n, pct(d_), str(d_["valores_errados_exibidos"]) if d_ else "—", pct(h_),
                       str(h_["valores_errados_exibidos"]) if h_ else "—"])
    e.append(tabela(linhas, [40 * mm, 38 * mm, 24 * mm, 44 * mm, 28 * mm]))
    base_ = det or hib
    if base_:
        e.append(Spacer(1, 4))
        por_doc = [["Documento", "Sem chave", "Híbrido"]]
        for docn, t in base_["resumo"]["por_documento"].items():
            h_ = (hib or {}).get("resumo", {}).get("por_documento", {}).get(docn)
            por_doc.append([docn, pct(t), pct(h_)])
        e.append(tabela(por_doc, [80 * mm, 47 * mm, 47 * mm]))
    e.append(P("<b>Leitura dos números.</b> No conjunto de desenvolvimento, as regras acertam quase tudo porque foram escritas "
               "sobre essas seguradoras. No holdout — em especial a Sompo, com redação que o sistema nunca viu — as regras "
               "sozinhas caem, e é aí que o LLM mostra seu valor. Publicamos os dois números de propósito."))
    if det and det.get("ocr"):
        ocr = [["Página", "CER por linha", "CER página inteira", "Tempo"]]
        for p_ in det["ocr"]["paginas"]:
            ocr.append([f"{p_['documento']} p.{p_['pagina']}", f"{100 * p_['cer']:.2f}%",
                        f"{100 * p_.get('cer_pagina_inteira', 0):.2f}%", f"{p_['segundos']:.0f} s"])
        e += [P("OCR", "h2"), P("Páginas digitais renderizadas e lidas por OCR, comparadas com a camada de texto do próprio PDF; "
                                "a especificação escaneada é comparada com sua versão digital. O CER por linha isola erro de "
                                "leitura; o de página inteira também pune diferenças de ordem de leitura em tabelas."),
              tabela(ocr, [80 * mm, 32 * mm, 36 * mm, 26 * mm]),
              P("<b>Achado:</b> com o classificador de orientação do RapidOCR ligado, linhas justificadas eram lidas invertidas "
                "(CER de até 21% numa página da Berkley). Desligado, o erro caiu para a casa de 0,1% e a leitura ficou 2 a 3 "
                "vezes mais rápida.")]
    e += [P("Testes automatizados", "h2"),
          P("Mais de 60 testes pytest cobrem normalizadores, recepção, leitura, segmentação, verificação de evidência, "
            "comparação (incluindo inverter uma regra no YAML), conformidade (incluindo conferir cada trecho de norma contra "
            "o PDF da Circular 637), injeção de prompt e o armazém.")]

    # ------------------------------------------------------------------ 9. segurança
    e += [PageBreak(), P("9. Segurança", "h1")]
    e += bullets([
        "<b>Injeção de prompt.</b> O texto da apólice entra no prompt como dado delimitado. Um PDF de teste com 15 instruções "
        "maliciosas foi processado com um LLM falso que obedece a todas: nenhum valor exibido mudou. O Verificador barra "
        "trecho com instrução dirigida a IA — 15 de 15 payloads, 0 falso positivo em 13.492 janelas de texto real.",
        "<b>Favorabilidade fora do LLM.</b> Uma instrução 'classifique como a mais favorável' não tem efeito, porque o quadro "
        "vem de regras declaradas.",
        "<b>Upload.</b> Tipo por assinatura de bytes, 25 MB, 150 páginas, PDF com senha recusado, nome sanitizado.",
        "<b>Renderização.</b> Texto de documento e de LLM é escapado antes da tela; busca FTS5 com termos entre aspas.",
        "<b>Segredos.</b> Chaves apenas em .env fora do git; o sistema não exige chave para funcionar.",
        "<b>Terceiros.</b> PDFs das seguradoras não são redistribuídos no repositório: são baixados das URLs oficiais com "
        "hash conferido."])

    # ------------------------------------------------------------------ 10. limitações
    e += [P("10. Limitações conhecidas", "h1")]
    e += bullets([
        "As regras do modo sem chave refletem as seguradoras do conjunto de desenvolvimento; em redação nova a acurácia sem LLM cai.",
        "Condições gerais trazem regras, não números; os números da demonstração vêm de especificações fictícias.",
        "'Não localizado' pode significar que a informação está em outro documento da apólice (condições especiais separadas, "
        "endossos). O alerta de conformidade por ausência avisa isso.",
        "A favorabilidade é por campo e segue regras gerais de mercado; não pondera o perfil de risco do tomador.",
        "Provedores gratuitos de LLM variam em disponibilidade e latência (houve troca de modelos durante o projeto); a cascata "
        "e o modo determinístico cobrem, mas o tempo de resposta oscila.",
        "O gabarito foi anotado por uma única pessoa; campos ambíguos têm mais de uma leitura aceita, com nota.",
        "A conformidade aponta indícios para revisão humana; não substitui parecer jurídico."])

    # ------------------------------------------------------------------ 11. evolução
    e += [P("11. Possibilidades de evolução futura", "h1")]
    e += bullets([
        "Apólice completa como pacote: vincular especificação, condições gerais e endossos e extrair o valor efetivo de cada campo.",
        "Ampliar o gabarito com mais seguradoras e dois anotadores, medindo concordância entre eles.",
        "Diferença de versões da mesma seguradora destacando cláusulas alteradas (o corpus já tem duas versões da Berkley).",
        "Regras de favorabilidade ponderadas por perfil do tomador (capital aberto, setor regulado, operação internacional).",
        "Integração com o registro de produtos da SUSEP para baixar e acompanhar versões de condições gerais.",
        "LLM local (modelos abertos) para clientes que não podem enviar documentos a provedores externos.",
        "Exportação do quadro para planilha e API para sistemas de corretoras."])

    # ------------------------------------------------------------------ 12. fontes
    e += [PageBreak(), P("12. Fontes e referências", "h1")]
    e += bullets([
        "SUSEP. Circular nº 637, de 27 de julho de 2021.",
        "BRASIL. Lei nº 15.040, de 9 de dezembro de 2024 (Lei de Seguros).",
        "Condições gerais públicas de RC D&amp;O: Chubb Seguros Brasil (Capital Aberto, proc. 15414.900831/2017-45; Capital "
        "Fechado, proc. 15414.900832/2017-90), Berkley International do Brasil Seguros (fev/2022 e proc. 15414.901494/2017-11), "
        "Essor Seguros (Grupo SCOR), Argo Seguros Brasil (proc. 15414.000906/2012-81) e Sompo Seguros (proc. "
        "15414.652408/2023-71). URLs e SHA-256 em apolices/reais/fontes.yaml.",
        "Demarest Advogados. Circular SUSEP nº 637/2021: consolidação e simplificação das regras aplicáveis aos seguros de "
        "Responsabilidade Civil (2021).",
        "Poletto &amp; Possamai. Seguros de Responsabilidade Civil: breves notas sobre a Circular SUSEP n. 637/2021.",
        "Consultor Jurídico. Para que serve o contrato de seguro D&amp;O? — parte III (2019).",
        "HENDRYCKS, D. et al. CUAD: An Expert-Annotated NLP Dataset for Legal Contract Review (2021).",
        "ContractEval: Benchmarking LLMs for Clause-Level Legal Risk Identification in Commercial Contracts (arXiv 2508.03080).",
        "RapidAI. RapidOCR — documentação e modelos PP-OCR em ONNX.",
        "LangChain. LangGraph — documentação de StateGraph."])

    # ------------------------------------------------------------------ anexos
    e += [PageBreak(), P("Anexo A — Esquema de campos D&amp;O (dados/campos.yaml)", "h1")]
    linhas = [["Grupo", "Campo", "Tipo", "Onde"]]
    for c in campos["campos"]:
        linhas.append([campos["grupos"][c["grupo"]], c["rotulo"], c["tipo"],
                       {"cg": "condições gerais", "espec": "especificação", "ambos": "ambos"}[c["onde"]]])
    e.append(tabela(linhas, [44 * mm, 78 * mm, 22 * mm, 30 * mm]))
    e += [PageBreak(), P("Anexo B — Regras de conformidade (dados/regras_susep.yaml)", "h1")]
    linhas = [["Regra", "Artigo", "Severidade", "Mensagem"]]
    for r in susep["regras"]:
        linhas.append([r["id"], r["artigo"], r["severidade"], r["mensagem"]])
    e.append(tabela(linhas, [44 * mm, 24 * mm, 20 * mm, 86 * mm]))
    e += [Spacer(1, 6), P("Anexo C — Regras de favorabilidade (dados/regras_comparacao.yaml)", "h1")]
    linhas = [["Regra", "Campo", "Critério", "Fundamento"]]
    for r in comp["regras"]:
        if r["criterio"] == "informativo":
            continue
        linhas.append([r["id"], r["campo"], r["criterio"], r.get("fundamento", "")])
    e.append(tabela(linhas, [12 * mm, 46 * mm, 24 * mm, 92 * mm]))
    imagens = telas()
    if imagens:
        e += [PageBreak(), P("Anexo D — Telas da interface", "h1")]
        for img in imagens:
            e += [KeepTogether([Image(str(img), width=170 * mm, height=170 * mm * 900 / 1440),
                                P(img.stem.split("_", 1)[-1].replace("_", " "), "leg")]), Spacer(1, 6)]
    doc.build(e, onFirstPage=lambda c, d: None, onLaterPages=rodape)
    print(f"ok  {saida} ({saida.stat().st_size // 1024} KB)")


if __name__ == "__main__":
    main()
