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
import numpy as np
import requests

BANCO = "loterias.db"
DEZENA_MIN, DEZENA_MAX = 1, 31
QTD_DEZENAS_POR_JOGO = 7
API_BASE = "https://servicebus2.caixa.gov.br/portaldeloterias/api/diadesorte"
COLUNAS_DEZENAS = ["bola1", "bola2", "bola3", "bola4", "bola5", "bola6", "bola7"]
PRIMOS = {2, 3, 5, 7, 11, 13, 17, 19, 23, 29, 31}
FIBONACCI = {1, 2, 3, 5, 8, 13, 21}

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


# ---------------------------------------------------------------------------
# Estatísticas avançadas
# ---------------------------------------------------------------------------

def calcular_frequencia_janela(df, janela):
    """Frequência de cada dezena só nos últimos N concursos."""
    sub = df.tail(janela)
    contador = Counter()
    for col in COLUNAS_DEZENAS:
        contador.update(sub[col].tolist())
    return {d: contador.get(d, 0) for d in range(DEZENA_MIN, DEZENA_MAX + 1)}


def calcular_coocorrencia_top(df, top_n=15):
    """Pares de dezenas que mais saíram juntas no mesmo concurso."""
    pares = Counter()
    for linha in df[COLUNAS_DEZENAS].itertuples(index=False):
        numeros = sorted(linha)
        for i in range(len(numeros)):
            for j in range(i + 1, len(numeros)):
                pares[(numeros[i], numeros[j])] += 1
    return pares.most_common(top_n)


def calcular_sequencias(df):
    """Distribuição de quantos pares de dezenas consecutivas (ex: 14-15) saíram por concurso."""
    contagem = Counter()
    for linha in df[COLUNAS_DEZENAS].itertuples(index=False):
        numeros = sorted(linha)
        seguidas = sum(1 for i in range(1, len(numeros)) if numeros[i] == numeros[i - 1] + 1)
        contagem[seguidas] += 1
    return contagem


def contagem_por_criterio(df, conjunto):
    """Distribuição de quantas dezenas do conjunto dado (primos, fibonacci, etc.) saíram por concurso."""
    contagem = Counter()
    for linha in df[COLUNAS_DEZENAS].itertuples(index=False):
        qtd = sum(1 for d in linha if d in conjunto)
        contagem[qtd] += 1
    return contagem


def calcular_faixas(df):
    """Quantas vezes cada faixa (1-10, 11-20, 21-31) apareceu no total de dezenas sorteadas."""
    def faixa_de(d):
        if d <= 10:
            return "1 a 10"
        elif d <= 20:
            return "11 a 20"
        return "21 a 31"

    contador = Counter()
    for col in COLUNAS_DEZENAS:
        for d in df[col]:
            contador[faixa_de(d)] += 1
    return contador


def calcular_terminacoes(df):
    """Frequência de cada dígito final (0-9) entre todas as dezenas sorteadas."""
    contador = Counter()
    for col in COLUNAS_DEZENAS:
        for d in df[col]:
            contador[d % 10] += 1
    return contador


def calcular_amplitude(df):
    """Diferença entre a maior e a menor dezena de cada concurso."""
    return df[COLUNAS_DEZENAS].max(axis=1) - df[COLUNAS_DEZENAS].min(axis=1)


def calcular_ciclos_fechamento(df):
    """Tamanho de cada 'ciclo' até todas as 31 dezenas terem aparecido pelo menos uma vez."""
    ciclos = []
    vistos = set()
    inicio = 0
    for indice, linha in enumerate(df[COLUNAS_DEZENAS].itertuples(index=False)):
        vistos.update(linha)
        if len(vistos) == DEZENA_MAX:
            ciclos.append(indice - inicio + 1)
            vistos = set()
            inicio = indice + 1
    return ciclos


def calcular_mes_sorte(df):
    """Frequência e atraso de cada Mês da Sorte."""
    contador = Counter(df["mes_da_sorte"])
    total = len(df)
    ultimo_visto = {}
    for indice, mes in enumerate(df["mes_da_sorte"]):
        ultimo_visto[mes] = indice
    atraso = {mes: total - 1 - indice for mes, indice in ultimo_visto.items()}
    return contador, atraso


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
# Gerador de Jogos Inteligente — combina os critérios avançados de uma vez
# ---------------------------------------------------------------------------

