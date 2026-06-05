import { NextRequest, NextResponse } from "next/server";
import path from "path";
import fs from "fs";
import { createClient } from "@supabase/supabase-js";

export const dynamic = "force-dynamic";

const supabaseUrl = process.env.NEXT_PUBLIC_SUPABASE_URL!;
const supabaseKey = process.env.NEXT_PUBLIC_SUPABASE_ANON_KEY!;
const supabase = createClient(supabaseUrl, supabaseKey);

const ENGINE_SERVER_URL = process.env.ENGINE_SERVER_URL || "http://localhost:5001";
const isLocal = ENGINE_SERVER_URL.includes("localhost");

// ── Types ────────────────────────────────────────────────────────────────────

interface GameRecord {
  gameNum: number;
  opponentId: string;
  won: boolean;
  moves: number;
  baselineMoves: number | null;
  chosenStrategy: string; // strategy selected by bandit at game start
  moveTimes: number[];
  shipsLost: number;
  hitsReceived: number;
  improvement: number | null;
  knownPlacement: boolean;
  knownFiring: boolean;
  trust: number;
  classification: string;
}

interface PatternRecord {
  opponentId: string;
  patternType: string;
  gamesConfirmed: number;
  detail: string;
}

interface MemoryRecord {
  opponentId: string;
  gamesPlayed: number;
  fixedPlacement: boolean;
  fixedFiring: boolean;
  winRate: number;
}

// ── Helpers ──────────────────────────────────────────────────────────────────

function parseStrategyReason(reason: string): { trust: number; classification: string } {
  // "bandit (trust=0.07 antiparity | stab=0.17 pa=0.41 games=62 place=30/30)"
  const m = reason.match(/trust=([0-9.]+)\s+(\w+)/);
  return {
    trust: m ? parseFloat(m[1]) : 0,
    classification: m ? m[2] : "unknown",
  };
}

async function fetchPreviousRun(battleId: string) {
  // Get the run for this battle
  const { data: thisRun } = await supabase
    .from("runs")
    .select("created_at")
    .eq("battle_id", battleId)
    .single();

  if (!thisRun) return null;

  // Get the most recent run BEFORE this one
  const { data: prevRun } = await supabase
    .from("runs")
    .select("*")
    .lt("created_at", thisRun.created_at)
    .order("created_at", { ascending: false })
    .limit(1)
    .single();

  return prevRun;
}

async function fetchRunScore(battleId: string): Promise<number | null> {
  const { data } = await supabase
    .from("runs")
    .select("total_score")
    .eq("battle_id", battleId)
    .single();
  return data?.total_score ?? null;
}

interface HistoricalRun {
  runLabel: string; // e.g. "Run #3"
  battleId: string;
  createdAt: string;
  winRate: number;
  avgMoves: number;
  gameWinRates: number[];  // cumulative win rate per game index
  gameMoves: number[];     // moves per game index
}

async function fetchHistoricalRuns(battleId: string, maxRuns: number = 15): Promise<HistoricalRun[]> {
  // Get the current run's created_at to find older runs
  const { data: thisRun } = await supabase
    .from("runs")
    .select("created_at")
    .eq("battle_id", battleId)
    .single();

  if (!thisRun) return [];

  // Fetch up to maxRuns previous runs (excluding current)
  const { data: prevRuns } = await supabase
    .from("runs")
    .select("id, battle_id, created_at, wins, losses, total_games, avg_moves")
    .lt("created_at", thisRun.created_at)
    .order("created_at", { ascending: false })
    .limit(maxRuns);

  if (!prevRuns || prevRuns.length === 0) return [];

  // Fetch games for all these runs in one query
  const runIds = prevRuns.map((r) => r.id);
  const { data: allGames } = await supabase
    .from("games")
    .select("run_id, won, moves")
    .in("run_id", runIds)
    .order("id", { ascending: true });

  // Group games by run_id
  const gamesByRun = new Map<number, { won: boolean; moves: number }[]>();
  for (const g of allGames ?? []) {
    const list = gamesByRun.get(g.run_id) || [];
    list.push({ won: g.won, moves: g.moves });
    gamesByRun.set(g.run_id, list);
  }

  // Build historical data (reverse so oldest = Run #1)
  const results: HistoricalRun[] = [];
  const reversed = [...prevRuns].reverse();

  for (let i = 0; i < reversed.length; i++) {
    const run = reversed[i];
    const games = gamesByRun.get(run.id) || [];
    const wr = run.total_games > 0 ? (run.wins / run.total_games) * 100 : 0;

    // Compute cumulative win rate per game
    let cumWins = 0;
    const gameWinRates = games.map((g, idx) => {
      if (g.won) cumWins++;
      return Number(((cumWins / (idx + 1)) * 100).toFixed(1));
    });

    const gameMoves = games.map((g) => g.moves);

    results.push({
      runLabel: `Run #${i + 1}`,
      battleId: run.battle_id,
      createdAt: run.created_at,
      winRate: Number(wr.toFixed(1)),
      avgMoves: run.avg_moves,
      gameWinRates,
      gameMoves,
    });
  }

  return results;
}

