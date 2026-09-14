# -*- coding: utf-8 -*-
"""Interface do PRISMA D&O (Streamlit).

    streamlit run streamlit_app.py

Tudo que vem de documento ou de LLM é tratado como texto não confiável: escapado antes de ir para
a tela (markdown escapado em `seguro`, HTML escapado em `h`). O HTML próprio da interface é estático.
"""
from __future__ import annotations

import html
import json
import re
import time
from urllib.parse import urlparse

import pandas as pd
import streamlit as st

from prisma import config, corpus, grafo, llm
from prisma.agentes import consultor, recepcionista
from prisma.armazem import Armazem
from prisma.modelos import Favorabilidade, StatusEvidencia, carregar_esquema

st.set_page_config(page_title="PRISMA D&O", page_icon="🔎", layout="wide")

CORES = {"mais_favoravel": "#dcf1e1", "menos_favoravel": "#f9dedb", "intermediaria": "#fcf0d2",
         "equivalente": "#e8eef7", "nao_comparavel": "#ffffff"}
TINTA = {"mais_favoravel": "#1d6b3c", "menos_favoravel": "#9b2f24", "intermediaria": "#7a5a12",
         "equivalente": "#34507a", "nao_comparavel": "#1f2a44"}
SIMBOLO_FAV = {"mais_favoravel": "▲", "menos_favoravel": "▼", "intermediaria": "◆", "equivalente": "=", "nao_comparavel": ""}
CURTO = {"basica": "básica", "adicional": "adicional (contratável)", "contratada": "contratada",
         "nao_contratada": "não contratada", "excluida": "excluída", "nao_prevista": "não prevista",
         "excluido": "excluído", "excluido_com_ressalva": "excluído com ressalva", "exclusao_opcional": "exclusão opcional",
         "nao_excluido": "não excluído", "reclamacao": "reclamações (sem notificação)",
         "reclamacao_com_notificacao": "reclamações com notificação", "primeira_manifestacao": "primeira manifestação",
         "ocorrencia": "ocorrência", "adiantamento": "adiantamento", "reembolso": "só reembolso",
         "sem_reintegracao": "sem reintegração", "com_reintegracao": "com reintegração",
         "dentro_do_limite": "dentro do limite", "adicional_ao_limite": "além do limite",
         "decisao_final": "só após decisão final", "decisao_nao_definitiva": "antes da decisão final",
         "sem_gatilho": "sem gatilho definido", "mundial": "mundial", "mundial_exceto_eua_canada": "mundial exceto EUA/Canadá",
         "brasil": "Brasil", "renuncia_salvo_dolo": "renuncia (salvo dolo)", "sem_renuncia": "sem renúncia"}
ROTULO_STATUS = {"verificado": "✅ conferido", "nao_verificado": "⛔ descartado", "nao_localizado": "— não encontrado",
                 "definido_na_especificacao": "📄 fica na especificação"}

