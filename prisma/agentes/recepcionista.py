# -*- coding: utf-8 -*-
"""Agente Recepcionista — porta de entrada dos documentos.

Valida tipo pela ASSINATURA DE BYTES (não pela extensão), tamanho e número de páginas;
calcula SHA-256 (identidade e deduplicação) e decide se o documento é fictício.
"""
from __future__ import annotations

import hashlib
from dataclasses import dataclass

from prisma import config

ASSINATURAS = {
    b"%PDF-": "pdf",
    b"\x89PNG\r\n\x1a\n": "png",
    b"\xff\xd8\xff": "jpg",
}

CARIMBO_FICTICIO = "FICTÍCIO"


class DocumentoRecusado(ValueError):
    """Arquivo fora da política de upload. A mensagem é segura para mostrar ao usuário."""


@dataclass
class Recebido:
    nome: str
    conteudo: bytes
    sha256: str
    tipo_arquivo: str

    @property
    def doc_id(self) -> str:
        return self.sha256[:12]


def detectar_tipo(conteudo: bytes) -> str | None:
    for assinatura, tipo in ASSINATURAS.items():
        if conteudo.startswith(assinatura):
            return tipo
    # alguns PDFs trazem lixo antes do cabeçalho; a especificação tolera até 1024 bytes
    if b"%PDF-" in conteudo[:1024]:
        return "pdf"
    return None


def receber(nome: str, conteudo: bytes) -> Recebido:
    if not conteudo:
        raise DocumentoRecusado("Arquivo vazio.")
    if len(conteudo) > config.TAMANHO_MAXIMO_BYTES:
        mb = config.TAMANHO_MAXIMO_BYTES // (1024 * 1024)
        raise DocumentoRecusado(f"Arquivo maior que o limite de {mb} MB.")
    tipo = detectar_tipo(conteudo)
    if tipo not in config.TIPOS_ACEITOS:
        raise DocumentoRecusado("Tipo de arquivo não aceito. Envie PDF, PNG ou JPG.")
    if tipo == "pdf":
        import pymupdf

        try:
            with pymupdf.open(stream=conteudo, filetype="pdf") as doc:
                if doc.needs_pass:
                    raise DocumentoRecusado("PDF protegido por senha não é aceito.")
                if doc.page_count > config.PAGINAS_MAXIMAS:
                    raise DocumentoRecusado(f"PDF com mais de {config.PAGINAS_MAXIMAS} páginas.")
                if doc.page_count == 0:
                    raise DocumentoRecusado("PDF sem páginas.")
        except DocumentoRecusado:
            raise
        except Exception:
            raise DocumentoRecusado("PDF corrompido ou ilegível.")
    nome_seguro = "".join(c for c in nome if c.isalnum() or c in "._- ()").strip() or "documento"
    return Recebido(nome=nome_seguro[:120], conteudo=conteudo,
                    sha256=hashlib.sha256(conteudo).hexdigest(), tipo_arquivo=tipo)


def eh_ficticio(textos_paginas: list[str]) -> bool:
    """Lei do Documento Rotulado: o carimbo está no próprio arquivo, não num banco de dados."""
    primeiras = " ".join(textos_paginas[:2]).upper()
    return CARIMBO_FICTICIO in primeiras
