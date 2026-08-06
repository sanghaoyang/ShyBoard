# -*- coding: utf-8 -*-
"""下载三套开源 emoji 精选，生成对比页面供挑选。

来源:
  - OpenMoji   (CC BY-SA 4.0) https://openmoji.org/data/color/svg/{code}.svg
  - Twemoji    (CC BY 4.0)    https://cdn.jsdelivr.net/gh/twitter/twemoji@14.0.2/assets/svg/{code}.svg
  - Fluent     (MIT)          https://raw.githubusercontent.com/microsoft/fluentui-emoji/main/assets/{Name}/Flat/{Name}_flat.svg
"""
import os
import json
import re
import sys
import urllib.request

OUT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "emoji_preview")

PROXY = os.environ.get("WB_PROXY", "")
UA = {"User-Agent": "Mozilla/5.0"}

# 精选 emoji：码点 / 名称 / 含义（覆盖常见快捷方式场景）
# code 是 Unicode 码点（小写 hex），name 用于 Fluent 路径
EMOJIS = [
    ("1f600", "Grinning face", "笑脸"),
    ("1f419", "Octopus", "章鱼 (GitHub)"),
    ("1f4fa", "Television", "电视 (视频站)"),
    ("1f4da", "Books", "书 (学习)"),
    ("1f426", "Bird", "鸟 (Twitter/X)"),
    ("1f4f0", "Newspaper", "报纸 (新闻)"),
    ("1f3ae", "Video game", "游戏"),
    ("1f6d2", "Shopping cart", "购物车"),
    ("1f3b5", "Musical note", "音乐"),
    ("1f4f7", "Camera", "相机"),
    ("1f4bc", "Briefcase", "公文包 (工作)"),
    ("2709", "Envelope", "信封 (邮箱)"),
    ("1f4ac", "Speech balloon", "聊天气泡"),
    ("1f50d", "Magnifying glass", "放大镜 (搜索)"),
    ("1f6e0", "Hammer and wrench", "工具"),
    ("1f4dd", "Memo", "便签"),
    ("1f4ca", "Bar chart", "图表 (数据)"),
    ("1f3ac", "Clapper board", "电影"),
    ("1f3e0", "House", "主页"),
    ("1f310", "Globe with meridians", "地球 (网站)"),
    ("1f4f1", "Mobile phone", "手机"),
    ("1f3a7", "Headphone", "耳机 (音乐)"),
    ("1f4c8", "Chart increasing", "上升图表 (行情)"),
    ("2b50", "Star", "星标"),
    ("2764", "Red heart", "爱心"),
    ("1f525", "Fire", "火"),
    ("26a1", "High voltage", "闪电"),
    ("1f4a1", "Light bulb", "灯泡 (灵感)"),
    ("1f3af", "Direct hit", "靶心 (目标)"),
    ("1f680", "Rocket", "火箭"),
    ("1f9ed", "Compass", "指南针"),
    ("1f4c5", "Calendar", "日历"),
    ("1f4b0", "Money bag", "钱袋"),
    ("1f512", "Lock", "锁 (安全)"),
    ("1f3a8", "Artist palette", "调色板 (设计)"),
    ("1f3c6", "Trophy", "奖杯"),
    ("1f35c", "Steaming bowl", "面 (美食)"),
    ("2615", "Hot beverage", "咖啡"),
    ("1f389", "Party popper", "庆祝"),
    ("1f431", "Cat face", "猫"),
]


def _fetch(url, binary=True):
    try:
        req = urllib.request.Request(url, headers=UA)
        with urllib.request.urlopen(req, timeout=12) as r:
            return r.read() if binary else r.read().decode("utf-8")
    except Exception:
        proxy_handler = urllib.request.ProxyHandler({"http": PROXY, "https": PROXY})
        opener = urllib.request.build_opener(proxy_handler)
        req = urllib.request.Request(url, headers=UA)
        with opener.open(req, timeout=12) as r:
            return r.read() if binary else r.read().decode("utf-8")


def slug(name):
    return re.sub(r"[^a-z0-9]+", "_", name.lower()).strip("_")


