from __future__ import annotations

import csv
import html
import json
from pathlib import Path

from .maps_distance import google_maps_api_key
from .paths import ROOT, output_dir, rel


SEASON_COLORS = {
    "spring_3_5": "#e53935",
    "summer_6_8": "#1e88e5",
    "autumn_9_11": "#fdd835",
    "winter_12_2": "#43a047",
}
NAMBA_STATION_LAT = 34.66315


def season_key_from_label(value: object) -> str:
    text = str(value or "")
    if "春" in text:
        return "spring_3_5"
    if "夏" in text:
        return "summer_6_8"
    if "秋" in text:
        return "autumn_9_11"
    if "冬" in text:
        return "winter_12_2"
    return ""


def parse_float(value: object) -> float | None:
    text = str(value or "").replace(",", "").strip()
    if not text:
        return None
    try:
        return float(text)
    except ValueError:
        return None


def csv_rows(path: Path) -> list[dict[str, str]]:
    with path.open("r", encoding="utf-8-sig", newline="") as f:
        return list(csv.DictReader(f))


def season_rows_by_park(season_path: Path) -> dict[tuple[str, str, str], dict[str, str]]:
    rows: dict[tuple[str, str, str], dict[str, str]] = {}
    for row in csv_rows(season_path):
        key = (row.get("park_name", ""), row.get("nearest_station_name", ""), row.get("season", ""))
        rows[key] = row
    return rows


def marker_rows(candidate_path: Path, season_path: Path) -> list[dict[str, object]]:
    season_lookup = season_rows_by_park(season_path)
    markers = []
    for row in csv_rows(candidate_path):
        lat = parse_float(row.get("park_google_lat")) or parse_float(row.get("park_lat"))
        lon = parse_float(row.get("park_google_lng")) or parse_float(row.get("park_lon"))
        if lat is None or lon is None:
            continue
        if lat > NAMBA_STATION_LAT:
            continue
        season_key = row.get("station_peak_season_key") or season_key_from_label(row.get("station_peak_season"))
        season = season_lookup.get((row.get("park_name", ""), row.get("nearest_station_name", ""), season_key), {})
        markers.append(
            {
                "park_name": row.get("park_name", ""),
                "nearest_station_name": row.get("nearest_station_name", ""),
                "season": season_key,
                "season_label": row.get("station_peak_season", "") or season.get("season_label", ""),
                "station_peak_year_month": row.get("station_peak_year_month", ""),
                "season_rank_at_station": season.get("season_rank_at_station", row.get("season_rank_at_station", "")),
                "season_avg_daily_total": season.get("season_avg_daily_total", ""),
                "season_total_count": season.get("season_total_count", ""),
                "months_included": season.get("months_included", ""),
                "color": SEASON_COLORS.get(season_key, "#757575"),
                "lat": lat,
                "lng": lon,
                "area_ha": row.get("area_ha", ""),
                "straight_line_distance_m": row.get("straight_line_distance_m", ""),
                "walking_distance_m": row.get("walking_distance_m", ""),
                "walking_duration_min": row.get("walking_duration_min", ""),
                "event_keywords": row.get("event_keywords", ""),
                "official_event_source_url": row.get("official_event_source_url", ""),
                "nearest_station_candidates_top5": row.get("nearest_station_candidates_top5", ""),
                "priority_score": row.get("priority_score", ""),
            }
        )
    return markers


PUBLIC_API_KEY_PLACEHOLDER = "__GOOGLE_MAPS_API_KEY__"


def station_monthly_lookup(monthly_path: Path) -> dict[str, list[dict[str, str]]]:
    monthly: dict[str, list[dict[str, str]]] = {}
    if not monthly_path.exists():
        return monthly
    for row in csv_rows(monthly_path):
        station_key = row.get("station_key", "")
        if not station_key:
            continue
        monthly.setdefault(station_key, []).append(
            {
                "year_month": row.get("year_month", ""),
                "season_label": row.get("season_label", ""),
                "board_count": row.get("board_count", ""),
                "alight_count": row.get("alight_count", ""),
                "total_count": row.get("total_count", ""),
                "avg_daily_total": row.get("avg_daily_total", ""),
                "month_share_of_period": row.get("month_share_of_period", ""),
            }
        )
    for rows in monthly.values():
        rows.sort(key=lambda item: item.get("year_month", ""))
    return monthly


