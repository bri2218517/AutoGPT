"use client";

import {
  IconAutoGPTLogo,
  IconAutoGPTLogoMinimal,
} from "@/components/__legacy__/ui/icons";
import {
  Sidebar,
  SidebarContent,
  SidebarFooter,
  SidebarGroup,
  SidebarGroupContent,
  SidebarHeader,
  SidebarMenu,
  SidebarMenuButton,
  SidebarMenuItem,
  SidebarSeparator,
  SidebarTrigger,
  useSidebar,
} from "@/components/ui/sidebar";
import {
  Tooltip,
  TooltipContent,
  TooltipTrigger,
} from "@/components/ui/tooltip";
import { NAVBAR_HEIGHT_PX } from "@/lib/constants";
import { cn } from "@/lib/utils";
import { useSupabase } from "@/lib/supabase/hooks/useSupabase";
import { Flag, useGetFlag } from "@/services/feature-flags/use-get-flag";
import {
  Sparkle,
  TreeStructure,
  Compass,
  Wrench,
  GearSix,
} from "@phosphor-icons/react";
import Link from "next/link";
import { usePathname } from "next/navigation";
import { ReactNode } from "react";
import { useGetV2GetUserProfile } from "@/app/api/__generated__/endpoints/store/store";
import { okData } from "@/app/api/helpers";
import { isLogoutInProgress } from "@/lib/autogpt-server-api/helpers";
import { FeedbackButton } from "@/components/layout/Navbar/components/FeedbackButton";
import { AgentActivityDropdown } from "@/components/layout/Navbar/components/AgentActivityDropdown/AgentActivityDropdown";
import { AccountMenu } from "@/components/layout/Navbar/components/AccountMenu/AccountMenu";
import { getAccountMenuItems } from "@/components/layout/Navbar/helpers";
import { useLayout } from "@/components/layout/LayoutContext";

interface Props {
  dynamicContent?: ReactNode;
}

