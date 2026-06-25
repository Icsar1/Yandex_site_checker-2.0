import * as React from "react";
import * as ToastPrimitive from "@radix-ui/react-toast";
import { X } from "lucide-react";

import { cn } from "@/lib/utils";

export type ToastVariant = "default" | "destructive";

export interface ToastOptions {
  title: string;
  description?: string;
  variant?: ToastVariant;
}

interface ToastItem extends ToastOptions {
  id: string;
  open: boolean;
}

type Listener = (toasts: ToastItem[]) => void;

let memoryToasts: ToastItem[] = [];
const listeners: Listener[] = [];

function emit() {
  listeners.forEach((listener) => listener(memoryToasts));
}

export function toast(options: ToastOptions) {
  const id = crypto.randomUUID();
  memoryToasts = [
    ...memoryToasts,
    {
      id,
      open: true,
      variant: "default",
      ...options,
    },
  ];
  emit();
  window.setTimeout(() => dismissToast(id), 4500);
  return id;
}

export function dismissToast(id: string) {
  memoryToasts = memoryToasts.map((item) =>
    item.id === id ? { ...item, open: false } : item,
  );
  emit();
  window.setTimeout(() => {
    memoryToasts = memoryToasts.filter((item) => item.id !== id);
    emit();
  }, 250);
}

export function useToastStore() {
  const [toasts, setToasts] = React.useState(memoryToasts);

  React.useEffect(() => {
    listeners.push(setToasts);
    return () => {
      const index = listeners.indexOf(setToasts);
      if (index >= 0) {
        listeners.splice(index, 1);
      }
    };
  }, []);

  return toasts;
}

export const ToastProvider = ToastPrimitive.Provider;

export const ToastViewport = React.forwardRef<
  React.ElementRef<typeof ToastPrimitive.Viewport>,
  React.ComponentPropsWithoutRef<typeof ToastPrimitive.Viewport>
>(({ className, ...props }, ref) => (
  <ToastPrimitive.Viewport
    ref={ref}
    className={cn(
      "fixed right-0 top-0 z-[100] flex max-h-screen w-full flex-col-reverse gap-2 p-4 sm:bottom-0 sm:top-auto sm:max-w-sm",
      className,
    )}
    {...props}
  />
));
ToastViewport.displayName = ToastPrimitive.Viewport.displayName;

export const ToastRoot = React.forwardRef<
  React.ElementRef<typeof ToastPrimitive.Root>,
  React.ComponentPropsWithoutRef<typeof ToastPrimitive.Root> & {
    variant?: ToastVariant;
  }
>(({ className, variant = "default", ...props }, ref) => (
  <ToastPrimitive.Root
    ref={ref}
    className={cn(
      "grid grid-cols-[1fr_auto] items-start gap-x-3 gap-y-1 rounded-md border bg-card p-4 text-card-foreground shadow-lg",
      variant === "destructive" &&
        "border-destructive/60 bg-destructive text-destructive-foreground",
      className,
    )}
    {...props}
  />
));
ToastRoot.displayName = ToastPrimitive.Root.displayName;

export const ToastTitle = React.forwardRef<
  React.ElementRef<typeof ToastPrimitive.Title>,
  React.ComponentPropsWithoutRef<typeof ToastPrimitive.Title>
>(({ className, ...props }, ref) => (
  <ToastPrimitive.Title
    ref={ref}
    className={cn("text-sm font-semibold", className)}
    {...props}
  />
));
ToastTitle.displayName = ToastPrimitive.Title.displayName;

export const ToastDescription = React.forwardRef<
  React.ElementRef<typeof ToastPrimitive.Description>,
  React.ComponentPropsWithoutRef<typeof ToastPrimitive.Description>
>(({ className, ...props }, ref) => (
  <ToastPrimitive.Description
    ref={ref}
    className={cn("text-sm opacity-90", className)}
    {...props}
  />
));
ToastDescription.displayName = ToastPrimitive.Description.displayName;

export const ToastClose = React.forwardRef<
  React.ElementRef<typeof ToastPrimitive.Close>,
  React.ComponentPropsWithoutRef<typeof ToastPrimitive.Close>
>(({ className, ...props }, ref) => (
  <ToastPrimitive.Close
    ref={ref}
    className={cn("rounded-md p-1 opacity-80 transition-opacity hover:opacity-100", className)}
    {...props}
  >
    <X className="h-4 w-4" />
    <span className="sr-only">Закрыть уведомление</span>
  </ToastPrimitive.Close>
));
ToastClose.displayName = ToastPrimitive.Close.displayName;