CSS = """
<style>
:root { --marinho:#141c2e; --marinho2:#22304f; --dourado:#d8b877; --tinta:#1f2a44; --cinza:#5b6477; --claro:#f2f5fa; }
[data-testid="stMainBlockContainer"] { padding-top: 1.6rem; max-width: 1280px; }
[data-testid="stSidebar"] { background: var(--marinho); }
[data-testid="stSidebar"] * { color: #e9edf5; }
[data-testid="stSidebar"] .stButton button { background: var(--dourado); color: var(--marinho); border: 0; font-weight: 600; }
[data-testid="stSidebar"] .stButton button * { color: var(--marinho); }
[data-testid="stSidebar"] [data-testid="stAlert"] { background: rgba(255,255,255,.07); }
.marca { font-size: 1.55rem; font-weight: 700; letter-spacing: .5px; margin: 0 0 .2rem 0; }
.marca span { color: var(--dourado) !important; }
.lema { font-size: .86rem; opacity: .8; margin-bottom: 1rem; }
.passos-lat { margin: .4rem 0 0 0; padding: 0; list-style: none; }
.passos-lat li { margin: .45rem 0; font-size: .88rem; }
.passos-lat b { display: inline-block; width: 1.4rem; height: 1.4rem; border-radius: 50%; text-align: center;
                line-height: 1.4rem; background: var(--dourado); color: var(--marinho) !important; margin-right: .45rem; font-size: .78rem; }
.heroi { background: linear-gradient(120deg, var(--marinho) 0%, var(--marinho2) 100%); border-radius: 14px;
         padding: 1.1rem 1.5rem; color: #fff; margin-bottom: .6rem; }
.heroi h1 { font-size: 1.45rem; margin: 0; padding: 0; color: #fff; font-weight: 650; }
.heroi h1 em { color: var(--dourado); font-style: normal; }
.heroi p { margin: .25rem 0 .8rem 0; color: #cfd6e4; font-size: .93rem; }
.trilha { display: flex; gap: .6rem; flex-wrap: wrap; }
.trilha div { flex: 1 1 200px; background: rgba(255,255,255,.08); border: 1px solid rgba(216,184,119,.35);
              border-radius: 10px; padding: .5rem .75rem; font-size: .85rem; color: #e9edf5; }
.trilha b { color: var(--dourado); margin-right: .3rem; }
.stTabs [data-baseweb="tab-list"] { gap: .3rem; }
.stTabs [data-baseweb="tab"] { font-weight: 600; padding: .4rem .8rem; }
[data-testid="stMetric"] { background: var(--claro); border-radius: 10px; padding: .6rem .9rem; }
[data-testid="stMetricValue"] { font-size: 1.7rem; }
.dica { background: #eef4ec; border-left: 4px solid #2e7d4f; padding: .55rem .9rem; border-radius: 6px; font-size: .9rem; margin: .5rem 0; }
.nota { background: var(--claro); border-left: 4px solid var(--dourado); padding: .55rem .9rem; border-radius: 6px; font-size: .9rem; margin: .5rem 0; }
.legenda { display: flex; gap: .5rem; flex-wrap: wrap; margin: .4rem 0 .6rem 0; font-size: .82rem; }
.legenda span { padding: .15rem .55rem; border-radius: 20px; border: 1px solid #dde3ec; }
.quadro-wrap { overflow-x: auto; border: 1px solid #dde3ec; border-radius: 10px; max-height: 720px; overflow-y: auto; }
table.quadro { border-collapse: collapse; width: 100%; font-size: .86rem; }
table.quadro th { position: sticky; top: 0; background: var(--marinho); color: #fff; text-align: left; padding: .55rem .6rem;
                  font-weight: 600; z-index: 2; }
table.quadro td { padding: .45rem .6rem; border-top: 1px solid #e6ebf2; vertical-align: top; }
table.quadro td.campo { font-weight: 600; color: var(--tinta); background: #fafbfd; min-width: 220px; position: sticky; left: 0; z-index: 1; }
table.quadro td .pg { color: var(--cinza); font-size: .75rem; margin-left: .25rem; white-space: nowrap; }
[data-testid="stFileUploaderDropzone"] button [data-testid="stMarkdownContainer"] { display: none; }
[data-testid="stFileUploaderDropzone"] button [data-has-shortcut]::after { content: "Escolher arquivos"; font-size: .9rem; margin-left: .4rem; }
[data-testid="stFileUploaderDropzoneInstructions"] span, [data-testid="stFileUploaderDropzoneInstructions"] small { display: none; }
[data-testid="stFileUploaderDropzoneInstructions"] > div::after { content: "ou arraste para cá · PDF, PNG ou JPG · até 25 MB cada"; font-size: .88rem; color: var(--cinza); }
</style>
"""


def h(texto) -> str:
    """Escapa HTML para exibir texto não confiável dentro do HTML próprio da interface."""
    return html.escape(str(texto or ""), quote=True)


def seguro(texto) -> str:
    """Escapa markdown para exibir texto não confiável literalmente."""
    return re.sub(r"([\\`*_{}\[\]()#+\-.!|<>~$])", r"\\\1", str(texto or ""))


