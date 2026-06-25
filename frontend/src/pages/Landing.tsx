import { FormEvent, useEffect, useMemo, useState } from "react";
import {
  ArrowRight,
  BarChart3,
  FileText,
  Loader2,
  RotateCcw,
  Search,
  Sparkles,
} from "lucide-react";

import {
  ApiError,
  createTask,
  getTask,
  type Region,
  type TaskResponse,
} from "@/api/client";
import { Layout } from "@/components/Layout";
import { ProgressBar } from "@/components/ProgressBar";
import { RegionCombobox } from "@/components/RegionCombobox";
import { ResultCard } from "@/components/ResultCard";
import { Button } from "@/components/ui/button";
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { useProgress } from "@/hooks/useProgress";

type LandingState = "form" | "progress" | "result";

const trustBadges = ["⚡ < 3 минут", "📊 До 200 ключевых слов", "🤖 YandexGPT", "📄 PDF"];

function initialErrorMessage(caught: unknown) {
  if (caught instanceof ApiError && caught.status === 429) {
    return "Слишком много запросов. Попробуйте немного позже.";
  }

  return caught instanceof Error ? caught.message : "Не удалось создать задачу";
}

export function Landing() {
  const [view, setView] = useState<LandingState>("form");
  const [niche, setNiche] = useState("");
  const [region, setRegion] = useState<Region | null>(null);
  const [contact, setContact] = useState("");
  const [taskId, setTaskId] = useState<string | null>(null);
  const [task, setTask] = useState<TaskResponse | null>(null);
  const [submitting, setSubmitting] = useState(false);
  const [formError, setFormError] = useState<string | null>(null);
  const [terminalLoading, setTerminalLoading] = useState(false);

  const { progress, error: progressError } = useProgress(taskId);

  const regionName = region?.name ?? task?.region_label ?? "";
  const canSubmit = niche.trim().length > 1 && region !== null && !submitting;

  useEffect(() => {
    if (!taskId || !progress?.terminal) {
      return undefined;
    }

    let active = true;
    setTerminalLoading(true);

    void getTask(taskId)
      .then((nextTask) => {
        if (!active) {
          return;
        }

        setTask(nextTask);
        if (nextTask.status === "done") {
          setView("result");
        }
      })
      .catch((caught) => {
        if (!active) {
          return;
        }

        setFormError(
          caught instanceof Error ? caught.message : "Не удалось получить результат",
        );
      })
      .finally(() => {
        if (active) {
          setTerminalLoading(false);
        }
      });

    return () => {
      active = false;
    };
  }, [taskId, progress?.terminal]);

  const resetForm = () => {
    setView("form");
    setTaskId(null);
    setTask(null);
    setFormError(null);
    setTerminalLoading(false);
    setNiche("");
    setRegion(null);
    setContact("");
  };

  const retryCurrent = () => {
    setView("form");
    setTaskId(null);
    setTask(null);
    setFormError(null);
    setTerminalLoading(false);
  };

  const searchSuggested = async (suggested: string) => {
    const regionId = region?.id ?? task?.region_ids?.[0];

    if (!regionId) {
      setFormError("Выберите регион.");
      setView("form");
      return;
    }

    setSubmitting(true);
    setFormError(null);
    try {
      const created = await createTask({
        niche: suggested,
        region_ids: [regionId],
        contact: contact.trim() || undefined,
      });

      setNiche(suggested);
      setTaskId(created.task_id);
      setTask(null);
      setView("progress");
    } catch (caught) {
      setFormError(initialErrorMessage(caught));
      setView("form");
    } finally {
      setSubmitting(false);
    }
  };

  const submit = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    setFormError(null);

    if (!niche.trim()) {
      setFormError("Укажите нишу.");
      return;
    }

    if (!region) {
      setFormError("Выберите регион.");
      return;
    }

    setSubmitting(true);
    try {
      const createdTask = await createTask({
        niche: niche.trim(),
        region_ids: [region.id],
        contact: contact.trim() || undefined,
      });

      setTaskId(createdTask.task_id);
      setTask(null);
      setView("progress");
    } catch (caught) {
      setFormError(initialErrorMessage(caught));
    } finally {
      setSubmitting(false);
    }
  };

  const failedMessage = useMemo(() => {
    if (task?.status === "failed") {
      return task.error_message ?? "Задача завершилась с ошибкой.";
    }

    return progressError;
  }, [progressError, task]);

  return (
    <Layout>
      <section className="grid min-h-[calc(100vh-8rem)] items-center gap-10 pb-8 lg:grid-cols-[1.05fr_0.95fr]">
        <div className="space-y-8">
          <div className="space-y-5">
            <span className="inline-flex rounded-full border bg-card px-4 py-2 text-sm font-medium text-muted-foreground shadow-sm">
              ✦ Бесплатно · Без регистрации · Результат сразу
            </span>
            <div className="space-y-5">
              <h1 className="max-w-3xl text-[36px] font-bold leading-[1.05] tracking-normal text-slate-950 dark:text-slate-50 lg:text-[54px]">
                Медиаплан за 3 минуты
              </h1>
              <p className="max-w-2xl text-lg leading-8 text-muted-foreground">
                Автоматически собираем ключевые слова, считаем прогноз бюджета
                Яндекс Директ и формируем PDF-отчёт.
              </p>
            </div>
          </div>

          <div className="flex flex-wrap gap-3">
            {trustBadges.map((badge) => (
              <span
                key={badge}
                className="rounded-full border bg-card px-4 py-2 text-sm font-medium text-foreground shadow-sm"
              >
                {badge}
              </span>
            ))}
          </div>
        </div>

        {view === "result" && task ? (
          <ResultCard task={task} onReset={resetForm} />
        ) : (
          <Card className="shadow-panel">
            <CardHeader>
              <CardTitle>
                {view === "form" ? "Рассчитать бюджет" : "Ваш расчёт"}
              </CardTitle>
              <CardDescription>
                {view === "form"
                  ? "Заполните нишу и регион, остальное сделает сервис."
                  : "Статус обновляется автоматически."}
              </CardDescription>
            </CardHeader>
            <CardContent>
              {view === "form" ? (
                <form className="space-y-4" onSubmit={submit}>
                  <div className="space-y-2">
                    <label className="text-sm font-medium" htmlFor="niche">
                      Ниша
                    </label>
                    <Input
                      id="niche"
                      aria-label="Ниша"
                      value={niche}
                      placeholder="Натяжные потолки, ремонт ванной..."
                      onChange={(event) => setNiche(event.target.value)}
                    />
                  </div>
                  <div className="space-y-2">
                    <label className="text-sm font-medium">Регион</label>
                    <RegionCombobox value={region} onChange={setRegion} />
                  </div>
                  <div className="space-y-2">
                    <label className="text-sm font-medium" htmlFor="contact">
                      Контакт
                    </label>
                    <Input
                      id="contact"
                      aria-label="Email или телефон"
                      value={contact}
                      placeholder="Email или телефон (необязательно)"
                      onChange={(event) => setContact(event.target.value)}
                    />
                  </div>

                  {formError ? (
                    <p className="rounded-md border border-red-200 bg-red-50 p-3 text-sm text-red-700 dark:border-red-900/70 dark:bg-red-950/30 dark:text-red-300">
                      {formError}
                    </p>
                  ) : null}

                  <Button
                    type="submit"
                    size="lg"
                    className="w-full"
                    disabled={!canSubmit}
                  >
                    {submitting ? (
                      <Loader2 className="h-5 w-5 animate-spin" />
                    ) : (
                      <ArrowRight className="h-5 w-5" />
                    )}
                    Рассчитать медиаплан
                  </Button>
                  <p className="text-center text-sm text-muted-foreground">
                    Бесплатно. Без регистрации.
                  </p>
                </form>
              ) : null}

              {view === "progress" ? (
                <div className="space-y-6">
                  <ProgressBar
                    progress={progress}
                    niche={niche}
                    region={regionName || "Регион выбран"}
                  />

                  {terminalLoading ? (
                    <p className="flex items-center gap-2 text-sm text-muted-foreground">
                      <Loader2 className="h-4 w-4 animate-spin" />
                      Получаем готовый отчёт...
                    </p>
                  ) : null}

                  {failedMessage ? (
                    <div className="space-y-3 rounded-lg border border-red-200 bg-red-50 p-4 text-sm text-red-700 dark:border-red-900/70 dark:bg-red-950/30 dark:text-red-300">
                      <p>{failedMessage}</p>
                      {task?.suggested_niche ? (
                        <Button
                          type="button"
                          onClick={() => searchSuggested(task.suggested_niche!)}
                          disabled={submitting}
                        >
                          {submitting ? (
                            <Loader2 className="h-4 w-4 animate-spin" />
                          ) : (
                            <Search className="h-4 w-4" />
                          )}
                          Искать «{task.suggested_niche}»
                        </Button>
                      ) : null}
                      <Button type="button" variant="outline" onClick={retryCurrent}>
                        <RotateCcw className="h-4 w-4" />
                        Попробовать снова
                      </Button>
                    </div>
                  ) : null}
                </div>
              ) : null}
            </CardContent>
          </Card>
        )}
      </section>

      <section className="border-t py-12">
        <div className="grid gap-6 md:grid-cols-3">
          {[
            {
              title: "Собираем спрос",
              text: "Находим поисковые формулировки и группируем ключи по смыслу.",
              icon: Search,
            },
            {
              title: "Считаем бюджет",
              text: "Прогнозируем показы, клики и диапазон расходов для Яндекс Директ.",
              icon: BarChart3,
            },
            {
              title: "Готовим отчёт",
              text: "Формируем PDF с выводами, рекомендациями и медиапланом.",
              icon: FileText,
            },
          ].map(({ title, text, icon: Icon }) => (
            <article key={title} className="rounded-lg border bg-card p-5 shadow-sm">
              <span className="mb-4 flex h-10 w-10 items-center justify-center rounded-md bg-primary/10 text-primary">
                <Icon className="h-5 w-5" />
              </span>
              <h2 className="text-lg font-semibold">{title}</h2>
              <p className="mt-2 text-sm leading-6 text-muted-foreground">{text}</p>
            </article>
          ))}
        </div>
      </section>

      <section className="pb-12">
        <div className="flex flex-wrap items-center justify-center gap-3 text-sm text-muted-foreground">
          <Sparkles className="h-4 w-4 text-primary" />
          <span>PDF-отчёт сохраняется по защищённой ссылке после завершения расчёта.</span>
        </div>
      </section>
    </Layout>
  );
}
