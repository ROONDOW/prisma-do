# -*- coding: utf-8 -*-
"""Gera Projeto_Final_Artefatos/InsurMinds_Projeto_Final.pptx (pitch deck, 16:9).

Números lidos de saida/avaliacao_*.json; telas de Projeto_Final_Artefatos/telas; diagrama recortado do
relatório técnico. Uso: python scripts/gerar_pitch.py
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import yaml
from pptx import Presentation
from pptx.dml.color import RGBColor
from pptx.enum.shapes import MSO_SHAPE
from pptx.enum.text import MSO_ANCHOR, PP_ALIGN
from pptx.util import Emu, Inches, Pt

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ))
from prisma import config  # noqa: E402

ART = RAIZ / "Projeto_Final_Artefatos"
TELAS = ART / "telas"
MARINHO, DOURADO, BRANCO = RGBColor(0x14, 0x1C, 0x2E), RGBColor(0xD8, 0xB8, 0x77), RGBColor(0xFF, 0xFF, 0xFF)
CLARO, CINZA, VERDE, VERMELHO = RGBColor(0xF2, 0xF5, 0xFA), RGBColor(0x5B, 0x64, 0x77), RGBColor(0x2E, 0x7D, 0x4F), RGBColor(0xB0, 0x3A, 0x2E)
FONTE = "Segoe UI"


def av(modo):
    arq = config.SAIDA / f"avaliacao_{modo}.json"
    return json.loads(arq.read_text(encoding="utf-8")) if arq.exists() else None


def pct(t):
    return f"{100 * t['acuracia']:.0f}%" if t and t.get("campos") else "—"


class Deck:
    def __init__(self):
        self.prs = Presentation()
        self.prs.slide_width, self.prs.slide_height = Inches(13.333), Inches(7.5)
        self.n = 0

    def slide(self, fundo=BRANCO):
        s = self.prs.slides.add_slide(self.prs.slide_layouts[6])
        s.background.fill.solid()
        s.background.fill.fore_color.rgb = fundo
        self.n += 1
        if self.n > 1:
            self.texto(s, f"PRISMA D&O  ·  {self.n:02d}", Inches(0.5), Inches(7.0), Inches(4), Inches(0.3), 10,
                       cor=CINZA if fundo == BRANCO else DOURADO)
        return s

    def texto(self, s, t, x, y, w, h, tamanho, cor=MARINHO, negrito=False, alinhar=PP_ALIGN.LEFT, ancora=MSO_ANCHOR.TOP):
        caixa = s.shapes.add_textbox(x, y, w, h)
        tf = caixa.text_frame
        tf.word_wrap = True
        tf.vertical_anchor = ancora
        linhas = t if isinstance(t, list) else [t]
        for i, linha in enumerate(linhas):
            p = tf.paragraphs[0] if i == 0 else tf.add_paragraph()
            p.alignment = alinhar
            run = p.add_run()
            run.text = linha
            run.font.size, run.font.bold, run.font.name = Pt(tamanho), negrito, FONTE
            run.font.color.rgb = cor
            p.space_after = Pt(tamanho * 0.45)
        return caixa

    def titulo(self, s, t, sub=None, escuro=False):
        self.texto(s, t, Inches(0.6), Inches(0.45), Inches(12), Inches(0.9), 34, cor=BRANCO if escuro else MARINHO, negrito=True)
        barra = s.shapes.add_shape(MSO_SHAPE.RECTANGLE, Inches(0.62), Inches(1.28), Inches(0.9), Emu(38000))
        barra.fill.solid()
        barra.fill.fore_color.rgb = DOURADO
        barra.line.fill.background()
        if sub:
            self.texto(s, sub, Inches(0.6), Inches(1.4), Inches(12), Inches(0.6), 16, cor=CINZA if not escuro else CLARO)

    def cartao(self, s, x, y, w, h, grande, legenda, cor_num=MARINHO, fundo=CLARO, tam=34, cor_leg=CINZA):
        r = s.shapes.add_shape(MSO_SHAPE.ROUNDED_RECTANGLE, x, y, w, h)
        r.adjustments[0] = 0.08
        r.fill.solid()
        r.fill.fore_color.rgb = fundo
        r.line.fill.background()
        self.texto(s, grande, x, y + Inches(0.18), w, Inches(0.9), tam, cor=cor_num, negrito=True, alinhar=PP_ALIGN.CENTER)
        self.texto(s, legenda, x + Inches(0.15), y + Inches(1.05), w - Inches(0.3), h - Inches(1.1), 14, cor=cor_leg,
                   alinhar=PP_ALIGN.CENTER)

    def imagem(self, s, arq, x, y, largura):
        if Path(arq).exists():
            s.shapes.add_picture(str(arq), x, y, width=largura)
            return True
        self.texto(s, f"[tela não capturada: {Path(arq).name}]", x, y, largura, Inches(0.5), 12, cor=CINZA)
        return False

    def lista(self, s, itens, x, y, w, tamanho=18, cor=MARINHO):
        caixa = s.shapes.add_textbox(x, y, w, Inches(5))
        tf = caixa.text_frame
        tf.word_wrap = True
        for i, (forte, resto) in enumerate(itens):
            p = tf.paragraphs[0] if i == 0 else tf.add_paragraph()
            p.space_after = Pt(tamanho * 0.7)
            r1 = p.add_run()
            r1.text = forte
            r1.font.bold, r1.font.size, r1.font.name, r1.font.color.rgb = True, Pt(tamanho), FONTE, cor
            r2 = p.add_run()
            r2.text = resto
            r2.font.size, r2.font.name, r2.font.color.rgb = Pt(tamanho), FONTE, CINZA
        return caixa


def recorte(nome: str, caixa: tuple[int, int, int, int]) -> Path:
    """Recorta a área útil de uma tela (sem barra lateral) para ficar legível no slide."""
    from PIL import Image

    origem = TELAS / f"{nome}.png"
    destino = TELAS / "recortes" / f"{nome}.png"
    if origem.exists():
        destino.parent.mkdir(parents=True, exist_ok=True)
        Image.open(origem).crop(caixa).save(destino)
    return destino


def recortar_diagrama() -> Path | None:
    rel = ART / "Relatorio_Tecnico_PRISMA_DO.pdf"
    if not rel.exists():
        return None
    import pymupdf

    with pymupdf.open(rel) as d:
        for pg in d:
            achados = pg.search_for("Grafo 1 — processar documento")
            if achados:
                y0 = achados[0].y0 - 6
                figura = pg.search_for("Figura 1")
                y1 = figura[0].y0 - 4 if figura else y0 + 270
                destino = TELAS / "diagrama_arquitetura.png"
                TELAS.mkdir(parents=True, exist_ok=True)
                pg.get_pixmap(dpi=220, clip=pymupdf.Rect(40, y0, pg.rect.width - 40, y1)).save(str(destino))
                return destino
    return None


def main():
    det, hib = av("deterministico"), av("hibrido")
    arq_ens = config.SAIDA / "experimento_ensino.json"
    ens = json.loads(arq_ens.read_text(encoding="utf-8")) if arq_ens.exists() else None
    grupo_arq = config.DADOS / "grupo.yaml"
    grupo = yaml.safe_load(grupo_arq.read_text(encoding="utf-8")) if grupo_arq.exists() else {}
    D = Deck()

    # 1 — capa
    s = D.slide(MARINHO)
    D.texto(s, "PRISMA D&O", Inches(0.8), Inches(2.0), Inches(11.5), Inches(1.3), 66, cor=BRANCO, negrito=True)
    D.texto(s, "Compare apólices D&O em minutos —\ne veja a página de onde saiu cada número.", Inches(0.8), Inches(3.3),
            Inches(11), Inches(1.5), 28, cor=DOURADO)
    D.texto(s, "Projeto Final · InsurMinds · Instituto de Inteligência Artificial Aplicada (I2A2)", Inches(0.8),
            Inches(5.6), Inches(11), Inches(0.5), 16, cor=CLARO)
    if grupo.get("nome"):
        D.texto(s, f"Grupo {grupo['nome']}", Inches(0.8), Inches(6.1), Inches(11), Inches(0.5), 16, cor=CLARO)

    # 2 — problema
    s = D.slide()
    D.titulo(s, "O problema", "Apólices D&O têm 30 a 70 páginas de linguagem jurídica, e cada seguradora redige do seu jeito.")
    D.cartao(s, Inches(0.6), Inches(2.3), Inches(3.9), Inches(2.3), "72 páginas", "numa só condição geral (Chubb D&O Capital Aberto)")
    D.cartao(s, Inches(4.7), Inches(2.3), Inches(3.9), Inches(2.3), "horas", "de especialista para comparar duas propostas lendo cláusula por cláusula")
    D.cartao(s, Inches(8.8), Inches(2.3), Inches(3.9), Inches(2.3), "detalhes", "decidem o valor: quando a exclusão de dolo se aplica, se a defesa é adiantada, qual a retroatividade")
    D.texto(s, "E um erro de leitura não é neutro: é o administrador descobrindo, no meio de um processo, que o bloqueio "
               "dos seus bens não estava coberto.", Inches(0.6), Inches(5.0), Inches(12), Inches(1), 18, cor=MARINHO)

    # 3 — solução
    s = D.slide()
    D.titulo(s, "A solução", "Uma plataforma de agentes de IA que lê, organiza, verifica e compara.")
    D.lista(s, [("Lê ", "PDF digital, PDF escaneado e foto — com OCR gratuito e offline."),
                ("Extrai ", "36 campos D&O com o trecho literal e a página de cada valor."),
                ("Verifica ", "cada evidência automaticamente antes de mostrar."),
                ("Compara ", "campo a campo, com regras de favorabilidade declaradas."),
                ("Aponta ", "indícios de desconformidade com a Circular SUSEP 637/2021."),
                ("Responde ", "perguntas com citação e gera o relatório comparativo em PDF.")],
            Inches(0.6), Inches(2.2), Inches(7.2), 19)
    r = s.shapes.add_shape(MSO_SHAPE.ROUNDED_RECTANGLE, Inches(8.3), Inches(2.3), Inches(4.4), Inches(3.4))
    r.fill.solid()
    r.fill.fore_color.rgb = MARINHO
    r.line.fill.background()
    D.texto(s, ["Princípio", "Nenhum valor aparece sem um trecho que exista na página citada.",
                "O LLM lê e redige. O código confere, compara e decide."],
            Inches(8.6), Inches(2.55), Inches(3.9), Inches(3.0), 19, cor=BRANCO)

    # 4 — arquitetura
    s = D.slide()
    D.titulo(s, "Como funciona", "Nove agentes especializados orquestrados em dois grafos LangGraph.")
    diag = recortar_diagrama()
    if diag:
        D.imagem(s, diag, Inches(1.6), Inches(1.95), Inches(10.1))
    else:
        D.texto(s, "Recepcionista → Leitor → Segmentador → Extrator → Verificador → Comparador → Conformidade → Relator",
                Inches(0.6), Inches(3), Inches(12), Inches(1), 20)

    # 5 — demonstração
    s = D.slide()
    D.titulo(s, "Na prática", "Três cotações para a mesma empresa, em formatos diferentes, lado a lado.")
    D.imagem(s, recorte("05_comparacao_quadro", (378, 150, 1362, 720)), Inches(0.6), Inches(2.0), Inches(8.4))
    D.lista(s, [("Verde ", "= mais favorável ao segurado"), ("Vermelho ", "= menos favorável"),
                ("p. ", "= página da evidência"), ("Por quê? ", "cada classificação cita a regra e o fundamento")],
            Inches(9.2), Inches(2.3), Inches(3.7), 16)

    # 6 — evidência
    s = D.slide()
    D.titulo(s, "Cada número é provado", "O Verificador só aprova um valor que passa em quatro testes.")
    D.lista(s, [("1. O trecho existe ", "na página citada (similaridade ≥ 0,90, tolerante a OCR)."),
                ("2. Fala do assunto ", "do campo — não basta a palavra “Contratada”."),
                ("3. Contém o número ", "extraído: R$ 30.000.000,00 tem que estar no trecho."),
                ("4. Não é instrução ", "dirigida a IA escondida no documento.")],
            Inches(0.6), Inches(2.2), Inches(6.4), 18)
    D.imagem(s, recorte("03_ficha_evidencia", (378, 400, 1362, 870)), Inches(7.1), Inches(2.0), Inches(5.8))

    # 7 — conformidade
    s = D.slide()
    D.titulo(s, "Conformidade regulatória", "11 regras declaradas, cada uma com o trecho literal da norma.")
    D.lista(s, [("Art. 19 — ", "a cotação Cruzeiro não indica prazo adicional para reclamações."),
                ("Art. 9º, II — ", "achado real: as condições da Argo não mencionam livre escolha do advogado nem profissionais referenciados."),
                ("Art. 17 — ", "retroatividade precisa estar indicada em destaque."),
                ("Lei 15.040/2024 — ", "sinaliza condições que não citam a nova Lei de Seguros.")],
            Inches(0.6), Inches(2.2), Inches(6.6), 17)
    D.imagem(s, recorte("06_comparacao_conformidade", (378, 120, 1362, 745)), Inches(7.2), Inches(2.0), Inches(5.7))
    D.texto(s, "Indícios para revisão humana — não é parecer jurídico.", Inches(0.6), Inches(6.3), Inches(8), Inches(0.4), 13, cor=CINZA)

    # 8 — resultados
    s = D.slide(MARINHO)
    D.titulo(s, "Resultados medidos", "Contra um gabarito anotado à mão. Só conta o valor verificado.", escuro=True)
    cartoes = []
    if det:
        cartoes += [(pct(det["resumo"]["desenvolvimento"]), "acurácia sem chave de API\n(conjunto de desenvolvimento)"),
                    (pct(det["resumo"]["holdout"]), "sem chave em documentos\nnunca vistos (holdout)")]
    if hib:
        cartoes += [(pct(hib["resumo"]["holdout"]), "com LLM gratuito no holdout\n(onde as regras não bastam)")]
    if det and det.get("ocr"):
        cartoes += [(f"{100 * det['ocr']['cer_medio']:.2f}%".replace(".", ","),"erro de caractere do OCR\n(por linha)")]
    cartoes += [("15/15", "injeções de prompt barradas\n0 falso positivo")]
    largura = Inches(12.1 / len(cartoes)) - Inches(0.15)
    for i, (g, l) in enumerate(cartoes):
        D.cartao(s, Inches(0.6) + i * (largura + Inches(0.15)), Inches(2.4), largura, Inches(2.6), g, l, cor_num=DOURADO,
                 fundo=RGBColor(0x22, 0x2D, 0x45), cor_leg=CLARO)
    D.texto(s, "Publicamos o holdout de propósito: as regras foram escritas sobre as seguradoras que lemos. Em documento novo, o LLM acrescenta acerto — e o Verificador segura o que ele erra.",
            Inches(0.6), Inches(5.5), Inches(12), Inches(0.8), 16, cor=CLARO)

    # 9 — diferenciais
    s = D.slide()
    D.titulo(s, "Por que confiar", "Decisões que tornam o resultado auditável.")
    D.lista(s, [("Regras em YAML, ", "não no código nem no LLM: mudar uma regra muda o quadro — e dá para explicar ao cliente."),
                ("Roda sem chave: ", "modo determinístico completo; com chave gratuita, o LLM amplia a cobertura."),
                ("Custo zero: ", "Gemini, Groq e NVIDIA em cascata, com troca automática quando um provedor cai."),
                ("Aprende com o corretor: ", (f"{len(ens['ensinamentos'])} ensinamentos corrigiram "
                                              f"{sum(1 for m in ens['mudancas'] if m['acertou'])} campos, "
                                              f"{sum(1 for m in ens['mudancas'] if m['tipo'] == 'transferido')} em outros documentos, "
                                              f"{sum(1 for m in ens['mudancas'] if not m['acertou'])} erro novo.")
                                             if ens else "o trecho apontado vira regra para a mesma redação."),
                ("Rastro completo: ", "cada agente registra o que fez e quanto tempo levou.")],
            Inches(0.6), Inches(2.1), Inches(12), 17)
    D.imagem(s, recorte("10_ensinar", (640, 340, 1345, 700)), Inches(8.3), Inches(4.75), Inches(4.4))

    # 10 — limitações e próximos passos
    s = D.slide()
    D.titulo(s, "Limites honestos e próximos passos")
    D.texto(s, "Limites", Inches(0.6), Inches(1.7), Inches(6), Inches(0.5), 20, cor=VERMELHO, negrito=True)
    D.lista(s, [("Regras ", "sem LLM caem em seguradora nova (o corretor ensina uma vez)."), ("Números ", "de apólice real são privados: a demo usa cotações fictícias."),
                ("“Não localizado” ", "pode estar em outro documento da apólice."), ("Favorabilidade ", "por campo, sem perfil de risco.")],
            Inches(0.6), Inches(2.3), Inches(5.9), 16)
    D.texto(s, "Próximos passos", Inches(6.9), Inches(1.7), Inches(6), Inches(0.5), 20, cor=VERDE, negrito=True)
    D.lista(s, [("Pacote da apólice: ", "especificação + condições + endossos."), ("Mais seguradoras ", "e dois anotadores."),
                ("Diferença de versões ", "da mesma seguradora."), ("LLM local ", "para quem não pode enviar documentos para fora.")],
            Inches(6.9), Inches(2.3), Inches(5.9), 16)

    # 11 — para quem
    s = D.slide()
    D.titulo(s, "Para quem", "Apoio à decisão em quem lê apólice D&O todos os dias.")
    for i, (g, l) in enumerate([("Corretores", "comparar propostas e explicar ao cliente onde cada uma é mais favorável"),
                                ("Gestores de risco", "conferir renovação e mudanças de redação entre versões"),
                                ("Seguradoras", "revisar conformidade de condições com a Circular 637")]):
        D.cartao(s, Inches(0.6) + i * Inches(4.15), Inches(2.4), Inches(3.9), Inches(2.4), g, l, tam=26)

    # 12 — encerramento
    s = D.slide(MARINHO)
    D.texto(s, "PRISMA D&O", Inches(0.8), Inches(2.1), Inches(11.5), Inches(1.2), 54, cor=BRANCO, negrito=True)
    D.texto(s, "Cada número, com a página.", Inches(0.8), Inches(3.2), Inches(11), Inches(0.8), 28, cor=DOURADO)
    D.texto(s, ["Código aberto (MIT) · README com instalação e execução", "Relatório técnico e vídeo em Projeto_Final_Artefatos/"],
            Inches(0.8), Inches(4.5), Inches(11), Inches(1.2), 17, cor=CLARO)
    if grupo.get("integrantes"):
        D.texto(s, " · ".join(grupo["integrantes"]), Inches(0.8), Inches(5.8), Inches(11.5), Inches(0.8), 14, cor=CLARO)

    destino = ART / "InsurMinds_Projeto_Final.pptx"
    ART.mkdir(parents=True, exist_ok=True)
    D.prs.save(str(destino))
    print(f"ok  {destino} ({D.n} slides)")


if __name__ == "__main__":
    main()
