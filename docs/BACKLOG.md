# Backlog — incrementos e aceite

Espelho do board Kanban `redes-av3` (um cartão por incremento). Este documento é a **especificação**;
o board é o **fluxo**. Quando a ordem mudar, os dois mudam juntos.

## Visão geral

| # | Incremento | Depende de | Aceite (como se prova) |
|---|---|---|---|
| **E1** | Contrato de fio + servidor de controle (registro, lista, presença) | — | `python3 testes/teste_protocolo.py -k controle` verde; 2 `nc` registram e um `LIST` mostra os dois com ip/porta |
| **E2** | Cliente: sessão de controle, `/listar`, eventos `ENTROU`/`SAIU` | E1 | abrir 3 clientes e ver, no prompt dos outros, o evento de entrada e de saída em menos de 1 s |
| **E3** | Ponto a ponto TCP direto entre clientes | E1, E2 | ana e bruno trocam mensagens com o log do servidor parado; terceira tentativa de entrada recebe `OCUPADO` |
| **E4** | Grupo via UDP (broadcast pelo servidor) | E1, E2 | `/grupo` de um cliente aparece nos outros dois; servidor loga "3 destinatários"; `seq` com lacuna é sinalizado |
| **E5** | Robustez: erros, quotas, queda, spoof, linha > 1024, porta ocupada | E3, E4 | suíte completa verde (`python3 testes/teste_protocolo.py`), incluindo `ERR 409`, `ERR 401`, `ERR 403`, `410 contato_offline` |
| **E6** | Evidências e roteiro da apresentação | E5 | `docs/evidencias/` com logs reais dos quatro fluxos + `demo.sh` que sobe servidor e 3 clientes em tmux |
| **E7** | Fechamento SIGAA: checagem do enunciado item a item e pacote de entrega | E6 | `docs/evidencias/checagem-enunciado.md` com R1..R11 marcados e o `.zip`/`.pdf` gerado |

Sequência recomendada: E1 → E2 → (E3 e E4 em paralelo, são canais independentes) → E5 → E6 → E7.

**Situação em 16/11/2026, 23:56** — E1 a E6 implementados e verificados na mesma sessão
(`testes/teste_protocolo.py` 14/14 e `testes/teste_cliente.py` 10/10, duas rodadas seguidas sem porta
órfã; evidências regravadas em `docs/evidencias/`). E7 tem a checagem
(`docs/evidencias/checagem-enunciado.md`) pronta; o pacote `.zip` e o envio no SIGAA ficam para o
Roberto decidir.

## Mapa requisito → cartão → prova

| Requisito (ESPECIFICACAO.md) | Cartão | Prova |
|---|---|---|
| R1 servidor na 9990, 2+ clientes | E1 | teste `test_aceita_tres_clientes` |
| R2 nick solicitado no primeiro acesso | E1 | teste `test_registro_e_dup` |
| R3 lista de contatos (nick, ip, porta) | E1 | `LIST` nos três clientes |
| R4 cliente pede lista ao servidor | E2 | `/listar` |
| R5 P2P direto TCP | E3 | log do servidor sem tráfego + teste `test_p2p_direto` |
| R6 broadcast via servidor, UDP | E4 | teste `test_grupo_tres_destinatarios` |
| R7 os dois protocolos | E3+E4 | tabela de sockets + captura |
| R8 modo síncrono (só conectados) | E2+E5 | `EVENTO SAIU` e `410 contato_offline` |
| R9 só socket padrão | E1 | imports e ausência de `requirements.txt` |
| R10 apresentação e envio | E6+E7 | roteiro, logs, pacote |
| R11 informar tecnologia ao professor | — | pendência do aluno (e-mail até 12/11) |

## Decisões que travam cartões

| Decisão | Estado | Trava |
|---|---|---|
| Interface: CLI (padrão) ou CLI + Tkinter extra | **aberta — aguardando o Roberto** | E6 (roteiro depende de como a demo é feita) |
| Um P2P por vez (`OCUPADO`) | aceita nesta spec | E3 |
| Grupo sem confirmação por destinatário (perda visível pelo `seq`) | aceita nesta spec | E4 |
| Repositório git + envio para o GitHub | não iniciado | E7 |

## Fora do backlog

Assistente com histórico persistente, criptografia, transferência de arquivos, interface gráfica
completa, reconexão automática — ver ESPECIFICACAO.md §3.
