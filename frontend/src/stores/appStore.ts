import { create } from 'zustand';
import type { ChatMessage, JarvisAction } from '../types/jarvis';

interface AppState {
  theme: 'dark' | 'light';
  isChatOpen: boolean;
  isSidebarCollapsed: boolean;
  messages: ChatMessage[];
  pendingAction: JarvisAction | null;
  isModalOpen: boolean;
  isSending: boolean;
  setTheme: (theme: 'dark' | 'light') => void;
  toggleTheme: () => void;
  setChatOpen: (open: boolean) => void;
  toggleChatOpen: () => void;
  toggleSidebarCollapsed: () => void;
  addMessage: (msg: ChatMessage) => void;
  clearMessages: () => void;
  openConfirmation: (action: JarvisAction) => void;
  updatePendingActionSlot: (start: string, end: string) => void;
  closeConfirmation: () => void;
  setIsSending: (val: boolean) => void;
}

const savedTheme =
  (typeof window !== 'undefined' && (localStorage.getItem('jarvis_theme') as 'dark' | 'light')) || 'dark';

if (typeof document !== 'undefined') {
  document.documentElement.classList.toggle('dark', savedTheme === 'dark');
  document.documentElement.classList.toggle('light', savedTheme === 'light');
}

export const useAppStore = create<AppState>((set) => ({
  theme: savedTheme,
  isChatOpen: false,
  isSidebarCollapsed: false,
  messages: [
    {
      id: 'welcome-1',
      role: 'assistant',
      content:
        'Assalam-o-Alaikum Anas! Main JARVIS hoon — tumhara personal AI executive. Hold the Mic button to speak, ya neeche type karo. Commands confirm karne ke liye clean popup modal aayega.',
      timestamp: new Date().toISOString(),
    },
  ],
  pendingAction: null,
  isModalOpen: false,
  isSending: false,
  setTheme: (theme) => {
    localStorage.setItem('jarvis_theme', theme);
    document.documentElement.classList.toggle('dark', theme === 'dark');
    document.documentElement.classList.toggle('light', theme === 'light');
    set({ theme });
  },
  toggleTheme: () =>
    set((s) => {
      const next = s.theme === 'dark' ? 'light' : 'dark';
      localStorage.setItem('jarvis_theme', next);
      document.documentElement.classList.toggle('dark', next === 'dark');
      document.documentElement.classList.toggle('light', next === 'light');
      return { theme: next };
    }),
  setChatOpen: (isChatOpen) => set({ isChatOpen }),
  toggleChatOpen: () => set((s) => ({ isChatOpen: !s.isChatOpen })),
  toggleSidebarCollapsed: () => set((s) => ({ isSidebarCollapsed: !s.isSidebarCollapsed })),
  addMessage: (msg) => set((s) => ({ messages: [...s.messages, msg] })),
  clearMessages: () => set({ messages: [] }),
  openConfirmation: (action) => set({ pendingAction: action, isModalOpen: true }),
  updatePendingActionSlot: (start, end) =>
    set((s) => {
      if (!s.pendingAction) return s;
      return {
        pendingAction: {
          ...s.pendingAction,
          params: {
            ...s.pendingAction.params,
            start_time: start,
            end_time: end,
          },
        },
      };
    }),
  closeConfirmation: () => set({ pendingAction: null, isModalOpen: false }),
  setIsSending: (val) => set({ isSending: val }),
}));
