// Mock data shaped after the agent's internal systems:
//   events.py  → MetricsSummary (wins, losses, per-opponent, move_times_ms)
//   bandit.py  → BanditArmStats (strategy win rates per opponent)
//   feedback.py → Lesson (type, confidence, gain, summary)
//   opponent.py → OpponentModel (games_played, wins, losses, is_fixed_*)
//   bots.py    → 15 bots: 5 SCOUT (fixed placement+fire), 5 WARSHIP fixed-place, 5 WARSHIP random

// ── Per-Opponent Stats ────────────────────────────────────────────────────────

export interface OpponentStat {
  id: string;
  displayName: string;
  opponentClass: "SCOUT" | "WARSHIP";
  baseScore: number;
  gamesPlayed: number;
  wins: number;
  losses: number;
  winRate: number;
  avgMoves: number;
  bestMoves: number;
  fixedPlacement: boolean;
  fixedFiring: boolean;
  strategyUsed: string;
}

export const perOpponentStats: OpponentStat[] = [
  { id: "scout-01", displayName: "Scout Alpha",       opponentClass: "SCOUT",   baseScore: 14, gamesPlayed: 1, wins: 1, losses: 0, winRate: 1.0,  avgMoves: 17, bestMoves: 17, fixedPlacement: true,  fixedFiring: true,  strategyUsed: "exploit" },
  { id: "scout-02", displayName: "Scout Bravo",       opponentClass: "SCOUT",   baseScore: 14, gamesPlayed: 1, wins: 1, losses: 0, winRate: 1.0,  avgMoves: 17, bestMoves: 17, fixedPlacement: true,  fixedFiring: true,  strategyUsed: "exploit" },
  { id: "scout-03", displayName: "Scout Charlie",     opponentClass: "SCOUT",   baseScore: 14, gamesPlayed: 1, wins: 1, losses: 0, winRate: 1.0,  avgMoves: 19, bestMoves: 19, fixedPlacement: true,  fixedFiring: true,  strategyUsed: "exploit" },
  { id: "scout-04", displayName: "Scout Delta",       opponentClass: "SCOUT",   baseScore: 14, gamesPlayed: 1, wins: 1, losses: 0, winRate: 1.0,  avgMoves: 17, bestMoves: 17, fixedPlacement: true,  fixedFiring: true,  strategyUsed: "exploit" },
  { id: "scout-05", displayName: "Scout Echo",        opponentClass: "SCOUT",   baseScore: 14, gamesPlayed: 1, wins: 1, losses: 0, winRate: 1.0,  avgMoves: 18, bestMoves: 18, fixedPlacement: true,  fixedFiring: true,  strategyUsed: "exploit" },
  { id: "warship-01", displayName: "Warship Alpha",   opponentClass: "WARSHIP", baseScore: 15, gamesPlayed: 1, wins: 1, losses: 0, winRate: 1.0,  avgMoves: 24, bestMoves: 24, fixedPlacement: true,  fixedFiring: false, strategyUsed: "exploit" },
  { id: "warship-02", displayName: "Warship Bravo",   opponentClass: "WARSHIP", baseScore: 15, gamesPlayed: 1, wins: 1, losses: 0, winRate: 1.0,  avgMoves: 22, bestMoves: 22, fixedPlacement: true,  fixedFiring: false, strategyUsed: "hunt" },
  { id: "warship-03", displayName: "Warship Charlie", opponentClass: "WARSHIP", baseScore: 15, gamesPlayed: 1, wins: 1, losses: 0, winRate: 1.0,  avgMoves: 28, bestMoves: 28, fixedPlacement: true,  fixedFiring: false, strategyUsed: "hunt" },
  { id: "warship-04", displayName: "Warship Delta",   opponentClass: "WARSHIP", baseScore: 15, gamesPlayed: 1, wins: 0, losses: 1, winRate: 0.0,  avgMoves: 51, bestMoves: 51, fixedPlacement: true,  fixedFiring: false, strategyUsed: "probability" },
  { id: "warship-05", displayName: "Warship Echo",    opponentClass: "WARSHIP", baseScore: 15, gamesPlayed: 1, wins: 1, losses: 0, winRate: 1.0,  avgMoves: 35, bestMoves: 35, fixedPlacement: true,  fixedFiring: false, strategyUsed: "probability" },
  { id: "warship-06", displayName: "Warship Foxtrot", opponentClass: "WARSHIP", baseScore: 15, gamesPlayed: 1, wins: 0, losses: 1, winRate: 0.0,  avgMoves: 58, bestMoves: 58, fixedPlacement: false, fixedFiring: false, strategyUsed: "probability" },
  { id: "warship-07", displayName: "Warship Golf",    opponentClass: "WARSHIP", baseScore: 15, gamesPlayed: 1, wins: 1, losses: 0, winRate: 1.0,  avgMoves: 41, bestMoves: 41, fixedPlacement: false, fixedFiring: false, strategyUsed: "hunt" },
  { id: "warship-08", displayName: "Warship Hotel",   opponentClass: "WARSHIP", baseScore: 15, gamesPlayed: 1, wins: 0, losses: 1, winRate: 0.0,  avgMoves: 62, bestMoves: 62, fixedPlacement: false, fixedFiring: false, strategyUsed: "probability" },
  { id: "warship-09", displayName: "Warship India",   opponentClass: "WARSHIP", baseScore: 15, gamesPlayed: 1, wins: 1, losses: 0, winRate: 1.0,  avgMoves: 38, bestMoves: 38, fixedPlacement: false, fixedFiring: false, strategyUsed: "hunt" },
  { id: "warship-10", displayName: "Warship Juliet",  opponentClass: "WARSHIP", baseScore: 15, gamesPlayed: 1, wins: 0, losses: 1, winRate: 0.0,  avgMoves: 55, bestMoves: 55, fixedPlacement: false, fixedFiring: false, strategyUsed: "probability" },
];

