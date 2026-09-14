# -*- coding: utf-8 -*-
"""Captura telas reais da interface (Playwright + Chromium headless) para relatório, pitch e vídeo.

Pré-requisito: Streamlit no ar (`streamlit run streamlit_app.py`) com o corpus processado.
Uso: python scripts/capturar_telas.py [--url http://localhost:8501] [--video]
Saída: Projeto_Final_Artefatos/telas/*.png (e .webm da navegação com --video)
"""
from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path

from playwright.sync_api import Page, sync_playwright

RAIZ = Path(__file__).resolve().parent.parent
DESTINO = RAIZ / "Projeto_Final_Artefatos" / "telas"


def esperar_streamlit(page: Page, segundos: float = 90) -> None:
    """Espera o Streamlit terminar de rodar o script (some o indicador 'Running')."""
    fim = time.time() + segundos
    time.sleep(1.5)
    while time.time() < fim:
        if page.locator('[data-testid="stStatusWidget"]').count() == 0:
            time.sleep(1.0)
            if page.locator('[data-testid="stStatusWidget"]').count() == 0:
                return
        time.sleep(0.5)


def aba(page: Page, nome: str) -> None:
    page.get_by_role("tab", name=nome).click()
    esperar_streamlit(page)


def rolar(page: Page, y: int) -> None:
    page.evaluate(f"document.querySelector('section.stMain') && (document.querySelector('section.stMain').scrollTop = {y})")
    time.sleep(0.8)


def foto(page: Page, nome: str) -> None:
    DESTINO.mkdir(parents=True, exist_ok=True)
    page.screenshot(path=str(DESTINO / f"{nome}.png"))
    print(f"ok  {nome}.png")


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--url", default="http://localhost:8502")
    ap.add_argument("--video", action="store_true")
    args = ap.parse_args()
    with sync_playwright() as p:
        navegador = p.chromium.launch()
        contexto = navegador.new_context(viewport={"width": 1440, "height": 900}, device_scale_factor=1,
                                         record_video_dir=str(DESTINO) if args.video else None,
                                         record_video_size={"width": 1440, "height": 900} if args.video else None)
        page = contexto.new_page()
        page.goto(args.url)
        page.wait_for_selector('[data-testid="stSidebar"]', timeout=60000)
        esperar_streamlit(page, 120)
        foto(page, "01_documentos")

        aba(page, "🗂️ Ficha")
        page.get_by_role("combobox").first.click()
        page.keyboard.type("Chubb Seguros Brasil")
        page.keyboard.press("Enter")
        esperar_streamlit(page)
        foto(page, "02_ficha_chubb")
        rolar(page, 700)
        foto(page, "03_ficha_coberturas")

        aba(page, "⚖️ Comparar")
        rolar(page, 0)
        page.get_by_role("button", name="Comparar").click()
        esperar_streamlit(page, 120)
        foto(page, "04_comparacao_resumo")
        rolar(page, 850)
        foto(page, "05_comparacao_quadro")
        rolar(page, 2000)
        foto(page, "06_comparacao_conformidade")

        aba(page, "💬 Pergunte")
        rolar(page, 0)
        page.get_by_placeholder("Ex.: A apólice cobre multas aplicadas pela CVM?").fill("A apólice cobre penhora online?")
        page.keyboard.press("Enter")
        esperar_streamlit(page)
        page.get_by_role("button", name="Perguntar").click()
        esperar_streamlit(page, 90)
        foto(page, "07_pergunte")

        aba(page, "🧭 Agentes")
        foto(page, "08_agentes")
        aba(page, "📏 Avaliação")
        foto(page, "09_avaliacao")
        contexto.close()
        navegador.close()


if __name__ == "__main__":
    sys.exit(main())