def texto_curto(v) -> str:
    return CURTO.get(str(v.valor), v.valor_texto) if isinstance(v.valor, str) else v.valor_texto


def modo_legivel(modo: str) -> str:
    """'deterministico (LLM indisponível)' → 'regras declaradas (IA indisponível)'; 'llm:gemini' → 'IA gratuita (gemini)'."""
    modo = str(modo or "").replace(" (cache)", "")
    base, _, extra = modo.partition(" (")
    extra = f" ({extra}" if extra else ""
    extra = extra.replace("LLM", "IA").replace("deterministico", "regras")
    if base.startswith("llm"):
        prov = base.split(":", 1)[1] if ":" in base else ""
        return f"IA gratuita{f' · {prov}' if prov else ''}, com números conferidos{extra}"
    if base == "hibrido":
        return "regras declaradas + IA gratuita"
    return f"regras declaradas{extra}"


def html_bloco(conteudo: str) -> None:
    st.markdown(re.sub(r"\n\s*", "", conteudo), unsafe_allow_html=True)


@st.cache_resource
def armazem() -> Armazem:
    return Armazem()


@st.cache_resource
def cascata_llm():
    config.carregar_env()
    c = llm.obter()
    if c is not None:
        c.orcamento_s = 30  # na tela, 30 s por pergunta; passou disso, modo determinístico
    return c


def cascata_ativa():
    return cascata_llm() if st.session_state.get("usar_llm", True) else None


def pagina_png(doc, numero: int, trecho: str | None = None) -> bytes | None:
    import pymupdf

    conteudo = armazem().arquivo(doc)
    if conteudo is None:
        return None
    if doc.tipo_arquivo in ("png", "jpg"):
        return conteudo
    with pymupdf.open(stream=conteudo, filetype="pdf") as d:
        pg = d[max(0, min(numero - 1, d.page_count - 1))]
        if trecho and doc.paginas[numero - 1].metodo == "nativo":
            # destaca o trecho: procura pedaços de ~8 palavras (o PDF quebra linhas no meio da frase)
            palavras = re.sub(r"\s+", " ", trecho).split(" ")
            for i in range(0, len(palavras), 8):
                pedaco = " ".join(palavras[i:i + 8]).strip()
                if len(pedaco) > 12:
                    for r in pg.search_for(pedaco)[:3]:
                        pg.add_highlight_annot(r)
        return pg.get_pixmap(dpi=110).tobytes("png")


st.markdown(CSS, unsafe_allow_html=True)

# ============================================================================ barra lateral
with st.sidebar:
    html_bloco("""<div class="marca">🔎 PRISMA <span>D&amp;O</span></div>
        <div class="lema">Análise e comparação de apólices D&amp;O com evidência verificada</div>""")
    c = cascata_llm()
    st.toggle("Usar IA gratuita", value=c is not None, key="usar_llm", disabled=c is None,
              help="Com a IA ligada, modelos gratuitos ajudam a ler cláusulas difíceis. Desligada (ou sem chave de API), "
                   "o sistema usa só regras declaradas. Nos dois casos, todo valor passa pelo Verificador.")
    if c is None:
        st.info("Sem chave de API: leitura só por regras declaradas. O README explica como ligar a IA gratuita.")
    elif st.session_state.get("usar_llm"):
        st.caption(f"Ordem de uso: {c.descricao}")
    st.divider()
    html_bloco("""<div style="font-weight:600;font-size:.9rem">Como usar</div>
        <ul class="passos-lat">
        <li><b>1</b>Envie as apólices em <i>Documentos</i></li>
        <li><b>2</b>Confira os valores em <i>Ficha</i></li>
        <li><b>3</b>Compare e baixe o PDF em <i>Comparar</i></li>
        </ul>""")
    st.write("")
    if st.button("Carregar exemplos prontos", use_container_width=True,
                 help="Baixa condições gerais públicas de seguradoras (sites oficiais) e processa as cotações fictícias."):
        with st.status("Preparando exemplos…", expanded=True) as s:
            if not all((config.REAIS / d["arquivo"]).exists() for d in corpus.fontes()["documentos"]):
                s.write("Baixando condições gerais públicas (hash conferido)…")
                corpus.baixar(avisar=lambda m: s.write(m))
            for arq in corpus.arquivos_demo():
                s.write(f"Processando {arq.name}…")
                grafo.processar(arq.name, arq.read_bytes(), armazem(), None,
                                progresso=lambda ag, msg: None)
            s.update(label="Exemplos prontos", state="complete")
    st.divider()
    st.caption("Apoio à decisão — não é recomendação de contratação nem parecer jurídico.")

