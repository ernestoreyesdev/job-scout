"use client";

import { useRef, useState, useTransition } from "react";

import { removeAnthropicKey, saveAnthropicKey } from "@/app/actions";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";

/** Adds, replaces or removes the user's Anthropic key; shows only its hint. */
export function KeyForm({ hint }: { hint: string | null }) {
  const [error, setError] = useState<string | null>(null);
  const [pending, startTransition] = useTransition();
  const formRef = useRef<HTMLFormElement>(null);

  function save(formData: FormData) {
    startTransition(async () => {
      const result = await saveAnthropicKey(formData);
      setError(result.ok ? null : (result.error ?? "Could not save the key."));
      if (result.ok) formRef.current?.reset();
    });
  }

  function remove() {
    startTransition(async () => {
      const result = await removeAnthropicKey();
      setError(result.ok ? null : (result.error ?? "Could not remove the key."));
    });
  }

  return (
    <div className="mt-4 space-y-3">
      <p className="text-sm">
        {hint ? (
          <>
            Saved key ending in <span className="font-mono">{hint}</span>
          </>
        ) : (
          <span className="text-muted-foreground">No key saved yet.</span>
        )}
      </p>
      <form ref={formRef} action={save} className="flex gap-2">
        <Input
          name="apiKey"
          type="password"
          required
          autoComplete="off"
          placeholder={hint ? "Paste a new key to replace it" : "sk-ant-…"}
        />
        <Button type="submit" disabled={pending}>
          {pending ? "Saving…" : hint ? "Replace" : "Save"}
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
