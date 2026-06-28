"use client";

import * as Dialog from "@radix-ui/react-dialog";
import { X } from "@phosphor-icons/react";

export function SidePanel({
  open,
  onOpenChange,
  title,
  description,
  children,
  width = "max-w-xl",
}: {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  title: string;
  description?: string;
  children: React.ReactNode;
  width?: string;
}) {
  return (
    <Dialog.Root open={open} onOpenChange={onOpenChange}>
      <Dialog.Portal>
        <Dialog.Overlay className="fixed inset-0 z-50 bg-slate-950/35 backdrop-blur-[2px] data-[state=open]:animate-[fade-in_.18s_ease-out]" />
        <Dialog.Content
          className={`fixed inset-y-0 right-0 z-50 flex w-[min(100%,42rem)] ${width} flex-col border-l bg-white shadow-2xl data-[state=open]:animate-[panel-in_.24s_cubic-bezier(.2,.8,.2,1)]`}
        >
          <div className="border-b px-5 py-5 pr-16">
            <Dialog.Title className="text-xl font-semibold tracking-[-0.02em]">
              {title}
            </Dialog.Title>
            {description ? (
              <Dialog.Description className="mt-1.5 text-sm leading-6 text-muted">
                {description}
              </Dialog.Description>
            ) : null}
          </div>
          <Dialog.Close className="focus-ring absolute right-4 top-4 cursor-pointer rounded-xl p-2 text-muted hover:bg-slate-100 hover:text-foreground">
            <X className="size-5" />
          </Dialog.Close>
          <div className="min-h-0 flex-1 overflow-y-auto">{children}</div>
        </Dialog.Content>
      </Dialog.Portal>
    </Dialog.Root>
  );
}
