# Guia de apresentação — Sockets Chat (Av3)

> Documento de apoio para a apresentação em laboratório. À esquerda o que falar; à direita o que
> mostrar na tela. Tempo alvo: **10 a 12 minutos**, com demo ao vivo em 2 ou 3 máquinas.
> Para levar impresso, use [`COLA-APRESENTACAO.md`](COLA-APRESENTACAO.md) (uma página).

## Antes de entrar na sala (5 min)

```bash
cd ~/Documentos/ifrs/redes/av3-sockets-chat
git pull                                     # repo atualizado
ss -ltnp 'sport = :9990'                     # porta livre (nada deve aparecer)
./scripts/empacotar-cliente.sh                # zip para os colegas, se ainda não baixaram
python3 servidor.py                           # ANOTE o IP marcado "rede local"
```

Nas máquinas dos colegas: descompactar o zip e `nc -vz <ip> 9990` **antes** de começar. Se o teste
falhar, resolva agora: firewall (`sudo firewall-cmd --add-port=9990/tcp --add-port=9990/udp`) ou IP
errado (não use o do Tailscale).

**Regra de ouro**: todos os clientes com o **mesmo** `--servidor`. Mesma máquina → `127.0.0.1`;
máquinas diferentes → o IP da rede local. Misturar dá `403 origem_invalida`.

## Montagem da demo

| Papel | Onde | Comando |
|---|---|---|
| servidor | sua máquina | `python3 servidor.py` |
| ana | sua máquina | `python3 cliente.py --nick ana --servidor 192.168.0.6` |
| bruno | máquina do colega 1 | `python cliente.py --nick bruno --servidor 192.168.0.6` |
| carla | máquina do colega 2 | `python cliente.py --nick carla --servidor 192.168.0.6` |

Se só houver uma máquina: `./demo.sh` (servidor + 3 clientes em janelas tmux, `Ctrl+b 0..3`).

---

## 1. Abertura — 40 s

> "É um chat no estilo WhatsApp, feito só com a biblioteca padrão do Python: três arquivos.
> Um servidor na porta 9990 e três clientes. **A conversa de duas pessoas é TCP, ligando um cliente
> direto no outro** — o servidor só apresenta os endereços. **A conversa de grupo é UDP, passando pelo
> servidor**, que reenvia para todos. É a mesma troca de mensagens do enunciado, com os dois
> protocolos no mesmo app — e sem nenhuma biblioteca de rede."

Mostrar: a árvore do projeto (`servidor.py`, `cliente.py`, `protocolo.py`, `docs/`) e a janela do
servidor já com os três `REG` no log.

## 2. Tecnologias — 2 min (aqui está a nota)

Falar em **decisões**, não em lista de bibliotecas.

| Tecnologia | O que dizer em uma frase |
|---|---|
| `socket` padrão (stdlib) | "Só `socket`, `threading`, `queue` e `argparse`. Nenhum `pip install` — exigência do enunciado." |
| **Protocolo de texto por linhas** | "Cada mensagem é uma linha UTF-8 terminada em `\n`: comando + argumentos, e o último campo consome o resto — por isso o texto pode ter espaços. Dá para ver o protocolo acontecendo com `nc`." |
| **Enquadramento com buffer** | "`recv(1024)` **não** é uma mensagem: TCP é fluxo, pode chegar meia linha ou três coladas. O `LeitorLinhas` acumula bytes e só entrega linha inteira. Os exemplos de sala de aula tratam o retorno como mensagem e quebram com texto longo." |
| **TCP no ponto a ponto** | "Conversa de dois precisa de ordem e entrega garantida, e a conexão já identifica o par." |
| **UDP no grupo** | "Um envio alcança N destinos sem N conexões. O preço é perder datagrama — então cada mensagem leva `seq` e o receptor avisa a lacuna." |
| **Threads + um `Lock`** | "Uma thread por conexão e a lista de contatos protegida por lock. **Não usei `fork`** porque no fork cada processo fica com uma *cópia* da lista — a lista compartilhada não existiria; `select` travaria todo mundo num envio lento; `asyncio` mudaria o modelo que a disciplina ensina." |
| **Sessão de controle persistente** | "A conexão TCP com o servidor fica aberta: `EOF` quer dizer 'saiu', sem heartbeat e sem contato fantasma." |
| **Identidade não se declara** | "O IP vem de `getpeername()`; no grupo o servidor confere se o `(ip, porta)` de origem é o endpoint registrado."

