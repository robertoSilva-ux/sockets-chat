#!/usr/bin/env python3
"""Servidor do chat — Av3 Redes de Computadores.

Dois canais na mesma porta 9990 (portas TCP e UDP são espaços independentes):

* **TCP 9990 — controle.** Sessão persistente por cliente: `REG` (nick + porta do cliente),
  `LIST` (lista de contatos) e `BYE`. O servidor empurra `EVENTO ENTROU/SAIU` para os demais.
* **UDP 9990 — grupo.** Recebe `BC <nick> <seq> <texto>` e reenvia `BCAST` ao endpoint UDP de
  cada contato registrado.

Estado compartilhado: `contatos` (dict) protegido por `self.lock`. Regra: o lock protege a
**estrutura**; o envio acontece fora dele, sobre um *snapshot* — um destinatário lento não pode
travar o registro dos outros. Ver docs/adr/ADR-0002.

Somente biblioteca padrão.
"""

import argparse
import socket
import sys
import threading
import time

import protocolo as p


def agora():
    return time.strftime("%H:%M:%S")


def log(texto):
    print("[%s] %s" % (agora(), texto), flush=True)


class Contato:
    """Um cliente registrado. `saida` é a conexão de controle usada para empurrar eventos."""

    __slots__ = ("nick", "ip", "porta", "saida", "trava_envio")

    def __init__(self, nick, ip, porta, saida):
        self.nick = nick
        self.ip = ip
        self.porta = porta
        self.saida = saida
        # envio serializado por contato: sessão, broadcast e lista podem escrever no mesmo socket
        self.trava_envio = threading.Lock()

    def enviar(self, *campos):
        with self.trava_envio:
            self.saida.enviar(*campos)


