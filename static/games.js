/* ShyBoard · 摸鱼小馆 */
(() => {
  "use strict";

  const root = document.querySelector("#games-root");
  if (!root) return;

  const STORAGE_KEY = "shyboard.games.stats.v2";
  const LEGACY_KEY = "shyboard.games.stats.v1";
  const stats = (() => {
    try {
      const current = JSON.parse(localStorage.getItem(STORAGE_KEY));
      if (current && typeof current === "object") return current;
      const legacy = JSON.parse(localStorage.getItem(LEGACY_KEY)) || {};
      return {
        best: {
          ...(legacy.high2048 ? { "2048.4": legacy.high2048 } : {}),
          ...(legacy.memory ? { "memory.normal": legacy.memory } : {}),
          ...(legacy.mines ? { "mines.beginner": legacy.mines } : {}),
          ...(legacy.lights ? { "lights.5": legacy.lights } : {}),
        },
        wins: { nonogram: legacy.nonogram || 0 },
      };
    } catch (_) { return { best: {}, wins: {} }; }
  })();
  stats.best ||= {};
  stats.wins ||= {};

  let activeGame = "home";
  let timerId = null;
  let animationSerial = 0;

  const MEMORY_LEVELS = {
    easy: { label: "入门 · 4×3", short: "入门", rows: 3, cols: 4, pairs: 6 },
    normal: { label: "标准 · 4×4", short: "标准", rows: 4, cols: 4, pairs: 8 },
    hard: { label: "困难 · 5×4", short: "困难", rows: 4, cols: 5, pairs: 10 },
    expert: { label: "专家 · 6×4", short: "专家", rows: 4, cols: 6, pairs: 12 },
  };
  const MINE_LEVELS = {
    beginner: { label: "初级 · 9×9 / 10雷", short: "初级", rows: 9, cols: 9, count: 10, cell: 36 },
    intermediate: { label: "中级 · 16×16 / 40雷", short: "中级", rows: 16, cols: 16, count: 40, cell: 27 },
    expert: { label: "专家 · 30×16 / 99雷", short: "专家", rows: 16, cols: 30, count: 99, cell: 24 },
  };
  const GAME_2048_LEVELS = {
    3: { label: "挑战 · 3×3", short: "3×3", target: 512 },
    4: { label: "经典 · 4×4", short: "4×4", target: 2048 },
    5: { label: "悠闲 · 5×5", short: "5×5", target: 4096 },
  };
  const LIGHT_LEVELS = {
    3: { label: "入门 · 3×3", short: "3×3", shuffle: 4 },
    5: { label: "标准 · 5×5", short: "5×5", shuffle: 11 },
    7: { label: "困难 · 7×7", short: "7×7", shuffle: 22 },
  };

  function saveStats() {
    try { localStorage.setItem(STORAGE_KEY, JSON.stringify(stats)); } catch (_) { /* storage may be unavailable */ }
  }

  function formatTime(seconds) {
    const value = Math.max(0, Number(seconds) || 0);
    return `${String(Math.floor(value / 60)).padStart(2, "0")}:${String(value % 60).padStart(2, "0")}`;
  }

  function best(key) { return stats.best[key] ?? null; }

  function recordBest(key, value, higherIsBetter = false) {
    const old = best(key);
    const improved = old === null || (higherIsBetter ? value > old : value < old);
    if (improved) { stats.best[key] = value; saveStats(); }
    return improved;
  }

  function shuffle(items) {
    const copy = [...items];
    for (let i = copy.length - 1; i > 0; i--) {
      const j = Math.floor(Math.random() * (i + 1));
      [copy[i], copy[j]] = [copy[j], copy[i]];
    }
    return copy;
  }

  function stopTimer() {
    if (timerId) clearInterval(timerId);
    timerId = null;
  }

  function startTimer(update) {
    stopTimer();
    timerId = setInterval(update, 1000);
  }

  function selectOptions(entries, selected) {
    return entries.map(([value, label]) => `<option value="${value}" ${String(value) === String(selected) ? "selected" : ""}>${label}</option>`).join("");
  }

  function announce(message) {
    const live = root.querySelector("#game-live");
    if (live) live.textContent = message;
  }

  function shell(title, note, controls = "") {
    root.innerHTML = `
      <div class="game-room">
        <div class="game-room-bar">
          <button class="game-back" data-action="games-home" type="button"><span>‹</span> 全部游戏</button>
          <div class="game-room-title"><strong>${title}</strong><small>${note}</small></div>
          <div class="game-room-controls">${controls}</div>
        </div>
        <div class="game-stage" id="game-stage"></div>
        <div id="game-live" class="sr-only" aria-live="polite"></div>
      </div>`;
    return root.querySelector("#game-stage");
  }

  function showResult(title, message, action, actionLabel = "再来一局", isBest = false) {
    const stage = root.querySelector("#game-stage");
    if (!stage || stage.querySelector(".game-result")) return;
    stage.insertAdjacentHTML("beforeend", `
      <div class="game-result">
        <div class="game-result-card"><span class="game-result-spark">✦</span>${isBest ? '<b class="new-best">新的个人纪录</b>' : ""}<h3>${title}</h3><p>${message}</p>
        <div><button class="btn ghost" data-action="games-home">换个游戏</button><button class="btn primary" data-action="${action}">${actionLabel}</button></div></div>
      </div>`);
    announce(`${isBest ? "新的个人纪录。" : ""}${title}，${message}`);
  }

  function recordChips(game) {
    const values = [];
    if (game === "nonogram") [5, 10, 15, 20, 25].forEach((size) => { if (best(`nonogram.${size}`) !== null) values.push(`${size}×${size} ${formatTime(best(`nonogram.${size}`))}`); });
    if (game === "2048") [3, 4, 5].forEach((size) => { if (best(`2048.${size}`) !== null) values.push(`${size}×${size} ${best(`2048.${size}`)}分`); });
    if (game === "memory") Object.entries(MEMORY_LEVELS).forEach(([key, level]) => { if (best(`memory.${key}`) !== null) values.push(`${level.short} ${best(`memory.${key}`)}步`); });
    if (game === "mines") Object.entries(MINE_LEVELS).forEach(([key, level]) => { if (best(`mines.${key}`) !== null) values.push(`${level.short} ${formatTime(best(`mines.${key}`))}`); });
    if (game === "lights") Object.entries(LIGHT_LEVELS).forEach(([size, level]) => { if (best(`lights.${size}`) !== null) values.push(`${level.short} ${best(`lights.${size}`)}步`); });
    return values;
  }

  const gameList = [
    { id: "nonogram", mark: "01", name: "数织", sub: "从 5×5 入门，一路挑战到 25×25", tone: "rose", summary: () => stats.wins.nonogram ? `完成 ${stats.wins.nonogram} 局` : "5 档难度" },
    { id: "2048", mark: "2ⁿ", name: "2048", sub: "三种棋盘，合并数字冲击目标", tone: "apricot", summary: () => best("2048.4") ? `经典最高 ${best("2048.4")} 分` : "3 档难度" },
    { id: "memory", mark: "PAIR", name: "翻牌配对", sub: "从 6 对到 12 对的记忆挑战", tone: "sage", summary: () => best("memory.normal") ? `标准最佳 ${best("memory.normal")} 步` : "4 档难度" },
    { id: "mines", mark: "99", name: "迷你扫雷", sub: "经典初级、中级与专家雷区", tone: "blue", summary: () => best("mines.beginner") !== null ? `初级最快 ${formatTime(best("mines.beginner"))}` : "3 档难度" },
    { id: "lights", mark: "✦", name: "点灯", sub: "3×3、5×5 与 7×7 联动谜题", tone: "violet", summary: () => best("lights.5") ? `标准最佳 ${best("lights.5")} 步` : "3 档难度" },
  ];

  function leaderboardHtml() {
    const names = { nonogram: "数织", "2048": "2048", memory: "翻牌", mines: "扫雷", lights: "点灯" };
    const rows = ["nonogram", "2048", "memory", "mines", "lights"].map((game) => {
      const chips = recordChips(game);
      return `<div class="best-row"><strong>${names[game]}</strong><div>${chips.length ? chips.map((chip) => `<span>${chip}</span>`).join("") : "<i>等待你的第一条纪录</i>"}</div></div>`;
    }).join("");
    return `<section class="personal-best"><div class="personal-best-head"><div><span class="eyebrow">PERSONAL BEST</span><h3>个人排行榜</h3></div><button class="btn ghost sm" data-action="clear-records">清除纪录</button></div><div class="best-list">${rows}</div></section>`;
  }

  function showGamesHome(reset = true) {
    if (activeGame === "home" && !reset && root.children.length) return;
    stopTimer(); animationSerial++;
    activeGame = "home";
    root.innerHTML = `
      <div class="games-home">
        <section class="games-welcome">
          <div><span class="eyebrow">FIVE LITTLE BREAKS</span><h2>忙里偷一小会儿闲</h2><p>五个不用联网、随开随停的小游戏。每档难度都会留下你的个人最佳纪录。</p></div>
          <div class="welcome-orbit" aria-hidden="true"><i></i><i></i><i></i><i></i><span>PLAY</span></div>
        </section>
        <div class="game-card-grid">
          ${gameList.map((game) => `<button class="game-card ${game.tone}" data-game="${game.id}" type="button"><span class="game-card-mark">${game.mark}</span><span class="game-card-copy"><strong>${game.name}</strong><small>${game.sub}</small></span><span class="game-card-foot"><i>${game.summary()}</i><b>开始玩 <span>→</span></b></span></button>`).join("")}
        </div>
        ${leaderboardHtml()}
        <p class="games-footnote">所有纪录只保存在这台设备上 · 随时按 Esc 返回合集</p>
      </div>`;
  }

  /* ---------- 数织 ---------- */
  const NG_SIZES = [5, 10, 15, 20, 25];
  let ng = null;
  let lastNgName = "";

  function lineClues(line) {
    const clues = []; let run = 0;
    for (const value of line) {
      if (value) run++;
      else if (run) { clues.push(run); run = 0; }
    }
    if (run) clues.push(run);
    return clues.length ? clues : [0];
  }

  function patternRows(size, kind) {
    const mid = (size - 1) / 2;
    return Array.from({ length: size }, (_, row) => Array.from({ length: size }, (_, col) => {
      const x = (col - mid) / Math.max(1, mid), y = (mid - row) / Math.max(1, mid);
      if (kind === "爱心") {
        const hx = x * 1.18, hy = y * 1.18 - .18;
        const value = (hx * hx + hy * hy - .72) ** 3 - hx * hx * hy * hy * hy;
        return value <= 0;
      }
      if (kind === "小屋") {
        const roof = row <= Math.floor(size * .46) && Math.abs(col - mid) <= row + (size < 10 ? 0 : 1);
        const wall = row > Math.floor(size * .42) && row < size - 1 && col >= Math.floor(size * .2) && col <= Math.ceil(size * .8);
        const door = row >= Math.floor(size * .68) && Math.abs(col - mid) <= Math.max(0, Math.floor(size * .08));
        const windows = row >= Math.floor(size * .52) && row <= Math.floor(size * .62) && (Math.abs(col - size * .3) < size * .07 || Math.abs(col - size * .7) < size * .07);
        return (roof || wall) && !door && !windows;
      }
      if (kind === "笑脸") {
        const d = Math.sqrt(x * x + y * y);
        const rim = d > .72 && d < .95;
        const eyes = y > .18 && y < .42 && (Math.abs(x - .32) < .1 || Math.abs(x + .32) < .1);
        const smile = y < -.05 && y > -.5 && Math.abs(d - .55) < .1;
        return rim || eyes || smile;
      }
      if (kind === "雪花") {
        const band = 1 / size * 1.4;
        return Math.abs(x) < band || Math.abs(y) < band || Math.abs(x - y) < band || Math.abs(x + y) < band;
      }
      const diamond = Math.abs(x) + Math.abs(y);
      return diamond < .82 && diamond > .46 || Math.abs(x) < .07 || Math.abs(y) < .07;
    }).map(Number).join(""));
  }

  const NG_BEGINNER_PUZZLES = [
    { name: "小爱心", rows: ["01110", "11111", "11111", "01110", "00100"] },
    { name: "小树", rows: ["00100", "01110", "11111", "00100", "01110"] },
    { name: "茶杯", rows: ["00000", "11110", "10111", "11110", "01100"] },
    { name: "小鱼", rows: ["00010", "10111", "11111", "10111", "00010"] },
  ];

  function createNonogramPuzzle(size) {
    if (size === 5) {
      let choices = NG_BEGINNER_PUZZLES.filter((puzzle) => puzzle.name !== lastNgName);
      if (!choices.length) choices = NG_BEGINNER_PUZZLES;
      return choices[Math.floor(Math.random() * choices.length)];
    }
    const generated = window.ShyNonogram.generate(size);
    return { name: "逻辑像素画", rows: generated.rows, rating: generated.rating };
  }

  function newNonogram(size = 5) {
    activeGame = "nonogram"; stopTimer();
    const puzzle = createNonogramPuzzle(size);
    lastNgName = puzzle.name;
    ng = { size, puzzle, solution: puzzle.rows.join("").split("").map(Number), cells: Array(size * size).fill(0), markMode: false, seconds: 0, started: false, done: false };
    renderNonogram();
  }

  function renderNonogram() {
    const sizeOptions = NG_SIZES.map((size) => [size, `${size} × ${size}${size === 5 ? " · 入门" : size === 10 ? " · 轻松" : size === 15 ? " · 标准" : size === 20 ? " · 困难" : " · 专家"}`]);
    const stage = shell("数织", "根据行列数字，填出隐藏图案", `<label class="game-select">难度 <select id="ng-size">${selectOptions(sizeOptions, ng.size)}</select></label><button class="btn ghost sm" data-action="ng-new">换一题</button>`);
    const cols = Array.from({ length: ng.size }, (_, col) => lineClues(Array.from({ length: ng.size }, (_, row) => ng.solution[row * ng.size + col])));
    const rows = Array.from({ length: ng.size }, (_, row) => lineClues(ng.solution.slice(row * ng.size, (row + 1) * ng.size)));
    const cellSize = ng.size <= 5 ? 42 : ng.size <= 10 ? 31 : ng.size <= 15 ? 25 : ng.size <= 20 ? 21 : 18;
    const currentBest = best(`nonogram.${ng.size}`);
    const verified = ng.puzzle.rating ? `唯一解 · 纯逻辑 ${ng.puzzle.rating.rounds} 轮` : "入门图案";
    stage.innerHTML = `<div class="game-info-row"><span>${verified}</span><strong id="ng-time">${formatTime(ng.seconds)}</strong><span>最佳 ${currentBest === null ? "--:--" : formatTime(currentBest)}</span></div><div class="nonogram-wrap"><div class="nonogram-board" style="--ng-size:${ng.size};--ng-cell:${cellSize}px"><span class="ng-corner"></span>${cols.map((clue) => `<span class="ng-col-clue">${clue.map((n) => `<i>${n}</i>`).join("")}</span>`).join("")}${rows.map((clue, row) => `<span class="ng-row-clue">${clue.join(" ")}</span>${Array.from({ length: ng.size }, (_, col) => { const index = row * ng.size + col; return `<button class="ng-cell ${ng.cells[index] === 1 ? "filled" : ng.cells[index] === 2 ? "marked" : ""} ${(col + 1) % 5 === 0 && col < ng.size - 1 ? "block-right" : ""} ${(row + 1) % 5 === 0 && row < ng.size - 1 ? "block-bottom" : ""}" data-ng-cell="${index}" type="button" aria-label="第 ${row + 1} 行第 ${col + 1} 列">${ng.cells[index] === 2 ? "×" : ""}</button>`; }).join("")}`).join("")}</div></div><div class="game-actions centered"><button class="btn ${ng.markMode ? "primary" : "ghost"}" data-action="ng-mode">${ng.markMode ? "标记模式：开" : "标记模式"}</button><button class="btn ghost" data-action="ng-hint">提示一格</button></div><p class="game-help">点击填色；标记模式或鼠标右键可画 ×。题目经过唯一解与纯逻辑验证，粗线每五格分组。</p>`;
  }

  function startNonogramTimer() {
    if (ng.started) return;
    ng.started = true;
    startTimer(() => { if (!ng || activeGame !== "nonogram" || ng.done) return; ng.seconds++; const time = root.querySelector("#ng-time"); if (time) time.textContent = formatTime(ng.seconds); });
  }

  function setNonogramCell(index, mark = ng.markMode) {
    if (ng.done) return;
    startNonogramTimer();
    ng.cells[index] = mark ? (ng.cells[index] === 2 ? 0 : 2) : (ng.cells[index] === 1 ? 0 : 1);
    const cell = root.querySelector(`[data-ng-cell="${index}"]`);
    if (cell) { cell.classList.toggle("filled", ng.cells[index] === 1); cell.classList.toggle("marked", ng.cells[index] === 2); cell.textContent = ng.cells[index] === 2 ? "×" : ""; }
    if (ng.cells.every((value, i) => (value === 1) === (ng.solution[i] === 1))) {
      ng.done = true; stopTimer(); stats.wins.nonogram = (stats.wins.nonogram || 0) + 1;
      const isBest = recordBest(`nonogram.${ng.size}`, ng.seconds); saveStats();
      showResult(`原来是${ng.puzzle.name}`, `${ng.size}×${ng.size} · 用时 ${formatTime(ng.seconds)}`, "ng-new", "再来一题", isBest);
    }
  }

  function hintNonogram() {
    if (ng.done) return;
    startNonogramTimer();
    const choices = ng.solution.map((value, i) => ({ value, i })).filter(({ value, i }) => (value === 1) !== (ng.cells[i] === 1));
    if (!choices.length) return;
    const pick = choices[Math.floor(Math.random() * choices.length)]; ng.cells[pick.i] = pick.value ? 1 : 2; renderNonogram();
  }

  /* ---------- 2048 ---------- */
  let g2048 = null;

  function new2048(size = 4) {
    activeGame = "2048"; stopTimer(); animationSerial++;
    g2048 = { size, target: GAME_2048_LEVELS[size].target, board: Array(size * size).fill(0), score: 0, won: false, over: false, animating: false, newBest: false };
    add2048Tile(); add2048Tile(); render2048();
  }

  function add2048Tile() {
    const free = g2048.board.map((v, i) => v ? -1 : i).filter((i) => i >= 0);
    if (!free.length) return null;
    const index = free[Math.floor(Math.random() * free.length)]; g2048.board[index] = Math.random() < .9 ? 2 : 4; return index;
  }

  function tileClass2048(value) { return value >= 2048 ? "super" : `v${value}`; }

  function position2048Tiles() {
    const board = root.querySelector(".board-2048"), layer = root.querySelector(".tile-layer-2048");
    if (!board || !layer) return;
    const layerRect = layer.getBoundingClientRect();
    layer.querySelectorAll("[data-tile-index]").forEach((tile) => {
      const target = board.querySelector(`[data-grid-index="${tile.dataset.tileIndex}"]`);
      if (!target) return;
      const targetRect = target.getBoundingClientRect();
      tile.style.left = `${targetRect.left - layerRect.left}px`; tile.style.top = `${targetRect.top - layerRect.top}px`; tile.style.width = `${targetRect.width}px`; tile.style.height = `${targetRect.height}px`;
    });
    requestAnimationFrame(() => board.classList.add("ready"));
  }

  function render2048(effects = {}) {
    const levelOptions = Object.entries(GAME_2048_LEVELS).map(([size, level]) => [size, `${level.label} · 目标 ${level.target}`]);
    const stage = shell("2048", "合并相同数字，挑战不同尺寸棋盘", `<label class="game-select">难度 <select id="size-2048">${selectOptions(levelOptions, g2048.size)}</select></label><button class="btn ghost sm" data-action="2048-new">重新开始</button>`);
    const high = Math.max(best(`2048.${g2048.size}`) || 0, g2048.score);
    stage.innerHTML = `<div class="score-row"><div><span>本局得分</span><strong>${g2048.score}</strong></div><div><span>${g2048.size}×${g2048.size} 个人最佳</span><strong>${high}</strong></div><div><span>本局目标</span><strong>${g2048.target}</strong></div></div><div class="board-2048 size-${g2048.size}" style="--grid-size:${g2048.size}" tabindex="0" aria-label="${g2048.size} 乘 ${g2048.size} 的 2048 棋盘"><div class="grid-2048">${g2048.board.map((_, index) => `<i data-grid-index="${index}"></i>`).join("")}</div><div class="tile-layer-2048">${g2048.board.map((value, index) => value ? `<div class="tile-2048 ${tileClass2048(value)} ${effects.spawnIndex === index ? "spawn" : ""} ${(effects.mergedIndices || []).includes(index) ? "merged" : ""}" data-value="${value}" data-tile-index="${index}">${value}</div>` : "").join("")}</div></div><div class="arrow-pad" aria-label="移动方向"><button data-move="up" aria-label="向上">↑</button><button data-move="left" aria-label="向左">←</button><button data-move="down" aria-label="向下">↓</button><button data-move="right" aria-label="向右">→</button></div><p class="game-help">使用方向键、滑动棋盘或下方按钮。数字会沿移动方向平滑滑行并合并。</p>`;
    requestAnimationFrame(position2048Tiles);
    root.querySelector(".board-2048")?.focus({ preventScroll: true });
  }

  function lineIndices2048(direction, line) {
    const n = g2048.size, ascending = Array.from({ length: n }, (_, i) => i), descending = [...ascending].reverse();
    if (direction === "left") return ascending.map((c) => line * n + c);
    if (direction === "right") return descending.map((c) => line * n + c);
    if (direction === "up") return ascending.map((r) => r * n + line);
    return descending.map((r) => r * n + line);
  }

  function plan2048(direction) {
    const n = g2048.size, next = Array(n * n).fill(0), mappings = [], mergedIndices = []; let gained = 0;
    for (let line = 0; line < n; line++) {
      const indices = lineIndices2048(direction, line);
      const sources = indices.filter((index) => g2048.board[index]);
      const results = [];
      for (const source of sources) {
        const value = g2048.board[source], previous = results[results.length - 1];
        if (previous && previous.value === value && !previous.merged) {
          previous.value *= 2; previous.merged = true; gained += previous.value;
          mappings.push({ from: source, to: previous.destination }); mergedIndices.push(previous.destination);
        } else {
          const destination = indices[results.length];
          results.push({ value, merged: false, destination }); mappings.push({ from: source, to: destination });
        }
      }
      results.forEach((item) => { next[item.destination] = item.value; });
    }
    return { board: next, mappings, mergedIndices, gained, changed: next.join(",") !== g2048.board.join(",") };
  }

  function canMove2048() {
    const n = g2048.size;
    return g2048.board.some((v) => !v) || g2048.board.some((v, i) => (i % n < n - 1 && v === g2048.board[i + 1]) || (i < n * (n - 1) && v === g2048.board[i + n]));
  }

  function move2048(direction) {
    if (!g2048 || g2048.over || g2048.animating) return;
    const plan = plan2048(direction);
    if (!plan.changed) return;
    const boardEl = root.querySelector(".board-2048");
    g2048.animating = true; g2048.board = plan.board; g2048.score += plan.gained;
    const serial = ++animationSerial;
    if (boardEl) {
      const layer = boardEl.querySelector(".tile-layer-2048");
      const layerRect = layer?.getBoundingClientRect();
      plan.mappings.forEach(({ from, to }) => {
        const tile = boardEl.querySelector(`[data-tile-index="${from}"]`), target = boardEl.querySelector(`[data-grid-index="${to}"]`);
        if (tile && target && layerRect) { const targetRect = target.getBoundingClientRect(); tile.style.left = `${targetRect.left - layerRect.left}px`; tile.style.top = `${targetRect.top - layerRect.top}px`; }
      });
    }
    setTimeout(() => {
      if (!g2048 || serial !== animationSerial) return;
      const spawnIndex = add2048Tile(); g2048.animating = false;
      if (g2048.score > 0) g2048.newBest = recordBest(`2048.${g2048.size}`, g2048.score, true) || g2048.newBest;
      const reached = g2048.board.some((value) => value >= g2048.target);
      const canMove = canMove2048();
      if (activeGame !== "2048") return;
      render2048({ spawnIndex, mergedIndices: plan.mergedIndices });
      if (reached && !g2048.won) { g2048.won = true; showResult(`到达 ${g2048.target}！`, `${g2048.size}×${g2048.size} · ${g2048.score} 分`, "2048-new", "再来一局", g2048.newBest); }
      else if (!canMove) { g2048.over = true; showResult("棋盘满啦", `最终得分 ${g2048.score}`, "2048-new", "再试一次", g2048.newBest); }
    }, 175);
  }

  /* ---------- 翻牌配对 ---------- */
  let memory = null;
  const MEMORY_SYMBOLS = ["叶", "月", "云", "茶", "星", "花", "鱼", "果", "雨", "山", "风", "鹿"];

  function newMemory(levelKey = "normal") {
    activeGame = "memory"; stopTimer();
    const level = MEMORY_LEVELS[levelKey], symbols = shuffle([...MEMORY_SYMBOLS.slice(0, level.pairs), ...MEMORY_SYMBOLS.slice(0, level.pairs)]);
    memory = { levelKey, level, cards: symbols.map((symbol) => ({ symbol, open: false, matched: false })), first: null, lock: false, moves: 0, seconds: 0, started: false, done: false };
    renderMemory();
  }

  function renderMemory() {
    const options = Object.entries(MEMORY_LEVELS).map(([key, level]) => [key, level.label]);
    const stage = shell("翻牌配对", "记住位置，找出所有成对图案", `<label class="game-select">难度 <select id="memory-level">${selectOptions(options, memory.levelKey)}</select></label><button class="btn ghost sm" data-action="memory-new">重新洗牌</button>`);
    const currentBest = best(`memory.${memory.levelKey}`);
    stage.innerHTML = `<div class="game-info-row"><span>步数 <strong>${memory.moves}</strong></span><span>配对 <strong>${memory.cards.filter((c) => c.matched).length / 2}</strong> / ${memory.level.pairs}</span><span id="memory-time">${formatTime(memory.seconds)}</span><span>最佳 ${currentBest === null ? "--" : `${currentBest}步`}</span></div><div class="memory-grid" style="--memory-cols:${memory.level.cols};--memory-width:${Math.min(570, memory.level.cols * 88)}px">${memory.cards.map((card, index) => `<button class="memory-card ${card.open || card.matched ? "open" : ""} ${card.matched ? "matched" : ""}" data-memory-card="${index}" type="button" aria-label="${card.open || card.matched ? card.symbol : "未翻开的卡片"}"><span class="memory-front">✦</span><span class="memory-back">${card.symbol}</span></button>`).join("")}</div><p class="game-help">每次翻开两张；图案相同就会留下。排行榜按完成步数记录。</p>`;
  }

  function flipMemory(index) {
    const card = memory.cards[index];
    if (memory.lock || memory.done || card.open || card.matched) return;
    if (!memory.started) { memory.started = true; startTimer(() => { if (activeGame !== "memory" || memory.done) return; memory.seconds++; const time = root.querySelector("#memory-time"); if (time) time.textContent = formatTime(memory.seconds); }); }
    card.open = true;
    if (memory.first === null) { memory.first = index; renderMemory(); return; }
    memory.moves++; const first = memory.cards[memory.first];
    if (first.symbol === card.symbol) {
      first.matched = card.matched = true; memory.first = null; renderMemory();
      if (memory.cards.every((item) => item.matched)) { memory.done = true; stopTimer(); const isBest = recordBest(`memory.${memory.levelKey}`, memory.moves); showResult("全部配对成功", `${memory.level.short} · ${memory.moves} 步 · ${formatTime(memory.seconds)}`, "memory-new", "再来一局", isBest); }
      return;
    }
    memory.lock = true; renderMemory(); const firstIndex = memory.first;
    setTimeout(() => { if (activeGame !== "memory" || !memory) return; memory.cards[firstIndex].open = false; memory.cards[index].open = false; memory.first = null; memory.lock = false; renderMemory(); }, 650);
  }

  /* ---------- 扫雷 ---------- */
  let mines = null;
  let mineChord = null;

  function newMines(levelKey = "beginner") {
    activeGame = "mines"; stopTimer();
    const level = MINE_LEVELS[levelKey];
    mines = { levelKey, level, cells: Array.from({ length: level.rows * level.cols }, () => ({ mine: false, revealed: false, flag: false, near: 0 })), ready: false, mode: "reveal", seconds: 0, started: false, done: false };
    renderMines();
  }

  function mineNeighbors(index) {
    const { rows, cols } = mines.level, row = Math.floor(index / cols), col = index % cols, result = [];
    for (let dr = -1; dr <= 1; dr++) for (let dc = -1; dc <= 1; dc++) { const r = row + dr, c = col + dc; if ((dr || dc) && r >= 0 && r < rows && c >= 0 && c < cols) result.push(r * cols + c); }
    return result;
  }

  function prepareMines(safeIndex) {
    const excluded = new Set([safeIndex, ...mineNeighbors(safeIndex)]);
    shuffle(Array.from({ length: mines.cells.length }, (_, i) => i).filter((i) => !excluded.has(i))).slice(0, mines.level.count).forEach((i) => { mines.cells[i].mine = true; });
    mines.cells.forEach((cell, i) => { cell.near = mineNeighbors(i).filter((n) => mines.cells[n].mine).length; }); mines.ready = true;
  }

  function renderMines() {
    const options = Object.entries(MINE_LEVELS).map(([key, level]) => [key, level.label]), flags = mines.cells.filter((cell) => cell.flag).length;
    const stage = shell("扫雷", "数字代表周围八格中的地雷数量", `<label class="game-select">难度 <select id="mines-level">${selectOptions(options, mines.levelKey)}</select></label><button class="btn ghost sm" data-action="mines-new">新棋盘</button>`);
    const currentBest = best(`mines.${mines.levelKey}`), { rows, cols, cell } = mines.level;
    stage.innerHTML = `<div class="game-info-row mines-info"><span>剩余标记 <strong>${mines.level.count - flags}</strong></span><strong id="mines-time">${formatTime(mines.seconds)}</strong><span>最佳 ${currentBest === null ? "--:--" : formatTime(currentBest)}</span><span>${mines.ready ? "棋盘已生成" : "首格一定安全"}</span></div><div class="mines-wrap"><div class="mines-grid" style="--mine-cols:${cols};--mine-cell:${cell}px">${mines.cells.map((item, index) => `<button class="mine-cell ${item.revealed ? "revealed" : ""} ${item.flag ? "flagged" : ""} ${item.revealed && item.mine ? "is-mine" : ""}" data-mine-cell="${index}" type="button" data-near="${item.near}" aria-label="${item.flag ? "已标记" : item.revealed ? (item.mine ? "雷" : `周围 ${item.near} 颗雷`) : "未打开"}">${item.revealed ? (item.mine ? "✹" : item.near || "") : item.flag ? "⚑" : ""}</button>`).join("")}</div></div><div class="game-actions centered"><button class="btn ${mines.mode === "reveal" ? "primary" : "ghost"}" data-action="mines-reveal">打开格子</button><button class="btn ${mines.mode === "flag" ? "primary" : "ghost"}" data-action="mines-flag">插旗标记</button></div><p class="game-help">右键插旗；在已揭开的数字上同时按住鼠标左右键，可预览并展开所有可确定的相邻格。</p>`;
  }

  function startMinesTimer() {
    if (mines.started) return;
    mines.started = true; startTimer(() => { if (activeGame !== "mines" || mines.done) return; mines.seconds++; const time = root.querySelector("#mines-time"); if (time) time.textContent = formatTime(mines.seconds); });
  }

  function flagMine(index) {
    const cell = mines.cells[index]; if (mines.done || cell.revealed) return;
    if (!cell.flag && mines.cells.filter((item) => item.flag).length >= mines.level.count) return;
    cell.flag = !cell.flag; renderMines();
  }

  function floodRevealMines(startIndices) {
    const queue = [...startIndices], seen = new Set();
    while (queue.length) {
      const current = queue.shift();
      if (seen.has(current)) continue;
      seen.add(current);
      const cell = mines.cells[current];
      if (!cell || cell.flag || cell.revealed) continue;
      cell.revealed = true;
      if (!cell.mine && cell.near === 0) mineNeighbors(current).forEach((next) => { if (!mines.cells[next].revealed) queue.push(next); });
    }
  }

  function finishMineReveal(hitMine = false) {
    if (hitMine) {
      mines.done = true; stopTimer(); mines.cells.forEach((cell) => { if (cell.mine) cell.revealed = true; });
      renderMines(); showResult("踩到雷啦", "旗帜数量正确但位置错误时，双键展开也可能触雷", "mines-new", "再试一次"); return;
    }
    const won = mines.cells.every((cell) => cell.mine || cell.revealed);
    if (won) {
      mines.done = true; stopTimer(); const isBest = recordBest(`mines.${mines.levelKey}`, mines.seconds);
      renderMines(); showResult("雷区清理完成", `${mines.level.short} · 用时 ${formatTime(mines.seconds)}`, "mines-new", "再来一局", isBest);
    } else renderMines();
  }

  function revealMine(index) {
    if (mines.done || mines.cells[index].flag || mines.cells[index].revealed) return;
    if (!mines.ready) prepareMines(index); startMinesTimer();
    const hitMine = mines.cells[index].mine;
    floodRevealMines([index]);
    finishMineReveal(hitMine);
  }

  function previewMineChord(index, active) {
    mineNeighbors(index).forEach((neighbor) => {
      const cell = mines.cells[neighbor];
      if (!cell.revealed && !cell.flag) root.querySelector(`[data-mine-cell="${neighbor}"]`)?.classList.toggle("chord-preview", active);
    });
  }

  function chordMine(index) {
    const cell = mines.cells[index];
    if (!cell?.revealed || cell.near <= 0 || mines.done) return;
    const neighbors = mineNeighbors(index);
    const flags = neighbors.filter((neighbor) => mines.cells[neighbor].flag).length;
    if (flags !== cell.near) { previewMineChord(index, false); announce(`需要 ${cell.near} 面旗，当前有 ${flags} 面`); return; }
    const targets = neighbors.filter((neighbor) => !mines.cells[neighbor].flag && !mines.cells[neighbor].revealed);
    const hitMine = targets.some((neighbor) => mines.cells[neighbor].mine);
    floodRevealMines(targets);
    finishMineReveal(hitMine);
  }

  /* ---------- 点灯 ---------- */
  let lights = null;

  function toggleLight(board, index, size = lights.size) {
    const row = Math.floor(index / size), col = index % size;
    [[row, col], [row - 1, col], [row + 1, col], [row, col - 1], [row, col + 1]].forEach(([r, c]) => { if (r >= 0 && r < size && c >= 0 && c < size) board[r * size + c] ^= 1; });
  }

  function solveLights(board, size = lights.size) {
    let bestSolution = null;
    for (let mask = 0; mask < 2 ** size; mask++) {
      const work = [...board], presses = [];
      for (let col = 0; col < size; col++) if (mask & (1 << col)) { toggleLight(work, col, size); presses.push(col); }
      for (let row = 1; row < size; row++) for (let col = 0; col < size; col++) if (work[(row - 1) * size + col]) { const index = row * size + col; toggleLight(work, index, size); presses.push(index); }
      if (work.slice(size * (size - 1)).every((v) => !v) && (!bestSolution || presses.length < bestSolution.length)) bestSolution = presses;
    }
    return bestSolution || [];
  }

  function newLights(size = 5) {
    activeGame = "lights"; stopTimer();
    let board = Array(size * size).fill(0); shuffle(Array.from({ length: size * size }, (_, i) => i)).slice(0, LIGHT_LEVELS[size].shuffle).forEach((i) => toggleLight(board, i, size));
    if (board.every((v) => !v)) toggleLight(board, Math.floor(size * size / 2), size);
    lights = { size, board, moves: 0, hint: null, done: false }; renderLights();
  }

  function renderLights() {
    const options = Object.entries(LIGHT_LEVELS).map(([size, level]) => [size, level.label]);
    const stage = shell("点灯", "按下一格，它和上下左右会一起变化", `<label class="game-select">难度 <select id="lights-size">${selectOptions(options, lights.size)}</select></label><button class="btn ghost sm" data-action="lights-new">新棋局</button>`);
    const currentBest = best(`lights.${lights.size}`), cellSize = lights.size === 3 ? 64 : lights.size === 5 ? 54 : 43;
    stage.innerHTML = `<div class="game-info-row"><span>目标：全部熄灭</span><strong>${lights.moves} 步</strong><span>${lights.board.filter(Boolean).length} 盏亮着</span><span>最佳 ${currentBest === null ? "--" : `${currentBest}步`}</span></div><div class="lights-grid" style="--light-size:${lights.size};--light-cell:${cellSize}px">${lights.board.map((on, index) => `<button class="light-cell ${on ? "on" : ""} ${lights.hint === index ? "hint" : ""}" data-light-cell="${index}" type="button" aria-label="第 ${Math.floor(index / lights.size) + 1} 行第 ${index % lights.size + 1} 列，${on ? "亮" : "灭"}"><i></i></button>`).join("")}</div><div class="game-actions centered"><button class="btn ghost" data-action="lights-hint">提示下一步</button></div><p class="game-help">每次点击会翻转十字范围。所有尺寸均保证有解，提示会标出推荐的下一步。</p>`;
  }

  function pressLight(index) {
    if (lights.done) return;
    toggleLight(lights.board, index); lights.moves++; lights.hint = null;
    if (lights.board.every((value) => !value)) { lights.done = true; const isBest = recordBest(`lights.${lights.size}`, lights.moves); renderLights(); showResult("灯都熄灭了", `${lights.size}×${lights.size} · ${lights.moves} 步完成`, "lights-new", "再来一局", isBest); } else renderLights();
  }

  function openGame(id) {
    stopTimer();
    if (id === "nonogram") newNonogram(5);
    else if (id === "2048") new2048(4);
    else if (id === "memory") newMemory("normal");
    else if (id === "mines") newMines("beginner");
    else if (id === "lights") newLights(5);
  }

  root.addEventListener("click", async (event) => {
    const gameCard = event.target.closest("[data-game]"); if (gameCard) { openGame(gameCard.dataset.game); return; }
    const ngCell = event.target.closest("[data-ng-cell]"); if (ngCell) { setNonogramCell(Number(ngCell.dataset.ngCell)); return; }
    const memoryCard = event.target.closest("[data-memory-card]"); if (memoryCard) { flipMemory(Number(memoryCard.dataset.memoryCard)); return; }
    const mineCell = event.target.closest("[data-mine-cell]"); if (mineCell) { const index = Number(mineCell.dataset.mineCell); if (mines.mode === "flag") flagMine(index); else revealMine(index); return; }
    const lightCell = event.target.closest("[data-light-cell]"); if (lightCell) { pressLight(Number(lightCell.dataset.lightCell)); return; }
    const move = event.target.closest("[data-move]"); if (move) { move2048(move.dataset.move); return; }
    const action = event.target.closest("[data-action]")?.dataset.action; if (!action) return;
    if (action === "games-home") showGamesHome();
    else if (action === "clear-records") { const allowed = typeof confirmDialog === "function" ? await confirmDialog("确定清除所有小游戏个人纪录吗？游戏内容不会受影响。", { title: "清除个人排行榜", okText: "清除", icon: "↺" }) : false; if (allowed) { stats.best = {}; stats.wins = {}; saveStats(); showGamesHome(); } }
    else if (action === "ng-new") newNonogram(ng?.size || 5);
    else if (action === "ng-mode") { ng.markMode = !ng.markMode; renderNonogram(); }
    else if (action === "ng-hint") hintNonogram();
    else if (action === "2048-new") new2048(g2048?.size || 4);
    else if (action === "memory-new") newMemory(memory?.levelKey || "normal");
    else if (action === "mines-new") newMines(mines?.levelKey || "beginner");
    else if (action === "mines-reveal") { mines.mode = "reveal"; renderMines(); }
    else if (action === "mines-flag") { mines.mode = "flag"; renderMines(); }
    else if (action === "lights-new") newLights(lights?.size || 5);
    else if (action === "lights-hint") { lights.hint = solveLights(lights.board)[0] ?? null; renderLights(); }
  });

  root.addEventListener("change", (event) => {
    if (event.target.id === "ng-size") newNonogram(Number(event.target.value));
    else if (event.target.id === "size-2048") new2048(Number(event.target.value));
    else if (event.target.id === "memory-level") newMemory(event.target.value);
    else if (event.target.id === "mines-level") newMines(event.target.value);
    else if (event.target.id === "lights-size") newLights(Number(event.target.value));
  });

  root.addEventListener("contextmenu", (event) => {
    const ngCell = event.target.closest("[data-ng-cell]"), mineCell = event.target.closest("[data-mine-cell]");
    if (!ngCell && !mineCell) return; event.preventDefault();
    if (ngCell) setNonogramCell(Number(ngCell.dataset.ngCell), true);
    if (mineCell) flagMine(Number(mineCell.dataset.mineCell));
  });

  let swipeStart = null;
  root.addEventListener("mousedown", (event) => {
    const mineCell = event.target.closest("[data-mine-cell]");
    if (activeGame === "mines" && mineCell && event.buttons === 3) {
      const index = Number(mineCell.dataset.mineCell), cell = mines.cells[index];
      if (cell?.revealed && cell.near > 0) { event.preventDefault(); mineChord = { index }; previewMineChord(index, true); }
    }
  });
  root.addEventListener("mouseup", (event) => {
    if (!mineChord) return;
    event.preventDefault();
    const index = mineChord.index; previewMineChord(index, false); mineChord = null; chordMine(index);
  });
  root.addEventListener("pointerdown", (event) => {
    if (event.target.closest(".board-2048")) swipeStart = { x: event.clientX, y: event.clientY };
  });
  root.addEventListener("pointerup", (event) => {
    if (!swipeStart || !event.target.closest(".board-2048")) { swipeStart = null; return; }
    const dx = event.clientX - swipeStart.x, dy = event.clientY - swipeStart.y; swipeStart = null;
    if (Math.max(Math.abs(dx), Math.abs(dy)) < 24) return;
    move2048(Math.abs(dx) > Math.abs(dy) ? (dx > 0 ? "right" : "left") : (dy > 0 ? "down" : "up"));
  });
  root.addEventListener("mouseleave", () => { if (mineChord) { previewMineChord(mineChord.index, false); mineChord = null; } });

  document.addEventListener("keydown", (event) => {
    const gamesView = document.querySelector("#games-view"); if (!gamesView || gamesView.classList.contains("hidden")) return;
    if (event.key === "Escape" && activeGame !== "home") { event.preventDefault(); showGamesHome(); return; }
    if (activeGame !== "2048") return;
    const directions = { ArrowUp: "up", ArrowDown: "down", ArrowLeft: "left", ArrowRight: "right" };
    if (directions[event.key]) { event.preventDefault(); move2048(directions[event.key]); }
  });

  function leaveGamesView() {
    stopTimer(); animationSerial++;
    activeGame = "home";
    ng = null; g2048 = null; memory = null; mines = null; lights = null;
    mineChord = null; swipeStart = null;
    root.replaceChildren();
    window.ShyNonogram?.release?.();
  }

  window.showGamesHome = showGamesHome;
  window.leaveGamesView = leaveGamesView;
  showGamesHome();
})();
