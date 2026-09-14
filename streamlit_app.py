# -*- coding: utf-8 -*-
"""Interface do PRISMA D&O (Streamlit).

    streamlit run streamlit_app.py

Tudo que vem de documento ou de LLM é tratado como texto não confiável: escapado antes de ir para
a tela (sem HTML, sem link markdown).
"""
from __future__ import annotations

import json
import re
import time

import pandas as pd
import streamlit as st

from prisma import config, corpus, grafo, llm
from prisma.agentes import consultor, recepcionista
from prisma.armazem import Armazem
from prisma.modelos import Favorabilidade, StatusEvidencia, carregar_esquema

st.set_page_config(page_title="PRISMA D&O", page_icon="🔎", layout="wide")

CORES = {"mais_favoravel": "#d8f0dc", "menos_favoravel": "#f8d9d6", "intermediaria": "#fdf1d0",
         "equivalente": "#e8eef7", "nao_comparavel": "#ffffff"}
ROTULO_FAV = {"mais_favoravel": "▲ mais favorável", "menos_favoravel": "▼ menos favorável",
              "intermediaria": "◆ intermediária", "equivalente": "= equivalente", "nao_comparavel": ""}
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


def texto_curto(v) -> str:
    return CURTO.get(str(v.valor), v.valor_texto) if isinstance(v.valor, str) else v.valor_texto
ROTULO_STATUS = {"verificado": "✅ verificado", "nao_verificado": "⚠️ reprovado", "nao_localizado": "— não localizado",
                 "definido_na_especificacao": "📄 na especificação"}


def seguro(texto) -> str:
    """Escapa markdown para exibir texto não confiável literalmente."""
    return re.sub(r"([\\`*_{}\[\]()#+\-.!|<>~$])", r"\\\1", str(texto or ""))


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


# ============================================================================ barra lateral
with st.sidebar:
    st.title("🔎 PRISMA D&O")
    st.caption("Análise e comparação de apólices D&O com evidência verificada")
    c = cascata_llm()
    st.toggle("Usar LLM gratuito", value=c is not None, key="usar_llm", disabled=c is None,
              help="Sem chave, o sistema roda com regras declaradas (modo determinístico).")
    if c is None:
        st.info("Sem chave de API: modo determinístico (regras declaradas). Veja o README para ativar o LLM gratuito.")
    elif st.session_state.get("usar_llm"):
        st.success(f"Cascata: {c.descricao}")
    st.divider()
    if st.button("Carregar corpus de demonstração", use_container_width=True):
        with st.status("Preparando demonstração…", expanded=True) as s:
            if not all((config.REAIS / d["arquivo"]).exists() for d in corpus.fontes()["documentos"]):
                s.write("Baixando condições gerais públicas (hash conferido)…")
                corpus.baixar(avisar=lambda m: s.write(m))
            for arq in corpus.arquivos_demo():
                s.write(f"Processando {arq.name}…")
                grafo.processar(arq.name, arq.read_bytes(), armazem(), None,
                                progresso=lambda ag, msg: None)
            s.update(label="Demonstração pronta", state="complete")
    st.caption("Apoio à decisão — não é recomendação de contratação.")

tab_docs, tab_ficha, tab_comp, tab_perg, tab_rastro, tab_aval = st.tabs(
    ["📥 Documentos", "🗂️ Ficha", "⚖️ Comparar", "💬 Pergunte", "🧭 Agentes", "📏 Avaliação"])

