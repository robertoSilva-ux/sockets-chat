#!/usr/bin/env python3
"""Cliente do chat — Av3 Redes de Computadores.

Concorrência (ver docs/ARQUITETURA.md §2): quatro fontes de evento ao mesmo tempo.

* thread principal  — prompt e comandos (`input()` bloqueante);
* sessão de controle — eventos `ENTROU`/`SAIU` empurrados pelo servidor;
* socket UDP        — mensagens de grupo (`BCAST`);
* listener TCP      — conversas ponto a ponto entrantes (`OI`).

Toda escrita no terminal passa por `mostrar()`, que segura um lock e reimprime o prompt,
senão mensagem recebida entra no meio do que a pessoa está digitando.

Comandos: /listar  /p2p <nick>  /grupo <texto>  /ajuda  /sair
Dentro de uma conversa P2P, texto sem "/" vai para o par; /sair encerra só a conversa.
"""

import argparse
import queue
import socket
import sys
import threading
import time

import protocolo as p

AJUDA = """\
comandos:
  /listar          pede ao servidor a lista de contatos (nick, ip, porta)
  /p2p <nick>      abre conversa ponto a ponto direta (TCP) com <nick>
  /grupo <texto>   envia <texto> para todos os clientes (UDP, via servidor)
  /sair            encerra a conversa aberta ou, fora dela, sai do chat
dentro de uma conversa, texto sem "/" vai para o par."""


