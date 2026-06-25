import { FormEvent, useCallback, useEffect, useMemo, useState } from "react";
import { Loader2, LogOut, ShieldCheck } from "lucide-react";

import {
  AdminAuthError,
  ApiError,
  adminLogin,
  adminLogout,
  cancelTask,
  getAdminStats,
  getAdminTask,
  getAdminTasks,
  retryTask,
  uploadXls,
  type AdminStats,
  type TaskResponse,
} from "@/api/client";
import { Layout } from "@/components/Layout";
import { StatsCards } from "@/components/StatsCards";
import { TaskTable, type TaskDetailsData } from "@/components/TaskTable";
import { ThemeToggle } from "@/components/ThemeToggle";
import { Button } from "@/components/ui/button";
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { toast } from "@/components/ui/toast";
import { cn } from "@/lib/utils";

const PAGE_SIZE = 25;

type StatusFilter = "all" | "active" | "done" | "failed" | "awaiting_manual";

const activeStatuses = [
  "queued",
  "collecting_keys",
  "forecasting",
  "generating_text",
  "rendering_pdf",
  "running",
  "processing",
];

const filters: Array<{ value: StatusFilter; label: string }> = [
  { value: "all", label: "Все" },
  { value: "active", label: "В работе" },
  { value: "done", label: "Готово" },
  { value: "failed", label: "Ошибка" },
  { value: "awaiting_manual", label: "Ждёт XLS" },
];

function loginErrorMessage(caught: unknown) {
  if (caught instanceof ApiError) {
    if (caught.status === 401) {
      return "Неверный пароль.";
    }

    if (caught.status === 429) {
      return "Слишком много попыток. Попробуйте позже.";
    }

    return caught.message;
  }

  return caught instanceof Error ? caught.message : "Не удалось войти";
}

function sortTasksDesc(tasks: TaskResponse[]) {
  return [...tasks].sort(
    (a, b) =>
      new Date(b.created_at).getTime() - new Date(a.created_at).getTime(),
  );
}