html_bloco("""<div class="heroi">
    <h1>Compare apólices D&amp;O <em>e veja a página de onde saiu cada número</em></h1>
    <p>Envie PDFs, digitalizações ou fotos. Nove agentes de IA leem, extraem 36 campos, comparam e conferem a norma SUSEP.</p>
    <div class="trilha">
      <div><b>1</b>Envie as apólices</div>
      <div><b>2</b>Confira a ficha e as evidências</div>
      <div><b>3</b>Compare e baixe o relatório</div>
    </div></div>""")

tab_docs, tab_ficha, tab_comp, tab_perg, tab_rastro, tab_aval = st.tabs(
    ["1 · Documentos", "2 · Ficha", "3 · Comparar", "💬 Pergunte", "🧭 Como funciona", "📏 Qualidade"])


def tipo_documento(d: dict) -> str:
    return "Cotação (especificação)" if d["ficticio"] or d["nome"].startswith("especificacao") else "Condição geral"


def origem_legivel(d: dict) -> str:
    url = d["metadados"].get("url")
    if url:
        return "site " + urlparse(url).netloc.removeprefix("www.")
    return "exemplo fictício" if d["ficticio"] else "enviado por você"


# ============================================================================ documentos
with tab_docs:
    st.subheader("Enviar apólices")
    st.caption(f"PDF com texto ou escaneado, PNG ou JPG · até {config.TAMANHO_MAXIMO_BYTES // 2**20} MB e "
               f"{config.PAGINAS_MAXIMAS} páginas por arquivo. Páginas sem texto são lidas por OCR automaticamente.")
    enviados = st.file_uploader("Arquivos", type=["pdf", "png", "jpg", "jpeg"], accept_multiple_files=True,
                                label_visibility="collapsed")
    if enviados and st.button(f"Processar {len(enviados)} arquivo(s)", type="primary"):
        ok = 0
        for arq in enviados:
            with st.status(f"{arq.name}", expanded=True) as s:
                t0 = time.time()
                try:
                    estado = grafo.processar(arq.name, arq.getvalue(), armazem(), cascata_ativa(),
                                             progresso=lambda ag, msg: s.write(f"**{ag.capitalize()}** · {seguro(msg)}"))
                    s.update(label=f"{seguro(estado['documento'].rotulo)} · pronto em {time.time() - t0:.0f} s",
                             state="complete", expanded=False)
                    ok += 1
                except recepcionista.DocumentoRecusado as erro:
                    s.update(label=f"{arq.name}: recusado", state="error")
                    st.error(str(erro))
                except Exception:
                    s.update(label=f"{arq.name}: falhou", state="error")
                    st.error("Não foi possível processar este arquivo. Detalhes no log do servidor.")
        if ok:
            html_bloco('<div class="dica">✔ Pronto. Próximo passo: abra a aba <b>2 · Ficha</b> para conferir os valores '
                       'ou vá direto para <b>3 · Comparar</b>.</div>')
    docs = armazem().documentos()
    st.subheader(f"Documentos processados ({len(docs)})")
    if docs:
        tabela = pd.DataFrame([{
            "Seguradora": armazem().documento(d["id"]).rotulo if d["ficticio"] else (d["metadados"].get("seguradora") or d["nome"]),
            "Tipo": tipo_documento(d), "Arquivo": d["nome"], "Páginas": d["paginas"],
            "Lidas por OCR": d["paginas_ocr"], "Origem": origem_legivel(d),
        } for d in docs])
        st.dataframe(tabela, hide_index=True, use_container_width=True)
        st.caption("Condição geral é o contrato-modelo da seguradora (coberturas e exclusões). Cotação/especificação traz "
                   "os números do cliente: limite, franquia, prêmio e datas.")
    else:
        st.info("Nenhum documento ainda. Envie arquivos acima ou clique em “Carregar exemplos prontos” na barra lateral.")


