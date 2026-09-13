# -*- coding: utf-8 -*-
"""Armazém SQLite do PRISMA D&O — armazenamento estruturado (etapa 4 do edital).

Tabelas: documentos · paginas (+ paginas_fts, busca textual FTS5) · clausulas · fichas ·
comparacoes · rastro (uma linha por passo de agente, com duração e detalhe).
O arquivo original fica em `saida/arquivos/<sha256>.<ext>` para a interface mostrar a página.
Reprocessar o mesmo arquivo (mesmo SHA-256) reaproveita leitura e segmentação.
"""
from __future__ import annotations

import json
import sqlite3
import time
from contextlib import contextmanager
from pathlib import Path
from typing import Iterator, Optional

from prisma import config
from prisma.modelos import Clausula, Comparacao, Documento, Ficha, Pagina

ESQUEMA_SQL = """
CREATE TABLE IF NOT EXISTS documentos (
    id TEXT PRIMARY KEY, nome TEXT NOT NULL, sha256 TEXT NOT NULL UNIQUE, tipo_arquivo TEXT NOT NULL,
    ficticio INTEGER NOT NULL DEFAULT 0, metadados TEXT NOT NULL DEFAULT '{}', criado_em REAL NOT NULL
);
CREATE TABLE IF NOT EXISTS paginas (
    doc_id TEXT NOT NULL REFERENCES documentos(id) ON DELETE CASCADE, numero INTEGER NOT NULL,
    texto TEXT NOT NULL, metodo TEXT NOT NULL, confianca_ocr REAL, PRIMARY KEY (doc_id, numero)
);
CREATE VIRTUAL TABLE IF NOT EXISTS paginas_fts USING fts5(doc_id UNINDEXED, numero UNINDEXED, texto,
    tokenize = 'unicode61 remove_diacritics 2');
CREATE TABLE IF NOT EXISTS clausulas (
    id TEXT PRIMARY KEY, doc_id TEXT NOT NULL REFERENCES documentos(id) ON DELETE CASCADE,
    numero TEXT, titulo TEXT NOT NULL, nivel INTEGER, pagina_inicio INTEGER, pagina_fim INTEGER,
    secao TEXT, texto TEXT NOT NULL, mapa_paginas TEXT NOT NULL DEFAULT '[]'
);
CREATE TABLE IF NOT EXISTS fichas (
    doc_id TEXT NOT NULL REFERENCES documentos(id) ON DELETE CASCADE, modo TEXT NOT NULL,
    conteudo TEXT NOT NULL, criada_em REAL NOT NULL, PRIMARY KEY (doc_id, modo)
);
CREATE TABLE IF NOT EXISTS comparacoes (
    id INTEGER PRIMARY KEY AUTOINCREMENT, doc_ids TEXT NOT NULL, conteudo TEXT NOT NULL, criada_em REAL NOT NULL
);
CREATE TABLE IF NOT EXISTS rastro (
    id INTEGER PRIMARY KEY AUTOINCREMENT, execucao TEXT NOT NULL, agente TEXT NOT NULL, doc_id TEXT,
    inicio REAL NOT NULL, duracao_s REAL NOT NULL, detalhe TEXT NOT NULL DEFAULT '{}'
);
CREATE INDEX IF NOT EXISTS idx_clausulas_doc ON clausulas(doc_id);
CREATE INDEX IF NOT EXISTS idx_rastro_execucao ON rastro(execucao);
"""


