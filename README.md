# Sockets Chat — Av3 de Redes de Computadores

Sistema de conversas no estilo WhatsApp, escrito **só com a biblioteca padrão do Python**
(`socket`, `threading`), para a Atividade Avaliada 3 de Redes de Computadores — IFRS Rio Grande,
Prof. Luciano V. Gonçalves. Apresentação em sala **19/11/2026**, envio no SIGAA **22/11/2026**.

| Conversa | Protocolo | Caminho da mensagem |
|---|---|---|
| Ponto a ponto (duas pessoas) | **TCP** | cliente → cliente, conexão direta (o servidor só entrega o endereço) |
| Grupo / broadcast (uma para várias) | **UDP** | cliente → servidor → todos os clientes registrados |

O servidor escuta na **porta 9990 nos dois protocolos**: TCP 9990 para controle (registro, lista,
presença) e UDP 9990 para o grupo. Portas TCP e UDP são espaços independentes, então a mesma
numeração vale para os dois canais sem conflito.

## Como rodar

Precisa apenas de Python 3.8+ (nada de `pip install`).

```bash
# terminal 1 — servidor
python3 servidor.py

# terminal 2, 3, 4 — clientes
python3 cliente.py --nick ana
python3 cliente.py --nick bruno
python3 cliente.py --nick carla
```

Ou, com `tmux` instalado:

```bash
./demo.sh                 # servidor + 3 clientes, uma janela cada
./demo.sh --porta 9991    # outra porta
```

### No laboratório, com dois computadores

O servidor escuta em **todas as interfaces** e imprime, ao subir, o endereço que o colega deve usar:

```
[00:32:51] Servidor do chat no ar — TCP e UDP na porta 9990, em todas as interfaces
[00:32:51] Nesta máquina:   127.0.0.1      (para testar sozinho, na mesma máquina)
[00:32:51]                  192.168.0.6     rede local
[00:32:51]                  100.74.198.127  VPN/Tailscale
[00:32:51] Em outro computador:  python3 cliente.py --nick ana --servidor 192.168.0.6
```

Na outra máquina, basta trocar o `--servidor`:

```bash
python3 cliente.py --nick bruno --servidor 192.168.0.6
```

O IP que aparece no `LIST` é o do remetente **como o servidor o viu** (`getpeername()`), não o que o
cliente declarou — por isso o P2P entre máquinas funciona sem configuração extra: cada cliente
escuta na própria porta em todas as interfaces e o par conecta direto naquele endereço.

**Firewall.** Fedora com `firewalld` ativo bloqueia conexões de entrada por padrão. Na máquina que
roda o servidor:

```bash
sudo firewall-cmd --add-port=9990/tcp --add-port=9990/udp               # até o próximo reload
sudo firewall-cmd --permanent --add-port=9990/tcp --add-port=9990/udp   # persistente
sudo firewall-cmd --reload
```

Para o **P2P** a porta é a do cliente (efêmera, por padrão). Se o colega não conseguir abrir a
conversa, fixe as portas e libere a faixa na máquina que vai **receber**:

```bash
python3 cliente.py --nick bruno --porta 5002 --servidor 192.168.0.6
sudo firewall-cmd --add-port=5001-5099/tcp
```

Diagnóstico rápido da outra máquina: `nc -vz 192.168.0.6 9990`.
Não conecta → IP errado ou servidor fora do ar. Conecta mas nada chega → firewall, ou o IP da VPN
usado no lugar do IP da rede local.

### Comandos do cliente

```
/listar          pede ao servidor a lista de contatos (nick, ip, porta)
/quem            mostra a lista que já está em memória
/p2p <nick>      abre conversa ponto a ponto direta (TCP) com <nick>
/grupo <texto>   envia <texto> para todos os clientes (UDP, via servidor)
/sair            encerra a conversa aberta ou, fora dela, sai do chat
```

Dentro de uma conversa, texto sem `/` vai para o par. `--porta 5001` fixa a porta local (útil para
mostrar `ss` na apresentação); por padrão a porta é efêmera, descoberta com `getsockname()` e
anunciada no registro — assim dois clientes rodam na mesma máquina sem colidir.