class Servidor:
    def __init__(self, host="0.0.0.0", porta=p.PORTA_SERVIDOR):
        self.host = host
        self.porta = porta
        self.contatos = {}
        self.lock = threading.Lock()
        self.total_grupo = 0
        self.tcp = self._abrir_tcp()
        self.udp = self._abrir_udp()

    # ---------------------------------------------------------------- sockets de escuta

    def _abrir_tcp(self):
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        try:
            sock.bind((self.host, self.porta))
        except OSError as erro:
            print("[erro] porta %d/TCP indisponível (%s)." % (self.porta, erro.strerror),
                  file=sys.stderr, flush=True)
            print("       quem está usando:  ss -ltnup 'sport = :%d'" % self.porta,
                  file=sys.stderr, flush=True)
            sock.close()
            raise SystemExit(2)
        sock.listen(16)
        return sock

    def _abrir_udp(self):
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        sock.bind((self.host, self.porta))
        return sock

    # ---------------------------------------------------------------- laços

    def servir(self):
        threading.Thread(target=self._laco_grupo, name="grupo", daemon=True).start()
        log("Servidor do chat no ar — TCP %s:%d (controle) e UDP %s:%d (grupo)"
            % (self.host, self.porta, self.host, self.porta))
        log("Ctrl+C para encerrar. Aguardando clientes...")
        try:
            while True:
                try:
                    con, endereco = self.tcp.accept()
                except OSError:
                    break
                threading.Thread(target=self._sessao, args=(con, endereco),
                                 name="sessao-%s:%d" % endereco, daemon=True).start()
        except KeyboardInterrupt:
            log("encerrando (Ctrl+C)")
        finally:
            for sock in (self.tcp, self.udp):
                try:
                    sock.close()
                except OSError:
                    pass
        return 0

    def _sessao(self, con, endereco):
        """Thread de controle de um cliente: lê comandos, responde, empurra eventos."""
        ip = endereco[0]
        cx = p.Conexao(con)
        nick = None
        encerrar = False
        try:
            while not encerrar:
                try:
                    linha = cx.linha()
                except p.ErroProtocolo as erro:
                    log("linha inválida de %s:%d (%s)" % (ip, endereco[1], erro))
                    cx.enviar("ERR", p.ERR_ENTRADA, str(erro))
                    continue
                except OSError:
                    break
                if linha is None:
                    break
                linha = linha.strip()
                if not linha:
                    continue
                nick, encerrar = self._tratar(cx, nick, ip, endereco, linha)
        except (ConnectionResetError, BrokenPipeError):
            pass
        finally:
            self._remover(nick, ip)
            cx.fechar()

    def _tratar(self, cx, nick, ip, endereco, linha):
        comando, _, resto = linha.partition(" ")
        comando = comando.upper()

        if comando == "REG":
            return self._registrar(cx, nick, ip, endereco, resto), False
        if nick is None:
            log("%s:%d tentou %s sem registro" % (ip, endereco[1], comando))
            cx.enviar("ERR", p.ERR_NAO_REGISTRADO, "nao_registrado")
            return nick, False
        if comando == "LIST":
            self._listar(cx)
            return nick, False
        if comando == "BYE":
            cx.enviar("BYE")
            log("%s pediu para sair" % nick)
            return nick, True
        log("%s enviou comando inválido: %r" % (nick, linha))
        cx.enviar("ERR", p.ERR_ENTRADA, "comando_invalido")
        return nick, False

    def _registrar(self, cx, nick_atual, ip, endereco, resto):
        if nick_atual is not None:
            cx.enviar("ERR", p.ERR_ENTRADA, "ja_registrado")
            return nick_atual
        campos = p.separar(resto.strip(), 2)
        if len(campos) < 2 or not campos[0]:
            cx.enviar("ERR", p.ERR_ENTRADA, "nick_invalido")
            return None
        nick = p.normalizar_nick(campos[0])
        if not p.nick_valido(nick):
            log("registro recusado: nick inválido %r de %s" % (campos[0], ip))
            cx.enviar("ERR", p.ERR_ENTRADA, "nick_invalido")
            return None
        try:
            porta = int(campos[1])
        except ValueError:
            cx.enviar("ERR", p.ERR_ENTRADA, "porta_invalida")
            return None
        if not p.porta_valida(porta):
            cx.enviar("ERR", p.ERR_ENTRADA, "porta_invalida")
            return None

        with self.lock:
            if nick in self.contatos:
                ocupado = True
            else:
                self.contatos[nick] = Contato(nick, ip, porta, cx)
                ocupado = False
        if ocupado:
            log("registro recusado: nick %r já em uso (pedido de %s)" % (nick, ip))
            cx.enviar("ERR", p.ERR_EM_USO, "nick_em_uso")
            return None

        cx.enviar("OK", nick, ip, porta)
        log("REG %s %s:%d (%d contato(s) no total)" % (nick, ip, porta, len(self.contatos)))
        self._avisar("EVENTO", "ENTROU", nick, ip, porta, exceto=nick)
        return nick

    def _listar(self, cx):
        with self.lock:
            contatos = list(self.contatos.values())
        cx.enviar("LISTA", len(contatos))
        for c in contatos:
            cx.enviar("CONTATO", c.nick, c.ip, c.porta)
        cx.enviar("FIM")

    def _avisar(self, *campos, exceto=None):
        """Empurra um evento a todos os contatos (fora do lock)."""
        with self.lock:
            destinos = [c for c in self.contatos.values() if c.nick != exceto]
        for contato in destinos:
            try:
                contato.enviar(*campos)
            except OSError:
                pass  # cliente sumiu: a sessão dele vai limpar o contato

    def _remover(self, nick, ip):
        if not nick:
            return
        with self.lock:
            contato = self.contatos.get(nick)
            removido = self.contatos.pop(nick) if contato and contato.ip == ip else None
        if removido:
            log("SAIU %s %s:%d (%d contato(s) no total)"
                % (nick, ip, removido.porta, len(self.contatos)))
            self._avisar("EVENTO", "SAIU", nick, exceto=nick)

    # ---------------------------------------------------------------- canal de grupo (UDP)

    def _laco_grupo(self):
        while True:
            try:
                dados, origem = self.udp.recvfrom(4096)
            except OSError:
                return  # socket fechado no encerramento
            linha = dados.decode("utf-8", "replace").strip()
            if not linha:
                continue
            try:
                self._repassar_grupo(linha, origem)
            except Exception as erro:  # noqa: BLE001 - o laço do grupo não pode morrer
                log("erro no grupo: %r" % erro)

    def _repassar_grupo(self, linha, origem):
        comando, _, resto = linha.partition(" ")
        if comando.upper() != "BC":
            log("UDP ignorado de %s:%d: %r" % (origem[0], origem[1], linha[:40]))
            return
        campos = p.separar(resto.strip(), 3)
        if len(campos) < 3 or not campos[0]:
            log("BC malformado de %s:%d" % origem)
            return
        nick, seq, texto = campos
        nick = p.normalizar_nick(nick)

        # Identidade em UDP não existe: só vale se o endpoint de origem for o registrado.
        with self.lock:
            autor = self.contatos.get(nick)
            autorizado = autor is not None and autor.ip == origem[0] and autor.porta == origem[1]
            destinos = [(c.ip, c.porta) for c in self.contatos.values()]
        if not autorizado:
            log("BC rejeitado de %s:%d (diz ser %r)" % (origem[0], origem[1], nick))
            return

        linha_saida = p.montar("BCAST", nick, seq, texto)
        enviados = 0
        for destino in destinos:
            try:
                self.udp.sendto(linha_saida, destino)
                enviados += 1
            except OSError as erro:
                log("falha ao enviar BCAST para %s:%d (%s)" % (destino[0], destino[1], erro))
        self.total_grupo += 1
        log('BC de %s %s:%d seq=%s "%s" -> %d destinatario(s)'
            % (nick, origem[0], origem[1], seq, texto, enviados))


def main(argv=None):
    ap = argparse.ArgumentParser(description="Servidor do chat (Av3 — Redes de Computadores)")
    ap.add_argument("--host", default="0.0.0.0", help="endereço de escuta (padrão: todas as interfaces)")
    ap.add_argument("--porta", type=int, default=p.PORTA_SERVIDOR,
                    help="porta TCP e UDP (padrão: %d)" % p.PORTA_SERVIDOR)
    args = ap.parse_args(argv)
    servidor = Servidor(args.host, args.porta)
    try:
        return servidor.servir()
    except KeyboardInterrupt:
        return 0


if __name__ == "__main__":
    sys.exit(main())
