"""
Protótipo web do sistema de análise de loterias - Dia de Sorte.

Como rodar:
    streamlit run app.py

Isso abre automaticamente uma aba no navegador com o site.
"""

import sqlite3
import random
import time
from collections import Counter

import streamlit as st
import pandas as pd
import requests

BANCO = "loterias.db"
DEZENA_MIN, DEZENA_MAX = 1, 31
QTD_DEZENAS_POR_JOGO = 7
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


# ---------------------------------------------------------------------------
# Funções de acesso ao banco e cálculo (mesma lógica dos scripts anteriores)
# ---------------------------------------------------------------------------

@st.cache_data(ttl=60)
def carregar_concursos():
    conexao = sqlite3.connect(BANCO)
    df = pd.read_sql_query(
        "SELECT * FROM dia_de_sorte ORDER BY concurso ASC", conexao
    )
    conexao.close()
    return df


def calcular_frequencia(df):
    contador = Counter()
    for col in ["bola1", "bola2", "bola3", "bola4", "bola5", "bola6", "bola7"]:
        contador.update(df[col].tolist())
    return {d: contador.get(d, 0) for d in range(DEZENA_MIN, DEZENA_MAX + 1)}


def calcular_atraso(df):
    total = len(df)
    ultimo_visto = {}
    colunas = ["bola1", "bola2", "bola3", "bola4", "bola5", "bola6", "bola7"]
    for indice, linha in enumerate(df[colunas].itertuples(index=False)):
        for dezena in linha:
            ultimo_visto[dezena] = indice
    atrasos = {}
    for dezena in range(DEZENA_MIN, DEZENA_MAX + 1):
        atrasos[dezena] = (total - 1 - ultimo_visto[dezena]) if dezena in ultimo_visto else total
    return atrasos


def jogo_valido(jogo, ultimo_concurso, soma_min, soma_max, pares_min, pares_max, max_repetidos):
    soma = sum(jogo)
    if not (soma_min <= soma <= soma_max):
        return False
    pares = sum(1 for d in jogo if d % 2 == 0)
    if not (pares_min <= pares <= pares_max):
        return False
    if len(set(jogo) & ultimo_concurso) > max_repetidos:
        return False
    return True


def buscar_concurso_api(numero=None):
    """Busca um concurso específico, ou o mais recente se numero=None."""
    url = API_BASE if numero is None else f"{API_BASE}/{numero}"
    resposta = requests.get(url, headers=CABECALHOS, timeout=15)
    resposta.raise_for_status()
    return resposta.json()


def valor_faixa(lista_rateio, faixa):
    for item in lista_rateio:
        if item["faixa"] == faixa:
            return item["numeroDeGanhadores"], item["valorPremio"]
    return 0, 0.0


def salvar_concurso_api(cursor, dados):
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
        dados["numero"], dados["dataApuracao"],
        dezenas[0], dezenas[1], dezenas[2], dezenas[3],
        dezenas[4], dezenas[5], dezenas[6],
        dados.get("nomeTimeCoracaoMesSorte"),
        ganhadores_7, rateio_7, ganhadores_6, rateio_6,
        ganhadores_5, rateio_5, ganhadores_4, rateio_4,
        ganhadores_mes, rateio_mes,
        1 if dados.get("acumulado") else 0,
        dados.get("valorArrecadado", 0.0),
        dados.get("valorEstimadoProximoConcurso", 0.0),
    ))


def atualizar_base_dados():
    """Busca na Caixa os concursos que ainda não estão no banco local. Retorna (lista_adicionados, erro)."""
    conexao = sqlite3.connect(BANCO)
    cursor = conexao.cursor()
    try:
        ultimo_no_banco = cursor.execute(
            "SELECT COALESCE(MAX(concurso), 0) FROM dia_de_sorte"
        ).fetchone()[0]

        dados_recentes = buscar_concurso_api()
        ultimo_disponivel = dados_recentes["numero"]

        if ultimo_disponivel <= ultimo_no_banco:
            return [], None

        novos = list(range(ultimo_no_banco + 1, ultimo_disponivel + 1))
        adicionados = []
        for numero in novos:
            dados = dados_recentes if numero == ultimo_disponivel else buscar_concurso_api(numero)
            salvar_concurso_api(cursor, dados)
            adicionados.append(numero)
            if numero != ultimo_disponivel:
                time.sleep(0.5)

        conexao.commit()
        return adicionados, None
    except Exception as erro:
        return [], str(erro)
    finally:
        conexao.close()


def gerar_jogos(df, quantidade, soma_min, soma_max, pares_min, pares_max, max_repetidos):
    ultima_linha = df.iloc[-1]
    ultimo_concurso = {
        int(ultima_linha[c]) for c in ["bola1", "bola2", "bola3", "bola4", "bola5", "bola6", "bola7"]
    }
    jogos, tentativas = [], 0
    while len(jogos) < quantidade and tentativas < 20000:
        tentativas += 1
        candidato = sorted(random.sample(range(DEZENA_MIN, DEZENA_MAX + 1), QTD_DEZENAS_POR_JOGO))
        if jogo_valido(candidato, ultimo_concurso, soma_min, soma_max, pares_min, pares_max, max_repetidos):
            if candidato not in jogos:
                jogos.append(candidato)
    return jogos


# ---------------------------------------------------------------------------
# Interface
# ---------------------------------------------------------------------------

st.set_page_config(page_title="Loterias - Dia de Sorte", layout="wide")

