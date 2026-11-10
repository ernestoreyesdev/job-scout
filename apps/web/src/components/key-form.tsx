"use client";

import { KeyRound } from "lucide-react";
import { useRef, useState, useTransition } from "react";

import { removeSharedKey, saveSharedKey } from "@/app/actions";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";

/**
 * Adds, replaces or removes the shared Anthropic key; shows only its hint. `fallback` says whether the
 * ANTHROPIC_API_KEY setting still covers runs when no shared key is saved.
 */
export function KeyForm({ hint, fallback }: { hint: string | null; fallback: boolean }) {
  const [error, setError] = useState<string | null>(null);
  const [pending, startTransition] = useTransition();
  const formRef = useRef<HTMLFormElement>(null);

  function save(formData: FormData) {
    startTransition(async () => {
      const result = await saveSharedKey(formData);
      setError(result.ok ? null : (result.error ?? "Could not save the key."));
      if (result.ok) formRef.current?.reset();
    });
  }

  function remove() {
    startTransition(async () => {
      const result = await removeSharedKey();
      setError(result.ok ? null : (result.error ?? "Could not remove the key."));
    });
  }

  return (
    <div className="space-y-3">
      <div className="flex items-center gap-2 text-sm">
        <KeyRound className="size-4 text-muted-foreground" />
        {hint ? (
          <span>
            Shared key ending in <span className="font-mono">{hint}</span>
          </span>
        ) : fallback ? (
          <span className="text-muted-foreground">No shared key saved. Runs use the ANTHROPIC_API_KEY setting.</span>
        ) : (
          <span className="text-destructive">No key at all. Searches fail for users without their own key.</span>
        )}
      </div>
      <form ref={formRef} action={save} className="flex flex-wrap gap-2">
        <Input
          name="apiKey"
          type="password"
          required
          autoComplete="off"
          placeholder={hint ? "Paste a new key to switch to it" : "sk-ant-…"}
          className="min-w-64 flex-1"
        />
        <Button type="submit" disabled={pending}>
          {pending ? "Saving…" : hint ? "Switch key" : "Add key"}
        </Button>
        {hint && (
          <Button type="button" variant="outline" onClick={remove} disabled={pending}>
            Remove
          </Button>
        )}
      </form>
      {error && <p className="text-sm text-destructive">{error}</p>}
    </div>
  );
}
