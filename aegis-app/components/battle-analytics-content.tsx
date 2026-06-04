"use client";

import { useEffect, useState } from "react";
import dynamic from "next/dynamic";
import {
  RiTrophyFill,
  RiFocus2Fill,
  RiTimerFill,
  RiBrainFill,
  RiBarChartFill,
  RiArrowUpSLine,
  RiArrowDownSLine,
  RiShieldFill,
} from "@remixicon/react";
import { cn } from "@/lib/utils";
import { Badge } from "@/components/ui/badge";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import type { ApexOptions } from "apexcharts";

// Dynamically import ApexCharts (SSR-incompatible)
const Chart = dynamic(() => import("react-apexcharts"), { ssr: false });

// ── Types ────────────────────────────────────────────────────────────────────

interface KPIs {
  totalGames: number;
  wins: number;
  losses: number;
  winRate: number;
  winRateDelta: number;
  avgMovesPerGame: number;
  avgMovesDelta: number;
  avgLatencyMs: number;
  latencyStatus: string;
  patternsDetected: number;
  patternBreakdown: { fixedPlacement: number; fixedFiring: number };
  totalScore: number;
  scoreDelta: number;
  strategySwitches: number;
  timeoutWarnings: number;
  totalMoveSavings: number;
}

interface GameTimelineEntry {
  game: number;
  opponent: string;
  won: boolean;
  moves: number;
  baselineMoves: number | null;
  strategy: string;
  avgLatencyMs: number;
  cumulativeWinRate: number;
}

interface StrategyStats {
  strategy: string;
  gamesPlayed: number;
  wins: number;
  losses: number;
  winRate: number;
  avgMoves: number;
  color: string;
}

interface LatencyBucket {
  range: string;
  count: number;
  percentage: number;
}

interface OpponentStat {
  id: string;
  displayName: string;
  classification: string;
  gamesPlayed: number;
  wins: number;
  losses: number;
  winRate: number;
  avgMoves: number;
  bestMoves: number;
  avgShipsLost: number;
  trust: number;
  fixedPlacement: boolean;
  fixedFiring: boolean;
  strategyUsed: string;
  exploitable: boolean;
}

interface LessonEntry {
  opponentId: string;
  lessonType: string;
  summary: string;
  confidence: number;
  gain: number | null;
  gamesBasis: number;
}

interface HistoricalRun {
  runLabel: string;
  battleId: string;
  createdAt: string;
  winRate: number;
  avgMoves: number;
  gameWinRates: number[];
  gameMoves: number[];
}

interface AnalyticsData {
  kpis: KPIs;
  gameTimeline: GameTimelineEntry[];
  historicalRuns: HistoricalRun[];
  strategyStats: StrategyStats[];
  latencyDistribution: LatencyBucket[];
  perOpponentStats: OpponentStat[];
  lessons: LessonEntry[];
}

// ── Palette ──────────────────────────────────────────────────────────────────

const P = {
  100: "#F26B21",
  200: "#F78E31",
  300: "#FBB040",
  400: "#FCEC52",
  500: "#CBDB47",
  600: "#99CA3C",
  700: "#208B3A",
} as const;

// ── Shared ApexChart Theme ───────────────────────────────────────────────────

const APEX_DARK_THEME: ApexOptions = {
  chart: {
    background: "transparent",
    foreColor: "#a1a1aa",
    fontFamily: "var(--font-sans), system-ui, sans-serif",
    toolbar: { show: false },
    zoom: { enabled: false },
  },
  grid: {
    borderColor: "rgba(255,255,255,0.06)",
    strokeDashArray: 4,
  },
  tooltip: {
    theme: "dark",
    style: { fontSize: "12px" },
  },
};

function mergeOptions(options: ApexOptions): ApexOptions {
  return {
    ...APEX_DARK_THEME,
    ...options,
    chart: { ...APEX_DARK_THEME.chart, ...options.chart },
    grid: { ...APEX_DARK_THEME.grid, ...options.grid },
    tooltip: { ...APEX_DARK_THEME.tooltip, ...options.tooltip },
  };
}

// ── KPI Card ─────────────────────────────────────────────────────────────────

