import { useToastStore } from "@/lib/toast";
import { cn } from "@/lib/cn";

export function Toaster() {
  const toasts = useToastStore((s) => s.toasts);
  const dismiss = useToastStore((s) => s.dismiss);
  return (
    <div className="fixed bottom-4 right-4 z-50 flex flex-col gap-2 w-[min(360px,calc(100vw-2rem))]" aria-live="polite">
      {toasts.map((t) => (
        <button
          key={t.id}
          onClick={() => dismiss(t.id)}
          className={cn(
            "rounded-md border p-3 text-left shadow-md text-sm bg-card text-card-foreground border-border",
            t.kind === "success" && "border-success/40",
            t.kind === "error" && "border-destructive/60",
            t.kind === "warning" && "border-warning/60",
          )}
        >
          {t.title && <div className="font-semibold mb-0.5">{t.title}</div>}
          {t.description && <div className="text-muted-foreground">{t.description}</div>}
        </button>
      ))}
    </div>
  );
}
