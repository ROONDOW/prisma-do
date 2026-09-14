# -*- coding: utf-8 -*-
"""Grava a navegação REAL da interface para o vídeo (Playwright, 1440×810) e anota os tempos de cada
passo em marcas.json, para a montagem cortar os trechos certos.

Pré-requisito: Streamlit no ar. As cotações fictícias são removidas do banco antes, para que o
upload e o OCR aconteçam de verdade na gravação.
Uso: python scripts/gravar_demo.py --url http://localhost:8502 --destino F:/hyperframes-projs/prisma-do/assets/demo
"""
from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

from playwright.sync_api import sync_playwright

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ))
from prisma import config  # noqa: E402
from prisma.armazem import Armazem  # noqa: E402
from scripts.capturar_telas import esperar_streamlit  # noqa: E402

ARQUIVOS = ["especificacao_aurora.pdf", "especificacao_boreal_escaneada.pdf", "especificacao_cruzeiro.png"]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--url", default="http://localhost:8502")
    ap.add_argument("--destino", required=True)
    args = ap.parse_args()
    destino = Path(args.destino)
    destino.mkdir(parents=True, exist_ok=True)

    import hashlib
    a = Armazem()
    for nome in ARQUIVOS:
        a.remover(hashlib.sha256((config.SINTETICAS / nome).read_bytes()).hexdigest()[:12])

    marcas, t0 = {}, None

    def marca(nome):
        marcas[nome] = round(time.time() - t0, 2)
        print(f"{marcas[nome]:7.2f}s  {nome}", flush=True)

    def rolar_suave(page, ate, passos=40, pausa=0.05):
        inicio = page.evaluate("document.querySelector('section.stMain').scrollTop")
        for i in range(1, passos + 1):
            y = inicio + (ate - inicio) * i / passos
            page.evaluate(f"document.querySelector('section.stMain').scrollTop = {y}")
            time.sleep(pausa)

    with sync_playwright() as p:
        nav = p.chromium.launch()
        ctx = nav.new_context(viewport={"width": 1440, "height": 810}, record_video_dir=str(destino),
                              record_video_size={"width": 1440, "height": 810})
        page = ctx.new_page()
        t0 = time.time()
        page.goto(args.url)
        page.wait_for_selector('[data-testid="stSidebar"]', timeout=90000)
        esperar_streamlit(page, 120)
        marca("pronto")

        # --- upload real e processamento
        page.locator('input[type="file"]').set_input_files([str(config.SINTETICAS / n) for n in ARQUIVOS])
        time.sleep(2.0)
        marca("arquivos_escolhidos")
        page.get_by_role("button", name="Processar 3 arquivo(s)").click()
        marca("processar_clicado")
        esperar_streamlit(page, 300)
        marca("processado")
        time.sleep(1.5)
        rolar_suave(page, 900)
        time.sleep(2.0)
        marca("lista_documentos")
        page.screenshot(path=str(destino / "passo_1_documentos.png"))
        # sessão nova: a seleção padrão da comparação passa a enxergar as cotações recém-processadas
        page.goto(args.url)
        page.wait_for_selector('[data-testid="stSidebar"]', timeout=90000)
        esperar_streamlit(page, 120)
        marca("recarregado")

        # --- ficha e evidência
        page.get_by_role("tab", name="2 · Ficha").click()
        esperar_streamlit(page)
        page.get_by_role("combobox").first.click()
        page.keyboard.type("Boreal")
        page.keyboard.press("Enter")
        esperar_streamlit(page)
        marca("ficha_boreal")
        page.screenshot(path=str(destino / "passo_2_ficha.png"))
        time.sleep(2.0)
        page.get_by_role("button", name="Evidência").first.click()
        time.sleep(1.5)
        marca("evidencia_aberta")
        page.get_by_text("Ver página original").first.click()
        esperar_streamlit(page)
        time.sleep(3.0)
        marca("pagina_original")
        page.screenshot(path=str(destino / "passo_3_pagina.png"))
        page.keyboard.press("Escape")
        time.sleep(1.0)

        # --- comparação
        page.get_by_role("tab", name="3 · Comparar").click()
        esperar_streamlit(page)
        marca("aba_comparar")
        page.get_by_role("button", name="Comparar").click()
        esperar_streamlit(page, 120)
        marca("comparado")
        time.sleep(2.0)
        rolar_suave(page, 520, passos=60)
        marca("quadro")
        page.screenshot(path=str(destino / "passo_4_quadro.png"))
        time.sleep(5.0)
        rolar_suave(page, 1400, passos=80)
        time.sleep(1.0)
        rolar_suave(page, 3200, passos=80)
        marca("conformidade")
        page.screenshot(path=str(destino / "passo_5_conformidade.png"))
        time.sleep(4.0)
        marca("fim")
        video = page.video
        ctx.close()
        nav.close()
        Path(video.path()).replace(destino / "demo.webm")
    (destino / "marcas.json").write_text(json.dumps(marcas, indent=1), encoding="utf-8")
    print("ok", destino / "demo.webm")


if __name__ == "__main__":
    main()
