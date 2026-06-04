"use client";

import * as React from "react";
import {
  IconCamera,
  IconChartBar,
  IconDashboard,
  IconDatabase,
  IconFileAi,
  IconFileDescription,
  IconFileWord,
  IconFolder,
  IconHelp,
  IconInnerShadowTop,
  IconListDetails,
  IconReport,
  IconSearch,
  IconSettings,
  IconUsers,
} from "@tabler/icons-react";

import { NavMain } from "@/components/nav-main";
import { NavSecondary } from "@/components/nav-secondary";
import {
  Sidebar,
  SidebarContent,
  SidebarFooter,
  SidebarHeader,
  SidebarMenu,
  SidebarMenuButton,
  SidebarMenuItem,
} from "@/components/ui/sidebar";
import { Logo } from "@/components/logo";

import {
  RiHome6Line,
  RiShip2Line,
  RiDonutChartFill,
  RiSettings6Line,
  RiHeartLine,
} from "@remixicon/react";

const data = {
  user: {
    name: "shadcn",
    email: "m@example.com",
    avatar: "/avatars/shadcn.jpg",
  },
  navMain: [
    {
      title: "Dashboard",
      url: "/dashboard",
      icon: RiHome6Line,
    },
    {
      title: "Battle Arena",
      url: "/battle-arena",
      icon: RiShip2Line,
    },
    {
      title: "Battle Analytics",
      url: "/battle-analytics",
      icon: RiDonutChartFill,
    },
    {
      title: "Status",
      url: "#",
      icon: RiHeartLine,
    },
    {
      title: "Settings",
      url: "/settings",
      icon: RiSettings6Line,
    },
  ],
};

export function AppSidebar({ ...props }: React.ComponentProps<typeof Sidebar>) {
  return (
    <Sidebar collapsible="offcanvas" {...props}>
      <SidebarHeader className="items-start">
        <SidebarMenu>
          <SidebarMenuItem>
            <Logo className="-ml-2" />
          </SidebarMenuItem>
        </SidebarMenu>
      </SidebarHeader>
      <SidebarContent>
        <NavMain items={data.navMain} />
      </SidebarContent>
    </Sidebar>
  );
}
