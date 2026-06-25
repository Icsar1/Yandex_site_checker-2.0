import { Badge } from "@/components/ui/badge";
import { cn } from "@/lib/utils";

interface StatusBadgeProps {
  status: string;
}

const workingStatuses = new Set([
  "collecting_keys",
  "forecasting",
  "generating_text",
  "rendering_pdf",
  "running",
  "processing",
]);

const statusLabels: Record<string, string> = {
  queued: "В очереди",
  collecting_keys: "Ключи",
  forecasting: "Прогноз",
  generating_text: "Текст",
  rendering_pdf: "PDF",
  done: "Готово",
  failed: "Ошибка",
  awaiting_manual: "Ждёт XLS",
  canceled: "Отменено",
  cancelled: "Отменено",
};

function statusClassName(status: string) {
  if (status === "done") {
    return "border-emerald-200 bg-emerald-50 text-emerald-700 dark:border-emerald-900/70 dark:bg-emerald-950/40 dark:text-emerald-300";
  }

  if (status === "failed") {
    return "border-red-200 bg-red-50 text-red-700 dark:border-red-900/70 dark:bg-red-950/40 dark:text-red-300";
  }

  if (status === "awaiting_manual") {
    return "border-amber-200 bg-amber-50 text-amber-700 dark:border-amber-900/70 dark:bg-amber-950/40 dark:text-amber-300";
  }

  if (status === "queued") {
    return "border-slate-200 bg-slate-50 text-slate-700 dark:border-slate-700 dark:bg-slate-900 dark:text-slate-300";
  }

  if (workingStatuses.has(status)) {
    return "border-blue-200 bg-blue-50 text-blue-700 dark:border-blue-900/70 dark:bg-blue-950/40 dark:text-blue-300";
  }

  return "border-slate-200 bg-slate-50 text-slate-700 dark:border-slate-700 dark:bg-slate-900 dark:text-slate-300";
}

export function getStatusLabel(status: string) {
  return statusLabels[status] ?? status;
}

export function StatusBadge({ status }: StatusBadgeProps) {
  const isWorking = workingStatuses.has(status);

  return (
    <Badge
      variant="outline"
      className={cn("gap-1.5 whitespace-nowrap", statusClassName(status))}
    >
      {isWorking ? (
        <span className="h-1.5 w-1.5 rounded-full bg-current animate-pulse" />
      ) : null}
      {getStatusLabel(status)}
    </Badge>
  );
}
