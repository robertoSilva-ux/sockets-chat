#!/usr/bin/env python3
"""Suíte do protocolo — só stdlib, sem framework.

Sobe o servidor de verdade (subprocesso, porta livre) e fala com ele por sockets crus:
cada critério de aceite dos cartões E1..E5 vira um teste nomeado.

    python3 testes/teste_protocolo.py            # tudo
    python3 testes/teste_protocolo.py -k controle  # filtra por pedaço do nome
"""

import pathlib
import socket
import subprocess
import sys
import threading
import time

RAIZ = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ))

import protocolo as p  # noqa: E402  (o próprio módulo de contrato é testado aqui)

SERVIDOR = RAIZ / "servidor.py"


# --------------------------------------------------------------------------- apoio

def porta_livre():
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    s.bind(("127.0.0.1", 0))
    porta = s.getsockname()[1]
    s.close()
    return porta


class Servidor:
    """Servidor em subprocesso, com o log capturado linha a linha para os testes que o inspecionam."""

    def __init__(self, porta=None, limite=5.0):
        self.porta = porta or porta_livre()
        self.proc = subprocess.Popen(
            [sys.executable, str(SERVIDOR), "--host", "127.0.0.1", "--porta", str(self.porta)],
            cwd=str(RAIZ), stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, bufsize=1,
        )
        self.linhas = []
        self._trava = threading.Lock()
        threading.Thread(target=self._ler_log, daemon=True).start()
        self._esperar(limite)

    def _ler_log(self):
        for linha in self.proc.stdout:
            with self._trava:
                self.linhas.append(linha.rstrip())

    def _esperar(self, limite):
        fim = time.time() + limite
        while time.time() < fim:
            if self.proc.poll() is not None:
                raise RuntimeError("servidor morreu ao subir: " + self.log())
            try:
                socket.create_connection(("127.0.0.1", self.porta), timeout=0.2).close()
                return
            except OSError:
                time.sleep(0.05)
        raise RuntimeError("servidor nao abriu a porta %d" % self.porta)

    def log(self):
        with self._trava:
            return "\n".join(self.linhas)

    def marcador(self):
        with self._trava:
            return len(self.linhas)

    def log_apos(self, marcador):
        with self._trava:
            return "\n".join(self.linhas[marcador:])

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        self.proc.terminate()
        try:
            self.proc.wait(timeout=5)
        except subprocess.TimeoutExpired:
            self.proc.kill()
            self.proc.wait(timeout=5)


class Cliente:
    """Cliente cru: sessão de controle TCP, listener TCP (P2P) e socket UDP (grupo)."""

    def __init__(self, porta_servidor, host="127.0.0.1", anunciar=None):
        self.host = host
        # listener TCP: é a porta que anunciamos no REG (P2P entrante)
        self.ouvinte = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.ouvinte.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self.ouvinte.bind((host, anunciar or 0))
        self.porta = self.ouvinte.getsockname()[1]
        self.ouvinte.listen(4)
        # socket UDP de grupo: mesma porta, família independente
        self.udp = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self.udp.bind((host, self.porta))
        self.udp.settimeout(3)
        self.sock = socket.create_connection((host, porta_servidor), timeout=3)
        self.cx = p.Conexao(self.sock)
        self.porta_servidor = porta_servidor
        self.nick = None
        self.seq = 0
        self.eventos = []

    def enviar(self, *campos):
        self.cx.enviar(*campos)

    def linha(self, timeout=3):
        return self.cx.linha(timeout)

    def _resposta(self, timeout=3):
        """Lê a próxima linha que não seja evento: eventos vão para self.eventos."""
        while True:
            linha = self.cx.linha(timeout)
            if linha is None:
                raise EOFError("conexao fechada pelo servidor")
            if linha.startswith("EVENTO "):
                self.eventos.append(linha)
                continue
            return linha

    def proximo_evento(self, timeout=3):
        if self.eventos:
            return self.eventos.pop(0)
        while True:
            linha = self.cx.linha(timeout)
            if linha is None:
                raise EOFError("conexao fechada pelo servidor")
            if linha.startswith("EVENTO "):
                return linha

    def registra(self, nick):
        self.enviar("REG", nick, self.porta)
        resposta = self._resposta()
        if resposta.startswith("OK"):
            self.nick = nick
        return resposta

    def lista(self):
        """Devolve [(nick, ip, porta)] a partir do LIST."""
        self.enviar("LIST")
        cabecalho = self._resposta()
        assert cabecalho.startswith("LISTA "), "esperava LISTA, veio %r" % cabecalho
        total = int(cabecalho.split()[1])
        contatos = []
        for _ in range(total):
            linha = self._resposta()
            _, nick, ip, porta = linha.split(" ", 3)
            contatos.append((nick, ip, int(porta)))
        assert self._resposta() == "FIM", "LIST sem FIM"
        return contatos

    def grupo(self, texto):
        self.seq += 1
        self.udp.sendto(p.montar("BC", self.nick, self.seq, texto), (self.host, self.porta_servidor))

    def receber(self, timeout=3):
        self.udp.settimeout(timeout)
        dados, _ = self.udp.recvfrom(4096)
        return dados.decode("utf-8").strip()

    def sem_mensagem(self, espera=0.6):
        self.udp.settimeout(espera)
        try:
            return self.udp.recvfrom(4096) is None
        except socket.timeout:
            return True

    def fechar(self):
        try:
            self.enviar("BYE")
            self.linha(timeout=1)
        except (OSError, EOFError):
            pass
        for sock in (self.sock, self.udp, self.ouvinte):
            try:
                sock.close()
            except OSError:
                pass