// ── Aggregate KPIs ────────────────────────────────────────────────────────────

export const kpis = {
  totalGames: 15,
  wins: 11,
  losses: 4,
  winRate: 73.3,
  winRateDelta: 8.2,       // vs previous run
  avgMovesPerGame: 32.8,
  avgMovesDelta: -5.6,     // improvement (negative = better)
  avgLatencyMs: 12.3,
  latencyStatus: "healthy" as const,
  patternsDetected: 18,
  patternBreakdown: { fixedPlacement: 10, fixedFiring: 5, heatmapPrior: 3 },
  totalScore: 387,
  scoreDelta: 24,
  strategySwitches: 7,
  timeoutWarnings: 0,
  totalMoveSavings: 42,
};

// ── Per-Game Timeline ─────────────────────────────────────────────────────────

export interface GameTimelineEntry {
  game: number;
  opponent: string;
  opponentClass: "SCOUT" | "WARSHIP";
  won: boolean;
  moves: number;
  baselineMoves: number | null;
  strategy: string;
  avgLatencyMs: number;
  cumulativeWinRate: number;
}

export const gameTimeline: GameTimelineEntry[] = [
  { game: 1,  opponent: "Scout Alpha",       opponentClass: "SCOUT",   won: true,  moves: 17, baselineMoves: null, strategy: "exploit",      avgLatencyMs: 8.2,  cumulativeWinRate: 100.0 },
  { game: 2,  opponent: "Scout Bravo",       opponentClass: "SCOUT",   won: true,  moves: 17, baselineMoves: 34,   strategy: "exploit",      avgLatencyMs: 7.8,  cumulativeWinRate: 100.0 },
  { game: 3,  opponent: "Scout Charlie",     opponentClass: "SCOUT",   won: true,  moves: 19, baselineMoves: 38,   strategy: "exploit",      avgLatencyMs: 9.1,  cumulativeWinRate: 100.0 },
  { game: 4,  opponent: "Scout Delta",       opponentClass: "SCOUT",   won: true,  moves: 17, baselineMoves: null, strategy: "exploit",      avgLatencyMs: 11.4, cumulativeWinRate: 100.0 },
  { game: 5,  opponent: "Scout Echo",        opponentClass: "SCOUT",   won: true,  moves: 18, baselineMoves: 32,   strategy: "exploit",      avgLatencyMs: 6.5,  cumulativeWinRate: 100.0 },
  { game: 6,  opponent: "Warship Alpha",     opponentClass: "WARSHIP", won: true,  moves: 24, baselineMoves: 41,   strategy: "exploit",      avgLatencyMs: 14.2, cumulativeWinRate: 100.0 },
  { game: 7,  opponent: "Warship Bravo",     opponentClass: "WARSHIP", won: true,  moves: 22, baselineMoves: 39,   strategy: "hunt",         avgLatencyMs: 12.7, cumulativeWinRate: 100.0 },
  { game: 8,  opponent: "Warship Charlie",   opponentClass: "WARSHIP", won: true,  moves: 28, baselineMoves: 45,   strategy: "hunt",         avgLatencyMs: 15.3, cumulativeWinRate: 100.0 },
  { game: 9,  opponent: "Warship Delta",     opponentClass: "WARSHIP", won: false, moves: 51, baselineMoves: null, strategy: "probability",  avgLatencyMs: 18.6, cumulativeWinRate: 88.9 },
  { game: 10, opponent: "Warship Echo",      opponentClass: "WARSHIP", won: true,  moves: 35, baselineMoves: 48,   strategy: "probability",  avgLatencyMs: 13.1, cumulativeWinRate: 90.0 },
  { game: 11, opponent: "Warship Foxtrot",   opponentClass: "WARSHIP", won: false, moves: 58, baselineMoves: null, strategy: "probability",  avgLatencyMs: 19.4, cumulativeWinRate: 81.8 },
  { game: 12, opponent: "Warship Golf",      opponentClass: "WARSHIP", won: true,  moves: 41, baselineMoves: 52,   strategy: "hunt",         avgLatencyMs: 11.8, cumulativeWinRate: 83.3 },
  { game: 13, opponent: "Warship Hotel",     opponentClass: "WARSHIP", won: false, moves: 62, baselineMoves: null, strategy: "probability",  avgLatencyMs: 21.2, cumulativeWinRate: 76.9 },
  { game: 14, opponent: "Warship India",     opponentClass: "WARSHIP", won: true,  moves: 38, baselineMoves: 50,   strategy: "hunt",         avgLatencyMs: 10.5, cumulativeWinRate: 78.6 },
  { game: 15, opponent: "Warship Juliet",    opponentClass: "WARSHIP", won: false, moves: 55, baselineMoves: null, strategy: "probability",  avgLatencyMs: 16.9, cumulativeWinRate: 73.3 },
];

