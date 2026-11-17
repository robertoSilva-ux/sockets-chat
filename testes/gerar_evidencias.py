#!/usr/bin/env python3
"""Gera as evidências de execução real em docs/evidencias/.

Sobe o servidor e três clientes de verdade (processos separados, sockets reais) e conduz uma
sessão roteirizada: registro, lista, ponto a ponto, grupo e os casos de erro. O stdout de cada
processo é gravado como veio, com o carimbo de data/hora no topo do arquivo.

Uso:  python3 testes/gerar_evidencias.py
"""

import pathlib
import subprocess
import sys
import time

RAIZ = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ))
sys.path.insert(0, str(RAIZ / "testes"))

from teste_protocolo import Servidor  # noqa: E402
from teste_cliente import ClienteProc  # noqa: E402

DESTINO = RAIZ / "docs" / "evidencias"


def escrever(nome, titulo, corpo):
    DESTINO.mkdir(parents=True, exist_ok=True)
    carimbo = time.strftime("%Y-%m-%d %H:%M:%S %z")
    texto = (
        "# %s\n\n"
        "Evidência capturada por `testes/gerar_evidencias.py` em %s.\n"
        "Conteúdo = stdout real dos processos (sem o prompt do terminal).\n\n"
        "```\n%s\n```\n" % (titulo, carimbo, corpo.rstrip())
    )
    (DESTINO / nome).write_text(texto, encoding="utf-8")
    print("  gravado docs/evidencias/%s (%d linhas)" % (nome, corpo.count("\n") + 1))


def capturar_sockets(portas):
    """ss com todos os estados: mostra LISTEN/UNCONN e as conexões ESTAB abertas."""
    linhas = ["#       estado local                remoto              processo"]
    for comando in (["ss", "-tunap"],):
        resultado = subprocess.run(comando, capture_output=True, text=True)
        for linha in resultado.stdout.splitlines():
            if any((":%d " % porta) in linha for porta in portas):
                if linha not in linhas:
                    linhas.append(linha)
    return "\n".join(linhas) if len(linhas) > 1 else "(ss não disponível nesta máquina)"


def main():
    print("gerando evidências (execução real, ~15s)...")
    with Servidor() as srv:
        carla = ClienteProc("carla", srv.porta)
        bruno = ClienteProc("bruno", srv.porta)
        ana = ClienteProc("ana", srv.porta)
        portas = [srv.porta] + [_porta_de(c) for c in (ana, bruno, carla)]

        # ---- 1. registro e lista
        ana.digitar("/listar")
        ana.exigir("[lista] 3 contato(s)")
        escrever("01-registro-lista.log", "Registro e lista de contatos (R1-R4)",
                 "### ana (cliente 1)\n" + ana.saida()
                 + "\n\n### bruno (cliente 2)\n" + bruno.saida()
                 + "\n\n### carla (cliente 3)\n" + carla.saida())

        # ---- 2. ponto a ponto TCP direto
        marco = srv.marcador()
        ana.digitar("/p2p bruno")
        ana.exigir("[p2p] conectado a bruno")
        bruno.exigir("[p2p] ana conectou")
        ana.digitar("oi bruno, conseguiu rodar o servidor?")
        bruno.exigir("ana> oi bruno, conseguiu rodar o servidor?")
        bruno.digitar("consegui, porta 9990 nos dois protocolos")
        ana.exigir("bruno> consegui")
        # captura dos sockets AQUI: a conversa está aberta (conexão direta entre os clientes)
        sockets_p2p = capturar_sockets(portas)
        # terceiro tentando entrar na conversa de bruno
        carla.digitar("/p2p bruno")
        carla.exigir("bruno está em outra conversa")
        ana.digitar("/sair")
        ana.exigir("[p2p] conversa com bruno encerrada")
        bruno.exigir("[p2p] ana encerrou a conversa")
        log_p2p = srv.log_apos(marco).strip()
        if not log_p2p:
            log_p2p = "(vazio — nenhuma linha nova no log do servidor enquanto os dois conversaram)"
        escrever("02-p2p.log", "Ponto a ponto TCP direto (R5)",
                 "### ana\n" + ana.saida()
                 + "\n\n### bruno\n" + bruno.saida()
                 + "\n\n### carla (tentativa com bruno ocupado)\n" + carla.saida()
                 + "\n\n### log do SERVIDOR durante a conversa (nenhuma mensagem passou por ele)\n"
                 + log_p2p)

        # ---- 3. grupo UDP
        marco = srv.marcador()
        ana.digitar("/grupo reuniao de apresentacao 19h na sala 12")
        ana.exigir("[grupo ana] reuniao")
        bruno.exigir("[grupo ana] reuniao de apresentacao 19h na sala 12")
        carla.exigir("[grupo ana] reuniao de apresentacao 19h na sala 12")
        carla.digitar("/grupo ok, levo o notebook")
        ana.exigir("[grupo carla] ok, levo o notebook")
        bruno.exigir("[grupo carla] ok, levo o notebook")
        escrever("03-grupo.log", "Broadcast pelo servidor em UDP (R6)",
                 "### ana\n" + ana.saida()
                 + "\n\n### bruno\n" + bruno.saida()
                 + "\n\n### carla\n" + carla.saida()
                 + "\n\n### log do SERVIDOR (um envio, N destinatários)\n" + srv.log_apos(marco))

        # ---- 4. sockets, os dois transportes (e a conexão P2P direta, aberta no momento da captura)
        escrever("04-sockets.log", "Sockets abertos: TCP (controle/P2P) e UDP (grupo) (R7)",
                 "$ ss -tunap   # capturado DURANTE a conversa ponto a ponto\n"
                 + sockets_p2p
                 + "\n\n# Os dois lados da conversa P2P aparecem ligados entre si (portas dos clientes),\n"
                 "# e cada cliente tem também uma sessão de controle com a porta do servidor.\n"
                 "# Cada cliente aparece duas vezes: LISTEN/UNCONN na sua porta (TCP e UDP).")

        # ---- 5. erros
        ana.digitar("/p2p fantasma")
        ana.exigir("contato_offline")
        ana.digitar("/comando-que-nao-existe")
        ana.exigir("comando desconhecido")
        duplicado = subprocess.run(
            [sys.executable, str(RAIZ / "cliente.py"), "--nick", "ana",
             "--porta-servidor", str(srv.porta)],
            capture_output=True, text=True, timeout=20, input="",
        )
        escrever("05-erros.log", "Erros como protocolo, não como traceback (E5)",
                 "### cliente repetindo nick em uso\n" + duplicado.stdout + duplicado.stderr
                 + "\n\n### ana: contato offline e comando inválido\n" + ana.saida())

        for cliente in (ana, bruno, carla):
            cliente.fechar()
        time.sleep(0.3)
        escrever("06-servidor.log", "Log completo do servidor", srv.log())

    print("pronto: docs/evidencias/")


def _porta_de(cliente):
    for linha in cliente.saida().splitlines():
        if "minha porta local é" in linha:
            return int(linha.rsplit(" ", 1)[1])
    return 0


if __name__ == "__main__":
    main()
