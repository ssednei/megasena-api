from fastapi import FastAPI
import pandas as pd
import numpy as np
import requests

app = FastAPI()

# =========================
# LOAD DATA
# =========================
def load_data():
    url = "https://loteriascaixa-api.herokuapp.com/api/megasena"
    raw = requests.get(url).json()
    df = pd.DataFrame(raw)
    df["data"] = pd.to_datetime(df["data"], format="%d/%m/%Y")
    df = df.sort_values("data")

    dezenas = df["dezenas"].apply(lambda x: list(map(int, x)))
    df_nums = pd.DataFrame(dezenas.tolist(), columns=[f"D{i}" for i in range(1,7)])

    ultimo = df.iloc[-1]

    return df.reset_index(drop=True), df_nums, ultimo

df, df_nums, ultimo_concurso = load_data()

# =========================
# MÉTRICAS
# =========================
all_numbers = df_nums.values.flatten()
freq_total = pd.Series(all_numbers).value_counts().sort_index()

recent = df_nums.tail(100).values.flatten()
freq_recent = pd.Series(recent).value_counts().sort_index()

last_seen = {}
for n in range(1, 61):
    mask = df_nums.isin([n]).any(axis=1)
    last_seen[n] = (len(df_nums) - mask[::-1].idxmax()) if mask.any() else len(df_nums)

metrics = pd.DataFrame({
    "Frequência Total": freq_total,
    "Frequência Recente": freq_recent,
    "Atraso": pd.Series(last_seen)
}).fillna(0)

metrics["Score Estatístico"] = (
    0.4 * (metrics["Frequência Total"] / metrics["Frequência Total"].max()) +
    0.4 * (metrics["Frequência Recente"] / metrics["Frequência Recente"].max()) +
    0.2 * (metrics["Atraso"] / metrics["Atraso"].max())
)

# =========================
# FUNÇÃO PRINCIPAL
# =========================
def gerar_jogo(estrategia, modo):
    if estrategia == "Mais Frequentes":
        base = metrics.sort_values("Frequência Total", ascending=False)
    elif estrategia == "Menos Frequentes":
        base = metrics.sort_values("Frequência Total")
    elif estrategia == "Mais Atrasados":
        base = metrics.sort_values("Atraso", ascending=False)
    elif estrategia == "Frequência Recente":
        base = metrics.sort_values("Frequência Recente", ascending=False)
    else:
        base = metrics.sort_values("Score Estatístico", ascending=False)

    if modo == "Números fixos estatisticamente":
        jogo = base.head(6).index.tolist()
    else:
        pesos = base["Score Estatístico"].values
        pesos = pesos / pesos.sum()
        jogo = np.random.choice(base.index, size=6, replace=False, p=pesos).tolist()

    return sorted(jogo)

# =========================
# ENDPOINT
# =========================
@app.get("/")
def home():
    return {"status": "API rodando"}

@app.get("/gerar-jogos")
def gerar(estrategia: str, modo: str, quantidade: int = 1):
    jogos = []

    for _ in range(quantidade):
        jogos.append(gerar_jogo(estrategia, modo))

    return {
        "ultimo_concurso": int(ultimo_concurso["concurso"]),
        "data": str(ultimo_concurso["data"]),
        "jogos": jogos
    }