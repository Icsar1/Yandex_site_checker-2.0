import {
  dismissToast,
  ToastClose,
  ToastDescription,
  ToastProvider,
  ToastRoot,
  ToastTitle,
  ToastViewport,
  useToastStore,
} from "@/components/ui/toast";

export function Toaster() {
  const toasts = useToastStore();

  return (
    <ToastProvider swipeDirection="right">
      {toasts.map(({ id, title, description, variant, open }) => (
        <ToastRoot
          key={id}
          open={open}
          variant={variant}
          onOpenChange={(nextOpen) => {
            if (!nextOpen) {
              dismissToast(id);
            }
          }}
        >
          <div>
            <ToastTitle>{title}</ToastTitle>
            {description ? (
              <ToastDescription>{description}</ToastDescription>
            ) : null}
          </div>
          <ToastClose />
        </ToastRoot>
      ))}
      <ToastViewport />
    </ToastProvider>
  );
}
