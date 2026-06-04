"use client";

import { useEffect, useRef, useState } from "react";
import {
  ArrowRight,
  Layers3,
  Maximize,
  Minus,
  RotateCcw,
  Undo2,
  ZoomIn,
} from "lucide-react";
import { RiCheckboxCircleFill } from "@remixicon/react";
import { cn } from "@/lib/utils";
import { Button } from "@/components/ui/button";
import { motion } from "motion/react";

export interface WorkflowNode {
  id: string;
  name: string;
  type: string;
  status: "completed" | "running" | "pending" | "failed";
  description?: string;
  children?: WorkflowNode[];
  metrics?: {
    duration?: string;
    accuracy?: string;
    [key: string]: unknown;
  };
}

export interface Workflow {
  id: string;
  nodes: WorkflowNode[];
}

export interface LogItem {
  timestamp: string;
  text: string;
  type: "info" | "success" | "warn" | "error";
}

type ViewState = { x: number; y: number; scale: number };

const DEFAULT_VIEW: ViewState = { x: 0, y: 0, scale: 1.1 };
const MIN_SCALE = 0.4;
const MAX_SCALE = 2.0;

const DOT_PATTERN =
  "url(\"data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' width='22' height='22' viewBox='0 0 22 22'%3E%3Ccircle cx='11' cy='11' r='1' fill='%235F5C6C' /%3E%3C/svg%3E\")";

function clampScale(scale: number) {
  return Math.min(MAX_SCALE, Math.max(MIN_SCALE, scale));
}

function isSameView(a: ViewState, b: ViewState) {
  return a.x === b.x && a.y === b.y && a.scale === b.scale;
}

function WorkspaceControlButton({
  active = false,
  className,
  ...props
}: React.ComponentProps<typeof Button> & { active?: boolean }) {
  return (
    <Button
      variant="outline"
      size="icon"
      className={cn(
        "h-10 w-10 rounded-xl border-white/10 bg-white/5 text-zinc-200 shadow-[0_8px_24px_rgba(0,0,0,0.35)] backdrop-blur hover:bg-white/10 hover:text-white",
        active && "border-white/16 bg-black/40 text-white",
        className,
      )}
      {...props}
    />
  );
}

function Connector({ active }: { active: boolean }) {
  return (
    <div className="flex shrink-0 items-center px-3">
      <div
        className={cn(
          "h-px w-10 transition-colors duration-500",
          active ? "bg-emerald-500/60" : "bg-white/10",
        )}
      />
      <ArrowRight
        className={cn(
          "size-4 -ml-1 transition-colors duration-500",
          active ? "text-emerald-500/60" : "text-white/10",
        )}
      />
    </div>
  );
}

function AgentNode({
  node,
  onClick,
}: {
  node: WorkflowNode;
  onClick?: () => void;
}) {
  const isRunning = node.status === "running";

  return (
    <motion.div
      layout
      initial={{ scale: 0.95, opacity: 0 }}
      animate={{ scale: 1, opacity: 1 }}
      transition={{ type: "spring", stiffness: 300, damping: 25 }}
      onClick={(e) => {
        e.stopPropagation();
        onClick?.();
      }}
      data-drag-ignore="true"
      className={cn(
        "relative flex flex-col rounded-2xl border bg-zinc-900/90 p-4 transition-all duration-300 w-72 shadow-lg backdrop-blur select-none cursor-pointer hover:brightness-110 overflow-hidden",
        isRunning
          ? "border-emerald-600 shadow-emerald-600/15 shadow-2xl"
          : node.status === "completed"
          ? "border-emerald-500/30"
          : "border-white/10"
      )}
    >
      {/* Processing sweep animation */}
      {isRunning && (
        <div
          className="absolute inset-0 pointer-events-none"
          style={{
            background: "linear-gradient(90deg, transparent 0%, rgba(5,150,105,0.08) 40%, rgba(5,150,105,0.15) 50%, rgba(5,150,105,0.08) 60%, transparent 100%)",
            animation: "sweep 2s ease-in-out infinite",
          }}
        />
      )}

      {/* Header */}
      <div className="relative flex items-center justify-between shrink-0">
        <div className="flex flex-col gap-0.5">
          <span className="text-[10px] font-semibold uppercase tracking-wider text-zinc-500">
            {node.type}
          </span>
          <h4 className="text-sm font-semibold text-zinc-100">{node.name}</h4>
        </div>
        {node.status === "completed" ? (
          <motion.div
            initial={{ scale: 0.5, opacity: 0 }}
            animate={{ scale: 1, opacity: 1 }}
          >
            <RiCheckboxCircleFill className="size-4 text-emerald-500 shrink-0" />
          </motion.div>
        ) : (
          <motion.span
            layout
            key={node.status}
            initial={{ scale: 0.5, opacity: 0 }}
            animate={{ scale: 1, opacity: 1 }}
            className={cn(
              "h-2 w-2 rounded-full shrink-0",
              isRunning && "bg-emerald-500 animate-pulse shadow-[0_0_8px_#059669]",
              node.status === "pending" && "bg-zinc-600",
              node.status === "failed" && "bg-rose-500 shadow-[0_0_8px_#f43f5e]"
            )}
          />
        )}
      </div>

      {/* Description */}
      {node.description && (
        <p className="text-xs text-zinc-400 mt-2">{node.description}</p>
      )}

      {/* Sub-processes */}
      {node.children && node.children.length > 0 && (
        <div className="flex flex-col gap-2 mt-auto pt-3 border-t border-white/5">
          <span className="text-[10px] font-bold uppercase tracking-wider text-zinc-500">
            Sub-processes
          </span>
          <div className="flex flex-col gap-1.5">
            {node.children.map((child) => (
              <div
                key={child.id}
                className="flex items-center justify-between rounded-lg px-2.5 py-1.5 text-left text-xs bg-white/[0.02] text-zinc-400 border border-transparent w-full"
              >
                <span className="truncate">{child.name}</span>
                <motion.span
                  layout
                  key={child.status}
                  initial={{ scale: 0.5 }}
                  animate={{ scale: 1 }}
                  className={cn(
                    "h-1.5 w-1.5 rounded-full shrink-0 ml-2",
                    child.status === "completed" && "bg-emerald-500",
                    child.status === "running" && "bg-emerald-500 animate-pulse",
                    child.status === "pending" && "bg-zinc-600",
                    child.status === "failed" && "bg-rose-500"
                  )}
                />
              </div>
            ))}
          </div>
        </div>
      )}
    </motion.div>
  );
}