export function AppSidebar({ dynamicContent }: Props) {
  const { layout } = useLayout();
  const { state } = useSidebar();
  const isCollapsed = state === "collapsed";
  const pathname = usePathname();
  const isChatEnabled = useGetFlag(Flag.CHAT);
  const { user, isLoggedIn, isUserLoading } = useSupabase();
  const logoutInProgress = isLogoutInProgress();
  const dynamicMenuItems = getAccountMenuItems(user?.role);

  const { data: profile, isLoading: isProfileLoading } =
    useGetV2GetUserProfile({
      query: {
        select: okData,
        enabled: isLoggedIn && !!user && !logoutInProgress,
        queryKey: ["/api/store/profile", user?.id],
      },
    });

  const isLoadingProfile = isProfileLoading || isUserLoading;
  const isModern = layout === "modern";

  const homeHref = isChatEnabled === true ? "/copilot" : "/library";

  const navLinks = [
    isChatEnabled === true
      ? {
          name: "Copilot",
          href: "/copilot",
          icon: Sparkle,
          testId: "sidebar-link-copilot",
        }
      : {
          name: "Library",
          href: "/library",
          icon: TreeStructure,
          testId: "sidebar-link-library",
        },
    ...(isChatEnabled === true
      ? [
          {
            name: "Workflows",
            href: "/library",
            icon: TreeStructure,
            testId: "sidebar-link-workflows",
          },
        ]
      : []),
    {
      name: "Explore",
      href: "/marketplace",
      icon: Compass,
      testId: "sidebar-link-marketplace",
    },
    {
      name: "Builder",
      href: "/build",
      icon: Wrench,
      testId: "sidebar-link-build",
    },
    ...(!isModern
      ? [
          {
            name: "Settings",
            href: "/profile/settings",
            icon: GearSix,
            testId: "sidebar-link-settings",
          },
        ]
      : []),
  ];

  function isActive(href: string) {
    if (href === homeHref) {
      return pathname === "/" || pathname.startsWith(homeHref);
    }
    return pathname.startsWith(href);
  }

  if (!isLoggedIn) return null;

  return (
    <Sidebar
      variant="sidebar"
      collapsible="icon"
      className="border-r border-zinc-100"
    >
      {/* Header */}
      <SidebarHeader
        className={cn(
          "!flex-row border-b border-zinc-100 px-3",
          isCollapsed
            ? "items-center justify-center py-0"
            : "items-center py-0",
          isModern && (isCollapsed ? "py-3" : "py-3"),
        )}
        style={!isModern ? { height: NAVBAR_HEIGHT_PX } : undefined}
      >
        {!isCollapsed && (
          <div className="flex w-full items-center justify-between">
            <Link href={homeHref}>
              {isModern ? (
                <IconAutoGPTLogoMinimal className="h-8 w-8" />
              ) : (
                <IconAutoGPTLogo className="h-8 w-24" />
              )}
            </Link>
            <div className="flex items-center gap-1">
              {isModern && <AgentActivityDropdown />}
              <Tooltip>
                <TooltipTrigger asChild>
                  <SidebarTrigger className="size-10 p-2 hover:bg-sidebar-accent hover:text-sidebar-accent-foreground [&>svg]:!size-5" />
                </TooltipTrigger>
                <TooltipContent side="right">Close sidebar</TooltipContent>
              </Tooltip>
            </div>
          </div>
        )}
        {isCollapsed && (
          <div className={cn(isModern && "flex flex-col items-center gap-2")}>
            {isModern && (
              <Link href={homeHref}>
                <IconAutoGPTLogoMinimal className="h-6 w-6" />
              </Link>
            )}
            <Tooltip>
              <TooltipTrigger asChild>
                <SidebarTrigger
                  className={cn(
                    "hover:bg-sidebar-accent hover:text-sidebar-accent-foreground",
                    isModern
                      ? "size-8 p-1.5 [&>svg]:!size-4"
                      : "size-10 p-2 [&>svg]:!size-5",
                  )}
                />
              </TooltipTrigger>
              <TooltipContent side="right">Open sidebar</TooltipContent>
            </Tooltip>
          </div>
        )}
      </SidebarHeader>

      {/* Navigation links */}
      <SidebarContent>
        <SidebarGroup>
          <SidebarGroupContent>
            <SidebarMenu className={cn(isCollapsed && "gap-3")}>
              {navLinks.map((link) => (
                <SidebarMenuItem key={link.name}>
                  <SidebarMenuButton
                    asChild
                    isActive={isActive(link.href)}
                    tooltip={link.name}
                    className="py-5 data-[active=true]:bg-violet-50 data-[active=true]:font-normal data-[active=true]:text-violet-700"
                  >
                    <Link href={link.href} data-testid={link.testId}>
                      <link.icon className="!size-5" weight="regular" />
                      <span>{link.name}</span>
                    </Link>
                  </SidebarMenuButton>
                </SidebarMenuItem>
              ))}
            </SidebarMenu>
          </SidebarGroupContent>
        </SidebarGroup>

        <SidebarSeparator className="mx-0" />

        {dynamicContent && (
          <SidebarGroup className="flex-1 overflow-hidden">
            {!isCollapsed && (
              <SidebarGroupContent className="h-full overflow-y-auto [-ms-overflow-style:none] [scrollbar-width:none] [&::-webkit-scrollbar]:hidden">
                {dynamicContent}
              </SidebarGroupContent>
            )}
          </SidebarGroup>
        )}
      </SidebarContent>

      {/* Footer: only in modern layout */}
      {isModern && (
        <SidebarFooter className="border-t border-zinc-100 p-3">
          {!isCollapsed ? (
            <div className="flex items-center justify-between">
              <AccountMenu
                userName={profile?.username}
                userEmail={profile?.name}
                avatarSrc={profile?.avatar_url ?? ""}
                menuItemGroups={dynamicMenuItems}
                isLoading={isLoadingProfile}
              />
              <FeedbackButton />
            </div>
          ) : (
            <div className="flex flex-col items-center gap-3">
              <AccountMenu
                userName={profile?.username}
                userEmail={profile?.name}
                avatarSrc={profile?.avatar_url ?? ""}
                menuItemGroups={dynamicMenuItems}
                isLoading={isLoadingProfile}
              />
            </div>
          )}
        </SidebarFooter>
      )}
    </Sidebar>
  );
}
