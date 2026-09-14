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
    ocupado = '[data-testid="stStatusWidget"], [data-testid="stSpinner"], [data-stale="true"]'
    time.sleep(1.5)
    while time.time() < fim:
        if page.locator(ocupado).count() == 0:
            time.sleep(1.0)
            if page.locator(ocupado).count() == 0:
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


def usar_ia(page: Page, ligada: bool) -> None:
    """Liga/desliga a IA gratuita na barra lateral. As telas da comparação saem com a IA desligada:
    provedor gratuito congestionado atrasa o resumo em minutos e a foto sairia com o spinner."""
    chave = page.locator('[data-testid="stSidebar"] input[type="checkbox"]').first
    if chave.count() and chave.is_enabled() and chave.is_checked() != ligada:
        page.locator('[data-testid="stSidebar"] [data-testid="stCheckbox"], [data-testid="stSidebar"] label').filter(
            has_text="Usar IA gratuita").first.click()
        esperar_streamlit(page)


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

        aba(page, "2 · Ficha")  # abre na cotação fictícia Aurora, onde há números
        foto(page, "02_ficha")
        page.get_by_role("button", name="Evidência").first.click()
        time.sleep(1.5)
        foto(page, "03_ficha_evidencia")
        page.keyboard.press("Escape")
        time.sleep(0.8)

        # ensinar: abre o formulário num campo não encontrado (sem enviar; o banco não muda)
        page.get_by_role("combobox").first.click()
        page.keyboard.type("berkley_do.pdf")
        page.keyboard.press("Enter")
        esperar_streamlit(page)
        for resumo in page.locator('[data-testid="stExpander"] summary').all():
            if "mbito e cl" in resumo.inner_text():
                resumo.click()
                time.sleep(0.8)
        linha = page.locator('[data-testid="stHorizontalBlock"]').filter(has_text="Âmbito geográfico").last
        linha.get_by_role("button", name="🎓 Ensinar").click()
        time.sleep(1.2)
        corpo = page.locator('[data-testid="stPopoverBody"]').last
        corpo.get_by_label("Procurar no documento").fill("âmbito geográfico")
        corpo.get_by_label("Procurar no documento").press("Enter")
        esperar_streamlit(page)
        corpo = page.locator('[data-testid="stPopoverBody"]').last
        corpo.get_by_label("Página").fill("17")
        corpo.get_by_label("Trecho exato").fill("As disposições deste contrato de seguro aplicam-se exclusivamente a danos "
                                                "ocorridos e reclamados em qualquer parte do mundo, com exceção a Estados "
                                                "Unidos, Canadá, Irã e Cuba")
        corpo.locator('[data-testid="stSelectbox"]').click()
        time.sleep(0.5)
        page.get_by_role("option").filter(has_text="exceto EUA").first.click()
        time.sleep(0.8)
        foto(page, "10_ensinar")
        page.keyboard.press("Escape")
        time.sleep(0.8)

        aba(page, "3 · Comparar")
        rolar(page, 0)
        usar_ia(page, False)
        page.get_by_role("button", name="Comparar").click()
        page.wait_for_selector("table.quadro", timeout=180000)
        esperar_streamlit(page, 60)
        foto(page, "04_comparacao_resumo")
        rolar(page, 900)
        foto(page, "05_comparacao_quadro")
        rolar(page, 2000)
        foto(page, "06_comparacao_conformidade")

        aba(page, "💬 Pergunte")
        usar_ia(page, True)
        rolar(page, 0)
        page.get_by_placeholder("Ex.: A apólice cobre multas aplicadas pela CVM?").fill("A apólice cobre penhora online?")
        page.keyboard.press("Enter")
        esperar_streamlit(page)
        page.get_by_role("button", name="Perguntar").click()
        page.get_by_text("Respondido por").first.wait_for(timeout=240000)
        esperar_streamlit(page, 60)
        foto(page, "07_pergunte")

        aba(page, "🧭 Como funciona")
        foto(page, "08_agentes")
        aba(page, "📏 Qualidade")
        foto(page, "09_avaliacao")
        contexto.close()
        navegador.close()


if __name__ == "__main__":
    sys.exit(main())
