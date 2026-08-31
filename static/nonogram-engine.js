(function (host) {
  "use strict";

  const patternCache = new Map();
  const MAX_PATTERN_CACHE_ENTRIES = 192;

  function rememberPatterns(key, patterns) {
    if (patternCache.has(key)) patternCache.delete(key);
    while (patternCache.size >= MAX_PATTERN_CACHE_ENTRIES) {
      patternCache.delete(patternCache.keys().next().value);
    }
    patternCache.set(key, patterns);
    return patterns;
  }

  function release() {
    patternCache.clear();
  }

  function cluesForLine(line) {
    const clues = [];
    let run = 0;
    for (const value of line) {
      if (Number(value)) run++;
      else if (run) { clues.push(run); run = 0; }
    }
    if (run) clues.push(run);
    return clues.length ? clues : [0];
  }

  function cluesForRows(rows) {
    const size = rows.length;
    const matrix = rows.map((row) => Array.from(row, Number));
    return {
      rows: matrix.map(cluesForLine),
      cols: Array.from({ length: size }, (_, col) => cluesForLine(matrix.map((row) => row[col]))),
    };
  }

  function combination(n, k) {
    const count = Math.min(k, n - k);
    let value = 1;
    for (let i = 1; i <= count; i++) value = value * (n - count + i) / i;
    return Math.round(value);
  }

  function linePatterns(length, rawClues) {
    const clues = rawClues.length === 1 && rawClues[0] === 0 ? [] : rawClues;
    const key = `${length}:${clues.join(",")}`;
    if (patternCache.has(key)) return patternCache.get(key);
    const slack = length - clues.reduce((sum, value) => sum + value, 0) - Math.max(0, clues.length - 1);
    const patternCount = clues.length ? combination(slack + clues.length, clues.length) : 1;
    const patterns = new Uint32Array(patternCount);
    let patternIndex = 0;
    const remaining = Array(clues.length + 1).fill(0);
    for (let i = clues.length - 1; i >= 0; i--) remaining[i] = remaining[i + 1] + clues[i] + (i < clues.length - 1 ? 1 : 0);
    function place(group, start, mask) {
      if (group === clues.length) { patterns[patternIndex++] = mask >>> 0; return; }
      const run = clues[group];
      const latest = length - remaining[group];
      for (let pos = start; pos <= latest; pos++) {
        let nextMask = mask;
        for (let cell = pos; cell < pos + run; cell++) nextMask |= (1 << cell);
        place(group + 1, pos + run + 1, nextMask);
      }
    }
    if (!clues.length) patterns[0] = 0;
    else place(0, 0, 0);
    return rememberPatterns(key, patterns);
  }

  function settleLine(state, clues) {
    let knownOn = 0, knownOff = 0;
    for (let i = 0; i < state.length; i++) {
      if (state[i] === 1) knownOn |= (1 << i);
      else if (state[i] === 0) knownOff |= (1 << i);
    }
    const patterns = linePatterns(state.length, clues);
    let validCount = 0, alwaysOn = 0, everOn = 0;
    for (const mask of patterns) {
      if ((mask & knownOn) !== knownOn || (mask & knownOff) !== 0) continue;
      if (!validCount) alwaysOn = mask;
      else alwaysOn &= mask;
      everOn |= mask;
      validCount++;
    }
    if (!validCount) return { contradiction: true, changes: [] };
    const changes = [];
    for (let i = 0; i < state.length; i++) {
      if (state[i] !== -1) continue;
      const bit = 1 << i;
      if (alwaysOn & bit) changes.push([i, 1]);
      else if (!(everOn & bit)) changes.push([i, 0]);
    }
    return { contradiction: false, changes, candidates: validCount };
  }

  function solveWithLogic(rows) {
    const size = rows.length;
    const clues = cluesForRows(rows);
    const grid = new Int8Array(size * size); grid.fill(-1);
    let rounds = 0, successfulLines = 0, singleCellSteps = 0, lineChecks = 0, openingCells = 0;
    let maxCandidates = 0, minGain = size;
    while (rounds < size * 4) {
      rounds++;
      let roundChanges = 0;
      for (let axis = 0; axis < 2; axis++) for (let line = 0; line < size; line++) {
        const state = Array.from({ length: size }, (_, pos) => grid[axis === 0 ? line * size + pos : pos * size + line]);
        const result = settleLine(state, axis === 0 ? clues.rows[line] : clues.cols[line]);
        lineChecks++;
        if (result.contradiction) return { solved: false, contradiction: true, rounds, score: 0 };
        maxCandidates = Math.max(maxCandidates, result.candidates || 0);
        if (!result.changes.length) continue;
        successfulLines++;
        if (result.changes.length === 1) singleCellSteps++;
        minGain = Math.min(minGain, result.changes.length);
        for (const [pos, value] of result.changes) grid[axis === 0 ? line * size + pos : pos * size + line] = value;
        roundChanges += result.changes.length;
      }
      if (rounds === 1) openingCells = roundChanges;
      if (grid.every((value) => value !== -1)) break;
      if (!roundChanges) break;
    }
    const solved = grid.every((value) => value !== -1);
    const matches = solved && rows.every((row, r) => Array.from(row, Number).every((value, c) => value === grid[r * size + c]));
    const stepRatio = successfulLines / Math.max(1, size * 2);
    const narrowRatio = singleCellSteps / Math.max(1, successfulLines);
    const openingRatio = openingCells / (size * size);
    const score = Math.round(rounds * 24 + stepRatio * 28 + narrowRatio * 28 + (1 - openingRatio) * 24);
    return { solved: matches, contradiction: false, rounds, successfulLines, singleCellSteps, lineChecks, openingCells, maxCandidates, minGain, score };
  }

  function quality(rows) {
    const size = rows.length;
    const matrix = rows.map((row) => Array.from(row, Number));
    const lines = [...matrix, ...Array.from({ length: size }, (_, col) => matrix.map((row) => row[col]))];
    const lineClues = lines.map(cluesForLine);
    const clues = lineClues.flat().filter(Boolean);
    const filled = matrix.flat().reduce((sum, value) => sum + value, 0);
    const singleCount = clues.filter((value) => value === 1).length;
    return {
      density: filled / (size * size),
      emptyLines: lineClues.filter((clue) => clue.length === 1 && clue[0] === 0).length,
      fullLines: lineClues.filter((clue) => clue.length === 1 && clue[0] === size).length,
      singleRatio: singleCount / Math.max(1, clues.length),
      shortRatio: clues.filter((value) => value <= 2).length / Math.max(1, clues.length),
      averageRun: clues.reduce((sum, value) => sum + value, 0) / Math.max(1, clues.length),
      maxSinglesInLine: Math.max(...lineClues.map((clue) => clue.filter((value) => value === 1).length), 0),
      distinctRuns: new Set(clues).size,
      longest: Math.max(...clues, 0),
    };
  }

  function passesQuality(rows) {
    const size = rows.length;
    const q = quality(rows);
    return q.density >= .32 && q.density <= .58
      && q.emptyLines <= Math.max(1, Math.floor(size * .08))
      && q.fullLines === 0
      && q.singleRatio <= (size <= 10 ? .24 : .20)
      && q.shortRatio <= .62
      && q.averageRun >= (size <= 10 ? 2.15 : 2.35)
      && q.maxSinglesInLine <= Math.max(2, Math.floor(size / 7))
      && q.distinctRuns >= Math.min(6, Math.max(3, Math.floor(size / 5) + 2))
      && q.longest >= Math.max(4, Math.floor(size * .2));
  }

  function randomCandidate(size, random) {
    let grid = Array.from({ length: size }, () => Array.from({ length: size }, () => random() < (.47 + (random() - .5) * .08) ? 1 : 0));
    const passes = size <= 10 ? 1 : 2;
    for (let pass = 0; pass < passes; pass++) {
      grid = grid.map((row, r) => row.map((value, c) => {
        let near = 0, total = 0;
        for (let dr = -1; dr <= 1; dr++) for (let dc = -1; dc <= 1; dc++) {
          if (!dr && !dc) continue;
          const rr = r + dr, cc = c + dc;
          if (rr >= 0 && rr < size && cc >= 0 && cc < size) { near += grid[rr][cc]; total++; }
        }
        const threshold = total < 8 ? 3 : 4;
        return near > threshold || (near === threshold && (value || random() < .38)) ? 1 : 0;
      }));
    }
    // A few thick strokes create recognisable, longer runs without forcing perfect symmetry.
    const strokes = Math.max(2, Math.floor(size / 7));
    for (let stroke = 0; stroke < strokes; stroke++) {
      let r = Math.floor(random() * size), c = Math.floor(random() * size);
      const length = Math.floor(size * (.35 + random() * .45));
      const horizontal = random() < .5;
      for (let step = 0; step < length; step++) {
        const radius = random() < .72 ? 1 : 0;
        for (let dr = -radius; dr <= radius; dr++) for (let dc = -radius; dc <= radius; dc++) {
          const rr = r + dr, cc = c + dc;
          if (rr >= 0 && rr < size && cc >= 0 && cc < size) grid[rr][cc] = 1;
        }
        if (horizontal) { c += random() < .78 ? 1 : (random() < .5 ? -1 : 0); r += random() < .18 ? (random() < .5 ? -1 : 1) : 0; }
        else { r += random() < .78 ? 1 : (random() < .5 ? -1 : 0); c += random() < .18 ? (random() < .5 ? -1 : 1) : 0; }
        r = Math.max(0, Math.min(size - 1, r)); c = Math.max(0, Math.min(size - 1, c));
      }
    }
    return grid.map((row) => row.join(""));
  }

  const profiles = {
    10: { minRounds: 3, minScore: 120, attempts: 150 },
    15: { minRounds: 4, minScore: 160, attempts: 130 },
    20: { minRounds: 5, minScore: 195, attempts: 110 },
    25: { minRounds: 6, minScore: 240, attempts: 90 },
  };

  // These are deterministic safety nets, pre-checked by the same logical solver.
  const verifiedFallbacks = {
    10: ["1111110000", "1111110000", "1110011100", "0000001110", "0111001111", "0001101111", "0000111111", "1000011000", "1000011100", "0000000000"],
    15: ["000000100001110", "000001100001111", "000011100001111", "000111100001111", "000111000000000", "000000000001000", "010111000000000", "011111000000000", "111111000000000", "111111110000000", "010111111101111", "000000110111111", "000000011111111", "000000011111111", "000000011111110"],
    20: ["00111000000000011110", "01111000000000011110", "01110000000000111110", "01110000000000101110", "00000000000001111110", "01000011100001111111", "01110111110000111111", "11111111110000011111", "00111111110000000111", "00011111111000000111", "00001111111000000011", "00001111111000000011", "00000111111000000000", "00000011111100000000", "00000111111110000000", "00000111111110000000", "10001111100000001100", "00001110100000011111", "00000011111000011100", "00000000111000011110"],
    25: ["0110000000000000000011000", "1110000000000000001111100", "1110000000000000101111100", "1010001111110000111111100", "1000011111111111111111110", "1100011111111111011111111", "1000011100111111000111111", "1000111100011111101111111", "0000011100011111110111110", "0000111111111111100011111", "0011111111111111000000111", "1111111111111111000000011", "1100011111111111000110000", "0000111111111111101111000", "0000011111111111111111000", "0000001111111111101110000", "0000000000110000000000011", "0000001111111000000000011", "0000011111111110000000011", "0000111111111111111000011", "1000011111111111110000011", "1100011111111111110000000", "1000011111111111100000000", "0000011111110011000000001", "0000011111110000000000011"],
  };

  function generate(size, random = Math.random) {
    const profile = profiles[size] || profiles[10];
    release();
    try {
      for (let attempt = 0; attempt < profile.attempts; attempt++) {
        const rows = randomCandidate(size, random);
        if (!passesQuality(rows)) continue;
        const rating = solveWithLogic(rows);
        if (!rating.solved) continue;
        const candidate = { rows, rating, quality: quality(rows) };
        if (rating.rounds >= profile.minRounds && rating.score >= profile.minScore) return candidate;
      }
      const rows = verifiedFallbacks[size] || verifiedFallbacks[10];
      return { rows: [...rows], rating: solveWithLogic(rows), quality: quality(rows), fallback: true };
    } finally {
      // Runtime gameplay only needs the accepted rows and rating. The often-large
      // line permutations are generation scratch data and must not accumulate.
      release();
    }
  }

  const api = {
    cluesForLine, cluesForRows, quality, passesQuality, solveWithLogic, generate, profiles, release,
    cacheSize: () => patternCache.size,
  };
  host.ShyNonogram = api;
  if (typeof module !== "undefined" && module.exports) module.exports = api;
})(typeof window !== "undefined" ? window : globalThis);
