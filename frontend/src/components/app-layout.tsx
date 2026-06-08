import { useState } from "react";
import { Link, Outlet, useRouterState } from "@tanstack/react-router";
import {
  LayoutDashboard,
  Briefcase,
  ListChecks,
  Building2,
  GraduationCap,
  FileText,
  Settings,
  Send,
  Menu,
  Sun,
  Moon,
} from "lucide-react";
import { cn } from "@/lib/cn";
import { useThemeStore } from "@/lib/theme";
import { Button } from "./ui/button";

type NavItem = { to: string; label: string; icon: React.ElementType };

const NAV: NavItem[] = [
  { to: "/", label: "Dashboard", icon: LayoutDashboard },
  { to: "/jobs", label: "Jobs", icon: Briefcase },
  { to: "/applications", label: "Applications", icon: ListChecks },
  { to: "/companies", label: "Companies", icon: Building2 },
  { to: "/skill-gaps", label: "Skill Gaps", icon: GraduationCap },
  { to: "/resume", label: "Resume", icon: FileText },
  { to: "/settings", label: "Settings", icon: Settings },
  { to: "/telegram", label: "Telegram", icon: Send },
];

function ThemeToggle() {
  const theme = useThemeStore((s) => s.theme);
  const toggle = useThemeStore((s) => s.toggle);
  return (
    <Button
      variant="ghost"
      size="icon"
      onClick={toggle}
      aria-label="Toggle theme"
      data-testid="theme-toggle"
    >
      {theme === "dark" ? <Sun className="h-4 w-4" /> : <Moon className="h-4 w-4" />}
    </Button>
  );
}

function SidebarNav({ onNavigate }: { onNavigate?: () => void }) {
  const pathname = useRouterState({ select: (s) => s.location.pathname });
  return (
    <nav aria-label="Primary" className="flex flex-col gap-0.5 p-3">
      {NAV.map((it) => {
        const active =
          it.to === "/" ? pathname === "/" : pathname.startsWith(it.to);
        const Icon = it.icon;
        return (
          <Link
            key={it.to}
            to={it.to}
            onClick={onNavigate}
            className={cn(
              "flex items-center gap-3 rounded-md px-3 py-2 text-sm font-medium transition-colors",
              active
                ? "bg-primary text-primary-foreground"
                : "text-muted-foreground hover:bg-accent hover:text-accent-foreground",
            )}
            data-active={active}
            data-testid={`nav-${it.to.replace(/\//g, "") || "dashboard"}`}
          >
            <Icon className="h-4 w-4" />
            <span>{it.label}</span>
          </Link>
        );
      })}
    </nav>
  );
}

export function AppLayout() {
  const [mobileOpen, setMobileOpen] = useState(false);
  return (
    <div className="flex h-full">
      <aside className="hidden md:flex w-60 shrink-0 flex-col border-r border-border bg-card">
        <div className="px-5 h-14 flex items-center border-b border-border">
          <Link to="/" className="font-bold tracking-tight text-lg">
            Job<span className="text-primary">Forge</span>
          </Link>
        </div>
        <SidebarNav />
        <div className="mt-auto p-3 text-xs text-muted-foreground">v0.1.0</div>
      </aside>

      <div className="flex-1 flex flex-col min-w-0">
        <header className="h-14 flex items-center justify-between gap-2 border-b border-border bg-card px-3 sm:px-6">
          <div className="flex items-center gap-2">
            <Button
              variant="ghost"
              size="icon"
              className="md:hidden"
              aria-label="Open menu"
              onClick={() => setMobileOpen((v) => !v)}
            >
              <Menu className="h-4 w-4" />
            </Button>
            <Link to="/" className="md:hidden font-bold tracking-tight">
              Job<span className="text-primary">Forge</span>
            </Link>
          </div>
          <div className="flex items-center gap-1">
            <ThemeToggle />
          </div>
        </header>

        {mobileOpen && (
          <div className="md:hidden border-b border-border bg-card">
            <SidebarNav onNavigate={() => setMobileOpen(false)} />
          </div>
        )}

        <main className="flex-1 overflow-y-auto p-4 sm:p-6 lg:p-8">
          <Outlet />
        </main>
      </div>
    </div>
  );
}
