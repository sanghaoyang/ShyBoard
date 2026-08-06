# -*- coding: utf-8 -*-
"""下载中国天气网城市代码表并生成 static/cities.json"""
import json
import os
import urllib.request

URL = "https://raw.githubusercontent.com/Memoyu/ChinaWeatherCityCode-JSON/master/WeatherCode.txt"
BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT = os.path.join(BASE, "static", "cities.json")


def main():
    req = urllib.request.Request(URL, headers={"User-Agent": "hermes-agent"})
    raw_text = urllib.request.urlopen(req, timeout=30).read().decode("utf-8")
    raw = json.loads(raw_text)
    cities = []
    for p in raw["城市代码"]:
        prov = p["省"]
        for c in p["市"]:
            cities.append({"n": c["市名"], "p": prov, "c": c["编码"]})
    print("省份数:", len(raw["城市代码"]), "| 城市数:", len(cities))
    for target in ["上海", "北京", "杭州", "深圳", "成都"]:
        hits = [c for c in cities if c["n"] == target]
        print(target, "->", [(c["p"], c["c"]) for c in hits[:3]])
    with open(OUT, "w", encoding="utf-8") as f:
        json.dump(cities, f, ensure_ascii=False)
    print("written:", OUT, os.path.getsize(OUT), "bytes")


if __name__ == "__main__":
    main()
