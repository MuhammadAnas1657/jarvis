import * as Dialog from '@radix-ui/react-dialog';
import { CalendarClock, Check, Loader2, X } from 'lucide-react';
import { useConfirmation } from '../../hooks/useConfirmation';

export function ConfirmationModal() {
  const { pendingAction, isModalOpen, isExecuting, confirm, cancel, selectSlot } =
    useConfirmation();

  if (!pendingAction) return null;

  const selectedStart = String(pendingAction.params?.start_time || '');
  const selectedEnd = String(pendingAction.params?.end_time || '');

  return (
    <Dialog.Root open={isModalOpen} onOpenChange={(open) => !open && cancel()}>
      <Dialog.Portal>
        <Dialog.Overlay className="fixed inset-0 z-50 bg-black/70 backdrop-blur-sm animate-in fade-in" />
        <Dialog.Content className="fixed left-1/2 top-1/2 z-50 w-[92vw] max-w-md -translate-x-1/2 -translate-y-1/2 rounded-2xl border border-slate-700/80 bg-slate-900 p-6 text-slate-100 shadow-2xl light:bg-white light:text-slate-900 light:border-slate-200">
          <div className="flex items-start justify-between gap-3">
            <div className="flex items-center gap-3">
              <div className="flex h-10 w-10 items-center justify-center rounded-xl bg-sky-500/15 text-sky-400">
                <CalendarClock className="h-5 w-5" />
              </div>
              <div>
                <Dialog.Title className="text-base font-semibold">
                  {pendingAction.title}
                </Dialog.Title>
                <span className="inline-block rounded-full bg-slate-800 px-2 py-0.5 text-[11px] uppercase tracking-wider text-sky-300 light:bg-slate-100 light:text-sky-700">
                  {pendingAction.type.replace(/_/g, ' ')}
                </span>
              </div>
            </div>
            <button
              type="button"
              onClick={cancel}
              className="rounded-lg p-1.5 text-slate-400 hover:bg-slate-800 hover:text-slate-200"
              aria-label="Close"
            >
              <X className="h-4 w-4" />
            </button>
          </div>

          <Dialog.Description className="mt-4 text-sm text-slate-300 light:text-slate-600">
            {pendingAction.details}
          </Dialog.Description>

          {pendingAction.slots && pendingAction.slots.length > 0 && (
            <div className="mt-4">
              <p className="mb-2 text-xs font-medium uppercase tracking-wider text-slate-400">
                Available Free Slots {pendingAction.day ? `(${pendingAction.day})` : ''}
              </p>
              <div className="flex flex-wrap gap-2">
                {pendingAction.slots.map((slot) => {
                  const isActive = selectedStart === slot.start && selectedEnd === slot.end;
                  return (
                    <button
                      key={`${slot.start}-${slot.end}`}
                      type="button"
                      onClick={() => selectSlot(slot.start, slot.end)}
                      className={`rounded-xl border px-3 py-1.5 text-xs font-medium transition ${
                        isActive
                          ? 'border-sky-500 bg-sky-500/20 text-sky-300 light:text-sky-700'
                          : 'border-slate-700 bg-slate-800/70 text-slate-300 hover:border-slate-500 light:border-slate-300 light:bg-slate-100 light:text-slate-700'
                      }`}
                    >
                      {slot.label}
                    </button>
                  );
                })}
              </div>
            </div>
          )}

          {selectedStart && selectedEnd && (
            <div className="mt-3 rounded-xl border border-slate-800 bg-slate-950/60 px-3 py-2 text-xs text-slate-300 light:border-slate-200 light:bg-slate-50 light:text-slate-700">
              Selected Time: <span className="font-semibold text-sky-400">{selectedStart} – {selectedEnd}</span>
            </div>
          )}

          <div className="mt-6 flex items-center justify-end gap-3">
            <button
              type="button"
              onClick={cancel}
              disabled={isExecuting}
              className="rounded-xl border border-slate-700 px-4 py-2 text-sm font-medium text-slate-300 hover:bg-slate-800 light:border-slate-300 light:text-slate-700 light:hover:bg-slate-100"
            >
              Cancel
            </button>
            <button
              type="button"
              onClick={confirm}
              disabled={isExecuting}
              className="inline-flex items-center gap-2 rounded-xl bg-emerald-600 px-4 py-2 text-sm font-semibold text-white hover:bg-emerald-500 disabled:opacity-60"
            >
              {isExecuting ? (
                <Loader2 className="h-4 w-4 animate-spin" />
              ) : (
                <Check className="h-4 w-4" />
              )}
              Confirm & Save
            </button>
          </div>
        </Dialog.Content>
      </Dialog.Portal>
    </Dialog.Root>
  );
}