def calcular_pesos_frequencia(df, janela):
    """Converte a frequência recente de cada dezena em pesos de sorteio (soma = 1)."""
    freq = calcular_frequencia_janela(df, janela)
    ajustado = {d: freq[d] + 1 for d in freq}  # +1 evita peso zero para dezenas que não saíram
    total = sum(ajustado.values())
    return {d: valor / total for d, valor in ajustado.items()}


def sortear_ponderado(pesos_dict):
    """Sorteia 7 dezenas sem repetição, dando mais chance às de maior peso."""
    dezenas = list(range(DEZENA_MIN, DEZENA_MAX + 1))
    pesos = np.array([pesos_dict[d] for d in dezenas])
    pesos = pesos / pesos.sum()
    escolhidos = np.random.choice(dezenas, size=QTD_DEZENAS_POR_JOGO, replace=False, p=pesos)
    return sorted(int(d) for d in escolhidos)


def jogo_valido_inteligente(jogo, ultimo_concurso, filtros):
    soma = sum(jogo)
    if not (filtros["soma_min"] <= soma <= filtros["soma_max"]):
        return False

    pares = sum(1 for d in jogo if d % 2 == 0)
    if not (filtros["pares_min"] <= pares <= filtros["pares_max"]):
        return False

    if len(set(jogo) & ultimo_concurso) > filtros["max_repetidos"]:
        return False

    primos_qtd = sum(1 for d in jogo if d in PRIMOS)
    if not (filtros["primos_min"] <= primos_qtd <= filtros["primos_max"]):
        return False

    fib_qtd = sum(1 for d in jogo if d in FIBONACCI)
    if not (filtros["fib_min"] <= fib_qtd <= filtros["fib_max"]):
        return False

    numeros = sorted(jogo)
    seguidas = sum(1 for i in range(1, len(numeros)) if numeros[i] == numeros[i - 1] + 1)
    if seguidas > filtros["seq_max"]:
        return False

    amplitude = max(jogo) - min(jogo)
    if not (filtros["amplitude_min"] <= amplitude <= filtros["amplitude_max"]):
        return False

    return True


def gerar_jogos_inteligente(df, quantidade, filtros, usar_pesos, pesos_dict):
    ultima_linha = df.iloc[-1]
    ultimo_concurso = {int(ultima_linha[c]) for c in COLUNAS_DEZENAS}
    jogos, tentativas = [], 0
    tentativas_maximas = 30000

    while len(jogos) < quantidade and tentativas < tentativas_maximas:
        tentativas += 1
        if usar_pesos:
            candidato = sortear_ponderado(pesos_dict)
        else:
            candidato = sorted(random.sample(range(DEZENA_MIN, DEZENA_MAX + 1), QTD_DEZENAS_POR_JOGO))

        if jogo_valido_inteligente(candidato, ultimo_concurso, filtros) and candidato not in jogos:
            jogos.append(candidato)

    return jogos, tentativas


# ---------------------------------------------------------------------------
# Interface
# ---------------------------------------------------------------------------

st.set_page_config(page_title="Dia de Sorte — Painel", page_icon="🍀", layout="wide")

