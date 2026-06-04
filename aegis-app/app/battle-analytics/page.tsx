"use client";

import * as React from "react";
import { Suspense, useCallback, useEffect, useState } from "react";
import { useSearchParams, useRouter } from "next/navigation";
import { AppSidebar } from "@/components/app-sidebar";
import { SiteHeader } from "@/components/site-header";
import { SidebarInset, SidebarProvider } from "@/components/ui/sidebar";
import { BattleAnalyticsContent } from "@/components/battle-analytics-content";
import { DataTable, type TableRowData } from "@/components/data-table";
import { fetchRuns, type Run } from "@/lib/supabase";
import { ChatBar } from "@/components/chat-bar";

function runsToTableData(runs: Run[]) {
  return runs.map((r, idx) => ({
    id: r.id,
    battleId: r.battle_id,
    run: `#${runs.length - idx}`,
    score: r.total_score ?? 0,
    winRate: r.total_games ? `${r.wins}/${r.total_games}` : "0/0",
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

function BattleAnalyticsInner() {
  const searchParams = useSearchParams();
  const router = useRouter();
  const battleId = searchParams.get("id");

  const [runs, setRuns] = useState<Run[]>([]);
  const [loadingRuns, setLoadingRuns] = useState(true);

  useEffect(() => {
    fetchRuns(50).then((r) => {
      setRuns(r);
      setLoadingRuns(false);
    });
  }, []);

  const tableData = runsToTableData(runs);

  const handleRowClick = useCallback(
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
            <div className="flex flex-col gap-4 px-4 py-6 lg:px-6">
              <div className="flex flex-col gap-1">
                <h1 className="text-2xl font-semibold text-zinc-100">
                  Battle Analytics
                </h1>
                <p className="text-sm text-zinc-500">
                  {battleId
                    ? "Performance metrics and agent intelligence from this battle"
                    : "Select a battle to view analytics"}
                </p>
              </div>
              {battleId ? (
                <BattleAnalyticsContent battleId={battleId} />
              ) : (
                <div>
                  <h2 className="text-base font-semibold mb-2">Battle History</h2>
                  {loadingRuns ? (
                    <div className="flex items-center justify-center py-8 text-muted-foreground text-sm">
                      Loading...
                    </div>
                  ) : (
                    <DataTable data={tableData} onRowClick={handleRowClick} />
                  )}
                </div>
              )}
            </div>
          </div>
        </div>
        <ChatBar />
      </SidebarInset>
    </SidebarProvider>
  );
}

export default function Page() {
  return (
    <Suspense>
      <BattleAnalyticsInner />
    </Suspense>
  );
}
