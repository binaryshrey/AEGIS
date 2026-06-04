"use client";

import { Suspense, useCallback, useEffect, useRef, useState } from "react";
import { useSearchParams } from "next/navigation";
import { AppSidebar } from "@/components/app-sidebar";
import { SiteHeader } from "@/components/site-header";
import { SidebarInset, SidebarProvider } from "@/components/ui/sidebar";
import { WorkflowCanvas, Workflow, LogItem } from "@/components/workflow-canvas";
import {
  Sheet,
  SheetContent,
  SheetHeader,
  SheetTitle,
  SheetDescription,
} from "@/components/ui/sheet";
import { cn } from "@/lib/utils";

type NodeStatus = "pending" | "running" | "completed";

function makeEmptyWorkflow(): Workflow {
  return {
    id: "battle",
    nodes: [
      {
        id: "node-1",
        name: "Opponent Profiler",
        type: "INTELLIGENCE",
        status: "pending",
        description:
          "Loads opponent history from memory across prior games. Computes a trust score (0.0–1.0) by blending placement stability, prediction accuracy, and sample size. Classifies the opponent as scout, rotating, adaptive, drift, etc.",
        children: [
          { id: "node-1-1", name: "Trust Score Computation", type: "SUBPROCESS", status: "pending" },
          { id: "node-1-2", name: "Placement Pattern Analysis", type: "SUBPROCESS", status: "pending" },
          { id: "node-1-3", name: "Firing Sequence Detection", type: "SUBPROCESS", status: "pending" },
        ],
      },
      {
        id: "node-2",
        name: "Defensive Ship Placement",
        type: "PLACEMENT",
        status: "pending",
        description:
          "Places our fleet on low-frequency cells to minimize opponent hit probability. Blends the opponent's historical shot heatmap with an occupancy prior, then scores candidate layouts to find the safest arrangement.",
        children: [
          { id: "node-2-1", name: "Shot Heatmap Construction", type: "SUBPROCESS", status: "pending" },
          { id: "node-2-2", name: "Candidate Layout Scoring", type: "SUBPROCESS", status: "pending" },
          { id: "node-2-3", name: "Fleet Position Assignment", type: "SUBPROCESS", status: "pending" },
        ],
      },
      {
        id: "node-3",
        name: "Thompson Bandit Selector",
        type: "STRATEGY",
        status: "pending",
        description:
          "Samples from per-opponent Beta(wins, losses) posteriors for each strategy arm — probability sweep, hunt mode, or full exploit. The highest sampled value wins. Bayesian confidence naturally balances exploration vs exploitation.",
        children: [
          { id: "node-3-1", name: "Beta Posterior Sampling", type: "SUBPROCESS", status: "pending" },
          { id: "node-3-2", name: "Strategy Arm Selection", type: "SUBPROCESS", status: "pending" },
          { id: "node-3-3", name: "Composite Reward Update", type: "SUBPROCESS", status: "pending" },
        ],
      },
      {
        id: "node-4",
        name: "Probability Targeting Engine",
        type: "TARGETING",
        status: "pending",
        description:
          "Enumerates every legal placement for all remaining unsunk ships. Weights each by ship value — Carrier contributes 2.5x more than Destroyer to the probability map. Trusted opponents get their heatmap prior blended in multiplicatively.",
        children: [
          { id: "node-4-1", name: "Ship Enumeration", type: "SUBPROCESS", status: "pending" },
          { id: "node-4-2", name: "Value-Weighted Scoring", type: "SUBPROCESS", status: "pending" },
          { id: "node-4-3", name: "Heatmap Prior Blending", type: "SUBPROCESS", status: "pending" },
        ],
      },
      {
        id: "node-5",
        name: "ReAct Decision Loop",
        type: "AGENT",
        status: "pending",
        description:
          "The core Observe-Reason-Act cycle. Observes the last shot result and opponent's counter-shot. Reasons about whether to exploit known cells, hunt adjacent hits, or sweep by probability. Fires the pre-computed highest-value coordinate.",
        children: [
          { id: "node-5-1", name: "Observe & Update State", type: "SUBPROCESS", status: "pending" },
          { id: "node-5-2", name: "Reason & Select Strategy", type: "SUBPROCESS", status: "pending" },
          { id: "node-5-3", name: "Act & Fire Shot", type: "SUBPROCESS", status: "pending" },
        ],
      },
      {
        id: "node-6",
        name: "Memory & Learning",
        type: "FEEDBACK",
        status: "pending",
        description:
          "Records game outcomes back into opponent memory. Updates ship placement grids, firing sequence logs, and dangerous-square heatmaps. Feeds the composite reward (win + move efficiency + survival) into the bandit's arm posteriors for next game.",
        children: [
          { id: "node-6-1", name: "Placement Grid Recording", type: "SUBPROCESS", status: "pending" },
          { id: "node-6-2", name: "Dangerous Squares Update", type: "SUBPROCESS", status: "pending" },
          { id: "node-6-3", name: "Bandit Posterior Update", type: "SUBPROCESS", status: "pending" },
        ],
      },
    ],
  };
}