class Armazem:
    def __init__(self, caminho: Optional[Path] = None):
        self.caminho = Path(caminho or config.BANCO)
        self.caminho.parent.mkdir(parents=True, exist_ok=True)
        self.pasta_arquivos = self.caminho.parent / "arquivos"
        self.pasta_arquivos.mkdir(parents=True, exist_ok=True)
        with self._conexao() as c:
            c.executescript(ESQUEMA_SQL)

    @contextmanager
    def _conexao(self) -> Iterator[sqlite3.Connection]:
        con = sqlite3.connect(self.caminho, timeout=30)
        con.execute("PRAGMA foreign_keys = ON")
        try:
            yield con
            con.commit()
        finally:
            con.close()

    # ------------------------------------------------------------------ documentos
    def salvar_documento(self, doc: Documento, conteudo: bytes, clausulas: list[Clausula]) -> None:
        (self.pasta_arquivos / f"{doc.sha256}.{doc.tipo_arquivo}").write_bytes(conteudo)
        with self._conexao() as c:
            c.execute("DELETE FROM documentos WHERE id = ?", (doc.id,))
            c.execute("DELETE FROM paginas_fts WHERE doc_id = ?", (doc.id,))
            c.execute("INSERT INTO documentos VALUES (?,?,?,?,?,?,?)",
                      (doc.id, doc.nome, doc.sha256, doc.tipo_arquivo, int(doc.ficticio),
                       json.dumps(doc.metadados, ensure_ascii=False), time.time()))
            c.executemany("INSERT INTO paginas VALUES (?,?,?,?,?)",
                          [(doc.id, p.numero, p.texto, p.metodo.value, p.confianca_ocr) for p in doc.paginas])
            c.executemany("INSERT INTO paginas_fts VALUES (?,?,?)", [(doc.id, p.numero, p.texto) for p in doc.paginas])
            c.executemany("INSERT INTO clausulas VALUES (?,?,?,?,?,?,?,?,?,?)",
                          [(k.id, k.doc_id, k.numero, k.titulo, k.nivel, k.pagina_inicio, k.pagina_fim,
                            k.secao, k.texto, json.dumps(k.mapa_paginas)) for k in clausulas])

    def atualizar_metadados(self, doc_id: str, metadados: dict) -> None:
        with self._conexao() as c:
            c.execute("UPDATE documentos SET metadados = ? WHERE id = ?", (json.dumps(metadados, ensure_ascii=False), doc_id))

    def existe(self, doc_id: str) -> bool:
        with self._conexao() as c:
            return c.execute("SELECT 1 FROM documentos WHERE id = ?", (doc_id,)).fetchone() is not None

    def documento(self, doc_id: str) -> Optional[Documento]:
        with self._conexao() as c:
            linha = c.execute("SELECT id, nome, sha256, tipo_arquivo, ficticio, metadados FROM documentos WHERE id = ?",
                              (doc_id,)).fetchone()
            if not linha:
                return None
            paginas = [Pagina(numero=n, texto=t, metodo=m, confianca_ocr=cf) for n, t, m, cf in
                       c.execute("SELECT numero, texto, metodo, confianca_ocr FROM paginas WHERE doc_id = ? "
                                 "ORDER BY numero", (doc_id,))]
        return Documento(id=linha[0], nome=linha[1], sha256=linha[2], tipo_arquivo=linha[3],
                         ficticio=bool(linha[4]), metadados=json.loads(linha[5]), paginas=paginas)

    def documentos(self) -> list[dict]:
        with self._conexao() as c:
            linhas = c.execute("SELECT d.id, d.nome, d.tipo_arquivo, d.ficticio, d.metadados, d.criado_em, "
                               "(SELECT COUNT(*) FROM paginas p WHERE p.doc_id = d.id), "
                               "(SELECT COUNT(*) FROM paginas p WHERE p.doc_id = d.id AND p.metodo = 'ocr') "
                               "FROM documentos d ORDER BY d.criado_em").fetchall()
        return [{"id": i, "nome": n, "tipo_arquivo": t, "ficticio": bool(f), "metadados": json.loads(m),
                 "criado_em": cr, "paginas": np, "paginas_ocr": no} for i, n, t, f, m, cr, np, no in linhas]

    def remover(self, doc_id: str) -> None:
        with self._conexao() as c:
            c.execute("DELETE FROM paginas_fts WHERE doc_id = ?", (doc_id,))
            c.execute("DELETE FROM documentos WHERE id = ?", (doc_id,))

    def arquivo(self, doc: Documento) -> Optional[bytes]:
        caminho = self.pasta_arquivos / f"{doc.sha256}.{doc.tipo_arquivo}"
        return caminho.read_bytes() if caminho.exists() else None

    def clausulas(self, doc_id: str) -> list[Clausula]:
        with self._conexao() as c:
            linhas = c.execute("SELECT id, doc_id, numero, titulo, nivel, pagina_inicio, pagina_fim, secao, texto, "
                               "mapa_paginas FROM clausulas WHERE doc_id = ? ORDER BY id", (doc_id,)).fetchall()
        return [Clausula(id=a, doc_id=b, numero=cn, titulo=d, nivel=e, pagina_inicio=f, pagina_fim=g, secao=h or "",
                         texto=i, mapa_paginas=json.loads(j)) for a, b, cn, d, e, f, g, h, i, j in linhas]

    def buscar_texto(self, consulta: str, doc_ids: Optional[list[str]] = None, limite: int = 8) -> list[dict]:
        """Busca FTS5 (sem acento) nas páginas. A consulta vira termos OR entre aspas: nenhum
        caractere do usuário é interpretado como operador FTS."""
        termos = [t for t in "".join(ch if ch.isalnum() else " " for ch in consulta).split() if len(t) > 2]
        if not termos:
            return []
        expressao = " OR ".join(f'"{t}"' for t in termos[:12])
        sql = "SELECT doc_id, numero, snippet(paginas_fts, 2, '[', ']', ' … ', 18), bm25(paginas_fts) " \
              "FROM paginas_fts WHERE paginas_fts MATCH ?"
        params: list = [expressao]
        if doc_ids:
            sql += f" AND doc_id IN ({','.join('?' * len(doc_ids))})"
            params += doc_ids
        sql += " ORDER BY bm25(paginas_fts) LIMIT ?"
        params.append(limite)
        with self._conexao() as c:
            return [{"doc_id": d, "pagina": n, "trecho": s, "nota": b} for d, n, s, b in c.execute(sql, params)]

    # ------------------------------------------------------------------ fichas e comparações
    def salvar_ficha(self, ficha: Ficha) -> None:
        with self._conexao() as c:
            c.execute("INSERT OR REPLACE INTO fichas VALUES (?,?,?,?)",
                      (ficha.doc_id, ficha.modo, ficha.model_dump_json(), time.time()))

    def ficha(self, doc_id: str, modo: Optional[str] = None) -> Optional[Ficha]:
        with self._conexao() as c:
            if modo:
                linha = c.execute("SELECT conteudo FROM fichas WHERE doc_id = ? AND modo = ?", (doc_id, modo)).fetchone()
            else:
                linha = c.execute("SELECT conteudo FROM fichas WHERE doc_id = ? ORDER BY criada_em DESC LIMIT 1",
                                  (doc_id,)).fetchone()
        return Ficha.model_validate_json(linha[0]) if linha else None

    def salvar_comparacao(self, comp: Comparacao) -> int:
        with self._conexao() as c:
            cur = c.execute("INSERT INTO comparacoes (doc_ids, conteudo, criada_em) VALUES (?,?,?)",
                            (json.dumps(comp.doc_ids), comp.model_dump_json(), time.time()))
            return int(cur.lastrowid)

    def comparacao(self, comp_id: int) -> Optional[Comparacao]:
        with self._conexao() as c:
            linha = c.execute("SELECT conteudo FROM comparacoes WHERE id = ?", (comp_id,)).fetchone()
        return Comparacao.model_validate_json(linha[0]) if linha else None

    # ------------------------------------------------------------------ rastro
    def registrar(self, execucao: str, agente: str, doc_id: Optional[str], inicio: float, detalhe: dict) -> None:
        with self._conexao() as c:
            c.execute("INSERT INTO rastro (execucao, agente, doc_id, inicio, duracao_s, detalhe) VALUES (?,?,?,?,?,?)",
                      (execucao, agente, doc_id, inicio, round(time.time() - inicio, 3),
                       json.dumps(detalhe, ensure_ascii=False, default=str)))

    def rastro(self, execucao: Optional[str] = None, limite: int = 200) -> list[dict]:
        with self._conexao() as c:
            if execucao:
                linhas = c.execute("SELECT execucao, agente, doc_id, inicio, duracao_s, detalhe FROM rastro "
                                   "WHERE execucao = ? ORDER BY id", (execucao,)).fetchall()
            else:
                linhas = c.execute("SELECT execucao, agente, doc_id, inicio, duracao_s, detalhe FROM rastro "
                                   "ORDER BY id DESC LIMIT ?", (limite,)).fetchall()
        return [{"execucao": e, "agente": a, "doc_id": d, "inicio": i, "duracao_s": s, "detalhe": json.loads(dt)}
                for e, a, d, i, s, dt in linhas]