function KPICard({
  icon: Icon,
  label,
  value,
  delta,
  deltaLabel,
  positive,
  arrowUp,
}: {
  icon: React.ComponentType<{ className?: string }>;
  label: string;
  value: string;
  delta?: string;
  deltaLabel?: string;
  positive?: boolean;
  arrowUp?: boolean;
}) {
  // Arrow direction defaults to match positive (up=good, down=bad)
  // but can be overridden via arrowUp prop
  const showUp = arrowUp ?? positive;
  const color = positive === true ? "text-green-500" : positive === false ? "text-rose-400" : "text-muted-foreground";

  return (
    <div className="relative overflow-hidden rounded-2xl border border-border bg-card p-5 shadow-xs transition-all duration-300 hover:scale-[1.02] hover:shadow-md">
      <div className="flex items-start justify-between">
        <div className="flex flex-col gap-1">
          <span className="text-[11px] font-semibold uppercase tracking-wider text-muted-foreground">
            {label}
          </span>
          <span className="text-3xl font-bold tracking-tight text-card-foreground">
            {value}
          </span>
        </div>
        <div className="flex h-10 w-10 items-center justify-center rounded-xl bg-muted text-muted-foreground">
          <Icon className="size-5" />
        </div>
      </div>
      {delta && (
        <div className="mt-3 flex items-center gap-1.5">
          {showUp === true && <RiArrowUpSLine className={cn("size-3.5", color)} />}
          {showUp === false && <RiArrowDownSLine className={cn("size-3.5", color)} />}
          <span className={cn("text-xs font-semibold", color)}>
            {delta}
          </span>
          {deltaLabel && (
            <span className="text-[11px] text-muted-foreground">{deltaLabel}</span>
          )}
        </div>
      )}
    </div>
  );
}

// ── Lesson Type Badge ────────────────────────────────────────────────────────

const lessonTypeConfig: Record<string, { label: string; text: string }> = {
  placement_exploit: { label: "EXPLOIT", text: P[100] },
  firing_dodge: { label: "DODGE", text: P[300] },
  strategy_effective: { label: "EFFECTIVE", text: P[700] },
  strategy_failed: { label: "FAILED", text: "#f43f5e" },
  timing_ok: { label: "TIMING OK", text: "#a1a1aa" },
  timing_risk: { label: "TIMING RISK", text: P[400] },
};

// ── Chart Section Wrapper ────────────────────────────────────────────────────

function ChartSection({
  title,
  subtitle,
  children,
  className,
}: {
  title: string;
  subtitle?: string;
  children: React.ReactNode;
  className?: string;
}) {
  return (
    <div
      className={cn(
        "rounded-2xl border border-white/8 bg-zinc-900/60 p-6 backdrop-blur",
        className,
      )}
    >
      <div className="mb-5">
        <h3 className="text-base font-semibold text-zinc-100">{title}</h3>
        {subtitle && <p className="mt-0.5 text-xs text-zinc-400">{subtitle}</p>}
      </div>
      {children}
    </div>
  );
}

// ── Main Content Component ───────────────────────────────────────────────────

export function BattleAnalyticsContent({ battleId }: { battleId: string }) {
  const [data, setData] = useState<AnalyticsData | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    setLoading(true);
    setError(null);
    fetch(`/api/battle/analytics?id=${battleId}`)
      .then((res) => {
        if (!res.ok) throw new Error(`Failed to load analytics (${res.status})`);
        return res.json();
      })
      .then((d) => {
        setData(d);
        setLoading(false);
      })
      .catch((err) => {
        setError(err.message);
        setLoading(false);
      });
  }, [battleId]);

  if (loading) {
    return (
      <div className="flex h-64 w-full items-center justify-center">
        <div
          className="h-8 w-8 animate-spin rounded-full border-2 border-zinc-700"
          style={{ borderTopColor: P[200] }}
        />
      </div>
    );
  }

  if (error || !data) {
    return (
      <div className="flex h-64 w-full items-center justify-center text-zinc-500">
        {error || "No data available"}
      </div>
    );
  }

  return <AnalyticsCharts {...data} />;
}