# ============================================================================ documentos
with tab_docs:
    st.subheader("Enviar apólices")
    st.caption(f"PDF (digital ou escaneado), PNG ou JPG · até {config.TAMANHO_MAXIMO_BYTES // 2**20} MB · "
               f"até {config.PAGINAS_MAXIMAS} páginas")
    enviados = st.file_uploader("Arquivos", type=["pdf", "png", "jpg", "jpeg"], accept_multiple_files=True,
                                label_visibility="collapsed")
    if enviados and st.button("Processar", type="primary"):
        for arq in enviados:
            with st.status(f"{arq.name}", expanded=True) as s:
                t0 = time.time()
                try:
                    estado = grafo.processar(arq.name, arq.getvalue(), armazem(), cascata_ativa(),
                                             progresso=lambda ag, msg: s.write(f"**{ag}** · {seguro(msg)}"))
                    s.update(label=f"{seguro(estado['documento'].rotulo)} · {time.time() - t0:.0f}s", state="complete")
                except recepcionista.DocumentoRecusado as erro:
                    s.update(label=f"{arq.name}: recusado", state="error")
                    st.error(str(erro))
                except Exception:
                    s.update(label=f"{arq.name}: falhou", state="error")
                    st.error("Não foi possível processar este arquivo. Detalhes no log do servidor.")
    docs = armazem().documentos()
    st.subheader(f"Documentos processados ({len(docs)})")
    if docs:
        tabela = pd.DataFrame([{
            "Documento": (d["metadados"].get("seguradora") or d["nome"]) + (" [FICTÍCIO]" if d["ficticio"] and
                                                                          "fict" not in (d["metadados"].get("seguradora") or "").lower() else ""),
            "Arquivo": d["nome"], "Tipo": d["tipo_arquivo"].upper(), "Páginas": d["paginas"],
            "Páginas com OCR": d["paginas_ocr"], "Origem": d["metadados"].get("url") or ("fictício" if d["ficticio"] else "enviado"),
        } for d in docs])
        st.dataframe(tabela, hide_index=True, use_container_width=True)
    else:
        st.info("Nenhum documento ainda. Envie arquivos acima ou use “Carregar corpus de demonstração”.")


def seletor_documentos(chave: str, multiplo: bool, padrao=None):
    docs = armazem().documentos()
    opcoes = {d["id"]: armazem().documento(d["id"]).rotulo for d in docs}
    if not opcoes:
        st.info("Processe documentos na aba Documentos.")
        return [] if multiplo else None
    if multiplo:
        ficticios = [d["id"] for d in docs if d["ficticio"]]
        inicial = padrao or (ficticios[:3] if len(ficticios) >= 2 else list(opcoes)[:2])
        return st.multiselect("Documentos", list(opcoes), default=inicial,
                              format_func=lambda i: opcoes[i], key=chave, max_selections=4)
    return st.selectbox("Documento", list(opcoes), format_func=lambda i: opcoes[i], key=chave)


def mostrar_evidencia(doc, v, chave: str):
    st.markdown(f"**Página {v.evidencia.pagina}** · similaridade {v.evidencia.similaridade:.2f} · {seguro(v.metodo)}")
    st.text(v.evidencia.trecho)
    if v.observacao:
        st.caption(seguro(v.observacao))
    if st.toggle("Ver página original", key=chave):
        img = pagina_png(doc, v.evidencia.pagina, v.evidencia.trecho)
        if img:
            st.image(img, caption=f"{doc.rotulo} — página {v.evidencia.pagina} (trecho destacado quando o PDF tem texto)")


# ============================================================================ ficha
with tab_ficha:
    doc_id = seletor_documentos("ficha_doc", multiplo=False)
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
            a.metric("Verificados", cont["verificado"])
            b.metric("Reprovados pelo verificador", cont["nao_verificado"])
            c_.metric("Não localizados", cont["nao_localizado"])
            d_.metric("Modo", ficha.modo)
            esq = carregar_esquema()
            for grupo_id, grupo_nome in esq.grupos.items():
                with st.expander(grupo_nome, expanded=grupo_id in ("limites", "coberturas")):
                    for campo in [x for x in esq.campos if x.grupo == grupo_id]:
                        v = ficha.valores.get(campo.id)
                        if v is None:
                            continue
                        col1, col2, col3 = st.columns([3, 4, 2])
                        col1.markdown(f"**{seguro(campo.rotulo)}**")
                        col2.markdown(seguro(texto_curto(v)) if v.exibivel else "—")
                        col3.markdown(ROTULO_STATUS[v.status.value])
                        if v.exibivel and v.evidencia:
                            with st.popover("Evidência", use_container_width=False):
                                mostrar_evidencia(doc, v, f"pg_{doc_id}_{campo.id}")
                        elif v.status == StatusEvidencia.NAO_VERIFICADO:
                            st.caption(f"Valor descartado: {seguro(v.observacao)}")

