# Arquitetura

## 1. Processos e sockets

```
        ┌──────────────────────────────────────────────────────────┐
        │                        SERVIDOR                          │
        │                                                          │
        │  TCP :9990  (controle)      UDP :9990  (grupo)           │
        │      │                          │                        │
        │      ├── thread sessão/ana      └── thread grupo         │
        │      ├── thread sessão/bruno         (reenvia BCAST)     │
        │      └── thread sessão/carla                             │
        │                                                          │
        │     lista_contatos: dict[nick] → Contato                 │
        │     (nick, ip, porta, conexão)  + threading.Lock         │
        └──────────────────────────────────────────────────────────┘
             ▲   TCP controle          ▲  UDP grupo (BC)
             │   (persistente)         │
      ┌──────┴──────────┐        ┌──────┴──────────┐
      │   CLIENTE ana   │        │  CLIENTE bruno  │
      │  TCP :41231 esc.│        │  TCP :41502 esc.│
      │  UDP :41231 rec.│        │  UDP :41502 rec.│
      └─────────────────┘        └─────────────────┘
              └──────── TCP direto (P2P, sem servidor) ────────┘
```

### Tabela de sockets

| Processo | Socket | Endereço | Papel |
|---|---|---|---|
| servidor | TCP | `0.0.0.0:9990` | canal de controle: `REG`, `LIST`, `BYE`; eventos `ENTROU`/`SAIU` de volta ao cliente |
| servidor | UDP | `0.0.0.0:9990` | recebe `BC`, reenvia `BCAST` a cada contato registrado |
| cliente | TCP | `0.0.0.0:<porta do cliente>` | **listener** para o P2P entrante (é a porta que ele anuncia no `REG`) |
| cliente | UDP | `0.0.0.0:<porta do cliente>` | recebe `BCAST`; é também a origem dos `BC` (permite ao servidor validar remetente) |
| cliente | TCP efêmero | `→ servidor:9990` | sessão de controle |
| cliente | TCP efêmero | `→ par:<porta>` | saída do P2P; identifica-se com `OI <nick>` |

O número de porta do cliente pode ser o mesmo nas duas famílias (TCP e UDP são espaços de porta
independentes). Por padrão usa-se `bind(("0.0.0.0", 0))` e a porta real é descoberta com
`getsockname()` e anunciada no `REG`; `--porta 5001` fixa o valor para quem quiser digitar à mão
durante a apresentação.

## 2. Threads por processo

| Processo | Thread | Bloqueia em | O que faz |
|---|---|---|---|
| servidor | principal | `accept()` da TCP 9990 | cria uma thread de sessão por cliente |
| servidor | sessão (uma por cliente) | `recv()` do socket do cliente | lê `REG`/`LIST`/`BYE`; remove o contato no `finally` e notifica os demais |
| servidor | grupo | `recvfrom()` da UDP 9990 | valida remetente, faz *snapshot* da lista sob lock e envia `BCAST` |
| cliente | principal | `input()` | prompt e interpretação de comandos |
| cliente | sessão de controle | `recv()` do servidor | eventos `ENTROU`/`SAIU`/`ERR` |
| cliente | receptor UDP | `recvfrom()` | mensagens de grupo |
| cliente | listener TCP | `accept()` | aceita P2P entrante → delega a uma thread de conversa |
| cliente | conversa P2P | `recv()` do par | recebe e imprime as mensagens do par |

**Duas regras de I/O que o código respeita e valem explicar:**

1. **Timeout é por chamada, não do socket.** `LeitorLinhas.linha(timeout)` reaplica o `settimeout`
   sempre — inclusive para bloqueante (`None`). Um timeout esquecido no socket faz o primeiro silêncio
   de N segundos virar `socket.timeout` na leitura de fundo, e a thread de controle anuncia "conexão
   encerrada" com o servidor vivo. `socket.timeout` **é** `OSError`: quem trata `OSError` como fim de
   conexão precisa separar os dois casos.
2. **Escrita serializada por conexão.** Duas threads escrevem no mesmo socket de controle (a sessão
   dona respondendo `LIST` e outra sessão empurrando `EVENTO`); sem uma trava no envio, uma linha
   entra no meio da outra e o cliente lê lixo. A trava mora na `Conexao` (`protocolo.py`), junto com
   a montagem da linha.

**Ponto crítico único:** a lista de contatos do servidor (`dict` + `Lock`). O broadcast copia a lista
(`list(contatos.values())`) dentro do lock e envia fora dele — enviar segurando o lock faria um cliente
lento travar o registro dos outros.

