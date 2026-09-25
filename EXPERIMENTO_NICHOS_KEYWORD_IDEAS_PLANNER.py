from __future__ import annotations

"""
EXPERIMENTO_NICHOS_KEYWORD_IDEAS_PLANNER.py

Fluxo correto: Google Ads API via REST direto.
- GenerateKeywordIdeas
- GenerateKeywordHistoricalMetrics
- sem GoogleAdsClient
- sem Google Trends
- sem criar/alterar campanhas

Ao terminar, envie para o ChatGPT:
resultado_experimento_keywords_rest/05_RESULTADO_PARA_CHATGPT.txt
"""

import csv
import json
import os
import sys
import time
import unicodedata
from collections import defaultdict
from pathlib import Path

import requests
from google.auth.transport.requests import Request as GoogleAuthRequest
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow


# =============================================================================
# CONFIGURAÇÃO — MESMO PADRÃO DO DEMO REST VALIDADO
# =============================================================================

API_VERSION = "v25"

CREDENTIALS_JSON = Path(r"C:\Users\Alan\Desktop\credentials.json")

MANAGER_ID = "958-868-7649"
CUSTOMER_ID = "804-276-8058"

SCOPES = ["https://www.googleapis.com/auth/adwords"]
DEVELOPER_TOKEN_ENV = "GOOGLE_ADS_DEVELOPER_TOKEN"

GEO_TARGET = "geoTargetConstants/2076"      # Brasil
LANGUAGE = "languageConstants/1014"         # Português
NETWORK = "GOOGLE_SEARCH"

SCRIPT_DIR = Path(__file__).resolve().parent
TOKEN_CANDIDATES = [
    SCRIPT_DIR / "google_ads_oauth_token.json",
    Path(r"D:\python\google_ads_oauth_token.json"),
]

OUTPUT_DIR = SCRIPT_DIR / "resultado_experimento_keywords_rest"
OUTPUT_IDEAS_JSON = OUTPUT_DIR / "01_keyword_ideas_raw.json"
OUTPUT_HISTORICAL_JSON = OUTPUT_DIR / "02_historical_raw.json"
OUTPUT_KEYWORDS_CSV = OUTPUT_DIR / "03_keywords_detalhadas.csv"
OUTPUT_SUMMARY_CSV = OUTPUT_DIR / "04_resumo_nichos.csv"
OUTPUT_CHATGPT_TXT = OUTPUT_DIR / "05_RESULTADO_PARA_CHATGPT.txt"
OUTPUT_ANALYSIS_JSON = OUTPUT_DIR / "06_analise_completa.json"

TIMEOUT_SECONDS = 180
MAX_RETRIES = 3
TRANSIENT_HTTP = {429, 500, 502, 503, 504}

PAGE_SIZE = 1000
TOP_IDEAS_PER_NICHE = 50
HISTORICAL_BATCH_SIZE = 500
PAUSE_SECONDS = 1.0

STARTED = time.perf_counter()


# =============================================================================
# NICHOS PARA O PRIMEIRO EXPERIMENTO
# =============================================================================

