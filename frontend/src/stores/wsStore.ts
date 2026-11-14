import { create } from 'zustand';
import type { WsEvent } from '../types/jarvis';

interface WsState {
  connected: boolean;
  lastEvent: WsEvent | null;
  setConnected: (connected: boolean) => void;
  setLastEvent: (event: WsEvent) => void;
}

export const useWsStore = create<WsState>((set) => ({
  connected: false,
  lastEvent: null,
  setConnected: (connected) => set({ connected }),
  setLastEvent: (lastEvent) => set({ lastEvent }),
}));
