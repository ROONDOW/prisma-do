# -*- coding: utf-8 -*-
"""Linha de comando do PRISMA D&O.

  python -m prisma.cli baixar-corpus              baixa as condições gerais públicas (hash conferido)
  python -m prisma.cli demo [--sem-llm]           processa o corpus e gera os relatórios comparativos
  python -m prisma.cli processar ARQ [ARQ...]     processa documentos (PDF, PNG, JPG)
  python -m prisma.cli comparar ARQ ARQ [...]     compara documentos já processados (ou processa antes)
  python -m prisma.cli perguntar "PERGUNTA" ARQ…  pergunta livre com citação
  python -m prisma.cli avaliar [--modo M]         acurácia contra o gabarito + CER do OCR
  python -m prisma.cli rastro [EXECUCAO]          passos dos agentes
"""
from __future__ import annotations

import argparse
import hashlib
import json
import sys
import time
from pathlib import Path

from prisma import config


def _cascata(sem_llm: bool):
    if sem_llm:
        return None
    from prisma import llm

    config.carregar_env()
    c = llm.obter()
    print(f"[LLM] {'cascata: ' + c.descricao if c else 'sem chave: modo determinístico (regras declaradas)'}")
    return c


def _processar(caminhos: list[Path], armazem, cascata, forcar_ficha: bool = False) -> list[str]:
    from prisma import grafo

    ids = []
    for caminho in caminhos:
        conteudo = caminho.read_bytes()
        doc_id = hashlib.sha256(conteudo).hexdigest()[:12]
        ficha = armazem.ficha(doc_id)
        modo_desejado = "hibrido" if cascata else "deterministico"
        if ficha and ficha.modo == modo_desejado and not forcar_ficha:
            print(f"  = {caminho.name}: ficha {ficha.modo} já existe")
            ids.append(doc_id)
            continue
        t0 = time.time()
        estado = grafo.processar(caminho.name, conteudo, armazem, cascata,
                                 progresso=lambda ag, msg: print(f"    {ag:<13} {msg}"))
        print(f"  ✓ {estado['documento'].rotulo} ({time.time() - t0:.1f}s)")
        ids.append(estado["documento"].id)
    return ids


def cmd_baixar(_args) -> int:
    from prisma import corpus

    baixados = corpus.baixar()
    print(f"{len(baixados)} documento(s) disponíveis em {config.REAIS}")
    return 0


def cmd_processar(args) -> int:
    from prisma.armazem import Armazem

    _processar([Path(a) for a in args.arquivos], Armazem(), _cascata(args.sem_llm), forcar_ficha=args.refazer)
    return 0


def cmd_comparar(args) -> int:
    from prisma import grafo
    from prisma.armazem import Armazem

    armazem, cascata = Armazem(), _cascata(args.sem_llm)
    ids = _processar([Path(a) for a in args.arquivos], armazem, cascata)
    estado = grafo.comparar(ids, armazem, cascata)
    comp = estado["comparacao"]
    destino = Path(args.pdf or config.SAIDA / f"comparativo_{estado['comparacao_id']}.pdf")
    destino.parent.mkdir(parents=True, exist_ok=True)
    destino.write_bytes(estado["pdf"])
    print("\nRESUMO\n" + comp.resumo)
    for a in comp.alertas:
        print(f"  [{a.severidade}] {a.artigo}: {a.mensagem}")
    print(f"\nRelatório comparativo: {destino}")
    return 0


def cmd_perguntar(args) -> int:
    from prisma.agentes import consultor
    from prisma.armazem import Armazem

    armazem, cascata = Armazem(), _cascata(args.sem_llm)
    ids = _processar([Path(a) for a in args.arquivos], armazem, cascata)
    r = consultor.perguntar(args.pergunta, [armazem.documento(i) for i in ids], armazem, cascata)
    print(f"\n{r.texto}\n")
    for c in r.citacoes:
        print(f"  [{c['rotulo']}, pág. {c['pagina']}] \"{c['trecho'][:200]}\"")
    if r.descartadas:
        print(f"  ({r.descartadas} citação(ões) do LLM descartada(s) por não existirem no documento)")
    return 0