def seletor_documentos(chave: str, multiplo: bool, rotulo: str):
    docs = armazem().documentos()
    opcoes = {d["id"]: armazem().documento(d["id"]).rotulo for d in docs}
    if not opcoes:
        st.info("Nenhum documento processado ainda: comece pela aba 1 · Documentos.")
        return [] if multiplo else None
    ficticios = [d["id"] for d in docs if d["ficticio"]]
    if multiplo:
        inicial = ficticios[:3] if len(ficticios) >= 2 else list(opcoes)[:2]
        return st.multiselect(rotulo, list(opcoes), default=inicial,
                              format_func=lambda i: opcoes[i], key=chave, max_selections=4)
    ordem = ficticios + [i for i in opcoes if i not in ficticios]  # abre numa cotação: é onde há números
    return st.selectbox(rotulo, ordem, format_func=lambda i: opcoes[i], key=chave)


def mostrar_evidencia(doc, v, chave: str):
    origem = "regras declaradas" if v.metodo == "deterministico" else modo_legivel(v.metodo).split(",")[0]
    st.markdown(f"**Página {v.evidencia.pagina}** · trecho confere {100 * v.evidencia.similaridade:.0f}% com o "
                f"documento · lido por {seguro(origem)}")
    st.text(v.evidencia.trecho)
    if v.observacao:
        st.caption(seguro(v.observacao))
    if st.toggle("Ver página original", key=chave):
        img = pagina_png(doc, v.evidencia.pagina, v.evidencia.trecho)
        if img:
            st.image(img, caption=f"{doc.rotulo} — página {v.evidencia.pagina} (trecho destacado quando o PDF tem texto)")


# ============================================================================ ficha
with tab_ficha:
    doc_id = seletor_documentos("ficha_doc", multiplo=False, rotulo="Documento")
    if doc_id:
        doc = armazem().documento(doc_id)
        ficha = armazem().ficha(doc_id)
        if doc.ficticio:
            st.warning("DOCUMENTO FICTÍCIO — demonstração acadêmica; valores e seguradora inventados.")
        if ficha is None:
            st.info("Documento sem ficha: processe-o novamente.")
        else:
            cont = {s.value: 0 for s in StatusEvidencia}
            for v in ficha.valores.values():
                cont[v.status.value] += 1
            a, b, c_, d_ = st.columns(4)
            a.metric("Valores conferidos", cont["verificado"], help="Trecho encontrado na página, sobre o assunto certo e com o número.")
            b.metric("Descartados pelo verificador", cont["nao_verificado"],
                     help="A leitura propôs um valor, mas o trecho não comprovou. Nada é exibido sem prova.")
            c_.metric("Não encontrados", cont["nao_localizado"])
            d_.metric("Leitura feita por", "regras + IA" if ficha.modo == "hibrido" else "regras")
            if cont["definido_na_especificacao"]:
                html_bloco('<div class="nota">📄 Este é um <b>contrato-modelo</b> (condição geral). Limite, franquia, prêmio e '
                           'datas ficam na <b>especificação</b> de cada cliente — por isso aparecem como “fica na especificação”.</div>')
            st.caption("✅ conferido: valor com trecho e página · ⛔ descartado: sem prova, não exibido · "
                       "— não encontrado: o documento não trata do assunto")
            esq = carregar_esquema()
            for grupo_id, grupo_nome in esq.grupos.items():
                with st.expander(grupo_nome, expanded=grupo_id in ("limites", "coberturas")):
                    for campo in [x for x in esq.campos if x.grupo == grupo_id]:
                        v = ficha.valores.get(campo.id)
                        if v is None:
                            continue
                        col1, col2, col3, col4 = st.columns([3, 3, 2, 1.3], vertical_alignment="center")
                        col1.markdown(f"**{seguro(campo.rotulo)}**")
                        col2.markdown(seguro(texto_curto(v)) if v.exibivel else "—")
                        col3.markdown(ROTULO_STATUS[v.status.value])
                        if v.exibivel and v.evidencia:
                            with col4.popover("Evidência", use_container_width=True):
                                mostrar_evidencia(doc, v, f"pg_{doc_id}_{campo.id}")
                        elif v.status == StatusEvidencia.NAO_VERIFICADO:
                            col4.caption("sem prova")

