import { useCallback } from 'react';
import { toast } from 'sonner';
import { apiUrl } from '../lib/api';
import { useAppStore } from '../stores/appStore';
import type { JarvisAction } from '../types/jarvis';

export function useJarvis(speak: (text: string) => void) {
  const messages = useAppStore((s) => s.messages);
  const isSending = useAppStore((s) => s.isSending);
  const addMessage = useAppStore((s) => s.addMessage);
  const openConfirmation = useAppStore((s) => s.openConfirmation);
  const setIsSending = useAppStore((s) => s.setIsSending);

  const sendMessage = useCallback(
    async (rawText: string, options?: { viaVoice?: boolean }) => {
      const text = rawText.trim();
      if (!text || isSending) return;

      const viaVoice = Boolean(options?.viaVoice);

      addMessage({
        id: `u-${Date.now()}`,
        role: 'user',
        content: text,
        timestamp: new Date().toISOString(),
        viaVoice,
      });

      setIsSending(true);
      try {
        const history = messages.slice(-8).map((m) => ({
          role: m.role,
          content: m.content,
        }));

        const res = await fetch(apiUrl('/api/chat'), {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ message: text, history }),
        });

        if (!res.ok) {
          throw new Error(`Chat failed (${res.status})`);
        }

        const data = (await res.json()) as {
          reply: string;
          action?: JarvisAction | null;
          timestamp?: string;
        };

        addMessage({
          id: `a-${Date.now()}`,
          role: 'assistant',
          content: data.reply,
          timestamp: data.timestamp || new Date().toISOString(),
          viaVoice,
        });

        // Open clean popup confirmation modal instead of burying JSON in chat
        if (data.action) {
          openConfirmation(data.action);
        }

        // Auto-speak ONLY when the user used voice input (mic)
        if (viaVoice) {
          const speechPrompt = data.action
            ? `${data.reply}. Should I confirm: ${data.action.title}?`
            : data.reply;
          speak(speechPrompt);
        }
      } catch (err) {
        toast.error(err instanceof Error ? err.message : 'Failed to reach Jarvis backend');
      } finally {
        setIsSending(false);
      }
    },
    [addMessage, isSending, messages, openConfirmation, setIsSending, speak]
  );

  return { sendMessage, isSending };
}