class Cliente:
    def __init__(self, nick, host_servidor="127.0.0.1", porta_servidor=p.PORTA_SERVIDOR,
                 porta_local=0):
        self.nick = p.normalizar_nick(nick)
        self.host_servidor = host_servidor
        self.porta_servidor = porta_servidor
        self.interativo = sys.stdout.isatty()

        self.contatos = {}            # nick -> (ip, porta)
        self.seq_vistos = {}          # nick -> último seq recebido no grupo
        self.seq = 0
        self.conversa = None          # {"nick", "sock", "cx", "trava"}
        self.rodando = True
        self.trava_saida = threading.Lock()
        self.trava_conversa = threading.Lock()
        self.respostas = queue.Queue()   # linhas de resposta vindas da sessão de controle

        self._abrir_escuta(porta_local)
        self._conectar()

    # ------------------------------------------------------------------ sockets

    def _abrir_escuta(self, porta_local):
        """Listener TCP e socket UDP no MESMO número de porta (famílias independentes)."""
        for tentativa in range(10):
            ouvinte = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            ouvinte.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            try:
                ouvinte.bind(("0.0.0.0", porta_local))
                porta = ouvinte.getsockname()[1]
                udp = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
                udp.bind(("0.0.0.0", porta))
            except OSError:
                ouvinte.close()
                if porta_local:
                    raise SystemExit("[erro] porta %d já está em uso; escolha outra com --porta"
                                     % porta_local)
                continue  # porta efêmera colidiu no UDP: tenta outro número
            ouvinte.listen(4)
            self.ouvinte, self.porta, self.udp = ouvinte, porta, udp
            return
        raise SystemExit("[erro] não consegui reservar porta local para TCP e UDP")

    def _conectar(self):
        try:
            self.controle = socket.create_connection(
                (self.host_servidor, self.porta_servidor), timeout=6)
        except OSError as erro:
            raise SystemExit("[erro] servidor %s:%d inacessível (%s). Ele está no ar?"
                             % (self.host_servidor, self.porta_servidor, erro))
        self.cx = p.Conexao(self.controle)

    def registrar(self):
        while True:
            self.cx.enviar("REG", self.nick, self.porta)
            resposta = self.cx.linha(6) or ""
            if resposta.startswith("OK"):
                _, nick, ip, porta = p.separar(resposta, 4)
                self.nick = nick
                self.mostrar("[+] registrado como %s — servidor %s:%d registrou %s:%s"
                             % (nick, self.host_servidor, self.porta_servidor, ip, porta))
                return True
            if resposta.startswith("ERR 409"):
                self.mostrar("[erro] nick %r já está em uso." % self.nick)
                if not self.interativo:
                    return False
                novo = input("outro nick: ").strip()
                if not novo:
                    return False
                self.nick = p.normalizar_nick(novo)
                continue
            self.mostrar("[erro] registro recusado: %s" % (resposta or "sem resposta"))
            return False

    # ------------------------------------------------------------------ saída no terminal

    def _texto_prompt(self):
        if self.conversa:
            return "%s[%s]> " % (self.nick, self.conversa["nick"])
        return "%s> " % self.nick

    def mostrar(self, texto, redesenhar=None):
        """Escreve no terminal sem atropelar o que a pessoa digita.

        Mensagem que chega de thread de fundo (evento, grupo, P2P) precisa reimprimir o prompt,
        porque entrou em cima da linha de digitação. Resposta de comando sai do fluxo principal:
        o próprio `input()` imprime o prompt na volta, e redesenhar aqui deixaria um prompt sobrando.
        """
        if redesenhar is None:
            redesenhar = threading.current_thread() is not threading.main_thread()
        with self.trava_saida:
            if self.interativo:
                sys.stdout.write("\r\033[K" + texto + "\n")
                if redesenhar:
                    sys.stdout.write(self._texto_prompt())
            else:
                sys.stdout.write(texto + "\n")
            sys.stdout.flush()

    # ------------------------------------------------------------------ threads

    def iniciar_threads(self):
        for alvo, nome in ((self.rx_controle, "controle"), (self.rx_udp, "grupo"),
                           (self.aceitar, "listener")):
            threading.Thread(target=alvo, name=nome, daemon=True).start()

    def rx_controle(self):
        """Lê a sessão persistente: eventos vão para a tela, respostas vão para a fila."""
        while True:
            try:
                linha = self.cx.linha()
            except socket.timeout:
                continue  # socket.timeout é OSError, mas significa "silêncio", não "acabou"
            except OSError:
                break
            if linha is None:
                break
            if linha.startswith("EVENTO "):
                self._evento(linha)
            else:
                self.respostas.put(linha)
        self.rodando = False
        self.mostrar("[!] sessão com o servidor %s:%d encerrada"
                     % (self.host_servidor, self.porta_servidor))

    def _evento(self, linha):
        campos = p.separar(linha, 5)
        if len(campos) < 3 or campos[1] != "ENTROU":
            if len(campos) >= 3 and campos[1] == "SAIU":
                nick = campos[2]
                self.contatos.pop(nick, None)
                self.mostrar("[-] %s saiu" % nick)
            return
        nick, ip, porta = campos[2], campos[3], campos[4]
        self.contatos[nick] = (ip, int(porta) if porta.isdigit() else 0)
        self.mostrar("[+] %s entrou (%s:%s)" % (nick, ip, porta))

    def rx_udp(self):
        while True:
            try:
                dados, _ = self.udp.recvfrom(4096)
            except OSError:
                return
            linha = dados.decode("utf-8", "replace").strip()
            campos = p.separar(linha, 4)
            if len(campos) < 4 or campos[0] != "BCAST":
                continue
            _, autor, seq, texto = campos
            if autor == self.nick:
                continue  # já mostrei o eco local ao enviar
            numero = int(seq) if seq.isdigit() else 0
            anterior = self.seq_vistos.get(autor)
            if anterior is not None:
                perdidas = p.lacuna(anterior, numero)
                if perdidas:
                    self.mostrar("[grupo %s] (UDP) %d mensagem(ns) perdida(s)"
                                 % (autor, perdidas))
            self.seq_vistos[autor] = numero
            self.mostrar("[grupo %s] %s" % (autor, texto))

    def aceitar(self):
        while True:
            try:
                con, endereco = self.ouvinte.accept()
            except OSError:
                return
            threading.Thread(target=self._handshake_entrante, args=(con, endereco),
                             name="p2p-entrada", daemon=True).start()

    def _handshake_entrante(self, con, endereco):
        cx = p.Conexao(con)
        try:
            linha = cx.linha(5)
        except OSError:
            cx.fechar()
            return
        if not linha:
            cx.fechar()
            return
        campos = p.separar(linha, 2)
        if campos[0].upper() != "OI":
            cx.enviar("ERR", p.ERR_ENTRADA, "comando_invalido")
            cx.fechar()
            return
        nick = p.normalizar_nick(campos[1])
        registrado = self.contatos.get(nick)
        if not registrado:
            self.mostrar("[p2p] recusei %r: não está na minha lista" % nick)
            cx.enviar("ERR", p.ERR_DESCONHECIDO, "contato_desconhecido")
            cx.fechar()
            return
        if registrado[0] != endereco[0]:
            self.mostrar("[p2p] recusei %r: IP de origem %s não confere com o registrado %s"
                         % (nick, endereco[0], registrado[0]))
            cx.enviar("ERR", p.ERR_ORIGEM, "origem_invalida")
            cx.fechar()
            return
        with self.trava_conversa:
            if self.conversa:
                ocupado = True
            else:
                self.conversa = {"nick": nick, "sock": con, "cx": cx, "trava": threading.Lock()}
                ocupado = False
        if ocupado:
            self.mostrar("[p2p] %s tentou entrar, mas já estou em conversa" % nick)
            cx.enviar("OCUPADO")
            cx.fechar()
            return
        cx.enviar("OI-OK", self.nick)
        self.mostrar("[p2p] %s conectou (%s:%d) — /sair encerra" % (nick, endereco[0], endereco[1]))
        self._receber_par(nick, cx)

    def _receber_par(self, par, cx):
        while True:
            try:
                linha = cx.linha()
            except OSError:
                break
            if linha is None:
                self.mostrar("[p2p] %s encerrou a conversa" % par)
                break
            if linha == "TCHAU":
                self.mostrar("[p2p] %s encerrou a conversa" % par)
                break
            campos = p.separar(linha, 2)
            if campos[0] == "MSG":
                self.mostrar("%s> %s" % (par, campos[1]))
            else:
                self.mostrar("[p2p] %s mandou algo fora do protocolo: %r" % (par, linha))
        self._encerrar_conversa(mandar_tchau=False, quem=par)

    # ------------------------------------------------------------------ conversa P2P

    def abrir_p2p(self, alvo):
        alvo = p.normalizar_nick(alvo)
        if alvo == self.nick:
            self.mostrar("[p2p] você não pode conversar consigo mesmo")
            return
        with self.trava_conversa:
            if self.conversa:
                self.mostrar("[p2p] já estou em conversa com %s — /sair primeiro"
                             % self.conversa["nick"])
                return
        destino = self.contatos.get(alvo)
        if not destino:
            self.mostrar("[p2p] contato_offline: %r não está na lista (use /listar)" % alvo)
            return
        try:
            sock = socket.create_connection(destino, timeout=5)
        except OSError as erro:
            self.mostrar("[p2p] não consegui conectar em %s:%d (%s)"
                         % (destino[0], destino[1], erro))
            return
        cx = p.Conexao(sock)
        try:
            cx.enviar("OI", self.nick)
            resposta = cx.linha(5) or ""
        except OSError:
            cx.fechar()
            self.mostrar("[p2p] %s não respondeu ao handshake" % alvo)
            return
        if resposta.startswith("OI-OK"):
            with self.trava_conversa:
                self.conversa = {"nick": alvo, "sock": sock, "cx": cx,
                                 "trava": threading.Lock()}
            self.mostrar("[p2p] conectado a %s (%s:%d) — /sair encerra"
                         % (alvo, destino[0], destino[1]))
            threading.Thread(target=self._receber_par, args=(alvo, cx),
                             name="p2p-saida", daemon=True).start()
            return
        cx.fechar()
        if resposta.strip() == "OCUPADO":
            self.mostrar("[p2p] %s está em outra conversa" % alvo)
        else:
            self.mostrar("[p2p] %s recusou: %s" % (alvo, resposta or "sem resposta"))

    def enviar_msg(self, texto):
        conv = self.conversa
        if not conv:
            return
        with conv["trava"]:
            conv["cx"].enviar("MSG", texto)

    def _encerrar_conversa(self, mandar_tchau, quem=None):
        with self.trava_conversa:
            conv = self.conversa
            self.conversa = None
        if not conv:
            return
        if mandar_tchau:
            try:
                conv["cx"].enviar("TCHAU")
            except OSError:
                pass
        conv["cx"].fechar()
        self.mostrar("[p2p] conversa com %s encerrada" % (quem or conv["nick"]))

    # ------------------------------------------------------------------ comandos

    def listar(self):
        self._descartar_respostas_antigas()
        self.cx.enviar("LIST")
        cabecalho = self._resposta(6)
        if cabecalho is None:
            self.mostrar("[erro] o servidor não respondeu ao LIST — a sessão de controle caiu?")
            return
        if not cabecalho.startswith("LISTA "):
            self.mostrar("[erro] resposta inesperada do LIST: %r" % cabecalho)
            return
        try:
            total = int(cabecalho.split()[1])
        except (IndexError, ValueError):
            self.mostrar("[erro] cabeçalho de lista inválido: %r" % cabecalho)
            return
        contatos = {}
        for _ in range(total):
            linha = self._resposta(6) or ""
            campos = p.separar(linha, 4)
            if len(campos) < 4 or campos[0] != "CONTATO" or not campos[3].isdigit():
                self.mostrar("[erro] linha de contato inválida: %r" % linha)
                self._descartar_respostas_antigas()
                return
            contatos[campos[1]] = (campos[2], int(campos[3]))
        self._resposta(6)  # FIM
        self.contatos = contatos
        self.mostrar("[lista] %d contato(s)" % len(contatos))
        for nick, (ip, porta) in sorted(contatos.items()):
            marca = " (você)" if nick == self.nick else ""
            self.mostrar("   %-16s %s:%d%s" % (nick, ip, porta, marca))

    def _descartar_respostas_antigas(self):
        """Fila de respostas só deve conter o que o próximo comando vai ler."""
        while True:
            try:
                self.respostas.get_nowait()
            except queue.Empty:
                return

    def _resposta(self, timeout=6):
        try:
            return self.respostas.get(timeout=timeout)
        except queue.Empty:
            return None

    def grupo(self, texto):
        if not texto:
            self.mostrar("[grupo] uso: /grupo <texto>")
            return
        self.seq += 1
        self.udp.sendto(p.montar("BC", self.nick, self.seq, texto),
                        (self.host_servidor, self.porta_servidor))
        self.mostrar("[grupo %s] %s" % (self.nick, texto))

    def tratar(self, entrada):
        """Devolve False quando é hora de encerrar o cliente."""
        entrada = entrada.strip()
        if not entrada:
            return True
        if not entrada.startswith("/"):
            if self.conversa:
                self.enviar_msg(entrada)
            else:
                self.mostrar("(sem conversa aberta — use /p2p <nick> ou /grupo <texto>)")
            return True

        comando, _, argumento = entrada.partition(" ")
        comando = comando.lower()
        argumento = argumento.strip()
        try:
            return self._despachar(comando, argumento)
        except (OSError, ValueError) as erro:
            self.mostrar("[erro] falha ao executar %s: %s" % (comando, erro))
            return True

    def _despachar(self, comando, argumento):
        if comando == "/listar":
            self.listar()
        elif comando == "/p2p":
            if not argumento:
                self.mostrar("uso: /p2p <nick>")
            else:
                self.abrir_p2p(argumento)
        elif comando == "/grupo":
            self.grupo(argumento)
        elif comando == "/ajuda":
            self.mostrar(AJUDA)
        elif comando in ("/sair", "/quit", "/exit"):
            if self.conversa:
                self._encerrar_conversa(mandar_tchau=True)
                return True
            return False
        else:
            self.mostrar("comando desconhecido: %s (use /ajuda)" % comando)
        return True

    def encerrar(self):
        if self.conversa:
            self._encerrar_conversa(mandar_tchau=True)
        try:
            self.cx.enviar("BYE")
        except OSError:
            pass
        self.cx.fechar()
        for sock in (self.udp, self.ouvinte):
            try:
                sock.close()
            except OSError:
                pass
        self.rodando = False

    def loop(self):
        while self.rodando:
            try:
                entrada = input(self._texto_prompt() if self.interativo else "")
            except EOFError:
                break
            except KeyboardInterrupt:
                print()
                break
            if not self.tratar(entrada):
                break
        self.encerrar()


