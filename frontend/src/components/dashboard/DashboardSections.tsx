import { useMemo, useState } from 'react';
import {
  Activity,
  Bell,
  Calendar,
  Check,
  CheckCircle2,
  Clock,
  Globe,
  Moon,
  Smartphone,
  Sun,
  Trash2,
} from 'lucide-react';
import { toast } from 'sonner';
import { getServerUrl, setServerUrl } from '../../lib/api';
import {
  useFreeSlots,
  useSyncData,
  useTaskAction,
  useToggleRoutineCompletion,
} from '../../queries/sync';
import { useAppStore } from '../../stores/appStore';
import { MobileInstallButtonAndModal } from '../modals/MobileInstallModal';
import { AddReminderButton, AddRoutineBlockButton } from '../modals/QuickAddModals';
import { ProjectsLearningsSection } from './ProjectsLearningsSection';

const DAYS = [
  'Monday',
  'Tuesday',
  'Wednesday',
  'Thursday',
  'Friday',
  'Saturday',
  'Sunday',
] as const;

function getTodayInfo() {
  const now = new Date();
  const ymd = now.toISOString().slice(0, 10);
  const weekday = now.toLocaleDateString('en-US', { weekday: 'long' });
  return { ymd, weekday };
}

export function DashboardSections() {
  const { data: sync, isLoading } = useSyncData();
  const { ymd: todayYmd, weekday: todayName } = useMemo(getTodayInfo, []);
  const { data: freeSlotsData } = useFreeSlots(todayName);
  const toggleCompletion = useToggleRoutineCompletion();
  const taskAction = useTaskAction();

  const theme = useAppStore((s) => s.theme);
  const toggleTheme = useAppStore((s) => s.toggleTheme);
  const [serverUrlInput, setServerUrlInput] = useState(() => getServerUrl());

  const routineBlocks = sync?.weekly_routine ?? [];
  const completions = sync?.routine_completions ?? [];
  const tasks = sync?.tasks ?? [];

  const completedTodayIds = useMemo(() => {
    return new Set(
      completions
        .filter((c) => c.date_str === todayYmd && c.status === 'completed')
        .map((c) => c.routine_id)
    );
  }, [completions, todayYmd]);

  const todayBlocks = useMemo(
    () =>
      routineBlocks.filter(
        (b) => b.day_of_week === todayName || b.day_of_week === 'Daily'
      ),
    [routineBlocks, todayName]
  );

  const disciplinePct = useMemo(() => {
    if (todayBlocks.length === 0) return 100;
    const doneCount = todayBlocks.filter((b) => completedTodayIds.has(b.id)).length;
    return Math.round((doneCount / todayBlocks.length) * 100);
  }, [todayBlocks, completedTodayIds]);

  const activeReminders = useMemo(
    () => tasks.filter((t) => t.status !== 'completed' && t.status !== 'rejected'),
    [tasks]
  );

  const calendarItems = useMemo(
    () =>
      activeReminders
        .filter((t) => Boolean(t.due_datetime || t.raw_due_text))
        .slice(0, 12),
    [activeReminders]
  );

  return (
    <div className="space-y-6">
      {/* Top Row: Discipline Score + Today's Free Slots */}
      <div className="grid grid-cols-1 gap-4 lg:grid-cols-2">
        <div className="rounded-2xl border border-slate-800/80 bg-slate-900/60 p-5 light:border-slate-200 light:bg-white">
          <div className="flex items-center justify-between">
            <div className="flex items-center gap-2.5">
              <Activity className="h-5 w-5 text-emerald-400" />
              <h3 className="text-sm font-semibold uppercase tracking-wider text-slate-300 light:text-slate-700">
                Today&apos;s Discipline ({todayName})
              </h3>
            </div>
            <span className="text-2xl font-bold text-emerald-400">{disciplinePct}%</span>
          </div>
          <div className="mt-3 h-2.5 w-full overflow-hidden rounded-full bg-slate-800 light:bg-slate-200">
            <div
              className="h-full rounded-full bg-emerald-500 transition-all duration-300"
              style={{ width: `${disciplinePct}%` }}
            />
          </div>
          <p className="mt-2 text-xs text-slate-400">
            {todayBlocks.filter((b) => completedTodayIds.has(b.id)).length} of{' '}
            {todayBlocks.length} routine blocks completed today ({todayYmd})
          </p>
        </div>

        <div className="rounded-2xl border border-slate-800/80 bg-slate-900/60 p-5 light:border-slate-200 light:bg-white">
          <div className="flex items-center gap-2.5">
            <Clock className="h-5 w-5 text-sky-400" />
            <h3 className="text-sm font-semibold uppercase tracking-wider text-slate-300 light:text-slate-700">
              Free Slots Today ({todayName})
            </h3>
          </div>
          <div className="mt-3 flex flex-wrap gap-2">
            {(freeSlotsData?.slots ?? []).length === 0 ? (
              <span className="text-xs text-slate-400">
                {isLoading ? 'Calculating free slots...' : 'No free windows detected today'}
              </span>
            ) : (
              freeSlotsData!.slots.map((s) => (
                <span
                  key={`${s.start}-${s.end}`}
                  className="rounded-xl border border-sky-500/30 bg-sky-500/10 px-3 py-1.5 text-xs font-medium text-sky-300 light:text-sky-700"
                >
                  {s.label}
                </span>
              ))
            )}
          </div>
        </div>
      </div>

      {/* Section: Projects & Learnings */}
      <ProjectsLearningsSection projects={sync?.projects ?? []} />

      {/* Section: 7-Day Routine Matrix */}
      <section
        id="routine"
        className="rounded-2xl border border-slate-800/80 bg-slate-900/60 p-5 light:border-slate-200 light:bg-white"
      >
        <div className="mb-4 flex flex-wrap items-center justify-between gap-2">
          <div>
            <h2 className="text-base font-semibold">7-Day Fixed Routine &amp; Extra Work</h2>
            <p className="text-xs text-slate-400">
              Check off items directly or tell JARVIS via voice/chat — synced live via WebSocket
            </p>
          </div>
          <AddRoutineBlockButton />
        </div>

        <div className="grid grid-cols-1 gap-4 md:grid-cols-2 xl:grid-cols-3">
          {DAYS.map((day) => {
            const blocks = routineBlocks.filter(
              (b) => b.day_of_week === day || b.day_of_week === 'Daily'
            );
            const dayExtra = activeReminders.filter((t) =>
              `${t.raw_due_text || ''} ${t.description || ''}`
                .toLowerCase()
                .includes(day.toLowerCase())
            );
            const isToday = day === todayName;

            return (
              <div
                key={day}
                className={`rounded-xl border p-4 transition ${
                  isToday
                    ? 'border-sky-500/60 bg-slate-950/70 light:bg-sky-50/40'
                    : 'border-slate-800 bg-slate-950/40 light:border-slate-200 light:bg-slate-50/70'
                }`}
              >
                <div className="mb-3 flex items-center justify-between">
                  <span className="text-sm font-bold">{day}</span>
                  {isToday && (
                    <span className="rounded-full bg-sky-500/20 px-2 py-0.5 text-[10px] font-semibold uppercase text-sky-300 light:text-sky-700">
                      Today
                    </span>
                  )}
                </div>

                <div className="space-y-2">
                  {blocks.length === 0 ? (
                    <p className="text-xs text-slate-500">No fixed blocks</p>
                  ) : (
                    blocks.map((block) => {
                      const isDone = completedTodayIds.has(block.id);
                      return (
                        <label
                          key={block.id}
                          className={`flex cursor-pointer items-start gap-2.5 rounded-lg border px-2.5 py-2 text-xs transition ${
                            isDone
                              ? 'border-emerald-500/30 bg-emerald-500/10 text-emerald-300 light:text-emerald-700'
                              : 'border-slate-800/80 bg-slate-900/60 hover:border-slate-700 light:border-slate-200 light:bg-white'
                          }`}
                        >
                          <input
                            type="checkbox"
                            checked={isDone}
                            onChange={(e) =>
                              toggleCompletion.mutate({
                                routine_id: block.id,
                                date: todayYmd,
                                completed: e.target.checked,
                              })
                            }
                            className="mt-0.5 h-4 w-4 rounded accent-emerald-500"
                          />
                          <div className="flex-1">
                            <p className={isDone ? 'font-medium line-through' : 'font-medium'}>
                              {block.title}
                            </p>
                            <p className="text-[11px] opacity-70">
                              {block.start_time} – {block.end_time}
                            </p>
                          </div>
                          {isDone && (
                            <span className="rounded bg-emerald-500/20 px-1.5 py-0.5 text-[10px] font-semibold">
                              Done
                            </span>
                          )}
                        </label>
                      );
                    })
                  )}
                </div>

                {dayExtra.length > 0 && (
                  <div className="mt-3 border-t border-slate-800/70 pt-2.5 light:border-slate-200">
                    <p className="mb-1.5 text-[10px] font-semibold uppercase tracking-wider text-amber-400">
                      Extra Work Scheduled
                    </p>
                    <div className="space-y-1">
                      {dayExtra.map((item) => (
                        <div
                          key={item.id}
                          className="rounded-md bg-amber-500/10 px-2 py-1 text-[11px] text-amber-200 light:text-amber-800"
                        >
                          {item.title}
                        </div>
                      ))}
                    </div>
                  </div>
                )}
              </div>
            );
          })}
        </div>
      </section>

      {/* Section: Reminders */}
      <section
        id="reminders"
        className="rounded-2xl border border-slate-800/80 bg-slate-900/60 p-5 light:border-slate-200 light:bg-white"
      >
        <div className="mb-4 flex flex-wrap items-center justify-between gap-2">
          <div className="flex items-center gap-2">
            <Bell className="h-5 w-5 text-sky-400" />
            <h2 className="text-base font-semibold">
              Active Reminders &amp; Deadlines ({activeReminders.length})
            </h2>
          </div>
          <AddReminderButton />
        </div>

        {activeReminders.length === 0 ? (
          <p className="text-sm text-slate-400">
            No active reminders. Ask JARVIS in chat to schedule a reminder or free slot!
          </p>
        ) : (
          <div className="space-y-2">
            {activeReminders.map((task) => (
              <div
                key={task.id}
                className="flex flex-wrap items-center justify-between gap-3 rounded-xl border border-slate-800 bg-slate-950/50 px-4 py-3 light:border-slate-200 light:bg-slate-50"
              >
                <div>
                  <div className="flex items-center gap-2">
                    <span className="text-sm font-medium">{task.title}</span>
                    <span
                      className={`rounded-full px-2 py-0.5 text-[10px] font-semibold uppercase ${
                        task.priority === 'high' || task.priority === 'urgent'
                          ? 'bg-rose-500/20 text-rose-300 light:text-rose-700'
                          : 'bg-sky-500/15 text-sky-300 light:text-sky-700'
                      }`}
                    >
                      {task.priority}
                    </span>
                    <span className="rounded-full bg-slate-800 px-2 py-0.5 text-[10px] text-slate-400 light:bg-slate-200 light:text-slate-600">
                      {task.status}
                    </span>
                  </div>
                  {(task.description || task.raw_due_text) && (
                    <p className="mt-0.5 text-xs text-slate-400">
                      {task.description || task.raw_due_text}
                    </p>
                  )}
                </div>

                <div className="flex items-center gap-2">
                  {task.status === 'pending_review' && (
                    <button
                      type="button"
                      onClick={() => taskAction.mutate({ id: task.id, action: 'confirm' })}
                      className="inline-flex items-center gap-1 rounded-lg bg-emerald-600/20 px-2.5 py-1.5 text-xs font-medium text-emerald-300 hover:bg-emerald-600/30"
                    >
                      <Check className="h-3.5 w-3.5" />
                      Confirm
                    </button>
                  )}
                  <button
                    type="button"
                    onClick={() => taskAction.mutate({ id: task.id, action: 'complete' })}
                    className="inline-flex items-center gap-1 rounded-lg bg-sky-500/15 px-2.5 py-1.5 text-xs font-medium text-sky-300 hover:bg-sky-500/25 light:text-sky-700"
                  >
                    <CheckCircle2 className="h-3.5 w-3.5" />
                    Done
                  </button>
                  <button
                    type="button"
                    onClick={() => taskAction.mutate({ id: task.id, action: 'delete' })}
                    className="rounded-lg p-1.5 text-slate-400 hover:bg-rose-500/20 hover:text-rose-300"
                    aria-label="Delete reminder"
                  >
                    <Trash2 className="h-4 w-4" />
                  </button>
                </div>
              </div>
            ))}
          </div>
        )}
      </section>

      {/* Section: Deadlines Calendar */}
      <section
        id="calendar"
        className="rounded-2xl border border-slate-800/80 bg-slate-900/60 p-5 light:border-slate-200 light:bg-white"
      >
        <div className="mb-4 flex items-center gap-2">
          <Calendar className="h-5 w-5 text-amber-400" />
          <h2 className="text-base font-semibold">Deadlines &amp; Scheduled Calendar</h2>
        </div>
        {calendarItems.length === 0 ? (
          <p className="text-sm text-slate-400">No upcoming dated deadlines.</p>
        ) : (
          <div className="grid grid-cols-1 gap-3 sm:grid-cols-2 lg:grid-cols-3">
            {calendarItems.map((item) => (
              <div
                key={item.id}
                className="rounded-xl border border-slate-800 bg-slate-950/60 p-3.5 light:border-slate-200 light:bg-slate-50"
              >
                <p className="text-xs font-semibold text-sky-400">
                  {item.due_datetime
                    ? new Date(item.due_datetime).toLocaleString([], {
                        weekday: 'short',
                        month: 'short',
                        day: 'numeric',
                        hour: '2-digit',
                        minute: '2-digit',
                      })
                    : item.raw_due_text}
                </p>
                <p className="mt-1 text-sm font-medium">{item.title}</p>
              </div>
            ))}
          </div>
        )}
      </section>

      {/* Section: Settings & Mobile */}
      <section
        id="settings"
        className="rounded-2xl border border-slate-800/80 bg-slate-900/60 p-5 light:border-slate-200 light:bg-white"
      >
        <h2 className="mb-4 text-base font-semibold">Settings &amp; Mobile App</h2>
        <div className="grid grid-cols-1 gap-4 md:grid-cols-2">
          <div className="flex items-center justify-between rounded-xl border border-slate-800 bg-slate-950/50 p-4 light:border-slate-200 light:bg-slate-50">
            <div>
              <p className="text-sm font-medium">Appearance Theme</p>
              <p className="text-xs text-slate-400">
                Dark mode default with instant light toggle
              </p>
            </div>
            <button
              type="button"
              onClick={toggleTheme}
              className="inline-flex items-center gap-2 rounded-xl border border-slate-700 px-3.5 py-2 text-xs font-semibold hover:bg-slate-800 light:border-slate-300 light:hover:bg-slate-200"
            >
              {theme === 'dark' ? (
                <>
                  <Sun className="h-4 w-4 text-amber-400" />
                  Switch to Light
                </>
              ) : (
                <>
                  <Moon className="h-4 w-4 text-sky-500" />
                  Switch to Dark
                </>
              )}
            </button>
          </div>

          <div className="flex items-center justify-between gap-3 rounded-xl border border-slate-800 bg-slate-950/50 p-4 light:border-slate-200 light:bg-slate-50">
            <div className="flex items-center gap-3">
              <Smartphone className="h-5 w-5 shrink-0 text-emerald-400" />
              <div>
                <p className="text-sm font-medium">Mobile App (Android &amp; iOS)</p>
                <p className="text-xs text-slate-400">
                  Download APK or install PWA on phone
                </p>
              </div>
            </div>
            <MobileInstallButtonAndModal />
          </div>

          <div className="md:col-span-2 rounded-xl border border-slate-800 bg-slate-950/50 p-4 light:border-slate-200 light:bg-slate-50">
            <div className="mb-2 flex items-center gap-2">
              <Globe className="h-4 w-4 text-sky-400" />
              <p className="text-sm font-medium">Backend Server URL (for Mobile APK)</p>
            </div>
            <p className="mb-3 text-xs text-slate-400">
              Leave blank to use current website origin, or enter your deployed server (e.g. https://jarvis.yourdomain.com).
            </p>
            <div className="flex flex-wrap gap-2">
              <input
                type="url"
                value={serverUrlInput}
                onChange={(e) => setServerUrlInput(e.target.value)}
                placeholder="https://jarvis.yourdomain.com"
                className="flex-1 min-w-[200px] rounded-xl border border-slate-800 bg-slate-900 px-3 py-2 text-xs text-slate-100 placeholder:text-slate-500 focus:border-sky-500 focus:outline-none light:border-slate-300 light:bg-white light:text-slate-900"
              />
              <button
                type="button"
                onClick={() => {
                  setServerUrl(serverUrlInput);
                  toast.success('Server URL saved! Reloading connection...');
                  window.location.reload();
                }}
                className="rounded-xl bg-sky-600 px-4 py-2 text-xs font-semibold text-white hover:bg-sky-500"
              >
                Save URL
              </button>
            </div>
          </div>
        </div>
      </section>
    </div>
  );
}