export function WorkflowCanvas({
  workflow,
  onNodeClick,
}: {
  workflow: Workflow | null;
  onNodeClick?: (nodeId: string) => void;
}) {
  const [view, setView] = useState(DEFAULT_VIEW);
  const [history, setHistory] = useState<ViewState[]>([DEFAULT_VIEW]);
  const [historyIndex, setHistoryIndex] = useState(0);
  const [showGuides, setShowGuides] = useState(true);
  const [isDragging, setIsDragging] = useState(false);

  const dragRef = useRef<{
    pointerId: number;
    pointerX: number;
    pointerY: number;
    startView: ViewState;
  } | null>(null);

  const viewRef = useRef(view);
  useEffect(() => {
    viewRef.current = view;
  }, [view]);

  const historyRef = useRef(history);
  useEffect(() => {
    historyRef.current = history;
  }, [history]);

  const historyIndexRef = useRef(historyIndex);
  useEffect(() => {
    historyIndexRef.current = historyIndex;
  }, [historyIndex]);

  const commitView = (nextView: ViewState) => {
    setView(nextView);
    setHistory((prev) => {
      const truncated = prev.slice(0, historyIndexRef.current + 1);
      const last = truncated.at(-1);
      if (last && isSameView(last, nextView)) return prev;
      const updated = [...truncated, nextView];
      setHistoryIndex(updated.length - 1);
      return updated;
    });
  };

  const restoreHistory = (nextIndex: number) => {
    if (nextIndex < 0 || nextIndex >= historyRef.current.length) return;
    setHistoryIndex(nextIndex);
    setView(historyRef.current[nextIndex]);
  };

  const adjustScale = (delta: number) => {
    const next = {
      ...viewRef.current,
      scale: clampScale(Number((viewRef.current.scale + delta).toFixed(2))),
    };
    commitView(next);
  };

  const handleCanvasPointerDown = (e: React.PointerEvent<HTMLElement>) => {
    if (
      e.target instanceof HTMLElement &&
      e.target.closest('[data-drag-ignore="true"]')
    )
      return;
    dragRef.current = {
      pointerId: e.pointerId,
      pointerX: e.clientX,
      pointerY: e.clientY,
      startView: viewRef.current,
    };
    setIsDragging(true);
  };

  useEffect(() => {
    const handlePointerMove = (e: PointerEvent) => {
      if (!dragRef.current || dragRef.current.pointerId !== e.pointerId) return;
      const { pointerX, pointerY, startView } = dragRef.current;
      setView({
        ...startView,
        x: startView.x + e.clientX - pointerX,
        y: startView.y + e.clientY - pointerY,
      });
    };

    const handlePointerUp = (e: PointerEvent) => {
      if (!dragRef.current || dragRef.current.pointerId !== e.pointerId) return;
      const { pointerX, pointerY, startView } = dragRef.current;
      const nextView = {
        ...startView,
        x: startView.x + e.clientX - pointerX,
        y: startView.y + e.clientY - pointerY,
      };
      dragRef.current = null;
      setIsDragging(false);
      commitView(nextView);
    };

    window.addEventListener("pointermove", handlePointerMove);
    window.addEventListener("pointerup", handlePointerUp);
    window.addEventListener("pointercancel", handlePointerUp);
    return () => {
      window.removeEventListener("pointermove", handlePointerMove);
      window.removeEventListener("pointerup", handlePointerUp);
      window.removeEventListener("pointercancel", handlePointerUp);
    };
  }, []);

  return (
    <section
      className={cn(
        "relative flex h-full w-full min-h-0 min-w-0 overflow-hidden rounded-[28px] border border-white/8 bg-[#171717] shadow-[0_30px_80px_rgba(0,0,0,0.45)]",
        isDragging ? "cursor-grabbing" : "cursor-grab",
      )}
      onPointerDown={handleCanvasPointerDown}
    >
      {/* Dot grid */}
      <div
        className="pointer-events-none absolute inset-0 h-full w-full"
        style={{
          backgroundImage: DOT_PATTERN,
          backgroundSize: "22px 22px",
          backgroundPosition: `${view.x % 22}px ${view.y % 22}px`,
        }}
      />

      {/* Controls */}
      <div
        className="absolute top-1/2 left-5 z-20 flex -translate-y-1/2 cursor-default flex-col items-center gap-3"
        data-drag-ignore="true"
      >
        <div className="flex flex-col gap-2 rounded-[18px] border border-white/10 bg-[#16141B]/85 p-2 shadow-[0_20px_40px_rgba(0,0,0,0.35)] backdrop-blur">
          <WorkspaceControlButton
            aria-label="Zoom in"
            onClick={() => adjustScale(0.1)}
          >
            <ZoomIn className="size-4" />
          </WorkspaceControlButton>
          <WorkspaceControlButton
            aria-label="Zoom out"
            onClick={() => adjustScale(-0.1)}
          >
            <Minus className="size-4" />
          </WorkspaceControlButton>
          <WorkspaceControlButton
            aria-label="Center canvas"
            onClick={() => commitView(DEFAULT_VIEW)}
          >
            <Maximize className="size-4" />
          </WorkspaceControlButton>
          <WorkspaceControlButton
            aria-label="Undo"
            disabled={historyIndex === 0}
            onClick={() => restoreHistory(historyIndex - 1)}
          >
            <Undo2 className="size-4" />
          </WorkspaceControlButton>
          <WorkspaceControlButton
            aria-label="Redo"
            disabled={historyIndex === history.length - 1}
            onClick={() => restoreHistory(historyIndex + 1)}
          >
            <RotateCcw className="size-4 scale-x-[-1]" />
          </WorkspaceControlButton>
        </div>

        <WorkspaceControlButton
          active={showGuides}
          aria-label={showGuides ? "Hide guides" : "Show guides"}
          onClick={() => setShowGuides((v) => !v)}
        >
          <Layers3 className="size-4" />
        </WorkspaceControlButton>
      </div>

      {/* Canvas */}
      {workflow ? (
        <div
          className="relative h-full w-full"
          style={{
            transform: `translate(${view.x}px, ${view.y}px)`,
            transition: isDragging ? "none" : "transform 180ms ease-out",
          }}
        >
          <div
            className="relative"
            style={{
              transform: `scale(${view.scale})`,
              transformOrigin: "top left",
              transition: isDragging ? "none" : "transform 180ms ease-out",
            }}
          >
            <div className="pl-24 pt-[20vh]">
              <div className="relative inline-block">
                {/* Battleship image behind nodes */}
                <div
                  className="pointer-events-none absolute rounded-3xl opacity-[0.07]"
                  style={{
                    left: "-10px",
                    right: "-10px",
                    top: "50%",
                    transform: "translateY(-50%)",
                    aspectRatio: "1 / 1",
                    backgroundImage: "url('/battleship.webp')",
                    backgroundSize: "100% 100%",
                    backgroundRepeat: "no-repeat",
                  }}
                />
                <div className="relative flex items-center gap-0">
                  {workflow.nodes.map((node, i) => (
                  <div key={node.id} className="flex items-center">
                    {i > 0 && (
                      <Connector
                        active={
                          node.status === "completed" ||
                          node.status === "running" ||
                          (node.children?.[0]?.status === "completed" ||
                            node.children?.[0]?.status === "running") === true
                        }
                      />
                    )}
                    <AgentNode
                      node={node}
                      onClick={() => onNodeClick?.(node.id)}
                    />
                  </div>
                ))}
                </div>
              </div>
            </div>
          </div>
        </div>
      ) : (
        <div className="absolute inset-0 flex items-center justify-center pointer-events-none">
          <div className="flex flex-col items-center gap-3 text-center pointer-events-auto">
            <div className="flex size-16 items-center justify-center rounded-2xl border border-white/8 bg-white/[0.03]">
              <ArrowRight className="size-7 text-zinc-600" />
            </div>
            <h3 className="text-lg font-semibold text-zinc-200">
              No active battles
            </h3>
            <p className="max-w-xs text-sm text-zinc-600">
              Click &quot;+ Start New Battle&quot; to deploy your agent and watch the workflow in action
            </p>
          </div>
        </div>
      )}
    </section>
  );
}