def cmd_demo(args) -> int:
    from prisma import corpus, grafo
    from prisma.armazem import Armazem

    armazem, cascata = Armazem(), _cascata(args.sem_llm)
    if not all((config.REAIS / d["arquivo"]).exists() for d in corpus.fontes()["documentos"]):
        print("Baixando o corpus público…")
        corpus.baixar()
    print("\n1) Processando documentos")
    arquivos = corpus.arquivos_demo()
    ids = dict(zip([a.name for a in arquivos], _processar(arquivos, armazem, cascata)))
    pares = {
        "cotacoes_ficticias": ["especificacao_aurora.pdf", "especificacao_boreal_escaneada.pdf", "especificacao_cruzeiro.png"],
        "condicoes_gerais": ["chubb_do_capital_aberto.pdf", "berkley_do.pdf", "essor_do.pdf", "argo_do.pdf"],
        "versoes_berkley": ["berkley_do_v2017_2023.pdf", "berkley_do.pdf"],
    }
    print("\n2) Comparando")
    for nome, arqs in pares.items():
        doc_ids = [ids[a] for a in arqs if a in ids]
        if len(doc_ids) < 2:
            continue
        estado = grafo.comparar(doc_ids, armazem, cascata)
        destino = config.SAIDA / f"comparativo_{nome}.pdf"
        destino.write_bytes(estado["pdf"])
        diferentes = sum(l.diferente for l in estado["comparacao"].linhas)
        print(f"  ✓ {nome}: {diferentes} campos diferentes, {len(estado['comparacao'].alertas)} alerta(s) -> {destino}")
    print(f"\nPronto. Interface: streamlit run streamlit_app.py")
    return 0


