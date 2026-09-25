"""
EXPERIMENTO_NICHOS_KEYWORD_IDEAS_PLANNER.py

Objetivo
--------
Usar SOMENTE Google Ads API:
1) Keyword Ideas para descobrir como as pessoas pesquisam cada nicho.
2) Keyword Planner / Historical Metrics para medir demanda, histórico,
   concorrência publicitária e valor comercial aproximado.

O script NÃO usa Google Trends.

A finalidade é produzir dados para decidir quais nichos merecem receber
primeiro a capacidade limitada de prospecção por WhatsApp.

Base técnica
------------
Mantém o mesmo padrão do arquivo:
DEMO_GOOGLE_ADS_KEYWORD_IDEAS_E_PLANNER.py

- Google Ads API v25
- OAuth via credentials.json
- cache local google_ads_oauth_token.json
- developer token em GOOGLE_ADS_DEVELOPER_TOKEN
- MCC/login_customer_id
- KeywordPlanIdeaService
- GenerateKeywordIdeas
- GenerateKeywordHistoricalMetrics

Saídas
------
Cria uma pasta "resultado_experimento_keywords" ao lado deste .py com:

01_keyword_ideas_raw.json
02_historical_raw.json
03_keywords_detalhadas.csv
04_resumo_nichos.csv
05_RESULTADO_PARA_CHATGPT.txt

O arquivo 05_RESULTADO_PARA_CHATGPT.txt foi feito especificamente para
você copiar/colar no ChatGPT depois da execução.
"""

import csv
import json
import math
import os
import statistics
import sys
import time
import unicodedata
from collections import defaultdict
from datetime import date
from pathlib import Path
from typing import Dict, Iterable, List, Set, Tuple

from google.ads.googleads.client import GoogleAdsClient
from google.auth.transport.requests import Request as GoogleAuthRequest
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from google.protobuf.json_format import MessageToDict


API_VERSION = "v25"

LOGIN_CUSTOMER_ID = "9588687649"
CUSTOMER_ID = "8042768058"

CREDENTIALS_PATH = Path(r"C:\Users\Alan\Desktop\credentials.json")
TOKEN_CACHE_PATH = Path(__file__).resolve().parent / "google_ads_oauth_token.json"

SCOPES = ["https://www.googleapis.com/auth/adwords"]

GEO_TARGET = "geoTargetConstants/2076"
LANGUAGE = "languageConstants/1014"

NETWORK_NAME = "GOOGLE_SEARCH"

TOP_IDEAS_PER_NICHE = 50
HISTORICAL_BATCH_SIZE = 500
SLEEP_BETWEEN_IDEA_CALLS = 2.0
HISTORICAL_MONTHS = 48

OUTPUT_DIR = Path(__file__).resolve().parent / "resultado_experimento_keywords"
IDEAS_JSON = OUTPUT_DIR / "01_keyword_ideas_raw.json"
HISTORICAL_JSON = OUTPUT_DIR / "02_historical_raw.json"
KEYWORDS_CSV = OUTPUT_DIR / "03_keywords_detalhadas.csv"
SUMMARY_CSV = OUTPUT_DIR / "04_resumo_nichos.csv"
CHATGPT_TXT = OUTPUT_DIR / "05_RESULTADO_PARA_CHATGPT.txt"

START_TIME = time.perf_counter()