# ============================================================================ comparar
with tab_comp:
    ids = seletor_documentos("comp_docs", multiplo=True, rotulo="Apólices para comparar (de 2 a 4)")
    col_a, col_b = st.columns([1, 3], vertical_alignment="center")
    so_diferencas = col_b.toggle("Mostrar só o que muda entre elas", value=True)
    if len(ids) >= 2 and col_a.button("Comparar", type="primary", use_container_width=True):
        with st.spinner("Comparador, Conformidade e Relator trabalhando…"):
            try:
                st.session_state["comparacao"] = grafo.comparar(ids, armazem(), cascata_ativa())
            except ValueError as erro:
                st.error(str(erro))
    estado = st.session_state.get("comparacao")
    if len(ids) < 2:
        st.caption("Escolha pelo menos duas apólices.")
    elif not (estado and estado["comparacao"].doc_ids == ids):
        st.caption("Clique em Comparar para montar o quadro.")
    if estado and estado["comparacao"].doc_ids == ids:
        comp, docs = estado["comparacao"], estado["documentos"]
        if any(d.ficticio for d in docs):
            st.warning("A comparação inclui DOCUMENTO FICTÍCIO (demonstração acadêmica).")
        st.subheader("Resumo")
        st.caption(f"Escrito por {seguro(modo_legivel(comp.modo_resumo))}")
        st.markdown("\n".join(seguro(l).replace("\\- ", "- ", 1) for l in comp.resumo.splitlines()))
        st.download_button("⬇️ Baixar relatório comparativo (PDF)", estado["pdf"], file_name="PRISMA_DO_comparativo.pdf",
                           mime="application/pdf")
        st.subheader("Quadro comparativo")
        linhas_html = []
        for l in comp.linhas:
            if so_diferencas and not l.diferente:
                continue
            celulas = [f'<td class="campo">{h(l.rotulo)}</td>']
            for d in docs:
                v = l.valores.get(d.id)
                fav = l.classificacao.get(d.id, Favorabilidade.NAO_COMPARAVEL).value
                if v and v.status == StatusEvidencia.VERIFICADO:
                    texto = f'{h(texto_curto(v))}<span class="pg">p.{v.evidencia.pagina}</span>'
                elif v and v.status == StatusEvidencia.NA_ESPECIFICACAO:
                    texto = '<span class="pg">fica na especificação</span>'
                else:
                    texto = '<span class="pg">não encontrado</span>'
                simbolo = SIMBOLO_FAV[fav]
                celulas.append(f'<td style="background:{CORES[fav]};color:{TINTA[fav]}">'
                               f'{simbolo + " " if simbolo else ""}{texto}</td>')
            linhas_html.append("<tr>" + "".join(celulas) + "</tr>")
        if linhas_html:
            html_bloco(f"""<div class="legenda">
                <span style="background:{CORES['mais_favoravel']};color:{TINTA['mais_favoravel']}">▲ mais favorável ao segurado</span>
                <span style="background:{CORES['intermediaria']};color:{TINTA['intermediaria']}">◆ intermediária</span>
                <span style="background:{CORES['menos_favoravel']};color:{TINTA['menos_favoravel']}">▼ menos favorável</span>
                <span style="background:{CORES['equivalente']};color:{TINTA['equivalente']}">= equivalente</span>
                <span>p. = página da evidência</span><span>sem cor = informativo</span></div>""")
            cabecalho = "<th>Campo</th>" + "".join(f"<th>{h(d.rotulo)}</th>" for d in docs)
            html_bloco(f'<div class="quadro-wrap"><table class="quadro"><thead><tr>{cabecalho}</tr></thead>'
                       f'<tbody>{"".join(linhas_html)}</tbody></table></div>')
        else:
            st.info("As apólices escolhidas não diferem em nenhum campo.")
        st.subheader("Por que essa classificação?")
        # primeiro os campos com juízo de favorabilidade; os informativos (seguradora, processo…) por último
        campos_dif = sorted([l for l in comp.linhas if l.diferente],
                            key=lambda l: all(f == Favorabilidade.NAO_COMPARAVEL for f in l.classificacao.values()))
        esq = carregar_esquema()
        escolhido = st.selectbox("Escolha um campo para ver o critério e os trechos de cada apólice",
                                 [l.campo_id for l in campos_dif],
                                 format_func=lambda cid: esq.campo(cid).rotulo) if campos_dif else None
        if escolhido:
            l = next(x for x in comp.linhas if x.campo_id == escolhido)
            html_bloco(f'<div class="nota"><b>Critério:</b> {h(l.motivo) or "campo informativo, sem juízo de favorabilidade"}'
                       f'<span class="pg" style="color:#5b6477;font-size:.75rem"> · regra {h(l.regra_id or "—")}</span></div>')
            cols = st.columns(len(docs))
            for col, d in zip(cols, docs):
                with col:
                    st.markdown(f"**{seguro(d.rotulo)}**")
                    v = l.valores.get(d.id)
                    if v and v.status == StatusEvidencia.VERIFICADO:
                        mostrar_evidencia(d, v, f"cmp_{d.id}_{escolhido}")
                    else:
                        st.caption("sem valor conferido")
        st.subheader("Pontos de atenção — Circular SUSEP 637")
        st.caption("Indícios para revisão humana, não parecer jurídico.")
        if not comp.alertas:
            st.success("Nenhum ponto de atenção pelas regras declaradas.")
        por_id = {d.id: d for d in docs}
        for a in comp.alertas:
            caixa = st.warning if a.severidade == "atencao" else st.info
            caixa(f"**{seguro(por_id[a.doc_id].rotulo)} · {seguro(a.artigo)}** — {seguro(a.mensagem)}")
            with st.expander("O que diz a norma e onde está no documento"):
                st.text(a.fundamento)
                if a.evidencia:
                    st.text(f"pág. {a.evidencia.pagina}: {a.evidencia.trecho}")

