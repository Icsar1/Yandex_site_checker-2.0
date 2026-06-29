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
  generateMasks,
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

type LandingState = "form" | "masks" | "progress" | "result";

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
  const [masks, setMasks] = useState<string[]>([]);
  const [selectedMasks, setSelectedMasks] = useState<Set<number>>(new Set());
  const [newMask, setNewMask] = useState("");
  const [masksLoading, setMasksLoading] = useState(false);

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
    setMasks([]);
    setSelectedMasks(new Set());
    setNewMask("");
    setMasksLoading(false);
  };

  const retryCurrent = () => {
    setView("form");
    setTaskId(null);
    setTask(null);
    setFormError(null);
    setTerminalLoading(false);
  };

  const searchSuggested = async (suggested: string) => {
    if (!region?.id && !task?.region_ids?.[0]) {
      setFormError("Выберите регион.");
      setView("form");
      return;
    }

    setMasksLoading(true);
    setSubmitting(true);
    setFormError(null);
    try {
      const result = await generateMasks(suggested);

      setNiche(suggested);
      setMasks(result.masks);
      setSelectedMasks(new Set(result.masks.map((_, i) => i)));
      setView("masks");
    } catch {
      const regionId = region?.id ?? task?.region_ids?.[0];

      if (!regionId) {
        setView("form");
        return;
      }

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
      }
    } finally {
      setSubmitting(false);
      setMasksLoading(false);
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

    setMasksLoading(true);
    setSubmitting(true);
    try {
      const result = await generateMasks(niche.trim());

      setMasks(result.masks);
      setSelectedMasks(new Set(result.masks.map((_, i) => i)));
      setView("masks");
    } catch (caught) {
      setFormError(initialErrorMessage(caught));
    } finally {
      setSubmitting(false);
      setMasksLoading(false);
    }
  };

  const launchSearch = async () => {
    if (!region) {
      return;
    }

    const selected = masks.filter((_, i) => selectedMasks.has(i));
    const masksToUse = selected.length > 0 ? selected : masks;

    setSubmitting(true);
    setFormError(null);
    try {
      const created = await createTask({
        niche: niche.trim(),
        region_ids: [region.id],
        contact: contact.trim() || undefined,
        masks: masksToUse,
      });

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

  const toggleMask = (i: number) => {
    setSelectedMasks((prev) => {
      const next = new Set(prev);

      if (next.has(i)) {
        next.delete(i);
      } else {
        next.add(i);
      }

      return next;
    });
  };

  const removeMask = (i: number) => {
    setMasks((prev) => prev.filter((_, idx) => idx !== i));
    setSelectedMasks((prev) => {
      const next = new Set<number>();

      prev.forEach((idx) => {
        if (idx < i) {
          next.add(idx);
        } else if (idx > i) {
          next.add(idx - 1);
        }
      });

      return next;
    });
  };

  const addMask = () => {
    const m = newMask.trim().toLowerCase();

    if (!m || masks.includes(m)) {
      setNewMask("");
      return;
    }

    setMasks((prev) => [...prev, m]);
    setSelectedMasks((prev) => new Set([...prev, masks.length]));
    setNewMask("");
  };

  const failedMessage = useMemo(() => {
    if (task?.status === "failed") {
      return task.error_message ?? "Задача завершилась с ошибкой.";
    }

    return progressError;
  }, [progressError, task]);

  return (
    <Layout>
      {/* Hero */}
      <section className="relative overflow-hidden">
        <div
          className="pointer-events-none absolute inset-0 -z-10"
          style={{ background: "linear-gradient(135deg, #DCF2FF 0%, #ffffff 60%)" }}
        />
        <div
          className="pointer-events-none absolute -right-32 -top-32 h-96 w-96 rounded-full opacity-25 blur-3xl"
          style={{ background: "#5A96EF" }}
        />
        <div className="grid min-h-[calc(100vh-8rem)] items-center gap-10 pb-8 lg:grid-cols-[1.1fr_0.9fr]">
          <div className="space-y-8 py-8">
            <span
              className="inline-flex items-center gap-2 rounded-full px-5 py-2 text-sm font-semibold shadow-sm"
              style={{ background: "#F0C555", color: "#3a2c00" }}
            >
              ✦ Бесплатно · Без регистрации · Результат сразу
            </span>
            <div className="space-y-5">
              <h1
                className="max-w-2xl text-[40px] leading-[1.08] tracking-tight lg:text-[60px]"
                style={{ fontFamily: "Forum, Georgia, serif", color: "#547DB9" }}
              >
                Медиаплан<br />за 3 минуты
              </h1>
              <p className="max-w-xl text-lg leading-8 text-muted-foreground">
                Автоматически собираем ключевые слова, считаем прогноз
                бюджета Яндекс Директ и формируем PDF-отчёт.
              </p>
            </div>
            <div className="flex flex-wrap gap-3">
              {["⚡ < 3 минут", "📊 До 200 ключевых слов", "🤖 YandexGPT", "📄 PDF"].map((badge) => (
                <span
                  key={badge}
                  className="rounded-full border px-4 py-2 text-sm font-medium shadow-sm"
                  style={{ borderColor: "#5A96EF44", background: "#DCF2FF", color: "#547DB9" }}
                >
                  {badge}
                </span>
              ))}
            </div>
          </div>

          {view === "result" && task ? (
            <ResultCard task={task} onReset={resetForm} />
          ) : (
            <Card
              className="border-0"
              style={{ background: "#ffffff", boxShadow: "0 18px 50px rgba(90,150,239,0.13)" }}
            >
              <CardHeader className="pb-4">
                <div className="mb-4 h-1 w-12 rounded-full" style={{ background: "#F0C555" }} />
                <CardTitle
                  className="text-2xl"
                  style={{ fontFamily: "Forum, Georgia, serif", color: "#547DB9" }}
                >
                  {view === "form" ? "Рассчитать бюджет" : view === "masks" ? "Поисковые маски" : "Ваш расчёт"}
                </CardTitle>
                <CardDescription>
                  {view === "form"
                    ? "Заполните нишу и регион, остальное сделает сервис."
                    : view === "masks"
                    ? "Выберите маски для поиска ключевых слов."
                    : "Статус обновляется автоматически."}
                </CardDescription>
              </CardHeader>
              <CardContent>
                {view === "form" ? (
                  <form className="space-y-4" onSubmit={submit}>
                    <div className="space-y-2">
                      <label className="text-sm font-semibold" htmlFor="niche">Ниша</label>
                      <Input
                        id="niche"
                        aria-label="Ниша"
                        value={niche}
                        placeholder="Натяжные потолки, ремонт ванной..."
                        onChange={(event) => setNiche(event.target.value)}
                        style={{ borderColor: "#5A96EF55" }}
                      />
                    </div>
                    <div className="space-y-2">
                      <label className="text-sm font-semibold">Регион</label>
                      <RegionCombobox value={region} onChange={setRegion} />
                    </div>
                    <div className="space-y-2">
                      <label className="text-sm font-semibold" htmlFor="contact">Контакт</label>
                      <Input
                        id="contact"
                        aria-label="Email или телефон"
                        value={contact}
                        placeholder="Email или телефон (необязательно)"
                        onChange={(event) => setContact(event.target.value)}
                        style={{ borderColor: "#5A96EF55" }}
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
                      className="w-full font-semibold text-white"
                      disabled={!canSubmit}
                      style={{ background: "#5A96EF" }}
                    >
                      {submitting || masksLoading ? (
                        <Loader2 className="h-5 w-5 animate-spin" />
                      ) : (
                        <Sparkles className="h-5 w-5" />
                      )}
                      Подобрать маски
                    </Button>
                    <p className="text-center text-sm text-muted-foreground">
                      Бесплатно. Без регистрации.
                    </p>
                  </form>
                ) : null}

                {view === "masks" ? (
                  <div className="space-y-4">
                    <div>
                      <p className="mb-3 text-sm text-muted-foreground">
                        ИИ подобрал поисковые маски для ниши «{niche}». Снимите галочку чтобы исключить маску или добавьте свою.
                      </p>
                      <div className="space-y-2">
                        {masks.map((mask, i) => (
                          <div
                            key={i}
                            className="flex items-center gap-2 rounded-md border px-3 py-2"
                            style={{
                              borderColor: "#5A96EF33",
                              background: selectedMasks.has(i) ? "#DCF2FF" : "#f5f5f5",
                            }}
                          >
                            <input
                              type="checkbox"
                              checked={selectedMasks.has(i)}
                              onChange={() => toggleMask(i)}
                              className="h-4 w-4 shrink-0 accent-[#5A96EF]"
                            />
                            <span className="flex-1 text-sm">{mask}</span>
                            <button
                              type="button"
                              onClick={() => removeMask(i)}
                              className="px-1 text-xs text-muted-foreground hover:text-red-500"
                              aria-label="Удалить"
                            >
                              ✕
                            </button>
                          </div>
                        ))}
                      </div>
                    </div>
                    <div className="flex gap-2">
                      <Input
                        value={newMask}
                        onChange={(event) => setNewMask(event.target.value)}
                        placeholder="Добавить маску..."
                        onKeyDown={(event) => {
                          if (event.key === "Enter") {
                            event.preventDefault();
                            addMask();
                          }
                        }}
                        style={{ borderColor: "#5A96EF55" }}
                      />
                      <Button type="button" variant="outline" onClick={addMask} disabled={!newMask.trim()}>
                        +
                      </Button>
                    </div>
                    {formError ? (
                      <p className="rounded-md border border-red-200 bg-red-50 p-3 text-sm text-red-700">
                        {formError}
                      </p>
                    ) : null}
                    <div className="flex gap-2">
                      <Button
                        type="button"
                        variant="outline"
                        onClick={() => setView("form")}
                        disabled={submitting}
                        className="flex-1"
                      >
                        ← Назад
                      </Button>
                      <Button
                        type="button"
                        onClick={launchSearch}
                        disabled={submitting || selectedMasks.size === 0}
                        className="flex-1 font-semibold text-white"
                        style={{ background: "#5A96EF" }}
                      >
                        {submitting ? (
                          <Loader2 className="h-4 w-4 animate-spin" />
                        ) : (
                          <ArrowRight className="h-4 w-4" />
                        )}
                        Запустить поиск
                      </Button>
                    </div>
                  </div>
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
                            className="text-white"
                            style={{ background: "#5A96EF" }}
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
        </div>
      </section>

      {/* How it works */}
      <section className="border-t py-16">
        <h2
          className="mb-10 text-center text-3xl lg:text-4xl"
          style={{ fontFamily: "Forum, Georgia, serif", color: "#547DB9" }}
        >
          Как это работает
        </h2>
        <div className="grid gap-6 md:grid-cols-3">
          {[
            { title: "Собираем спрос", text: "Находим поисковые формулировки и группируем ключи по смыслу.", icon: Search, num: "01" },
            { title: "Считаем бюджет", text: "Прогнозируем показы, клики и диапазон расходов для Яндекс Директ.", icon: BarChart3, num: "02" },
            { title: "Готовим отчёт", text: "Формируем PDF с выводами, рекомендациями и медиапланом.", icon: FileText, num: "03" },
          ].map(({ title, text, icon: Icon, num }) => (
            <article
              key={title}
              className="relative rounded-xl p-6 shadow-sm"
              style={{ background: "#DCF2FF" }}
            >
              <span
                className="absolute right-5 top-4 text-4xl font-bold opacity-15"
                style={{ fontFamily: "Forum, Georgia, serif", color: "#5A96EF" }}
              >
                {num}
              </span>
              <span
                className="mb-4 flex h-11 w-11 items-center justify-center rounded-xl"
                style={{ background: "#5A96EF" }}
              >
                <Icon className="h-5 w-5 text-white" />
              </span>
              <h3
                className="mb-2 text-xl"
                style={{ fontFamily: "Forum, Georgia, serif", color: "#547DB9" }}
              >
                {title}
              </h3>
              <p className="text-sm leading-6 text-muted-foreground">{text}</p>
            </article>
          ))}
        </div>
      </section>

      {/* Footer note */}
      <section className="pb-12">
        <div
          className="flex flex-wrap items-center justify-center gap-3 rounded-xl px-6 py-4 text-sm font-medium"
          style={{ background: "#F0C555", color: "#3a2c00" }}
        >
          <Sparkles className="h-4 w-4" />
          <span>PDF-отчёт сохраняется по защищённой ссылке после завершения расчёта.</span>
        </div>
      </section>
    </Layout>
  );
}
