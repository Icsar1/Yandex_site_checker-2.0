import type { ReactNode } from "react";
import { Link } from "react-router-dom";
import { BarChart3 } from "lucide-react";

import { ThemeToggle } from "@/components/ThemeToggle";
import { cn } from "@/lib/utils";

interface LayoutProps {
  children: ReactNode;
  actions?: ReactNode;
  admin?: boolean;
  className?: string;
}

export function Layout({ children, actions, admin = false, className }: LayoutProps) {
  return (
    <div
      className={cn(
        "min-h-screen bg-background text-foreground transition-colors duration-300",
        admin && "dark:bg-[#0D1117]",
      )}
    >
      <header
        className={cn(
          "sticky top-0 z-40 border-b bg-background/90 backdrop-blur",
          admin && "dark:border-[#21262D] dark:bg-[#0D1117]/90",
        )}
      >
        <div className="mx-auto flex h-16 max-w-7xl items-center justify-between gap-4 px-4 sm:px-6 lg:px-8">
          <Link to="/" className="flex min-w-0 items-center gap-3 font-semibold">
            <span className="flex h-9 w-9 shrink-0 items-center justify-center rounded-md bg-primary text-primary-foreground">
              <BarChart3 className="h-5 w-5" />
            </span>
            <span className="truncate">Медиаплан</span>
          </Link>
          <div className="flex items-center gap-2">
            {actions}
            <ThemeToggle />
          </div>
        </div>
      </header>
      <main className={cn("mx-auto w-full max-w-7xl px-4 py-8 sm:px-6 lg:px-8", className)}>
        {children}
      </main>
    </div>
  );
}
