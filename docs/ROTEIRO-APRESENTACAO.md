# Roteiro da apresentação — 10 minutos

Preparação: `./demo.sh` já sobe servidor + 3 clientes. Tenha este roteiro impresso e um terminal
extra para `ss`/testes. Se `tmux` não existir, abra 4 terminais.

## 0. Abertura (30 s)

> "É um WhatsApp de terminal. Um servidor na porta 9990 e três clientes. Conversa entre duas pessoas
> é **TCP direto entre os clientes** — o servidor só apresenta os endereços. Conversa de grupo é
> **UDP pelo servidor**. Só biblioteca padrão: nenhuma biblioteca de rede."

Mostrar a árvore: `ls` (servidor.py, cliente.py, protocolo.py, docs/).

## 1. Registro e lista — R1, R2, R3, R4 (1 min 30 s)

1. Mostrar a janela do servidor: já logou as três entradas (`REG ana ...`, `REG bruno ...`).
2. Em `ana`: `/listar`.
   > "O servidor guarda nick, IP e porta de cada cliente. O IP não foi o cliente que disse: veio do
   > `getpeername()` — o cliente só declara a porta onde escuta."
3. Em `bruno`, digitar `/listar` e voltar para `ana`.
   > "Quando o bruno entrou, a ana recebeu o evento sem apertar nada: a sessão de controle é
   > persistente. Some o contato do `LIST`? Não: quem fecha o socket sai da lista na hora."

## 2. Ponto a ponto — R5 (2 min 30 s)

1. `ana`: `/p2p bruno` → "conectado a bruno (127.0.0.1:porta)".
2. Trocar duas mensagens nos dois sentidos (mostrar que o `prompt` passa a ser `ana[bruno]>`).
3. **A prova**: no terminal extra, `ss -tunap | grep <porta do bruno>`.
   > "Olha a conexão ESTAB ligando a porta de um cliente à porta do outro, sem passar pelo servidor.
   > É por isso que o log do servidor, aqui ao lado, não tem nenhuma linha de mensagem."
4. Em `carla`: `/p2p bruno` → "bruno está em outra conversa" (`OCUPADO`).
   > "Uma conversa por vez: se o servidor não intermedeia, quem controla a ocupação é o próprio par."
5. `ana`: `/sair` → encerra só a conversa, o cliente continua no ar.

## 3. Grupo — R6, R7 (2 min)

1. `ana`: `/grupo reuniao 19h na sala 12`.
   > "Um envio. O servidor reenviou para os três — está no log dele: `-> 3 destinatario(s)`."
2. Confirmar que `bruno` e `carla` receberam com o prefixo `[grupo ana]`.
3. `carla`: `/grupo ok, levo o notebook` → aparece nos outros dois.
4. Explicar a escolha: **um datagrama alcança N destinos** sem N conexões; o custo é que UDP pode
   perder — por isso cada mensagem leva `seq` por remetente e o cliente avisa
   "(UDP) N mensagem(ns) perdida(s)" quando o número pula.
5. Se sobrar tempo: `ss -ulnp` mostrando o UDP 9990 e os sockets UDP dos clientes.

## 4. Robustez (1 min)

| Provar | Como |
|---|---|
| nick repetido não entra | abrir `python3 cliente.py --nick ana` → "já está em uso", sessão viva |
| cliente cai sem avisar | `kill -9` numa janela de cliente → os outros mostram `[-] nome saiu` |
| entrada inválida | `/p2p fantasma` → `contato_offline`; `/foo` → "comando desconhecido" |

> "Erro é protocolo, não exceção: nenhum traceback aparece na tela em nenhum desses casos."

## 5. Fechamento (1 min)

1. Rodar `python3 testes/teste_protocolo.py` (14 testes) e `teste_cliente.py` (10) — tudo verde.
   > "As duas suítes sobem servidor e clientes de verdade, em portas livres; cada critério do
   > enunciado tem um teste nomeado."
2. Mostrar `docs/evidencias/` — logs capturados de execução real, e a checagem R1–R11.
3. Fechar pelas decisões:
   > "Três decisões explicam o código: enquadramento em linhas (`recv` não é mensagem), threads com
   > um lock (com `fork` a lista de contatos seria copiada por processo) e sessão persistente
   > (presença exata). Os ADRs estão em `docs/adr/`."

## Se algo falhar na hora

| Sintoma | Ação |
|---|---|
| "porta 9990 indisponível" | `ss -ltnup 'sport = :9990'`; rodar `./demo.sh --porta 9991` e clientes com `--porta-servidor 9991` |
| outro computador não conecta | usar o IP marcado **rede local** no banner do servidor (não o da VPN); liberar `9990/tcp` e `9990/udp` no firewalld; testar com `nc -vz <ip> 9990` |
| conecta mas o P2P não abre | porta do cliente barrada: rodar os clientes com `--porta 5001`/`5002` e liberar `5001-5099/tcp` na máquina que recebe |
| cliente não vê os outros | ele precisa ter recebido `EVENTO ENTROU` ou rodado `/listar`; a lista é pedida no registro |
| P2P recusa com `404` | o destino não está na lista **deste** cliente: `/listar` e tentar de novo |
| nada aparece no terminal | `python3 -u` ou conferir se está na janela certa do tmux (`Ctrl+b` + número) |

Rede de segurança: as evidências gravadas em `docs/evidencias/` mostram os quatro fluxos; e as
suítes rodam em 25 s se for preciso demonstrar sem digitar.
