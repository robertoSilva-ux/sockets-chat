# COLA — Sockets Chat (Av3)

*Imprimir frente e verso: a frente é o que falar e mostrar; o verso são as perguntas prováveis e o
plano B.*

## Ordem da apresentação

| ✔ | Bloco | Tempo | O que mostrar / dizer |
|---|---|---|---|
| ☐ | Abertura | 40 s | "3 arquivos, só stdlib. P2P em TCP direto; grupo em UDP pelo servidor." |
| ☐ | Tecnologias | 2 min | protocolo de linhas · buffer (`recv` não é mensagem) · threads + lock (`fork` copiaria a lista) · sessão persistente · `getpeername` |
| ☐ | Registro | 1:30 | servidor mostra `REG ...`; ana `/listar`; bruno entra → `[+] bruno entrou` |
| ☐ | P2P | 2:30 | ana `/p2p bruno`; 2 mensagens; **log do servidor vazio**; carla `/p2p bruno` → ocupado; ana `/sair` |
| ☐ | Grupo | 2 min | ana `/grupo ...`; 3 telas recebem; servidor `-> 3 destinatario(s)` |
| ☐ | Robustez | 1 min | nick repetido · `kill -9` → `[-] carla saiu` · `/p2p fantasma` |
| ☐ | Fechamento | 1 min | suítes **16 + 11** · `docs/evidencias/` · 3 decisões |

## Antes de entrar (5 min)

```bash
git pull && ss -ltnp 'sport = :9990'        # porta livre
python3 servidor.py                          # ANOTAR o IP "rede local"
python3 cliente.py --nick ana --servidor <IP>
# nas máquinas dos colegas:  nc -vz <IP> 9990   (antes da aula!)
```

Todos com o **mesmo** `--servidor`: mesma máquina → `127.0.0.1`; máquinas diferentes → IP local.

## Seis frases que valem a nota

1. "`recv` não é mensagem: TCP é fluxo — o leitor acumula bytes até o `\n`."
2. "`fork` copia a lista de contatos em cada processo; por isso threads com um único lock."
3. "O log do servidor está vazio durante a conversa: as mensagens foram de máquina para máquina."
4. "Um envio, três recebimentos: é o motivo do UDP no grupo."
5. "O IP não é declarado pelo cliente, vem do `getpeername()`; o grupo confere o endpoint de origem."
6. "Erro é protocolo, não exceção: nenhum traceback em nenhum caso."

## Números para não gaguejar

**9990** TCP (controle/P2P) e **9990** UDP (grupo) · **4** portas por cliente (escuta, controle, grupo =
escuta, P2P de saída) · **1024** bytes por linha · **1016** linhas em 3 arquivos (860 sem comentários) ·
**27** testes (16 + 11) · **4** ADRs.

## Três perguntas e a resposta de 20 s

- **"Por que não `fork`?"** — a lista de contatos precisa ser a mesma para todos; no fork cada filho
  tem uma cópia e o registro de um cliente seria invisível para os outros.
- **"Por que UDP no grupo?"** — um envio alcança N destinos sem N conexões; a perda existe e é
  declarada pelo `seq`, que avisa a lacuna.
- **"Funciona entre máquinas?"** — sim, é o que estou demonstrando: cada cliente anuncia a própria
  porta, o servidor registra o IP real e o P2P conecta direto.

## Se travar

| Sintoma | O que fazer |
|---|---|
| `403 origem_invalida` | clientes com `--servidor` diferentes — usar o mesmo em todos |
| `404 contato` | não está na lista daquele cliente: `/listar` e repetir |
| 9990 ocupada | `ss -ltnp 'sport = :9990'`; rodar tudo com `--porta 9991` |
| P2P não abre | firewall da máquina que **recebe** (`--porta 5001` + liberar a faixa) |
| tudo falhou | `docs/evidencias/` tem os 4 fluxos gravados; suítes em 25 s |