def station_marker_rows(station_path: Path, monthly_path: Path) -> list[dict[str, object]]:
    monthly = station_monthly_lookup(monthly_path)
    stations = []
    for row in csv_rows(station_path):
        lat = parse_float(row.get("lat"))
        lon = parse_float(row.get("lon"))
        if lat is None or lon is None:
            continue
        stations.append(
            {
                "station_key": row.get("station_key", ""),
                "station_name_norm": row.get("station_name_norm", ""),
                "operators": row.get("operators", ""),
                "routes": row.get("routes", ""),
                "lat": lat,
                "lng": lon,
                "board_count": row.get("board_count", ""),
                "alight_count": row.get("alight_count", ""),
                "total_count": row.get("total_count", ""),
                "monthly": monthly.get(row.get("station_key", ""), []),
            }
        )
    return stations


def build_html(markers: list[dict[str, object]], stations: list[dict[str, object]], public_api_key: str = "") -> str:
    data = json.dumps(markers, ensure_ascii=False)
    station_data = json.dumps(stations, ensure_ascii=False)
    embedded_key = json.dumps(public_api_key, ensure_ascii=False)
    api_row = ""
    public_note = "APIキーを入力すると地図を読み込みます。"
    if public_api_key:
        public_note = "公開用HTMLのため、Google Mapsを自動で読み込みます。"
    else:
        api_row = """
    <div id="apiRow">
      <input id="apiKey" type="password" placeholder="Google Maps JavaScript APIキーを貼り付け">
      <button id="loadMap" type="button">地図を読み込む</button>
    </div>"""
    counts = {}
    for marker in markers:
        label = marker.get("season_label") or "未分類"
        counts[label] = counts.get(label, 0) + 1
    count_text = " / ".join(f"{html.escape(str(label))}: {count}" for label, count in sorted(counts.items()))
    return f"""<!doctype html>
<html lang="ja">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>ODQ2026 公園×最寄駅 季節ピークマップ</title>
  <style>
    html, body, #map {{ height: 100%; margin: 0; font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif; }}
    #panel {{
      position: absolute; z-index: 5; top: 12px; left: 12px; width: min(460px, calc(100vw - 24px));
      background: #fff; border: 1px solid #d0d7de; box-shadow: 0 8px 28px rgba(0,0,0,.16); padding: 12px;
    }}
    #panel h1 {{ font-size: 16px; margin: 0 0 8px; }}
    #panel p {{ margin: 6px 0; font-size: 12px; line-height: 1.55; color: #24292f; }}
    #apiRow {{ display: flex; gap: 8px; margin: 8px 0; }}
    #apiKey {{ flex: 1; min-width: 0; padding: 7px 8px; border: 1px solid #8c959f; font-size: 13px; }}
    #loadMap {{ padding: 7px 10px; border: 1px solid #1f6feb; background: #1f6feb; color: #fff; cursor: pointer; }}
    #legend {{ display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 4px 10px; margin-top: 8px; font-size: 12px; }}
    .chip {{ display: inline-flex; align-items: center; gap: 6px; }}
    .dot {{ width: 12px; height: 12px; border-radius: 50%; border: 1px solid #24292f; display: inline-block; }}
    .station-square {{ width: 10px; height: 10px; background: #7e22ce; border: 1px solid #ffffff; box-shadow: 0 0 0 1px #4c1d95; display: inline-block; }}
    .muted {{ color: #57606a; }}
    .info {{ max-width: 320px; font-size: 13px; line-height: 1.45; }}
    .info h2 {{ font-size: 15px; margin: 0 0 6px; }}
    .info dl {{ display: grid; grid-template-columns: 92px 1fr; gap: 3px 8px; margin: 0; }}
    .info dt {{ color: #57606a; }}
    .info dd {{ margin: 0; }}
    .monthly-wrap {{ margin-top: 10px; max-height: 230px; overflow: auto; border: 1px solid #d0d7de; }}
    .monthly-table {{ width: 100%; border-collapse: collapse; font-size: 12px; white-space: nowrap; }}
    .monthly-table th, .monthly-table td {{ border-bottom: 1px solid #d8dee4; padding: 4px 6px; text-align: right; }}
    .monthly-table th:first-child, .monthly-table td:first-child,
    .monthly-table th:nth-child(2), .monthly-table td:nth-child(2) {{ text-align: left; }}
    .monthly-table th {{ position: sticky; top: 0; background: #f6f8fa; z-index: 1; }}
  </style>
</head>
<body>
  <div id="panel">
    <h1>ODQ2026 公園×最寄駅 季節ピークマップ</h1>
    <p>公園の位置を、最寄駅のピーク月 <code>station_peak_year_month</code> を季節化した色で表示します。難波より北側の公園は除外しています。</p>
    <p class="muted">{html.escape(public_note)}</p>{api_row}
    <div id="legend">
      <span class="chip"><span class="dot" style="background:#e53935"></span>春: 赤</span>
      <span class="chip"><span class="dot" style="background:#1e88e5"></span>夏: 青</span>
      <span class="chip"><span class="dot" style="background:#fdd835"></span>秋: 黄</span>
      <span class="chip"><span class="dot" style="background:#43a047"></span>冬: 緑</span>
      <span class="chip"><span class="station-square"></span>南海・泉北駅</span>
    </div>
    <p class="muted">公園表示件数: {len(markers)}件。駅表示件数: {len(stations)}件。{count_text}</p>
  </div>
  <div id="map"></div>
  <script>
    const PARK_MARKERS = {data};
    const STATION_MARKERS = {station_data};
    const EMBEDDED_GOOGLE_MAPS_API_KEY = {embedded_key};

    function escapeHtml(value) {{
      return String(value ?? "").replace(/[&<>"']/g, ch => ({{
        "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;"
      }}[ch]));
    }}

    function markerScale(areaHa) {{
      const value = Number(areaHa);
      if (!Number.isFinite(value)) return 7;
      return Math.max(6, Math.min(15, 5 + Math.sqrt(value) * 0.75));
    }}

    function formatNumber(value) {{
      const number = Number(value);
      if (!Number.isFinite(number)) return escapeHtml(value);
      return number.toLocaleString("ja-JP");
    }}

    function formatPercent(value) {{
      const number = Number(value);
      if (!Number.isFinite(number)) return escapeHtml(value);
      return `${{(number * 100).toFixed(1)}}%`;
    }}

    function stationPeriodLabel(rows) {{
      if (!Array.isArray(rows) || rows.length === 0) return "";
      const first = rows[0]?.year_month || "";
      const last = rows[rows.length - 1]?.year_month || "";
      return first && last ? `${{first}} - ${{last}}` : "";
    }}

    function stationMonthlyTable(rows) {{
      if (!Array.isArray(rows) || rows.length === 0) {{
        return `<p class="muted">月別乗降データはありません。</p>`;
      }}
      const body = rows.map(row => `
        <tr>
          <td>${{escapeHtml(row.year_month)}}</td>
          <td>${{escapeHtml(row.season_label)}}</td>
          <td>${{formatNumber(row.board_count)}}</td>
          <td>${{formatNumber(row.alight_count)}}</td>
          <td>${{formatNumber(row.total_count)}}</td>
          <td>${{formatNumber(row.avg_daily_total)}}</td>
          <td>${{formatPercent(row.month_share_of_period)}}</td>
        </tr>
      `).join("");
      return `
        <div class="monthly-wrap">
          <table class="monthly-table">
            <thead>
              <tr><th>月</th><th>季節</th><th>乗車</th><th>降車</th><th>合計</th><th>日平均</th><th>期間比</th></tr>
            </thead>
            <tbody>${{body}}</tbody>
          </table>
        </div>
      `;
    }}

    function initMap() {{
      const center = {{ lat: 34.55, lng: 135.43 }};
      const map = new google.maps.Map(document.getElementById("map"), {{
        center,
        zoom: 10,
        mapTypeControl: true,
        streetViewControl: false,
        fullscreenControl: true,
      }});
      const bounds = new google.maps.LatLngBounds();
      const info = new google.maps.InfoWindow();

      PARK_MARKERS.forEach(item => {{
        const position = {{ lat: Number(item.lat), lng: Number(item.lng) }};
        bounds.extend(position);
        const marker = new google.maps.Marker({{
          position,
          map,
          title: `${{item.park_name}} / ${{item.nearest_station_name}}`,
          icon: {{
            path: google.maps.SymbolPath.CIRCLE,
            scale: markerScale(item.area_ha),
            fillColor: item.color,
            fillOpacity: 0.9,
            strokeColor: "#24292f",
            strokeWeight: 1,
          }},
          zIndex: 10,
        }});
        marker.addListener("click", () => {{
          const distance = item.walking_distance_m
            ? `${{escapeHtml(item.walking_distance_m)}}m / ${{escapeHtml(item.walking_duration_min)}}分`
            : `直線 ${{escapeHtml(item.straight_line_distance_m)}}m`;
          const sourceLink = item.official_event_source_url
            ? `<a href="${{escapeHtml(item.official_event_source_url)}}" target="_blank" rel="noopener">公式イベント情報</a>`
            : "";
          info.setContent(`
            <div class="info">
              <h2>${{escapeHtml(item.park_name)}}</h2>
              <dl>
                <dt>最寄駅</dt><dd>${{escapeHtml(item.nearest_station_name)}}</dd>
                <dt>ピーク月</dt><dd>${{escapeHtml(item.station_peak_year_month)}}</dd>
                <dt>地図色の季節</dt><dd>${{escapeHtml(item.season_label || "未分類")}}</dd>
                <dt>季節平均順位</dt><dd>${{escapeHtml(item.season_rank_at_station ? item.season_rank_at_station + "位" : "")}}</dd>
                <dt>季節対象月</dt><dd>${{escapeHtml(item.months_included)}}</dd>
                <dt>季節日平均</dt><dd>${{escapeHtml(item.season_avg_daily_total)}}</dd>
                <dt>距離</dt><dd>${{distance}}</dd>
                <dt>面積</dt><dd>${{escapeHtml(item.area_ha)}}ha</dd>
                <dt>近い駅候補</dt><dd>${{escapeHtml(item.nearest_station_candidates_top5)}}</dd>
                <dt>イベント</dt><dd>${{escapeHtml(item.event_keywords)}}</dd>
                <dt></dt><dd>${{sourceLink}}</dd>
              </dl>
            </div>
          `);
          info.open(map, marker);
        }});
      }});

      STATION_MARKERS.forEach(item => {{
        const position = {{ lat: Number(item.lat), lng: Number(item.lng) }};
        bounds.extend(position);
        const marker = new google.maps.Marker({{
          position,
          map,
          title: item.station_name_norm || item.station_key,
          icon: {{
            path: "M -4 -4 L 4 -4 L 4 4 L -4 4 Z",
            scale: 1.05,
            fillColor: "#7e22ce",
            fillOpacity: 0.95,
            strokeColor: "#ffffff",
            strokeWeight: 1,
          }},
          zIndex: 100,
        }});
        marker.addListener("click", () => {{
          info.setContent(`
            <div class="info">
              <h2>${{escapeHtml(item.station_name_norm || item.station_key)}}</h2>
              <dl>
                <dt>路線</dt><dd>${{escapeHtml(item.routes)}}</dd>
                <dt>事業者</dt><dd>${{escapeHtml(item.operators)}}</dd>
                <dt>対象期間</dt><dd>${{escapeHtml(stationPeriodLabel(item.monthly))}}</dd>
                <dt>期間乗車数</dt><dd>${{formatNumber(item.board_count)}}</dd>
                <dt>期間降車数</dt><dd>${{formatNumber(item.alight_count)}}</dd>
                <dt>期間合計</dt><dd>${{formatNumber(item.total_count)}}</dd>
              </dl>
              <h2 style="margin-top:10px;">月別乗降（月合計）</h2>
              <p class="muted">上段は対象期間の累計、下段は各月の合計です。月別合計はおおむね期間累計の1/12前後になります。</p>
              ${{stationMonthlyTable(item.monthly)}}
            </div>
          `);
          info.open(map, marker);
        }});
      }});
      if (!bounds.isEmpty()) map.fitBounds(bounds);
    }}

    function loadGoogleMaps(forcedKey = "") {{
      const key = forcedKey || document.getElementById("apiKey")?.value.trim();
      if (!key) {{
        alert("Google Maps JavaScript APIキーを入力してください。");
        return;
      }}
      window.initMap = initMap;
      const script = document.createElement("script");
      script.async = true;
      script.defer = true;
      script.src = `https://maps.googleapis.com/maps/api/js?key=${{encodeURIComponent(key)}}&callback=initMap`;
      document.head.appendChild(script);
    }}

    document.getElementById("loadMap")?.addEventListener("click", () => loadGoogleMaps());
    if (EMBEDDED_GOOGLE_MAPS_API_KEY) {{
      window.addEventListener("DOMContentLoaded", () => loadGoogleMaps(EMBEDDED_GOOGLE_MAPS_API_KEY));
    }}
  </script>
</body>
</html>
"""