// ── Core JSONL parser ────────────────────────────────────────────────────────

function parseBattleLogContent(raw: string) {
  const lines = raw.split("\n").filter((l) => l.trim());

  const games: GameRecord[] = [];
  const patterns: PatternRecord[] = [];
  const memoryUpdates: Map<string, MemoryRecord> = new Map();
  const strategySwitches: { opponentId: string; from: string; to: string; reason: string }[] = [];
  let timeoutWarnings = 0;
  let errors = 0;

  // Current game being built
  let cur: {
    opponentId: string;
    chosenStrategy: string;
    strategyReason: string;
    knownPlacement: boolean;
    knownFiring: boolean;
    moveTimes: number[];
  } = { opponentId: "", chosenStrategy: "", strategyReason: "", knownPlacement: false, knownFiring: false, moveTimes: [] };

  for (const line of lines) {
    let parsed;
    try { parsed = JSON.parse(line); } catch { continue; }
    const { event, data } = parsed;

    switch (event) {
      case "game_started":
        cur = {
          opponentId: data.opponent_id,
          chosenStrategy: data.chosen_strategy,
          strategyReason: data.strategy_reason || "",
          knownPlacement: data.known_placement || false,
          knownFiring: data.known_firing || false,
          moveTimes: [],
        };
        break;

      case "move":
        cur.moveTimes.push(data.elapsed_ms);
        break;

      case "strategy_changed":
        strategySwitches.push({
          opponentId: data.opponent_id,
          from: data.from,
          to: data.to,
          reason: data.reason,
        });
        break;

      case "game_ended": {
        const { trust, classification } = parseStrategyReason(cur.strategyReason);
        games.push({
          gameNum: data.game_num,
          opponentId: data.opponent_id,
          won: data.won,
          moves: data.total_moves,
          baselineMoves: data.baseline_moves ?? null,
          chosenStrategy: cur.chosenStrategy,
          moveTimes: cur.moveTimes,
          shipsLost: data.ships_lost ?? 0,
          hitsReceived: data.hits_received ?? 0,
          improvement: data.improvement ?? null,
          knownPlacement: cur.knownPlacement,
          knownFiring: cur.knownFiring,
          trust,
          classification,
        });
        cur = { opponentId: "", chosenStrategy: "", strategyReason: "", knownPlacement: false, knownFiring: false, moveTimes: [] };
        break;
      }

      case "pattern_detected":
        patterns.push({
          opponentId: data.opponent_id,
          patternType: data.pattern_type,
          gamesConfirmed: data.games_confirmed,
          detail: data.detail,
        });
        break;

      case "memory_updated":
        memoryUpdates.set(data.opponent_id, {
          opponentId: data.opponent_id,
          gamesPlayed: data.games_played,
          fixedPlacement: data.fixed_placement,
          fixedFiring: data.fixed_firing,
          winRate: data.win_rate,
        });
        break;

      case "timeout_warning":
        timeoutWarnings++;
        break;

      case "error":
        errors++;
        break;
    }
  }

  return { games, patterns, memoryUpdates, strategySwitches, timeoutWarnings, errors };
}

