"""
Motor de estatísticas do Dia de Sorte.
Lê o banco loterias.db (já criado pelo importar_dados.py) e calcula:
    - Frequência de cada dezena (1 a 31)
    - Atraso de cada dezena (há quantos concursos não sai)
    - Distribuição de pares/ímpares por concurso
    - Soma das dezenas por concurso

Como rodar:
    python estatisticas.py
"""

import sqlite3
from collections import Counter

BANCO = "loterias.db"
DEZENA_MIN, DEZENA_MAX = 1, 31


def carregar_concursos(cursor):
    """Retorna lista de tuplas (concurso, [7 dezenas]) em ordem crescente."""
    linhas = cursor.execute("""
        SELECT concurso, bola1, bola2, bola3, bola4, bola5, bola6, bola7
        FROM dia_de_sorte
        ORDER BY concurso ASC
    """).fetchall()
    return [(linha[0], list(linha[1:])) for linha in linhas]


def calcular_frequencia(concursos):
    """Quantas vezes cada dezena (1-31) saiu no total."""
    contador = Counter()
    for _, dezenas in concursos:
        contador.update(dezenas)
    # garante que todas as dezenas de 1 a 31 apareçam, mesmo com 0 ocorrências
    return {d: contador.get(d, 0) for d in range(DEZENA_MIN, DEZENA_MAX + 1)}


def calcular_atraso(concursos):
    """Há quantos concursos cada dezena não é sorteada (0 = saiu no último)."""
    total_concursos = len(concursos)
    ultimo_visto = {}
    for indice, (numero_concurso, dezenas) in enumerate(concursos):
        for dezena in dezenas:
            ultimo_visto[dezena] = indice  # guarda a posição (não o número do concurso)

    atrasos = {}
    for dezena in range(DEZENA_MIN, DEZENA_MAX + 1):
        if dezena in ultimo_visto:
            atrasos[dezena] = (total_concursos - 1) - ultimo_visto[dezena]
        else:
            atrasos[dezena] = total_concursos  # nunca saiu
    return atrasos


def calcular_pares_impares(concursos):
    """Distribuição de quantos pares saíram por concurso (0 a 7 pares)."""
    distribuicao = Counter()
    for _, dezenas in concursos:
        pares = sum(1 for d in dezenas if d % 2 == 0)
        distribuicao[pares] += 1
    return distribuicao


def calcular_soma(concursos):
    """Soma das 7 dezenas em cada concurso -> menor, maior e média."""
    somas = [sum(dezenas) for _, dezenas in concursos]
    return {
        "minima": min(somas),
        "maxima": max(somas),
        "media": sum(somas) / len(somas),
    }


def main():
    conexao = sqlite3.connect(BANCO)
    cursor = conexao.cursor()
    concursos = carregar_concursos(cursor)
    conexao.close()

    print(f"Total de concursos analisados: {len(concursos)}\n")

    # --- Frequência ---
    frequencia = calcular_frequencia(concursos)
    mais_frequentes = sorted(frequencia.items(), key=lambda x: -x[1])[:10]
    menos_frequentes = sorted(frequencia.items(), key=lambda x: x[1])[:10]

    print("=== 10 dezenas MAIS sorteadas ===")
    for dezena, vezes in mais_frequentes:
        print(f"  Dezena {dezena:02d}: {vezes} vezes")

    print("\n=== 10 dezenas MENOS sorteadas ===")
    for dezena, vezes in menos_frequentes:
        print(f"  Dezena {dezena:02d}: {vezes} vezes")

    # --- Atraso ---
    atraso = calcular_atraso(concursos)
    mais_atrasadas = sorted(atraso.items(), key=lambda x: -x[1])[:10]

    print("\n=== 10 dezenas mais ATRASADAS (há mais concursos sem sair) ===")
    for dezena, concursos_sem_sair in mais_atrasadas:
        print(f"  Dezena {dezena:02d}: {concursos_sem_sair} concursos sem sair")

    # --- Pares/ímpares ---
    distribuicao = calcular_pares_impares(concursos)
    print("\n=== Distribuição de pares por concurso (de 7 dezenas) ===")
    for pares in sorted(distribuicao):
        print(f"  {pares} pares / {7 - pares} ímpares: ocorreu em {distribuicao[pares]} concursos")

    # --- Soma ---
    soma = calcular_soma(concursos)
    print("\n=== Soma das 7 dezenas por concurso ===")
    print(f"  Mínima: {soma['minima']}")
    print(f"  Máxima: {soma['maxima']}")
    print(f"  Média:  {soma['media']:.1f}")


if __name__ == "__main__":
    main()