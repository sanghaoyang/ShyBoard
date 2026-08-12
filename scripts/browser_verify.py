# -*- coding: utf-8 -*-
"""ShyBoard 浏览器实测（headless chromium，端口 17892）。

v1.0.3: 左侧导航（3 项：任务/日历/设置）+ 纪念日集成在日历内 + 当天任务弹窗 + 年月跳转。
用法: /c/tools/badminton/venv/Scripts/python.exe scripts/browser_verify.py
前置: WORKBENCH_DB=... app.py --no-window --port 17892 已在跑
"""
import sys
from playwright.sync_api import sync_playwright

URL = "http://127.0.0.1:17892/"
results = []


def check(name, ok, detail=""):
    results.append((name, ok, detail))
    print(("PASS " if ok else "FAIL ") + name + (f"  [{detail}]" if detail else ""))


def nav(page, view):
    page.click(f'#sidenav .nav-item[data-view="{view}"]')
    page.wait_for_timeout(350)


with sync_playwright() as p:
    browser = p.chromium.launch(headless=True)
    page = browser.new_page(viewport={"width": 1280, "height": 900})
    page.goto(URL, wait_until="networkidle")
    page.wait_for_timeout(600)

    # 1. 左侧导航 3 项，默认任务视图
    check("左侧导航 3 项", page.locator("#sidenav .nav-item").count() == 3)
    check("默认任务视图 active",
          page.locator("#view-tasks.active").count() == 1 and
          page.locator("#view-calendar.active").count() == 0)
    check("任务视图内容可见", page.is_visible("#lanes"))

    # 2. 切日历
    nav(page, "calendar")
    check("日历视图 active", page.locator("#view-calendar.active").count() == 1)
    check("任务视图隐藏", page.locator("#view-tasks.active").count() == 0)
    title = f"{page.input_value('#cal-year')}年{page.input_value('#cal-month')}月"
    check("日历年月下拉有值", "年" in title and "月" in title, title)

    # 3. 农历格子显示：动态对比 API（避免写死日期，2026-08-12 code-review #11）
    import datetime as _dt
    _today = _dt.date.today()
    _ts = _today.isoformat()
    _lun_api = page.evaluate(f"""async () => {{
      const d = await (await fetch('/api/calendar?month={_ts[:7]}')).json();
      const l = d.lunar[String({_today.day})] || {{}};
      return {{mn: l.month_name || '', dn: l.day_name || ''}};
    }}""")
    _lun_cell = (page.text_content(f'.cal-cell[data-date="{_ts}"] .cal-lunar') or "").strip()
    _lun_expected = _lun_api["dn"] if _lun_api["dn"] != "初一" else f'{_lun_api["mn"]}月初一'
    check("今天农历格子与 API 一致", _lun_cell == _lun_expected or (not _lun_api["dn"] and _lun_cell == str(_today.day)),
          f"cell={_lun_cell} expected={_lun_expected}")
    check("今天格子有 today 类", page.locator(f'.cal-cell[data-date="{_ts}"].today').count() == 1)

    # 4. 日历内"＋ 纪念日"添加阳历纪念日（11/6）
    page.click("#cal-add-ann-btn")
    page.wait_for_timeout(250)
    check("纪念日弹窗打开", page.is_visible("#a-name"))
    page.fill("#a-name", "QA浏览器生日")
    page.select_option("#a-month", "11")
    page.select_option("#a-day", "6")
    page.click("#modal-ok")
    page.wait_for_timeout(600)
    anns = page.text_content("#anns") or ""
    check("日历纪念日条出现阳历纪念日", "QA浏览器生日" in anns, anns[:80])

    # 5. 翻到 11 月，格子有纪念日标记（年份动态，2026-08-12 code-review #11）
    _y11 = _dt.date.today().year
    for _ in range(3):
        page.click("#cal-next")
        page.wait_for_timeout(250)
    t3 = f"{page.input_value('#cal-year')}年{page.input_value('#cal-month')}月"
    cell11 = page.text_content(f'.cal-cell[data-date="{_y11}-11-06"]') or ""
    check("翻到11月", t3 == f"{_y11}年11月", t3)
    check("11/6 格子显示纪念日", "QA浏览器生日" in cell11, cell11[:60])

    # 5.5 节日/节气标识（动态：年份用当前年，清明从 API 动态定位，避免写死日期）
    import datetime as _dt
    _cur_year = _dt.date.today().year
    page.select_option("#cal-year", str(_cur_year))
    page.select_option("#cal-month", "10")
    page.wait_for_timeout(500)
    hol1 = page.text_content(f'.cal-cell[data-date="{_cur_year}-10-01"] .cal-holidays') or ""
    check("10/1 国庆节标识", "国庆节" in hol1, hol1[:60])
    # 清明：从当年 4 月 API 数据动态找节气日，再断言格子显示
    qm_day = page.evaluate(f"""async () => {{
      const d = await (await fetch('/api/calendar?month={_cur_year}-04')).json();
      for (const k of Object.keys(d.holidays || {{}})) {{
        if (d.holidays[k].includes('清明')) return k;
      }}
      return '';
    }}""")
    check("4月有清明节气数据", qm_day != "", qm_day)
    if qm_day:
        page.select_option("#cal-month", "4")
        page.wait_for_timeout(500)
        hol_qm = page.text_content(f'.cal-cell[data-date="{_cur_year}-04-{int(qm_day):02d}"] .cal-holidays') or ""
        check("清明节气格子标识", "清明" in hol_qm, hol_qm[:60])
    page.click("#cal-today-btn")
    page.wait_for_timeout(500)

    # 6. 年月跳转：直接跳到 2000 年 2 月
    page.select_option("#cal-year", "2000")
    page.select_option("#cal-month", "2")
    page.wait_for_timeout(500)
    t2000 = f"{page.input_value('#cal-year')}年{page.input_value('#cal-month')}月"
    check("年月跳转到 2000年2月", t2000 == "2000年2月", t2000)
    check("2000年2月格子存在", page.locator('.cal-cell[data-date="2000-02-01"]').count() == 1)
    lun2000 = (page.text_content('.cal-cell[data-date="2000-02-08"] .cal-lunar') or "").strip()
    check("2000-02-08 农历（正月初四）", lun2000 == "初四", lun2000)
    # 回到今天
    page.click("#cal-today-btn")
    page.wait_for_timeout(500)

    # 7. 当天记录弹窗：日记保存（确定按钮）+ 读回 + 换行 + 设为纪念日（右上角）
    page.click(f'.cal-cell[data-date="{_ts}"]')
    page.wait_for_timeout(400)
    check("当天弹窗打开", page.is_visible("#day-log-input"))
    dbody = page.text_content("#modal-body") or ""
    check("弹窗含农历信息", _lun_expected in dbody, dbody[:80])
    check("设为纪念日在标题行（右上角）", page.locator("#modal-title #day-add-ann").count() == 1)
    check("无保存记录按钮", page.locator("#day-log-save").count() == 0)
    # 保存日记（文本框，不进任务）：确定按钮 = 保存并关闭
    page.fill("#day-log-input", "QA今天测试记录内容")
    page.click("#modal-ok")
    page.wait_for_timeout(600)
    check("确定保存并关闭弹窗", not page.is_visible("#modal-mask"))
    check("保存后日历格子直接显示日记文本",
          (page.text_content(f'.cal-cell[data-date="{_ts}"] .cal-log') or "") == "QA今天测试记录内容",
          page.text_content(f'.cal-cell[data-date="{_ts}"] .cal-log') or "无")
    # 换行保留：多行日记在格子内原样显示（white-space pre-line + 文本含换行）
    page.click(f'.cal-cell[data-date="{_ts}"]')
    page.wait_for_timeout(400)
    page.fill("#day-log-input", "QA第一行\nQA第二行")
    page.click("#modal-ok")
    page.wait_for_timeout(600)
    log_txt = page.text_content(f'.cal-cell[data-date="{_ts}"] .cal-log') or ""
    ws = page.evaluate(f"getComputedStyle(document.querySelector('.cal-cell[data-date=\"{_ts}\"] .cal-log')).whiteSpace")
    check("日记换行保留", "\n" in log_txt and ws == "pre-line", repr(log_txt[:60]) + f" ws={ws}")
    # 读回
    page.click(f'.cal-cell[data-date="{_ts}"]')
    page.wait_for_timeout(400)
    check("日记读回（多行）", page.input_value("#day-log-input") == "QA第一行\nQA第二行",
          repr(page.input_value("#day-log-input"))[:60])
    # 确定按钮保存并关闭（再次验证）
    page.fill("#day-log-input", "QA确定按钮保存")
    page.click("#modal-ok")
    page.wait_for_timeout(500)
    page.click(f'.cal-cell[data-date="{_ts}"]')
    page.wait_for_timeout(400)
    check("确定按钮保存日记生效", page.input_value("#day-log-input") == "QA确定按钮保存")
    page.evaluate("closeModal()")
    page.wait_for_timeout(350)
    # 设为纪念日（农历七月初一，右上角按钮）
    page.click(f'.cal-cell[data-date="{_ts}"]')
    page.wait_for_timeout(400)
    page.click("#day-add-ann")
    page.wait_for_timeout(350)
    check("设为纪念日弹窗打开", page.is_visible("#a-name"))
    page.click('.ann-type-btn[data-type="lunar"]')
    page.wait_for_timeout(450)
    hint = page.text_content("#a-type-hint") or ""
    check("农历换算提示（动态）", f"该日农历为 {_lun_api['mn']}月{_lun_api['dn']}" in hint, hint)
    page.fill("#a-name", "QA农历初一")
    page.click("#modal-ok")
    page.wait_for_timeout(700)
    dbody4 = page.text_content("#modal-body") or ""
    check("保存后回到当天弹窗且含农历纪念日",
          "QA农历初一" in dbody4 and "农历" in dbody4, dbody4[:100])
    page.evaluate("closeModal()")
    page.wait_for_timeout(350)
    cell13 = page.text_content(f'.cal-cell[data-date="{_ts}"]') or ""
    check("今天格子显示农历纪念日", "QA农历初一" in cell13, cell13[:80])

    # 7.5 日历待办 DDL 标注：todo 带 DDL 显示，doing 不显示（日期=今天，避免跨月）
    page.evaluate(f"""(async () => {{
      await fetch('/api/tasks', {{method:'POST', headers:{{'Content-Type':'application/json'}},
        body: JSON.stringify({{title:'QA日历DDL任务', due_date:'{_ts}'}})}});
      await fetch('/api/tasks', {{method:'POST', headers:{{'Content-Type':'application/json'}},
        body: JSON.stringify({{title:'QA日历进行中', status:'doing', due_date:'{_ts}'}})}});
    }})()""")
    page.wait_for_timeout(400)
    page.evaluate("loadCalendar()")
    page.wait_for_timeout(600)
    ddl15 = page.locator(f'.cal-cell[data-date="{_ts}"] .cal-ddl')
    check("日历格子显示待办 DDL 标注", ddl15.count() == 1 and
          "QA日历DDL任务" in (ddl15.get_attribute("title") or ""),
          ddl15.get_attribute("title") if ddl15.count() else "无标注")
    check("进行中任务不标注", "QA日历进行中" not in (ddl15.get_attribute("title") or ""))

    # 8. 日历纪念日条农历显示格式（中文写法）+ 编辑纪念日 + 删除确认
    anns2 = page.text_content("#anns") or ""
    check("农历显示中文写法（动态）", f"农历{_lun_api['mn']}月{_lun_api['dn']}" in anns2, anns2[:200])
    page.hover('#anns .ann-item:has-text("QA农历初一")')
    page.wait_for_timeout(200)
    page.click('#anns .ann-item:has-text("QA农历初一") .ann-edit')
    page.wait_for_timeout(350)
    check("编辑纪念日弹窗预填", page.is_visible("#a-name") and
          page.input_value("#a-name") == "QA农历初一")
    page.fill("#a-name", "QA农历初一改名")
    page.click("#modal-ok")
    page.wait_for_timeout(700)
    anns3 = page.text_content("#anns") or ""
    check("纪念日编辑生效", "QA农历初一改名" in anns3, anns3[:120])
    # 删除确认：点删除 → 确认弹窗出现 → 取消（不删）
    page.hover('#anns .ann-item:has-text("QA农历初一改名")')
    page.wait_for_timeout(200)
    page.click('#anns .ann-item:has-text("QA农历初一改名") .ann-del')
    page.wait_for_timeout(300)
    check("删除弹确认框", page.is_visible("#confirm-box"))
    page.click("#confirm-cancel")
    page.wait_for_timeout(300)
    check("取消删除后纪念日还在", "QA农历初一改名" in (page.text_content("#anns") or ""))

    # 8.1 设置"删除纪念日确认"开关：关闭后删除直接执行（2026-08-12 做成设置项）
    page.evaluate("""async () => {
      await fetch('/api/settings', {method:'PUT', headers:{'Content-Type':'application/json'}, body: JSON.stringify({confirm_delete_ann: false})});
    }""")
    page.evaluate("loadSettings()")
    page.wait_for_timeout(500)
    page.hover('#anns .ann-item:has-text("QA农历初一改名")')
    page.wait_for_timeout(200)
    page.click('#anns .ann-item:has-text("QA农历初一改名") .ann-del')
    page.wait_for_timeout(500)
    check("关闭确认后删除直接执行", not page.is_visible("#confirm-box"))
    check("纪念日已删除", "QA农历初一改名" not in (page.text_content("#anns") or ""))
    page.evaluate("""async () => {
      await fetch('/api/settings', {method:'PUT', headers:{'Content-Type':'application/json'}, body: JSON.stringify({confirm_delete_ann: true})});
    }""")
    page.evaluate("loadSettings()")
    page.wait_for_timeout(400)

    # 9. 设置视图 + 五主题切换
    nav(page, "settings")
    check("设置视图 active", page.locator("#view-settings.active").count() == 1)
    check("主题选择器可见", page.is_visible("#theme-picker"))
    check("主题选择器 10 套", page.locator("#theme-picker .theme-opt").count() == 10)
    seen_primary = {}
    for t in ["pink", "dark", "light", "orange", "green", "teal", "terracotta", "navy", "graphite", "plum"]:
        page.click(f'#theme-picker .theme-opt[data-theme="{t}"]')
        page.wait_for_timeout(400)
        primary = page.evaluate("getComputedStyle(document.body).getPropertyValue('--primary').trim()")
        bg = page.evaluate("getComputedStyle(document.body).getPropertyValue('--bg').trim()")
        seen_primary[t] = (primary, bg)
    check("十主题 primary 各不相同",
          len({v[0] for v in seen_primary.values()}) == 10,
          str(seen_primary))
    check("十主题 bg 各不相同",
          len({v[1] for v in seen_primary.values()}) == 10,
          str(seen_primary))
    page.click('#theme-picker .theme-opt[data-theme="pink"]')
    page.wait_for_timeout(300)

    # 10. 任务页侧栏快捷方式：添加 + 编辑
    nav(page, "tasks")
    check("任务页侧栏快捷方式面板", page.is_visible("#link-panel"))
    page.click(".add-link-btn")
    page.wait_for_timeout(250)
    page.fill("#l-name", "QA测试站")
    page.fill("#l-url", "https://example.com")
    page.click("#modal-ok")
    page.wait_for_timeout(600)
    check("侧栏快捷方式出现新链接",
          "QA测试站" in (page.text_content("#links") or ""))
    page.hover(".link-item")
    page.wait_for_timeout(200)
    page.click(".link-item .link-edit")
    page.wait_for_timeout(300)
    check("编辑快捷方式弹窗预填",
          page.input_value("#l-name") == "QA测试站")
    page.fill("#l-name", "QA测试站改名")
    page.click("#modal-ok")
    page.wait_for_timeout(600)
    check("快捷方式编辑生效",
          "QA测试站改名" in (page.text_content("#links") or ""))

    # 11. 任务页侧栏便签：添加 + 编辑
    check("任务页侧栏便签面板", page.is_visible("#note-panel"))
    page.click(".add-note-btn")
    page.wait_for_timeout(250)
    page.fill("#n-content", "QA测试便签内容")
    page.click("#modal-ok")
    page.wait_for_timeout(600)
    check("侧栏便签出现新便签",
          "QA测试便签内容" in (page.text_content("#notes") or ""))
    page.hover(".note-item")
    page.wait_for_timeout(200)
    page.click(".note-item .note-edit")
    page.wait_for_timeout(300)
    page.fill("#n-content", "QA测试便签已编辑")
    page.click("#modal-ok")
    page.wait_for_timeout(600)
    check("便签编辑生效",
          "QA测试便签已编辑" in (page.text_content("#notes") or ""))

    # 12. 清理测试数据（纪念日/任务/快捷方式/便签/日记，全部 QA 开头或测试日期）
    page.evaluate("""(async () => {
      await fetch('/api/log', {method:'PUT', headers:{'Content-Type':'application/json'}, body: JSON.stringify({date:'__TODAY__', content:''})});
      const anns = await (await fetch('/api/anniversaries')).json();
      for (const a of anns) {
        if (a.name.startsWith('QA')) await fetch('/api/anniversaries/' + a.id, {method: 'DELETE'});
      }
      const tasks = await (await fetch('/api/tasks')).json();
      for (const t of tasks) {
        if (String(t.title).startsWith('QA')) await fetch('/api/tasks/' + t.id, {method: 'DELETE'});
      }
      const links = await (await fetch('/api/links')).json();
      for (const l of links) {
        if (String(l.name).startsWith('QA')) await fetch('/api/links/' + l.id, {method: 'DELETE'});
      }
      const notes = await (await fetch('/api/notes')).json();
      for (const n of notes) {
        if (String(n.content).startsWith('QA')) await fetch('/api/notes/' + n.id, {method: 'DELETE'});
      }
      return 'cleaned';
    })()""".replace("__TODAY__", _ts))
    page.wait_for_timeout(400)
    nav(page, "calendar")
    page.evaluate("loadAnns()")
    page.wait_for_timeout(300)
    check("测试数据已清理",
          "QA" not in (page.text_content("#anns") or ""))
    nav(page, "tasks")
    page.evaluate("loadLinks(); loadNotes()")
    page.wait_for_timeout(300)
    check("快捷方式/便签已清理",
          "QA" not in (page.text_content("#links") or "") and
          "QA" not in (page.text_content("#notes") or ""))

    browser.close()

fails = [r for r in results if not r[1]]
print(f"\nRESULT: {len(results) - len(fails)} passed, {len(fails)} failed")
sys.exit(1 if fails else 0)
