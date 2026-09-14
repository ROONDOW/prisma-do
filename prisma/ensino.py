# -*- coding: utf-8 -*-
"""Memória de ensinamentos — o corretor ensina, o Verificador continua mandando.

Quando a ficha diz "não encontrado", o corretor aponta o trecho e o valor. Isso vira três coisas:
  1. o valor entra na ficha deste documento (depois de o Verificador conferir que o trecho existe
     na página, contém o número e não é instrução escondida);
  2. um ensinamento guardado no armazém, que é reaplicado a OUTROS documentos onde a mesma
     redação aparece (típico de outra versão das condições gerais da mesma seguradora);
  3. exemplo para a IA: o trecho ensinado entra na busca de cláusulas e no pedido ao modelo.

Regras de segurança (ver testes):
- ensinamento só é gravado se o trecho for aprovado; trecho com instrução dirigida a IA nunca vira
  exemplo (seria injeção de prompt persistente em todos os documentos futuros);
- reaplicar exige semelhança >= 0,90 com o trecho ensinado e NENHUMA palavra de exceção/negação
  nova ("salvo", "exceto", "não"...): a outra versão pode ter mudado justamente o que importa;
- reaplicar só preenche lacuna: nunca troca um valor já verificado por outro método;
- no próprio documento ensinado, a palavra do corretor prevalece.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from difflib import SequenceMatcher
from typing import Optional

from prisma import config, normalizar
from prisma.agentes import verificador
from prisma.modelos import CampoDef, Documento, Evidencia, StatusEvidencia, ValorCampo, carregar_esquema

SEMELHANCA_MINIMA_REUSO = 0.90
# Palavra que, se aparecer só na versão nova, pode inverter o sentido do trecho ensinado.
_RE_DIFERENCA_PERIGOSA = re.compile(r"^(nao|salvo|exceto|excecao|excetuad|ressalv|exclu|sem|vedad|desde|apenas|somente|limitad|nunca)")
TIPOS_NUMERICOS = ("dinheiro", "data", "duracao", "periodo")


@dataclass
class Ensinamento:
    doc_id: str
    doc_nome: str
    seguradora: str
    campo_id: str
    valor: object
    valor_texto: str
    trecho: str
    pagina: int
    id: Optional[int] = None
    criado_em: Optional[float] = None


class EnsinamentoRecusado(ValueError):
    """O trecho ou o valor não passaram na conferência; nada foi gravado."""


def interpretar_valor(campo: CampoDef, bruto) -> tuple[object, str]:
    """Texto digitado pelo corretor → valor normalizado (mesmas regras usadas para a IA)."""
    from prisma.agentes.extrator import _normalizar_llm

    return _normalizar_llm(campo, bruto)


def conferir(doc: Documento, campo: CampoDef, valor, valor_texto: str, trecho: str, pagina: int,
             metodo: str, observacao: str) -> ValorCampo:
    """Verificador para valor confirmado por pessoa: o trecho precisa existir, ter tamanho de prova,
    não conter instrução a IA e conter o número. O assunto e a coerência do valor são julgamento do
    corretor, que conhece a redação da seguradora melhor que as pistas genéricas."""
    trecho = (trecho or "").strip()
    if valor is None:
        raise EnsinamentoRecusado("valor não reconhecido para este campo")
    if valor in ("nao_prevista", "nao_excluido"):
        raise EnsinamentoRecusado("ausência não se ensina com trecho: deixe o campo como não encontrado")
    if verificador.instrucao_suspeita(trecho):
        raise EnsinamentoRecusado("o trecho contém instrução dirigida a IA; não pode virar exemplo")
    if len(normalizar.texto_busca(trecho)) < verificador.TAMANHO_MINIMO_TRECHO:
        raise EnsinamentoRecusado("trecho curto demais para servir de prova")
    achada, sim = verificador.localizar(doc, trecho, pagina)
    if achada is None or sim < config.SIMILARIDADE_MINIMA_TRECHO:
        raise EnsinamentoRecusado(f"trecho não encontrado no documento (semelhança máxima {100 * sim:.0f}%); "
                                  "copie o texto exatamente como está na página")
    if not verificador._numero_confere(campo, valor, trecho):
        raise EnsinamentoRecusado("o número informado não aparece no trecho")
    if achada != pagina:
        observacao = (observacao + f" (página corrigida de {pagina} para {achada})").strip()
    return ValorCampo(campo_id=campo.id, valor=valor, valor_texto=valor_texto, status=StatusEvidencia.VERIFICADO,
                      evidencia=Evidencia(trecho=trecho, pagina=achada, similaridade=round(sim, 3)),
                      metodo=metodo, observacao=observacao)


def ensinar(doc: Documento, campo_id: str, valor_bruto, trecho: str, pagina: int) -> tuple[ValorCampo, Ensinamento]:
    """Confere e devolve (valor para a ficha, ensinamento para gravar). Levanta EnsinamentoRecusado."""
    campo = carregar_esquema().campo(campo_id)
    valor, valor_texto = interpretar_valor(campo, valor_bruto)
    v = conferir(doc, campo, valor, valor_texto, trecho, pagina, "humano", "ensinado pelo corretor")
    lic = Ensinamento(doc_id=doc.id, doc_nome=doc.nome, seguradora=str(doc.metadados.get("seguradora") or ""),
                      campo_id=campo_id, valor=valor, valor_texto=valor_texto, trecho=v.evidencia.trecho,
                      pagina=v.evidencia.pagina)
    return v, lic


# ============================================================================ reaplicar
def _forma(palavra: str) -> str:
    """Forma de comparação: sem pontuação nas pontas, e todo número vira '#' (o valor muda entre
    apólices; a redação em volta é o que identifica a cláusula)."""
    p = normalizar.texto_busca(palavra).strip(".,;:()\"'")
    return "#" if re.fullmatch(r"(r\$)?[0-9][0-9.,/]*", p) else p


def _palavras(texto: str) -> list[tuple[str, str]]:
    """(palavra original, forma de comparação) — permite recortar o trecho com a grafia da página."""
    saida = []
    for bruto in re.sub(r"(\w)-\s*\n\s*(\w)", r"\1\2", texto).split():
        forma = _forma(bruto)
        if forma:
            saida.append((bruto, forma))
    return saida


def melhor_janela(trecho: str, doc: Documento) -> tuple[float, Optional[int], str, list[str]]:
    """Janela do documento mais parecida com o trecho ensinado.
    Devolve (semelhança, página, texto recortado com a grafia original, palavras novas na janela)."""
    alvo = [f for f in (_forma(p) for p in trecho.split()) if f]
    if not alvo:
        return 0.0, None, "", []
    inicio_alvo = set(alvo[: max(1, len(alvo) // 4)])
    melhor = (0.0, None, "", [])
    for pag in doc.paginas:
        palavras = _palavras(pag.texto)
        normas = [n for _, n in palavras]
        janela = int(len(alvo) * 1.3) + 2
        for i, n in enumerate(normas):
            if n not in inicio_alvo:
                continue
            cand = normas[i:i + janela]
            blocos = [b for b in SequenceMatcher(None, alvo, cand, autojunk=False).get_matching_blocks() if b.size]
            if not blocos:
                continue
            sim = sum(b.size for b in blocos) / len(alvo)
            if sim <= melhor[0]:
                continue
            ini, fim = blocos[0].b, blocos[-1].b + blocos[-1].size
            casados_cand = {k for b in blocos for k in range(b.b, b.b + b.size)}
            casados_alvo = {k for b in blocos for k in range(b.a, b.a + b.size)}
            # palavras que mudaram nos dois sentidos: acrescentadas na versão nova ou retiradas dela
            novas = [cand[k] for k in range(ini, fim) if k not in casados_cand] + \
                    [alvo[k] for k in range(len(alvo)) if k not in casados_alvo]
            texto = " ".join(p for p, _ in palavras[i + ini:i + fim])
            melhor = (sim, pag.numero, texto, novas)
            if sim >= 0.999 and not novas:
                return melhor
    return melhor


def _reler_numero(campo: CampoDef, texto: str):
    if campo.tipo == "dinheiro":
        return normalizar.dinheiro(texto)
    if campo.tipo == "data":
        return normalizar.data(texto)
    if campo.tipo == "duracao":
        return normalizar.duracao_dias(texto)
    if campo.tipo == "periodo":
        ds = normalizar.datas(texto)
        return {"inicio": ds[0], "fim": ds[1]} if len(ds) >= 2 else None
    return None


def reaplicar(doc: Documento, valores: dict[str, ValorCampo], licoes: list[Ensinamento]) -> tuple[dict[str, ValorCampo], list[dict]]:
    """Aplica ensinamentos à ficha de `doc`. Devolve (valores atualizados, relatório do que foi aplicado)."""
    from prisma.agentes.extrator import texto_do_valor

    esq = carregar_esquema()
    novos, relatorio = dict(valores), []
    # 1) ensinamentos do próprio documento: a palavra do corretor prevalece
    for lic in [l for l in licoes if l.doc_id == doc.id]:
        campo = esq.campo(lic.campo_id)
        try:
            novos[lic.campo_id] = conferir(doc, campo, lic.valor, lic.valor_texto, lic.trecho, lic.pagina,
                                           "humano", "ensinado pelo corretor")
            relatorio.append({"campo": lic.campo_id, "origem": "este documento", "valor": lic.valor})
        except EnsinamentoRecusado:
            continue
    # 2) ensinamentos de outros documentos: só preenchem lacuna, e só com a mesma redação
    outros = sorted([l for l in licoes if l.doc_id != doc.id],
                    key=lambda l: l.seguradora != doc.metadados.get("seguradora"))  # mesma seguradora primeiro
    for lic in outros:
        atual = novos.get(lic.campo_id)
        if atual is not None and atual.status in (StatusEvidencia.VERIFICADO, StatusEvidencia.NA_ESPECIFICACAO):
            continue
        campo = esq.campo(lic.campo_id)
        sim, pagina, janela, palavras_novas = melhor_janela(lic.trecho, doc)
        if pagina is None or sim < SEMELHANCA_MINIMA_REUSO:
            continue
        perigosas = [p for p in palavras_novas if _RE_DIFERENCA_PERIGOSA.match(p)]
        if perigosas:
            relatorio.append({"campo": lic.campo_id, "origem": lic.doc_nome, "recusado": f"redação mudou: {perigosas[:3]}"})
            continue
        if campo.tipo in TIPOS_NUMERICOS:
            valor = _reler_numero(campo, janela)  # o número é deste documento, não do ensinado
            valor_texto = texto_do_valor(campo, valor) if valor is not None else ""
        else:
            valor, valor_texto = lic.valor, lic.valor_texto
        try:
            v = conferir(doc, campo, valor, valor_texto, janela, pagina, f"aprendido:{lic.doc_nome}",
                         f"mesma redação ensinada em {lic.doc_nome}, p. {lic.pagina} (semelhança {100 * sim:.0f}%)")
        except EnsinamentoRecusado:
            continue
        novos[lic.campo_id] = v
        relatorio.append({"campo": lic.campo_id, "origem": lic.doc_nome, "valor": valor, "pagina": pagina,
                          "semelhanca": round(sim, 3)})
    return novos, relatorio


def exemplos_para_ia(licoes: list[Ensinamento], doc_id: str, por_campo: int = 2) -> dict[str, list[Ensinamento]]:
    """Ensinamentos de outros documentos, por campo, para a busca de cláusulas e o pedido ao modelo."""
    saida: dict[str, list[Ensinamento]] = {}
    for lic in licoes:
        if lic.doc_id == doc_id or verificador.instrucao_suspeita(lic.trecho):
            continue
        lista = saida.setdefault(lic.campo_id, [])
        if len(lista) < por_campo:
            lista.append(lic)
    return saida