# ============================================================================ pergunte
with tab_perg:
    st.caption("Pergunte em português. A resposta só aparece com citação que existe de verdade no documento.")
    ids_p = seletor_documentos("perg_docs", multiplo=True, rotulo="Em quais documentos procurar")
    pergunta = st.text_input("Pergunta", placeholder="Ex.: A apólice cobre multas aplicadas pela CVM?", max_chars=500)
    if pergunta and ids_p and st.button("Perguntar", type="primary"):
        docs_p = [armazem().documento(i) for i in ids_p]
        with st.spinner("Buscando trechos e conferindo citações…"):
            r = consultor.perguntar(pergunta, docs_p, armazem(), cascata_ativa())
        st.markdown(seguro(r.texto))
        st.caption(f"Respondido por {seguro(modo_legivel(r.modo))}" +
                   (f" · {r.descartadas} citação(ões) descartada(s) por não existirem no documento" if r.descartadas else ""))
        por_id = {d.id: d for d in docs_p}
        for i, cit in enumerate(r.citacoes):
            with st.expander(f"{cit['rotulo']} — página {cit['pagina']}"):
                st.text(cit["trecho"])
                if st.toggle("Ver página", key=f"perg_pg_{i}"):
                    img = pagina_png(por_id[cit["doc_id"]], cit["pagina"], cit["trecho"])
                    if img:
                        st.image(img)

