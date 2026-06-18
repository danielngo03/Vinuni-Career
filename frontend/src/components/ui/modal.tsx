"use client";

import * as Dialog from "@radix-ui/react-dialog";
import { X } from "@phosphor-icons/react";
import type { ReactNode } from "react";

export function Modal({
  open,
  onOpenChange,
  title,
  description,
  children,
}: {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  title: string;
  description?: string;
  children: ReactNode;
}) {
  return (
    <Dialog.Root open={open} onOpenChange={onOpenChange}>
      <Dialog.Portal>
        <Dialog.Overlay className="fixed inset-0 z-50 bg-slate-950/40 backdrop-blur-[2px]" />
        <Dialog.Content className="fixed left-1/2 top-1/2 z-50 max-h-[90vh] w-[calc(100%-2rem)] max-w-xl -translate-x-1/2 -translate-y-1/2 overflow-y-auto rounded-2xl border bg-white p-6 shadow-2xl">
          <div className="pr-10">
            <Dialog.Title className="text-xl font-semibold">{title}</Dialog.Title>
            {description ? (
              <Dialog.Description className="mt-2 text-sm leading-6 text-muted">
                {description}
              </Dialog.Description>
            ) : null}
          </div>
          <Dialog.Close className="focus-ring absolute right-4 top-4 cursor-pointer rounded-lg p-2 text-muted hover:bg-slate-100 hover:text-foreground">
            <X className="size-5" />
          </Dialog.Close>
          <div className="mt-6">{children}</div>
        </Dialog.Content>
      </Dialog.Portal>
    </Dialog.Root>
  );
}
