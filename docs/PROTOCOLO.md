# Protocolo de aplicação (contrato de fio)

> Transcrições neste documento são o **formato alvo**, não saída capturada. Logs reais vão para
> `docs/evidencias/` nos incrementos E1..E6.

## 1. Enquadramento

- Codificação **UTF-8**; terminador de mensagem `\n` (LF).
- Uma mensagem por linha; o **primeiro campo é o comando**, os demais são argumentos separados por
  espaço simples. O **último argumento consome o resto da linha**, então texto livre pode ter espaços.
- `\n` nunca aparece dentro de um argumento (o protocolo é orientado a linhas; `input()` já garante isso).
- Tamanho máximo de linha: **1024 bytes** incluindo o `\n`. `protocolo.montar()` corta o excesso em
  fronteira de caractere e marca o corte com `…` (U+2026) no fim do último campo — o receptor mostra
  a mensagem como chegou, sem inventar fragmentação. Linha terminada acima de 1024 bytes que venha de
  fora do contrato é rejeitada com `ERR 400 linha_longa` e a sessão continua.
- TCP é fluxo: `recv(1024)` **não** devolve uma mensagem. O leitor acumula bytes e entrega apenas
  linhas terminadas (`protocolo.LeitorLinhas`), o que evita o defeito clássico do material da aula
  (duas mensagens coladas ou uma cortada).

## 2. Canais

| Canal | Transporte | Endereço |
|---|---|---|
| Controle | TCP | `servidor:9990`, sessão persistente por cliente |
| Grupo | UDP | `servidor:9990` (entrada `BC`) e `cliente:<porta>` (saída `BCAST`) |
| Ponto a ponto | TCP | `cliente:<porta>` (o listener do destino) |

## 3. Controle (cliente → servidor)

| Comando | Formato | Resposta |
|---|---|---|
| Registro | `REG <nick> <porta>` | `OK <nick> <ip> <porta>` · `ERR 400 nick_invalido` · `ERR 409 nick_em_uso` · `ERR 400 porta_invalida` |
| Lista | `LIST` | `LISTA <n>` + `n`× `CONTATO <nick> <ip> <porta>` + `FIM` |
| Saída | `BYE` | `BYE` e o servidor fecha a conexão |

Regras de `nick`: 3..16 caracteres, `[a-z0-9_-]`, comparação case-insensitive (`Ana` = `ana`).
Primeiro comando de uma sessão **tem** que ser `REG`; qualquer outro recebe `ERR 401 nao_registrado`.

Depois do `REG` bem-sucedido o cliente envia `LIST` automaticamente — é o "primeiro acesso ao
servidor" do enunciado (R4). Sem isso, quem entra depois não sabe com quem pode falar até digitar
`/listar`.

## 4. Controle (servidor → cliente, assíncrono)

| Evento | Formato | Quando |
|---|---|---|
| Entrada de contato | `EVENTO ENTROU <nick> <ip> <porta>` | outro cliente registrou depois de mim |
| Saída de contato | `EVENTO SAIU <nick>` | o socket do contato fechou |
| Erro | `ERR <código> <motivo>` | comando inválido, `LIST` com sessão não registrada |

O cliente pode receber `EVENTO` a qualquer momento, inclusive enquanto espera resposta de um
comando: por isso a leitura do canal de controle é feita em thread separada e o cliente casa
as respostas por ordem de comando emitido (`LIST` é o único comando que espera resposta depois do `REG`).

## 5. Grupo (UDP)

| Direção | Formato |
|---|---|
| cliente → servidor | `BC <nick> <seq> <texto>` |
| servidor → cada contato | `BCAST <nick> <seq> <texto>` |

