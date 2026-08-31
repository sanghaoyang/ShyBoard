const engine = require("../static/nonogram-engine.js");

const samplesPerSize = Number(process.argv[2] || 250);
let failures = 0;

for (const size of [10, 15, 20, 25]) {
  const profile = engine.profiles[size];
  const summary = { minScore: Infinity, maxScore: 0, minRounds: Infinity, maxRounds: 0, maxSingleRatio: 0, fallbacks: 0 };
  const started = Date.now();
  for (let sample = 0; sample < samplesPerSize; sample++) {
    const puzzle = engine.generate(size);
    if (engine.cacheSize() !== 0) {
      failures++;
      console.error("CACHE_NOT_RELEASED", { size, sample, entries: engine.cacheSize() });
      break;
    }
    const rating = engine.solveWithLogic(puzzle.rows);
    const quality = engine.quality(puzzle.rows);
    const valid = rating.solved
      && engine.passesQuality(puzzle.rows)
      && rating.rounds >= profile.minRounds
      && rating.score >= profile.minScore
      && quality.singleRatio <= (size <= 10 ? .24 : .20);
    if (!valid) {
      failures++;
      console.error("INVALID", { size, sample, rating, quality });
      break;
    }
    summary.minScore = Math.min(summary.minScore, rating.score);
    summary.maxScore = Math.max(summary.maxScore, rating.score);
    summary.minRounds = Math.min(summary.minRounds, rating.rounds);
    summary.maxRounds = Math.max(summary.maxRounds, rating.rounds);
    summary.maxSingleRatio = Math.max(summary.maxSingleRatio, quality.singleRatio);
    if (puzzle.fallback) summary.fallbacks++;
    engine.release();
  }
  console.log(`${size}x${size}`, { ...summary, milliseconds: Date.now() - started });
}

if (failures) process.exit(1);
console.log(`PASS: ${samplesPerSize * 4} generated puzzles are unique-by-propagation, logically solvable, and inside their difficulty bands.`);
