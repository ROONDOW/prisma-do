# -*- coding: utf-8 -*-
"""Contratos de dados do PRISMA D&O (Pydantic).

Tudo que atravessa o grafo de agentes é um destes objetos. O `EstadoDocumento` e o
`EstadoComparacao` são os estados dos grafos LangGraph.
"""
from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Any, Optional

import yaml
from pydantic import BaseModel, Field

from prisma import config


# ---------------------------------------------------------------------------- documento
class MetodoLeitura(str, Enum):
    NATIVO = "nativo"
    OCR = "ocr"


class Pagina(BaseModel):
    numero: int
    texto: str
    metodo: MetodoLeitura = MetodoLeitura.NATIVO
    confianca_ocr: Optional[float] = None


class Documento(BaseModel):
    id: str  # sha256[:12]
    nome: str
    sha256: str
    tipo_arquivo: str  # pdf | png | jpg
    ficticio: bool = False
    metadados: dict[str, Any] = Field(default_factory=dict)
    paginas: list[Pagina] = Field(default_factory=list)

    @property
    def rotulo(self) -> str:
        base = self.metadados.get("seguradora") or self.nome
        return f"{base} [FICTÍCIO]" if self.ficticio else base

    def texto_pagina(self, numero: int) -> str:
        for p in self.paginas:
            if p.numero == numero:
                return p.texto
        return ""


class Clausula(BaseModel):
    id: str
    doc_id: str
    numero: Optional[str] = None
    titulo: str
    nivel: int = 1
    pagina_inicio: int
    pagina_fim: int
    texto: str
    secao: str = ""  # "condicoes_gerais" | "condicoes_especiais" | "condicoes_particulares" | "especificacao"
    mapa_paginas: list[int] = Field(default_factory=list)  # página de cada linha de `texto`


# ---------------------------------------------------------------------------- extração
class StatusEvidencia(str, Enum):
    VERIFICADO = "verificado"
    NAO_VERIFICADO = "nao_verificado"
    NAO_LOCALIZADO = "nao_localizado"
    NA_ESPECIFICACAO = "definido_na_especificacao"


class Evidencia(BaseModel):
    trecho: str
    pagina: int
    similaridade: float = 0.0


class ValorCampo(BaseModel):
    campo_id: str
    valor: Any = None  # valor normalizado (float, str de enum, dict de período, ...)
    valor_texto: str = ""  # como aparece para humanos
    status: StatusEvidencia = StatusEvidencia.NAO_LOCALIZADO
    evidencia: Optional[Evidencia] = None
    metodo: str = "deterministico"  # "deterministico" | "llm:<provedor>"
    observacao: str = ""

    @property
    def exibivel(self) -> bool:
        """Só vai para a tela o valor com evidência verificada (Lei da Citação Verificável)."""
        return self.status == StatusEvidencia.VERIFICADO and self.valor is not None


class Ficha(BaseModel):
    doc_id: str
    valores: dict[str, ValorCampo] = Field(default_factory=dict)
    modo: str = "deterministico"
    criada_em: datetime = Field(default_factory=datetime.now)


# ---------------------------------------------------------------------------- comparação
class Favorabilidade(str, Enum):
    MAIS_FAVORAVEL = "mais_favoravel"
    MENOS_FAVORAVEL = "menos_favoravel"
    EQUIVALENTE = "equivalente"
    NAO_COMPARAVEL = "nao_comparavel"


class LinhaComparacao(BaseModel):
    campo_id: str
    rotulo: str
    grupo: str
    valores: dict[str, ValorCampo]  # doc_id -> valor
    classificacao: dict[str, Favorabilidade]  # doc_id -> favorabilidade
    regra_id: Optional[str] = None
    motivo: str = ""
    diferente: bool = False


class AlertaConformidade(BaseModel):
    regra_id: str
    doc_id: str
    artigo: str
    severidade: str  # "atencao" | "informativo"
    mensagem: str
    fundamento: str = ""
    evidencia: Optional[Evidencia] = None


class Comparacao(BaseModel):
    doc_ids: list[str]
    linhas: list[LinhaComparacao] = Field(default_factory=list)
    alertas: list[AlertaConformidade] = Field(default_factory=list)
    resumo: str = ""
    modo_resumo: str = "deterministico"
    criada_em: datetime = Field(default_factory=datetime.now)


# ---------------------------------------------------------------------------- esquema declarado
class CampoDef(BaseModel):
    id: str
    grupo: str
    rotulo: str
    tipo: str
    onde: str
    pistas: list[str] = Field(default_factory=list)
    rotulos_espec: list[str] = Field(default_factory=list)
    valores: dict[str, str] = Field(default_factory=dict)
    padrao: Optional[str] = None
    instrucao: str = ""


class Esquema(BaseModel):
    versao: int
    grupos: dict[str, str]
    status_cobertura: dict[str, str]
    status_exclusao: dict[str, str]
    campos: list[CampoDef]

    def campo(self, campo_id: str) -> CampoDef:
        for c in self.campos:
            if c.id == campo_id:
                return c
        raise KeyError(campo_id)

    def valores_validos(self, c: CampoDef) -> dict[str, str]:
        if c.tipo == "cobertura":
            return self.status_cobertura
        if c.tipo == "exclusao":
            return self.status_exclusao
        return c.valores


_ESQUEMA: Optional[Esquema] = None


def carregar_esquema() -> Esquema:
    global _ESQUEMA
    if _ESQUEMA is None:
        dados = yaml.safe_load((config.DADOS / "campos.yaml").read_text(encoding="utf-8"))
        _ESQUEMA = Esquema(**dados)
    return _ESQUEMA