# ---------------------------------------------------------------------------
# Identidade visual — paleta "bilhete de loteria": verde-cédula + carimbo dourado
# ---------------------------------------------------------------------------
st.markdown("""
<style>
@import url('https://fonts.googleapis.com/css2?family=Fraunces:opsz,wght@9..144,600;9..144,700&family=IBM+Plex+Sans:wght@400;500;600&family=IBM+Plex+Mono:wght@500;600&display=swap');

html, body, [class*="css"] { font-family: 'IBM Plex Sans', sans-serif; }

[data-testid="stAppViewContainer"] { background: #0F2A1E; }
[data-testid="stHeader"] { background: transparent; }

[data-testid="stSidebar"] {
    background: #163826;
    border-right: 1px solid rgba(217,164,65,0.35);
}
[data-testid="stSidebar"] * { color: #F3EFE4 !important; }

h1, h2, h3 {
    font-family: 'Fraunces', serif !important;
    color: #F3EFE4 !important;
    letter-spacing: -0.01em;
}
p, span, label, .stCaption, [data-testid="stCaptionContainer"] { color: #E4DFCF !important; }

[data-testid="stMetric"] {
    background: #163826;
    border: 1px solid rgba(217,164,65,0.35);
    border-radius: 10px;
    padding: 14px 16px;
}
[data-testid="stMetricLabel"] { color: #D9A441 !important; }
[data-testid="stMetricValue"] { color: #F3EFE4 !important; font-family: 'IBM Plex Mono', monospace !important; }

.stButton > button, .stFormSubmitButton > button {
    background: #D9A441; color: #0F2A1E; border: none;
    border-radius: 8px; font-weight: 600; padding: 0.5em 1.2em;
}
.stButton > button:hover, .stFormSubmitButton > button:hover { background: #C79433; color: #0F2A1E; }

[data-testid="stForm"], [data-testid="stExpander"] {
    background: #163826;
    border: 1px solid rgba(217,164,65,0.25);
    border-radius: 12px;
}

[data-testid="stDataFrame"] { border: 1px solid rgba(217,164,65,0.25); border-radius: 8px; }

.selo-topo {
    display: flex; align-items: center; gap: 14px;
    border-bottom: 2px dashed rgba(217,164,65,0.5);
    padding-bottom: 14px; margin-bottom: 18px;
}
.selo-icone {
    width: 46px; height: 46px; border-radius: 50%;
    border: 2px solid #D9A441; display: flex; align-items: center;
    justify-content: center; font-size: 22px; flex-shrink: 0;
}
.selo-texto p { margin: 0; color: #D9A441 !important; font-size: 0.85rem; letter-spacing: 0.05em; text-transform: uppercase; }

.dezena-bola {
    display: inline-flex; align-items: center; justify-content: center;
    width: 42px; height: 42px; margin: 3px 5px 3px 0;
    border-radius: 50%; background: #0F2A1E; border: 2px solid #D9A441;
    color: #F3EFE4 !important; font-family: 'IBM Plex Mono', monospace;
    font-weight: 600; font-size: 0.95rem;
}
.dezena-bola.destaque { background: #D9A441; color: #0F2A1E !important; border-color: #F3EFE4; }
</style>
""", unsafe_allow_html=True)


def selo_topo(icone, rotulo, titulo):
    st.markdown(f"""
    <div class="selo-topo">
        <div class="selo-icone">{icone}</div>
        <div class="selo-texto"><p>{rotulo}</p><h1 style="margin:0;">{titulo}</h1></div>
    </div>
    """, unsafe_allow_html=True)


def dezenas_html(dezenas, destaque=False):
    classe = "dezena-bola destaque" if destaque else "dezena-bola"
    bolas = "".join(f'<span class="{classe}">{d:02d}</span>' for d in dezenas)
    return f'<div style="margin:6px 0 10px 0;">{bolas}</div>'


st.sidebar.markdown("### 🍀 Dia de Sorte")
pagina = st.sidebar.radio(
    "Navegação",
    ["📊 Estatísticas", "⭐ Estatísticas Avançadas", "🎲 Gerador de Jogos",
     "🧠 Gerador Inteligente", "🔍 Consultar Concurso", "🔄 Atualizar Base"],
)

df = carregar_concursos()
st.sidebar.markdown(f"---\n**{len(df)}** concursos carregados\n\nÚltimo: **{int(df['concurso'].max())}**")

if pagina == "📊 Estatísticas":
    selo_topo("📊", "Painel", "Estatísticas do Dia de Sorte")
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

