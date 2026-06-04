"use client";

import { useState } from "react";
import { usePathname, useRouter } from "next/navigation";

import { Button } from "@/components/ui/button";
import { Separator } from "@/components/ui/separator";
import { SidebarTrigger } from "@/components/ui/sidebar";
import {
  AlertDialog,
  AlertDialogAction,
  AlertDialogCancel,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogHeader,
  AlertDialogTitle,
} from "@/components/ui/alert-dialog";
import { createBattle } from "@/lib/supabase";

const ROUTE_TITLES = [
  { prefix: "/dashboard", title: "Dashboard" },
  { prefix: "/battle-arena", title: "Battle Arena" },
  { prefix: "/battle-analytics", title: "" },
  { prefix: "/analytics", title: "Analytics" },
  { prefix: "/settings", title: "Settings" },
];

function getPageTitle(pathname: string) {
  const match = ROUTE_TITLES.find(
    (route) =>
      pathname === route.prefix || pathname.startsWith(`${route.prefix}/`),
  );

  return match?.title ?? "Documents";
}

export function SiteHeader({ analyticsBattleId }: { analyticsBattleId?: string } = {}) {
  const pathname = usePathname();
  const router = useRouter();
  const pageTitle = getPageTitle(pathname);
  const [confirmOpen, setConfirmOpen] = useState(false);
  const [deploying, setDeploying] = useState(false);
  const [countdown, setCountdown] = useState<number | null>(null);

  const handleDeploy = async () => {
    setDeploying(true);
    setCountdown(3);

    // Countdown 3 → 2 → 1
    for (let i = 3; i >= 1; i--) {
      setCountdown(i);
      await new Promise((r) => setTimeout(r, 1000));
    }
    setCountdown(null);

    const battle = await createBattle();

    if (battle) {
      fetch("/api/battle/start", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ battleId: battle.battle_id }),
      }).catch((err) => console.error("Failed to start engine:", err));

      setDeploying(false);
      setConfirmOpen(false);
      router.push(`/battle-arena?id=${battle.battle_id}`);
    } else {
      setDeploying(false);
    }
  };

  return (
    <>
      <header className="flex h-(--header-height) shrink-0 items-center gap-2 border-b transition-[width,height] ease-linear group-has-data-[collapsible=icon]/sidebar-wrapper:h-(--header-height)">
        <div className="flex w-full items-center gap-1 px-4 lg:gap-2 lg:px-6">
          <SidebarTrigger className="-ml-1" />
          <Separator
            orientation="vertical"
            className="mx-2 data-[orientation=vertical]:h-4"
          />
          <h1 className="text-base font-medium">{pageTitle}</h1>
          <div className="ml-auto flex items-center gap-2">
            {analyticsBattleId && (
              <Button
                variant="outline"
                size="sm"
                className="hidden sm:flex"
                onClick={() => router.push(`/battle-analytics?id=${analyticsBattleId}`)}
              >
                Get Battle Analysis
              </Button>
            )}
            <Button
              size="sm"
              className="hidden bg-white text-black hover:bg-white/90 sm:flex"
              onClick={() => setConfirmOpen(true)}
            >
              + Start New Battle
            </Button>
          </div>
        </div>
      </header>

      <AlertDialog open={confirmOpen} onOpenChange={(open) => { if (!deploying) setConfirmOpen(open); }}>
        <AlertDialogContent>
          <AlertDialogHeader>
            <AlertDialogTitle>Are you absolutely sure?</AlertDialogTitle>
            <AlertDialogDescription>
              Wars cost lives and should be avoided at all costs. But if diplomacy has failed and the fleet is ready, there is no turning back. This will deploy your agent into live combat against the opponent roster.
            </AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter>
            <AlertDialogCancel disabled={deploying}>Stand Down</AlertDialogCancel>
            <Button onClick={handleDeploy} disabled={deploying}>
              {countdown !== null
                ? `Deploying Fleet in ${countdown}...`
                : deploying
                  ? "Deploying..."
                  : "Deploy Fleet"}
            </Button>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>
    </>
  );
}