# ============================================================================ como funciona
with tab_rastro:
    st.subheader("Nove agentes em dois fluxos")
    st.caption("Cada documento passa pelo fluxo 1 uma vez; a comparação usa as fichas salvas (fluxo 2). "
               "O Verificador barra qualquer valor sem trecho, página e número que o comprovem.")
    st.graphviz_chart("""digraph {
      rankdir=LR; bgcolor="transparent";
      node [shape=box, style="rounded,filled", fillcolor="#eef2f8", color="#c9d3e3", fontname="Helvetica", fontsize=11];
      edge [color="#5b6477"];
      subgraph cluster_1 { label="Fluxo 1 — ler cada documento"; style=dashed; color="#d8b877"; fontname="Helvetica";
        R [label="Recepcionista\\ntipo, tamanho, SHA-256"]; L [label="Leitor\\ntexto nativo + OCR por página"];
        S [label="Segmentador\\ncláusulas com página"]; E [label="Extrator\\nregras + IA gratuita"];
        V [label="Verificador\\ntrecho, assunto, número, injeção", fillcolor="#141c2e", fontcolor="white"]; R->L->S->E->V; }
      DB [label="SQLite\\nfichas + rastro", shape=cylinder, fillcolor="#fcf0d2"];
      subgraph cluster_2 { label="Fluxo 2 — comparar"; style=dashed; color="#d8b877"; fontname="Helvetica";
        C [label="Comparador\\nregras de favorabilidade"]; F [label="Conformidade\\nCircular SUSEP 637"];
        RE [label="Relator\\nresumo ancorado + PDF"]; C->F->RE; }
      Q [label="Consultor\\nperguntas com citação"];
      V->DB; DB->C; DB->Q; }""")
    st.subheader("O que cada agente fez (últimos passos)")
    passos = armazem().rastro(limite=60)
    if passos:
        nomes = {d["id"]: d["nome"] for d in armazem().documentos()}
        st.dataframe(pd.DataFrame([{"Execução": p["execucao"], "Agente": p["agente"].replace("_", " ").capitalize(),
                                    "Documento": nomes.get(p["doc_id"], p["doc_id"]) if p["doc_id"] else "(comparação)",
                                    "Duração (s)": p["duracao_s"],
                                    "Detalhe": json.dumps(p["detalhe"], ensure_ascii=False)[:160]} for p in passos]),
                     hide_index=True, use_container_width=True)

# ============================================================================ qualidade
with tab_aval:
    st.subheader("Quanto o sistema acerta")
    st.caption("Medido contra um gabarito anotado à mão (281 campos). “Nunca vistos” são documentos separados antes do "
               "desenvolvimento e usados só na medição final.")
    achou = False
    for modo, titulo in (("deterministico", "Só regras declaradas (sem chave de API)"), ("hibrido", "Regras + IA gratuita")):
        arq = config.SAIDA / f"avaliacao_{modo}.json"
        if not arq.exists():
            continue
        achou = True
        dados = json.loads(arq.read_text(encoding="utf-8"))
        st.markdown(f"#### {titulo}")
        cols = st.columns(4)
        for col, chave, nome in zip(cols, ("desenvolvimento", "holdout", "especificacoes", "condicoes_gerais"),
                                    ("Desenvolvimento", "Nunca vistos (holdout)", "Cotações", "Condições gerais")):
            t = dados["resumo"][chave]
            if t["campos"]:
                col.metric(nome, f"{100 * t['acuracia']:.1f}%".replace(".", ","), f"{t['acertos']} de {t['campos']} campos",
                           delta_color="off", delta_arrow="off")
                col.caption(f"valores errados mostrados na tela: {t['valores_errados_exibidos']}")
        if dados.get("ocr"):
            st.caption(f"OCR — erro por caractere: médio {100 * dados['ocr']['cer_medio']:.2f}% · "
                       f"máximo {100 * dados['ocr']['cer_maximo']:.2f}%".replace(".", ","))
    if achou:
        with st.expander("Como reproduzir"):
            st.code("python -m prisma.cli avaliar --modo deterministico --ocr\npython -m prisma.cli avaliar --modo hibrido",
                    language="bash")
    else:
        st.info("Rode a avaliação pela linha de comando para ver as métricas aqui.")
