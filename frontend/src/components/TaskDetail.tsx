import { useMemo, useState } from "react";
import { Download, RotateCcw, Square, Upload } from "lucide-react";

import type { AdminEvent, TaskResponse } from "@/api/client";
import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
  DialogTrigger,
} from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { Separator } from "@/components/ui/separator";
import { StatusBadge } from "@/components/StatusBadge";

interface TaskDetailProps {
  task: TaskResponse;
  events: AdminEvent[];
  onRetry: (taskId: string) => Promise<void> | void;
  onCancel: (taskId: string) => Promise<void> | void;
  onUploadXls: (taskId: string, file: File) => Promise<void> | void;
}

function formatDate(value: string | null | undefined) {
  if (!value) {
    return "—";
  }

  return new Intl.DateTimeFormat("ru-RU", {
    day: "2-digit",
    month: "2-digit",
    year: "numeric",
    hour: "2-digit",
    minute: "2-digit",
  }).format(new Date(value));
}

function valueAsString(event: AdminEvent, keys: string[]) {
  for (const key of keys) {
    const value = event[key];

    if (typeof value === "string" && value.trim()) {
      return value;
    }

    if (typeof value === "number") {
      return String(value);
    }
  }

  return null;
}

export function TaskDetail({
  task,
  events,
  onRetry,
  onCancel,
  onUploadXls,
}: TaskDetailProps) {
  const [dialogOpen, setDialogOpen] = useState(false);
  const [file, setFile] = useState<File | null>(null);
  const [uploading, setUploading] = useState(false);

  const details = useMemo(
    () => [
      ["ID", task.id],
      ["Источник", task.source],
      ["Этап", task.stage ?? "—"],
      ["Прогресс", `${task.progress_pct}%`],
      ["Создано", formatDate(task.created_at)],
      ["Обновлено", formatDate(task.updated_at)],
    ],
    [task],
  );

  const submitUpload = async () => {
    if (!file) {
      return;
    }

    setUploading(true);
    try {
      await onUploadXls(task.id, file);
      setDialogOpen(false);
      setFile(null);
    } catch {
      // Уведомление об ошибке показывает родительский обработчик.
    } finally {
      setUploading(false);
    }
  };

  return (
    <div className="space-y-5 rounded-lg border bg-background/70 p-4">
      <div className="flex flex-col gap-3 md:flex-row md:items-start md:justify-between">
        <div className="space-y-1">
          <div className="flex flex-wrap items-center gap-2">
            <h3 className="text-lg font-semibold">{task.niche}</h3>
            <StatusBadge status={task.status} />
          </div>
          <p className="text-sm text-muted-foreground">{task.region_label}</p>
          {task.error_message ? (
            <p className="text-sm text-red-600 dark:text-red-300">
              {task.error_message}
            </p>
          ) : null}
        </div>

        <div className="flex flex-wrap gap-2">
          {task.download_url ? (
            <Button asChild size="sm" variant="outline">
              <a href={task.download_url} target="_blank" rel="noreferrer">
                <Download className="h-4 w-4" />
                PDF
              </a>
            </Button>
          ) : null}
          <Dialog open={dialogOpen} onOpenChange={setDialogOpen}>
            <DialogTrigger asChild>
              <Button size="sm" variant="outline">
                <Upload className="h-4 w-4" />
                XLS
              </Button>
            </DialogTrigger>
            <DialogContent>
              <DialogHeader>
                <DialogTitle>Загрузить XLS</DialogTitle>
                <DialogDescription>
                  Файл будет привязан к выбранной задаче.
                </DialogDescription>
              </DialogHeader>
              <Input
                type="file"
                accept=".xls,.xlsx"
                aria-label="Файл XLS"
                onChange={(event) => setFile(event.target.files?.[0] ?? null)}
              />
              <DialogFooter>
                <Button
                  type="button"
                  variant="outline"
                  onClick={() => setDialogOpen(false)}
                >
                  Отмена
                </Button>
                <Button type="button" disabled={!file || uploading} onClick={submitUpload}>
                  {uploading ? "Загрузка..." : "Загрузить"}
                </Button>
              </DialogFooter>
            </DialogContent>
          </Dialog>
          <Button size="sm" variant="outline" onClick={() => onRetry(task.id)}>
            <RotateCcw className="h-4 w-4" />
            Повторить
          </Button>
          <Button size="sm" variant="destructive" onClick={() => onCancel(task.id)}>
            <Square className="h-4 w-4" />
            Отменить
          </Button>
        </div>
      </div>

      <Separator />

      <div className="grid gap-3 text-sm md:grid-cols-3">
        {details.map(([label, value]) => (
          <div key={label} className="rounded-md border bg-card p-3">
            <p className="text-xs uppercase text-muted-foreground">{label}</p>
            <p className="mt-1 break-words font-medium">{value}</p>
          </div>
        ))}
      </div>

      <div className="space-y-3">
        <h4 className="text-sm font-semibold">События</h4>
        {events.length === 0 ? (
          <p className="text-sm text-muted-foreground">Событий пока нет.</p>
        ) : (
          <ol className="space-y-3">
            {events.map((event, index) => {
              const title =
                valueAsString(event, ["label", "message", "event", "type", "stage"]) ??
                "Событие";
              const eventTime = valueAsString(event, [
                "created_at",
                "timestamp",
                "time",
                "updated_at",
              ]);
              const status = valueAsString(event, ["status"]);

              return (
                <li key={`${title}-${index}`} className="flex gap-3 text-sm">
                  <span className="mt-1 h-2.5 w-2.5 shrink-0 rounded-full bg-primary" />
                  <div>
                    <p className="font-medium">{title}</p>
                    <p className="text-muted-foreground">
                      {eventTime ? formatDate(eventTime) : "Время не указано"}
                      {status ? ` · ${status}` : ""}
                    </p>
                  </div>
                </li>
              );
            })}
          </ol>
        )}
      </div>
    </div>
  );
}
