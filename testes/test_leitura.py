# -*- coding: utf-8 -*-
import pymupdf
import pytest

from prisma.agentes import leitor, recepcionista, segmentador
from prisma.modelos import Documento, Pagina


def _pdf(paginas: list[str]) -> bytes:
    doc = pymupdf.open()
    for texto in paginas:
        pg = doc.new_page()
        pg.insert_text((50, 60), texto, fontsize=10)
    return doc.tobytes()


# ---------------------------------------------------------------- recepcionista
def test_recusa_por_assinatura_e_nao_por_extensao():
    with pytest.raises(recepcionista.DocumentoRecusado):
        recepcionista.receber("apolice.pdf", b"MZ\x90\x00 isto e um executavel")


def test_recusa_arquivo_grande(monkeypatch):
    monkeypatch.setattr("prisma.config.TAMANHO_MAXIMO_BYTES", 10)
    with pytest.raises(recepcionista.DocumentoRecusado, match="limite"):
        recepcionista.receber("a.pdf", b"%PDF-1.7 " + b"x" * 100)


def test_aceita_pdf_e_calcula_hash():
    r = recepcionista.receber("../../etc/passwd.pdf", _pdf(["ola"]))
    assert r.tipo_arquivo == "pdf"
    assert len(r.sha256) == 64 and r.doc_id == r.sha256[:12]
    assert "/" not in r.nome


def test_pdf_corrompido_e_recusado():
    with pytest.raises(recepcionista.DocumentoRecusado):
        recepcionista.receber("x.pdf", b"%PDF-1.7 lixo sem estrutura")


def test_carimbo_ficticio():
    assert recepcionista.eh_ficticio(["ESPECIFICAÇÃO — DOCUMENTO FICTÍCIO — DEMONSTRAÇÃO"])
    assert not recepcionista.eh_ficticio(["Condições Gerais Chubb"])


# ---------------------------------------------------------------- leitor
def test_leitor_texto_nativo_por_pagina():
    paginas = leitor.ler(_pdf(["Pagina um com texto suficiente para nao precisar de OCR algum aqui " * 2,
                               "Pagina dois tambem com bastante texto nativo para a leitura direta " * 2]), "pdf")
    assert [p.numero for p in paginas] == [1, 2]
    assert all(p.metodo == "nativo" for p in paginas)


def test_remove_cabecalho_e_rodape_repetidos():
    def corpo(i: int) -> str:  # páginas realistas: corpo maior que a janela de bordas
        return "\n".join(f"clausula {i}.{k} texto proprio {'abcdefgh'[k % 8] * (k + i)} sobre franquia"
                         for k in range(12))

    paginas = [Pagina(numero=i, texto=f"SEGURADORA X - RC D&O\nProcesso SUSEP 15414.000001/2020-{i:02d}\n"
                                      f"{corpo(i)}\nPágina {i} de 6")
               for i in range(1, 7)]
    limpas = leitor.remover_cabecalhos_rodapes(paginas)
    assert "Processo SUSEP" in limpas[0].texto  # a 1ª página preserva o cabeçalho (metadados)
    for p in limpas[1:]:
        assert "SEGURADORA X" not in p.texto
        assert "Processo SUSEP" not in p.texto
        assert "Página" not in p.texto
        assert f"clausula {p.numero}.5 texto proprio" in p.texto


def test_cer():
    assert leitor.cer("abc", "abc") == 0
    assert leitor.cer("abcd", "abxd") == 0.25


# ---------------------------------------------------------------- segmentador
def _doc(textos: list[str]) -> Documento:
    return Documento(id="t1", nome="t", sha256="0" * 64, tipo_arquivo="pdf",
                     paginas=[Pagina(numero=i + 1, texto=t) for i, t in enumerate(textos)])


def test_segmenta_os_quatro_estilos_de_titulo():
    doc = _doc([
        "CONDIÇÕES GERAIS\n1. DEFINIÇÕES\nApólice: documento emitido.\n"
        "CLÁUSULA 7ª - EXCLUSÕES\nNão cobre dolo.\n",
        "COBERTURA ADICIONAL DE MULTAS E\nPENALIDADES\nCobre multas.\n"
        "9.1. Prazo Adicional\nO segurado terá direito.\n3.1. O presente seguro é contratado à base de reclamações.\n",
    ])
    cl = segmentador.segmentar(doc)
    titulos = [c.titulo for c in cl]
    assert "DEFINIÇÕES" in titulos
    assert any(t.startswith("CLÁUSULA 7ª") for t in titulos)
    assert "COBERTURA ADICIONAL DE MULTAS E PENALIDADES" in titulos
    assert "Prazo Adicional" in titulos
    assert not any(t.startswith("O presente seguro") for t in titulos)  # frase numerada não é título
    multas = next(c for c in cl if c.titulo.startswith("COBERTURA ADICIONAL"))
    assert multas.pagina_inicio == 2 and multas.secao == "condicoes_gerais"


def test_pagina_de_indice_nao_gera_titulos():
    indice = "\n".join(f"{i}. TITULO NUMERO {i} ........................ {i + 3}" for i in range(1, 9))
    doc = _doc([indice, "1. DEFINIÇÕES\nTexto real.\n"])
    assert segmentador.paginas_de_indice(doc) == {1}
    cl = segmentador.segmentar(doc)
    assert [c.titulo for c in cl if c.titulo != "ÍNDICE"] == ["DEFINIÇÕES"]


def test_blocos_marcam_mudanca_de_pagina():
    doc = _doc(["4. EXCLUSÕES\nlinha a\n", "linha b\n"])
    cl = segmentador.segmentar(doc)
    bl = segmentador.blocos(doc, cl)
    exc = next(b for b in bl if "EXCLUSÕES" in b.titulo)
    assert "[pág. 1]" in exc.texto and "[pág. 2]" in exc.texto
