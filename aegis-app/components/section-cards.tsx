import { RiArrowDownSLine, RiArrowUpSLine, RiTrophyFill } from "@remixicon/react"

import { Badge } from "@/components/ui/badge"
import {
  Card,
  CardAction,
  CardDescription,
  CardFooter,
  CardHeader,
  CardTitle,
} from "@/components/ui/card"
import type { Run, Opponent } from "@/lib/supabase"

interface SectionCardsProps {
  latest: Run | null;
  previous: Run | null;
  opponents: Opponent[];
  bestRun: Run | null;
}

function delta(curr: number | null | undefined, prev: number | null | undefined): number {
  return (curr ?? 0) - (prev ?? 0);
}

function fmt(n: number, decimals = 1): string {
  return n.toLocaleString("en-US", { maximumFractionDigits: decimals });
}

export function SectionCards({ latest, previous, opponents, bestRun }: SectionCardsProps) {
  const bestScore = bestRun?.total_score ?? 0;
  const latestScore = latest?.total_score ?? 0;
  const isLatestBest = bestRun && latest && bestRun.id === latest.id;

  const avgMoves = latest?.avg_moves ?? 0;
  const movesDelta = delta(latest?.avg_moves, previous?.avg_moves);

  const survival = latest?.ships_surviving ?? 0;
  const survivalDelta = delta(latest?.ships_surviving, previous?.ships_surviving);

  const winRate = latest && latest.total_games > 0
    ? Math.round((latest.wins / latest.total_games) * 100)
    : 0;
  const prevWinRate = previous && previous.total_games > 0
    ? Math.round((previous.wins / previous.total_games) * 100)
    : 0;
  const winRateDelta = winRate - prevWinRate;

  const totalModeled = opponents.length;

  return (
    <div className="grid grid-cols-1 gap-2 px-2 *:data-[slot=card]:bg-gradient-to-t *:data-[slot=card]:from-primary/5 *:data-[slot=card]:to-card *:data-[slot=card]:shadow-xs lg:px-2 @xl/main:grid-cols-2 @5xl/main:grid-cols-4 dark:*:data-[slot=card]:bg-card">
      {/* Best Score */}
      <Card className="@container/card">
        <CardHeader className="p-4 pb-2">
          <CardDescription>Best Score</CardDescription>
          <CardTitle className="text-2xl font-semibold tabular-nums @[250px]/card:text-3xl">
            {fmt(bestScore, 0)}
          </CardTitle>
          <CardAction>
            {isLatestBest ? (
              <Badge variant="outline" className="text-green-500">
                <RiTrophyFill className="size-3.5" />
                New best
              </Badge>
            ) : (
              <Badge variant="outline" className={latestScore >= bestScore * 0.95 ? "text-green-500" : "text-muted-foreground"}>
                {latestScore >= bestScore * 0.95 ? <RiArrowUpSLine /> : <RiArrowDownSLine />}
                {fmt(latestScore, 0)} latest
              </Badge>
            )}
          </CardAction>
        </CardHeader>
        <CardFooter className="flex-col items-start gap-1.5 text-sm p-4 pt-0">
          <div className="line-clamp-1 flex gap-2 font-medium">
            {bestRun ? `${bestRun.wins}W / ${bestRun.losses}L` : "No runs yet"}
          </div>
          <div className="text-muted-foreground">
            {bestRun ? `Run #${bestRun.attempt_num} \u00b7 Max possible: 1,000` : ""}
          </div>
        </CardFooter>
      </Card>
      {/* Targeting Efficiency */}
      <Card className="@container/card">
        <CardHeader className="p-4 pb-2">
          <CardDescription>Avg Moves / Game</CardDescription>
          <CardTitle className="text-2xl font-semibold tabular-nums @[250px]/card:text-3xl">
            {fmt(avgMoves)}
          </CardTitle>
          <CardAction>
            {previous && (
              <Badge variant="outline" className={movesDelta <= 0 ? "text-green-500" : "text-red-500"}>
                {movesDelta <= 0 ? <RiArrowDownSLine /> : <RiArrowUpSLine />}
                {movesDelta >= 0 ? "+" : ""}{movesDelta.toFixed(1)}
              </Badge>
            )}
          </CardAction>
        </CardHeader>
        <CardFooter className="flex-col items-start gap-1.5 text-sm p-4 pt-0">
          <div className="line-clamp-1 flex gap-2 font-medium">
            {movesDelta <= 0 ? "Fewer moves per win" : "More moves needed"}
            {movesDelta <= 0 ? <RiArrowDownSLine className="size-4" /> : <RiArrowUpSLine className="size-4" />}
          </div>
          <div className="text-muted-foreground">
            Perfect: 17 moves
          </div>
        </CardFooter>
      </Card>
      {/* Fleet Survival */}
      <Card className="@container/card">
        <CardHeader className="p-4 pb-2">
          <CardDescription>Fleet Survival</CardDescription>
          <CardTitle className="text-2xl font-semibold tabular-nums @[250px]/card:text-3xl">
            {fmt(survival)} / 5
          </CardTitle>
          <CardAction>
            {previous && (
              <Badge variant="outline" className={survivalDelta >= 0 ? "text-green-500" : "text-red-500"}>
                {survivalDelta >= 0 ? <RiArrowUpSLine /> : <RiArrowDownSLine />}
                {survivalDelta >= 0 ? "+" : ""}{survivalDelta.toFixed(1)}
              </Badge>
            )}
          </CardAction>
        </CardHeader>
        <CardFooter className="flex-col items-start gap-1.5 text-sm p-4 pt-0">
          <div className="line-clamp-1 flex gap-2 font-medium">
            {survivalDelta >= 0 ? "Improved evasion" : "Survival decreased"}
            {survivalDelta >= 0 ? <RiArrowUpSLine className="size-4" /> : <RiArrowDownSLine className="size-4" />}
          </div>
          <div className="text-muted-foreground">
            Avg {fmt(latest?.hits_taken ?? 0)} hits taken / game
          </div>
        </CardFooter>
      </Card>
      {/* Win Rate */}
      <Card className="@container/card">
        <CardHeader className="p-4 pb-2">
          <CardDescription>Win Rate</CardDescription>
          <CardTitle className="text-2xl font-semibold tabular-nums @[250px]/card:text-3xl">
            {winRate}%
          </CardTitle>
          <CardAction>
            {previous && (
              <Badge variant="outline" className={winRateDelta >= 0 ? "text-green-500" : "text-red-500"}>
                {winRateDelta >= 0 ? <RiArrowUpSLine /> : <RiArrowDownSLine />}
                {winRateDelta >= 0 ? "+" : ""}{winRateDelta}%
              </Badge>
            )}
          </CardAction>
        </CardHeader>
        <CardFooter className="flex-col items-start gap-1.5 text-sm p-4 pt-0">
          <div className="line-clamp-1 flex gap-2 font-medium">
            {latest ? `${latest.wins}W / ${latest.losses}L latest` : "No runs yet"}
          </div>
          <div className="text-muted-foreground">
            {totalModeled} opponents modeled
          </div>
        </CardFooter>
      </Card>
    </div>
  )
}