function fmtTime(ts: string): string {
  try {
    const d = new Date(ts);
    return `${String(d.getHours()).padStart(2, "0")}:${String(d.getMinutes()).padStart(2, "0")}:${String(d.getSeconds()).padStart(2, "0")}`;
  } catch {
    return "--:--:--";
  }
}

function coordToCell(row: number, col: number): string {
  return `${String.fromCharCode(65 + row)}${col + 1}`;
}

/** Convert a JSONL event into one or more LogItems + optional node status updates */
function processEvent(
  event: string,
  data: Record<string, unknown>,
  ts: string,
): { logs: LogItem[]; nodeUpdates?: Record<string, NodeStatus> } {
  const t = fmtTime(ts);
  const logs: LogItem[] = [];
  let nodeUpdates: Record<string, NodeStatus> | undefined;

  switch (event) {
    case "run_started":
      logs.push({ timestamp: t, text: "INITIALIZING CLOSED-LOOP AGENT...", type: "warn" });
      break;

    case "registered":
      logs.push({
        timestamp: t,
        text: `Registered as player ${data.player_id}. ${data.num_opponents} opponents, ${data.turn_timeout}ms timeout.`,
        type: "success",
      });
      break;

    case "attempt_started":
      logs.push({
        timestamp: t,
        text: `━━━ ATTEMPT ${data.attempt} STARTED ━━━`,
        type: "warn",
      });
      break;

    case "game_started": {
      const opp = data.opponent_id as string;
      const strat = data.chosen_strategy as string;
      const reason = data.strategy_reason as string;
      const wr = data.win_rate as number;
      const gamesVs = data.games_vs_opponent as number;

      // Profiler, Placement, Bandit all done; Targeting + ReAct start
      nodeUpdates = {
        "node-1": "completed", "node-1-1": "completed", "node-1-2": "completed", "node-1-3": "completed",
        "node-2": "completed", "node-2-1": "completed", "node-2-2": "completed", "node-2-3": "completed",
        "node-3": "completed", "node-3-1": "completed", "node-3-2": "completed", "node-3-3": "completed",
        "node-4": "running", "node-4-1": "running",
        "node-5": "running", "node-5-1": "running",
      };

      logs.push({
        timestamp: t,
        text: `[GAME ${data.game_num}] vs ${opp} — ${gamesVs} prior games, win rate ${(wr * 100).toFixed(0)}%`,
        type: "warn",
      });
      if (data.known_placement) {
        logs.push({ timestamp: t, text: `  [INTELLIGENCE] Known placement pattern detected`, type: "info" });
      }
      if (data.known_firing) {
        logs.push({ timestamp: t, text: `  [INTELLIGENCE] Known firing sequence detected`, type: "info" });
      }
      logs.push({
        timestamp: t,
        text: `  [STRATEGY] ${strat}${reason ? ` — ${reason}` : ""}`,
        type: "info",
      });
      break;
    }

    case "move": {
      const cell = coordToCell(data.row as number, data.col as number);
      const result = (data.result as string).toUpperCase();
      const turn = data.turn as number;
      const ms = data.elapsed_ms as number;
      const strat = data.strategy as string;

      nodeUpdates = {
        "node-4": "running", "node-4-1": "running", "node-4-2": "running",
        "node-5": "running", "node-5-1": "running", "node-5-2": "running", "node-5-3": "running",
      };

      const isHit = result === "HIT" || result.includes("SUNK");
      logs.push({
        timestamp: t,
        text: `  [T${turn}] ${cell} → ${result}  (${ms}ms, ${strat})`,
        type: isHit ? "success" : "info",
      });
      break;
    }

    case "pattern_detected":
      logs.push({
        timestamp: t,
        text: `  [PATTERN] ${data.pattern_type} on ${data.opponent_id} (${data.games_confirmed} games): ${data.detail}`,
        type: "warn",
      });
      break;

    case "strategy_changed":
      logs.push({
        timestamp: t,
        text: `  [STRATEGY SWITCH] ${data.from} → ${data.to}: ${data.reason}`,
        type: "warn",
      });
      break;

    case "game_ended": {
      const won = data.won as boolean;
      const moves = data.total_moves as number;
      const avgMs = data.avg_ms as number;
      const shipsLost = data.ships_lost as number;
      const improvement = data.improvement as number | null;

      // Targeting + ReAct done, Memory starts
      nodeUpdates = {
        "node-4": "completed", "node-4-1": "completed", "node-4-2": "completed", "node-4-3": "completed",
        "node-5": "completed", "node-5-1": "completed", "node-5-2": "completed", "node-5-3": "completed",
        "node-6": "running", "node-6-1": "running", "node-6-2": "running",
      };

      const improvementStr = improvement != null && improvement > 0 ? ` (${improvement} moves saved)` : "";
      logs.push({
        timestamp: t,
        text: `  [RESULT] ${won ? "WIN" : "LOSS"} in ${moves} moves, ${avgMs}ms avg, ${shipsLost} ships lost${improvementStr}`,
        type: won ? "success" : "error",
      });
      break;
    }

    case "memory_updated": {
      nodeUpdates = {
        "node-6": "completed", "node-6-1": "completed", "node-6-2": "completed", "node-6-3": "completed",
      };
      logs.push({
        timestamp: t,
        text: `  [MEMORY] ${data.opponent_id}: ${data.games_played} games, WR ${((data.win_rate as number) * 100).toFixed(0)}%, fixed_placement=${data.fixed_placement}, fixed_firing=${data.fixed_firing}`,
        type: "info",
      });
      break;
    }

    case "attempt_ended": {
      const wins = data.wins as number;
      const losses = data.losses as number;
      const wr = data.win_rate as number;
      logs.push({
        timestamp: t,
        text: `━━━ ATTEMPT ${data.attempt} ENDED: ${wins}W / ${losses}L (${(wr * 100).toFixed(1)}%) ━━━`,
        type: wins > losses ? "success" : "error",
      });
      break;
    }

    case "run_ended":
      // Mark all nodes completed
      nodeUpdates = {};
      for (let i = 1; i <= 6; i++) {
        nodeUpdates[`node-${i}`] = "completed";
        for (let j = 1; j <= 3; j++) {
          nodeUpdates[`node-${i}-${j}`] = "completed";
        }
      }
      logs.push({ timestamp: t, text: "BATTLE COMPLETE. All rounds finished.", type: "success" });
      break;

    case "timeout_warning":
      logs.push({
        timestamp: t,
        text: `  [TIMEOUT] Turn ${data.turn} took ${data.elapsed_ms}ms / ${data.budget_ms}ms budget`,
        type: "error",
      });
      break;

    case "error":
      logs.push({
        timestamp: t,
        text: `  [ERROR] ${data.context}: ${data.message}`,
        type: "error",
      });
      break;

    case "learning_curve":
      // Summary event, skip in live logs
      break;

    default:
      logs.push({ timestamp: t, text: `[${event}] ${JSON.stringify(data)}`, type: "info" });
  }

  return { logs, nodeUpdates };
}