## 3. Fluxos

### 3.1 Registro (R2, R3)

```
ana                    SERVIDOR
 │  TCP connect :9990     │
 │─── REG ana 41231 ─────>│  ip = getpeername()  (não confia no cliente)
 │<── OK ana 127.0.0.1 41231 ─│  insere contato; avisa os já presentes
 │<── EVENTO ENTROU ... ──│  (para os outros clientes)
```

Nick repetido → `ERR 409 nick_em_uso` e o cliente escolhe outro. O servidor nunca aceita o IP
declarado pelo cliente: em rede local isso seria falsificação trivial de identidade.

### 3.2 Descoberta da lista (R4)

`/listar` → `LIST` → `LISTA 3` seguido de 3 linhas `CONTATO <nick> <ip> <porta>` e `FIM`. O cliente
guarda a lista para completar `/p2p` e para reconhecer quem mandou cada `BCAST`. A mesma consulta é
feita automaticamente logo após o `REG` (primeiro acesso), como pede o enunciado; os eventos
`ENTROU`/`SAIU` mantêm a lista atualizada depois disso.

### 3.3 Ponto a ponto (R5) — TCP, direto

```
ana (quer falar com bruno)                 bruno
 │── TCP connect 127.0.0.1:41502 ─────────>│  thread listener aceita
 │─── OI ana ─────────────────────────────>│
 │<── OI-OK bruno ─────────────────────────│
 │─── MSG oi, tudo bem? ──────────────────>│
 │<── MSG tudo! ───────────────────────────│
 │─── TCHAU ──────────────────────────────>│  fecha
```

O servidor **não participa**: só forneceu ip/porta no `LIST`. Se bruno já estiver em outra conversa,
responde `OCUPADO` e a conexão é encerrada (escopo: uma conversa por vez).

### 3.4 Grupo (R6) — UDP, via servidor

```
ana          SERVIDOR              bruno            carla
 │── BC ana 7 "reuniao 19h" ──>│
 │                             │── BCAST ana 7 ... ──>│
 │                             │── BCAST ana 7 ... ───────────>│
```

Um datagrama na entrada, N datagramas na saída. O servidor valida que `(ip, porta)` de origem
corresponde ao contato que diz ser o `nick` — sem isso qualquer processo poderia publicar como
qualquer pessoa. Sequência por remetente permite ao cliente detectar lacuna (perda de UDP).

## 4. Máquina de estados do cliente

```
        ┌──────────┐  /p2p nick (conexão aceita)   ┌─────────────┐
        │  LIVRE   │ ────────────────────────────> │ EM_CONVERSA │
        │ (prompt) │ <──────────────────────────── │  (P2P TCP)  │
        └──────────┘      /sair  ou  TCHAU         └─────────────┘
             │  também entra em EM_CONVERSA quando aceita um OI
             │  /grupo e /listar funcionam nos dois estados
             ▼  /sair no prompt → BYE → fecha sockets → processo termina
```

Durante `EM_CONVERSA`, texto sem `/` vai para o par; comandos começam com `/`.

## 5. Verificação (como cada coisa é provada por execução)

| Prova | Ferramenta | O que se vê |
|---|---|---|
| Protocolo de controle e grupo | `testes/teste_protocolo.py` (sockets crus, sem UI) | assert por comando: registro, duplicado, lista, broadcast para 3, spoof recusado |
| P2P direto | teste com dois sockets locais | handshake `OI`/`OI-OK`, `MSG` nos dois sentidos, `OCUPADO` na segunda entrada |
| Demo humana | `demo.sh` (server + 3 clientes em tmux) | roteiro da apresentação |
| Enunciado item a item | `docs/evidencias/checagem-enunciado.md` | R1..R11 com ponteiro para log/teste |

## 6. Decisões registradas

| ADR | Decisão |
|---|---|
| [0001](adr/ADR-0001-protocolo-texto.md) | protocolo de aplicação em texto, uma linha por mensagem |
| [0002](adr/ADR-0002-concorrencia-servidor.md) | servidor concorrente com threads + lock (não `fork`, não `select`) |
| [0003](adr/ADR-0003-tcp-p2p-udp-grupo.md) | TCP no ponto a ponto, UDP no grupo |
| [0004](adr/ADR-0004-sessao-controle-persistente.md) | sessão de controle persistente em vez de requisições curtas |
