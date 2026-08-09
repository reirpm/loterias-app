"""
Atualiza automaticamente o banco loterias.db, buscando os concursos novos
direto na API pública da Caixa (não precisa mais baixar planilha manualmente).

Como rodar:
    python atualizar_base.py
"""

import sqlite3
import time
import requests

BANCO = "loterias.db"
API_BASE = "https://servicebus2.caixa.gov.br/portaldeloterias/api/diadesorte"

# A Caixa bloqueia requisições que não parecem vir de um navegador comum,
# então simulamos os cabeçalhos de um navegador real.
CABECALHOS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
    ),
    "Accept": "application/json, text/plain, */*",
    "Referer": "https://loterias.caixa.gov.br/",
}


def buscar_concurso(numero=None):
    """Busca um concurso específico, ou o mais recente se numero=None."""
    url = API_BASE if numero is None else f"{API_BASE}/{numero}"
    resposta = requests.get(url, headers=CABECALHOS, timeout=15)
    resposta.raise_for_status()
    return resposta.json()


def valor_faixa(lista_rateio, faixa):
    """Extrai (ganhadores, valor) de uma faixa específica do rateio."""
    for item in lista_rateio:
        if item["faixa"] == faixa:
            return item["numeroDeGanhadores"], item["valorPremio"]
    return 0, 0.0


def salvar_concurso(cursor, dados):
    dezenas = sorted(int(d) for d in dados["listaDezenas"])

    ganhadores_7, rateio_7 = valor_faixa(dados["listaRateioPremio"], 1)
    ganhadores_6, rateio_6 = valor_faixa(dados["listaRateioPremio"], 2)
    ganhadores_5, rateio_5 = valor_faixa(dados["listaRateioPremio"], 3)
    ganhadores_4, rateio_4 = valor_faixa(dados["listaRateioPremio"], 4)
    ganhadores_mes, rateio_mes = valor_faixa(dados["listaRateioPremio"], 5)

    cursor.execute("""
        INSERT OR REPLACE INTO dia_de_sorte VALUES
        (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
    """, (
        dados["numero"],
        dados["dataApuracao"],
        dezenas[0], dezenas[1], dezenas[2], dezenas[3],
        dezenas[4], dezenas[5], dezenas[6],
        dados.get("nomeTimeCoracaoMesSorte"),
        ganhadores_7, rateio_7,
        ganhadores_6, rateio_6,
        ganhadores_5, rateio_5,
        ganhadores_4, rateio_4,
        ganhadores_mes, rateio_mes,
        1 if dados.get("acumulado") else 0,
        dados.get("valorArrecadado", 0.0),
        dados.get("valorEstimadoProximoConcurso", 0.0),
    ))


def main():
    conexao = sqlite3.connect(BANCO)
    cursor = conexao.cursor()

    ultimo_no_banco = cursor.execute(
        "SELECT COALESCE(MAX(concurso), 0) FROM dia_de_sorte"
    ).fetchone()[0]
    print(f"Último concurso salvo no banco: {ultimo_no_banco}")

    print("Consultando concurso mais recente na Caixa...")
    dados_recentes = buscar_concurso()
    ultimo_disponivel = dados_recentes["numero"]
    print(f"Último concurso disponível na Caixa: {ultimo_disponivel}")

    if ultimo_disponivel <= ultimo_no_banco:
        print("Base já está atualizada. Nada a fazer.")
        conexao.close()
        return

    novos = list(range(ultimo_no_banco + 1, ultimo_disponivel + 1))
    print(f"Buscando {len(novos)} concurso(s) novo(s): {novos}")

    atualizados = 0
    for numero in novos:
        if numero == ultimo_disponivel:
            dados = dados_recentes  # já temos, evita nova consulta
        else:
            dados = buscar_concurso(numero)
            time.sleep(0.5)  # gentileza com a API, evita bloqueio por excesso de chamadas

        salvar_concurso(cursor, dados)
        atualizados += 1
        print(f"  Concurso {numero} salvo.")

    conexao.commit()
    total = cursor.execute("SELECT COUNT(*) FROM dia_de_sorte").fetchone()[0]
    print(f"\nConcluído! {atualizados} concurso(s) novo(s) adicionados.")
    print(f"Total de concursos no banco agora: {total}")

    conexao.close()


if __name__ == "__main__":
    main()