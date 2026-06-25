import { Download, RotateCcw } from "lucide-react";

import type { TaskResponse } from "@/api/client";
import { Button } from "@/components/ui/button";
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";

interface ResultCardProps {
  task: TaskResponse;
  keywordCount?: number;
  onReset: () => void;
}

export function ResultCard({ task, keywordCount, onReset }: ResultCardProps) {
  return (
    <Card className="animate-in border-emerald-200 bg-emerald-50/60 shadow-panel dark:border-emerald-900/60 dark:bg-emerald-950/20">
      <CardHeader>
        <CardTitle className="text-2xl">Медиаплан готов</CardTitle>
        <CardDescription>
          Ваш медиаплан готов. Начните рекламу с правильных ключей.
        </CardDescription>
      </CardHeader>
      <CardContent className="space-y-5">
        <div className="grid gap-3 rounded-lg border bg-background/80 p-4 text-sm sm:grid-cols-3">
          <div>
            <p className="text-muted-foreground">Ниша</p>
            <p className="font-semibold text-foreground">{task.niche}</p>
          </div>
          <div>
            <p className="text-muted-foreground">Регион</p>
            <p className="font-semibold text-foreground">{task.region_label}</p>
          </div>
          <div>
            <p className="text-muted-foreground">Ключевые слова</p>
            <p className="font-semibold text-foreground">
              {keywordCount ? keywordCount : "до 200"}
            </p>
          </div>
        </div>

        <div className="flex flex-col gap-3 sm:flex-row">
          <Button size="lg" asChild disabled={!task.download_url}>
            <a
              href={task.download_url ?? "#"}
              target="_blank"
              rel="noreferrer"
              aria-disabled={!task.download_url}
            >
              <Download className="h-5 w-5" />
              Скачать медиаплан
            </a>
          </Button>
          <Button type="button" size="lg" variant="outline" onClick={onReset}>
            <RotateCcw className="h-5 w-5" />
            Создать новый
          </Button>
        </div>
      </CardContent>
    </Card>
  );
}
