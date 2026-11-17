# ADR-0001 — Protocolo de aplicação em texto, uma linha por mensagem

**Status:** aceita · **Data:** 2026-11-13

## Contexto

Os sockets entregam bytes, não mensagens. Toda aplicação sobre socket precisa de um contrato de
enquadramento próprio: onde começa e termina cada mensagem, e como distinguir comando de conteúdo.
O material da disciplina não define esse contrato — os exemplos enviam texto cru com `recv(1024)`,
o que funciona na demonstração e quebra na primeira mensagem longa.

## Alternativas

| Alternativa | A favor | Contra |
|---|---|---|
| **Texto, uma linha por mensagem** | inspecionável com `nc`/`tcpdump` ao vivo (ótimo para a apresentação); zero dependência; implementação curta | texto livre precisa escapar `\n`; número precisa ser convertido; sem tipos |
| JSON por linha (`json.loads`) | tipos, campos nomeados, extensível | `json` é stdlib (permitido), mas esconde exatamente o que a disciplina avalia: o enquadramento. Na apresentação vira caixa-preta |
| Binário com prefixo de tamanho (`struct`) | robusto, sem ambiguidade de texto, eficiente | ilegível em ferramenta de rede; exige documentar o layout byte a byte; nada a mostrar na tela |

## Decisão

Texto UTF-8, uma mensagem por linha terminada em `\n`, primeiro campo = comando, último argumento
consome o resto da linha (permite espaços no texto da mensagem). Leitura com buffer de linhas, nunca
assumindo que `recv` devolve uma mensagem inteira.

## Consequências

- Positivas: dá para ver o protocolo acontecendo na tela; o mesmo parser serve aos três canais
  (controle, grupo, P2P); depuração trivial com `nc`.
- Negativas: `\n` e truncamento em 1024 bytes viram regras do contrato (documentadas em PROTOCOLO.md
  §1 e §8); sem tipos, então porta e `seq` são convertidos com validação explícita.
