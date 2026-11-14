import { useState } from 'react';
import * as Dialog from '@radix-ui/react-dialog';
import {
  BookOpen,
  Check,
  CheckCircle2,
  FolderKanban,
  Loader2,
  Plus,
  Sparkles,
  Trash2,
  X,
} from 'lucide-react';
import { toast } from 'sonner';
import { useProjectMutations } from '../../queries/sync';
import type { ProjectItem, ProposedSlot } from '../../types/jarvis';

interface Props {
  projects: ProjectItem[];
}

export function ProjectsLearningsSection({ projects }: Props) {
  const { proposeSchedule, createProject, updateProjectStatus, deleteProject } =
    useProjectMutations();

  const [wizardOpen, setWizardOpen] = useState(false);
  const [step, setStep] = useState<1 | 2 | 3>(1);
  const [category, setCategory] = useState<'project' | 'learning'>('project');
  const [title, setTitle] = useState('');
  const [goal, setGoal] = useState('');
  const [totalHours, setTotalHours] = useState(4);
  const [sessionMinutes, setSessionMinutes] = useState(60);
  const [deadline, setDeadline] = useState('');
  const [priority, setPriority] = useState<'high' | 'medium' | 'low'>('high');
  const [proposedSlots, setProposedSlots] = useState<ProposedSlot[]>([]);
  const [selectedIndexes, setSelectedIndexes] = useState<number[]>([]);

  const openWizard = (cat: 'project' | 'learning') => {
    setCategory(cat);
    setStep(1);
    setTitle('');
    setGoal('');
    setTotalHours(cat === 'project' ? 6 : 3);
    setSessionMinutes(60);
    setDeadline('');
    setPriority(cat === 'project' ? 'high' : 'medium');
    setProposedSlots([]);
    setSelectedIndexes([]);
    setWizardOpen(true);
  };

  const handleComputeSlots = async () => {
    try {
      const res = await proposeSchedule.mutateAsync({
        title: title.trim(),
        category,
        goal: goal.trim(),
        total_hours: totalHours,
        session_minutes: sessionMinutes,
        priority,
        deadline: deadline || undefined,
      });
      setProposedSlots(res.proposed_slots);
      setSelectedIndexes(res.proposed_slots.map((_, idx) => idx));
      setStep(3);
    } catch (err) {
      toast.error(err instanceof Error ? err.message : 'Failed to propose slots');
    }
  };

  const handleConfirmSchedule = async () => {
    const chosen = proposedSlots.filter((_, i) => selectedIndexes.includes(i));
    try {
      await createProject.mutateAsync({
        title: title.trim(),
        category,
        goal: goal.trim(),
        total_hours: totalHours,
        session_minutes: sessionMinutes,
        priority,
        deadline: deadline || undefined,
        confirmed: true,
        selected_slots: chosen,
      });
      toast.success(
        `${category === 'project' ? 'Project' : 'Learning'} "${title}" scheduled into ${chosen.length} weekday slot(s)!`
      );
      setWizardOpen(false);
    } catch (err) {
      toast.error(err instanceof Error ? err.message : 'Failed to save');
    }
  };

  const toggleSlot = (idx: number) => {
    setSelectedIndexes((prev) =>
      prev.includes(idx) ? prev.filter((i) => i !== idx) : [...prev, idx]
    );
  };

  const projectItems = projects.filter((p) => p.category !== 'learning');
  const learningItems = projects.filter((p) => p.category === 'learning');

  const renderCard = (item: ProjectItem) => {
    const isDone = item.status === 'completed';
    return (
      <div
        key={item.id}
        className={`rounded-xl border p-3.5 transition ${
          isDone
            ? 'border-emerald-500/30 bg-emerald-500/10'
            : 'border-slate-800 bg-slate-950/60 light:border-slate-200 light:bg-slate-50'
        }`}
      >
        <div className="flex items-start justify-between gap-2">
          <div>
            <div className="flex items-center gap-2">
              <span className={`text-sm font-semibold ${isDone ? 'line-through opacity-75' : ''}`}>
                {item.title}
              </span>
              <span className="rounded-full bg-sky-500/15 px-2 py-0.5 text-[10px] font-semibold uppercase text-sky-300 light:text-sky-700">
                {item.priority}
              </span>
            </div>
            {item.goal && <p className="mt-1 text-xs text-slate-400">{item.goal}</p>}
            <p className="mt-1.5 text-[11px] text-slate-500">
              {item.total_hours}h total • {item.session_minutes}m sessions
              {item.deadline ? ` • Due ${item.deadline}` : ''}
            </p>
          </div>
          <div className="flex items-center gap-1">
            {!isDone && (
              <button
                type="button"
                onClick={() => updateProjectStatus.mutate({ id: item.id, status: 'completed' })}
                className="rounded-lg p-1.5 text-emerald-400 hover:bg-emerald-500/20"
                title="Mark completed"
              >
                <CheckCircle2 className="h-4 w-4" />
              </button>
            )}
            <button
              type="button"
              onClick={() => deleteProject.mutate(item.id)}
              className="rounded-lg p-1.5 text-slate-400 hover:bg-rose-500/20 hover:text-rose-300"
              title="Delete"
            >
              <Trash2 className="h-4 w-4" />
            </button>
          </div>
        </div>
      </div>
    );
  };

  return (
    <section
      id="projects"
      className="rounded-2xl border border-slate-800/80 bg-slate-900/60 p-5 light:border-slate-200 light:bg-white"
    >
      <div className="mb-4 flex flex-wrap items-center justify-between gap-3">
        <div>
          <h2 className="text-base font-semibold">Current Projects &amp; Active Learnings</h2>
          <p className="text-xs text-slate-400">
            Add projects or learnings — JARVIS asks 3 questions and schedules them into your weekday free slots
          </p>
        </div>
        <div className="flex items-center gap-2">
          <button
            type="button"
            onClick={() => openWizard('project')}
            className="inline-flex items-center gap-1.5 rounded-xl bg-sky-600 px-3 py-2 text-xs font-semibold text-white hover:bg-sky-500"
          >
            <Plus className="h-3.5 w-3.5" />
            Add Project
          </button>
          <button
            type="button"
            onClick={() => openWizard('learning')}
            className="inline-flex items-center gap-1.5 rounded-xl bg-emerald-600 px-3 py-2 text-xs font-semibold text-white hover:bg-emerald-500"
          >
            <Plus className="h-3.5 w-3.5" />
            Add Learning
          </button>
        </div>
      </div>

      <div className="grid grid-cols-1 gap-4 lg:grid-cols-2">
        <div className="space-y-2.5">
          <div className="flex items-center gap-2 text-xs font-semibold uppercase tracking-wider text-sky-400">
            <FolderKanban className="h-4 w-4" />
            Projects ({projectItems.length})
          </div>
          {projectItems.length === 0 ? (
            <p className="rounded-xl border border-dashed border-slate-800 p-4 text-xs text-slate-500 light:border-slate-300">
              No active projects yet. Click &quot;Add Project&quot; to schedule one into your free slots.
            </p>
          ) : (
            projectItems.map(renderCard)
          )}
        </div>

        <div className="space-y-2.5">
          <div className="flex items-center gap-2 text-xs font-semibold uppercase tracking-wider text-emerald-400">
            <BookOpen className="h-4 w-4" />
            Learnings ({learningItems.length})
          </div>
          {learningItems.length === 0 ? (
            <p className="rounded-xl border border-dashed border-slate-800 p-4 text-xs text-slate-500 light:border-slate-300">
              No active learning tracks yet. Click &quot;Add Learning&quot; to start one.
            </p>
          ) : (
            learningItems.map(renderCard)
          )}
        </div>
      </div>

      {/* 3-Step Interactive Intake & Weekday Slot Proposal Modal */}
      <Dialog.Root open={wizardOpen} onOpenChange={setWizardOpen}>
        <Dialog.Portal>
          <Dialog.Overlay className="fixed inset-0 z-50 bg-black/70 backdrop-blur-sm" />
          <Dialog.Content className="fixed left-1/2 top-1/2 z-50 w-[92vw] max-w-lg -translate-x-1/2 -translate-y-1/2 rounded-2xl border border-slate-700 bg-slate-900 p-6 text-slate-100 shadow-2xl light:border-slate-200 light:bg-white light:text-slate-900">
            <div className="flex items-start justify-between gap-3">
              <div className="flex items-center gap-2.5">
                <Sparkles className="h-5 w-5 text-sky-400" />
                <div>
                  <Dialog.Title className="text-base font-semibold">
                    {category === 'project' ? 'New Project' : 'New Learning'} — Step {step} of 3
                  </Dialog.Title>
                  <Dialog.Description className="text-xs text-slate-400">
                    {step === 1 && 'Question 1: What are we building or learning?'}
                    {step === 2 && 'Question 2: How much time & when is the target?'}
                    {step === 3 && 'Question 3: Priority & confirm weekday free slots'}
                  </Dialog.Description>
                </div>
              </div>
              <button
                type="button"
                onClick={() => setWizardOpen(false)}
                className="rounded-lg p-1.5 text-slate-400 hover:bg-slate-800 light:hover:bg-slate-100"
              >
                <X className="h-4 w-4" />
              </button>
            </div>

            {step === 1 && (
              <div className="mt-5 space-y-4">
                <div>
                  <label className="mb-1 block text-xs font-medium text-slate-300 light:text-slate-700">
                    Title
                  </label>
                  <input
                    type="text"
                    value={title}
                    onChange={(e) => setTitle(e.target.value)}
                    placeholder={
                      category === 'project'
                        ? 'e.g. FastAPI + React Portfolio App'
                        : 'e.g. System Design & Distributed Caching'
                    }
                    className="w-full rounded-xl border border-slate-700 bg-slate-950 px-3.5 py-2.5 text-sm focus:border-sky-500 focus:outline-none light:border-slate-300 light:bg-white"
                  />
                </div>
                <div>
                  <label className="mb-1 block text-xs font-medium text-slate-300 light:text-slate-700">
                    What does &quot;Done&quot; look like? (Goal)
                  </label>
                  <textarea
                    rows={2}
                    value={goal}
                    onChange={(e) => setGoal(e.target.value)}
                    placeholder="e.g. Deployed live with tests and README"
                    className="w-full rounded-xl border border-slate-700 bg-slate-950 px-3.5 py-2 text-sm focus:border-sky-500 focus:outline-none light:border-slate-300 light:bg-white"
                  />
                </div>
                <div className="flex justify-end">
                  <button
                    type="button"
                    disabled={!title.trim()}
                    onClick={() => setStep(2)}
                    className="rounded-xl bg-sky-600 px-4 py-2 text-sm font-semibold text-white hover:bg-sky-500 disabled:opacity-50"
                  >
                    Next →
                  </button>
                </div>
              </div>
            )}

            {step === 2 && (
              <div className="mt-5 space-y-4">
                <div className="grid grid-cols-2 gap-3">
                  <div>
                    <label className="mb-1 block text-xs font-medium text-slate-300 light:text-slate-700">
                      Total Hours Needed
                    </label>
                    <input
                      type="number"
                      min={0.5}
                      max={100}
                      step={0.5}
                      value={totalHours}
                      onChange={(e) => setTotalHours(Number(e.target.value))}
                      className="w-full rounded-xl border border-slate-700 bg-slate-950 px-3 py-2 text-sm light:border-slate-300 light:bg-white"
                    />
                  </div>
                  <div>
                    <label className="mb-1 block text-xs font-medium text-slate-300 light:text-slate-700">
                      Daily Session (mins)
                    </label>
                    <select
                      value={sessionMinutes}
                      onChange={(e) => setSessionMinutes(Number(e.target.value))}
                      className="w-full rounded-xl border border-slate-700 bg-slate-950 px-3 py-2 text-sm light:border-slate-300 light:bg-white"
                    >
                      <option value={30}>30 min</option>
                      <option value={60}>60 min (1 hr)</option>
                      <option value={90}>90 min (1.5 hrs)</option>
                      <option value={120}>120 min (2 hrs)</option>
                    </select>
                  </div>
                </div>
                <div className="grid grid-cols-2 gap-3">
                  <div>
                    <label className="mb-1 block text-xs font-medium text-slate-300 light:text-slate-700">
                      Priority
                    </label>
                    <select
                      value={priority}
                      onChange={(e) => setPriority(e.target.value as 'high' | 'medium' | 'low')}
                      className="w-full rounded-xl border border-slate-700 bg-slate-950 px-3 py-2 text-sm light:border-slate-300 light:bg-white"
                    >
                      <option value="high">High (Projects First)</option>
                      <option value="medium">Medium</option>
                      <option value="low">Low</option>
                    </select>
                  </div>
                  <div>
                    <label className="mb-1 block text-xs font-medium text-slate-300 light:text-slate-700">
                      Target Deadline (optional)
                    </label>
                    <input
                      type="date"
                      value={deadline}
                      onChange={(e) => setDeadline(e.target.value)}
                      className="w-full rounded-xl border border-slate-700 bg-slate-950 px-3 py-2 text-sm light:border-slate-300 light:bg-white"
                    />
                  </div>
                </div>
                <div className="flex justify-between">
                  <button
                    type="button"
                    onClick={() => setStep(1)}
                    className="rounded-xl border border-slate-700 px-4 py-2 text-sm text-slate-300 hover:bg-slate-800 light:border-slate-300 light:text-slate-700"
                  >
                    ← Back
                  </button>
                  <button
                    type="button"
                    disabled={proposeSchedule.isPending}
                    onClick={() => void handleComputeSlots()}
                    className="inline-flex items-center gap-2 rounded-xl bg-sky-600 px-4 py-2 text-sm font-semibold text-white hover:bg-sky-500"
                  >
                    {proposeSchedule.isPending && <Loader2 className="h-4 w-4 animate-spin" />}
                    Find Weekday Free Slots →
                  </button>
                </div>
              </div>
            )}

            {step === 3 && (
              <div className="mt-5 space-y-4">
                <p className="text-xs text-slate-300 light:text-slate-600">
                  JARVIS calculated these weekday free-slot sessions for{' '}
                  <strong>{title}</strong>. Uncheck any slot you want to skip:
                </p>
                <div className="max-h-56 space-y-2 overflow-y-auto pr-1">
                  {proposedSlots.length === 0 ? (
                    <p className="text-xs text-amber-400">
                      No free weekday slots found matching your routine.
                    </p>
                  ) : (
                    proposedSlots.map((slot, idx) => {
                      const checked = selectedIndexes.includes(idx);
                      return (
                        <label
                          key={`${slot.day}-${slot.start}-${idx}`}
                          className={`flex cursor-pointer items-center gap-3 rounded-xl border px-3 py-2.5 text-xs transition ${
                            checked
                              ? 'border-sky-500/60 bg-sky-500/15 text-sky-200 light:text-sky-800'
                              : 'border-slate-800 bg-slate-950/50 text-slate-400 light:border-slate-200 light:bg-slate-50'
                          }`}
                        >
                          <input
                            type="checkbox"
                            checked={checked}
                            onChange={() => toggleSlot(idx)}
                            className="h-4 w-4 accent-sky-500"
                          />
                          <span className="font-medium">{slot.label}</span>
                        </label>
                      );
                    })
                  )}
                </div>
                <div className="flex justify-between">
                  <button
                    type="button"
                    onClick={() => setStep(2)}
                    className="rounded-xl border border-slate-700 px-4 py-2 text-sm text-slate-300 hover:bg-slate-800 light:border-slate-300 light:text-slate-700"
                  >
                    ← Back
                  </button>
                  <button
                    type="button"
                    disabled={createProject.isPending}
                    onClick={() => void handleConfirmSchedule()}
                    className="inline-flex items-center gap-2 rounded-xl bg-emerald-600 px-4 py-2 text-sm font-semibold text-white hover:bg-emerald-500"
                  >
                    {createProject.isPending ? (
                      <Loader2 className="h-4 w-4 animate-spin" />
                    ) : (
                      <Check className="h-4 w-4" />
                    )}
                    Confirm &amp; Schedule ({selectedIndexes.length})
                  </button>
                </div>
              </div>
            )}
          </Dialog.Content>
        </Dialog.Portal>
      </Dialog.Root>
    </section>
  );
}