st.sidebar.title("🍀 Dia de Sorte")
pagina = st.sidebar.radio(
    "Navegação",
    ["📊 Estatísticas", "🎲 Gerador de Jogos", "🔍 Consultar Concurso", "🔄 Atualizar Base"],
)

df = carregar_concursos()
st.sidebar.markdown(f"---\n**{len(df)}** concursos carregados\n\nÚltimo: **{int(df['concurso'].max())}**")

if pagina == "📊 Estatísticas":
    st.title("Estatísticas do Dia de Sorte")
    st.caption(
        "Estas estatísticas descrevem o que já aconteceu no histórico. "
        "Elas não preveem o próximo resultado — cada sorteio é independente."
    )

    frequencia = calcular_frequencia(df)
    atraso = calcular_atraso(df)

    tabela = pd.DataFrame({
        "Dezena": list(frequencia.keys()),
        "Vezes sorteada": list(frequencia.values()),
        "Concursos sem sair": [atraso[d] for d in frequencia.keys()],
    }).sort_values("Vezes sorteada", ascending=False)

    coluna1, coluna2 = st.columns(2)
    with coluna1:
        st.subheader("Frequência por dezena")
        st.bar_chart(tabela.set_index("Dezena")["Vezes sorteada"])
    with coluna2:
        st.subheader("Atraso por dezena")
        st.bar_chart(tabela.set_index("Dezena")["Concursos sem sair"])

    st.subheader("Tabela completa")
    st.dataframe(tabela, use_container_width=True, hide_index=True)

    st.subheader("Soma das 7 dezenas por concurso")
    somas = df[["bola1", "bola2", "bola3", "bola4", "bola5", "bola6", "bola7"]].sum(axis=1)
    c1, c2, c3 = st.columns(3)
    c1.metric("Mínima", int(somas.min()))
    c2.metric("Média", f"{somas.mean():.1f}")
    c3.metric("Máxima", int(somas.max()))

elif pagina == "🎲 Gerador de Jogos":
    st.title("Gerador de Jogos")
    st.caption(
        "Gera combinações respeitando os padrões estatísticos escolhidos abaixo. "
        "Isto organiza apostas dentro de padrões históricos — não é previsão."
    )

    with st.form("filtros"):
        col1, col2 = st.columns(2)
        with col1:
            quantidade = st.number_input("Quantos jogos gerar?", 1, 20, 5)
            soma_min, soma_max = st.slider("Faixa de soma das 7 dezenas", 28, 217, (95, 130))
        with col2:
            pares_min, pares_max = st.slider("Faixa de dezenas pares", 0, 7, (2, 5))
            max_repetidos = st.slider("Máx. de dezenas repetidas do último concurso", 0, 7, 3)

        gerar = st.form_submit_button("Gerar jogos")

    if gerar:
        jogos = gerar_jogos(df, quantidade, soma_min, soma_max, pares_min, pares_max, max_repetidos)
        if not jogos:
            st.warning("Não foi possível gerar jogos com esses filtros. Tente afrouxar os critérios.")
        else:
            for indice, jogo in enumerate(jogos, start=1):
                soma = sum(jogo)
                pares = sum(1 for d in jogo if d % 2 == 0)
                dezenas_formatadas = " - ".join(f"{d:02d}" for d in jogo)
                st.success(f"Jogo {indice}: {dezenas_formatadas}   (soma={soma}, pares={pares})")

elif pagina == "🔍 Consultar Concurso":
    st.title("Consultar Concurso")

    numero = st.number_input(
        "Número do concurso", min_value=int(df["concurso"].min()),
        max_value=int(df["concurso"].max()), value=int(df["concurso"].max()),
    )

    linha = df[df["concurso"] == numero]
    if linha.empty:
        st.error("Concurso não encontrado.")
    else:
        linha = linha.iloc[0]
        dezenas = [int(linha[f"bola{i}"]) for i in range(1, 8)]
        st.subheader(f"Concurso {int(linha['concurso'])} — {linha['data']}")
        st.write(" - ".join(f"{d:02d}" for d in dezenas))
        st.write(f"Mês da sorte: **{linha['mes_da_sorte']}**")

        c1, c2, c3, c4 = st.columns(4)
        c1.metric("Ganhadores 7 acertos", int(linha["ganhadores_7"]))
        c2.metric("Ganhadores 6 acertos", int(linha["ganhadores_6"]))
        c3.metric("Ganhadores 5 acertos", int(linha["ganhadores_5"]))
        c4.metric("Ganhadores 4 acertos", int(linha["ganhadores_4"]))

elif pagina == "🔄 Atualizar Base":
    st.title("Atualizar Base de Dados")
    st.write(
        "Busca automaticamente, direto na Caixa, os concursos que ainda não "
        "estão salvos no banco local."
    )
    st.info(f"Último concurso salvo no banco: **{int(df['concurso'].max())}**")

    if st.button("🔄 Buscar concursos novos", type="primary"):
        with st.spinner("Consultando a Caixa..."):
            adicionados, erro = atualizar_base_dados()

        if erro:
            st.error(f"Não foi possível atualizar: {erro}")
        elif not adicionados:
            st.success("A base já está atualizada. Nenhum concurso novo encontrado.")
        else:
            st.success(f"{len(adicionados)} concurso(s) adicionados: {adicionados}")
            st.cache_data.clear()  # força recarregar os dados nas outras telas
            st.button("Ver estatísticas atualizadas ➜")