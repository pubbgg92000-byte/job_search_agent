import { createRootRouteWithContext } from "@tanstack/react-router";
import type { QueryClient } from "@tanstack/react-query";
import { AppLayout } from "@/components/app-layout";

export const Route = createRootRouteWithContext<{ queryClient: QueryClient }>()({
  component: AppLayout,
});
