#!/usr/bin/env python3
"""Testes do cliente de verdade — processo `cliente.py` com stdin/stdout em pipe.

Cada teste sobe o servidor e os clientes como processos separados e conversa com eles
digitando comandos, exatamente como a pessoa faria. É a prova de execução real dos cartões
E2 (presença/lista), E3 (P2P) e E4 (grupo), e da robustez do E5.

    python3 testes/teste_cliente.py [-k parte_do_nome]
"""

import pathlib
import subprocess
import sys
import threading
import time

RAIZ = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ))
sys.path.insert(0, str(RAIZ / "testes"))

import protocolo as p  # noqa: E402
from teste_protocolo import Servidor  # noqa: E402  (reaproveita o servidor em subprocesso)

CLIENTE = RAIZ / "cliente.py"


class ClienteProc:
    """Um `cliente.py` rodando, com a saída lida linha a linha em thread."""

    def __init__(self, nick, porta_servidor, porta=0, timeout=8.0):
        argumentos = [sys.executable, "-u", str(CLIENTE), "--nick", nick,
                      "--porta-servidor", str(porta_servidor)]
        if porta:
            argumentos += ["--porta", str(porta)]
        self.proc = subprocess.Popen(argumentos, cwd=str(RAIZ), stdin=subprocess.PIPE,
                                     stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                                     text=True, bufsize=1)
        self.nick = nick
        self.linhas = []
        self._trava = threading.Lock()
        self._lidas = 0
        threading.Thread(target=self._ler, daemon=True).start()
        assert self.esperar("[+] registrado como", timeout), \
            "cliente %s não registrou: %s" % (nick, self.saida())

    def _ler(self):
        for linha in self.proc.stdout:
            with self._trava:
                self.linhas.append(linha.rstrip("\n"))

    def saida(self):
        with self._trava:
            return "\n".join(self.linhas)

    def esperar(self, padrao, timeout=8.0):
        """Espera uma linha (a partir da última consumida) que contenha `padrao`."""
        fim = time.time() + timeout
        while time.time() < fim:
            with self._trava:
                pendentes = self.linhas[self._lidas:]
            for i, linha in enumerate(pendentes):
                if padrao in linha:
                    with self._trava:
                        self._lidas += i + 1
                    return linha
            if self.proc.poll() is not None and not pendentes:
                return None
            time.sleep(0.05)
        return None

    def exigir(self, padrao, timeout=8.0):
        linha = self.esperar(padrao, timeout)
        assert linha is not None, "esperava %r de %s; saída:\n%s" % (padrao, self.nick, self.saida())
        return linha

    def digitar(self, texto):
        try:
            self.proc.stdin.write(texto + "\n")
            self.proc.stdin.flush()
        except (BrokenPipeError, ValueError):
            raise AssertionError("%s já encerrou; não dá para digitar %r\n%s"
                                 % (self.nick, texto, self.saida()))
        time.sleep(0.05)

    def sem_traceback(self):
        assert "Traceback" not in self.saida(), "%s imprimiu traceback:\n%s" % (self.nick, self.saida())

    def fechar(self):
        """Um /sair encerra a conversa aberta; o segundo sai do chat. Manda os dois."""
        for _ in range(2):
            if self.proc.poll() is not None:
                break
            try:
                self.proc.stdin.write("/sair\n")
                self.proc.stdin.flush()
            except (OSError, ValueError):
                break
            try:
                self.proc.wait(timeout=2)
                break
            except subprocess.TimeoutExpired:
                continue
        if self.proc.poll() is None:
            self.proc.kill()
            self.proc.wait(timeout=3)
        try:
            self.proc.stdin.close()
        except (OSError, ValueError):
            pass

    def matar(self):
        self.proc.kill()
        self.proc.wait(timeout=3)


def tres_clientes(srv):
    """Sobe ana, bruno e carla já registrados, na ordem."""
    return (ClienteProc("ana", srv.porta), ClienteProc("bruno", srv.porta),
            ClienteProc("carla", srv.porta))


# --------------------------------------------------------------------------- E2: lista e presença