NICHES = {
    "assistencia_celular": {
        "label": "Assistência técnica de celulares",
        "seeds": ["assistência técnica celular", "conserto de celular",
                  "troca de tela celular", "conserto iphone"],
    },
    "baterias_automotivas": {
        "label": "Loja de baterias automotivas",
        "seeds": ["bateria automotiva", "bateria de carro",
                  "troca de bateria carro", "loja de bateria automotiva"],
    },
    "grafica_comunicacao_visual": {
        "label": "Gráfica rápida / comunicação visual",
        "seeds": ["gráfica rápida", "gráfica", "comunicação visual",
                  "impressão gráfica"],
    },
    "despachante_veicular": {
        "label": "Despachante veicular",
        "seeds": ["despachante veicular", "despachante de veículos",
                  "despachante documentação veículo"],
    },
    "autoescola": {
        "label": "Autoescola independente",
        "seeds": ["autoescola", "auto escola", "carteira de motorista",
                  "aulas de direção"],
    },
    "pet_shop_banho_tosa": {
        "label": "Pet shop + banho e tosa",
        "seeds": ["pet shop", "banho e tosa", "banho para cachorro",
                  "tosa de cachorro"],
    },
    "floricultura": {
        "label": "Floricultura",
        "seeds": ["floricultura", "flores", "buquê de flores",
                  "entrega de flores"],
    },
    "barbearia": {
        "label": "Barbearia",
        "seeds": ["barbearia", "barbeiro", "corte masculino",
                  "corte de barba"],
    },
    "centro_automotivo": {
        "label": "Centro automotivo / pneus e alinhamento",
        "seeds": ["centro automotivo", "loja de pneus",
                  "alinhamento e balanceamento", "troca de pneus"],
    },
    "auto_eletrica": {
        "label": "Auto elétrica",
        "seeds": ["auto elétrica", "eletricista automotivo",
                  "conserto elétrico carro"],
    },
    "estetica_automotiva": {
        "label": "Estética automotiva / detalhamento",
        "seeds": ["estética automotiva", "detalhamento automotivo",
                  "polimento automotivo", "higienização automotiva"],
    },
    "lavanderia": {
        "label": "Lavanderia",
        "seeds": ["lavanderia", "lavanderia de roupas", "lavagem de roupa",
                  "lavanderia self service"],
    },
    "locadora_ferramentas": {
        "label": "Locadora de ferramentas / equipamentos",
        "seeds": ["aluguel de ferramentas", "locação de ferramentas",
                  "aluguel de equipamentos", "locadora de ferramentas"],
    },
    "salao_beleza": {
        "label": "Salão de beleza independente",
        "seeds": ["salão de beleza", "cabeleireiro",
                  "corte de cabelo feminino", "escova cabelo"],
    },
    "esmalteria_nail": {
        "label": "Esmalteria / nail studio",
        "seeds": ["esmalteria", "manicure", "nail designer",
                  "alongamento de unhas"],
    },
}


# =============================================================================
# UTILITÁRIOS
# =============================================================================

def elapsed() -> str:
    seconds = time.perf_counter() - STARTED
    minutes, seconds = divmod(seconds, 60)
    hours, minutes = divmod(int(minutes), 60)
    return f"{hours:02d}:{minutes:02d}:{seconds:05.2f}"


def log(message: str) -> None:
    print(f"[{elapsed()}] {message}", flush=True)


def only_digits(value: str) -> str:
    return "".join(ch for ch in str(value) if ch.isdigit())


def norm(text: str) -> str:
    text = unicodedata.normalize("NFKD", str(text or "").strip().casefold())
    text = "".join(ch for ch in text if not unicodedata.combining(ch))
    return " ".join(text.split())


def unique(items):
    seen = set()
    out = []
    for item in items:
        item = str(item or "").strip()
        key = norm(item)
        if item and key not in seen:
            seen.add(key)
            out.append(item)
    return out


def chunks(items, size):
    for i in range(0, len(items), size):
        yield items[i:i + size]


def safe_float(value, default=0.0):
    try:
        return default if value in (None, "") else float(value)
    except (TypeError, ValueError):
        return default


def safe_int(value, default=0):
    try:
        return default if value in (None, "") else int(value)
    except (TypeError, ValueError):
        try:
            return int(float(value))
        except (TypeError, ValueError):
            return default


def micros_to_brl(value):
    return safe_float(value) / 1_000_000.0


def pct_change(new, old):
    if old <= 0:
        return None
    return ((new / old) - 1.0) * 100.0


def fmt_pct(value):
    return "N/D" if value is None else f"{value:+.1f}%"


def fmt_money(value):
    return (f"R$ {value:,.2f}"
            .replace(",", "X").replace(".", ",").replace("X", "."))


def avg(values):
    return sum(values) / len(values) if values else 0.0


# =============================================================================
# OAUTH / HEADERS — COPIADO DO FLUXO REST CORRETO
# =============================================================================

def find_token_cache() -> Path:
    for path in TOKEN_CANDIDATES:
        if path.exists():
            return path
    return TOKEN_CANDIDATES[0]


TOKEN_CACHE_PATH = find_token_cache()


