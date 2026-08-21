# Transcrições das sessões

Registro das sessões de trabalho assistido que produziram este repositório. Serve para
auditar **como** as decisões foram tomadas — quais alternativas foram levantadas, o que
foi medido antes de escolher, onde houve erro e correção.

| Sessão | Data | Conteúdo |
| --- | --- | --- |
| [Estruturar o projeto](2026-08-15-estruturar-projeto-arc-agi-com-dados-e-plano.md) | 15–16/08/2026 | Desenho do experimento, escolha do modelo, rodadas de calibração |
| [Paralelização e rodada oficial](2026-08-20-experimento-gemini-com-paraleliza-o.md) | 20–21/08/2026 | Pool de chaves de API, execução das 270 tarefas, análise e relatório |

## O que foi preservado e o que não

- **Preservado:** todas as mensagens do usuário e todo o texto das respostas, na ordem
  original, com as chamadas de ferramenta listadas no ponto em que ocorreram.
- **Omitido:** o raciocínio interno do modelo, as saídas de ferramenta (leituras de
  arquivo, resultados de comando) e os blocos de sistema do harness.

A omissão das saídas é o que torna os arquivos legíveis: com elas, as duas sessões
passariam de 300 KB para quase 9 MB, majoritariamente conteúdo de arquivos que já estão
versionados neste mesmo repositório.

**Nenhuma credencial aparece nestes arquivos.** As chaves de API do `.env` foram
conferidas uma a uma contra os transcripts antes da exportação.