def test_cliente_lista_contatos():
    with Servidor() as srv:
        ana, bruno, carla = tres_clientes(srv)
        try:
            ana.digitar("/listar")
            ana.exigir("[lista] 3 contato(s)")
            ana.exigir("bruno")
            ana.exigir("carla")
            for c in (ana, bruno, carla):
                c.sem_traceback()
        finally:
            for c in (ana, bruno, carla):
                c.fechar()


def test_cliente_eventos_presenca():
    with Servidor() as srv:
        ana = ClienteProc("ana", srv.porta)
        bruno = ClienteProc("bruno", srv.porta)
        ana.exigir("[+] bruno entrou")
        bruno.fechar()
        ana.exigir("[-] bruno saiu")
        ana.digitar("/listar")
        ana.exigir("[lista] 1 contato(s)")
        ana.fechar()


def test_cliente_nick_duplicado():
    with Servidor() as srv:
        ana = ClienteProc("ana", srv.porta)
        segundo = subprocess.run([sys.executable, str(CLIENTE), "--nick", "ana",
                                  "--porta-servidor", str(srv.porta)],
                                 capture_output=True, text=True, timeout=15, input="")
        saida = segundo.stdout + segundo.stderr
        assert "já está em uso" in saida, "faltou o aviso de nick em uso: %r" % saida
        assert "Traceback" not in saida
        ana.fechar()


# --------------------------------------------------------------------------- E3: ponto a ponto

def test_p2p_direto():
    with Servidor() as srv:
        ana, bruno = ClienteProc("ana", srv.porta), ClienteProc("bruno", srv.porta)
        try:
            ana.digitar("/listar")
            ana.exigir("[lista] 2 contato(s)")
            marcador = srv.marcador()

            ana.digitar("/p2p bruno")
            ana.exigir("[p2p] conectado a bruno")
            bruno.exigir("[p2p] ana conectou")

            ana.digitar("oi bruno, tudo bem?")
            bruno.exigir("ana> oi bruno, tudo bem?")
            bruno.digitar("tudo! conseguiu rodar o servidor?")
            ana.exigir("bruno> tudo! conseguiu rodar o servidor?")

            # a conversa não passa pelo servidor
            log = srv.log_apos(marcador)
            assert "MSG" not in log, "o servidor viu mensagem de P2P:\n%s" % log
            assert "oi bruno" not in log, "texto da conversa apareceu no log do servidor"

            ana.digitar("/sair")
            ana.exigir("[p2p] conversa com bruno encerrada")
            bruno.exigir("[p2p] ana encerrou a conversa")
            for c in (ana, bruno):
                c.sem_traceback()
        finally:
            ana.fechar()
            bruno.fechar()


def test_p2p_ocupado():
    with Servidor() as srv:
        ana, bruno, carla = tres_clientes(srv)
        try:
            for c in (ana, carla):
                c.digitar("/listar")
                c.exigir("[lista] 3 contato(s)")
            ana.digitar("/p2p bruno")
            ana.exigir("[p2p] conectado a bruno")
            carla.digitar("/p2p bruno")
            carla.exigir("[p2p] bruno está em outra conversa")
            # a conversa de ana continua funcionando
            ana.digitar("ainda estou aqui")
            bruno.exigir("ana> ainda estou aqui")
        finally:
            for c in (ana, bruno, carla):
                c.fechar()


def test_p2p_contato_offline():
    with Servidor() as srv:
        ana = ClienteProc("ana", srv.porta)
        ana.digitar("/listar")
        ana.exigir("[lista] 1 contato(s)")
        ana.digitar("/p2p fantasma")
        ana.exigir("contato_offline")
        ana.sem_traceback()
        ana.fechar()


# --------------------------------------------------------------------------- E4: grupo

def test_grupo_pelo_cliente():
    with Servidor() as srv:
        ana, bruno, carla = tres_clientes(srv)
        try:
            ana.digitar("/grupo reuniao 19h na sala 12")
            ana.exigir("[grupo ana] reuniao 19h na sala 12")      # eco local
            bruno.exigir("[grupo ana] reuniao 19h na sala 12")
            carla.exigir("[grupo ana] reuniao 19h na sala 12")
            bruno.digitar("/grupo recebido")
            ana.exigir("[grupo bruno] recebido")
            carla.exigir("[grupo bruno] recebido")
            for c in (ana, bruno, carla):
                c.sem_traceback()
        finally:
            for c in (ana, bruno, carla):
                c.fechar()


