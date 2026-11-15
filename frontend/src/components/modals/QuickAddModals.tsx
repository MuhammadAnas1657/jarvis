import { FormEvent, useState } from 'react';
import * as Dialog from '@radix-ui/react-dialog';
import { useQueryClient } from '@tanstack/react-query';
import { Plus, X } from 'lucide-react';
import { toast } from 'sonner';
import { apiUrl } from '../../lib/api';
import { SYNC_QUERY_KEY } from '../../queries/sync';

const DAYS = [
  'Monday',
  'Tuesday',
  'Wednesday',
  'Thursday',
  'Friday',
  'Saturday',
  'Sunday',
  'Daily',
];

export function AddReminderButton() {
  const queryClient = useQueryClient();
  const [open, setOpen] = useState(false);
  const [title, setTitle] = useState('');
  const [dueDatetime, setDueDatetime] = useState('');
  const [priority, setPriority] = useState<'normal' | 'high' | 'urgent'>('normal');
  const [description, setDescription] = useState('');
  const [saving, setSaving] = useState(false);

  const handleSubmit = async (e: FormEvent) => {
    e.preventDefault();
    if (!title.trim()) return;
    setSaving(true);
    try {
      const res = await fetch(apiUrl('/api/actions/execute'), {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          action: 'create_reminder',
          params: {
            title: title.trim(),
            description: description.trim(),
            due_datetime: dueDatetime ? new Date(dueDatetime).toISOString() : null,
            raw_due_text: dueDatetime || '',
            priority,
          },
          user_confirmed: true,
        }),
      });
      if (!res.ok) throw new Error('Failed to create reminder');
      toast.success(`Added reminder "${title.trim()}"`);
      await queryClient.invalidateQueries({ queryKey: SYNC_QUERY_KEY });
      setTitle('');
      setDueDatetime('');
      setDescription('');
      setPriority('normal');
      setOpen(false);
    } catch (err) {
      toast.error(err instanceof Error ? err.message : 'Failed to save reminder');
    } finally {
      setSaving(false);
    }
  };

  return (
    <>
      <button
        type="button"
        onClick={() => setOpen(true)}
        className="inline-flex items-center gap-1.5 rounded-xl bg-sky-600 px-3 py-1.5 text-xs font-semibold text-white transition hover:bg-sky-500"
        title="Add reminder or deadline"
      >
        <Plus className="h-3.5 w-3.5" />
        Add Reminder
      </button>

      <Dialog.Root open={open} onOpenChange={setOpen}>
        <Dialog.Portal>
          <Dialog.Overlay className="fixed inset-0 z-50 bg-black/70 backdrop-blur-sm" />
          <Dialog.Content className="fixed left-1/2 top-1/2 z-50 w-[92vw] max-w-md -translate-x-1/2 -translate-y-1/2 rounded-2xl border border-slate-700 bg-slate-900 p-6 text-slate-100 shadow-2xl light:border-slate-200 light:bg-white light:text-slate-900">
            <div className="flex items-center justify-between">
              <Dialog.Title className="text-base font-semibold">
                Add Reminder / Deadline
              </Dialog.Title>
              <button
                type="button"
                onClick={() => setOpen(false)}
                className="rounded-lg p-1 text-slate-400 hover:bg-slate-800 light:hover:bg-slate-100"
              >
                <X className="h-4 w-4" />
              </button>
            </div>

            <form onSubmit={(e) => void handleSubmit(e)} className="mt-4 space-y-3.5">
              <div>
                <label className="mb-1 block text-xs font-medium text-slate-300 light:text-slate-700">
                  Title
                </label>
                <input
                  type="text"
                  required
                  value={title}
                  onChange={(e) => setTitle(e.target.value)}
                  placeholder="e.g. Submit OS Assignment"
                  className="w-full rounded-xl border border-slate-700 bg-slate-950 px-3 py-2 text-sm focus:border-sky-500 focus:outline-none light:border-slate-300 light:bg-white"
                />
              </div>

              <div className="grid grid-cols-2 gap-3">
                <div>
                  <label className="mb-1 block text-xs font-medium text-slate-300 light:text-slate-700">
                    Due Date &amp; Time
                  </label>
                  <input
                    type="datetime-local"
                    value={dueDatetime}
                    onChange={(e) => setDueDatetime(e.target.value)}
                    className="w-full rounded-xl border border-slate-700 bg-slate-950 px-3 py-2 text-xs light:border-slate-300 light:bg-white"
                  />
                </div>
                <div>
                  <label className="mb-1 block text-xs font-medium text-slate-300 light:text-slate-700">
                    Priority
                  </label>
                  <select
                    value={priority}
                    onChange={(e) => setPriority(e.target.value as 'normal' | 'high' | 'urgent')}
                    className="w-full rounded-xl border border-slate-700 bg-slate-950 px-3 py-2 text-sm light:border-slate-300 light:bg-white"
                  >
                    <option value="normal">Normal</option>
                    <option value="high">High</option>
                    <option value="urgent">Urgent</option>
                  </select>
                </div>
              </div>

              <div>
                <label className="mb-1 block text-xs font-medium text-slate-300 light:text-slate-700">
                  Notes (optional)
                </label>
                <input
                  type="text"
                  value={description}
                  onChange={(e) => setDescription(e.target.value)}
                  placeholder="Details..."
                  className="w-full rounded-xl border border-slate-700 bg-slate-950 px-3 py-2 text-sm light:border-slate-300 light:bg-white"
                />
              </div>

              <div className="flex justify-end gap-2 pt-2">
                <button
                  type="button"
                  onClick={() => setOpen(false)}
                  className="rounded-xl border border-slate-700 px-4 py-2 text-xs font-medium text-slate-300 hover:bg-slate-800 light:border-slate-300 light:text-slate-700"
                >
                  Cancel
                </button>
                <button
                  type="submit"
                  disabled={saving || !title.trim()}
                  className="rounded-xl bg-emerald-600 px-4 py-2 text-xs font-semibold text-white hover:bg-emerald-500 disabled:opacity-50"
                >
                  {saving ? 'Saving...' : 'Save Reminder'}
                </button>
              </div>
            </form>
          </Dialog.Content>
        </Dialog.Portal>
      </Dialog.Root>
    </>
  );
}

