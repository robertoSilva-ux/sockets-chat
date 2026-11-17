# Especificação — o que o enunciado pede e como cada item é cumprido

Fonte: `Av3.pdf` — *Redes de Computadores, Atividade Avaliada 3*, IFRS Rio Grande, Prof. Luciano V. Gonçalves.
Apresentação em sala **19/11/2026**; envio no SIGAA **22/11/2026**. Tecnologia declarada ao professor: **Python 3 (stdlib)**.

## 1. Requisitos extraídos

| # | Exigência do enunciado (citação) | Decisão do projeto | Como se prova |
|---|---|---|---|
| R1 | "Implemente um Servidor de Rede que receba **dois ou mais Clientes na porta 9990**" | `servidor.py` escuta TCP 9990; cada cliente aceito vira uma thread de sessão. N clientes simultâneos. | 3 clientes conectados ao mesmo tempo, com o servidor listando os três (`/listar` em cada um). |
| R2 | "Aguarda os Clientes ... e **solicita os Nicknames**" | O cliente envia `REG <nick> <porta>` ao abrir; o servidor responde `OK` ou `ERR 409 nick_em_uso`. | Log do servidor com a linha `REG` e a resposta; teste `teste_protocolo.py::test_registro_e_duplicado`. |
| R3 | "**Armazena os NICK, IPs e Portas em uma lista de Contatos**" | Dicionário `nick → Contato(nick, ip, porta, conexão)` protegido por `threading.Lock`. O IP vem de `socket.getpeername()` (nunca do que o cliente declara). | `LIST` devolvendo ip/porta corretos para cada um dos 3 clientes. |
| R4 | "O Cliente **solicita ao servidor a lista de Clientes** cadastrados, com Nomes, endereço IP e Porta" | Comando `/listar` → `LIST` → `LISTA n` + `n` linhas `CONTATO ...`. | `/listar` mostrando os outros dois clientes com IP e porta. |
| R5 | "Os clientes conversam em uma **conexão individual direta** entre os Clientes ... via **TCP**" | `cliente.py` mantém listener TCP na própria porta; `/p2p bruno` conecta direto em `ip:porta` do bruno. O servidor não vê as mensagens. | Duas conversas P2P simultâneas (ana↔bruno e carla↔bruno em momentos distintos) sem tráfego no servidor — provado por log do servidor vazio durante a troca. |
| R6 | "O Cliente envia mensagens Broadcast para o servidor que **reenvia para todos** os Clientes ... **UDP**" | `/grupo texto` → datagrama `BC` a `127.0.0.1:9990/udp` → servidor reenvia `BCAST` ao endpoint UDP de cada contato. | Três clientes recebendo a mesma mensagem: um envio, três recebimentos. |
| R7 | "Os alunos devem **utilizar os dois protocolos** no projeto" | TCP no P2P e no controle; UDP no grupo. | Tabela de sockets em `ARQUITETURA.md` + captura de tráfego mostrando `SOCK_STREAM` e `SOCK_DGRAM`. |
| R8 | "O Servidor opera de **modo síncrono**, os clientes precisam estar conectados para trocarem mensagens" | Sessão de controle persistente: contato existe apenas enquanto o socket TCP está aberto; queda = `EVENTO SAIU` e remoção da lista. P2P e grupo são recusados para contato ausente. | Derrubar um cliente (`Ctrl+C`) e ver o evento de saída nos outros dois + `ERR` ao tentar `/p2p` nele. |
| R9 | "**Não é permitido o uso de bibliotecas prontas**" | Só `socket`, `threading`, `select`, `sys`, `argparse`. Sem `asyncio`? → ver ADR-0002 (threads, decisão explícita). | `requirements.txt` inexistente; import list nos dois arquivos. |
| R10 | "**Apresentação 19/11/26**" e "Envio de arquivos no SIGAA 22/11/26" | Incremento E6 produz roteiro e evidências; E7 empacota a entrega. | `docs/evidencias/` com logs reais + `demo.sh`. |
| R11 | "Informe ao professor ... **até o dia 12/11/26**" | Data já passada em relação a hoje (13/11). | Pendência do aluno: confirmar por e-mail que Python foi informado. |

## 2. Escopo assumido

- **Um P2P por vez por cliente** ("conversas Ponto a Ponto entre duas pessoas"): o cliente em conversa
  responde `OCUPADO` a uma segunda tentativa de entrada. Mantém o modelo do enunciado e evita a
  complexidade de multiplexar conversas no terminal.
- **Mensagens de texto de uma linha**, até 1024 bytes (limite de `recv` do material da disciplina).
  `\n` não faz parte do conteúdo — o protocolo é orientado a linhas.
- **Nick único, case-insensitive**, 3 a 16 caracteres `[a-z0-9_-]`.
- **IPv4 e mesma rede local** (ou `localhost`). Sem NAT traversal, sem IPv6: o enunciado assume máquinas
  alcançáveis (laboratório), e o cliente anuncia a própria porta de escuta — atrás de NAT esse anúncio
  seria inútil.

## 3. Fora de escopo (e por quê)

| Não será feito | Motivo |
|---|---|
| Histórico/armazenamento de mensagens | O enunciado pede troca síncrona; persistir não é avaliado e adiciona estado no servidor. |
| Autenticação por senha, criptografia (TLS) | Não pedido; e TLS exigiria certificado em 6 dias. Registrado como limitação conhecida no README. |
| Envio de arquivos, áudio, "visto por último" | Escopo do produto WhatsApp, não da atividade. |
| Interface gráfica | Decisão do Roberto (ver pergunta em aberto): a entrega é CLI com prompt; GUI Tkinter seria incremento extra, depois do E6. |
| Múltiplas conversas P2P simultâneas | Ver escopo assumido acima. |
| Reconexão automática | Queda encerra a sessão (comportamento síncrono exigido por R8). |

## 4. Riscos

| Risco | Impacto | Mitigação |
|---|---|---|
| **Perda de datagrama UDP** no grupo | Mensagem "some" na apresentação e parece bug | Número de sequência por remetente; cliente mostra lacuna (`⚠ 1 mensagem perdida`) quando o seq salta. Vira argumento de disciplina, não defeito escondido. |
| Porta 9990 já ocupada na máquina | Servidor não sobe | `SO_REUSEADDR` + mensagem de erro explícita com o comando para descobrir o dono (`ss -ltnup 'sport = :9990'`). |
| Firewall/NAT entre duas máquinas | P2P "conecta mas nada chega" | Demonstração padrão em `localhost`; teste em duas máquinas como verificação extra no E6. |
| `recv(1024)` tratado como mensagem completa | Mensagens coladas ou cortadas — o defeito clássico do material da aula | Buffer de linhas por conexão (`protocolo.LeitorLinhas`): acumula bytes e só entrega linha terminada. |
| Prazo: 19/11 em sala (6 dias) | Sem demonstração, nota perdida | E1..E4 até 17/11; E6 (roteiro/evidências) até 18/11 pela manhã. |