# --------------------------------------------------------------------------- E5: robustez

def test_queda_abrupta_de_cliente():
    with Servidor() as srv:
        ana, bruno = ClienteProc("ana", srv.porta), ClienteProc("bruno", srv.porta)
        ana.exigir("[+] bruno entrou")
        bruno.matar()                       # kill -9, sem BYE
        ana.exigir("[-] bruno saiu", timeout=6)
        ana.digitar("/listar")
        ana.exigir("[lista] 1 contato(s)")
        ana.fechar()
        assert "Traceback" not in srv.log(), "servidor imprimiu traceback:\n%s" % srv.log()


def test_listar_depois_de_ociosidade():
    """Silêncio não pode derrubar a sessão: 8 s parado e o /listar ainda responde.

    Regressão real: `registrar()` deixava `settimeout(6)` grudado no socket de controle; a
    thread de leitura estourava aos 6 s de silêncio e o cliente anunciava "conexão encerrada"
    com o servidor perfeitamente vivo.
    """
    with Servidor() as srv:
        ana = ClienteProc("ana", srv.porta)
        bruno = ClienteProc("bruno", srv.porta)
        ana.exigir("[+] bruno entrou")
        time.sleep(8.0)
        assert "conexão com o servidor foi encerrada" not in ana.saida(), \
            "cliente achou que a conexão caiu durante o silêncio:\n%s" % ana.saida()
        ana.digitar("/listar")
        ana.exigir("[lista] 2 contato(s)")
        ana.exigir("bruno")
        # e o caminho de fundo continua vivo: bruno saindo chega em ana
        bruno.fechar()
        ana.exigir("[-] bruno saiu")
        ana.sem_traceback()
        ana.fechar()


def test_servidor_encerra_avisa_cliente():
    with Servidor() as srv:
        ana = ClienteProc("ana", srv.porta)
        srv.proc.terminate()
        ana.exigir("conexão com o servidor foi encerrada", timeout=6)
        ana.sem_traceback()
        ana.fechar()


def test_mensagem_longa_pelo_cliente():
    with Servidor() as srv:
        ana, bruno = ClienteProc("ana", srv.porta), ClienteProc("bruno", srv.porta)
        try:
            ana.digitar("/listar")
            ana.exigir("[lista] 2 contato(s)")
            ana.digitar("/p2p bruno")
            ana.exigir("[p2p] conectado a bruno")
            bruno.exigir("[p2p] ana conectou")
            ana.digitar("y" * 3000)
            linha = bruno.exigir("ana> ")
            assert len(linha.encode("utf-8")) <= p.MAX_LINHA, \
                "linha acima de MAX_LINHA chegou ao par: %d bytes" % len(linha.encode("utf-8"))
            assert p.MARCA_TRUNCADO in linha, "faltou marca de truncamento"
            for c in (ana, bruno):
                c.sem_traceback()
        finally:
            ana.fechar()
            bruno.fechar()


# --------------------------------------------------------------------------- runner

def principal(argv):
    filtro = argv[argv.index("-k") + 1] if "-k" in argv else ""
    testes = [(n, f) for n, f in sorted(globals().items())
              if n.startswith("test_") and callable(f) and filtro in n]
    if not testes:
        print("nenhum teste casa com %r" % filtro)
        return 2
    falhas = 0
    for nome, fn in testes:
        inicio = time.time()
        try:
            fn()
            print("ok    %-38s %.2fs" % (nome, time.time() - inicio))
        except Exception as erro:  # noqa: BLE001 - harness
            falhas += 1
            print("FALHA %-38s %s: %s" % (nome, type(erro).__name__, erro))
    print("\n%d teste(s), %d falha(s)" % (len(testes), falhas))
    return 1 if falhas else 0


if __name__ == "__main__":
    sys.exit(principal(sys.argv[1:]))
