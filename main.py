from fastapi import FastAPI
import pandas as pd
import numpy as np
import requests
from functools import lru_cache
from fastapi.middleware.cors import CORSMiddleware

app = FastAPI()

# =========================
# CORS
# =========================
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# =========================
# CACHE DE DADOS BASE
# =========================
import time

CACHE_TEMPO = 300  # 5 minutos
_cache = {"data": None, "timestamp": 0}

def carregar_dados():
    agora = time.time()

    if _cache["data"] is None or (agora - _cache["timestamp"] > CACHE_TEMPO):
        url = "https://loteriascaixa-api.herokuapp.com/api/megasena"
        raw = requests.get(url).json()
        df = pd.DataFrame(raw)

        df["data"] = pd.to_datetime(df["data"], format="%d/%m/%Y")
        df = df.sort_values("data")

        _cache["data"] = df.reset_index(drop=True)
        _cache["timestamp"] = agora

    return _cache["data"]

# =========================
# PREPARAÇÃO DOS DADOS
# =========================
@lru_cache(maxsize=1)
def preparar_dados():
    df = carregar_dados()

    dezenas = df["dezenas"].apply(lambda x: list(map(int, x)))
    df_nums = pd.DataFrame(dezenas.tolist(), columns=[f"D{i}" for i in range(1,7)])

    ultimo = df.iloc[-1]

    return df, df_nums, ultimo

# =========================
# MÉTRICAS (CACHE)
# =========================
@lru_cache(maxsize=1)
def calcular_metricas():
    df, df_nums, _ = preparar_dados()

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

    return metrics

# =========================
# FUNÇÃO PRINCIPAL
# =========================
def gerar_jogo(estrategia, modo):
    metrics = calcular_metricas()

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
# ENDPOINTS
# =========================
@app.get("/")
def home():
    return {"status": "API rodando"}

@app.api_route("/health", methods=["GET", "HEAD"])
def health():
    return {"status": "ok"}
    
@app.get("/gerar-jogos")
def gerar(estrategia: str, modo: str, quantidade: int = 1):
    jogos = []

    for _ in range(quantidade):
        jogos.append(gerar_jogo(estrategia, modo))

    _, _, ultimo_concurso = preparar_dados()
    metrics = calcular_metricas()

    return {
        "ultimo_concurso": int(ultimo_concurso["concurso"]),
        "data": str(ultimo_concurso["data"]),
        "resultado_ultimo": ultimo_concurso["dezenas"],
        "jogos": jogos,
        "estatisticas": {
            "frequencia_total": metrics["Frequência Total"].to_dict(),
            "frequencia_recente": metrics["Frequência Recente"].to_dict(),
            "atraso": metrics["Atraso"].to_dict(),
            "score": metrics["Score Estatístico"].to_dict()
        }
    }

@app.get("/historico")
def buscar_historico(concurso: int = None, data: str = None):
    df = carregar_dados()

    if concurso:
        resultado = df[df["concurso"] == concurso]
    elif data:
        data_convertida = pd.to_datetime(data)
        resultado = df[df["data"] == data_convertida]
    else:
        return {"erro": "Informe concurso ou data"}

    if resultado.empty:
        return {"erro": "Nenhum resultado encontrado"}

    row = resultado.iloc[0]

    return {
        "concurso": int(row["concurso"]),
        "data": str(row["data"]),
        "dezenas": row["dezenas"]
    }
