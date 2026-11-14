import { useState } from 'react';
import { useQueryClient } from '@tanstack/react-query';
import { toast } from 'sonner';
import { apiUrl } from '../lib/api';
import { SYNC_QUERY_KEY } from '../queries/sync';
import { useAppStore } from '../stores/appStore';

export function useConfirmation() {
  const [isExecuting, setIsExecuting] = useState(false);
  const queryClient = useQueryClient();

  const pendingAction = useAppStore((s) => s.pendingAction);
  const isModalOpen = useAppStore((s) => s.isModalOpen);
  const closeConfirmation = useAppStore((s) => s.closeConfirmation);
  const updatePendingActionSlot = useAppStore((s) => s.updatePendingActionSlot);
  const setTheme = useAppStore((s) => s.setTheme);

  const confirm = async () => {
    if (!pendingAction) return;

    if (pendingAction.type === 'switch_theme') {
      const next = (pendingAction.params?.theme as 'dark' | 'light') || 'dark';
      setTheme(next);
      toast.success(`Switched to ${next} theme`);
      closeConfirmation();
      return;
    }

    setIsExecuting(true);
    try {
      const res = await fetch(apiUrl('/api/actions/execute'), {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          action: pendingAction.type,
          params: pendingAction.params || {},
          user_confirmed: true,
        }),
      });
      const data = (await res.json()) as { status?: string; message?: string };
      if (!res.ok || data.status === 'error') {
        throw new Error(data.message || 'Action execution failed');
      }

      toast.success(data.message || `${pendingAction.title} confirmed!`);
      await queryClient.invalidateQueries({ queryKey: SYNC_QUERY_KEY });
      await queryClient.invalidateQueries({ queryKey: ['jarvis', 'free-slots'] });
      closeConfirmation();
    } catch (err) {
      toast.error(err instanceof Error ? err.message : 'Failed to execute action');
    } finally {
      setIsExecuting(false);
    }
  };

  const cancel = () => {
    closeConfirmation();
    toast.info('Action cancelled — nothing changed.');
  };

  return {
    pendingAction,
    isModalOpen,
    isExecuting,
    confirm,
    cancel,
    selectSlot: updatePendingActionSlot,
  };
}
