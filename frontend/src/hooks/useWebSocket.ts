import { useEffect, useRef } from 'react';
import { useQueryClient } from '@tanstack/react-query';
import { getWsUrl } from '../lib/api';
import { SYNC_QUERY_KEY } from '../queries/sync';
import { useWsStore } from '../stores/wsStore';
import type { WsEvent } from '../types/jarvis';

export function useWebSocket() {
  const queryClient = useQueryClient();
  const setConnected = useWsStore((s) => s.setConnected);
  const setLastEvent = useWsStore((s) => s.setLastEvent);
  const retryRef = useRef(0);

  useEffect(() => {
    let ws: WebSocket | null = null;
    let reconnectTimer: number | null = null;
    let cancelled = false;

    const connect = () => {
      if (cancelled) return;
      const url = getWsUrl();
      ws = new WebSocket(url);

      ws.onopen = () => {
        retryRef.current = 0;
        setConnected(true);
      };

      ws.onmessage = (evt) => {
        try {
          const payload = JSON.parse(evt.data) as WsEvent;
          setLastEvent(payload);

          if (
            payload.event === 'action_confirmed' ||
            payload.event === 'routine_updated' ||
            payload.event === 'reminder_added' ||
            payload.event === 'reminder_updated' ||
            payload.event === 'reminder_deleted'
          ) {
            queryClient.invalidateQueries({ queryKey: SYNC_QUERY_KEY });
            queryClient.invalidateQueries({ queryKey: ['jarvis', 'free-slots'] });
          }
        } catch {
          // ignore malformed messages
        }
      };

      ws.onclose = () => {
        setConnected(false);
        if (!cancelled) {
          const delay = Math.min(10000, 1000 * Math.pow(1.5, retryRef.current));
          retryRef.current += 1;
          reconnectTimer = window.setTimeout(connect, delay);
        }
      };

      ws.onerror = () => {
        ws?.close();
      };
    };

    connect();

    return () => {
      cancelled = true;
      if (reconnectTimer) window.clearTimeout(reconnectTimer);
      ws?.close();
    };
  }, [queryClient, setConnected, setLastEvent]);
}
