# ADR-0003 — TCP no ponto a ponto, UDP no grupo

**Status:** aceita · **Data:** 2026-11-13

## Contexto

O enunciado fixa o par no tema ("Ponto a Ponto ... TCP" / "Broadcast ... UDP") e ao mesmo tempo pede
que os dois protocolos apareçam no projeto, "alternando em TCP ou UDP para cada uma das conversas".
Ou seja: a escolha não é livre — o que cabe justificar é *por que* essa combinação faz sentido, e isso
precisa aparecer na apresentação.

## Alternativas

| Combinação | A favor | Contra |
|---|---|---|
| **P2P em TCP, grupo em UDP** | conversa de dois: cada linha chega inteira, em ordem, e a conexão já identifica o par; grupo: um envio alcança N sem N conexões | grupo perde datagrama |
| P2P em UDP, grupo em TCP | grupo confiável | P2P em UDP exigiria sequência, retransmissão e confirmação — reimplementar TCP no pior lugar; e o grupo em TCP exigiria N conexões mantidas pelo servidor só para isso |
| tudo em TCP | simples, confiável | contraria o enunciado e esconde a diferença entre os protocolos, que é o objeto da avaliação |
| tudo em UDP | leve | sem garantia nenhuma numa conversa de duas pessoas, onde a perda é inaceitável |

## Decisão

- **Ponto a ponto: TCP**, conexão direta entre os dois clientes (o servidor participa apenas da
  descoberta). Uma conversa = um socket = identidade do par. Entrega garantida é requisito de conversa.
- **Grupo: UDP**, cliente → servidor → N clientes. O valor está em **um envio alcançar N
  destinatários** sem que o remetente conheça N conexões.
- Para não esconder a fraqueza do UDP: `seq` por remetente e aviso de lacuna no cliente.

## Consequências

- Positivas: cada protocolo aparece com o problema que ele resolve; a demonstração mostra os dois
  comportamentos lado a lado (inclusive a perda, se o professor provocar).
- Negativas: o grupo pode perder mensagem — é limitação declarada em PROTOCOLO.md §8, não bug
  silencioso. Confirmação por destinatário (`ACK` UDP) fica fora do escopo por custo/benefício dentro
  do prazo da atividade.
- A clientes atrás de NAT, o grupo continua funcionando (o cliente só envia e recebe pelo endpoint
  registrado, e o servidor está na mesma rede); o **P2P** é o que quebra atrás de NAT — por isso a
  demonstração oficial é em rede local.
