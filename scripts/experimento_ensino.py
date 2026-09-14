# -*- coding: utf-8 -*-
"""Experimento "ensina uma vez": o que um ensinamento do corretor faz nos OUTROS documentos.

Parte das fichas determinísticas já avaliadas (python -m prisma.cli avaliar), aplica os ensinamentos
de dados/ensinamentos_experimento.yaml (só documentos de desenvolvimento) e reavalia tudo contra o
gabarito. Não grava nada no banco. Resultado: saida/experimento_ensino.json.

Uso: python scripts/experimento_ensino.py
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import yaml

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ))
from prisma import avaliacao, config, ensino  # noqa: E402
from prisma.armazem import Armazem  # noqa: E402


def main() -> int:
    arm = Armazem()
    plano = yaml.safe_load((config.DADOS / "ensinamentos_experimento.yaml").read_text(encoding="utf-8"))["documentos"]
    gabaritos = avaliacao.carregar_gabaritos()
    ids = {g["documento"]: avaliacao.doc_id_de(g["documento"]) for g in gabaritos}
    docs = {i: arm.documento(i) for i in ids.values() if i}
    antes = {i: arm.ficha(i, "deterministico") for i in docs}
    if any(f is None for f in antes.values()):
        print("Rode antes: python -m prisma.cli avaliar --modo deterministico")
        return 1

    # 1) o corretor ensina nos documentos de desenvolvimento
    holdout = {g["documento"] for g in gabaritos if g.get("holdout")}
    licoes = []
    for item in plano:
        assert item["documento"] not in holdout, "ensinamento em documento nunca visto invalidaria a medição"
        doc = docs[ids[item["documento"]]]
        _, lic = ensino.ensinar(doc, item["campo"], item["valor"], item["trecho"], item["pagina"])
        licoes.append(lic)

    # 2) cada documento recebe os ensinamentos (os do próprio documento e os dos outros)
    depois, aplicados = {}, {}
    for i, doc in docs.items():
        valores, rel = ensino.reaplicar(doc, antes[i].valores, licoes)
        depois[i] = antes[i].model_copy(update={"valores": valores})
        aplicados[doc.nome] = rel

    r0, r1 = avaliacao.avaliar_fichas(antes), avaliacao.avaliar_fichas(depois)
    ensinados = {(l.doc_nome, l.campo_id) for l in licoes}
    mudancas = []
    for a, b in zip(r0["detalhe"], r1["detalhe"]):
        if (a["acerto"], a["previsto"]) != (b["acerto"], b["previsto"]):
            mudancas.append({"documento": a["documento"], "holdout": a["holdout"], "campo": a["campo"],
                             "antes": a["previsto"], "depois": b["previsto"], "acertou": b["acerto"],
                             "tipo": "ensinado aqui" if (a["documento"], a["campo"]) in ensinados else "transferido",
                             "metodo": b["metodo"]})
    saida = {"ensinamentos": [{"documento": l.doc_nome, "campo": l.campo_id, "valor": l.valor, "pagina": l.pagina}
                              for l in licoes],
             "antes": {k: r0["resumo"][k] for k in ("desenvolvimento", "holdout")},
             "depois": {k: r1["resumo"][k] for k in ("desenvolvimento", "holdout")},
             "mudancas": mudancas, "aplicacoes": aplicados}
    destino = config.SAIDA / "experimento_ensino.json"
    destino.write_text(json.dumps(saida, ensure_ascii=False, indent=1, default=str), encoding="utf-8")

    print(f"{len(licoes)} ensinamentos em documentos de desenvolvimento\n")
    for k in ("desenvolvimento", "holdout"):
        a, b = r0["resumo"][k], r1["resumo"][k]
        print(f"  {k:<16} {a['acertos']}/{a['campos']} → {b['acertos']}/{b['campos']}   "
              f"valores errados na tela: {a['valores_errados_exibidos']} → {b['valores_errados_exibidos']}")
    print("\nMudanças campo a campo:")
    for m in mudancas:
        print(f"  [{m['tipo']:<13}] {m['documento']:<32} {m['campo']:<26} {m['antes']} → {m['depois']} "
              f"({'certo' if m['acertou'] else 'ERRADO'}){'  · nunca visto' if m['holdout'] else ''}")
    recusas = [(n, a) for n, rel in aplicados.items() for a in rel if "recusado" in a]
    for n, a in recusas:
        print(f"  [recusado     ] {n:<32} {a['campo']:<26} {a['recusado']}")
    print(f"\nDetalhe: {destino}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