export default function Page() {
  return (
    <Suspense>
      <BattleArena />
    </Suspense>
  );
}

function BattleArena() {
  const searchParams = useSearchParams();
  const battleId = searchParams.get("id");

  const [workflow, setWorkflow] = useState<Workflow | null>(null);
  const [logs, setLogs] = useState<LogItem[]>([]);
  const [drawerOpen, setDrawerOpen] = useState(false);
  const [battleComplete, setBattleComplete] = useState(false);
  const connectedRef = useRef(false);
  const logsEndRef = useRef<HTMLDivElement>(null);
  const eventSourceRef = useRef<EventSource | null>(null);

  // Auto-scroll logs
  useEffect(() => {
    logsEndRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [logs]);

  const applyNodeUpdates = useCallback(
    (updates: Record<string, NodeStatus>) => {
      setWorkflow((prev) => {
        if (!prev) return prev;
        const next = JSON.parse(JSON.stringify(prev)) as Workflow;
        for (const node of next.nodes) {
          if (updates[node.id]) node.status = updates[node.id];
          for (const child of node.children ?? []) {
            if (updates[child.id]) child.status = updates[child.id];
          }
        }
        return next;
      });
    },
    [],
  );

  // Reset nodes to pending for next game (except keep completed ones that are about to cycle)
  const resetForNewGame = useCallback(() => {
    setWorkflow((prev) => {
      if (!prev) return prev;
      const next = JSON.parse(JSON.stringify(prev)) as Workflow;
      for (const node of next.nodes) {
        node.status = "pending";
        for (const child of node.children ?? []) {
          child.status = "pending";
        }
      }
      return next;
    });
  }, []);

  // Connect to SSE stream
  useEffect(() => {
    if (!battleId || connectedRef.current) return;
    connectedRef.current = true;

    setWorkflow(makeEmptyWorkflow());
    setDrawerOpen(true);

    const es = new EventSource(`/api/battle/logs?id=${battleId}`);
    eventSourceRef.current = es;

    es.onmessage = (msg) => {
      try {
        const parsed = JSON.parse(msg.data);
        const { event, data, ts } = parsed;

        // Reset nodes when a new game starts (except first)
        if (event === "game_started") {
          resetForNewGame();
        }

        const { logs: newLogs, nodeUpdates } = processEvent(event, data, ts);

        if (newLogs.length > 0) {
          setLogs((prev) => [...prev, ...newLogs]);
        }
        if (nodeUpdates) {
          applyNodeUpdates(nodeUpdates);
        }

        if (event === "run_ended") {
          setBattleComplete(true);
          es.close();
        }
      } catch {
        // Skip parse errors
      }
    };

    es.onerror = () => {
      // EventSource auto-reconnects; no action needed unless it closes permanently
    };

    return () => {
      es.close();
      eventSourceRef.current = null;
      connectedRef.current = false;
    };
  }, [battleId, applyNodeUpdates, resetForNewGame]);

  return (
    <SidebarProvider
      className="h-screen w-screen overflow-hidden flex"
      style={
        {
          "--sidebar-width": "calc(var(--spacing) * 72)",
          "--header-height": "calc(var(--spacing) * 12)",
        } as React.CSSProperties
      }
    >
      <AppSidebar variant="inset" />
      <SidebarInset className="h-full min-h-0 overflow-hidden">
        <SiteHeader analyticsBattleId={battleComplete && battleId ? battleId : undefined} />
        <div className="flex-1 min-h-0 min-w-0 overflow-hidden p-6">
          <WorkflowCanvas
            workflow={workflow}
            onNodeClick={() => setDrawerOpen(true)}
          />
        </div>
      </SidebarInset>

      <Sheet open={drawerOpen} onOpenChange={setDrawerOpen}>
        <SheetContent
          side="right"
          showCloseButton
          className="w-[400px] sm:max-w-[400px] bg-[#0c0a0f] border-white/8 p-0 flex flex-col"
        >
          <SheetHeader className="px-5 pt-5 pb-3 border-b border-white/10 shrink-0">
            <div className="flex items-center justify-between">
              <SheetTitle className="text-[11px] font-bold text-zinc-400 uppercase tracking-wider">
                Live Battle Logs
              </SheetTitle>
              {logs.length > 0 && (
                <span className="flex h-2 w-2 rounded-full bg-emerald-500 animate-ping" />
              )}
            </div>
            <SheetDescription className="text-[10px] text-zinc-600">
              Click any agent node to reopen this panel
            </SheetDescription>
          </SheetHeader>

          <div className="flex-1 overflow-y-auto px-5 py-4 space-y-3 font-mono text-xs scrollbar-thin scrollbar-thumb-zinc-800 scrollbar-track-transparent">
            {logs.map((log, index) => (
              <div
                key={index}
                className={cn(
                  "leading-relaxed",
                  log.type === "info" && "text-zinc-400",
                  log.type === "success" && "text-emerald-400 font-semibold",
                  log.type === "warn" && "text-yellow-400",
                  log.type === "error" && "text-rose-500 font-semibold",
                )}
              >
                <span className="text-[9px] text-zinc-600 mr-2 font-sans select-none">
                  {log.timestamp}
                </span>
                {log.text}
              </div>
            ))}
            <div ref={logsEndRef} />
          </div>
        </SheetContent>
      </Sheet>
    </SidebarProvider>
  );
}
