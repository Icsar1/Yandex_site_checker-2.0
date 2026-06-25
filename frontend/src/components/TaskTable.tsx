import { Fragment } from "react";
import { ChevronDown, ChevronRight } from "lucide-react";

import type { AdminEvent, TaskResponse } from "@/api/client";
import { Button } from "@/components/ui/button";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import { StatusBadge } from "@/components/StatusBadge";
import { TaskDetail } from "@/components/TaskDetail";
import { cn } from "@/lib/utils";

export interface TaskDetailsData {
  task: TaskResponse;
  events: AdminEvent[];
}

interface TaskTableProps {
  tasks: TaskResponse[];
  offset: number;
  expandedTaskId: string | null;
  detailsById: Record<string, TaskDetailsData>;
  loadingDetailsId: string | null;
  onExpand: (taskId: string) => void;
  onRetry: (taskId: string) => Promise<void> | void;
  onCancel: (taskId: string) => Promise<void> | void;
  onUploadXls: (taskId: string, file: File) => Promise<void> | void;
}

function formatDate(value: string) {
  return new Intl.DateTimeFormat("ru-RU", {
    day: "2-digit",
    month: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
  }).format(new Date(value));
}

function formatDuration(task: TaskResponse) {
  const start = new Date(task.created_at).getTime();
  const end = new Date(task.updated_at).getTime();
  const diffSeconds = Math.max(0, Math.round((end - start) / 1000));

  if (diffSeconds < 60) {
    return `${diffSeconds} с`;
  }

  return `${Math.floor(diffSeconds / 60)} мин ${diffSeconds % 60} с`;
}

export function TaskTable({
  tasks,
  offset,
  expandedTaskId,
  detailsById,
  loadingDetailsId,
  onExpand,
  onRetry,
  onCancel,
  onUploadXls,
}: TaskTableProps) {
  if (tasks.length === 0) {
    return (
      <div className="rounded-lg border bg-card p-8 text-center text-sm text-muted-foreground">
        Задачи не найдены.
      </div>
    );
  }

  return (
    <Table>
      <TableHeader>
        <TableRow>
          <TableHead className="w-14">#</TableHead>
          <TableHead>Дата</TableHead>
          <TableHead>Ниша</TableHead>
          <TableHead>Регион</TableHead>
          <TableHead>Контакт</TableHead>
          <TableHead>Статус</TableHead>
          <TableHead>Время</TableHead>
          <TableHead className="text-right">Действия</TableHead>
        </TableRow>
      </TableHeader>
      <TableBody>
        {tasks.map((task, index) => {
          const expanded = expandedTaskId === task.id;
          const details = detailsById[task.id];

          return (
            <Fragment key={task.id}>
              <TableRow
                className={cn("cursor-pointer", expanded && "bg-muted/40")}
                onClick={() => onExpand(task.id)}
              >
                <TableCell className="font-medium">{offset + index + 1}</TableCell>
                <TableCell className="whitespace-nowrap">
                  {formatDate(task.created_at)}
                </TableCell>
                <TableCell className="min-w-48 font-medium">{task.niche}</TableCell>
                <TableCell className="min-w-40">{task.region_label}</TableCell>
                <TableCell className="min-w-40 text-muted-foreground">
                  {task.contact || "—"}
                </TableCell>
                <TableCell>
                  <StatusBadge status={task.status} />
                </TableCell>
                <TableCell className="whitespace-nowrap">
                  {formatDuration(task)}
                </TableCell>
                <TableCell className="text-right">
                  <Button
                    type="button"
                    size="sm"
                    variant="ghost"
                    aria-label={expanded ? "Свернуть задачу" : "Открыть задачу"}
                    onClick={(event) => {
                      event.stopPropagation();
                      onExpand(task.id);
                    }}
                  >
                    {expanded ? (
                      <ChevronDown className="h-4 w-4" />
                    ) : (
                      <ChevronRight className="h-4 w-4" />
                    )}
                  </Button>
                </TableCell>
              </TableRow>
              {expanded ? (
                <TableRow className="hover:bg-transparent">
                  <TableCell colSpan={8} className="p-4">
                    {loadingDetailsId === task.id && !details ? (
                      <div className="rounded-lg border bg-background/70 p-4 text-sm text-muted-foreground">
                        Загрузка деталей...
                      </div>
                    ) : details ? (
                      <TaskDetail
                        task={details.task}
                        events={details.events}
                        onRetry={onRetry}
                        onCancel={onCancel}
                        onUploadXls={onUploadXls}
                      />
                    ) : (
                      <div className="rounded-lg border bg-background/70 p-4 text-sm text-muted-foreground">
                        Детали недоступны.
                      </div>
                    )}
                  </TableCell>
                </TableRow>
              ) : null}
            </Fragment>
          );
        })}
      </TableBody>
    </Table>
  );
}