export function Access() {
  const [checking, setChecking] = useState(true);
  const [authenticated, setAuthenticated] = useState(false);
  const [password, setPassword] = useState("");
  const [loginError, setLoginError] = useState<string | null>(null);
  const [loggingIn, setLoggingIn] = useState(false);

  const [tasks, setTasks] = useState<TaskResponse[]>([]);
  const [total, setTotal] = useState(0);
  const [stats, setStats] = useState<AdminStats | null>(null);
  const [statusFilter, setStatusFilter] = useState<StatusFilter>("all");
  const [page, setPage] = useState(0);
  const [loadingTasks, setLoadingTasks] = useState(false);
  const [loadingStats, setLoadingStats] = useState(false);
  const [dashboardError, setDashboardError] = useState<string | null>(null);
  const [expandedTaskId, setExpandedTaskId] = useState<string | null>(null);
  const [detailsById, setDetailsById] = useState<Record<string, TaskDetailsData>>({});
  const [loadingDetailsId, setLoadingDetailsId] = useState<string | null>(null);

  const totalPages = Math.max(1, Math.ceil(total / PAGE_SIZE));

  const handleAuthError = useCallback((caught: unknown) => {
    if (caught instanceof AdminAuthError) {
      setAuthenticated(false);
      setPassword("");
      setDashboardError(null);
      setLoginError("Сессия истекла. Войдите ещё раз.");
      return true;
    }

    return false;
  }, []);

  const loadStats = useCallback(async () => {
    setLoadingStats(true);
    try {
      const nextStats = await getAdminStats();
      setStats(nextStats);
    } catch (caught) {
      if (!handleAuthError(caught)) {
        setDashboardError(
          caught instanceof Error ? caught.message : "Не удалось загрузить статистику",
        );
      }
    } finally {
      setLoadingStats(false);
    }
  }, [handleAuthError]);

  const loadTasks = useCallback(async () => {
    setLoadingTasks(true);
    setDashboardError(null);

    try {
      const offset = page * PAGE_SIZE;

      if (statusFilter === "active") {
        const fetchLimit = offset + PAGE_SIZE;
        const responses = await Promise.all(
          activeStatuses.map((status) =>
            getAdminTasks({ status, limit: fetchLimit, offset: 0 }),
          ),
        );
        const merged = sortTasksDesc(responses.flatMap((response) => response.items));
        setTasks(merged.slice(offset, offset + PAGE_SIZE));
        setTotal(responses.reduce((sum, response) => sum + response.total, 0));
      } else {
        const status = statusFilter === "all" ? undefined : statusFilter;
        const response = await getAdminTasks({
          status,
          limit: PAGE_SIZE,
          offset,
        });
        setTasks(response.items);
        setTotal(response.total);
      }
    } catch (caught) {
      if (!handleAuthError(caught)) {
        setDashboardError(
          caught instanceof Error ? caught.message : "Не удалось загрузить задачи",
        );
      }
    } finally {
      setLoadingTasks(false);
    }
  }, [handleAuthError, page, statusFilter]);

  useEffect(() => {
    let active = true;

    void getAdminStats()
      .then((nextStats) => {
        if (!active) {
          return;
        }

        setStats(nextStats);
        setAuthenticated(true);
      })
      .catch((caught) => {
        if (!active) {
          return;
        }

        if (!(caught instanceof AdminAuthError)) {
          setLoginError(
            caught instanceof Error
              ? caught.message
              : "Не удалось проверить сессию",
          );
        }
      })
      .finally(() => {
        if (active) {
          setChecking(false);
        }
      });

    return () => {
      active = false;
    };
  }, []);

  useEffect(() => {
    if (!authenticated) {
      return;
    }

    void loadStats();
  }, [authenticated, loadStats]);

  useEffect(() => {
    if (!authenticated) {
      return;
    }

    void loadTasks();
  }, [authenticated, loadTasks]);

  const submitLogin = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    setLoginError(null);
    setLoggingIn(true);

    try {
      await adminLogin(password);
      setPassword("");
      setAuthenticated(true);
    } catch (caught) {
      setLoginError(loginErrorMessage(caught));
    } finally {
      setLoggingIn(false);
    }
  };

  const logout = async () => {
    try {
      await adminLogout();
    } catch {
      // Состояние интерфейса всё равно переводим на логин.
    } finally {
      setAuthenticated(false);
      setPassword("");
      setTasks([]);
      setStats(null);
      setExpandedTaskId(null);
      setDetailsById({});
    }
  };

  const expandTask = async (taskId: string) => {
    if (expandedTaskId === taskId) {
      setExpandedTaskId(null);
      return;
    }

    setExpandedTaskId(taskId);

    if (detailsById[taskId]) {
      return;
    }

    setLoadingDetailsId(taskId);
    try {
      const details = await getAdminTask(taskId);
      setDetailsById((current) => ({ ...current, [taskId]: details }));
    } catch (caught) {
      if (!handleAuthError(caught)) {
        toast({
          title: "Не удалось открыть задачу",
          description: caught instanceof Error ? caught.message : undefined,
          variant: "destructive",
        });
      }
    } finally {
      setLoadingDetailsId(null);
    }
  };

  const refreshAfterAction = async () => {
    await Promise.all([loadTasks(), loadStats()]);
    if (expandedTaskId) {
      try {
        const details = await getAdminTask(expandedTaskId);
        setDetailsById((current) => ({ ...current, [expandedTaskId]: details }));
      } catch (caught) {
        handleAuthError(caught);
      }
    }
  };

  const retry = async (taskId: string) => {
    try {
      await retryTask(taskId);
      toast({ title: "Задача отправлена на повтор" });
      await refreshAfterAction();
    } catch (caught) {
      if (!handleAuthError(caught)) {
        toast({
          title: "Не удалось повторить задачу",
          description: caught instanceof Error ? caught.message : undefined,
          variant: "destructive",
        });
      }
    }
  };

  const cancel = async (taskId: string) => {
    try {
      await cancelTask(taskId);
      toast({ title: "Задача отменена" });
      await refreshAfterAction();
    } catch (caught) {
      if (!handleAuthError(caught)) {
        toast({
          title: "Не удалось отменить задачу",
          description: caught instanceof Error ? caught.message : undefined,
          variant: "destructive",
        });
      }
    }
  };

  const upload = async (taskId: string, file: File) => {
    try {
      const result = await uploadXls(taskId, file);
      toast({
        title: "XLS загружен",
        description: `Распознано строк: ${result.parsed_rows}`,
      });
      await refreshAfterAction();
    } catch (caught) {
      if (!handleAuthError(caught)) {
        toast({
          title: "Не удалось загрузить XLS",
          description: caught instanceof Error ? caught.message : undefined,
          variant: "destructive",
        });
      }
      throw caught;
    }
  };

  const headerActions = useMemo(
    () => (
      <Button type="button" variant="outline" size="sm" onClick={logout}>
        <LogOut className="h-4 w-4" />
        Выйти
      </Button>
    ),
    [],
  );

  if (checking) {
    return (
      <div className="flex min-h-screen items-center justify-center bg-background text-foreground">
        <p className="flex items-center gap-2 text-sm text-muted-foreground">
          <Loader2 className="h-4 w-4 animate-spin" />
          Проверяем доступ...
        </p>
      </div>
    );
  }

  if (!authenticated) {
    return (
      <main className="flex min-h-screen items-center justify-center bg-[#0D1117] px-4 text-[#E6EDF3]">
        <div className="absolute right-4 top-4 text-[#E6EDF3]">
          <ThemeToggle />
        </div>
        <Card className="w-full max-w-md border-[#21262D] bg-[#161B22] text-[#E6EDF3] shadow-2xl">
          <CardHeader className="space-y-3">
            <span className="flex h-11 w-11 items-center justify-center rounded-md bg-blue-600 text-white">
              <ShieldCheck className="h-5 w-5" />
            </span>
            <div>
              <CardTitle>Админ-панель</CardTitle>
              <CardDescription className="text-[#8B949E]">
                Введите пароль для доступа к задачам.
              </CardDescription>
            </div>
          </CardHeader>
          <CardContent>
            <form className="space-y-4" onSubmit={submitLogin}>
              <Input
                type="password"
                aria-label="Пароль"
                placeholder="Пароль"
                value={password}
                className="border-[#30363D] bg-[#0D1117] text-[#E6EDF3] placeholder:text-[#8B949E]"
                onChange={(event) => setPassword(event.target.value)}
              />
              {loginError ? (
                <p className="rounded-md border border-red-900/70 bg-red-950/40 p-3 text-sm text-red-200">
                  {loginError}
                </p>
              ) : null}
              <Button type="submit" className="w-full" disabled={!password || loggingIn}>
                {loggingIn ? <Loader2 className="h-4 w-4 animate-spin" /> : null}
                Войти
              </Button>
            </form>
          </CardContent>
        </Card>
      </main>
    );
  }

  return (
    <Layout admin actions={headerActions} className="space-y-8">
      <div className="flex flex-col gap-2">
        <p className="text-sm text-muted-foreground">Yandex Mediaplan MVP</p>
        <h1 className="text-3xl font-bold tracking-normal">Админ-панель</h1>
      </div>

      {dashboardError ? (
        <div className="rounded-lg border border-red-200 bg-red-50 p-4 text-sm text-red-700 dark:border-red-900/70 dark:bg-red-950/30 dark:text-red-300">
          {dashboardError}
        </div>
      ) : null}

      <Tabs defaultValue="tasks">
        <TabsList>
          <TabsTrigger value="tasks">Задачи</TabsTrigger>
          <TabsTrigger value="stats">Статистика</TabsTrigger>
        </TabsList>

        <TabsContent value="tasks" className="space-y-5">
          <div className="flex flex-wrap gap-2">
            {filters.map((filter) => (
              <Button
                key={filter.value}
                type="button"
                size="sm"
                variant={statusFilter === filter.value ? "default" : "outline"}
                onClick={() => {
                  setStatusFilter(filter.value);
                  setPage(0);
                  setExpandedTaskId(null);
                }}
              >
                {filter.label}
              </Button>
            ))}
          </div>

          <div
            className={cn(
              "rounded-lg border bg-card",
              loadingTasks && "opacity-70",
            )}
          >
            {loadingTasks ? (
              <div className="flex items-center gap-2 border-b p-4 text-sm text-muted-foreground">
                <Loader2 className="h-4 w-4 animate-spin" />
                Обновляем список...
              </div>
            ) : null}
            <TaskTable
              tasks={tasks}
              offset={page * PAGE_SIZE}
              expandedTaskId={expandedTaskId}
              detailsById={detailsById}
              loadingDetailsId={loadingDetailsId}
              onExpand={expandTask}
              onRetry={retry}
              onCancel={cancel}
              onUploadXls={upload}
            />
          </div>

          <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
            <p className="text-sm text-muted-foreground">
              Всего: {total}. Страница {page + 1} из {totalPages}.
            </p>
            <div className="flex gap-2">
              <Button
                type="button"
                variant="outline"
                disabled={page === 0 || loadingTasks}
                onClick={() => setPage((current) => Math.max(0, current - 1))}
              >
                Назад
              </Button>
              <Button
                type="button"
                variant="outline"
                disabled={page + 1 >= totalPages || loadingTasks}
                onClick={() =>
                  setPage((current) => Math.min(totalPages - 1, current + 1))
                }
              >
                Вперёд
              </Button>
            </div>
          </div>
        </TabsContent>

        <TabsContent value="stats">
          {loadingStats && !stats ? (
            <p className="flex items-center gap-2 text-sm text-muted-foreground">
              <Loader2 className="h-4 w-4 animate-spin" />
              Загружаем статистику...
            </p>
          ) : stats ? (
            <StatsCards stats={stats} />
          ) : (
            <p className="text-sm text-muted-foreground">Статистика недоступна.</p>
          )}
        </TabsContent>
      </Tabs>
    </Layout>
  );
}