## Testes

Dois harnesses, sem framework, que sobem o servidor e os clientes **de verdade**:

```bash
python3 testes/teste_protocolo.py    # 14 testes: controle, grupo, contrato e enquadramento
python3 testes/teste_cliente.py      # 10 testes: lista, presença, P2P, grupo, robustez
python3 testes/teste_protocolo.py -k controle   # filtra por pedaço do nome
```

As evidências de execução (logs reais dos processos, captura de `ss`) ficam em
[`docs/evidencias/`](docs/evidencias/) e são geradas por `python3 testes/gerar_evidencias.py`.

## Estrutura

```
servidor.py      TCP 9990 (controle/presença) + UDP 9990 (grupo), threads + lock
cliente.py       prompt, sessão de controle, listener TCP (P2P) e socket UDP (grupo)
protocolo.py     contrato de fio: enquadramento em linhas, validação de nick, erros
testes/          harness stdlib + gerador de evidências
docs/            especificação, arquitetura, protocolo, backlog, ADRs, evidências
demo.sh          servidor + 3 clientes em tmux
```

## Documentação

| Documento | Conteúdo |
|---|---|
| [`docs/ESPECIFICACAO.md`](docs/ESPECIFICACAO.md) | requisitos do enunciado (R1–R11), escopo, riscos, como cada item é provado |
| [`docs/ARQUITETURA.md`](docs/ARQUITETURA.md) | processos, sockets, threads, fluxos, máquina de estados |
| [`docs/PROTOCOLO.md`](docs/PROTOCOLO.md) | contrato de fio: comandos, respostas, erros, limites |
| [`docs/ROTEIRO-APRESENTACAO.md`](docs/ROTEIRO-APRESENTACAO.md) | roteiro de 10 minutos para a apresentação |
| [`docs/BACKLOG.md`](docs/BACKLOG.md) | incrementos e critério de aceite de cada um |
| [`docs/adr/`](docs/adr/) | decisões com alternativas e trade-offs |
| [`docs/evidencias/`](docs/evidencias/) | logs reais + checagem item a item do enunciado |

## Decisões que valem explicar (e onde estão)

- **Enquadramento em linhas**, com leitor que acumula bytes ([`protocolo.py:93`](protocolo.py#L93)):
  `recv(1024)` não é uma mensagem — TCP é fluxo. Os exemplos didáticos da disciplina assumem que é,
  e quebram com texto longo. ADR-0001.
- **Threads + `Lock`**, não `fork` (ADR-0002): no `fork` cada filho tem *cópia* da lista de contatos,
  então a lista compartilhada não existiria. O lock protege a estrutura; o envio do grupo acontece
  sobre um *snapshot*, fora do lock ([`servidor.py:242`](servidor.py#L242)).
- **TCP no P2P, UDP no grupo** (ADR-0003): conversa de dois precisa de ordem e entrega; grupo precisa
  alcançar N destinos com um envio. A fragilidade do UDP não é escondida: `seq` por remetente e aviso
  de lacuna no receptor ([`cliente.py:162`](cliente.py#L162)).
- **Sessão de controle persistente** (ADR-0004): "os clientes precisam estar conectados" vira verdade
  por construção — `EOF` = saiu, e os demais recebem `EVENTO SAIU` na hora.
- **Identidade não se declara**: o IP vem de `getpeername()`, e o broadcast só é aceito se o
  `(ip, porta)` de origem for o endpoint registrado daquele nick
  ([`servidor.py:159`](servidor.py#L159)) — sem isso, qualquer processo publica como qualquer pessoa.

## Limitações conhecidas

- Grupo em UDP **pode perder** mensagem: o `seq` detecta a lacuna e avisa, mas não retransmite.
- **Uma conversa P2P por vez** por cliente: a segunda tentativa recebe `OCUPADO`.
- **Sem autenticação forte** (sem senha nem TLS) e **sem histórico**: o modelo é síncrono, como pede
  o enunciado.
- P2P entre máquinas atrás de NAT não funciona (o cliente anuncia a própria porta); a demonstração é
  em rede local.