export function AddRoutineBlockButton() {
  const queryClient = useQueryClient();
  const [open, setOpen] = useState(false);
  const [day, setDay] = useState('Monday');
  const [title, setTitle] = useState('');
  const [startTime, setStartTime] = useState('20:00');
  const [endTime, setEndTime] = useState('21:00');
  const [saving, setSaving] = useState(false);

  const handleSubmit = async (e: FormEvent) => {
    e.preventDefault();
    if (!title.trim()) return;
    setSaving(true);
    try {
      const res = await fetch(apiUrl('/api/actions/execute'), {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          action: 'add_routine_block',
          params: {
            day_of_week: day,
            title: title.trim(),
            start_time: startTime,
            end_time: endTime,
            category: 'fixed',
          },
          user_confirmed: true,
        }),
      });
      if (!res.ok) throw new Error('Failed to add routine block');
      toast.success(`Added "${title.trim()}" to ${day}`);
      await queryClient.invalidateQueries({ queryKey: SYNC_QUERY_KEY });
      await queryClient.invalidateQueries({ queryKey: ['jarvis', 'free-slots'] });
      setTitle('');
      setOpen(false);
    } catch (err) {
      toast.error(err instanceof Error ? err.message : 'Failed to save routine block');
    } finally {
      setSaving(false);
    }
  };

  return (
    <>
      <button
        type="button"
        onClick={() => setOpen(true)}
        className="inline-flex items-center gap-1.5 rounded-xl bg-sky-600 px-3 py-1.5 text-xs font-semibold text-white transition hover:bg-sky-500"
        title="Add fixed routine block"
      >
        <Plus className="h-3.5 w-3.5" />
        Add Block
      </button>

      <Dialog.Root open={open} onOpenChange={setOpen}>
        <Dialog.Portal>
          <Dialog.Overlay className="fixed inset-0 z-50 bg-black/70 backdrop-blur-sm" />
          <Dialog.Content className="fixed left-1/2 top-1/2 z-50 w-[92vw] max-w-md -translate-x-1/2 -translate-y-1/2 rounded-2xl border border-slate-700 bg-slate-900 p-6 text-slate-100 shadow-2xl light:border-slate-200 light:bg-white light:text-slate-900">
            <div className="flex items-center justify-between">
              <Dialog.Title className="text-base font-semibold">
                Add Weekly Routine Block
              </Dialog.Title>
              <button
                type="button"
                onClick={() => setOpen(false)}
                className="rounded-lg p-1 text-slate-400 hover:bg-slate-800 light:hover:bg-slate-100"
              >
                <X className="h-4 w-4" />
              </button>
            </div>

            <form onSubmit={(e) => void handleSubmit(e)} className="mt-4 space-y-3.5">
              <div>
                <label className="mb-1 block text-xs font-medium text-slate-300 light:text-slate-700">
                  Day
                </label>
                <select
                  value={day}
                  onChange={(e) => setDay(e.target.value)}
                  className="w-full rounded-xl border border-slate-700 bg-slate-950 px-3 py-2 text-sm light:border-slate-300 light:bg-white"
                >
                  {DAYS.map((d) => (
                    <option key={d} value={d}>
                      {d}
                    </option>
                  ))}
                </select>
              </div>

              <div>
                <label className="mb-1 block text-xs font-medium text-slate-300 light:text-slate-700">
                  Activity Title
                </label>
                <input
                  type="text"
                  required
                  value={title}
                  onChange={(e) => setTitle(e.target.value)}
                  placeholder="e.g. Gym / Deep Work"
                  className="w-full rounded-xl border border-slate-700 bg-slate-950 px-3 py-2 text-sm light:border-slate-300 light:bg-white"
                />
              </div>

              <div className="grid grid-cols-2 gap-3">
                <div>
                  <label className="mb-1 block text-xs font-medium text-slate-300 light:text-slate-700">
                    Start Time
                  </label>
                  <input
                    type="time"
                    required
                    value={startTime}
                    onChange={(e) => setStartTime(e.target.value)}
                    className="w-full rounded-xl border border-slate-700 bg-slate-950 px-3 py-2 text-sm light:border-slate-300 light:bg-white"
                  />
                </div>
                <div>
                  <label className="mb-1 block text-xs font-medium text-slate-300 light:text-slate-700">
                    End Time
                  </label>
                  <input
                    type="time"
                    required
                    value={endTime}
                    onChange={(e) => setEndTime(e.target.value)}
                    className="w-full rounded-xl border border-slate-700 bg-slate-950 px-3 py-2 text-sm light:border-slate-300 light:bg-white"
                  />
                </div>
              </div>

              <div className="flex justify-end gap-2 pt-2">
                <button
                  type="button"
                  onClick={() => setOpen(false)}
                  className="rounded-xl border border-slate-700 px-4 py-2 text-xs font-medium text-slate-300 hover:bg-slate-800 light:border-slate-300 light:text-slate-700"
                >
                  Cancel
                </button>
                <button
                  type="submit"
                  disabled={saving || !title.trim()}
                  className="rounded-xl bg-emerald-600 px-4 py-2 text-xs font-semibold text-white hover:bg-emerald-500 disabled:opacity-50"
                >
                  {saving ? 'Saving...' : 'Save Block'}
                </button>
              </div>
            </form>
          </Dialog.Content>
        </Dialog.Portal>
      </Dialog.Root>
    </>
  );
}
