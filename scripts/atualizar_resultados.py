# -*- coding: utf-8 -*-
"""Escreve a seção "Resultados medidos" do README a partir de saida/avaliacao_*.json.

Nenhum número do README é digitado à mão: se `avaliar` não reproduzir, o README muda junto.
Uso: python scripts/atualizar_resultados.py
"""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ))
from prisma import config  # noqa: E402

NOMES = {"desenvolvimento": "Conjunto de desenvolvimento", "holdout": "**Holdout** (documentos nunca vistos)",
         "especificacoes": "↳ especificações (PDF digital, escaneado, PNG)", "condicoes_gerais": "↳ condições gerais reais"}


def carregar(modo: str) -> dict | None:
    arq = config.SAIDA / f"avaliacao_{modo}.json"
    return json.loads(arq.read_text(encoding="utf-8")) if arq.exists() else None


def pct(t: dict) -> str:
    return f"{100 * t['acuracia']:.1f}% ({t['acertos']}/{t['campos']})" if t and t["campos"] else "—"


def secao() -> str:
    det, hib = carregar("deterministico"), carregar("hibrido")
    if not det and not hib:
        return "_Ainda não há avaliação em `saida/`._"
    linhas = ["Acurácia de extração contra o gabarito anotado. Conta como resposta só o valor **verificado** "
              "(o que o usuário veria na tela). \"Errados exibidos\" = valor verificado mas diferente do gabarito.",
              "", "| Conjunto | Sem chave (regras) | Errados exibidos | Híbrido (LLM + regras) | Errados exibidos |",
              "|---|---|---|---|---|"]
    for chave, nome in NOMES.items():
        d = det["resumo"][chave] if det else None
        h = hib["resumo"][chave] if hib else None
        linhas.append(f"| {nome} | {pct(d)} | {d['valores_errados_exibidos'] if d else '—'} | "
                      f"{pct(h)} | {h['valores_errados_exibidos'] if h else '—'} |")
    base = det or hib
    docs = {i["documento"] for i in base["detalhe"]}
    campos = len(base["detalhe"])
    linhas += ["", f"Gabarito: **{campos} campos** em {len(docs)} documentos. O holdout (Sompo e Chubb Capital Fechado) "
               "foi anotado antes de rodar o extrator, e as regras não foram ajustadas depois dele."]
    ocr = (det or {}).get("ocr") or (hib or {}).get("ocr")
    if ocr:
        paginas = ocr["paginas"]
        inteira = [p.get("cer_pagina_inteira") for p in paginas if p.get("cer_pagina_inteira") is not None]
        linhas += ["", f"**OCR (RapidOCR)** em {len(paginas)} páginas: CER alinhado por linha médio "
                   f"**{100 * ocr['cer_medio']:.2f}%** (máximo {100 * ocr['cer_maximo']:.2f}%)"
                   + (f"; CER da página inteira, que também pune diferença de ordem de leitura, até "
                      f"{100 * max(inteira):.1f}%." if inteira else ".")]
    return "\n".join(linhas)


def main() -> None:
    readme = RAIZ / "README.md"
    texto = readme.read_text(encoding="utf-8")
    novo = re.sub(r"(<!-- RESULTADOS:INICIO -->\n).*?(\n<!-- RESULTADOS:FIM -->)",
                  lambda m: m.group(1) + secao() + m.group(2), texto, flags=re.S)
    readme.write_text(novo, encoding="utf-8")
    print(secao())


if __name__ == "__main__":
    main()