elif pagina == "⭐ Estatísticas Avançadas":
    selo_topo("⭐", "Premium", "Estatísticas Avançadas")
    st.caption(
        "Camada extra de análise sobre o mesmo histórico. Continua descrevendo "
        "o que já aconteceu — não prevê o próximo resultado."
    )

    aba1, aba2, aba3, aba4 = st.tabs([
        "Frequência recente", "Dupla mais sorteada", "Padrões numéricos", "Ciclos & Mês da Sorte"
    ])

    with aba1:
        st.subheader("Frequência em janela recente")
        janela = st.select_slider("Considerar os últimos:", options=[25, 50, 100], value=50)
        freq_recente = calcular_frequencia_janela(df, janela)
        tabela_recente = pd.DataFrame({
            "Dezena": list(freq_recente.keys()),
            f"Vezes nos últimos {janela}": list(freq_recente.values()),
        }).sort_values(f"Vezes nos últimos {janela}", ascending=False)
        st.bar_chart(tabela_recente.set_index("Dezena"))
        st.dataframe(tabela_recente, hide_index=True, use_container_width=True)

    with aba2:
        st.subheader("Pares de dezenas que mais saíram juntos")
        top_pares = calcular_coocorrencia_top(df, 15)
        for (a, b), vezes in top_pares:
            st.markdown(
                dezenas_html([a, b]) + f"<span style='color:#D9A441'>— saíram juntas {vezes} vezes</span>",
                unsafe_allow_html=True,
            )

    with aba3:
        col1, col2 = st.columns(2)
        with col1:
            st.subheader("Sequências consecutivas")
            st.caption("Ex: 14 e 15 no mesmo jogo conta como 1 sequência.")
            seq = calcular_sequencias(df)
            tabela_seq = pd.DataFrame({
                "Nº de pares consecutivos": list(seq.keys()), "Concursos": list(seq.values()),
            }).sort_values("Nº de pares consecutivos")
            st.dataframe(tabela_seq, hide_index=True, use_container_width=True)

            st.subheader("Primos vs não-primos")
            primos_dist = contagem_por_criterio(df, PRIMOS)
            tabela_primos = pd.DataFrame({
                "Qtd de primos no jogo": list(primos_dist.keys()), "Concursos": list(primos_dist.values()),
            }).sort_values("Qtd de primos no jogo")
            st.dataframe(tabela_primos, hide_index=True, use_container_width=True)

            st.subheader("Números de Fibonacci")
            st.caption("Curiosidade estatística (1, 2, 3, 5, 8, 13, 21) — não é padrão histórico causal.")
            fib_dist = contagem_por_criterio(df, FIBONACCI)
            tabela_fib = pd.DataFrame({
                "Qtd Fibonacci no jogo": list(fib_dist.keys()), "Concursos": list(fib_dist.values()),
            }).sort_values("Qtd Fibonacci no jogo")
            st.dataframe(tabela_fib, hide_index=True, use_container_width=True)

        with col2:
            st.subheader("Distribuição por faixas")
            faixas = calcular_faixas(df)
            st.bar_chart(pd.Series(faixas, name="Vezes sorteada"))

            st.subheader("Terminações (último dígito)")
            terminacoes = calcular_terminacoes(df)
            tabela_term = pd.DataFrame({
                "Dígito final": list(terminacoes.keys()), "Vezes": list(terminacoes.values()),
            }).sort_values("Dígito final")
            st.bar_chart(tabela_term.set_index("Dígito final"))

            st.subheader("Amplitude (maior − menor dezena)")
            amplitudes = calcular_amplitude(df)
            c1, c2, c3 = st.columns(3)
            c1.metric("Mínima", int(amplitudes.min()))
            c2.metric("Média", f"{amplitudes.mean():.1f}")
            c3.metric("Máxima", int(amplitudes.max()))

    with aba4:
        st.subheader("Ciclos de fechamento")
        st.caption("Quantos concursos, em média, até todas as 31 dezenas saírem pelo menos uma vez.")
        ciclos = calcular_ciclos_fechamento(df)
        if ciclos:
            c1, c2, c3 = st.columns(3)
            c1.metric("Ciclos completos", len(ciclos))
            c2.metric("Média de concursos por ciclo", f"{sum(ciclos) / len(ciclos):.1f}")
            c3.metric("Ciclo mais curto / mais longo", f"{min(ciclos)} / {max(ciclos)}")
        else:
            st.info("Ainda não há um ciclo completo fechado no histórico.")

        st.subheader("Estatísticas do Mês da Sorte")
        contador_mes, atraso_mes = calcular_mes_sorte(df)
        tabela_mes = pd.DataFrame({
            "Mês": list(contador_mes.keys()),
            "Vezes sorteado": list(contador_mes.values()),
            "Concursos sem sair": [atraso_mes[m] for m in contador_mes.keys()],
        }).sort_values("Vezes sorteado", ascending=False)
        st.dataframe(tabela_mes, hide_index=True, use_container_width=True)