NICHES = {
    "assistencia_celular": {
        "label": "Assistência técnica de celulares",
        "seeds": [
            "assistência técnica celular",
            "conserto de celular",
            "troca de tela celular",
            "conserto iphone",
        ],
    },
    "baterias_automotivas": {
        "label": "Loja de baterias automotivas",
        "seeds": [
            "bateria automotiva",
            "bateria de carro",
            "troca de bateria carro",
            "loja de bateria automotiva",
        ],
    },
    "grafica_comunicacao_visual": {
        "label": "Gráfica rápida / comunicação visual",
        "seeds": [
            "gráfica rápida",
            "gráfica",
            "comunicação visual",
            "impressão gráfica",
        ],
    },
    "despachante_veicular": {
        "label": "Despachante veicular",
        "seeds": [
            "despachante veicular",
            "despachante de veículos",
            "despachante documentação veículo",
        ],
    },
    "autoescola": {
        "label": "Autoescola independente",
        "seeds": [
            "autoescola",
            "auto escola",
            "carteira de motorista",
            "aulas de direção",
        ],
    },
    "pet_shop_banho_tosa": {
        "label": "Pet shop + banho e tosa",
        "seeds": [
            "pet shop",
            "banho e tosa",
            "banho para cachorro",
            "tosa de cachorro",
        ],
    },
    "floricultura": {
        "label": "Floricultura",
        "seeds": [
            "floricultura",
            "flores",
            "buquê de flores",
            "entrega de flores",
        ],
    },
    "barbearia": {
        "label": "Barbearia",
        "seeds": [
            "barbearia",
            "barbeiro",
            "corte masculino",
            "corte de barba",
        ],
    },
    "centro_automotivo": {
        "label": "Centro automotivo / pneus e alinhamento",
        "seeds": [
            "centro automotivo",
            "loja de pneus",
            "alinhamento e balanceamento",
            "troca de pneus",
        ],
    },
    "auto_eletrica": {
        "label": "Auto elétrica",
        "seeds": [
            "auto elétrica",
            "eletricista automotivo",
            "conserto elétrico carro",
        ],
    },
    "estetica_automotiva": {
        "label": "Estética automotiva / detalhamento",
        "seeds": [
            "estética automotiva",
            "detalhamento automotivo",
            "polimento automotivo",
            "higienização automotiva",
        ],
    },
    "lavanderia": {
        "label": "Lavanderia",
        "seeds": [
            "lavanderia",
            "lavanderia de roupas",
            "lavagem de roupa",
            "lavanderia self service",
        ],
    },
    "locadora_ferramentas": {
        "label": "Locadora de ferramentas / equipamentos",
        "seeds": [
            "aluguel de ferramentas",
            "locação de ferramentas",
            "aluguel de equipamentos",
            "locadora de ferramentas",
        ],
    },
    "salao_beleza": {
        "label": "Salão de beleza independente",
        "seeds": [
            "salão de beleza",
            "cabeleireiro",
            "corte de cabelo feminino",
            "escova cabelo",
        ],
    },
    "esmalteria_nail": {
        "label": "Esmalteria / nail studio",
        "seeds": [
            "esmalteria",
            "manicure",
            "nail designer",
            "alongamento de unhas",
        ],
    },
}

LOCAL_MARKERS = (
    "perto de mim",
    "próximo de mim",
    "proximo de mim",
    "mais próximo",
    "mais proximo",
)


def elapsed() -> str:
    seconds = time.perf_counter() - START_TIME
    minutes, seconds = divmod(seconds, 60)
    hours, minutes = divmod(int(minutes), 60)
    return f"{hours:02d}:{minutes:02d}:{seconds:05.2f}"


def log(message: str) -> None:
    print(f"[{elapsed()}] {message}", flush=True)


def proto_to_dict(message) -> dict:
    pb = getattr(message, "_pb", message)
    return MessageToDict(
        pb,
        preserving_proto_field_name=True,
        use_integers_for_enums=False,
    )