# --------------------------------------------------------------------------- E1: controle

def test_aceita_tres_clientes():
    with Servidor() as srv:
        clientes = [Cliente(srv.porta) for _ in range(3)]
        for i, c in enumerate(clientes):
            assert c.registra("user%d" % i).startswith("OK"), "registro recusado"
        contatos = clientes[0].lista()
        assert len(contatos) == 3, "LISTA devia ter 3, veio %r" % (contatos,)
        for c in clientes:
            c.fechar()


def test_registro_e_dup():
    with Servidor() as srv:
        a, b = Cliente(srv.porta), Cliente(srv.porta)
        assert a.registra("ana").startswith("OK")
        resposta = b.registra("ANA")
        assert resposta.startswith("ERR 409"), "nick deve ser case-insensitive, veio %r" % resposta
        # a sessão recusada continua viva: dá para registrar com outro nick
        assert b.registra("bia").startswith("OK"), "sessao deveria seguir aberta apos 409"
        a.fechar()
        b.fechar()


def test_list_mostra_ip_e_porta():
    with Servidor() as srv:
        a, b = Cliente(srv.porta), Cliente(srv.porta)
        a.registra("ana")
        b.registra("bruno")
        contatos = dict((n, (ip, pt)) for n, ip, pt in a.lista())
        assert contatos["bruno"] == ("127.0.0.1", b.porta), "ip/porta do bruno errados: %r" % contatos
        assert contatos["ana"] == ("127.0.0.1", a.porta)
        a.fechar()
        b.fechar()


def test_list_antes_de_reg():
    with Servidor() as srv:
        a = Cliente(srv.porta)
        a.enviar("LIST")
        resposta = a.linha()
        assert resposta.startswith("ERR 401"), "esperava 401, veio %r" % resposta
        a.fechar()


def test_bye_remove_contato():
    with Servidor() as srv:
        a, b = Cliente(srv.porta), Cliente(srv.porta)
        a.registra("ana")
        b.registra("bruno")
        b.fechar()
        time.sleep(0.3)
        assert [n for n, _, _ in a.lista()] == ["ana"], "contato do bruno deveria ter saido"
        a.fechar()


def test_evento_entrou_saiu():
    with Servidor() as srv:
        a = Cliente(srv.porta)
        a.registra("ana")
        b = Cliente(srv.porta)
        b.registra("bruno")
        evento = a.proximo_evento(2)
        assert evento.startswith("EVENTO ENTROU bruno "), "esperava ENTROU, veio %r" % evento
        b.fechar()
        evento = a.proximo_evento(2)
        assert evento == "EVENTO SAIU bruno", "esperava SAIU, veio %r" % evento
        a.fechar()


def test_entradas_invalidas():
    with Servidor() as srv:
        a = Cliente(srv.porta)
        assert a.registra("an").startswith("ERR 400"), "nick curto devia ser recusado"
        assert a.registra("ana silva").startswith("ERR 400"), "porta nao numerica devia ser recusada"
        a2 = Cliente(srv.porta)
        a2.enviar("REG", "bruno", "99999")
        assert a2.linha().startswith("ERR 400"), "porta fora do intervalo devia ser recusada"
        a2.enviar("REG", "bruno", "abc")
        assert a2.linha().startswith("ERR 400"), "porta nao numerica devia ser recusada"
        a2.enviar("XYZ")
        assert a2.linha() == "ERR 401 nao_registrado", "comando antes do REG devia dar 401"
        a2.enviar("REG", "bruno", a2.porta)
        assert a2.linha().startswith("OK"), "sessao deveria seguir viva"
        a2.enviar("XYZ")
        assert a2.linha() == "ERR 400 comando_invalido", "comando desconhecido devia dar 400"
        a.fechar()
        a2.fechar()


def test_porta_ocupada():
    with Servidor() as srv:
        segundo = subprocess.run(
            [sys.executable, str(SERVIDOR), "--host", "127.0.0.1", "--porta", str(srv.porta)],
            capture_output=True, text=True, timeout=10,
        )
        saida = segundo.stdout + segundo.stderr
        assert segundo.returncode == 2, "esperava exit 2, veio %d (%s)" % (segundo.returncode, saida)
        assert "indispon" in saida, "faltou a mensagem de porta ocupada: %r" % saida
        assert "Traceback" not in saida


