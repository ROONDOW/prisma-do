# Roteiro da apresentação — InsurMinds_Projeto_Final.mp4

Roteiro de apoio para a gravação do grupo: até 5 minutos (a fala abaixo dura cerca de 4min30s),
cobrindo problema, arquitetura, funcionamento e resultados, como pede o edital.
Números conferidos contra `saida/avaliacao_*.json` e `saida/experimento_ensino.json`.

**Antes de gravar**
- `streamlit run streamlit_app.py` e abra `http://localhost:8501`.
- O banco deve estar sem ensinamentos (aba Ficha → "O que o sistema já aprendeu (0)").
- Se a IA gratuita estiver lenta, desligue "Usar IA gratuita" na barra lateral antes de comparar:
  o resumo sai na hora pelas regras.
- Deixe copiado o trecho da cena 6:
  `As disposições deste contrato de seguro aplicam-se exclusivamente a danos ocorridos e reclamados em qualquer parte do mundo, com exceção a Estados Unidos, Canadá, Irã e Cuba`

| # | Tempo | Na tela | Fala |
|---|---|---|---|
| 1 | 0:00–0:25 | Slide 1–2 | Uma apólice de seguro D&O, o seguro que protege diretores e conselheiros, pode ter mais de setenta páginas. Comparar duas propostas cláusula por cláusula toma horas de um especialista. E os detalhes decidem tudo: a exclusão por fraude vale antes ou só depois da sentença? A defesa é adiantada ou só reembolsada no fim? Um erro de leitura aparece no pior momento: no meio de um processo. |
| 2 | 0:25–0:50 | Slide 3 | O PRISMA D&O lê apólices em PDF, escaneadas ou em foto, extrai trinta e seis campos, compara as propostas e aponta indícios de desconformidade com a Circular SUSEP 637. Com uma regra que não se negocia: nenhum número aparece na tela sem o trecho e a página de onde ele saiu. |
| 3 | 0:50–1:40 | Slide 4 | São nove agentes em dois fluxos no LangGraph. A Recepcionista valida o arquivo; o Leitor extrai o texto e usa OCR gratuito só nas páginas que são imagem; o Segmentador separa as cláusulas; o Extrator lê com regras declaradas, que funcionam sem chave de API, e com IA gratuita em cascata — Gemini, Groq e NVIDIA. Tudo passa pelo Verificador: o trecho existe na página, fala do assunto, contém o número e não é uma instrução maliciosa escondida no documento. Depois o Comparador aplica regras de favorabilidade, a Conformidade confere a norma e o Relator gera o resumo e o PDF. |
| 4 | 1:40–2:20 | App: Documentos → Ficha (Aurora) → Evidência → Ver página original | Na prática: três cotações fictícias para a mesma empresa — uma em PDF, uma escaneada e torta, uma em foto. Cada valor da ficha tem a sua evidência: o trecho literal e a página original. Se o trecho não existisse, o valor não apareceria. |
| 5 | 2:20–3:00 | App: Comparar → quadro → "Por que essa classificação?" → Pontos de atenção | No quadro, verde é mais favorável ao segurado e vermelho, menos. A Aurora tem o maior limite; a Boreal só reembolsa a defesa no fim. Cada cor explica o critério. E a conformidade encontrou um problema: a cotação Cruzeiro não indica prazo adicional para reclamações, como exige o artigo dezenove. |
| 6 | 3:00–3:45 | App: Ficha → berkley_do.pdf → Âmbito geográfico → 🎓 Ensinar (página 17, trecho, "mundial exceto EUA/Canadá") → depois berkley_do_v2017_2023.pdf → "Aplicar ensinamentos" | Em seguradora nova, as regras não reconhecem tudo. Em vez de inventar, o sistema diz "não encontrado" — e o corretor ensina: aponta o trecho e o valor. O Verificador confere antes de aceitar. Aqui, na outra versão da mesma seguradora, o campo aparece preenchido sozinho, marcado como aprendido. Cada seguradora nova é ensinada uma vez. |
| 7 | 3:45–4:20 | Slide 8 ou aba Qualidade | Medimos tudo contra um gabarito anotado à mão, com duzentos e oitenta e um campos. Sem chave de API, quase noventa e oito por cento de acerto no desenvolvimento e setenta e seis em documentos que o sistema nunca tinha visto; com a IA gratuita, setenta e nove. Três ensinamentos corrigiram seis campos — três deles em outros documentos — sem nenhum valor errado novo. O OCR erra três centésimos por cento dos caracteres, e quinze de quinze tentativas de injeção de prompt foram barradas. |
| 8 | 4:20–4:35 | Slide 12 | O PRISMA não substitui o especialista nem recomenda apólice: mostra as diferenças, com fundamento, e deixa cada número conferível. Código aberto, relatório técnico e instruções estão no GitHub. |