# ============================================================================ comparar
with tab_comp:
    ids = seletor_documentos("comp_docs", multiplo=True)
    so_diferencas = st.toggle("Mostrar só campos diferentes", value=True)
    if len(ids) >= 2 and st.button("Comparar", type="primary"):
        with st.spinner("Comparador → Conformidade → Relator…"):
            try:
                st.session_state["comparacao"] = grafo.comparar(ids, armazem(), cascata_ativa())
            except ValueError as erro:
                st.error(str(erro))
    estado = st.session_state.get("comparacao")
    if estado and estado["comparacao"].doc_ids == ids:
        comp, docs = estado["comparacao"], estado["documentos"]
        if any(d.ficticio for d in docs):
            st.warning("A comparação inclui DOCUMENTO FICTÍCIO (demonstração acadêmica).")
        st.subheader("Resumo executivo")
        st.caption(f"Gerado por: {seguro(comp.modo_resumo)}")
        st.markdown("\n".join(seguro(l).replace("\\- ", "- ", 1) for l in comp.resumo.splitlines()))
        st.download_button("⬇️ Relatório comparativo (PDF)", estado["pdf"], file_name="PRISMA_DO_comparativo.pdf",
                           mime="application/pdf")
        esq = carregar_esquema()
        linhas, estilos = [], []
        for l in comp.linhas:
            if so_diferencas and not l.diferente:
                continue
            linha, estilo = {"Campo": l.rotulo}, {"Campo": ""}
            for d in docs:
                v = l.valores.get(d.id)
                fav = l.classificacao.get(d.id, Favorabilidade.NAO_COMPARAVEL).value
                if v and v.status == StatusEvidencia.VERIFICADO:
                    texto = f"{texto_curto(v)} · p.{v.evidencia.pagina}"
                elif v and v.status == StatusEvidencia.NA_ESPECIFICACAO:
                    texto = "na especificação"
                else:
                    texto = "não localizado"
                linha[d.rotulo] = f"{SIMBOLO_FAV[fav]} {texto}".strip()
                estilo[d.rotulo] = f"background-color: {CORES[fav]}"
            linhas.append(linha)
            estilos.append(estilo)
        if linhas:
            st.caption("▲ mais favorável ao segurado · ▼ menos favorável · ◆ intermediária · = equivalente · "
                       "p. = página da evidência · sem símbolo = informativo ou não comparável")
            df = pd.DataFrame(linhas)
            st.dataframe(df.style.apply(lambda _: pd.DataFrame(estilos, index=df.index, columns=df.columns), axis=None),
                         hide_index=True, use_container_width=True, height=min(760, 36 * (len(linhas) + 1)),
                         column_config={"Campo": st.column_config.TextColumn(width=230),
                                        **{d.rotulo: st.column_config.TextColumn(width=250) for d in docs}})
        st.subheader("Por que essa classificação?")
        # primeiro os campos com juízo de favorabilidade; os informativos (seguradora, processo…) por último
        campos_dif = sorted([l for l in comp.linhas if l.diferente],
                            key=lambda l: all(f == Favorabilidade.NAO_COMPARAVEL for f in l.classificacao.values()))
        escolhido = st.selectbox("Campo", [l.campo_id for l in campos_dif],
                                 format_func=lambda cid: esq.campo(cid).rotulo) if campos_dif else None
        if escolhido:
            l = next(x for x in comp.linhas if x.campo_id == escolhido)
            st.caption(f"Regra {l.regra_id or '—'} · {seguro(l.motivo) or 'informativo'}")
            cols = st.columns(len(docs))
            for col, d in zip(cols, docs):
                with col:
                    st.markdown(f"**{seguro(d.rotulo)}**")
                    v = l.valores.get(d.id)
                    if v and v.status == StatusEvidencia.VERIFICADO:
                        mostrar_evidencia(d, v, f"cmp_{d.id}_{escolhido}")
                    else:
                        st.caption("sem valor verificado")
        st.subheader("Conformidade (indícios para revisão humana)")
        if not comp.alertas:
            st.success("Nenhum alerta das regras declaradas.")
        por_id = {d.id: d for d in docs}
        for a in comp.alertas:
            caixa = st.warning if a.severidade == "atencao" else st.info
            caixa(f"**{seguro(por_id[a.doc_id].rotulo)} · {seguro(a.artigo)}** — {seguro(a.mensagem)}")
            with st.expander("Fundamento e evidência"):
                st.text(a.fundamento)
                if a.evidencia:
                    st.text(f"pág. {a.evidencia.pagina}: {a.evidencia.trecho}")