def test_linha_longa():
    """Mandante que estoura o limite recebe ERR e a sessão continua viva."""
    with Servidor() as srv:
        a = Cliente(srv.porta)
        a.sock.sendall(b"A" * 5000 + b"\n")  # terminada, mas acima de MAX_LINHA
        primeira = a.linha(3)
        assert primeira == "ERR 400 linha_longa", "esperava ERR 400 linha_longa, veio %r" % primeira
        a.enviar("REG", "ana", a.porta)
        assert a.linha(3).startswith("OK"), "sessao devia sobreviver a linha longa"
        a.fechar()


# --------------------------------------------------------------------------- E4: grupo (lado servidor)

def test_grupo_tres_destinatarios():
    with Servidor() as srv:
        clientes = [Cliente(srv.porta) for _ in range(3)]
        for i, c in enumerate(clientes):
            c.registra("user%d" % i)
        ana, bruno, carla = clientes
        ana.udp.sendto(p.montar("BC", "user0", 1, "reuniao 19h"), ("127.0.0.1", srv.porta))
        for c in (bruno, carla, ana):
            recebido = c.receber(3)
            assert recebido == "BCAST user0 1 reuniao 19h", "recebido %r" % recebido
        time.sleep(0.2)
        assert "-> 3 destinatario(s)" in srv.log(), "log nao contou os destinatarios: %s" % srv.log()
        for c in clientes:
            c.fechar()


def test_grupo_remetente_falsificado():
    with Servidor() as srv:
        ana = Cliente(srv.porta)
        ana.registra("ana")
        bruno = Cliente(srv.porta)
        bruno.registra("bruno")
        ana.proximo_evento(2)  # EVENTO ENTROU bruno
        # socket UDP que não é o endpoint registrado de ninguém, dizendo ser ana
        falso = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        falso.bind(("127.0.0.1", 0))
        falso.sendto(p.montar("BC", "ana", 1, "sou a ana"), ("127.0.0.1", srv.porta))
        assert bruno.sem_mensagem(0.8), "cliente recebeu datagrama de remetente falsificado"
        assert "BC rejeitado" in srv.log(), "servidor devia registrar a rejeicao"
        falso.close()
        ana.fechar()
        bruno.fechar()


def test_grupo_texto_truncado():
    with Servidor() as srv:
        ana = Cliente(srv.porta)
        ana.registra("ana")
        grande = "x" * 3000
        datagrama = p.montar("BC", "ana", 1, grande)
        assert len(datagrama) <= p.MAX_LINHA, "montar() nao respeitou MAX_LINHA: %d" % len(datagrama)
        assert p.MARCA_TRUNCADO.encode() in datagrama, "faltou a marca de truncamento"
        ana.udp.sendto(datagrama, ("127.0.0.1", srv.porta))
        recebido = ana.receber(3)
        assert recebido.startswith("BCAST ana 1 ") and recebido.endswith(p.MARCA_TRUNCADO)
        ana.fechar()


# --------------------------------------------------------------------------- contrato puro

def test_contrato_separar_e_lacuna():
    assert p.separar("MSG oi, tudo bem?", 2) == ["MSG", "oi, tudo bem?"]
    assert p.separar("REG ana 5000", 3) == ["REG", "ana", "5000"]
    assert p.separar("BYE", 3) == ["BYE", "", ""]
    assert p.lacuna(7, 8) == 0
    assert p.lacuna(7, 10) == 2
    assert p.lacuna(7, 7) == 0
    assert p.nick_valido("ana") and p.nick_valido("A_1-b")
    assert not p.nick_valido("an") and not p.nick_valido("ana silva") and not p.nick_valido("josé")
    assert p.porta_valida(5000) and not p.porta_valida(80) and not p.porta_valida(70000)


def test_leitor_linhas_junta_pedacos():
    """O leitor precisa montar uma linha que chegou em três pedaços (TCP é fluxo)."""
    servidor = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    servidor.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    servidor.bind(("127.0.0.1", 0))
    servidor.listen(1)
    porta = servidor.getsockname()[1]

    def manda_pedacos():
        con, _ = servidor.accept()
        con.sendall(b"MSG primei")
        time.sleep(0.05)
        con.sendall(b"ra parte\nMSG segunda")
        time.sleep(0.05)
        con.sendall(b" parte\n")
        con.close()
        servidor.close()

    threading.Thread(target=manda_pedacos, daemon=True).start()
    sock = socket.create_connection(("127.0.0.1", porta), timeout=3)
    leitor = p.LeitorLinhas(sock)
    assert leitor.linha(3) == "MSG primeira parte"
    assert leitor.linha(3) == "MSG segunda parte"
    assert leitor.linha(3) is None
    sock.close()


# --------------------------------------------------------------------------- runner

def principal(argv):
    filtro = ""
    if "-k" in argv:
        filtro = argv[argv.index("-k") + 1]
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