elif pagina == "🎲 Gerador de Jogos":
    selo_topo("🎲", "Ferramenta", "Gerador de Jogos")
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
                st.markdown(f"**Jogo {indice}**  (soma={soma}, pares={pares})", unsafe_allow_html=True)
                st.markdown(dezenas_html(jogo), unsafe_allow_html=True)

elif pagina == "🧠 Gerador Inteligente":
    selo_topo("🧠", "Premium", "Gerador de Jogos Inteligente")
    st.caption(
        "Combina vários padrões estatísticos ao mesmo tempo (soma, pares, primos, "
        "Fibonacci, sequências, amplitude e frequência recente). Continua sendo "
        "organização de apostas dentro de padrões históricos — não é previsão."
    )

    with st.form("filtros_inteligente"):
        col1, col2, col3 = st.columns(3)
        with col1:
            quantidade = st.number_input("Quantos jogos gerar?", 1, 20, 5)
            soma_min, soma_max = st.slider("Faixa de soma das 7 dezenas", 28, 217, (95, 130))
            pares_min, pares_max = st.slider("Faixa de dezenas pares", 0, 7, (2, 5))
        with col2:
            primos_min, primos_max = st.slider("Faixa de primos no jogo", 0, 7, (1, 4))
            fib_min, fib_max = st.slider("Faixa de números Fibonacci", 0, 7, (0, 3))
            seq_max = st.slider("Máx. de sequências consecutivas (ex: 14-15)", 0, 6, 2)
        with col3:
            amplitude_min, amplitude_max = st.slider("Faixa de amplitude (maior − menor)", 0, 30, (10, 28))
            max_repetidos = st.slider("Máx. repetidas do último concurso", 0, 7, 3)
            usar_pesos = st.checkbox("Priorizar dezenas mais quentes (frequência recente)")
            janela_pesos = st.select_slider(
                "Janela para 'quentes'", options=[25, 50, 100], value=50, disabled=not usar_pesos
            )

        gerar = st.form_submit_button("🧠 Gerar jogos inteligentes")

    if gerar:
        filtros = dict(
            soma_min=soma_min, soma_max=soma_max, pares_min=pares_min, pares_max=pares_max,
            max_repetidos=max_repetidos, primos_min=primos_min, primos_max=primos_max,
            fib_min=fib_min, fib_max=fib_max, seq_max=seq_max,
            amplitude_min=amplitude_min, amplitude_max=amplitude_max,
        )
        pesos_dict = calcular_pesos_frequencia(df, janela_pesos) if usar_pesos else None

        with st.spinner("Sorteando e filtrando combinações..."):
            jogos, tentativas = gerar_jogos_inteligente(df, quantidade, filtros, usar_pesos, pesos_dict)

        if not jogos:
            st.warning(
                f"Não foi possível gerar jogos com esses filtros (tentei {tentativas} combinações). "
                "Tente afrouxar algum critério — faixas muito estreitas combinadas ficam difíceis de atender."
            )
        else:
            for indice, jogo in enumerate(jogos, start=1):
                soma = sum(jogo)
                pares = sum(1 for d in jogo if d % 2 == 0)
                primos_qtd = sum(1 for d in jogo if d in PRIMOS)
                fib_qtd = sum(1 for d in jogo if d in FIBONACCI)
                st.markdown(
                    f"**Jogo {indice}**  (soma={soma}, pares={pares}, primos={primos_qtd}, fibonacci={fib_qtd})",
                    unsafe_allow_html=True,
                )
                st.markdown(dezenas_html(jogo), unsafe_allow_html=True)

elif pagina == "🔍 Consultar Concurso":
    selo_topo("🔍", "Consulta", "Consultar Concurso")

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
        st.markdown(dezenas_html(dezenas, destaque=True), unsafe_allow_html=True)
        st.write(f"Mês da sorte: **{linha['mes_da_sorte']}**")

        c1, c2, c3, c4 = st.columns(4)
        c1.metric("Ganhadores 7 acertos", int(linha["ganhadores_7"]))
        c2.metric("Ganhadores 6 acertos", int(linha["ganhadores_6"]))
        c3.metric("Ganhadores 5 acertos", int(linha["ganhadores_5"]))
        c4.metric("Ganhadores 4 acertos", int(linha["ganhadores_4"]))

elif pagina == "🔄 Atualizar Base":
    selo_topo("🔄", "Manutenção", "Atualizar Base de Dados")
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
