# -*- coding: utf-8 -*-
import os
import sys
from pathlib import Path

RAIZ = Path(__file__).resolve().parent
sys.path.insert(0, str(RAIZ))

# Os testes nunca chamam LLM de verdade: sem chaves no ambiente, o sistema cai no modo
# determinístico. Testes que precisam de LLM injetam um falso.
for chave in ("GOOGLE_API_KEY", "GROQ_API_KEY", "NVIDIA_API_KEY"):
    os.environ.pop(chave, None)
os.environ["PRISMA_SEM_ENV"] = "1"