Se pedirem "por que não JSON": "Poderia, é stdlib — mas esconderia justamente o enquadramento, que é o
que a disciplina avalia. Com texto por linha o protocolo é visível na tela."

## 3. Registro, lista e presença — 1 min 30 s

1. No servidor: as linhas `REG ana ...`, `REG bruno ...`, `REG carla ...`.
2. `ana`: `/listar`.

> "O servidor guarda nick, IP e porta. Repare no `--servidor` real: o IP é o da máquina, e não foi o
> cliente que disse — veio do `getpeername()`. O cliente só declara a **porta onde escuta**."

3. No **bruno**, abrir o cliente agora (ou já estar aberto): a janela da `ana` mostra
   `[+] bruno entrou` sem ela pedir nada.

> "Isso é a sessão persistente: o servidor empurra o evento. E se o bruno fechar, a ana recebe
> `[-] bruno saiu` na hora — presença exata, não timeout."

## 4. Ponto a ponto — 2 min 30 s (a prova principal)

1. `ana`: `/p2p bruno` → `[p2p] conectado a bruno (192.168.0.x:porta)`.
2. No bruno: `[p2p] ana conectou (192.168.0.y:porta)`.
3. Trocar duas mensagens nos dois sentidos (o prompt fica `ana[bruno]>`).
4. **A prova**: apontar para a janela do servidor — **nenhuma linha nova**.

> "As mensagens não passaram pelo servidor. O servidor viu só o `REG` e o `LIST`; o texto foi direto
> de uma máquina para a outra. Se eu rodar `ss -tunap` na máquina do bruno, aparece uma conexão
> `ESTAB` ligando a minha porta à dele."

5. `carla`: `/p2p bruno` → `bruno está em outra conversa`.

> "Ocupação é controlada pelo próprio par: o servidor não intermedeia, então quem sabe se está em
> conversa é quem recebe a conexão. A recusa é uma linha do protocolo (`OCUPADO`), não um erro."

6. `ana`: `/sair` → encerra **só** a conversa; o cliente continua no ar.

## 5. Grupo — 2 min

1. `ana`: `/grupo reuniao 19h na sala 12`.
2. Mostrar nos outros dois: `[grupo ana] reuniao 19h na sala 12`.
3. No servidor: `BC de ana ... -> 3 destinatario(s)`.

> "Um envio, três recebimentos. Esse é o motivo do UDP aqui: o remetente não precisa conhecer nem
> manter três conexões. O servidor valida que o datagrama veio do endpoint registrado da ana —
> sem isso, qualquer processo publicaria como qualquer pessoa."

4. `carla`: `/grupo ok, levo o notebook` → chega nos outros dois.
5. Se quiser provocar: "se um datagrama se perder, o cliente mostra `(UDP) N mensagem(ns) perdida(s)`
   — o `seq` está ali para isso: a perda é visível, não silenciosa."

## 6. Robustez — 1 min

| Provar | Como | O que aparece |
|---|---|---|
| nick repetido | outro `cliente.py --nick ana` | `nick 'ana' já está em uso` e a sessão continua viva |
| queda abrupta | `kill -9` na janela do carla | `[-] carla saiu` nos outros |
| entrada inválida | `/p2p fantasma`, `/foo` | `contato_offline`, `comando desconhecido` |

> "Erro é protocolo, não exceção: nenhum traceback na tela em nenhum desses casos. Um traceback numa
> apresentação é falha de projeto, não de digitação."

## 7. Fechamento — 1 min

1. Rodar as suítes: `python3 testes/teste_protocolo.py` (**16**) e `teste_cliente.py` (**11**).

> "As duas suítes sobem servidor e clientes de verdade, em portas sorteadas, e cada critério do
> enunciado tem um teste nomeado: registro, nick duplicado, lista, P2P direto, grupo, spoof, linha
> longa, queda abrupta."