- `seq` é um inteiro por remetente, começando em 1, usado só para o cliente detectar lacuna.
- O servidor **valida o remetente**: `(ip de origem, porta de origem)` tem que ser exatamente o
  endpoint registrado para aquele `nick`. Divergência → datagrama descartado, log `BC rejeitado de
  <ip>:<porta> (diz ser <nick>)`. É o mesmo motivo pelo qual o cliente envia o `BC` a partir do
  socket UDP que escuta.
- O servidor reenvia para **todos** os registrados, inclusive o remetente (é uma só regra, sem caso
  especial no servidor). O cliente que enviou já imprimiu o eco local e descarta o próprio `BCAST` —
  assim a mensagem não aparece duas vezes na tela dele.
- Falha de envio para um contato não interrompe os demais (UDP não tem conexão; erro é por datagrama).
- Texto acima do limite é truncado para caber em 1024 bytes; o receptor marca `⚠ truncado`.

### Exemplo (transcrição alvo)

```
# ana, no grupo
ana> /grupo reuniao 19h na sala 12
[grupo ana] reuniao 19h na sala 12          ← eco local imediato
```

Nos outros dois clientes:

```
[grupo ana] reuniao 19h na sala 12
```

No log do servidor:

```
BC de ana 127.0.0.1:41231 seq=1 "reuniao 19h na sala 12" → 3 destinatarios
```

## 6. Ponto a ponto (TCP direto)

| Direção | Formato | Significado |
|---|---|---|
| entrante → destino | `OI <nick>` | "sou o <nick>, quero conversar" |
| destino → entrante | `OI-OK <nick>` | aceito; conversa aberta |
| destino → entrante | `OCUPADO` | já estou em outra conversa (escopo: uma por vez) |
| ambos | `MSG <texto>` | mensagem da conversa |
| ambos | `TCHAU` | encerra; o emissor fecha o socket |
| destino → entrante | `ERR 404 contato_desconhecido` | nick que não está na minha lista |

O destino confere o `nick` recebido contra a própria lista de contatos: se o IP de origem não bate com
o IP registrado para aquele nick, responde `ERR 403 origem_invalida` e fecha.

### Exemplo (transcrição alvo)

```
ana> /listar
  bruno        127.0.0.1:41502
  carla        127.0.0.1:41733

ana> /p2p bruno
[P2P] conectado a bruno (127.0.0.1:41502) — /sair para encerrar
ana(bruno)> oi bruno
bruno> oi! conseguiu rodar o servidor?
ana(bruno)> sim, porta 9990
ana(bruno)> /sair
[P2P] conversa encerrada
```

Do lado do bruno:

```
[P2P] ana conectou (127.0.0.1:50913) — /sair para encerrar
ana> oi bruno
bruno(ana)> oi! conseguiu rodar o servidor?
[P2P] ana encerrou a conversa
```

## 7. Códigos de erro

| Código | Motivo | Onde aparece |
|---|---|---|
| 400 | `nick_invalido`, `porta_invalida`, `comando_invalido` | controle |
| 401 | `nao_registrado` (mandou `LIST` antes de `REG`) | controle |
| 403 | `origem_invalida` (IP de origem não confere com o registrado) | P2P |
| 404 | `contato_desconhecido` | P2P |
| 409 | `nick_em_uso` | controle |
| 410 | `contato_offline` (tentou `/p2p` em nick que saiu) | cliente, local |

## 8. Limites conhecidos do protocolo

1. **UDP não garante entrega nem ordem.** O `seq` detecta a lacuna, não a corrige. Justificativa em
   ADR-0003; mitigação possível (confirmação por destinatário) fica fora do escopo.
2. **Sem autenticação forte**: identificação é "nick + IP/porta de origem". Suficiente para o
   laboratório, insuficiente em rede hostil — registrado como limitação.
3. **Sem fragmentação**: linha única de 1024 bytes; texto maior é truncado, não dividido.
4. **Sem confirmação de leitura**: não há `ACK` para `MSG`; entrega P2P é garantida pelo TCP na
   conexão, mas não há prova de que o humano leu.
