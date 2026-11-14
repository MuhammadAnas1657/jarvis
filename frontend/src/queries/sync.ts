import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { apiUrl } from '../lib/api';
import type { FreeSlot, ProposedSlot, SkillItem, SyncPayload } from '../types/jarvis';

export const SYNC_QUERY_KEY = ['jarvis', 'sync'] as const;

export function useSyncData() {
  return useQuery<SyncPayload>({
    queryKey: SYNC_QUERY_KEY,
    queryFn: async () => {
      const res = await fetch(apiUrl('/api/sync'));
      if (!res.ok) throw new Error('Failed to load sync payload');
      return res.json();
    },
    refetchInterval: 30000,
    staleTime: 5000,
  });
}

export function useFreeSlots(day: string) {
  return useQuery<{ day: string; slots: FreeSlot[] }>({
    queryKey: ['jarvis', 'free-slots', day],
    queryFn: async () => {
      const res = await fetch(apiUrl(`/api/routine/free-slots?day=${encodeURIComponent(day)}`));
      if (!res.ok) throw new Error('Failed to load free slots');
      return res.json();
    },
    staleTime: 10000,
  });
}

export function useToggleRoutineCompletion() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: async (vars: { routine_id: number; date: string; completed: boolean }) => {
      const res = await fetch(apiUrl('/api/routine/completions'), {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(vars),
      });
      if (!res.ok) throw new Error('Failed to toggle routine completion');
      return res.json();
    },
    onMutate: async (vars) => {
      await queryClient.cancelQueries({ queryKey: SYNC_QUERY_KEY });
      const prev = queryClient.getQueryData<SyncPayload>(SYNC_QUERY_KEY);
      if (prev) {
        const filtered = prev.routine_completions.filter(
          (c) => !(c.routine_id === vars.routine_id && c.date_str === vars.date)
        );
        if (vars.completed) {
          filtered.push({
            id: Date.now(),
            routine_id: vars.routine_id,
            date_str: vars.date,
            status: 'completed',
          });
        }
        queryClient.setQueryData<SyncPayload>(SYNC_QUERY_KEY, {
          ...prev,
          routine_completions: filtered,
        });
      }
      return { prev };
    },
    onError: (_err, _vars, ctx) => {
      if (ctx?.prev) {
        queryClient.setQueryData(SYNC_QUERY_KEY, ctx.prev);
      }
    },
    onSettled: () => {
      queryClient.invalidateQueries({ queryKey: SYNC_QUERY_KEY });
    },
  });
}

export function useTaskAction() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: async (vars: { id: number; action: 'confirm' | 'reject' | 'delete' | 'complete' }) => {
      if (vars.action === 'complete') {
        const res = await fetch(apiUrl('/api/actions/execute'), {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({
            action: 'complete_reminder',
            params: { task_id: vars.id },
            user_confirmed: true,
          }),
        });
        if (!res.ok) throw new Error('Failed to complete task');
        return res.json();
      }
      if (vars.action === 'delete') {
        const res = await fetch(apiUrl(`/api/tasks/${vars.id}`), { method: 'DELETE' });
        if (!res.ok) throw new Error('Failed to delete task');
        return res.json();
      }
      const res = await fetch(apiUrl(`/api/tasks/${vars.id}/${vars.action}`), { method: 'POST' });
      if (!res.ok) throw new Error(`Failed to ${vars.action} task`);
      return res.json();
    },
    onSettled: () => {
      queryClient.invalidateQueries({ queryKey: SYNC_QUERY_KEY });
    },
  });
}

export function useSkills() {
  return useQuery<{ skills: SkillItem[] }>({
    queryKey: ['jarvis', 'skills'],
    queryFn: async () => {
      const res = await fetch(apiUrl('/api/skills'));
      if (!res.ok) throw new Error('Failed to load skills');
      return res.json();
    },
    staleTime: 60000,
  });
}

export function useProjectMutations() {
  const queryClient = useQueryClient();

  const proposeSchedule = useMutation({
    mutationFn: async (body: {
      title: string;
      category: 'project' | 'learning';
      goal: string;
      total_hours: number;
      session_minutes: number;
      priority: string;
      deadline?: string;
      preferred_days?: string[];
    }) => {
      const res = await fetch(apiUrl('/api/projects/propose-schedule'), {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(body),
      });
      if (!res.ok) throw new Error('Failed to compute weekday slots');
      return res.json() as Promise<{ proposed_slots: ProposedSlot[] }>;
    },
  });

  const createProject = useMutation({
    mutationFn: async (body: {
      title: string;
      category: 'project' | 'learning';
      goal: string;
      total_hours: number;
      session_minutes: number;
      priority: string;
      deadline?: string;
      confirmed: boolean;
      selected_slots: ProposedSlot[];
    }) => {
      const res = await fetch(apiUrl('/api/projects'), {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(body),
      });
      if (!res.ok) throw new Error('Failed to save project');
      return res.json();
    },
    onSettled: () => {
      queryClient.invalidateQueries({ queryKey: SYNC_QUERY_KEY });
    },
  });

  const updateProjectStatus = useMutation({
    mutationFn: async (vars: { id: number; status: string }) => {
      const res = await fetch(apiUrl(`/api/projects/${vars.id}`), {
        method: 'PATCH',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ status: vars.status }),
      });
      if (!res.ok) throw new Error('Failed to update project');
      return res.json();
    },
    onSettled: () => {
      queryClient.invalidateQueries({ queryKey: SYNC_QUERY_KEY });
    },
  });

  const deleteProject = useMutation({
    mutationFn: async (id: number) => {
      const res = await fetch(apiUrl(`/api/projects/${id}`), { method: 'DELETE' });
      if (!res.ok) throw new Error('Failed to delete project');
      return res.json();
    },
    onSettled: () => {
      queryClient.invalidateQueries({ queryKey: SYNC_QUERY_KEY });
    },
  });

  return { proposeSchedule, createProject, updateProjectStatus, deleteProject };
}
