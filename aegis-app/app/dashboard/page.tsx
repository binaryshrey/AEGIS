"use client";

import * as React from "react";
import { useRouter } from "next/navigation";
import { AppSidebar } from "@/components/app-sidebar";
import { DataTable, type TableRowData } from "@/components/data-table";
import { SectionCards } from "@/components/section-cards";
import { SiteHeader } from "@/components/site-header";
import { SidebarInset, SidebarProvider } from "@/components/ui/sidebar";
import { DashboardInsights } from "@/components/dashboard-insights";
import { ChatBar } from "@/components/chat-bar";
import {
  fetchRuns,
  fetchOpponents,
  type Run,
  type Opponent,
} from "@/lib/supabase";

function runsToTableData(runs: Run[]) {
  return runs.map((r, idx) => ({
    id: r.id,
    battleId: r.battle_id,
    run: `#${runs.length - idx}`,
    score: r.total_score ?? 0,
    winRate: r.total_games
      ? `${r.wins}/${r.total_games}`
      : "0/0",
    avgMoves: r.avg_moves ?? 0,
    opponents: r.total_games ?? 0,
    date: new Date(r.created_at).toLocaleDateString("en-US", {
      month: "short",
      day: "numeric",
      year: "numeric",
    }),
    status: r.status === "complete" ? "Complete" : r.status ?? "Unknown",
  }));
}

export default function Page() {
  const router = useRouter();
  const [runs, setRuns] = React.useState<Run[]>([]);
  const [opponents, setOpponents] = React.useState<Opponent[]>([]);
  const [loading, setLoading] = React.useState(true);

  React.useEffect(() => {
    async function load() {
      const [r, o] = await Promise.all([fetchRuns(50), fetchOpponents()]);
      setRuns(r);
      setOpponents(o);
      setLoading(false);
    }
    load();
  }, []);

  const latest = runs[0] ?? null;
  const previous = runs[1] ?? null;
  const tableData = runsToTableData(runs);

  // All runs sorted by score (best first)
  const byScore = [...runs].sort((a, b) => (b.total_score ?? 0) - (a.total_score ?? 0));
  const leaderboard = byScore.slice(0, 10);
  const bestRun = byScore[0] ?? null;

  const handleRowClick = React.useCallback(
    (row: TableRowData) => {
      if (row.battleId) {
        router.push(`/battle-analytics?id=${row.battleId}`);
      }
    },
    [router],
  );

  return (
    <SidebarProvider
      style={
        {
          "--sidebar-width": "calc(var(--spacing) * 72)",
          "--header-height": "calc(var(--spacing) * 12)",
        } as React.CSSProperties
      }
    >
      <AppSidebar variant="inset" />
      <SidebarInset>
        <SiteHeader />
        <div className="flex flex-1 flex-col">
          <div className="@container/main flex flex-1 flex-col gap-2">
            <div className="flex flex-col gap-2 py-2 md:gap-2 md:py-2">
              {loading ? (
                <div className="flex items-center justify-center py-12 text-muted-foreground">
                  Loading dashboard data...
                </div>
              ) : (
                <>
                  <SectionCards latest={latest} previous={previous} opponents={opponents} bestRun={bestRun} />
                  <DashboardInsights opponents={opponents} leaderboard={leaderboard} />
                  <div className="px-2 lg:px-2">
                    <h2 className="text-base font-semibold mb-2">Battle History</h2>
                    <DataTable data={tableData} onRowClick={handleRowClick} />
                  </div>
                </>
              )}
            </div>
          </div>
        </div>
        <ChatBar />
      </SidebarInset>
    </SidebarProvider>
  );
}
