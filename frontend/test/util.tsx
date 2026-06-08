import { ReactNode } from "react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import {
  RouterProvider,
  createMemoryHistory,
  createRootRoute,
  createRoute,
  createRouter,
  Outlet,
} from "@tanstack/react-router";
import { render, type RenderResult } from "@testing-library/react";

export function makeQueryClient() {
  return new QueryClient({
    defaultOptions: {
      queries: { retry: false, gcTime: 0, staleTime: 0 },
      mutations: { retry: false },
    },
  });
}

export function renderWithProviders(ui: ReactNode): RenderResult & { client: QueryClient } {
  const client = makeQueryClient();
  const result = render(<QueryClientProvider client={client}>{ui}</QueryClientProvider>);
  return Object.assign(result, { client });
}

/**
 * Render a component inside a minimal TanStack Router setup so <Link/> works.
 * The test router declares every navigable route used by the app so Link's
 * runtime path resolution succeeds.
 */
export function renderInRouter(ui: ReactNode, path = "/") {
  const client = makeQueryClient();
  const Host = () => <>{ui}</>;
  const Stub = () => <div />;
  const root = createRootRoute({ component: () => <Outlet /> });
  const routes = [
    createRoute({ getParentRoute: () => root, path: "/", component: Host }),
    createRoute({ getParentRoute: () => root, path: "/jobs", component: Stub }),
    createRoute({ getParentRoute: () => root, path: "/jobs/$jobId", component: Stub }),
    createRoute({ getParentRoute: () => root, path: "/applications", component: Stub }),
    createRoute({
      getParentRoute: () => root,
      path: "/applications/$applicationId",
      component: Stub,
    }),
    createRoute({ getParentRoute: () => root, path: "/companies", component: Stub }),
    createRoute({ getParentRoute: () => root, path: "/skill-gaps", component: Stub }),
    createRoute({ getParentRoute: () => root, path: "/resume", component: Stub }),
    createRoute({ getParentRoute: () => root, path: "/settings", component: Stub }),
    createRoute({ getParentRoute: () => root, path: "/telegram", component: Stub }),
  ];
  const router = createRouter({
    routeTree: root.addChildren(routes),
    history: createMemoryHistory({ initialEntries: [path] }),
  });
  const result = render(
    <QueryClientProvider client={client}>
      <RouterProvider router={router} />
    </QueryClientProvider>,
  );
  return Object.assign(result, { client, router });
}

type FetchHandler = (url: string, init?: RequestInit) => Response | Promise<Response>;

export function mockFetch(handler: FetchHandler) {
  const fn = async (input: RequestInfo | URL, init?: RequestInit) => {
    const url = typeof input === "string" ? input : input.toString();
    return handler(url, init);
  };
  globalThis.fetch = fn as typeof fetch;
}

export function jsonResponse(body: unknown, status = 200): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: { "content-type": "application/json" },
  });
}
