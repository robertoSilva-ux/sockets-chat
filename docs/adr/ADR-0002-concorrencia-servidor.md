# ADR-0002 — Servidor concorrente com threads e um lock

**Status:** aceita · **Data:** 2026-11-13

## Contexto

O servidor precisa de N clientes simultâneos (R1) e de um estado compartilhado entre eles: a lista de
contatos (R3) alimenta `LIST` (R4) e o reenvio do grupo (R6). O exemplo da aula
(`ServidorTCPConcorrente.py`) resolve com `os.fork()`, e é justamente aí que a decisão fica
interessante.

## Alternativas

| Alternativa | A favor | Contra |
|---|---|---|
| **Threads + `threading.Lock`** | estado compartilhado direto (`dict` na memória do processo); envio bloqueante por conexão sem travar os demais; código curto e legível | precisa identificar e proteger todos os pontos de acesso à lista; encerramento exige cuidado (threads *daemon*) |
| `fork` (como no exemplo da aula) | isolamento total; nenhum risco de corrida | **cada filho tem cópia própria da lista** — o registro de um cliente não aparece no outro, então a lista de contatos exigiria memória compartilhada ou fila de mensagens/pipe; a contagem `i += 1` do exemplo só existe no processo pai (o filho imprime uma cópia); não porta para Windows |
| `select`/`poll` (single-thread) | um processo, sem lock, sem condição de corrida; escala para muitos sockets | um `send` bloqueante para um cliente lento para todos; o fluxo fica dominado pela máquina de estados de I/O e deixa de ser apresentável em 10 minutos |

## Decisão

Uma thread por sessão de controle, uma thread para o socket UDP do grupo, e a lista de contatos como
`dict` protegido por um `threading.Lock`. Regra de ouro: **o lock protege a estrutura, não a
comunicação** — o broadcast tira um *snapshot* da lista dentro do lock (`list(contatos.values())`) e
envia os datagramas fora dele.

## Consequências

- Positivas: o estado do servidor é único e coerente; adicionar um canal novo (ex.: mensagens
  privadas via servidor) é uma thread, não uma reescrita.
- Negativas: o registro/remoção de contatos precisa acontecer sempre sob o lock (senão `dict` corrompe
  ou `RuntimeError: dictionary changed size during iteration`); queda de conexão tem que passar por
  `try/finally` para não deixar contato fantasma na lista.
- Explícito: **não se usa `asyncio`** — mudaria o modelo mental que a disciplina está ensinando
  (sockets bloqueantes) e não é necessário para 3–5 clientes em laboratório.