def require_config():
    developer_token = os.getenv(DEVELOPER_TOKEN_ENV, "").strip()
    if not developer_token:
        raise RuntimeError(
            f"Variável de ambiente {DEVELOPER_TOKEN_ENV} não encontrada."
        )

    manager_id = only_digits(MANAGER_ID)
    customer_id = only_digits(CUSTOMER_ID)

    if len(manager_id) != 10 or len(customer_id) != 10:
        raise RuntimeError("Manager ID ou Customer ID inválido.")

    if not TOKEN_CACHE_PATH.exists() and not CREDENTIALS_JSON.exists():
        raise FileNotFoundError(
            "Não encontrei OAuth utilizável.\n"
            f"Cache procurado: {TOKEN_CACHE_PATH}\n"
            f"credentials.json: {CREDENTIALS_JSON}"
        )

    return developer_token, manager_id, customer_id


def save_token(creds: Credentials) -> None:
    TOKEN_CACHE_PATH.parent.mkdir(parents=True, exist_ok=True)
    TOKEN_CACHE_PATH.write_text(creds.to_json(), encoding="utf-8")


def get_credentials() -> Credentials:
    if TOKEN_CACHE_PATH.exists():
        try:
            creds = Credentials.from_authorized_user_file(
                str(TOKEN_CACHE_PATH), SCOPES
            )
            if creds.expired and creds.refresh_token:
                log("OAuth expirado; renovando silenciosamente...")
                creds.refresh(GoogleAuthRequest())
                save_token(creds)
            if creds.valid:
                log(f"OAuth OK: {TOKEN_CACHE_PATH}")
                return creds
        except Exception as exc:
            log(f"Cache OAuth falhou: {exc}")

    if not CREDENTIALS_JSON.exists():
        raise FileNotFoundError(
            f"credentials.json não encontrado: {CREDENTIALS_JSON}"
        )

    log("Cache OAuth não utilizável. Abrindo OAuth no navegador...")
    flow = InstalledAppFlow.from_client_secrets_file(
        str(CREDENTIALS_JSON), scopes=SCOPES
    )
    creds = flow.run_local_server(
        host="localhost",
        port=0,
        open_browser=True,
        access_type="offline",
        prompt="consent",
    )
    save_token(creds)
    log(f"OAuth salvo em: {TOKEN_CACHE_PATH}")
    return creds


def ensure_valid_token(creds: Credentials) -> None:
    if creds.valid:
        return
    if creds.expired and creds.refresh_token:
        creds.refresh(GoogleAuthRequest())
        save_token(creds)
        return
    raise RuntimeError("Credencial OAuth inválida e sem refresh token.")


def build_headers(creds, developer_token, manager_id):
    ensure_valid_token(creds)
    return {
        "Authorization": f"Bearer {creds.token}",
        "developer-token": developer_token,
        "login-customer-id": manager_id,
        "Content-Type": "application/json",
    }


# =============================================================================
# HTTP REST COM RETENTATIVA — MESMO FLUXO DO DEMO
# =============================================================================

def post_google_ads(url, headers, payload):
    last_status = None

    for attempt in range(1, MAX_RETRIES + 1):
        response = requests.post(
            url, headers=headers, json=payload, timeout=TIMEOUT_SECONDS
        )
        last_status = response.status_code

        request_id = (
            response.headers.get("request-id")
            or response.headers.get("x-request-id")
        )

        try:
            body = response.json()
        except Exception:
            body = None

        log(
            f"HTTP {response.status_code}"
            + (f" | request-id={request_id}" if request_id else "")
        )

        if response.ok:
            return body or {}

        if body is not None:
            print(json.dumps(body, ensure_ascii=False, indent=2))
        else:
            print(response.text[:5000])

        if response.status_code not in TRANSIENT_HTTP or attempt == MAX_RETRIES:
            break

        wait = attempt * 2
        log(f"Erro transitório. Tentando novamente em {wait}s...")
        time.sleep(wait)

    raise RuntimeError(
        f"Google Ads API falhou. Último HTTP={last_status}."
    )


# =============================================================================
# FASE 1 — GENERATE KEYWORD IDEAS
# =============================================================================