def _openmoji_filename(code):
    """OpenMoji 文件名是带 FE0F 变体选择符的大写形式，如 1F600-FE0F.svg。
    用官方 openmoji.json 建立码点→文件名映射（比 GitHub API 分页完整）。"""
    cache = os.path.join(OUT, "_openmoji_map.json")
    if os.path.exists(cache):
        with open(cache, encoding="utf-8") as f:
            return json.load(f).get(code)
    mapping = {}
    try:
        data = _fetch("https://raw.githubusercontent.com/hfg-gmuend/openmoji/master/data/openmoji.json", binary=False)
        items = json.loads(data)
        for it in items:
            mapping[it["hexcode"].lower()] = it["hexcode"] + ".svg"
        with open(cache, "w", encoding="utf-8") as f:
            json.dump(mapping, f, ensure_ascii=False)
    except Exception as e:
        print("OpenMoji 映射获取失败:", e)
    return mapping.get(code)


def main():
    os.makedirs(OUT, exist_ok=True)
    # 生成 unicode 字符版（系统渲染）作为对照
    html_rows = []
    stats = {}
    for code, name, meaning in EMOJIS:
        cp = int(code, 16)
        ch = chr(cp)
        row_cells = [f"<td><div class='sys'>{ch}</div><div class='m'>{meaning}</div></td>"]
        # OpenMoji
        try:
            fn_name = _openmoji_filename(code)
            if fn_name:
                data = _fetch(f"https://raw.githubusercontent.com/hfg-gmuend/openmoji/master/color/svg/{fn_name}")
                fn = os.path.join(OUT, f"openmoji_{code}.svg")
                with open(fn, "wb") as f:
                    f.write(data)
                row_cells.append(f"<td><img src='openmoji_{code}.svg'><div class='m'>{meaning}</div></td>")
                stats["openmoji"] = stats.get("openmoji", 0) + 1
            else:
                row_cells.append("<td class='err'>✗</td>")
        except Exception:
            row_cells.append("<td class='err'>✗</td>")
        # Twemoji
        try:
            data = _fetch(f"https://cdn.jsdelivr.net/gh/twitter/twemoji@14.0.2/assets/svg/{code}.svg")
            fn = os.path.join(OUT, f"twemoji_{code}.svg")
            with open(fn, "wb") as f:
                f.write(data)
            row_cells.append(f"<td><img src='twemoji_{code}.svg'><div class='m'>{meaning}</div></td>")
            stats["twemoji"] = stats.get("twemoji", 0) + 1
        except Exception as e:
            row_cells.append(f"<td class='err'>✗</td>")
        # Fluent（目录名/文件名都是小写 slug，URL 空格要编码）
        try:
            dir_slug = slug(name)
            fn_name = dir_slug + "_flat.svg"
            from urllib.parse import quote
            data = _fetch(f"https://raw.githubusercontent.com/microsoft/fluentui-emoji/main/assets/{quote(name)}/Flat/{fn_name}")
            fn = os.path.join(OUT, f"fluent_{code}.svg")
            with open(fn, "wb") as f:
                f.write(data)
            row_cells.append(f"<td><img src='fluent_{code}.svg'><div class='m'>{meaning}</div></td>")
            stats["fluent"] = stats.get("fluent", 0) + 1
        except Exception as e:
            print(f"fluent {code} {name}: {e}")
            row_cells.append("<td class='err'>✗</td>")
        html_rows.append("<tr>" + "".join(row_cells) + "</tr>")

    html = f"""<!DOCTYPE html><html lang="zh"><head><meta charset="UTF-8">
<title>emoji 对比</title><style>
body {{ font-family: 'Segoe UI', sans-serif; background:#FBF7F8; padding:30px; }}
h1 {{ color:#4E4450; }} h2 {{ color:#C4A0A8; margin-top:30px; }}
table {{ border-collapse: collapse; }}
td {{ border:1px solid #E8DDE0; padding:10px; text-align:center; width:120px; }}
.sys {{ font-size:34px; }} img {{ width:36px; height:36px; }}
.m {{ font-size:11px; color:#8A7B80; margin-top:6px; }}
.err {{ color:#C97B7B; }} .note {{ color:#8A7B80; font-size:13px; }}
</style></head><body>
<h1>开源 emoji 对比（{len(EMOJIS)} 个精选）</h1>
<p class="note">三列分别为：系统渲染（当前效果）| OpenMoji | Twemoji | Fluent</p>
<table>
<tr><th>系统</th><th>OpenMoji</th><th>Twemoji</th><th>Fluent</th></tr>
{''.join(html_rows)}
</table>
<p class="note">统计: {json.dumps(stats, ensure_ascii=False)}</p>
</body></html>"""
    with open(os.path.join(OUT, "index.html"), "w", encoding="utf-8") as f:
        f.write(html)
    print("完成:", json.dumps(stats, ensure_ascii=False))
    print("输出目录:", OUT)


if __name__ == "__main__":
    main()
