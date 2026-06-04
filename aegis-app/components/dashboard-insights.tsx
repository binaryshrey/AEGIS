"use client";

import {
  RiPhoneFindFill,
  RiFocus2Fill,
  RiShieldFill,
  RiTrophyFill,
  RiMedalFill,
} from "@remixicon/react";

import { Badge } from "@/components/ui/badge";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import type { Run, Opponent } from "@/lib/supabase";
import {
  Tooltip,
  TooltipContent,
  TooltipProvider,
  TooltipTrigger,
} from "@/components/ui/tooltip";

interface DashboardInsightsProps {
  opponents: Opponent[];
  leaderboard: Run[];
}

const CLASS_COLORS: Record<string, string> = {
  scout: "#ff7b00",
  rotating: "#ff8800",
  drift: "#ff9500",
  noisy: "#ffa200",
  adaptive: "#ffaa00",
  prob: "#ffb700",
  antiheat: "#ffc300",
  sparse: "#ffd000",
  antiparity: "#ffdd00",
  unknown: "#ffea00",
};

export function DashboardInsights({ opponents, leaderboard }: DashboardInsightsProps) {
  const totalModeled = opponents.length;
  const exploitableCount = opponents.filter((o) => o.exploitable).length;
  const avgTrust = totalModeled > 0
    ? opponents.reduce((s, o) => s + (o.trust ?? 0), 0) / totalModeled
    : 0;
  const avgWinRate = totalModeled > 0
    ? opponents.reduce((s, o) => s + (o.win_rate ?? 0), 0) / totalModeled
    : 0;

  // Build classification counts
  const classificationCounts: Record<string, number> = {};
  for (const o of opponents) {
    const cls = (o.classification ?? "unknown").toLowerCase();
    classificationCounts[cls] = (classificationCounts[cls] ?? 0) + 1;
  }

  // Sort classifications by count descending
  const sortedClasses = Object.entries(classificationCounts).sort(
    (a, b) => b[1] - a[1]
  );

  const totalForBar = totalModeled || 1;

  return (
    <div className="grid grid-cols-1 gap-2 px-2 lg:grid-cols-2 lg:px-2">
      {/* Left Column */}
      <div className="flex flex-col gap-2">
        {/* Opponent Intelligence Card */}
        <Card className="shadow-xs">
          <CardHeader className="p-4 pb-2">
            <CardTitle className="text-base font-semibold">
              Opponent Intelligence
            </CardTitle>
          </CardHeader>
          <CardContent className="flex flex-col gap-2 p-4 pt-0">
            {/* Stats Grid */}
            <div className="grid grid-cols-2 gap-2">
              <div className="flex items-center gap-2.5 rounded-lg bg-muted/50 px-3 py-2.5">
                <RiPhoneFindFill className="size-4 text-amber-300 shrink-0" />
                <div>
                  <div className="text-lg font-bold leading-tight">{totalModeled}</div>
                  <div className="text-[11px] text-muted-foreground">Modeled</div>
                </div>
              </div>
              <div className="flex items-center gap-2.5 rounded-lg bg-muted/50 px-3 py-2.5">
                <RiFocus2Fill className="size-4 text-amber-300 shrink-0" />
                <div>
                  <div className="text-lg font-bold leading-tight">{exploitableCount}</div>
                  <div className="text-[11px] text-muted-foreground">Exploitable</div>
                </div>
              </div>
              <div className="flex items-center gap-2.5 rounded-lg bg-muted/50 px-3 py-2.5">
                <RiShieldFill className="size-4 text-amber-300 shrink-0" />
                <div>
                  <div className="text-lg font-bold leading-tight">{(avgTrust * 100).toFixed(0)}%</div>
                  <div className="text-[11px] text-muted-foreground">Avg Trust</div>
                </div>
              </div>
              <div className="flex items-center gap-2.5 rounded-lg bg-muted/50 px-3 py-2.5">
                <RiTrophyFill className="size-4 text-amber-300 shrink-0" />
                <div>
                  <div className="text-lg font-bold leading-tight">{(avgWinRate * 100).toFixed(0)}%</div>
                  <div className="text-[11px] text-muted-foreground">Avg Win Rate</div>
                </div>
              </div>
            </div>
          </CardContent>
        </Card>

        {/* Classification Distribution Card */}
        <Card className="shadow-xs">
          <CardHeader className="p-4 pb-1">
            <CardTitle className="text-base font-semibold">
              Opponent Classification
            </CardTitle>
          </CardHeader>
          <CardContent className="flex flex-col gap-3 p-4 pt-2">
            {/* Segmented Bar */}
            <TooltipProvider>
              <div className="flex h-3 w-full overflow-hidden rounded-full gap-[2px]">
                {sortedClasses.map(([cls, count]) => (
                  <Tooltip key={cls}>
                    <TooltipTrigger asChild>
                      <div
                        className="transition-all cursor-pointer hover:opacity-80"
                        style={{ width: `${(count / totalForBar) * 100}%`, backgroundColor: CLASS_COLORS[cls] ?? "#ffea00" }}
                      />
                    </TooltipTrigger>
                    <TooltipContent side="top">
                      {cls.charAt(0).toUpperCase() + cls.slice(1)} — {count} opponent{count !== 1 ? "s" : ""}
                    </TooltipContent>
                  </Tooltip>
                ))}
              </div>
            </TooltipProvider>

            {/* Legend with win rates */}
            <div className="grid grid-cols-2 gap-x-4 gap-y-1.5">
              {sortedClasses.map(([cls, count]) => (
                  <div key={cls} className="flex items-center justify-between gap-1.5">
                    <div className="flex items-center gap-1.5">
                      <div
                        className="size-2.5 rounded-full"
                        style={{ backgroundColor: CLASS_COLORS[cls] ?? "#a9d6e5" }}
                      />
                      <span className="text-xs font-medium capitalize">
                        {cls}
                      </span>
                      <span className="text-xs text-muted-foreground">
                        ({count})
                      </span>
                    </div>
                  </div>
              ))}
            </div>
          </CardContent>
        </Card>
      </div>

      {/* Right Column - Leaderboard */}
      <Card className="shadow-xs flex flex-col h-full">
        <CardHeader className="p-4 pb-2">
          <CardTitle className="text-base font-semibold flex items-center gap-2">
            Run Leaderboard
            {leaderboard.length > 0 && (
              <Badge variant="outline" className="text-xs font-normal text-muted-foreground">
                Top {leaderboard.length}
              </Badge>
            )}
          </CardTitle>
        </CardHeader>
        <CardContent className="flex-1 p-4 pt-0 overflow-y-auto max-h-80">
          {leaderboard.length === 0 ? (
            <div className="flex items-center justify-center py-8 text-sm text-muted-foreground">
              No runs yet
            </div>
          ) : (
            <Table>
              <TableHeader className="bg-muted/50 rounded-md">
                <TableRow className="hover:bg-transparent border-none">
                  <TableHead className="w-10 h-8 rounded-l-md font-medium text-muted-foreground text-xs px-3">
                    #
                  </TableHead>
                  <TableHead className="h-8 font-medium text-muted-foreground text-xs px-3">
                    Score
                  </TableHead>
                  <TableHead className="h-8 font-medium text-muted-foreground text-xs px-3">
                    Record
                  </TableHead>
                  <TableHead className="h-8 font-medium text-muted-foreground text-xs px-3">
                    Moves
                  </TableHead>
                  <TableHead className="text-right h-8 rounded-r-md font-medium text-muted-foreground text-xs px-3">
                    Survival
                  </TableHead>
                </TableRow>
              </TableHeader>
              <TableBody className="text-sm">
                {leaderboard.map((run, idx) => (
                  <TableRow
                    key={run.id}
                    className={`${idx < leaderboard.length - 1 ? "border-b border-border/50" : "border-none"} ${idx === 0 ? "bg-yellow-500/5" : ""}`}
                  >
                    <TableCell className="py-2 px-3">
                      {idx === 0 ? (
                        <RiMedalFill className="size-4 text-yellow-500" />
                      ) : (
                        <span className="text-muted-foreground font-semibold">{idx + 1}</span>
                      )}
                    </TableCell>
                    <TableCell className="font-semibold py-2 px-3 tabular-nums">
                      {run.total_score ?? 0}
                    </TableCell>
                    <TableCell className="py-2 px-3 text-muted-foreground tabular-nums">
                      {run.wins}W/{run.losses}L
                    </TableCell>
                    <TableCell className="py-2 px-3 font-mono tabular-nums">
                      {(run.avg_moves ?? 0).toFixed(1)}
                    </TableCell>
                    <TableCell className="text-right py-2 px-3 tabular-nums">
                      <span className={(run.ships_surviving ?? 0) >= 4 ? "text-green-400" : (run.ships_surviving ?? 0) >= 3 ? "text-muted-foreground" : "text-red-400"}>
                        {(run.ships_surviving ?? 0).toFixed(1)}
                      </span>
                    </TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          )}
        </CardContent>
      </Card>
    </div>
  );
}
