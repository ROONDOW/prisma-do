# -*- coding: utf-8 -*-
"""Cascata de LLMs gratuitos com failover em voo (herdada do D5, Lei do Failover em Voo).

Ordem: Google Gemini -> Groq (gpt-oss-120b) -> NVIDIA NIM. Sem nenhuma chave, `obter()` devolve
None e os agentes usam o caminho determinístico. Nenhuma chave em código: tudo vem do ambiente
(`.env`, fora do git).

Cache em disco (`saida/cache_llm/`): a mesma pergunta devolve a mesma resposta. Isso torna
`avaliar.py` reproduzível e poupa a cota gratuita. Desligue com PRISMA_CACHE_LLM=0.
"""
from __future__ import annotations

import hashlib
import json
import os
import re
import time
from typing import Optional

from prisma import config

_VARIAVEIS = ("GOOGLE_API_KEY", "GROQ_API_KEY", "NVIDIA_API_KEY")


def _gemini():
    from langchain_google_genai import ChatGoogleGenerativeAI

    return ChatGoogleGenerativeAI(model=os.environ.get("GEMINI_MODEL", "gemini-flash-latest"), temperature=0,
                                  google_api_key=os.environ["GOOGLE_API_KEY"], max_retries=1, timeout=120)


def _groq():
    from langchain_groq import ChatGroq

    return ChatGroq(model=os.environ.get("GROQ_MODEL", "openai/gpt-oss-120b"), temperature=0,
                    api_key=os.environ["GROQ_API_KEY"], max_retries=1, timeout=120)


def _nvidia():
    from langchain_nvidia_ai_endpoints import ChatNVIDIA

    return ChatNVIDIA(model=os.environ.get("NVIDIA_MODEL", "deepseek-ai/deepseek-v4-flash-0731"), temperature=0,
                      api_key=os.environ["NVIDIA_API_KEY"], max_tokens=4096)


CASCATA = [("Google Gemini", "GOOGLE_API_KEY", _gemini), ("Groq", "GROQ_API_KEY", _groq),
           ("NVIDIA NIM", "NVIDIA_API_KEY", _nvidia)]


def texto_da_resposta(msg) -> str:
    conteudo = getattr(msg, "content", msg)
    if isinstance(conteudo, str):
        return conteudo
    if isinstance(conteudo, list):
        return "\n".join((b.get("text", "") if isinstance(b, dict) else str(b)) for b in conteudo)
    return str(conteudo)


def extrair_json(texto: str) -> Optional[dict]:
    """Primeiro objeto JSON da resposta (tolera cerca ```json e texto em volta)."""
    texto = re.sub(r"```(?:json)?", "", texto or "")
    inicio = texto.find("{")
    while inicio != -1:
        profundidade = 0
        em_string = escape = False
        for i in range(inicio, len(texto)):
            ch = texto[i]
            if em_string:
                escape = (ch == "\\" and not escape)
                if ch == '"' and not escape:
                    em_string = False
                continue
            if ch == '"':
                em_string = True
            elif ch == "{":
                profundidade += 1
            elif ch == "}":
                profundidade -= 1
                if profundidade == 0:
                    try:
                        return json.loads(texto[inicio:i + 1])
                    except json.JSONDecodeError:
                        break
        inicio = texto.find("{", inicio + 1)
    return None


class Cascata:
    def __init__(self, provedores: list[tuple[str, object]]):
        self.provedores = provedores
        self.mortos: set[str] = set()
        self.pausa_ate: dict[str, float] = {}
        self.ultimo_provedor = "nenhum"
        self.chamadas = 0

    @property
    def descricao(self) -> str:
        return " → ".join(n for n, _ in self.provedores)

    def _cache(self, chave: str) -> Optional[dict]:
        if os.environ.get("PRISMA_CACHE_LLM", "1") == "0":
            return None
        arq = config.SAIDA / "cache_llm" / f"{chave}.json"
        return json.loads(arq.read_text(encoding="utf-8")) if arq.exists() else None

    def _gravar(self, chave: str, dados: dict) -> None:
        if os.environ.get("PRISMA_CACHE_LLM", "1") == "0":
            return
        pasta = config.SAIDA / "cache_llm"
        pasta.mkdir(parents=True, exist_ok=True)
        (pasta / f"{chave}.json").write_text(json.dumps(dados, ensure_ascii=False), encoding="utf-8")

    def perguntar(self, sistema: str, usuario: str) -> tuple[str, str]:
        """Devolve (texto, provedor). Troca de provedor na mesma chamada se um falhar."""
        chave = hashlib.sha256((sistema + "\x00" + usuario).encode("utf-8")).hexdigest()[:32]
        em_cache = self._cache(chave)
        if em_cache:
            self.ultimo_provedor = em_cache["provedor"] + " (cache)"
            return em_cache["texto"], self.ultimo_provedor
        from langchain_core.messages import HumanMessage, SystemMessage

        erro_final: Optional[Exception] = None
        for nome, modelo in self.provedores:
            # erro transitório (cota por minuto, sobrecarga) põe o provedor em pausa, não o mata;
            # erro persistente (chave inválida, modelo inexistente) mata pelo resto da execução
            if nome in self.mortos or self.pausa_ate.get(nome, 0) > time.time():
                continue
            for tentativa in range(3):
                try:
                    self.chamadas += 1
                    resposta = modelo.invoke([SystemMessage(content=sistema), HumanMessage(content=usuario)])
                    texto = texto_da_resposta(resposta)
                    if not texto.strip():
                        raise ValueError("resposta vazia")
                    self.ultimo_provedor = nome
                    if extrair_json(texto) is not None or "{" not in usuario:
                        self._gravar(chave, {"provedor": nome, "texto": texto, "em": time.time()})
                    return texto, nome
                except Exception as erro:
                    erro_final = erro
                    mensagem = str(erro).lower()
                    transitorio = any(s in mensagem for s in ("429", "rate", "503", "unavailable", "overloaded",
                                                              "timeout", "timed out", "resposta vazia", "resource"))
                    if transitorio and tentativa < 2:
                        time.sleep(10 * (tentativa + 1))
                        continue
                    if transitorio:
                        self.pausa_ate[nome] = time.time() + 90
                    else:
                        self.mortos.add(nome)
                    break
            print(f"[LLM] {nome} falhou ({erro_final.__class__.__name__}); passando ao próximo provedor gratuito.")
        raise RuntimeError(f"todos os provedores gratuitos falharam: {erro_final}")


def ha_chave() -> bool:
    return any(os.environ.get(v) for v in _VARIAVEIS)


def obter() -> Optional[Cascata]:
    config.carregar_env() if os.environ.get("PRISMA_SEM_ENV") != "1" else None
    provedores = []
    for nome, variavel, construtor in CASCATA:
        if not os.environ.get(variavel):
            continue
        try:
            provedores.append((nome, construtor()))
        except Exception as erro:
            print(f"[LLM] {nome} indisponível ({erro.__class__.__name__}).")
    return Cascata(provedores) if provedores else None
