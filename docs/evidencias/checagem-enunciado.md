# Checagem do enunciado — item por item

Fonte: `Av3.pdf` (Redes de Computadores, Av3, prof. Luciano V. Gonçalves).
Conferência feita em **16/11/2026** contra o código deste repositório, com as duas suítes verdes
(`14/14` em `testes/teste_protocolo.py` e `10/10` em `testes/teste_cliente.py`) e as evidências de
`docs/evidencias/` geradas por execução real.

| # | Exigência | Resultado | Onde está a prova |
|---|---|---|---|
| R1 | Servidor recebendo dois ou mais clientes na porta 9990 | **cumpre** | `servidor.py:65` (bind TCP 9990, `SO_REUSEADDR`, `listen`) e `:80` (UDP 9990); teste `test_aceita_tres_clientes`; evidência `01-registro-lista.log` (3 no ar) e `06-servidor.log` (`3 contato(s) no total`) |
| R2 | Aguarda os clientes e solicita os nicknames | **cumpre** | `servidor.py:159` `_registrar` valida nick/porta e responde `OK`/`ERR 409`; o cliente pede o nick no `--nick` e reabre o pedido se estiver em uso (`cliente.py` `registrar`); teste `test_registro_e_dup`; evidência `05-erros.log` (nick repetido recusado, sessão viva) |
| R3 | Armazena NICK, IP e porta numa lista de contatos | **cumpre** | `servidor.py:35` (`Contato`) e o `dict` protegido por `Lock`; **o IP vem de `getpeername()`**, nunca do cliente (`servidor.py:112`); teste `test_list_mostra_ip_e_porta` |
| R4 | Cliente solicita ao servidor a lista com nome, IP e porta do destino | **cumpre** | `cliente.py:324` `listar()`; a lista é pedida **automaticamente após o registro** (primeiro acesso) e de novo em `/listar`; testes `test_cliente_lista_contatos`, `test_list_mostra_ip_e_porta`; evidência `01-registro-lista.log` |
| R5 | Conversas ponto a ponto em conexão individual direta, via TCP | **cumpre** | `cliente.py:258` `abrir_p2p` (conecta direto em `ip:porta` do par) e `:194` (handshake entrante `OI`/`OI-OK`/`OCUPADO`); testes `test_p2p_direto` (assegura que **nada** de P2P aparece no log do servidor) e `test_p2p_ocupado`; evidências `02-p2p.log` (log do servidor vazio durante a conversa) e `04-sockets.log` (ESTAB entre as portas dos dois clientes) |
| R6 | Broadcast pelo servidor, reenviado a todos os clientes, via UDP | **cumpre** | `servidor.py:242` `_repassar_grupo` (valida remetente, snapshot da lista, reenvia `BCAST`); `cliente.py:162` recebe, detecta lacuna e imprime; testes `test_grupo_tres_destinatarios`, `test_grupo_pelo_cliente`; evidência `03-grupo.log` + linha `-> 3 destinatario(s)` no `06-servidor.log` |
| R7 | Usar **os dois protocolos** no projeto | **cumpre** | `04-sockets.log`: `tcp LISTEN` e `udp UNCONN` na **mesma porta** de cada processo, mais `tcp ESTAB` de controle e de P2P |
| R8 | Servidor síncrono: clientes precisam estar conectados | **cumpre** | sessão de controle persistente (`ADR-0004`): queda = `EOF` → `EVENTO SAIU` e remoção da lista; testes `test_evento_entrou_saiu`, `test_queda_abrupta_de_cliente`, `test_p2p_contato_offline`, `test_bye_remove_contato` |
| R9 | Socket padrão, sem biblioteca pronta | **cumpre** | imports: `socket`, `threading`, `queue`, `argparse`, `sys`, `time`, `os` (só stdlib); **não existe** `requirements.txt`/`pyproject.toml`; nenhum `pip install` no README |
| R10 | Apresentação em sala 19/11 e envio no SIGAA 22/11 | **parcial** | `docs/ROTEIRO-APRESENTACAO.md` e `docs/evidencias/` prontos; falta o pacote `.zip` e o envio (decisão do Roberto) |
| R11 | Informar a tecnologia ao professor até 12/11 | **pendência do aluno** | não é verificável por código; assumido Python 3 — confirmar o e-mail enviado |

## O que fica de fora (e está declarado no README)

Perda de datagrama no grupo (detectada pelo `seq`, não corrigida), uma conversa P2P por vez, sem
autenticação/TLS e sem histórico, P2P inviável atrás de NAT. Nada disso é exigido pelo enunciado; o
que o enunciado pede está coberto por R1–R9.

## Reproduzir esta checagem

```bash
python3 testes/teste_protocolo.py     # 14 testes
python3 testes/teste_cliente.py       # 10 testes
python3 testes/gerar_evidencias.py    # regrava docs/evidencias/
```
