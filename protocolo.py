#!/usr/bin/env python3
"""Contrato de fio do chat — módulo comum ao servidor e ao cliente.

Aqui fica **somente** o que é contrato: enquadramento em linhas, validação de identidade e
montagem/leitura de comandos. Nenhuma política de aplicação mora neste arquivo.
O contrato completo (comandos, respostas, códigos de erro, limites) está em `docs/PROTOCOLO.md`.

Somente biblioteca padrão — a atividade proíbe biblioteca pronta de rede.
"""

import socket

PORTA_SERVIDOR = 9990

# Enquadramento (docs/PROTOCOLO.md §1)
MAX_LINHA = 1024              # bytes por linha, incluindo o "\n"
BUFFER_MAX = 4 * MAX_LINHA    # teto do leitor: acima disso, desiste da linha e reclama
MARCA_TRUNCADO = "…"

# Identidade (docs/PROTOCOLO.md §3)
NICK_MIN, NICK_MAX = 3, 16
CARACTERES_NICK = set("abcdefghijklmnopqrstuvwxyz0123456789_-")
PORTA_MIN, PORTA_MAX = 1024, 65535

# Códigos de erro (docs/PROTOCOLO.md §7)
ERR_ENTRADA = 400
ERR_NAO_REGISTRADO = 401
ERR_ORIGEM = 403
ERR_DESCONHECIDO = 404
ERR_EM_USO = 409
ERR_OFFLINE = 410


class ErroProtocolo(Exception):
    """Linha inválida vinda da rede. Tratada no laço de leitura, nunca mata o processo."""


def normalizar_nick(nick):
    """Nicks são case-insensitive: 'Ana' e 'ana' são o mesmo contato."""
    return nick.strip().lower()


def nick_valido(nick):
    n = normalizar_nick(nick)
    return NICK_MIN <= len(n) <= NICK_MAX and all(c in CARACTERES_NICK for c in n)


def porta_valida(porta):
    return isinstance(porta, int) and PORTA_MIN <= porta <= PORTA_MAX


def separar(linha, n_campos):
    """Divide a linha em n_campos; o último campo consome o resto (texto livre com espaços).

    'MSG oi, tudo bem?' com n_campos=2 -> ('MSG', 'oi, tudo bem?')
    """
    campos = []
    resto = linha
    for _ in range(n_campos - 1):
        campo, separador, resto = resto.partition(" ")
        campos.append(campo)
        if not separador:
            campos.extend([""] * (n_campos - len(campos)))
            return campos
    campos.append(resto)
    return campos


def montar(*campos):
    """Junta os campos numa linha UTF-8 terminada em "\\n".

    Se a linha passar de MAX_LINHA, o último campo é cortado em fronteira de caractere e
    recebe a marca de truncamento — o protocolo nunca fragmenta uma mensagem em duas linhas.
    """
    partes = [str(c) for c in campos]
    if not partes:
        raise ValueError("linha vazia")
    prefixo = (" ".join(partes[:-1]) + " ") if len(partes) > 1 else ""
    orcamento = MAX_LINHA - 1 - len(prefixo.encode("utf-8"))  # -1 pelo "\n"
    ultimo = partes[-1]
    marca = len(MARCA_TRUNCADO.encode("utf-8"))  # "…" são 3 bytes: contar caractere erra a conta
    if len(ultimo.encode("utf-8")) > orcamento:
        corte = ultimo.encode("utf-8")[: max(orcamento - marca, 0)]
        ultimo = corte.decode("utf-8", "ignore") + MARCA_TRUNCADO
    return (prefixo + ultimo).encode("utf-8") + b"\n"


def lacuna(ultimo_seq, novo_seq):
    """Quantas mensagens faltaram entre ultimo_seq e novo_seq (0 = em sequência)."""
    return max(0, novo_seq - ultimo_seq - 1)


class LeitorLinhas:
    """Acumula bytes e só devolve linha terminada em "\\n".

    TCP é fluxo: `recv(1024)` pode devolver meia mensagem, uma, ou três coladas. Tratar o
    retorno como mensagem é o defeito clássico dos exemplos didáticos.
    """

    def __init__(self, sock):
        self.sock = sock
        self.buf = b""

    def linha(self, timeout=None):
        """Próxima linha sem o terminador, ou None quando o par encerra a conexão."""
        if timeout is not None:
            self.sock.settimeout(timeout)
        while b"\n" not in self.buf:
            dados = self.sock.recv(4096)
            if not dados:
                return None
            self.buf += dados
            if len(self.buf) > BUFFER_MAX and b"\n" not in self.buf:
                self.buf = b""
                raise ErroProtocolo("linha_longa")
        linha, _, self.buf = self.buf.partition(b"\n")
        if len(linha) > MAX_LINHA:
            # linha terminada, mas acima do contrato: rejeita e segue (o buffer já está no
            # começo da próxima linha, então a ressincronização é limpa)
            raise ErroProtocolo("linha_longa")
        return linha.decode("utf-8", "replace").rstrip("\r")


class Conexao:
    """Socket + leitor de linhas + envio de comandos."""

    def __init__(self, sock):
        self.sock = sock
        self.leitor = LeitorLinhas(sock)

    def enviar(self, *campos):
        self.sock.sendall(montar(*campos))

    def linha(self, timeout=None):
        return self.leitor.linha(timeout)

    def fechar(self):
        try:
            self.sock.shutdown(socket.SHUT_RDWR)
        except OSError:
            pass
        try:
            self.sock.close()
        except OSError:
            pass
