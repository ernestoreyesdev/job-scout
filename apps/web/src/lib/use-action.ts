import { useState, useTransition } from "react";

import type { ActionResult } from "@/app/actions";

/** Runs server actions in a transition, keeping the last one's error, or `fallback` when it gave none. */
export function useAction() {
  const [error, setError] = useState<string | null>(null);
  const [pending, startTransition] = useTransition();

  function run<R extends ActionResult>(action: () => Promise<R>, fallback: string, then?: (result: R) => void) {
    startTransition(async () => {
      const result = await action();
      setError(result.ok ? null : (result.error ?? fallback));
      then?.(result);
    });
  }

  return { run, pending, error };
}
