# -*- coding: utf-8 -*-
"""天气服务。

- 城市搜索：离线城市表（static/cities.json，中国天气网 101 代码），
  本地秒回、无网络依赖、只含国内城市，不会搜出奇怪同名地名。
- 天气预报：itboy API（中国天气网数据源，免费无需 key），7 天预报。
- 兜底：itboy 不可用时回退 Open-Meteo（用设置的 lat/lon）。
"""
import json
import os
import re
import sys
import urllib.request

if getattr(sys, "frozen", False):
    # 打包版：静态资源在 _MEIPASS（PyInstaller 解包目录）
    if hasattr(sys, "_MEIPASS"):
        BASE = os.path.join(sys._MEIPASS, "static")
    else:
        BASE = os.path.join(os.path.dirname(sys.executable), "static")
else:
    BASE = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "static")
CITIES_FILE = os.path.join(BASE, "cities.json")

ITBOY_URL = "http://t.weather.itboy.net/api/weather/city/{code}"
OPENMETEO_URL = "https://api.open-meteo.com/v1/forecast"
# 可选代理：设置环境变量 WB_PROXY 时启用（例如 http://127.0.0.1:端口），未设置则直连
PROXY = os.environ.get("WB_PROXY", "")
TIMEOUT = 8

# 中文天气 -> emoji
WEATHER_ICONS = [
    ("雷阵雨", "⛈"), ("雷雨", "⛈"), ("冰雹", "🌨"), ("暴雨", "🌧"),
    ("大雨", "🌧"), ("中雨", "🌧"), ("小雨", "🌦"), ("雨", "🌧"),
    ("大雪", "🌨"), ("中雪", "🌨"), ("小雪", "🌨"), ("雪", "🌨"),
    ("雾", "🌫"), ("霾", "😷"), ("沙尘", "🌪"), ("风", "💨"),
    ("晴", "☀️"), ("多云", "⛅"), ("阴", "☁️"),
]


def _fetch_json(url):
    """直连一次，失败后走 WB_PROXY 代理（若配置）再试一次。"""
    try:
        with urllib.request.urlopen(url, timeout=TIMEOUT) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except Exception:
        if not PROXY:
            raise
        proxy_handler = urllib.request.ProxyHandler({
            "http": PROXY, "https": PROXY,
        })
        opener = urllib.request.build_opener(proxy_handler)
        with opener.open(url, timeout=TIMEOUT) as resp:
            return json.loads(resp.read().decode("utf-8"))


def _weather_icon(text):
    for kw, icon in WEATHER_ICONS:
        if kw in text:
            return icon
    return "🌡"


_cities_cache = None


def _load_cities():
    global _cities_cache
    if _cities_cache is None:
        with open(CITIES_FILE, encoding="utf-8") as f:
            _cities_cache = json.load(f)
    return _cities_cache


def geocode(query):
    """离线城市表搜索：精确优先，其次包含匹配。返回 [{n, p, c}]"""
    q = (query or "").strip()
    if not q:
        return []
    q2 = q[:-1] if q.endswith(("市", "县", "区")) else q

    exact, fuzzy = [], []
    for c in _load_cities():
        if c["n"] == q2 or c["n"] == q:
            exact.append(c)
        elif q2 in c["n"] or q in c["n"] or c["n"] in q:
            fuzzy.append(c)
    # 精确优先，最多 8 个
    return (exact + fuzzy)[:8]


def city_by_code(code):
    """按城市代码查城市，返回 {n, p, c} 或 None"""
    for c in _load_cities():
        if c["c"] == code:
            return c
    return None


def forecast(code, lat=None, lon=None, city_name=None):
    """itboy 预报（按城市代码）。失败回退 Open-Meteo（按经纬度）。"""
    try:
        return _forecast_itboy(code, city_name)
    except Exception:
        if lat and lon:
            return _forecast_openmeteo(lat, lon, city_name)
        raise


def _parse_temp(t):
    m = re.search(r"(-?\d+)", str(t))
    return int(m.group(1)) if m else None


def _forecast_itboy(code, city_name=None):
    data = _fetch_json(ITBOY_URL.format(code=code))
    if data.get("status") != 200 or "data" not in data:
        raise RuntimeError("itboy API error: %s" % data.get("message"))
    d = data["data"]
    fc = d.get("forecast", [])
    today = fc[0] if fc else {}
    daily = []
    for day in fc[:7]:
        daily.append({
            "date": day.get("ymd", ""),
            "week": day.get("week", ""),
            "desc": day.get("type", ""),
            "icon": _weather_icon(day.get("type", "")),
            "tmax": _parse_temp(day.get("high", "")),
            "tmin": _parse_temp(day.get("low", "")),
        })
    return {
        "city": city_name or data["cityInfo"].get("city", ""),
        "code": code,
        "source": "cn",
        "temp": _parse_temp(d.get("wendu")),
        "humidity": d.get("shidu", ""),
        "wind": f'{today.get("fx", "")} {today.get("fl", "")}'.strip(),
        "desc": today.get("type", ""),
        "icon": _weather_icon(today.get("type", "")),
        "aqi": f'{d.get("quality", "")} {d.get("pm25", "")}'.strip(),
        "sunrise": today.get("sunrise", ""),
        "sunset": today.get("sunset", ""),
        "notice": today.get("notice", ""),
        "daily": daily,
    }


WMO_CODES = {
    0: ("晴", "☀️"), 1: ("大部晴朗", "🌤"), 2: ("多云", "⛅"), 3: ("阴", "☁️"),
    45: ("雾", "🌫"), 48: ("雾凇", "🌫"), 51: ("毛毛雨", "🌦"), 55: ("毛毛雨", "🌦"),
    61: ("小雨", "🌧"), 63: ("中雨", "🌧"), 65: ("大雨", "🌧"), 71: ("小雪", "🌨"),
    75: ("大雪", "🌨"), 80: ("阵雨", "🌦"), 95: ("雷阵雨", "⛈"),
}


def _forecast_openmeteo(lat, lon, city_name=None):
    url = (
        f"{OPENMETEO_URL}?latitude={lat}&longitude={lon}"
        "&current=temperature_2m,relative_humidity_2m,weather_code,wind_speed_10m"
        "&daily=weather_code,temperature_2m_max,temperature_2m_min,sunrise,sunset"
        "&timezone=auto&forecast_days=7"
    )
    data = _fetch_json(url)
    cur = data.get("current", {})
    code = cur.get("weather_code", 0)
    desc, icon = WMO_CODES.get(code, ("未知", "🌡"))
    d = data.get("daily", {})
    times = d.get("time", [])
    daily = []
    for i, day in enumerate(times):
        dcode = d.get("weather_code", [0] * len(times))[i]
        ddesc, dicon = WMO_CODES.get(dcode, ("未知", "🌡"))
        daily.append({
            "date": day, "week": "",
            "desc": ddesc, "icon": dicon,
            "tmax": d.get("temperature_2m_max", [None] * len(times))[i],
            "tmin": d.get("temperature_2m_min", [None] * len(times))[i],
        })
    return {
        "city": city_name or "",
        "code": "",
        "source": "openmeteo",
        "temp": cur.get("temperature_2m"),
        "humidity": f'{cur.get("relative_humidity_2m", "")}%',
        "wind": f'{cur.get("wind_speed_10m", "")}km/h',
        "desc": desc, "icon": icon,
        "aqi": "", "sunrise": "", "sunset": "", "notice": "",
        "daily": daily,
    }

