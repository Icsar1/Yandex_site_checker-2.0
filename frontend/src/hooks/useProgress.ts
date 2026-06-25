import { useEffect, useState } from "react";

import { getProgress, type ProgressResponse } from "@/api/client";

interface UseProgressState {
  progress: ProgressResponse | null;
  isPolling: boolean;
  error: string | null;
}

export function useProgress(taskId: string | null): UseProgressState {
  const [progress, setProgress] = useState<ProgressResponse | null>(null);
  const [isPolling, setIsPolling] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!taskId) {
      setProgress(null);
      setIsPolling(false);
      setError(null);
      return undefined;
    }

    let active = true;
    let intervalId: number | undefined;

    const stop = () => {
      if (intervalId) {
        window.clearInterval(intervalId);
      }
      if (active) {
        setIsPolling(false);
      }
    };

    const poll = async () => {
      try {
        const nextProgress = await getProgress(taskId);

        if (!active) {
          return;
        }

        setProgress(nextProgress);
        setError(null);

        if (nextProgress.terminal) {
          stop();
        }
      } catch (caught) {
        if (!active) {
          return;
        }

        setError(
          caught instanceof Error
            ? caught.message
            : "Не удалось получить прогресс",
        );
        stop();
      }
    };

    setProgress(null);
    setError(null);
    setIsPolling(true);
    void poll();
    intervalId = window.setInterval(poll, 1500);

    return () => {
      active = false;
      if (intervalId) {
        window.clearInterval(intervalId);
      }
    };
  }, [taskId]);

  return { progress, isPolling, error };
}
