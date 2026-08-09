"""
Script para importar os resultados do Dia de Sorte da planilha Excel
para um banco de dados SQLite (loterias.db).

Como rodar:
    python importar_dados.py
"""

import sqlite3
import pandas as pd
import re

ARQUIVO_EXCEL = "Dia_de_Sorte.xlsx"
BANCO = "loterias.db"

# Mapa para normalizar a coluna "Mês da Sorte", que nos concursos antigos
# vem como número (ex: "2") e nos mais recentes vem como nome (ex: "Abril")
MESES = {
    "1": "Janeiro", "2": "Fevereiro", "3": "Março", "4": "Abril",
    "5": "Maio", "6": "Junho", "7": "Julho", "8": "Agosto",
    "9": "Setembro", "10": "Outubro", "11": "Novembro", "12": "Dezembro",
}


def normalizar_mes(valor):
    if valor is None:
        return None
    texto = str(valor).strip()
    return MESES.get(texto, texto)  # se já for nome, mantém como está


def dinheiro_para_float(valor):
    """Converte 'R$957.949,23' -> 957949.23"""
    if valor is None:
        return 0.0
    texto = str(valor)
    texto = re.sub(r"[^\d,.-]", "", texto)  # remove "R$" e espaços
    texto = texto.replace(".", "").replace(",", ".")  # formato BR -> float
    try:
        return float(texto)
    except ValueError:
        return 0.0


def sim_nao_para_bool(valor):
    return 1 if str(valor).strip().lower() == "sim" else 0


def inteiro_seguro(valor, padrao=0):
    try:
        return int(str(valor).replace(".", "").strip())
    except (ValueError, TypeError):
        return padrao


def main():
    print(f"Lendo {ARQUIVO_EXCEL} ...")
    df = pd.read_excel(ARQUIVO_EXCEL, sheet_name="DIA DE SORTE")

    conexao = sqlite3.connect(BANCO)
    cursor = conexao.cursor()

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS dia_de_sorte (
            concurso INTEGER PRIMARY KEY,
            data TEXT,
            bola1 INTEGER, bola2 INTEGER, bola3 INTEGER, bola4 INTEGER,
            bola5 INTEGER, bola6 INTEGER, bola7 INTEGER,
            mes_da_sorte TEXT,
            ganhadores_7 INTEGER, rateio_7 REAL,
            ganhadores_6 INTEGER, rateio_6 REAL,
            ganhadores_5 INTEGER, rateio_5 REAL,
            ganhadores_4 INTEGER, rateio_4 REAL,
            ganhadores_mes_sorte INTEGER, rateio_mes_sorte REAL,
            acumulado_7 INTEGER,
            arrecadacao_total REAL,
            estimativa_premio REAL
        )
    """)

    linhas_inseridas = 0
    for _, linha in df.iterrows():
        if pd.isna(linha["Concurso"]):
            continue  # pula linhas em branco no final da planilha

        cursor.execute("""
            INSERT OR REPLACE INTO dia_de_sorte VALUES
           (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
        """, (
            int(linha["Concurso"]),
            str(linha["Data Sorteio"]),
            int(linha["Bola1"]), int(linha["Bola2"]), int(linha["Bola3"]),
            int(linha["Bola4"]), int(linha["Bola5"]), int(linha["Bola6"]),
            int(linha["Bola7"]),
            normalizar_mes(linha["Mês da Sorte"]),
            inteiro_seguro(linha["Ganhadores 7 acertos"]),
            dinheiro_para_float(linha["Rateio 7 acertos"]),
            inteiro_seguro(linha["Ganhadores 6 acertos"]),
            dinheiro_para_float(linha["Rateio 6 acertos"]),
            inteiro_seguro(linha["Ganhadores 5 acertos"]),
            dinheiro_para_float(linha["Rateio 5 acertos"]),
            inteiro_seguro(linha["Ganhadores 4 acertos"]),
            dinheiro_para_float(linha["Rateio 4 acertos"]),
            inteiro_seguro(linha["Ganhadores mês da sorte"]),
            dinheiro_para_float(linha["Rateio mês da sorte"]),
            sim_nao_para_bool(linha["Acumulado 7 acertos"]),
            dinheiro_para_float(linha["Arrecadação Total"]),
            dinheiro_para_float(linha["Estimativa Prêmio"]),
        ))
        linhas_inseridas += 1

    conexao.commit()

    total_no_banco = cursor.execute(
        "SELECT COUNT(*) FROM dia_de_sorte"
    ).fetchone()[0]

    print(f"Concluído! {linhas_inseridas} concursos processados.")
    print(f"Total de concursos agora no banco: {total_no_banco}")

    ultimo = cursor.execute(
        "SELECT concurso, data, bola1, bola2, bola3, bola4, bola5, bola6, bola7 "
        "FROM dia_de_sorte ORDER BY concurso DESC LIMIT 1"
    ).fetchone()
    print(f"Último concurso importado: {ultimo}")

    conexao.close()


if __name__ == "__main__":
    main()