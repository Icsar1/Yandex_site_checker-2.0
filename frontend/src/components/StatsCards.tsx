import { AlertTriangle, BarChart3, CheckCircle2, Clock, Timer } from "lucide-react";

import type { AdminStats } from "@/api/client";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";

interface StatsCardsProps {
  stats: AdminStats;
}

function formatSeconds(value: number) {
  if (!Number.isFinite(value) || value <= 0) {
    return "0 с";
  }

  if (value < 60) {
    return `${Math.round(value)} с`;
  }

  const minutes = Math.floor(value / 60);
  const seconds = Math.round(value % 60);
  return `${minutes} мин ${seconds} с`;
}

export function StatsCards({ stats }: StatsCardsProps) {
  const inProgress = Object.entries(stats.by_status)
    .filter(([status]) => !["done", "failed", "awaiting_manual"].includes(status))
    .reduce((sum, [, count]) => sum + count, 0);

  const problemCount = stats.failed + stats.awaiting_manual;

  const cards = [
    {
      label: "Всего",
      value: stats.total,
      caption: "Все заявки",
      icon: BarChart3,
    },
    {
      label: "Успешно",
      value: stats.done,
      caption: `${stats.success_rate_pct.toFixed(1)}%`,
      icon: CheckCircle2,
    },
    {
      label: "В работе",
      value: inProgress,
      caption: "Активные этапы",
      icon: Clock,
    },
    {
      label: "Проблемы",
      value: problemCount,
      caption: `${stats.failed} ошибок · ${stats.awaiting_manual} ждёт XLS`,
      icon: AlertTriangle,
    },
  ];

  return (
    <div className="space-y-6">
      <div className="grid gap-4 md:grid-cols-2 xl:grid-cols-4">
        {cards.map(({ label, value, caption, icon: Icon }) => (
          <Card key={label} className="bg-card/80">
            <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
              <CardTitle className="text-sm font-medium text-muted-foreground">
                {label}
              </CardTitle>
              <Icon className="h-4 w-4 text-muted-foreground" />
            </CardHeader>
            <CardContent>
              <div className="text-3xl font-bold">{value}</div>
              <p className="mt-1 text-sm text-muted-foreground">{caption}</p>
            </CardContent>
          </Card>
        ))}
      </div>

      <div className="grid gap-4 md:grid-cols-2">
        <Card className="bg-card/80">
          <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
            <CardTitle className="text-sm font-medium text-muted-foreground">
              Медианное время
            </CardTitle>
            <Timer className="h-4 w-4 text-muted-foreground" />
          </CardHeader>
          <CardContent>
            <div className="text-2xl font-bold">
              {formatSeconds(stats.median_seconds)}
            </div>
          </CardContent>
        </Card>
        <Card className="bg-card/80">
          <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
            <CardTitle className="text-sm font-medium text-muted-foreground">
              P95 время
            </CardTitle>
            <Timer className="h-4 w-4 text-muted-foreground" />
          </CardHeader>
          <CardContent>
            <div className="text-2xl font-bold">
              {formatSeconds(stats.p95_seconds)}
            </div>
          </CardContent>
        </Card>
      </div>
    </div>
  );
}