def generate_keyword_ideas(headers, customer_id, niche_key, config):
    url = (
        f"https://googleads.googleapis.com/{API_VERSION}/"
        f"customers/{customer_id}:generateKeywordIdeas"
    )

    seeds = unique(config["seeds"])
    all_results = []
    raw_pages = []
    page_token = None
    page_number = 0

    while True:
        page_number += 1
        payload = {
            "geoTargetConstants": [GEO_TARGET],
            "language": LANGUAGE,
            "keywordPlanNetwork": NETWORK,
            "includeAdultKeywords": False,
            "historicalMetricsOptions": {"includeAverageCpc": True},
            "keywordSeed": {"keywords": seeds},
            "pageSize": PAGE_SIZE,
        }

        if page_token:
            payload["pageToken"] = page_token

        log(
            f"Keyword Ideas | {config['label']} | página {page_number}"
        )
        body = post_google_ads(url, headers, payload)
        raw_pages.append(body)

        page_results = body.get("results", []) or []
        all_results.extend(page_results)

        log(
            f"{config['label']}: +{len(page_results)} "
            f"| acumulado={len(all_results)}"
        )

        page_token = body.get("nextPageToken")
        if not page_token:
            break

        time.sleep(PAUSE_SECONDS)

    ranked = sorted(
        all_results,
        key=lambda x: safe_int(
            (x.get("keywordIdeaMetrics") or {}).get("avgMonthlySearches")
        ),
        reverse=True,
    )

    top_ideas = unique(
        x.get("text", "")
        for x in ranked[:TOP_IDEAS_PER_NICHE]
        if x.get("text")
    )

    local_seeds = [f"{seed} perto de mim" for seed in seeds]
    selected = unique(seeds + local_seeds + top_ideas)

    return {
        "niche_key": niche_key,
        "label": config["label"],
        "seeds": seeds,
        "local_seeds": local_seeds,
        "ideas_count": len(all_results),
        "selected_keywords": selected,
        "raw_pages": raw_pages,
        "ideas": all_results,
    }