def run_park_season_map() -> dict[str, object]:
    park_dir = output_dir("park_research")
    candidate_path = park_dir / "park_station_distance_results.csv"
    if not candidate_path.exists():
        candidate_path = park_dir / "park_station_candidates.csv"
    season_path = park_dir / "park_station_season_summary.csv"
    station_path = park_dir / "nankai_station_coords.csv"
    station_monthly_path = park_dir / "station_monthly_seasonality.csv"
    markers = marker_rows(candidate_path, season_path)
    stations = station_marker_rows(station_path, station_monthly_path)
    map_dir = output_dir("maps")
    output_path = map_dir / "odq2026_park_station_season_map.html"
    output_path.write_text(build_html(markers, stations), encoding="utf-8")
    public_preview_path = map_dir / "odq2026_park_station_season_map_github_pages.html"
    api_key = google_maps_api_key()
    if api_key:
        public_preview_path.write_text(build_html(markers, stations, api_key), encoding="utf-8")
    docs_dir = ROOT / "docs"
    docs_dir.mkdir(parents=True, exist_ok=True)
    docs_template_path = docs_dir / "index.template.html"
    docs_template_path.write_text(build_html(markers, stations, PUBLIC_API_KEY_PLACEHOLDER), encoding="utf-8")
    docs_local_path = docs_dir / "index.html"
    if api_key:
        docs_local_path.write_text(build_html(markers, stations, api_key), encoding="utf-8")
    return {
        "status": "ok",
        "map_html": rel(output_path),
        "github_pages_preview_html": rel(public_preview_path) if api_key else "",
        "github_pages_template_html": rel(docs_template_path),
        "github_pages_local_html": rel(docs_local_path) if api_key else "",
        "marker_count": len(markers),
        "station_marker_count": len(stations),
        "candidate_source": rel(candidate_path),
        "note": "HTMLを開いた後、Google Maps JavaScript APIキーを画面上で貼り付けてください。APIキーはHTMLファイルには保存していません。",
    }