def save_json(path: Path, data) -> None:
    path.write_text(
        json.dumps(data, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


def unique_preserving_order(items: Iterable[str]) -> List[str]:
    seen = set()
    output = []
    for item in items:
        item = str(item).strip()
        key = normalize_text(item)
        if item and key not in seen:
            seen.add(key)
            output.append(item)
    return output


def chunks(items: List[str], size: int):
    for i in range(0, len(items), size):
        yield items[i:i + size]


def normalize_text(text: str) -> str:
    text = str(text or "").strip().casefold()
    text = unicodedata.normalize("NFKD", text)
    text = "".join(ch for ch in text if not unicodedata.combining(ch))
    return " ".join(text.split())


def safe_float(value, default=0.0) -> float:
    try:
        if value is None or value == "":
            return default
        return float(value)
    except (TypeError, ValueError):
        return default


def safe_int(value, default=0) -> int:
    try:
        if value is None or value == "":
            return default
        return int(value)
    except (TypeError, ValueError):
        try:
            return int(float(value))
        except (TypeError, ValueError):
            return default


def micros_to_brl(value) -> float:
    return safe_float(value) / 1_000_000.0


def pct_change(new: float, old: float):
    if old <= 0:
        return None
    return ((new / old) - 1.0) * 100.0


def fmt_pct(value) -> str:
    if value is None:
        return "N/D"
    return f"{value:+.1f}%"


def fmt_money(value) -> str:
    return f"R$ {value:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")


def is_local_intent(text: str) -> bool:
    norm = normalize_text(text)
    return any(normalize_text(marker) in norm for marker in LOCAL_MARKERS)


def add_months(year: int, month: int, delta: int) -> Tuple[int, int]:
    zero_based = year * 12 + (month - 1) + delta
    new_year, new_month0 = divmod(zero_based, 12)
    return new_year, new_month0 + 1


def historical_range_48m() -> Tuple[Tuple[int, int], Tuple[int, int]]:
    today = date.today()
    end_year, end_month = add_months(today.year, today.month, -1)
    start_year, start_month = add_months(end_year, end_month, -(HISTORICAL_MONTHS - 1))
    return (start_year, start_month), (end_year, end_month)


MONTH_ENUM_NAMES = {
    1: "JANUARY", 2: "FEBRUARY", 3: "MARCH", 4: "APRIL",
    5: "MAY", 6: "JUNE", 7: "JULY", 8: "AUGUST",
    9: "SEPTEMBER", 10: "OCTOBER", 11: "NOVEMBER", 12: "DECEMBER",
}

MONTH_NAME_TO_NUMBER = {name: number for number, name in MONTH_ENUM_NAMES.items()}


def load_oauth_credentials() -> Credentials:
    creds = None
    if TOKEN_CACHE_PATH.exists():
        log(f"Carregando token OAuth: {TOKEN_CACHE_PATH}")
        creds = Credentials.from_authorized_user_file(str(TOKEN_CACHE_PATH), SCOPES)
    if creds and creds.expired and creds.refresh_token:
        log("Token expirado. Renovando...")
        creds.refresh(GoogleAuthRequest())
    if not creds or not creds.valid:
        if not CREDENTIALS_PATH.exists():
            raise FileNotFoundError(f"credentials.json não encontrado: {CREDENTIALS_PATH}")
        log("Abrindo autenticação OAuth no navegador...")
        flow = InstalledAppFlow.from_client_secrets_file(str(CREDENTIALS_PATH), SCOPES)
        creds = flow.run_local_server(port=0, access_type="offline", prompt="consent")
    TOKEN_CACHE_PATH.write_text(creds.to_json(), encoding="utf-8")
    log("OAuth pronto.")
    return creds


def build_google_ads_client(creds: Credentials) -> GoogleAdsClient:
    developer_token = os.environ.get("GOOGLE_ADS_DEVELOPER_TOKEN")
    if not developer_token:
        raise RuntimeError("Variável GOOGLE_ADS_DEVELOPER_TOKEN não encontrada.")
    config = {
        "developer_token": developer_token,
        "login_customer_id": LOGIN_CUSTOMER_ID,
        "client_id": creds.client_id,
        "client_secret": creds.client_secret,
        "refresh_token": creds.refresh_token,
        "use_proto_plus": True,
    }
    return GoogleAdsClient.load_from_dict(config)


def build_local_seeds(seeds: List[str]) -> List[str]:
    return [f"{seed} perto de mim" for seed in seeds]


def run_keyword_ideas_for_niche(client: GoogleAdsClient, niche_key: str, niche_config: dict):
    label = niche_config["label"]
    seeds = unique_preserving_order(niche_config["seeds"])
    log("=" * 78)
    log(f"KEYWORD IDEAS — {label}")
    log(f"Sementes: {', '.join(seeds)}")
    service = client.get_service("KeywordPlanIdeaService", version=API_VERSION)
    request = client.get_type("GenerateKeywordIdeasRequest", version=API_VERSION)
    request.customer_id = CUSTOMER_ID
    request.language = LANGUAGE
    request.geo_target_constants.append(GEO_TARGET)
    request.include_adult_keywords = False
    request.keyword_plan_network = getattr(client.enums.KeywordPlanNetworkEnum, NETWORK_NAME)
    request.keyword_seed.keywords.extend(seeds)
    response = service.generate_keyword_ideas(request=request)
    results = list(response.results)
    log(f"Ideias recebidas: {len(results)}")
    raw_results = [proto_to_dict(result) for result in results]
    ranked = sorted(
        results,
        key=lambda result: safe_int(getattr(getattr(result, "keyword_idea_metrics", None), "avg_monthly_searches", 0)),
        reverse=True,
    )
    top_ideas = [result.text for result in ranked[:TOP_IDEAS_PER_NICHE] if getattr(result, "text", None)]
    local_seeds = build_local_seeds(seeds)
    selected_keywords = unique_preserving_order(seeds + local_seeds + top_ideas)
    log(f"Termos selecionados para histórico: {len(selected_keywords)}")
    return {
        "niche_key": niche_key,
        "label": label,
        "seeds": seeds,
        "local_seeds": local_seeds,
        "ideas_count": len(results),
        "selected_keywords": selected_keywords,
        "raw_response": proto_to_dict(response),
        "raw_results": raw_results,
    }


def run_all_keyword_ideas(client: GoogleAdsClient):
    all_niches = {}
    total = len(NICHES)
    for index, (niche_key, niche_config) in enumerate(NICHES.items(), start=1):
        log(f"NICHO {index}/{total}")
        result = run_keyword_ideas_for_niche(client, niche_key, niche_config)
        all_niches[niche_key] = result
        if index < total:
            log(f"Aguardando {SLEEP_BETWEEN_IDEA_CALLS:.1f}s antes do próximo nicho...")
            time.sleep(SLEEP_BETWEEN_IDEA_CALLS)
    save_json(IDEAS_JSON, {
        "api_version": API_VERSION,
        "geo_target": GEO_TARGET,
        "language": LANGUAGE,
        "network": NETWORK_NAME,
        "top_ideas_per_niche": TOP_IDEAS_PER_NICHE,
        "niches": all_niches,
    })
    log(f"Keyword Ideas bruto salvo: {IDEAS_JSON}")
    return all_niches


def configure_historical_range(client, request):
    (start_year, start_month), (end_year, end_month) = historical_range_48m()
    options = request.historical_metrics_options
    options.include_average_cpc = True
    options.year_month_range.start.year = start_year
    options.year_month_range.start.month = getattr(client.enums.MonthOfYearEnum, MONTH_ENUM_NAMES[start_month])
    options.year_month_range.end.year = end_year
    options.year_month_range.end.month = getattr(client.enums.MonthOfYearEnum, MONTH_ENUM_NAMES[end_month])
    return (start_year, start_month), (end_year, end_month)


def build_keyword_maps(all_niches):
    keyword_to_niches: Dict[str, Set[str]] = defaultdict(set)
    keyword_original: Dict[str, str] = {}
    for niche_key, niche_data in all_niches.items():
        for keyword in niche_data["selected_keywords"]:
            norm = normalize_text(keyword)
            keyword_to_niches[norm].add(niche_key)
            keyword_original.setdefault(norm, keyword)
    all_keywords = [keyword_original[norm] for norm in keyword_original]
    return all_keywords, keyword_to_niches, keyword_original


def run_historical_metrics(client: GoogleAdsClient, all_niches):
    log("=" * 78)
    log("FASE 2 — HISTORICAL METRICS")
    all_keywords, keyword_to_niches, keyword_original = build_keyword_maps(all_niches)
    log(f"Termos únicos globais: {len(all_keywords)}")
    service = client.get_service("KeywordPlanIdeaService", version=API_VERSION)
    batch_list = list(chunks(all_keywords, HISTORICAL_BATCH_SIZE))
    all_raw_responses = []
    historical_rows = []
    requested_range = None
    for batch_number, keyword_batch in enumerate(batch_list, start=1):
        request = client.get_type("GenerateKeywordHistoricalMetricsRequest", version=API_VERSION)
        request.customer_id = CUSTOMER_ID
        request.language = LANGUAGE
        request.geo_target_constants.append(GEO_TARGET)
        request.keyword_plan_network = getattr(client.enums.KeywordPlanNetworkEnum, NETWORK_NAME)
        request.keywords.extend(keyword_batch)
        requested_range = configure_historical_range(client, request)
        log(f"Histórico lote {batch_number}/{len(batch_list)} ({len(keyword_batch)} termos)...")
        response = service.generate_keyword_historical_metrics(request=request)
        all_raw_responses.append(proto_to_dict(response))
        for result in response.results:
            result_dict = proto_to_dict(result)
            canonical_text = str(getattr(result, "text", "") or "")
            close_variants = list(getattr(result, "close_variants", []) or [])
            lookup_terms = unique_preserving_order([canonical_text] + close_variants)
            matched_niches = set()
            for term in lookup_terms:
                matched_niches.update(keyword_to_niches.get(normalize_text(term), set()))
            historical_rows.append({
                "canonical_text": canonical_text,
                "close_variants": close_variants,
                "matched_niches": sorted(matched_niches),
                "raw": result_dict,
            })
    save_json(HISTORICAL_JSON, {
        "api_version": API_VERSION,
        "geo_target": GEO_TARGET,
        "language": LANGUAGE,
        "network": NETWORK_NAME,
        "requested_range": requested_range,
        "keywords_requested": all_keywords,
        "responses": all_raw_responses,
        "mapped_results": historical_rows,
    })
    log(f"Historical bruto salvo: {HISTORICAL_JSON}")
    log(f"Resultados históricos: {len(historical_rows)}")
    return historical_rows, keyword_to_niches


def month_value(month_field) -> int:
    if month_field is None:
        return 0
    if isinstance(month_field, str):
        name = month_field.split(".")[-1].upper()
        return MONTH_NAME_TO_NUMBER.get(name, 0)
    name = getattr(month_field, "name", None)
    if name:
        return MONTH_NAME_TO_NUMBER.get(str(name).upper(), 0)
    value = safe_int(month_field, 0)
    if 2 <= value <= 13:
        return value - 1
    if 1 <= value <= 12:
        return value
    return 0


def parse_monthly_series(metrics_dict: dict):
    series = []
    for item in metrics_dict.get("monthly_search_volumes", []):
        year = safe_int(item.get("year"))
        month = month_value(item.get("month"))
        searches = safe_int(item.get("monthly_searches"))
        if year and month:
            series.append({"year": year, "month": month, "searches": searches})
    series.sort(key=lambda row: (row["year"], row["month"]))
    return series


def avg_last(series, n: int):
    values = [row["searches"] for row in series[-n:]]
    return sum(values) / len(values) if values else 0.0


def avg_slice_from_end(series, start_from_end: int, length: int):
    if not series:
        return 0.0
    end_index = len(series) - start_from_end
    start_index = max(0, end_index - length)
    if end_index <= 0:
        return 0.0
    values = [row["searches"] for row in series[start_index:end_index]]
    return sum(values) / len(values) if values else 0.0


def parse_historical_row(row: dict):
    raw = row["raw"]
    metrics = raw.get("keyword_metrics", {}) or {}
    series = parse_monthly_series(metrics)
    recent_3 = avg_last(series, 3)
    recent_12 = avg_last(series, 12)
    previous_9 = avg_slice_from_end(series, start_from_end=3, length=9)
    previous_12 = avg_slice_from_end(series, start_from_end=12, length=12)
    first_12_values = [item["searches"] for item in series[:12]]
    first_12 = sum(first_12_values) / len(first_12_values) if first_12_values else 0.0
    growth_12m = pct_change(recent_12, previous_12)
    momentum_3v9 = pct_change(recent_3, previous_9)
    growth_48m = pct_change(recent_12, first_12)
    competition = str(metrics.get("competition", "") or "")
    competition_index = safe_float(metrics.get("competition_index"))
    low_bid = micros_to_brl(metrics.get("low_top_of_page_bid_micros"))
    high_bid = micros_to_brl(metrics.get("high_top_of_page_bid_micros"))
    avg_cpc = micros_to_brl(metrics.get("average_cpc_micros"))
    all_texts = [row["canonical_text"], *row["close_variants"]]
    local_intent = any(is_local_intent(text) for text in all_texts)
    return {
        "keyword": row["canonical_text"],
        "close_variants": " | ".join(row["close_variants"]),
        "matched_niches": row["matched_niches"],
        "avg_monthly_searches_api": safe_int(metrics.get("avg_monthly_searches")),
        "recent_3m_avg": recent_3,
        "recent_12m_avg": recent_12,
        "previous_12m_avg": previous_12,
        "growth_12m_pct": growth_12m,
        "momentum_3v9_pct": momentum_3v9,
        "growth_48m_pct": growth_48m,
        "competition": competition,
        "competition_index": competition_index,
        "avg_cpc_brl": avg_cpc,
        "low_top_bid_brl": low_bid,
        "high_top_bid_brl": high_bid,
        "local_intent": local_intent,
        "months_available": len(series),
        "monthly_series": series,
    }


def weighted_average(rows: List[dict], value_key: str, weight_key: str):
    total_weight = 0.0
    weighted_sum = 0.0
    for row in rows:
        value = row.get(value_key)
        weight = max(safe_float(row.get(weight_key)), 0.0)
        if value is None or weight <= 0:
            continue
        weighted_sum += safe_float(value) * weight
        total_weight += weight
    return weighted_sum / total_weight if total_weight > 0 else 0.0


def top_k_volume(rows: List[dict], k: int = 10):
    ordered = sorted(rows, key=lambda row: row["recent_12m_avg"], reverse=True)
    return sum(row["recent_12m_avg"] for row in ordered[:k])


def percentile_rank(values: List[float], value: float) -> float:
    clean = sorted(safe_float(v) for v in values)
    if not clean:
        return 0.0
    if len(clean) == 1:
        return 50.0
    below = sum(1 for v in clean if v < value)
    equal = sum(1 for v in clean if v == value)
    rank = (below + max(equal - 1, 0) / 2) / (len(clean) - 1)
    return max(0.0, min(100.0, rank * 100.0))


def build_niche_summaries(parsed_rows: List[dict], all_niches):
    by_niche = defaultdict(list)
    for row in parsed_rows:
        for niche_key in row["matched_niches"]:
            by_niche[niche_key].append(row)
    summaries = []
    for niche_key, niche_data in all_niches.items():
        rows = by_niche.get(niche_key, [])
        local_rows = [row for row in rows if row["local_intent"]]
        top10 = top_k_volume(rows, 10)
        top20 = top_k_volume(rows, 20)
        local_volume = sum(row["recent_12m_avg"] for row in local_rows)
        weighted_comp = weighted_average(rows, "competition_index", "recent_12m_avg")
        weighted_high_bid = weighted_average(rows, "high_top_bid_brl", "recent_12m_avg")
        weighted_avg_cpc = weighted_average(rows, "avg_cpc_brl", "recent_12m_avg")
        weighted_growth = weighted_average([r for r in rows if r["growth_12m_pct"] is not None], "growth_12m_pct", "recent_12m_avg")
        weighted_momentum = weighted_average([r for r in rows if r["momentum_3v9_pct"] is not None], "momentum_3v9_pct", "recent_12m_avg")
        weighted_48m = weighted_average([r for r in rows if r["growth_48m_pct"] is not None], "growth_48m_pct", "recent_12m_avg")
        top_keywords = sorted(rows, key=lambda row: row["recent_12m_avg"], reverse=True)[:10]
        summaries.append({
            "niche_key": niche_key,
            "niche": niche_data["label"],
            "historical_keywords": len(rows),
            "top10_recent12_volume": top10,
            "top20_recent12_volume": top20,
            "explicit_local_volume": local_volume,
            "weighted_competition_index": weighted_comp,
            "weighted_avg_cpc_brl": weighted_avg_cpc,
            "weighted_high_top_bid_brl": weighted_high_bid,
            "weighted_growth_12m_pct": weighted_growth,
            "weighted_momentum_3v9_pct": weighted_momentum,
            "weighted_growth_48m_pct": weighted_48m,
            "top_keywords": top_keywords,
        })
    return summaries


def calculate_exploratory_score(summaries: List[dict]):
    fields = {
        "demand": [row["top10_recent12_volume"] for row in summaries],
        "local": [row["explicit_local_volume"] for row in summaries],
        "cpc": [row["weighted_avg_cpc_brl"] for row in summaries],
        "competition": [row["weighted_competition_index"] for row in summaries],
        "growth": [row["weighted_growth_12m_pct"] for row in summaries],
    }
    for row in summaries:
        p_demand = percentile_rank(fields["demand"], row["top10_recent12_volume"])
        p_local = percentile_rank(fields["local"], row["explicit_local_volume"])
        p_cpc = percentile_rank(fields["cpc"], row["weighted_avg_cpc_brl"])
        p_comp = percentile_rank(fields["competition"], row["weighted_competition_index"])
        p_growth = percentile_rank(fields["growth"], row["weighted_growth_12m_pct"])
        score = 0.35 * p_demand + 0.20 * p_local + 0.20 * p_cpc + 0.15 * p_comp + 0.10 * p_growth
        row["score_exploratory_0_100"] = score
        row["score_components"] = {
            "demand_percentile": p_demand,
            "local_percentile": p_local,
            "cpc_percentile": p_cpc,
            "competition_percentile": p_comp,
            "growth_percentile": p_growth,
        }
    summaries.sort(key=lambda row: row["score_exploratory_0_100"], reverse=True)
    for rank, row in enumerate(summaries, start=1):
        row["rank"] = rank
    return summaries


def export_keywords_csv(parsed_rows: List[dict]):
    fieldnames = [
        "niche", "keyword", "close_variants", "local_intent", "recent_3m_avg",
        "recent_12m_avg", "previous_12m_avg", "growth_12m_pct", "momentum_3v9_pct",
        "growth_48m_pct", "competition", "competition_index", "avg_cpc_brl",
        "low_top_bid_brl", "high_top_bid_brl", "months_available",
    ]
    with KEYWORDS_CSV.open("w", newline="", encoding="utf-8-sig") as file:
        writer = csv.DictWriter(file, fieldnames=fieldnames, delimiter=";")
        writer.writeheader()
        for row in parsed_rows:
            for niche_key in row["matched_niches"]:
                writer.writerow({
                    "niche": NICHES[niche_key]["label"],
                    "keyword": row["keyword"],
                    "close_variants": row["close_variants"],
                    "local_intent": "SIM" if row["local_intent"] else "NAO",
                    "recent_3m_avg": round(row["recent_3m_avg"], 2),
                    "recent_12m_avg": round(row["recent_12m_avg"], 2),
                    "previous_12m_avg": round(row["previous_12m_avg"], 2),
                    "growth_12m_pct": "" if row["growth_12m_pct"] is None else round(row["growth_12m_pct"], 2),
                    "momentum_3v9_pct": "" if row["momentum_3v9_pct"] is None else round(row["momentum_3v9_pct"], 2),
                    "growth_48m_pct": "" if row["growth_48m_pct"] is None else round(row["growth_48m_pct"], 2),
                    "competition": row["competition"],
                    "competition_index": round(row["competition_index"], 2),
                    "avg_cpc_brl": round(row["avg_cpc_brl"], 2),
                    "low_top_bid_brl": round(row["low_top_bid_brl"], 2),
                    "high_top_bid_brl": round(row["high_top_bid_brl"], 2),
                    "months_available": row["months_available"],
                })
    log(f"CSV detalhado: {KEYWORDS_CSV}")


def export_summary_csv(summaries: List[dict]):
    fieldnames = [
        "rank", "niche", "score_exploratory_0_100", "historical_keywords",
        "top10_recent12_volume", "top20_recent12_volume", "explicit_local_volume",
        "weighted_competition_index", "weighted_avg_cpc_brl", "weighted_high_top_bid_brl",
        "weighted_growth_12m_pct", "weighted_momentum_3v9_pct", "weighted_growth_48m_pct",
    ]
    with SUMMARY_CSV.open("w", newline="", encoding="utf-8-sig") as file:
        writer = csv.DictWriter(file, fieldnames=fieldnames, delimiter=";")
        writer.writeheader()
        for row in summaries:
            writer.writerow({
                "rank": row["rank"],
                "niche": row["niche"],
                "score_exploratory_0_100": round(row["score_exploratory_0_100"], 2),
                "historical_keywords": row["historical_keywords"],
                "top10_recent12_volume": round(row["top10_recent12_volume"], 2),
                "top20_recent12_volume": round(row["top20_recent12_volume"], 2),
                "explicit_local_volume": round(row["explicit_local_volume"], 2),
                "weighted_competition_index": round(row["weighted_competition_index"], 2),
                "weighted_avg_cpc_brl": round(row["weighted_avg_cpc_brl"], 2),
                "weighted_high_top_bid_brl": round(row["weighted_high_top_bid_brl"], 2),
                "weighted_growth_12m_pct": round(row["weighted_growth_12m_pct"], 2),
                "weighted_momentum_3v9_pct": round(row["weighted_momentum_3v9_pct"], 2),
                "weighted_growth_48m_pct": round(row["weighted_growth_48m_pct"], 2),
            })
    log(f"CSV resumo: {SUMMARY_CSV}")


def export_chatgpt_txt(summaries: List[dict]):
    lines = []
    lines.append("=" * 88)
    lines.append("RESULTADO — EXPERIMENTO NICHOS / KEYWORD IDEAS + KEYWORD PLANNER")
    lines.append("=" * 88)
    lines.append("")
    lines.append(f"API: {API_VERSION}")
    lines.append(f"Geo: {GEO_TARGET}")
    lines.append(f"Idioma: {LANGUAGE}")
    lines.append(f"Rede: {NETWORK_NAME}")
    (sy, sm), (ey, em) = historical_range_48m()
    lines.append(f"Histórico solicitado: {sy:04d}-{sm:02d} até {ey:04d}-{em:02d}")
    lines.append("")
    lines.append("IMPORTANTE: score abaixo é SOMENTE priorização exploratória de mercado de busca.")
    lines.append("Ele NÃO mede chance de resposta no WhatsApp, fechamento, facilidade operacional ou lucro.")
    lines.append("")
    lines.append("=" * 88)
    lines.append("RANKING EXPLORATÓRIO")
    lines.append("=" * 88)
    for row in summaries:
        lines.append("")
        lines.append(f"#{row['rank']} — {row['niche']} | SCORE {row['score_exploratory_0_100']:.1f}/100")
        lines.append(f"  Volume top10 (média mensal recente): {row['top10_recent12_volume']:.0f}")
        lines.append(f"  Volume explícito local: {row['explicit_local_volume']:.0f}")
        lines.append(f"  CPC médio ponderado: {fmt_money(row['weighted_avg_cpc_brl'])}")
        lines.append(f"  Lance topo alto ponderado: {fmt_money(row['weighted_high_top_bid_brl'])}")
        lines.append(f"  Competição Ads ponderada: {row['weighted_competition_index']:.1f}/100")
        lines.append(f"  Crescimento 12m ponderado: {fmt_pct(row['weighted_growth_12m_pct'])}")
        lines.append(f"  Momentum 3m vs 9m anteriores: {fmt_pct(row['weighted_momentum_3v9_pct'])}")
        lines.append(f"  Mudança início->fim da janela: {fmt_pct(row['weighted_growth_48m_pct'])}")
        lines.append("  Top keywords:")
        for kw in row["top_keywords"][:8]:
            lines.append(
                f"    - {kw['keyword']} | 12m={kw['recent_12m_avg']:.0f}/mês | "
                f"3m={kw['recent_3m_avg']:.0f}/mês | CPC={fmt_money(kw['avg_cpc_brl'])} | "
                f"Comp={kw['competition_index']:.0f} | Local={'SIM' if kw['local_intent'] else 'NAO'}"
            )
    lines.append("")
    lines.append("=" * 88)
    lines.append("O QUE EU QUERO QUE O CHATGPT FAÇA COM ISTO")
    lines.append("=" * 88)
    lines.append("")
    lines.append("Cruze estes resultados com o ranking anterior de FIT da Veriluno (WhatsApp + facilidade operacional GBP + necessidade de Google).")
    lines.append("Quero decidir quais nichos usar primeiro no experimento real de até 50 mensagens/dia.")
    lines.append("Não trate o score exploratório como verdade. Analise volume, intenção local, CPC, competição, crescimento e possíveis ruídos semânticos das keywords.")
    lines.append("Sugira uma primeira bateria pequena de nichos para teste e diga quais dados desta execução sustentam cada hipótese.")
    CHATGPT_TXT.write_text("\n".join(lines), encoding="utf-8")
    log(f"Arquivo para colar no ChatGPT: {CHATGPT_TXT}")


def print_console_summary(summaries: List[dict]):
    print()
    print("=" * 100)
    print("RANKING EXPLORATÓRIO — MERCADO DE BUSCA")
    print("=" * 100)
    header = (
        f"{'#':>2}  "
        f"{'NICHO':<40} "
        f"{'SCORE':>7} "
        f"{'VOL10':>10} "
        f"{'LOCAL':>10} "
        f"{'CPC':>10} "
        f"{'COMP':>7} "
        f"{'G12M':>9}"
    )
    print(header)
    print("-" * 100)
    for row in summaries:
        print(
            f"{row['rank']:>2}  "
            f"{row['niche'][:40]:<40} "
            f"{row['score_exploratory_0_100']:>7.1f} "
            f"{row['top10_recent12_volume']:>10.0f} "
            f"{row['explicit_local_volume']:>10.0f} "
            f"{row['weighted_avg_cpc_brl']:>10.2f} "
            f"{row['weighted_competition_index']:>7.1f} "
            f"{row['weighted_growth_12m_pct']:>8.1f}%"
        )
    print("=" * 100)
    print()
    print("ATENÇÃO: este ranking NÃO prevê resposta no WhatsApp nem venda.")
    print("Ele serve para escolher melhor ONDE COLETAR LEADS E TESTAR.")
    print()
    print(f"Para continuar comigo, cole o conteúdo de:\n{CHATGPT_TXT}")
    print()


def main():
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    log("=" * 78)
    log("EXPERIMENTO — NICHOS PARA PROSPECÇÃO WHATSAPP")
    log("Google Ads Keyword Ideas + Historical Metrics")
    log("SEM GOOGLE TRENDS")
    log("=" * 78)
    log(f"API: {API_VERSION}")
    log(f"Customer ID: {CUSTOMER_ID}")
    log(f"MCC/Login Customer ID: {LOGIN_CUSTOMER_ID}")
    log(f"Geo: {GEO_TARGET}")
    log(f"Idioma: {LANGUAGE}")
    log(f"Nichos: {len(NICHES)}")
    log(f"Saída: {OUTPUT_DIR}")
    (sy, sm), (ey, em) = historical_range_48m()
    log(f"Janela histórica solicitada: {sy:04d}-{sm:02d} até {ey:04d}-{em:02d}")
    creds = load_oauth_credentials()
    client = build_google_ads_client(creds)
    all_niches = run_all_keyword_ideas(client)
    historical_rows, _ = run_historical_metrics(client, all_niches)
    parsed_rows = [parse_historical_row(row) for row in historical_rows if row["matched_niches"]]
    log(f"Resultados históricos mapeados a nichos: {len(parsed_rows)}")
    summaries = build_niche_summaries(parsed_rows, all_niches)
    summaries = calculate_exploratory_score(summaries)
    export_keywords_csv(parsed_rows)
    export_summary_csv(summaries)
    export_chatgpt_txt(summaries)
    save_json(OUTPUT_DIR / "06_analise_completa.json", {"summary": summaries, "keywords": parsed_rows})
    print_console_summary(summaries)
    log("=" * 78)
    log("CONCLUÍDO")
    log(f"Tempo total: {elapsed()}")
    log("Próximo passo: trazer o arquivo 05_RESULTADO_PARA_CHATGPT.txt.")


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        log("Interrompido pelo usuário.")
        sys.exit(130)
    except Exception as exc:
        log("ERRO FATAL")
        print(f"{type(exc).__name__}: {exc}", file=sys.stderr)
        raise