def run_all_ideas(headers, customer_id):
    data = {}

    for i, (niche_key, config) in enumerate(NICHES.items(), start=1):
        log("=" * 78)
        log(f"NICHO {i}/{len(NICHES)} — {config['label']}")
        result = generate_keyword_ideas(
            headers, customer_id, niche_key, config
        )
        data[niche_key] = result
        log(
            f"Ideias={result['ideas_count']} | "
            f"termos p/ histórico={len(result['selected_keywords'])}"
        )
        if i < len(NICHES):
            time.sleep(PAUSE_SECONDS)

    OUTPUT_IDEAS_JSON.write_text(
        json.dumps(
            {
                "api_version": API_VERSION,
                "geo_target": GEO_TARGET,
                "language": LANGUAGE,
                "network": NETWORK,
                "top_ideas_per_niche": TOP_IDEAS_PER_NICHE,
                "niches": data,
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )

    return data


# =============================================================================
# FASE 2 — GENERATE KEYWORD HISTORICAL METRICS
# =============================================================================

def build_contexts(all_niches):
    contexts = defaultdict(list)
    original = {}

    for niche_key, niche in all_niches.items():
        local_norms = {norm(x) for x in niche["local_seeds"]}

        for keyword in niche["selected_keywords"]:
            key = norm(keyword)
            original.setdefault(key, keyword)
            contexts[key].append(
                {
                    "niche_key": niche_key,
                    "requested_keyword": keyword,
                    "local_requested": key in local_norms,
                }
            )

    return list(original.values()), contexts


def generate_historical_metrics(headers, customer_id, keywords):
    url = (
        f"https://googleads.googleapis.com/{API_VERSION}/"
        f"customers/{customer_id}:generateKeywordHistoricalMetrics"
    )

    payload = {
        "keywords": keywords,
        "geoTargetConstants": [GEO_TARGET],
        "language": LANGUAGE,
        "keywordPlanNetwork": NETWORK,
        "includeAdultKeywords": False,
        "historicalMetricsOptions": {"includeAverageCpc": True},
    }

    return post_google_ads(url, headers, payload)


def run_historical(headers, customer_id, all_niches):
    all_keywords, contexts = build_contexts(all_niches)
    batches = list(chunks(all_keywords, HISTORICAL_BATCH_SIZE))

    raw_batches = []
    mapped = []

    log(f"Termos históricos únicos: {len(all_keywords)}")

    for i, keyword_batch in enumerate(batches, start=1):
        log(
            f"Historical lote {i}/{len(batches)} "
            f"| {len(keyword_batch)} termos"
        )
        body = generate_historical_metrics(
            headers, customer_id, keyword_batch
        )

        raw_batches.append(
            {
                "batch_number": i,
                "keywords_requested": keyword_batch,
                "response": body,
            }
        )

        for result in body.get("results", []) or []:
            canonical = str(result.get("text", "") or "")
            close_variants = [
                str(x) for x in (result.get("closeVariants", []) or [])
            ]

            matched_contexts = []
            seen = set()

            for candidate in unique([canonical] + close_variants):
                for ctx in contexts.get(norm(candidate), []):
                    key = (
                        ctx["niche_key"],
                        ctx["local_requested"],
                        norm(ctx["requested_keyword"]),
                    )
                    if key not in seen:
                        seen.add(key)
                        matched_contexts.append(ctx)

            mapped.append(
                {
                    "canonical_text": canonical,
                    "close_variants": close_variants,
                    "contexts": matched_contexts,
                    "raw": result,
                }
            )

        if i < len(batches):
            time.sleep(PAUSE_SECONDS)

    OUTPUT_HISTORICAL_JSON.write_text(
        json.dumps(
            {
                "keywords_requested": all_keywords,
                "geo_target": GEO_TARGET,
                "language": LANGUAGE,
                "network": NETWORK,
                "batches": raw_batches,
                "mapped_results": mapped,
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )

    return mapped


# =============================================================================
# PARSE E AGREGAÇÃO
# =============================================================================

MONTHS = {
    "JANUARY": 1, "FEBRUARY": 2, "MARCH": 3, "APRIL": 4,
    "MAY": 5, "JUNE": 6, "JULY": 7, "AUGUST": 8,
    "SEPTEMBER": 9, "OCTOBER": 10, "NOVEMBER": 11, "DECEMBER": 12,
}


def parse_series(metrics):
    series = []
    for item in metrics.get("monthlySearchVolumes", []) or []:
        year = safe_int(item.get("year"))
        month = MONTHS.get(str(item.get("month", "")).upper(), 0)
        searches = safe_int(item.get("monthlySearches"))
        if year and month:
            series.append(
                {"year": year, "month": month, "searches": searches}
            )

    series.sort(key=lambda x: (x["year"], x["month"]))
    return series


def parse_mapped_result(mapped):
    metrics = (mapped["raw"].get("keywordMetrics") or {})
    series = parse_series(metrics)

    all_values = [x["searches"] for x in series]
    recent_3 = avg([x["searches"] for x in series[-3:]])
    previous = avg([x["searches"] for x in series[:-3]])
    first_3 = avg([x["searches"] for x in series[:3]])

    volume = (
        avg(all_values)
        if all_values
        else float(safe_int(metrics.get("avgMonthlySearches")))
    )

    by_niche = defaultdict(list)
    for ctx in mapped["contexts"]:
        by_niche[ctx["niche_key"]].append(ctx)

    rows = []
    for niche_key, ctxs in by_niche.items():
        rows.append(
            {
                "niche_key": niche_key,
                "niche": NICHES[niche_key]["label"],
                "keyword": mapped["canonical_text"],
                "requested_keywords": unique(
                    x["requested_keyword"] for x in ctxs
                ),
                "close_variants": mapped["close_variants"],
                "local_requested": any(
                    x["local_requested"] for x in ctxs
                ),
                "avg_monthly_searches_api": safe_int(
                    metrics.get("avgMonthlySearches")
                ),
                "volume_monthly": volume,
                "recent_3m_avg": recent_3,
                "previous_period_avg": previous,
                "momentum_pct": pct_change(recent_3, previous),
                "end_vs_start_pct": pct_change(recent_3, first_3),
                "competition": str(metrics.get("competition", "") or ""),
                "competition_index": safe_float(
                    metrics.get("competitionIndex")
                ),
                "average_cpc_brl": micros_to_brl(
                    metrics.get("averageCpcMicros")
                ),
                "low_top_bid_brl": micros_to_brl(
                    metrics.get("lowTopOfPageBidMicros")
                ),
                "high_top_bid_brl": micros_to_brl(
                    metrics.get("highTopOfPageBidMicros")
                ),
                "months_available": len(series),
                "monthly_series": series,
            }
        )

    return rows


def weighted_average(rows, value_key, weight_key="volume_monthly"):
    weighted_sum = 0.0
    total_weight = 0.0

    for row in rows:
        value = row.get(value_key)
        weight = max(safe_float(row.get(weight_key)), 0.0)
        if value is None or weight <= 0:
            continue
        weighted_sum += safe_float(value) * weight
        total_weight += weight

    return weighted_sum / total_weight if total_weight else 0.0


def top_k_volume(rows, k):
    ordered = sorted(
        rows, key=lambda x: x["volume_monthly"], reverse=True
    )
    return sum(x["volume_monthly"] for x in ordered[:k])


def percentile(values, value):
    values = sorted(safe_float(x) for x in values)
    if len(values) <= 1:
        return 50.0
    below = sum(1 for x in values if x < value)
    equal = sum(1 for x in values if x == value)
    midpoint = below + ((equal - 1) / 2)
    return max(0.0, min(100.0, midpoint / (len(values) - 1) * 100.0))


def build_summaries(rows):
    by_niche = defaultdict(list)
    for row in rows:
        by_niche[row["niche_key"]].append(row)

    summaries = []

    for niche_key, config in NICHES.items():
        niche_rows = by_niche.get(niche_key, [])
        local_rows = [x for x in niche_rows if x["local_requested"]]

        summaries.append(
            {
                "niche_key": niche_key,
                "niche": config["label"],
                "keyword_clusters": len(niche_rows),
                "top10_volume": top_k_volume(niche_rows, 10),
                "top20_volume": top_k_volume(niche_rows, 20),
                "explicit_local_volume": sum(
                    x["volume_monthly"] for x in local_rows
                ),
                "weighted_competition_index": weighted_average(
                    niche_rows, "competition_index"
                ),
                "weighted_average_cpc_brl": weighted_average(
                    niche_rows, "average_cpc_brl"
                ),
                "weighted_high_top_bid_brl": weighted_average(
                    niche_rows, "high_top_bid_brl"
                ),
                "weighted_momentum_pct": weighted_average(
                    [x for x in niche_rows if x["momentum_pct"] is not None],
                    "momentum_pct",
                ),
                "top_keywords": sorted(
                    niche_rows,
                    key=lambda x: x["volume_monthly"],
                    reverse=True,
                )[:10],
            }
        )

    demand = [x["top10_volume"] for x in summaries]
    local = [x["explicit_local_volume"] for x in summaries]
    cpc = [x["weighted_average_cpc_brl"] for x in summaries]
    comp = [x["weighted_competition_index"] for x in summaries]
    momentum = [x["weighted_momentum_pct"] for x in summaries]

    for row in summaries:
        p = {
            "demand": percentile(demand, row["top10_volume"]),
            "local": percentile(local, row["explicit_local_volume"]),
            "cpc": percentile(cpc, row["weighted_average_cpc_brl"]),
            "competition": percentile(
                comp, row["weighted_competition_index"]
            ),
            "momentum": percentile(
                momentum, row["weighted_momentum_pct"]
            ),
        }

        row["score_components"] = p
        row["score_exploratory_0_100"] = (
            0.35 * p["demand"]
            + 0.25 * p["local"]
            + 0.20 * p["cpc"]
            + 0.10 * p["competition"]
            + 0.10 * p["momentum"]
        )

    summaries.sort(
        key=lambda x: x["score_exploratory_0_100"], reverse=True
    )

    for rank, row in enumerate(summaries, start=1):
        row["rank"] = rank

    return summaries


# =============================================================================
# EXPORTAÇÕES
# =============================================================================

def export_keywords_csv(rows):
    fields = [
        "niche", "keyword", "requested_keywords", "close_variants",
        "local_requested", "avg_monthly_searches_api", "volume_monthly",
        "recent_3m_avg", "previous_period_avg", "momentum_pct",
        "end_vs_start_pct", "competition", "competition_index",
        "average_cpc_brl", "low_top_bid_brl", "high_top_bid_brl",
        "months_available",
    ]

    with OUTPUT_KEYWORDS_CSV.open(
        "w", newline="", encoding="utf-8-sig"
    ) as file:
        writer = csv.DictWriter(file, fieldnames=fields, delimiter=";")
        writer.writeheader()

        for row in rows:
            writer.writerow(
                {
                    "niche": row["niche"],
                    "keyword": row["keyword"],
                    "requested_keywords": " | ".join(
                        row["requested_keywords"]
                    ),
                    "close_variants": " | ".join(row["close_variants"]),
                    "local_requested": (
                        "SIM" if row["local_requested"] else "NAO"
                    ),
                    "avg_monthly_searches_api": row[
                        "avg_monthly_searches_api"
                    ],
                    "volume_monthly": round(row["volume_monthly"], 2),
                    "recent_3m_avg": round(row["recent_3m_avg"], 2),
                    "previous_period_avg": round(
                        row["previous_period_avg"], 2
                    ),
                    "momentum_pct": (
                        "" if row["momentum_pct"] is None
                        else round(row["momentum_pct"], 2)
                    ),
                    "end_vs_start_pct": (
                        "" if row["end_vs_start_pct"] is None
                        else round(row["end_vs_start_pct"], 2)
                    ),
                    "competition": row["competition"],
                    "competition_index": round(
                        row["competition_index"], 2
                    ),
                    "average_cpc_brl": round(row["average_cpc_brl"], 2),
                    "low_top_bid_brl": round(row["low_top_bid_brl"], 2),
                    "high_top_bid_brl": round(
                        row["high_top_bid_brl"], 2
                    ),
                    "months_available": row["months_available"],
                }
            )


def export_summary_csv(summaries):
    fields = [
        "rank", "niche", "score_exploratory_0_100", "keyword_clusters",
        "top10_volume", "top20_volume", "explicit_local_volume",
        "weighted_competition_index", "weighted_average_cpc_brl",
        "weighted_high_top_bid_brl", "weighted_momentum_pct",
    ]

    with OUTPUT_SUMMARY_CSV.open(
        "w", newline="", encoding="utf-8-sig"
    ) as file:
        writer = csv.DictWriter(file, fieldnames=fields, delimiter=";")
        writer.writeheader()
        for row in summaries:
            writer.writerow(
                {
                    key: (
                        round(row[key], 2)
                        if isinstance(row.get(key), float)
                        else row.get(key)
                    )
                    for key in fields
                }
            )


def export_chatgpt_txt(summaries):
    lines = [
        "=" * 92,
        "RESULTADO — KEYWORD IDEAS + HISTORICAL METRICS — REST",
        "=" * 92,
        "",
        f"API: {API_VERSION}",
        f"Geo: {GEO_TARGET}",
        f"Idioma: {LANGUAGE}",
        f"Rede: {NETWORK}",
        f"Nichos: {len(NICHES)}",
        "",
        "IMPORTANTE: este score é só priorização exploratória do mercado "
        "de busca. NÃO mede resposta no WhatsApp, fechamento, risco "
        "operacional do Perfil da Empresa no Google nem lucro.",
        "",
        "=" * 92,
        "RANKING EXPLORATÓRIO",
        "=" * 92,
    ]

    for row in summaries:
        lines += [
            "",
            (
                f"#{row['rank']} — {row['niche']} | "
                f"SCORE {row['score_exploratory_0_100']:.1f}/100"
            ),
            f"  Clusters históricos: {row['keyword_clusters']}",
            f"  Volume top10: {row['top10_volume']:.0f}/mês",
            (
                f"  Volume explicitamente local: "
                f"{row['explicit_local_volume']:.0f}/mês"
            ),
            (
                f"  CPC médio ponderado: "
                f"{fmt_money(row['weighted_average_cpc_brl'])}"
            ),
            (
                f"  Lance topo alto ponderado: "
                f"{fmt_money(row['weighted_high_top_bid_brl'])}"
            ),
            (
                f"  Competição Ads ponderada: "
                f"{row['weighted_competition_index']:.1f}/100"
            ),
            (
                f"  Momentum recente ponderado: "
                f"{fmt_pct(row['weighted_momentum_pct'])}"
            ),
            "  Top keywords:",
        ]

        for kw in row["top_keywords"][:8]:
            lines.append(
                f"    - {kw['keyword']} | "
                f"volume={kw['volume_monthly']:.0f}/mês | "
                f"3m={kw['recent_3m_avg']:.0f}/mês | "
                f"CPC={fmt_money(kw['average_cpc_brl'])} | "
                f"Comp={kw['competition_index']:.0f} | "
                f"Local={'SIM' if kw['local_requested'] else 'NAO'}"
            )

    lines += [
        "",
        "=" * 92,
        "PRÓXIMO PASSO",
        "=" * 92,
        "",
        (
            "Cruze estes dados com o FIT anterior da Veriluno e escolha "
            "uma bateria pequena de nichos para testar com o limite de "
            "aproximadamente 50 mensagens/dia."
        ),
        (
            "Antes de aceitar o ranking, cheque ruído semântico: volume "
            "alto pode vir de buscas que não representam procura local "
            "pelo tipo de empresa que queremos prospectar."
        ),
    ]

    OUTPUT_CHATGPT_TXT.write_text(
        "\n".join(lines), encoding="utf-8"
    )


def print_summary(summaries):
    print()
    print("=" * 112)
    print("RANKING EXPLORATÓRIO — GOOGLE ADS REST")
    print("=" * 112)
    print(
        f"{'#':>2}  {'NICHO':<40} {'SCORE':>7} {'VOL10':>10} "
        f"{'LOCAL':>10} {'CPC':>9} {'COMP':>7} {'MOM':>9}"
    )
    print("-" * 112)

    for row in summaries:
        print(
            f"{row['rank']:>2}  {row['niche'][:40]:<40} "
            f"{row['score_exploratory_0_100']:>7.1f} "
            f"{row['top10_volume']:>10.0f} "
            f"{row['explicit_local_volume']:>10.0f} "
            f"{row['weighted_average_cpc_brl']:>9.2f} "
            f"{row['weighted_competition_index']:>7.1f} "
            f"{row['weighted_momentum_pct']:>8.1f}%"
        )

    print("=" * 112)
    print()
    print("Depois me mande este arquivo:")
    print(OUTPUT_CHATGPT_TXT)
    print()


# =============================================================================
# MAIN
# =============================================================================

def main():
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    log("=" * 78)
    log("EXPERIMENTO NICHOS — GOOGLE ADS API REST")
    log("Keyword Ideas + Historical Metrics")
    log("SEM GoogleAdsClient | SEM Google Trends")
    log("=" * 78)

    developer_token, manager_id, customer_id = require_config()

    log(f"API: {API_VERSION}")
    log(f"Manager ID: {manager_id}")
    log(f"Customer ID: {customer_id}")
    log(f"Geo: {GEO_TARGET}")
    log(f"Idioma: {LANGUAGE}")
    log(f"Rede: {NETWORK}")
    log(f"Nichos: {len(NICHES)}")
    log(f"Saída: {OUTPUT_DIR}")

    creds = get_credentials()
    headers = build_headers(
        creds, developer_token, manager_id
    )

    log("")
    log("=" * 78)
    log("FASE 1 — GENERATE KEYWORD IDEAS")
    log("=" * 78)

    all_niches = run_all_ideas(headers, customer_id)

    log("")
    log("=" * 78)
    log("FASE 2 — GENERATE KEYWORD HISTORICAL METRICS")
    log("=" * 78)

    mapped = run_historical(
        headers, customer_id, all_niches
    )

    rows = []
    for item in mapped:
        rows.extend(parse_mapped_result(item))

    log(f"Linhas históricas mapeadas: {len(rows)}")

    summaries = build_summaries(rows)

    export_keywords_csv(rows)
    export_summary_csv(summaries)
    export_chatgpt_txt(summaries)

    OUTPUT_ANALYSIS_JSON.write_text(
        json.dumps(
            {"summary": summaries, "keywords": rows},
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )

    print_summary(summaries)

    log("=" * 78)
    log("CONCLUÍDO")
    log(f"Ideas JSON: {OUTPUT_IDEAS_JSON}")
    log(f"Historical JSON: {OUTPUT_HISTORICAL_JSON}")
    log(f"Resumo CSV: {OUTPUT_SUMMARY_CSV}")
    log(f"Arquivo p/ ChatGPT: {OUTPUT_CHATGPT_TXT}")
    log(f"Tempo total: {elapsed()}")
    log("=" * 78)


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        log("Execução interrompida pelo usuário.")
        sys.exit(130)
    except Exception as exc:
        log("ERRO")
        print(f"{type(exc).__name__}: {exc}", file=sys.stderr)
        raise