function AnalyticsCharts({
  kpis,
  gameTimeline,
  historicalRuns,
  strategyStats,
  latencyDistribution,
  perOpponentStats,
  lessons,
}: AnalyticsData) {
  const [mounted, setMounted] = useState(false);
  useEffect(() => setMounted(true), []);

  // ── 1. Cumulative Win Rate Area Chart (with historical overlays) ─────────
  const hasHistory = historicalRuns.length > 0;
  // Historical line colors: fade from zinc-500 (most recent) to zinc-800 (oldest)
  const histColors = historicalRuns.map((_, i) => {
    const t = historicalRuns.length === 1 ? 0.4 : 0.2 + (i / (historicalRuns.length - 1)) * 0.4;
    const v = Math.round(80 + t * 80); // 80..160 → #50..#a0
    const hex = v.toString(16).padStart(2, "0");
    return `#${hex}${hex}${hex}`;
  });

  const winRateOptions = mergeOptions({
    chart: { type: "line", height: 300 },
    stroke: {
      curve: "smooth",
      width: [3, ...historicalRuns.map(() => 1.5)],
      dashArray: [0, ...historicalRuns.map(() => 4)],
    },
    colors: [P[700], ...histColors],
    fill: {
      type: ["gradient", ...historicalRuns.map(() => "none")],
      gradient: {
        shadeIntensity: 1,
        opacityFrom: 0.3,
        opacityTo: 0.02,
        stops: [0, 100],
        colorStops: [
          { offset: 0, color: P[700], opacity: 0.3 },
          { offset: 100, color: P[700], opacity: 0.02 },
        ],
      },
    },
    xaxis: {
      categories: gameTimeline.map((g) => `G${g.game}`),
      labels: { style: { colors: "#71717a", fontSize: "11px" } },
      axisBorder: { show: false },
      axisTicks: { show: false },
    },
    yaxis: {
      min: 0,
      max: 100,
      labels: {
        style: { colors: "#71717a", fontSize: "11px" },
        formatter: (v: number) => `${v}%`,
      },
    },
    markers: {
      size: [4, ...historicalRuns.map(() => 0)],
      colors: [P[700]],
      strokeColors: "#171717",
      strokeWidth: 2,
      hover: { size: 6 },
    },
    legend: {
      show: hasHistory,
      position: "top" as const,
      horizontalAlign: "right" as const,
      labels: { colors: "#a1a1aa" },
      markers: { size: 4, offsetX: -2 },
      fontSize: "11px",
    },
    dataLabels: { enabled: false },
    tooltip: {
      shared: true,
      intersect: false,
      y: { formatter: (v: number) => v != null ? `${v.toFixed(1)}%` : "—" },
    },
  });
  const winRateSeries = [
    {
      name: "Current",
      type: "area",
      data: gameTimeline.map((g) => g.cumulativeWinRate),
    },
    ...historicalRuns.map((run) => ({
      name: run.runLabel,
      type: "line" as const,
      data: run.gameWinRates,
    })),
  ];

  // ── 2. Move Efficiency Timeline (with historical overlays) ──────────────
  const moveEffOptions = mergeOptions({
    chart: { type: "line", height: 300 },
    stroke: {
      width: [3, 2, ...historicalRuns.map(() => 1.5)],
      curve: "smooth" as const,
      dashArray: [0, 6, ...historicalRuns.map(() => 4)],
    },
    colors: [P[700], "#52525b", ...histColors],
    xaxis: {
      categories: gameTimeline.map((g) => `G${g.game}`),
      labels: { style: { colors: "#71717a", fontSize: "11px" } },
      axisBorder: { show: false },
      axisTicks: { show: false },
    },
    yaxis: {
      labels: {
        style: { colors: "#71717a", fontSize: "11px" },
        formatter: (v: number) => `${v}`,
      },
    },
    markers: {
      size: [4, 0, ...historicalRuns.map(() => 0)],
      colors: [P[700], "#52525b"],
      strokeColors: "#171717",
      strokeWidth: 2,
    },
    legend: {
      show: true,
      position: "top" as const,
      horizontalAlign: "right" as const,
      labels: { colors: "#a1a1aa" },
      markers: { size: 4, offsetX: -2 },
      fontSize: "11px",
    },
    dataLabels: { enabled: false },
    tooltip: {
      shared: true,
      intersect: false,
    },
  });
  const moveEffSeries = [
    { name: "Actual Moves", data: gameTimeline.map((g) => g.moves) },
    { name: "Baseline", data: gameTimeline.map((g) => g.baselineMoves ?? 0) },
    ...historicalRuns.map((run) => ({
      name: run.runLabel,
      data: run.gameMoves,
    })),
  ];

  // ── 3. Per-Opponent Win Rate Bar Chart ────────────────────────────────────
  const opponentBarOptions = mergeOptions({
    chart: { type: "bar", height: Math.max(280, perOpponentStats.length * 28) },
    plotOptions: {
      bar: {
        horizontal: true,
        barHeight: "55%",
        borderRadius: 6,
        borderRadiusApplication: "end" as const,
        distributed: true,
      },
    },
    colors: perOpponentStats.map((o) =>
      o.fixedPlacement && o.fixedFiring ? P[100] : P[300],
    ),
    xaxis: {
      min: 0,
      max: 100,
      labels: {
        style: { colors: "#71717a", fontSize: "11px" },
        formatter: (v: number) => `${v}%`,
      },
    },
    yaxis: {
      labels: { style: { colors: "#a1a1aa", fontSize: "11px" } },
    },
    dataLabels: {
      enabled: true,
      formatter: (v: number) => `${v}%`,
      style: { colors: ["#fff"], fontSize: "11px", fontWeight: "700" },
      offsetX: 8,
    },
    legend: { show: false },
    tooltip: {
      y: { formatter: (v: number) => `${v}%` },
    },
  });
  const opponentBarSeries = [
    {
      name: "Win Rate",
      data: perOpponentStats.map((o) => ({
        x: o.displayName,
        y: Math.round(o.winRate * 100),
      })),
    },
  ];

  // ── 4. Strategy Radar Chart ───────────────────────────────────────────────
  const radarOptions = mergeOptions({
    chart: { type: "radar", height: 320 },
    stroke: { width: 2 },
    fill: { opacity: 0.15 },
    colors: strategyStats.map((s) => s.color),
    xaxis: {
      categories: ["Win Rate", "Efficiency", "Games Played", "Consistency"],
      labels: { style: { colors: "#a1a1aa", fontSize: "11px" } },
    },
    yaxis: { show: false },
    markers: { size: 3, strokeWidth: 1 },
    legend: {
      show: true,
      position: "bottom" as const,
      labels: { colors: "#a1a1aa" },
      markers: { size: 4, offsetX: -2 },
      fontSize: "11px",
    },
    plotOptions: {
      radar: {
        polygons: {
          strokeColors: "rgba(255,255,255,0.06)",
          connectorColors: "rgba(255,255,255,0.06)",
          fill: { colors: ["rgba(255,255,255,0.02)", "transparent"] },
        },
      },
    },
  });
  const maxGames = Math.max(...strategyStats.map((s) => s.gamesPlayed), 1);
  const radarSeries = strategyStats.map((s) => ({
    name: s.strategy.charAt(0).toUpperCase() + s.strategy.slice(1),
    data: [
      s.winRate,
      Math.max(0, 100 - s.avgMoves),
      (s.gamesPlayed / maxGames) * 100,
      s.winRate,
    ],
  }));

  // ── 5. Latency Histogram ──────────────────────────────────────────────────
  const shadePool = ["#FDDCB5", "#FBB040", "#F78E31", "#F26B21", "#D45A1A", "#B34A14"];
  const counts = latencyDistribution.map((b) => b.count);
  const minC = Math.min(...counts);
  const maxC = Math.max(...counts);
  const latencyColors = counts.map((c) => {
    const t = maxC === minC ? 0.5 : (c - minC) / (maxC - minC);
    const idx = Math.round(t * (shadePool.length - 1));
    return shadePool[idx];
  });
  const latencyOptions = mergeOptions({
    chart: { type: "bar", height: 260 },
    plotOptions: {
      bar: {
        columnWidth: "60%",
        borderRadius: 6,
        borderRadiusApplication: "end" as const,
        distributed: true,
      },
    },
    colors: latencyColors,
    xaxis: {
      categories: latencyDistribution.map((b) => b.range),
      labels: { style: { colors: "#71717a", fontSize: "11px" } },
      axisBorder: { show: false },
      axisTicks: { show: false },
    },
    yaxis: {
      labels: { style: { colors: "#71717a", fontSize: "11px" } },
    },
    legend: { show: false },
    dataLabels: {
      enabled: true,
      formatter: (v: number) => `${v}`,
      style: { colors: ["#fff"], fontSize: "10px", fontWeight: "600" },
      offsetY: -6,
    },
    tooltip: {
      y: { formatter: (v: number) => `${v} shots` },
    },
  });
  const latencySeries = [
    { name: "Shots", data: latencyDistribution.map((b) => b.count) },
  ];

  // ── 6. Strategy Donut ─────────────────────────────────────────────────────
  const donutOptions = mergeOptions({
    chart: { type: "donut", height: 260 },
    labels: strategyStats.map(
      (s) => s.strategy.charAt(0).toUpperCase() + s.strategy.slice(1),
    ),
    colors: strategyStats.map((s) => s.color),
    stroke: { width: 0 },
    plotOptions: {
      pie: {
        donut: {
          size: "72%",
          labels: {
            show: true,
            name: {
              show: true,
              fontSize: "13px",
              color: "#a1a1aa",
              offsetY: -4,
            },
            value: {
              show: true,
              fontSize: "22px",
              fontWeight: "700",
              color: "#fafafa",
              offsetY: 4,
              formatter: (v: string) => `${v}`,
            },
            total: {
              show: true,
              label: "Total Games",
              fontSize: "11px",
              color: "#71717a",
              formatter: () => `${kpis.totalGames}`,
            },
          },
        },
      },
    },
    legend: {
      show: true,
      position: "bottom" as const,
      labels: { colors: "#a1a1aa" },
      markers: { size: 4, offsetX: -2 },
      fontSize: "11px",
    },
    dataLabels: { enabled: false },
  });
  const donutSeries = strategyStats.map((s) => s.gamesPlayed);

  if (!mounted) {
    return (
      <div className="flex h-64 w-full items-center justify-center">
        <div
          className="h-8 w-8 animate-spin rounded-full border-2 border-zinc-700"
          style={{ borderTopColor: P[200] }}
        />
      </div>
    );
  }

  return (
    <div className="flex flex-col gap-6 pb-8">
      {/* ── Hero KPI Cards ─────────────────────────────────────────────── */}
      <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 xl:grid-cols-5">
        <KPICard
          icon={RiTrophyFill}
          label="Win Rate"
          value={`${kpis.winRate}%`}
          delta={kpis.winRateDelta !== 0 ? `${kpis.winRateDelta > 0 ? "+" : ""}${kpis.winRateDelta}%` : `${kpis.wins}W / ${kpis.losses}L`}
          deltaLabel={kpis.winRateDelta !== 0 ? "vs prev run" : `of ${kpis.totalGames} games`}
          positive={kpis.winRateDelta !== 0 ? kpis.winRateDelta > 0 : kpis.winRate >= 50}
        />
        <KPICard
          icon={RiFocus2Fill}
          label="Avg Moves / Game"
          value={`${kpis.avgMovesPerGame}`}
          delta={kpis.avgMovesDelta !== 0 ? `${Math.abs(kpis.avgMovesDelta)} ${kpis.avgMovesDelta < 0 ? "fewer" : "more"}` : kpis.totalMoveSavings > 0 ? `${kpis.totalMoveSavings} saved` : undefined}
          deltaLabel={kpis.avgMovesDelta !== 0 ? "vs prev run" : "vs baseline"}
          positive={kpis.avgMovesDelta !== 0 ? kpis.avgMovesDelta < 0 : kpis.totalMoveSavings > 0}
          arrowUp={kpis.avgMovesDelta !== 0 ? kpis.avgMovesDelta > 0 : undefined}
        />
        <KPICard
          icon={RiTimerFill}
          label="Avg Latency"
          value={`${kpis.avgLatencyMs}ms`}
          delta={kpis.latencyStatus === "healthy" ? "Healthy" : "Warning"}
          deltaLabel="within budget"
          positive={kpis.latencyStatus === "healthy"}
        />
        <KPICard
          icon={RiBrainFill}
          label="Patterns Found"
          value={`${kpis.patternsDetected}`}
          delta={`${kpis.patternBreakdown.fixedPlacement} placement, ${kpis.patternBreakdown.fixedFiring} firing`}
        />
        <KPICard
          icon={RiBarChartFill}
          label="Total Score"
          value={`${kpis.totalScore}`}
          delta={kpis.scoreDelta !== 0 ? `${kpis.scoreDelta > 0 ? "+" : ""}${kpis.scoreDelta}` : undefined}
          deltaLabel={kpis.scoreDelta !== 0 ? "vs prev best" : undefined}
          positive={kpis.scoreDelta > 0}
        />
      </div>

      {/* ── Row 2: Win Rate + Move Efficiency ──────────────────────────── */}
      <div className="grid grid-cols-1 gap-5 lg:grid-cols-2">
        <ChartSection
          title="Cumulative Win Rate"
          subtitle={`Win rate progression across all ${kpis.totalGames} games`}
        >
          <Chart
            options={winRateOptions}
            series={winRateSeries}
            type="area"
            height={300}
          />
        </ChartSection>

        <ChartSection
          title="Move Efficiency"
          subtitle="Actual moves vs baseline — lower is better"
        >
          <Chart
            options={moveEffOptions}
            series={moveEffSeries}
            type="line"
            height={300}
          />
        </ChartSection>
      </div>

      {/* ── Row 3: Strategy Radar + Donut + Latency ────────────────────── */}
      <div className="grid grid-cols-1 gap-5 lg:grid-cols-3">
        <ChartSection
          title="Strategy Comparison"
          subtitle="Thompson Bandit — learned arm performance"
        >
          <Chart
            options={radarOptions}
            series={radarSeries}
            type="radar"
            height={320}
          />
        </ChartSection>

        <ChartSection
          title="Strategy Distribution"
          subtitle="Games played per strategy"
        >
          <Chart
            options={donutOptions}
            series={donutSeries}
            type="donut"
            height={260}
          />
          <div className="mt-4 grid grid-cols-3 gap-2">
            {strategyStats.map((s) => (
              <div
                key={s.strategy}
                className="flex flex-col items-center rounded-xl bg-white/[0.03] p-2.5"
              >
                <span className="text-[10px] font-semibold uppercase tracking-wider text-zinc-400">
                  {s.strategy}
                </span>
                <span className="text-lg font-bold" style={{ color: s.color }}>
                  {s.winRate}%
                </span>
                <span className="text-[10px] text-zinc-500">
                  {s.wins}W / {s.losses}L
                </span>
              </div>
            ))}
          </div>
        </ChartSection>

        <ChartSection
          title="Latency Distribution"
          subtitle="Decision time per shot across all games"
        >
          <Chart
            options={latencyOptions}
            series={latencySeries}
            type="bar"
            height={260}
          />
        </ChartSection>
      </div>

      {/* ── Opponent Intelligence Table ──────────────────────────────────── */}
      <div className="flex w-full flex-col gap-4">
        <div className="px-1">
          <h3 className="text-base font-semibold text-foreground">Opponent Intelligence</h3>
          <p className="mt-0.5 text-xs text-muted-foreground">
            Detailed stats and detected patterns per opponent
          </p>
        </div>
        <div className="overflow-hidden rounded-lg border">
          <Table>
            <TableHeader className="bg-muted">
              <TableRow>
                <TableHead>Opponent</TableHead>
                <TableHead>Class</TableHead>
                <TableHead className="text-center">W / L</TableHead>
                <TableHead className="text-center">Win Rate</TableHead>
                <TableHead className="text-center">Avg Moves</TableHead>
                <TableHead className="text-center">Trust</TableHead>
                <TableHead className="text-center">Strategy</TableHead>
                <TableHead>Intel</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {perOpponentStats.map((opp) => (
                <TableRow key={opp.id}>
                  <TableCell className="font-medium font-mono text-xs">
                    {opp.displayName}
                  </TableCell>
                  <TableCell>
                    <Badge variant="outline" className="px-1.5 text-muted-foreground text-[10px]">
                      {opp.classification}
                    </Badge>
                  </TableCell>
                  <TableCell className="text-center">
                    {opp.wins} / {opp.losses}
                  </TableCell>
                  <TableCell className="text-center">
                    <span
                      className="font-semibold"
                      style={{
                        color:
                          opp.winRate >= 0.7
                            ? "var(--color-green-500)"
                            : opp.winRate >= 0.4
                            ? P[300]
                            : "#f43f5e",
                      }}
                    >
                      {Math.round(opp.winRate * 100)}%
                    </span>
                  </TableCell>
                  <TableCell className="text-center font-mono">
                    {opp.avgMoves}
                  </TableCell>
                  <TableCell className="text-center">
                    <span
                      className="font-mono text-xs"
                      style={{
                        color: opp.trust >= 0.4 ? P[700] : opp.trust >= 0.15 ? P[300] : "#71717a",
                      }}
                    >
                      {opp.trust.toFixed(2)}
                    </span>
                  </TableCell>
                  <TableCell className="text-center">
                    <Badge variant="outline" className="px-1.5 text-muted-foreground">
                      {opp.strategyUsed}
                    </Badge>
                  </TableCell>
                  <TableCell>
                    <div className="flex gap-1 flex-wrap">
                      {opp.exploitable && (
                        <Badge variant="outline" className="gap-0.5 px-1.5 text-emerald-500 border-emerald-500/30 text-[10px]">
                          EXPLOITABLE
                        </Badge>
                      )}
                      {opp.fixedPlacement && (
                        <Badge variant="outline" className="gap-0.5 px-1.5 text-muted-foreground text-[10px]">
                          <RiShieldFill className="size-2.5" />
                          FIXED-PLACE
                        </Badge>
                      )}
                      {opp.fixedFiring && (
                        <Badge variant="outline" className="gap-0.5 px-1.5 text-muted-foreground text-[10px]">
                          <RiFocus2Fill className="size-2.5" />
                          FIXED-FIRE
                        </Badge>
                      )}
                      {!opp.fixedPlacement && !opp.fixedFiring && !opp.exploitable && (
                        <span className="text-[10px] text-muted-foreground">—</span>
                      )}
                    </div>
                  </TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        </div>
      </div>

      {/* ── Agent Feedback Loop ────────────────────────────────────────── */}
      {lessons.length > 0 && (
        <div className="flex w-full flex-col gap-4">
          <div className="px-1">
            <h3 className="text-base font-semibold text-foreground">Agent Feedback Loop</h3>
            <p className="mt-0.5 text-xs text-muted-foreground">
              Lessons learned during this battle — influences next run
            </p>
          </div>
          <div className="grid gap-3 sm:grid-cols-2">
            {lessons.map((lesson, i) => {
              const config = lessonTypeConfig[lesson.lessonType] || lessonTypeConfig.timing_ok;
              return (
                <div
                  key={i}
                  className="flex flex-col gap-3 rounded-lg border border-border bg-card p-4 shadow-xs transition-colors hover:bg-muted/50"
                >
                  <div className="flex items-center justify-between">
                    <Badge variant="outline" className="px-1.5 text-muted-foreground">
                      {config.label}
                    </Badge>
                    <span className="text-[10px] text-muted-foreground font-mono">
                      {lesson.opponentId}
                    </span>
                  </div>
                  <p className="text-sm text-foreground leading-relaxed">
                    {lesson.summary}
                  </p>
                  <div className="flex items-center gap-4">
                    <div className="flex flex-1 items-center gap-2">
                      <span className="text-[10px] text-muted-foreground">Confidence</span>
                      <div className="flex-1 h-1.5 rounded-full bg-muted overflow-hidden">
                        <div
                          className="h-full rounded-full bg-foreground/20 transition-all duration-500"
                          style={{ width: `${lesson.confidence * 100}%` }}
                        />
                      </div>
                      <span className="text-[10px] font-mono text-muted-foreground">
                        {(lesson.confidence * 100).toFixed(0)}%
                      </span>
                    </div>
                    {lesson.gain !== null && (
                      <div className="flex items-center gap-1">
                        {lesson.gain > 0 ? (
                          <RiArrowUpSLine className="size-3 text-green-500" />
                        ) : (
                          <RiArrowDownSLine className="size-3 text-rose-400" />
                        )}
                        <span
                          className={cn(
                            "text-[11px] font-semibold",
                            lesson.gain > 0 ? "text-green-500" : "text-rose-400",
                          )}
                        >
                          {lesson.gain > 0 ? "−" : "+"}{Math.abs(lesson.gain)} moves
                        </span>
                      </div>
                    )}
                  </div>
                </div>
              );
            })}
          </div>
        </div>
      )}
    </div>
  );
}