2. Mostrar `docs/evidencias/` (`04-sockets.log` tem o `ss` provando os dois transportes).

3. Fechar com as três decisões:

> "Três decisões explicam o código: enquadramento em linhas, porque `recv` não é mensagem; threads
> com um lock, porque com `fork` a lista de contatos seria copiada; e sessão persistente, porque o
> enunciado exige que só converse quem está conectado. Os ADRs estão em `docs/adr/`."

Frase de encerramento (se o professor puxar "por que isso não é o WhatsApp"): **"o app é fácil; o
produto é o estado que sobrevive à sessão"** — histórico, entrega offline, identidade e NAT, coisas
que este trabalho deixou de fora de propósito.

---

## Perguntas prováveis (respostas de 20 s)

**"Por que TCP no P2P e UDP no grupo?"**
Conversa de dois: cada linha precisa chegar inteira e em ordem, e a conexão já diz quem é o par.
Grupo: um envio para N destinos sem N conexões — e a perda do UDP é declarada, com `seq`.

**"Como você garante que a mensagem chegou inteira?"**
No TCP, o enquadramento: o leitor acumula bytes até o `\n`. O tamanho máximo é 1024 bytes, e o que
passa é cortado pelo remetente com marca `…`.

**"Por que não `fork`, que foi o que vimos em aula?"**
Porque a lista de contatos precisa ser a mesma para todos. No `fork`, cada filho recebe uma cópia:
o registro de um cliente ficaria invisível para os outros. Precisaria de memória compartilhada ou
fila entre processos.

**"Onde está a concorrência?"**
No servidor: uma thread por sessão de controle, uma thread para o socket UDP do grupo, e um lock
protegendo a lista. No cliente: quatro fontes de evento (prompt, controle, UDP, listener do P2P).

**"E se dois clientes tiverem o mesmo nick?"**
O segundo recebe `ERR 409 nick_em_uso` e pode tentar outro nick na mesma sessão. A comparação é
case-insensitive.

**"Como sabe quem está online?"**
Sessão persistente: contato existe enquanto o socket existe. Fechou, recebeu `EOF`, o servidor
remove e avisa os demais com `EVENTO SAIU`.

**"Como impede alguém de se passar por outro?"**
O IP vem do `getpeername()`, e no grupo o servidor confere o `(ip, porta)` de origem contra o
registrado. Nas conversas P2P o receptor confere o IP de quem conectou (`ERR 403 origem_invalida`).
Não é autenticação forte — está declarado como limitação.

**"Funciona em máquinas diferentes?"**
Sim, e é assim que estou demonstrando: cada cliente anuncia a própria porta, o servidor registra o IP
real, e o P2P conecta direto na máquina do colega. Precisa de firewall liberado para a porta de
entrada.

**"O que acontece se o servidor cair?"**
Os clientes mostram `[!] sessão com o servidor <ip>:<porta> encerrada` e não quebram. Não há
reconexão automática: está fora do escopo, e o enunciado pede operação síncrona.

**"Quantas linhas de código?"**
1.016 linhas nos três arquivos (860 sem comentários e linhas em branco), mais as duas suítes
com 27 testes.

## Se algo falhar na hora

| Sintoma | Ação |
|---|---|
| "porta 9990 indisponível" | `ss -ltnp 'sport = :9990'`; rodar tudo com `--porta 9991` |
| colega não conecta | `nc -vz <ip> 9990` na máquina dele; firewall ou IP da VPN no lugar do IP local |
| conecta mas `/p2p` não abre | firewall da máquina que **recebe**: usar `--porta 5001`/`5002` e liberar a faixa |
| `/p2p` dá `403 origem_invalida` | os clientes estão entrando por endereços diferentes: todos com o mesmo `--servidor` |
| `/p2p` dá `404` | o destino não está na lista *daquele* cliente: `/listar` e tentar de novo |
| nada aparece na tela | `python3 -u` (sem buffer) ou conferir a janela certa do tmux (`Ctrl+b` + número) |
| tudo falhou | `docs/evidencias/` tem os quatro fluxos gravados; as suítes rodam em 25 s |