# ============================================================================ pergunte
with tab_perg:
    ids_p = seletor_documentos("perg_docs", multiplo=True)
    pergunta = st.text_input("Pergunta", placeholder="Ex.: A apólice cobre multas aplicadas pela CVM?", max_chars=500)
    if pergunta and ids_p and st.button("Perguntar", type="primary"):
        docs_p = [armazem().documento(i) for i in ids_p]
        with st.spinner("Buscando trechos e conferindo citações…"):
            r = consultor.perguntar(pergunta, docs_p, armazem(), cascata_ativa())
        st.markdown(seguro(r.texto))
        st.caption(f"Modo: {seguro(r.modo)}" + (f" · {r.descartadas} citação(ões) descartada(s) por não existirem no documento"
                                               if r.descartadas else ""))
        por_id = {d.id: d for d in docs_p}
        for i, cit in enumerate(r.citacoes):
            with st.expander(f"{cit['rotulo']} — página {cit['pagina']}"):
                st.text(cit["trecho"])
                if st.toggle("Ver página", key=f"perg_pg_{i}"):
                    img = pagina_png(por_id[cit["doc_id"]], cit["pagina"], cit["trecho"])
                    if img:
                        st.image(img)

# ============================================================================ agentes
with tab_rastro:
    st.subheader("Arquitetura")
    st.graphviz_chart("""digraph {
      rankdir=LR; node [shape=box, style="rounded,filled", fillcolor="#eef2f8", fontname="Helvetica", fontsize=11];
      subgraph cluster_1 { label="Grafo 1 — processar documento"; style=dashed;
        R [label="Recepcionista\\ntipo, tamanho, SHA-256"]; L [label="Leitor\\ntexto nativo + OCR por página"];
        S [label="Segmentador\\ncláusulas com página"]; E [label="Extrator\\nregras + LLM gratuito"];
        V [label="Verificador\\ntrecho, assunto, número, injeção"]; R->L->S->E->V; }
      DB [label="SQLite\\nfichas + rastro", shape=cylinder, fillcolor="#fff5d6"];
      subgraph cluster_2 { label="Grafo 2 — comparar"; style=dashed;
        C [label="Comparador\\nregras de favorabilidade"]; F [label="Conformidade\\nCircular SUSEP 637"];
        RE [label="Relator\\nresumo ancorado + PDF"]; C->F->RE; }
      Q [label="Consultor\\nperguntas com citação"];
      V->DB; DB->C; DB->Q; }""")
    st.subheader("Rastro dos agentes (últimos passos)")
    passos = armazem().rastro(limite=60)
    if passos:
        st.dataframe(pd.DataFrame([{"Execução": p["execucao"], "Agente": p["agente"], "Documento": p["doc_id"],
                                    "Duração (s)": p["duracao_s"],
                                    "Detalhe": json.dumps(p["detalhe"], ensure_ascii=False)[:160]} for p in passos]),
                     hide_index=True, use_container_width=True)

# ============================================================================ avaliação
with tab_aval:
    st.subheader("Qualidade medida contra o gabarito")
    st.caption("python -m prisma.cli avaliar --modo deterministico --ocr · python -m prisma.cli avaliar --modo hibrido")
    achou = False
    for modo in ("deterministico", "hibrido"):
        arq = config.SAIDA / f"avaliacao_{modo}.json"
        if not arq.exists():
            continue
        achou = True
        dados = json.loads(arq.read_text(encoding="utf-8"))
        st.markdown(f"#### Modo {modo}")
        cols = st.columns(4)
        for col, chave, nome in zip(cols, ("desenvolvimento", "holdout", "especificacoes", "condicoes_gerais"),
                                    ("Desenvolvimento", "Holdout (nunca visto)", "Especificações", "Condições gerais")):
            t = dados["resumo"][chave]
            if t["campos"]:
                col.metric(nome, f"{100 * t['acuracia']:.1f}%", f"{t['acertos']}/{t['campos']} campos", delta_color="off")
                col.caption(f"valores errados exibidos: {t['valores_errados_exibidos']}")
        if dados.get("ocr"):
            st.caption(f"OCR — CER por linha: médio {100 * dados['ocr']['cer_medio']:.2f}% · máximo {100 * dados['ocr']['cer_maximo']:.2f}%")
    if not achou:
        st.info("Rode a avaliação pela linha de comando para ver as métricas aqui.")
