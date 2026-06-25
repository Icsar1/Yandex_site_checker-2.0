import {
  Calculator,
  CheckCircle2,
  FileText,
  Search,
  Sparkles,
} from "lucide-react";

import type { ProgressResponse } from "@/api/client";
import { cn } from "@/lib/utils";

interface ProgressBarProps {
  progress: ProgressResponse | null;
  niche: string;
  region: string;
}

const steps = [
  { step: 1, label: "Сбор ключевых слов", icon: Search },
  { step: 2, label: "Прогноз бюджета", icon: Calculator },
  { step: 3, label: "AI-аналитика", icon: Sparkles },
  { step: 4, label: "Сборка PDF", icon: FileText },
  { step: 5, label: "Готово", icon: CheckCircle2 },
];

const labelTranslations: Record<string, string> = {
  "Collecting keywords": "Сбор ключевых слов",
  "Budget forecast": "Прогноз бюджета",
  "AI analytics": "AI-аналитика",
  "PDF rendering": "Сборка PDF",
  Done: "Готово",
};

function clampStep(step: number | undefined) {
  if (!step || Number.isNaN(step)) {
    return 1;
  }

  return Math.min(Math.max(step, 1), steps.length);
}

function progressLabel(progress: ProgressResponse | null) {
  if (!progress) {
    return "Подготовка задачи";
  }

  if (progress.label && /[А-Яа-яЁё]/.test(progress.label)) {
    return progress.label;
  }

  if (progress.label && labelTranslations[progress.label]) {
    return labelTranslations[progress.label];
  }

  return steps[clampStep(progress.step) - 1]?.label ?? "Выполнение задачи";
}

export function ProgressBar({ progress, niche, region }: ProgressBarProps) {
  const currentStep = clampStep(progress?.step);
  const percent = Math.min(Math.max(progress?.percent ?? 0, 0), 100);
  const terminal = progress?.terminal ?? false;

  return (
    <section className="space-y-6" aria-live="polite">
      <div className="space-y-2">
        <p className="text-sm font-medium text-muted-foreground">Задача запущена</p>
        <h2 className="text-2xl font-bold tracking-normal text-foreground">
          {niche}
        </h2>
        <p className="text-sm text-muted-foreground">{region}</p>
      </div>

      <div className="space-y-3">
        <div className="flex items-center justify-between gap-4 text-sm">
          <span className="font-medium text-foreground">{progressLabel(progress)}</span>
          <span className="font-semibold text-primary">{Math.round(percent)}%</span>
        </div>
        <div className="h-2 overflow-hidden rounded-full bg-accent">
          <div
            className="h-full rounded-full bg-primary transition-all duration-500"
            style={{ width: `${percent}%` }}
          />
        </div>
      </div>

      <ol className="grid gap-3 sm:grid-cols-5">
        {steps.map(({ step, label, icon: Icon }) => {
          const completed = terminal || currentStep > step;
          const active = !terminal && currentStep === step;

          return (
            <li
              key={step}
              className={cn(
                "rounded-lg border bg-card p-3 transition-colors",
                completed &&
                  "border-emerald-200 bg-emerald-50 text-emerald-700 dark:border-emerald-900/70 dark:bg-emerald-950/30 dark:text-emerald-300",
                active &&
                  "border-primary/50 bg-primary/5 text-primary dark:bg-primary/10",
              )}
            >
              <div className="flex items-center gap-2 sm:flex-col sm:items-start">
                <span
                  className={cn(
                    "flex h-9 w-9 shrink-0 items-center justify-center rounded-full border bg-background",
                    active && "border-primary",
                    completed &&
                      "border-emerald-200 bg-emerald-100 dark:border-emerald-900 dark:bg-emerald-950",
                  )}
                >
                  {completed ? (
                    <CheckCircle2 className="h-4 w-4" />
                  ) : (
                    <Icon className={cn("h-4 w-4", active && "animate-pulse")} />
                  )}
                </span>
                <span className="text-sm font-medium leading-tight">{label}</span>
              </div>
            </li>
          );
        })}
      </ol>

      {progress?.needs_manual ? (
        <div className="rounded-lg border border-amber-200 bg-amber-50 p-4 text-sm text-amber-800 dark:border-amber-900/70 dark:bg-amber-950/30 dark:text-amber-200">
          Задача отправлена на ручную проверку. Результат будет готов в ближайшее
          время.
        </div>
      ) : null}
    </section>
  );
}