def _medir_ocr(amostras: int = 6) -> dict:
    """CER do OCR contra a camada de texto do próprio PDF: renderiza páginas digitais, lê com OCR
    e compara. Mais a especificação escaneada contra sua versão digital."""
    import pymupdf

    from prisma.agentes import leitor

    resultados = []
    candidatos = [config.REAIS / "chubb_do_capital_aberto.pdf", config.REAIS / "berkley_do.pdf",
                  config.REAIS / "argo_do.pdf"]
    for pdf in [c for c in candidatos if c.exists()]:
        with pymupdf.open(pdf) as d:
            for n in (10, 20, 30)[: max(1, amostras // len(candidatos))]:
                pg = d[min(n, d.page_count - 1)]
                ref = pg.get_text()
                t0 = time.time()
                hip, _ = leitor.ocr_imagem(pg.get_pixmap(dpi=config.DPI_OCR).tobytes("png"))
                resultados.append({"documento": pdf.name, "pagina": pg.number + 1,
                                   "cer": round(leitor.cer_por_linha(ref, hip), 4), "cer_pagina_inteira": round(leitor.cer(ref, hip), 4),
                                   "segundos": round(time.time() - t0, 1)})
    dig, esc = config.SINTETICAS / "especificacao_boreal_digital.pdf", config.SINTETICAS / "especificacao_boreal_escaneada.pdf"
    if dig.exists() and esc.exists():
        ref = leitor.ler(dig.read_bytes(), "pdf")[0].texto
        t0 = time.time()
        hip = leitor.ler(esc.read_bytes(), "pdf")[0].texto
        resultados.append({"documento": esc.name, "pagina": 1, "cer": round(leitor.cer_por_linha(ref, hip), 4),
                           "cer_pagina_inteira": round(leitor.cer(ref, hip), 4),
                           "segundos": round(time.time() - t0, 1), "nota": "escaneada (ruído, inclinação, JPEG) × digital"})
    cers = [r["cer"] for r in resultados]
    return {"paginas": resultados, "cer_medio": round(sum(cers) / len(cers), 4) if cers else None,
            "cer_maximo": max(cers) if cers else None}


def cmd_avaliar(args) -> int:
    from prisma import avaliacao
    from prisma.armazem import Armazem

    armazem = Armazem()
    cascata = _cascata(args.modo == "deterministico")
    arquivos = [avaliacao.caminho_documento(g["documento"]) for g in avaliacao.carregar_gabaritos()]
    faltando = [g["documento"] for g, a in zip(avaliacao.carregar_gabaritos(), arquivos) if a is None]
    if faltando:
        print(f"Faltam documentos (rode baixar-corpus): {faltando}")
    ids = _processar([a for a in arquivos if a], armazem, cascata)
    fichas = {i: armazem.ficha(i, "hibrido" if cascata else "deterministico") for i in ids}
    r = avaliacao.avaliar_fichas(fichas)
    saida = {"modo": "hibrido" if cascata else "deterministico", "resumo": r["resumo"], "detalhe": r["detalhe"]}
    if args.ocr:
        print("Medindo CER do OCR…")
        saida["ocr"] = _medir_ocr()
    destino = config.SAIDA / f"avaliacao_{saida['modo']}.json"
    destino.write_text(json.dumps(saida, ensure_ascii=False, indent=1, default=str), encoding="utf-8")
    res = r["resumo"]
    print(f"\nMODO {saida['modo'].upper()}")
    for chave in ("desenvolvimento", "holdout", "especificacoes", "condicoes_gerais"):
        t = res[chave]
        if t["campos"]:
            print(f"  {chave:<17} {t['acertos']:>3}/{t['campos']:<3} = {100 * t['acuracia']:.1f}%   "
                  f"valores errados exibidos: {t['valores_errados_exibidos']}")
    if saida.get("ocr"):
        print(f"  OCR: CER médio {100 * saida['ocr']['cer_medio']:.2f}% · máximo {100 * saida['ocr']['cer_maximo']:.2f}%")
    print(f"Detalhe: {destino}")
    return 0


def cmd_rastro(args) -> int:
    from prisma.armazem import Armazem

    for p in Armazem().rastro(args.execucao, limite=40)[::-1]:
        print(f"{p['execucao']}  {p['agente']:<15} {p['doc_id'] or '-':<13} {p['duracao_s']:>7.2f}s  "
              f"{json.dumps(p['detalhe'], ensure_ascii=False)[:110]}")
    return 0


def main(argv=None) -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    ap = argparse.ArgumentParser(prog="prisma", description="PRISMA D&O — análise e comparação de apólices D&O")
    sub = ap.add_subparsers(dest="comando", required=True)
    sub.add_parser("baixar-corpus").set_defaults(fn=cmd_baixar)
    p = sub.add_parser("demo"); p.add_argument("--sem-llm", action="store_true"); p.set_defaults(fn=cmd_demo)
    p = sub.add_parser("processar"); p.add_argument("arquivos", nargs="+"); p.add_argument("--sem-llm", action="store_true")
    p.add_argument("--refazer", action="store_true"); p.set_defaults(fn=cmd_processar)
    p = sub.add_parser("comparar"); p.add_argument("arquivos", nargs="+"); p.add_argument("--sem-llm", action="store_true")
    p.add_argument("--pdf"); p.set_defaults(fn=cmd_comparar)
    p = sub.add_parser("perguntar"); p.add_argument("pergunta"); p.add_argument("arquivos", nargs="+")
    p.add_argument("--sem-llm", action="store_true"); p.set_defaults(fn=cmd_perguntar)
    p = sub.add_parser("avaliar"); p.add_argument("--modo", choices=["deterministico", "hibrido"], default="deterministico")
    p.add_argument("--ocr", action="store_true"); p.set_defaults(fn=cmd_avaliar)
    p = sub.add_parser("rastro"); p.add_argument("execucao", nargs="?"); p.set_defaults(fn=cmd_rastro)
    args = ap.parse_args(argv)
    return args.fn(args)


if __name__ == "__main__":
    raise SystemExit(main())
