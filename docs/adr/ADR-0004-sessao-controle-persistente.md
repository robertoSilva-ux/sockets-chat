# ADR-0004 — Sessão de controle persistente em vez de requisições curtas

**Status:** aceita · **Data:** 2026-11-13

## Contexto

O cliente usa o servidor para três coisas: registrar-se (R2/R3), pedir a lista (R4) e publicar no
grupo (R6). As duas primeiras poderiam ser requisições TCP curtas — conecta, pede, fecha. Mas R8 exige
"modo síncrono: os clientes precisam estar conectados", o que implica alguém saber quem está
conectado agora.

## Alternativas

| Alternativa | A favor | Contra |
|---|---|---|
| **Sessão TCP persistente** (uma por cliente, viva enquanto o cliente está aberto) | presença exata: `recv` vazio/EOF = saiu, sem polling; o servidor pode **empurrar** eventos (`ENTROU`/`SAIU`), então o cliente sabe na hora em que alguém entra; um único canal de controle | precisa de thread de leitura no cliente e de tratamento de eventos fora de hora; NAT/timeout de firewall pode derrubar sessão ociosa (mitigável com keep-alive) |
| Requisições curtas + *heartbeat* UDP | servidor stateless por requisição; fácil de escalar | presença vira aproximação (expiração por timeout): contato fantasma por até X segundos; o cliente não recebe notificação de entrada; cada ação precisa de nova conexão TCP (3-way handshake por comando) |

## Decisão

Sessão TCP persistente na porta 9990. O contato existe na lista **exatamente** enquanto a conexão de
controle existe; o `finally` da thread de sessão remove o contato e avisa os demais. O grupo continua
100% UDP (a sessão persistente é só do controle, não carrega mensagens de grupo).

## Consequências

- Positivas: R8 fica verdadeiro por construção (não por timeout); `EVENTO ENTROU`/`SAIU` aparecem na
  tela sem polling; o professor pode derrubar um cliente e ver o efeito imediato na lista dos outros.
- Negativas: o cliente ganha uma thread de leitura dedicada e precisa distinguir, no mesmo canal,
  resposta de comando (`OK`, `LISTA`) de evento assíncrono (`EVENTO`) — resolvido porque toda resposta
  a comando é lida de forma síncrona logo após o envio, e eventos usam sempre o prefixo `EVENTO`.
- Encerramento tem que ser ordenado: `BYE` e `shutdown()` antes de fechar, senão o servidor registra
  `ERR` no log em vez de `SAIU`.
