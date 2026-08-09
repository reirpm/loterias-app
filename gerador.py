"""
Gerador de jogos do Dia de Sorte, com filtros configuráveis pelo usuário.

IMPORTANTE: isto NÃO prevê números vencedores. Cada sorteio é
independente e aleatório. Este gerador só organiza combinações
dentro de padrões estatísticos historicamente comuns -- não muda
a probabilidade real de acertar.

Como rodar:
    python gerador.py
"""

import sqlite3
import random

BANCO = "loterias.db"
DEZENA_MIN, DEZENA_MAX = 1, 31
QTD_DEZENAS_POR_JOGO = 7


def carregar_ultimo_concurso(cursor):
    linha = cursor.execute("""
        SELECT bola1, bola2, bola3, bola4, bola5, bola6, bola7
        FROM dia_de_sorte
        ORDER BY concurso DESC LIMIT 1
    """).fetchone()
    return set(linha)


def gerar_jogo_aleatorio():
    return sorted(random.sample(range(DEZENA_MIN, DEZENA_MAX + 1), QTD_DEZENAS_POR_JOGO))


def jogo_valido(jogo, ultimo_concurso, soma_min, soma_max, pares_min, pares_max, max_repetidos_ultimo):
    soma = sum(jogo)
    if not (soma_min <= soma <= soma_max):
        return False

    pares = sum(1 for d in jogo if d % 2 == 0)
    if not (pares_min <= pares <= pares_max):
        return False

    repetidos = len(set(jogo) & ultimo_concurso)
    if repetidos > max_repetidos_ultimo:
        return False

    return True


def gerar_jogos(cursor, quantidade, soma_min, soma_max, pares_min, pares_max, max_repetidos_ultimo):
    ultimo_concurso = carregar_ultimo_concurso(cursor)
    jogos_gerados = []
    tentativas = 0
    tentativas_maximas = 20000

    while len(jogos_gerados) < quantidade and tentativas < tentativas_maximas:
        tentativas += 1
        candidato = gerar_jogo_aleatorio()
        if jogo_valido(candidato, ultimo_concurso, soma_min, soma_max, pares_min, pares_max, max_repetidos_ultimo):
            if candidato not in jogos_gerados:
                jogos_gerados.append(candidato)

    return jogos_gerados, tentativas


def perguntar_inteiro(mensagem, padrao):
    """Pede um número ao usuário no terminal; usa o padrão se ele só apertar Enter."""
    entrada = input(f"{mensagem} [padrão: {padrao}]: ").strip()
    if entrada == "":
        return padrao
    try:
        return int(entrada)
    except ValueError:
        print("  valor inválido, usando o padrão.")
        return padrao


def main():
    print("=== Gerador de jogos configurável - Dia de Sorte ===\n")
    print("Aperte Enter em qualquer pergunta para usar o valor padrão sugerido.\n")

    quantidade = perguntar_inteiro("Quantos jogos gerar?", 5)
    soma_min = perguntar_inteiro("Soma mínima das 7 dezenas?", 95)
    soma_max = perguntar_inteiro("Soma máxima das 7 dezenas?", 130)
    pares_min = perguntar_inteiro("Mínimo de dezenas pares (0 a 7)?", 2)
    pares_max = perguntar_inteiro("Máximo de dezenas pares (0 a 7)?", 5)
    max_repetidos_ultimo = perguntar_inteiro("Máx. de dezenas repetidas do último concurso?", 3)

    conexao = sqlite3.connect(BANCO)
    cursor = conexao.cursor()

    print(f"\nGerando {quantidade} jogos com os filtros escolhidos...\n")
    jogos, tentativas = gerar_jogos(
        cursor, quantidade, soma_min, soma_max, pares_min, pares_max, max_repetidos_ultimo
    )

    if not jogos:
        print(f"Não foi possível gerar jogos com esses filtros (tentei {tentativas} vezes).")
        print("Tente afrouxar os critérios -- por exemplo, uma faixa de soma mais larga.")
    else:
        for indice, jogo in enumerate(jogos, start=1):
            soma = sum(jogo)
            pares = sum(1 for d in jogo if d % 2 == 0)
            dezenas_formatadas = " - ".join(f"{d:02d}" for d in jogo)
            print(f"Jogo {indice}: {dezenas_formatadas}   (soma={soma}, pares={pares})")

        if len(jogos) < quantidade:
            print(f"\n(Consegui gerar apenas {len(jogos)} de {quantidade} jogos únicos com esses filtros.)")

    conexao.close()


if __name__ == "__main__":
    main()