// ── Route Handler ────────────────────────────────────────────────────────────

export async function GET(req: NextRequest) {
  const battleId = req.nextUrl.searchParams.get("id");

  if (!battleId || !/^[a-f0-9-]+$/i.test(battleId)) {
    return NextResponse.json({ error: "Invalid or missing id" }, { status: 400 });
  }

  let logContent: string | null = null;

  if (isLocal) {
    const engineDir = path.resolve(process.cwd(), "..");
    let logFile = path.join(engineDir, "data", "battles", `${battleId}.jsonl`);
    if (!fs.existsSync(logFile)) {
      logFile = path.join(engineDir, "data", "prod", "battles", `${battleId}.jsonl`);
    }
    if (fs.existsSync(logFile)) {
      logContent = fs.readFileSync(logFile, "utf-8");
    }
  } else {
    try {
      const res = await fetch(`${ENGINE_SERVER_URL}/engine/raw-log?id=${battleId}`);
      if (res.ok) {
        logContent = await res.text();
      }
    } catch {
      // Render backend unreachable — fall through to Supabase
    }
  }

  // Fallback: read raw log from Supabase if filesystem/Render didn't have it
  if (!logContent) {
    const { data: logRow } = await supabase
      .from("battle_logs")
      .select("raw_jsonl")
      .eq("battle_id", battleId)
      .single();
    if (logRow?.raw_jsonl) {
      logContent = logRow.raw_jsonl;
    }
  }

  if (!logContent) {
    return NextResponse.json({ error: "Log file not found" }, { status: 404 });
  }

  // Parse current + fetch Supabase data in parallel
  const current = parseBattleLogContent(logContent);
  const [serverScore, prevRun, historicalRuns] = await Promise.all([
    fetchRunScore(battleId),
    fetchPreviousRun(battleId),
    fetchHistoricalRuns(battleId, 15),
  ]);

  const { games, patterns, memoryUpdates, strategySwitches, timeoutWarnings, errors } = current;

  // ── Aggregates ─────────────────────────────────────────────────────────────

  const totalGames = games.length;
  const wins = games.filter((g) => g.won).length;
  const losses = totalGames - wins;
  const winRate = totalGames > 0 ? (wins / totalGames) * 100 : 0;

  const allMoveTimes = games.flatMap((g) => g.moveTimes);
  const avgLatencyMs = allMoveTimes.length > 0
    ? allMoveTimes.reduce((a, b) => a + b, 0) / allMoveTimes.length
    : 0;

  const avgMovesPerGame = totalGames > 0
    ? games.reduce((a, g) => a + g.moves, 0) / totalGames
    : 0;

  const totalMoveSavings = games.reduce(
    (a, g) => a + (g.improvement != null && g.improvement > 0 ? g.improvement : 0), 0,
  );

  // ── Patterns: only count actionable opponent patterns ──────────────────────
  // Exclude per-game noise like timing_ok and heatmap_prior
  const actionableTypes = new Set([
    "fixed_placement", "fixed_firing", "placement_exploit", "firing_dodge",
    "strategy_effective", "strategy_failed",
  ]);
  const actionablePatterns = patterns.filter((p) => actionableTypes.has(p.patternType));
  // Deduplicate by opponent + type
  const uniquePatternKeys = new Set(actionablePatterns.map((p) => `${p.opponentId}:${p.patternType}`));

  const fixedPlacementOpps = [...memoryUpdates.values()].filter((m) => m.fixedPlacement);
  const fixedFiringOpps = [...memoryUpdates.values()].filter((m) => m.fixedFiring);

  // ── Previous run deltas ────────────────────────────────────────────────────
  const prevWinRate = prevRun ? (prevRun.wins / Math.max(prevRun.total_games, 1)) * 100 : null;
  const winRateDelta = prevWinRate != null ? Number((winRate - prevWinRate).toFixed(1)) : 0;
  const prevScore = prevRun?.total_score ?? null;
  const scoreDelta = prevScore != null && serverScore != null ? serverScore - prevScore : 0;

  // ── KPIs ───────────────────────────────────────────────────────────────────

  const kpis = {
    totalGames,
    wins,
    losses,
    winRate: Number(winRate.toFixed(1)),
    winRateDelta,
    avgMovesPerGame: Number(avgMovesPerGame.toFixed(1)),
    avgMovesDelta: prevRun ? Number((avgMovesPerGame - prevRun.avg_moves).toFixed(1)) : 0,
    avgLatencyMs: Number(avgLatencyMs.toFixed(1)),
    latencyStatus: avgLatencyMs < 50 ? "healthy" : "warning",
    patternsDetected: uniquePatternKeys.size,
    patternBreakdown: {
      fixedPlacement: fixedPlacementOpps.length,
      fixedFiring: fixedFiringOpps.length,
    },
    totalScore: serverScore ?? 0,
    scoreDelta,
    strategySwitches: strategySwitches.length,
    timeoutWarnings,
    totalMoveSavings,
  };

  // ── Game Timeline (current + previous for comparison) ──────────────────────

  let cumulativeWins = 0;
  const gameTimeline = games.map((g, i) => {
    if (g.won) cumulativeWins++;
    const avgMs = g.moveTimes.length > 0
      ? g.moveTimes.reduce((a, b) => a + b, 0) / g.moveTimes.length
      : 0;
    return {
      game: i + 1,
      opponent: g.opponentId,
      won: g.won,
      moves: g.moves,
      baselineMoves: g.baselineMoves,
      strategy: g.chosenStrategy,
      avgLatencyMs: Number(avgMs.toFixed(1)),
      cumulativeWinRate: Number(((cumulativeWins / (i + 1)) * 100).toFixed(1)),
    };
  });

  // Historical runs already computed by fetchHistoricalRuns

  // ── Per-Opponent Stats ─────────────────────────────────────────────────────

  const oppMap = new Map<string, {
    games: number; wins: number; totalMoves: number; bestMoves: number;
    shipsLost: number; hitsReceived: number;
    chosenStrategies: string[];
    knownPlacement: boolean; knownFiring: boolean;
    trust: number; classification: string;
    improvements: number[];
  }>();

  for (const g of games) {
    const existing = oppMap.get(g.opponentId) || {
      games: 0, wins: 0, totalMoves: 0, bestMoves: Infinity,
      shipsLost: 0, hitsReceived: 0,
      chosenStrategies: [],
      knownPlacement: false, knownFiring: false,
      trust: 0, classification: "unknown",
      improvements: [],
    };
    existing.games++;
    if (g.won) existing.wins++;
    existing.totalMoves += g.moves;
    existing.bestMoves = Math.min(existing.bestMoves, g.moves);
    existing.shipsLost += g.shipsLost;
    existing.hitsReceived += g.hitsReceived;
    existing.chosenStrategies.push(g.chosenStrategy);
    if (g.knownPlacement) existing.knownPlacement = true;
    if (g.knownFiring) existing.knownFiring = true;
    existing.trust = g.trust;
    existing.classification = g.classification;
    if (g.improvement != null) existing.improvements.push(g.improvement);
    oppMap.set(g.opponentId, existing);
  }

  const perOpponentStats = [...oppMap.entries()]
    .sort((a, b) => {
      // Sort by win rate desc, then by avg moves asc
      const wrA = a[1].wins / Math.max(a[1].games, 1);
      const wrB = b[1].wins / Math.max(b[1].games, 1);
      if (wrB !== wrA) return wrB - wrA;
      return (a[1].totalMoves / a[1].games) - (b[1].totalMoves / b[1].games);
    })
    .map(([oppId, stats]) => {
      const mem = memoryUpdates.get(oppId);
      // Most common strategy
      const stratCounts: Record<string, number> = {};
      for (const s of stats.chosenStrategies) {
        stratCounts[s] = (stratCounts[s] || 0) + 1;
      }
      const strategyUsed = Object.entries(stratCounts).sort((a, b) => b[1] - a[1])[0]?.[0] || "probability";

      return {
        id: oppId,
        displayName: oppId,
        classification: stats.classification,
        gamesPlayed: stats.games,
        wins: stats.wins,
        losses: stats.games - stats.wins,
        winRate: stats.games > 0 ? stats.wins / stats.games : 0,
        avgMoves: Number((stats.totalMoves / Math.max(stats.games, 1)).toFixed(1)),
        bestMoves: stats.bestMoves === Infinity ? 0 : stats.bestMoves,
        avgShipsLost: Number((stats.shipsLost / Math.max(stats.games, 1)).toFixed(1)),
        trust: Number(stats.trust.toFixed(2)),
        fixedPlacement: mem?.fixedPlacement ?? stats.knownPlacement,
        fixedFiring: mem?.fixedFiring ?? stats.knownFiring,
        strategyUsed,
        exploitable: stats.trust >= 0.4,
      };
    });

  // ── Strategy Stats ─────────────────────────────────────────────────────────

  const stratMap = new Map<string, { games: number; wins: number; totalMoves: number }>();
  for (const g of games) {
    const existing = stratMap.get(g.chosenStrategy) || { games: 0, wins: 0, totalMoves: 0 };
    existing.games++;
    if (g.won) existing.wins++;
    existing.totalMoves += g.moves;
    stratMap.set(g.chosenStrategy, existing);
  }

  const strategyColors: Record<string, string> = {
    exploit: "#F26B21",
    hunt: "#F78E31",
    probability: "#FBB040",
  };

  const strategyStats = [...stratMap.entries()]
    .sort((a, b) => b[1].games - a[1].games)
    .map(([strat, stats]) => ({
      strategy: strat,
      gamesPlayed: stats.games,
      wins: stats.wins,
      losses: stats.games - stats.wins,
      winRate: Number(((stats.wins / Math.max(stats.games, 1)) * 100).toFixed(1)),
      avgMoves: Number((stats.totalMoves / Math.max(stats.games, 1)).toFixed(1)),
      color: strategyColors[strat] || "#a1a1aa",
    }));

  // ── Latency Distribution ───────────────────────────────────────────────────

  const buckets = [
    { range: "0–5ms", min: 0, max: 5 },
    { range: "5–10ms", min: 5, max: 10 },
    { range: "10–15ms", min: 10, max: 15 },
    { range: "15–25ms", min: 15, max: 25 },
    { range: "25–50ms", min: 25, max: 50 },
    { range: "50ms+", min: 50, max: Infinity },
  ];

  const latencyDistribution = buckets.map((bucket) => {
    const count = allMoveTimes.filter((t) => t >= bucket.min && t < bucket.max).length;
    return {
      range: bucket.range,
      count,
      percentage: Number(((count / Math.max(allMoveTimes.length, 1)) * 100).toFixed(1)),
    };
  });

  // ── Lessons: use actual engine pattern_detected events + derived insights ──

  const lessons: Array<{
    opponentId: string;
    lessonType: string;
    summary: string;
    confidence: number;
    gain: number | null;
    gamesBasis: number;
  }> = [];

  // 1. Real engine-generated lessons (placement_exploit, firing_dodge, strategy_*)
  //    Map raw pattern types to lesson types, then deduplicate by opponent + lessonType
  const lessonTypeMap: Record<string, string> = {
    placement_exploit: "placement_exploit",
    firing_dodge: "firing_dodge",
    fixed_placement: "placement_exploit",
    fixed_firing: "firing_dodge",
    strategy_effective: "strategy_effective",
    strategy_failed: "strategy_failed",
  };

  // Deduplicate: keep the pattern with most games_confirmed per opponent+lessonType
  const seenLessons = new Map<string, PatternRecord>();
  for (const p of actionablePatterns) {
    const lt = lessonTypeMap[p.patternType] || p.patternType;
    const key = `${p.opponentId}:${lt}`;
    const existing = seenLessons.get(key);
    if (!existing || p.gamesConfirmed > existing.gamesConfirmed) {
      seenLessons.set(key, p);
    }
  }

  for (const [key, p] of seenLessons.entries()) {
    const lt = key.split(":")[1];
    const oppStats = oppMap.get(p.opponentId);
    const improvement = oppStats?.improvements?.[0] ?? null;

    lessons.push({
      opponentId: p.opponentId,
      lessonType: lt,
      summary: p.detail,
      confidence: Math.min(0.5 + (p.gamesConfirmed / 100), 0.98),
      gain: lt === "placement_exploit" && improvement != null && improvement > 0 ? improvement : null,
      gamesBasis: p.gamesConfirmed,
    });
  }

  // 2. Strategy-level insights (across all opponents)
  for (const [strat, stats] of stratMap.entries()) {
    if (stats.games >= 2) {
      const wr = stats.wins / stats.games;
      const avgM = stats.totalMoves / stats.games;
      if (wr >= 0.8) {
        lessons.push({
          opponentId: "global",
          lessonType: "strategy_effective",
          summary: `'${strat}' wins ${(wr * 100).toFixed(0)}% with ${avgM.toFixed(0)} avg moves across ${stats.games} games`,
          confidence: Math.min(0.5 + stats.games * 0.04, 0.92),
          gain: null,
          gamesBasis: stats.games,
        });
      } else if (wr <= 0.3) {
        lessons.push({
          opponentId: "global",
          lessonType: "strategy_failed",
          summary: `'${strat}' wins only ${(wr * 100).toFixed(0)}% across ${stats.games} games — reconsider`,
          confidence: Math.min(0.5 + stats.games * 0.04, 0.92),
          gain: null,
          gamesBasis: stats.games,
        });
      }
    }
  }

  // 3. Per-opponent move improvement insights (only for opponents with 2+ games)
  for (const [oppId, stats] of oppMap.entries()) {
    if (stats.improvements.length > 0 && stats.games >= 2) {
      const totalImprovement = stats.improvements.reduce((a, b) => a + b, 0);
      const alreadyCovered = seenLessons.has(`${oppId}:placement_exploit`);
      if (totalImprovement > 10 && !alreadyCovered) {
        lessons.push({
          opponentId: oppId,
          lessonType: "strategy_effective",
          summary: `Saved ${totalImprovement} moves vs baseline across ${stats.games} games`,
          confidence: Math.min(0.5 + stats.games * 0.08, 0.9),
          gain: totalImprovement,
          gamesBasis: stats.games,
        });
      } else if (totalImprovement < -10) {
        lessons.push({
          opponentId: oppId,
          lessonType: "strategy_failed",
          summary: `Took ${Math.abs(totalImprovement)} more moves than baseline — opponent may have adapted`,
          confidence: Math.min(0.5 + stats.games * 0.08, 0.9),
          gain: totalImprovement,
          gamesBasis: stats.games,
        });
      }
    }
  }

  // 4. Timing insight
  if (timeoutWarnings === 0 && allMoveTimes.length > 0) {
    lessons.push({
      opponentId: "global",
      lessonType: "timing_ok",
      summary: `Decision loop healthy at ${avgLatencyMs.toFixed(1)}ms avg — well within budget`,
      confidence: 0.99,
      gain: null,
      gamesBasis: totalGames,
    });
  } else if (timeoutWarnings > 0) {
    lessons.push({
      opponentId: "global",
      lessonType: "timing_risk",
      summary: `${timeoutWarnings} timeout warnings — review slow decision turns`,
      confidence: 0.85,
      gain: null,
      gamesBasis: totalGames,
    });
  }

  // Sort lessons: exploits first, then effective, then failed, then timing
  const lessonOrder: Record<string, number> = {
    placement_exploit: 0, firing_dodge: 1, strategy_effective: 2,
    strategy_failed: 3, timing_risk: 4, timing_ok: 5,
  };
  lessons.sort((a, b) => (lessonOrder[a.lessonType] ?? 9) - (lessonOrder[b.lessonType] ?? 9));

  return NextResponse.json({
    kpis,
    gameTimeline,
    historicalRuns,
    strategyStats,
    latencyDistribution,
    perOpponentStats,
    lessons,
  });
}