// ── Bandit Strategy Stats ─────────────────────────────────────────────────────

export interface StrategyStats {
  strategy: string;
  gamesPlayed: number;
  wins: number;
  losses: number;
  winRate: number;
  avgMoves: number;
  color: string;
}

export const strategyStats: StrategyStats[] = [
  { strategy: "exploit",     gamesPlayed: 6, wins: 6, losses: 0, winRate: 100.0, avgMoves: 19.2, color: "#F26B21" },
  { strategy: "hunt",        gamesPlayed: 4, wins: 4, losses: 0, winRate: 100.0, avgMoves: 32.3, color: "#F78E31" },
  { strategy: "probability", gamesPlayed: 5, wins: 1, losses: 4, winRate: 20.0,  avgMoves: 52.2, color: "#FBB040" },
];

// ── Latency Distribution ──────────────────────────────────────────────────────

export interface LatencyBucket {
  range: string;
  count: number;
  percentage: number;
}

export const latencyDistribution: LatencyBucket[] = [
  { range: "0–5ms",   count: 42,  percentage: 8.5 },
  { range: "5–10ms",  count: 186, percentage: 37.8 },
  { range: "10–15ms", count: 148, percentage: 30.1 },
  { range: "15–25ms", count: 89,  percentage: 18.1 },
  { range: "25–50ms", count: 24,  percentage: 4.9 },
  { range: "50ms+",   count: 3,   percentage: 0.6 },
];

// ── Feedback Lessons ──────────────────────────────────────────────────────────

export interface LessonEntry {
  opponentId: string;
  lessonType: "placement_exploit" | "firing_dodge" | "strategy_effective" | "strategy_failed" | "timing_ok" | "timing_risk";
  summary: string;
  confidence: number;
  gain: number | null;
  gamesBasis: number;
  metricBefore: number | null;
  metricAfter: number | null;
}

export const lessons: LessonEntry[] = [
  { opponentId: "scout-01",   lessonType: "placement_exploit",   summary: "Fixed placement confirmed — exploit drops moves to ~17",                         confidence: 0.92, gain: 17,  gamesBasis: 3, metricBefore: 34, metricAfter: 17 },
  { opponentId: "scout-02",   lessonType: "firing_dodge",        summary: "Firing pattern locked — avoid 14 hot squares on placement",                      confidence: 0.88, gain: null, gamesBasis: 3, metricBefore: null, metricAfter: 14 },
  { opponentId: "warship-01", lessonType: "placement_exploit",   summary: "Fixed placement confirmed — exploit drops moves to ~24",                         confidence: 0.78, gain: 17,  gamesBasis: 2, metricBefore: 41, metricAfter: 24 },
  { opponentId: "warship-07", lessonType: "strategy_effective",  summary: "'hunt' saved 11 moves vs last game",                                            confidence: 0.72, gain: 11,  gamesBasis: 3, metricBefore: 52, metricAfter: 41 },
  { opponentId: "warship-09", lessonType: "strategy_effective",  summary: "'hunt' saved 12 moves vs last game",                                            confidence: 0.71, gain: 12,  gamesBasis: 2, metricBefore: 50, metricAfter: 38 },
  { opponentId: "warship-06", lessonType: "strategy_failed",     summary: "'probability' took 8 more moves — reconsider",                                  confidence: 0.65, gain: -8,  gamesBasis: 2, metricBefore: 50, metricAfter: 58 },
  { opponentId: "warship-08", lessonType: "strategy_failed",     summary: "'probability' took 12 more moves — reconsider",                                 confidence: 0.60, gain: -12, gamesBasis: 2, metricBefore: 50, metricAfter: 62 },
  { opponentId: "scout-03",   lessonType: "timing_ok",           summary: "Decision loop healthy at 9.1ms avg — well within timeout",                       confidence: 0.99, gain: null, gamesBasis: 3, metricBefore: null, metricAfter: 9.1 },
];