def main(argv=None):
    p.console_seguro()
    ap = argparse.ArgumentParser(description="Cliente do chat (Av3 — Redes de Computadores)")
    ap.add_argument("--nick", required=True, help="seu apelido (3-16: letras, números, _ e -)")
    ap.add_argument("--servidor", default="127.0.0.1", help="IP do servidor (padrão: 127.0.0.1)")
    ap.add_argument("--porta-servidor", type=int, default=p.PORTA_SERVIDOR,
                    help="porta do servidor (padrão: %d)" % p.PORTA_SERVIDOR)
    ap.add_argument("--porta", type=int, default=0,
                    help="porta local fixa para TCP e UDP (padrão: efêmera)")
    args = ap.parse_args(argv)

    if not p.nick_valido(args.nick):
        print("[erro] nick inválido: use de %d a %d caracteres entre letras, números, _ e -"
              % (p.NICK_MIN, p.NICK_MAX), file=sys.stderr)
        return 2

    cliente = Cliente(args.nick, args.servidor, args.porta_servidor, args.porta)
    if not cliente.registrar():
        return 1
    cliente.iniciar_threads()
    # R4 do enunciado: a lista de contatos é pedida no primeiro acesso ao servidor, não só
    # quando alguém digita /listar — senão quem entra depois não sabe com quem falar.
    cliente.listar()
    cliente.mostrar(AJUDA)
    cliente.loop()
    return 0


if __name__ == "__main__":
    sys.exit(main())
