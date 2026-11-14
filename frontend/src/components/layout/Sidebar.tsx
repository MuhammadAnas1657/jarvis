import { useState } from 'react';
import {
  Bell,
  Calendar,
  CheckSquare,
  FolderKanban,
  Menu,
  MessageSquare,
  Settings,
  Wifi,
  WifiOff,
  X,
} from 'lucide-react';
import { useWsStore } from '../../stores/wsStore';

const NAV_ITEMS = [
  { id: 'chat', label: 'Chat & Voice', icon: MessageSquare },
  { id: 'projects', label: 'Projects & Learnings', icon: FolderKanban },
  { id: 'routine', label: 'Weekly Routine', icon: CheckSquare },
  { id: 'reminders', label: 'Reminders', icon: Bell },
  { id: 'calendar', label: 'Deadlines Calendar', icon: Calendar },
  { id: 'settings', label: 'Settings & Mobile', icon: Settings },
];

export function Sidebar() {
  const [mobileOpen, setMobileOpen] = useState(false);
  const wsConnected = useWsStore((s) => s.connected);

  const scrollTo = (id: string) => {
    setMobileOpen(false);
    document.getElementById(id)?.scrollIntoView({ behavior: 'smooth', block: 'start' });
  };

  const navContent = (
    <div className="flex h-full flex-col justify-between p-4">
      <div>
        <div className="mb-6 flex items-center gap-3 px-2">
          <img
            src="/jarvis-emblem-dark.png"
            alt="JARVIS"
            className="h-9 w-9 object-contain"
          />
          <div>
            <h1 className="text-base font-bold tracking-wider">JARVIS</h1>
            <p className="text-[11px] text-slate-400">Personal Executive AI</p>
          </div>
        </div>

        <nav className="space-y-1.5">
          {NAV_ITEMS.map(({ id, label, icon: Icon }) => (
            <button
              key={id}
              type="button"
              onClick={() => scrollTo(id)}
              className="flex w-full items-center gap-3 rounded-xl px-3 py-2.5 text-sm font-medium text-slate-300 transition hover:bg-slate-800/80 hover:text-white light:text-slate-700 light:hover:bg-slate-200/70"
            >
              <Icon className="h-4 w-4 text-sky-400" />
              <span>{label}</span>
            </button>
          ))}
        </nav>
      </div>

      <div className="rounded-xl border border-slate-800 bg-slate-900/70 px-3 py-2.5 text-xs light:border-slate-200 light:bg-slate-100">
        <div className="flex items-center gap-2">
          {wsConnected ? (
            <>
              <Wifi className="h-3.5 w-3.5 text-emerald-400" />
              <span className="font-medium text-emerald-400">Live Sync Connected</span>
            </>
          ) : (
            <>
              <WifiOff className="h-3.5 w-3.5 text-amber-400" />
              <span className="font-medium text-amber-400">Reconnecting...</span>
            </>
          )}
        </div>
        <p className="mt-1 text-[11px] text-slate-500">PG LISTEN/NOTIFY + WebSocket</p>
      </div>
    </div>
  );

  return (
    <>
      {/* Mobile top bar */}
      <div className="sticky top-0 z-30 flex items-center justify-between border-b border-slate-800 bg-slate-950/90 px-4 py-3 backdrop-blur md:hidden light:border-slate-200 light:bg-white/90">
        <div className="flex items-center gap-2.5">
          <img src="/jarvis-emblem-dark.png" alt="JARVIS" className="h-7 w-7 object-contain" />
          <span className="font-bold tracking-wider">JARVIS</span>
        </div>
        <button
          type="button"
          onClick={() => setMobileOpen(true)}
          className="rounded-lg p-2 text-slate-300 hover:bg-slate-800"
          aria-label="Open menu"
        >
          <Menu className="h-5 w-5" />
        </button>
      </div>

      {/* Desktop persistent left sidebar */}
      <aside className="hidden w-64 shrink-0 border-r border-slate-800/80 bg-slate-950 md:sticky md:top-0 md:block md:h-screen light:border-slate-200 light:bg-slate-50">
        {navContent}
      </aside>

      {/* Mobile slide-over drawer */}
      {mobileOpen && (
        <div className="fixed inset-0 z-40 flex md:hidden">
          <div className="fixed inset-0 bg-black/60" onClick={() => setMobileOpen(false)} />
          <div className="relative z-10 w-64 bg-slate-950 shadow-xl light:bg-white">
            <button
              type="button"
              onClick={() => setMobileOpen(false)}
              className="absolute right-3 top-3 rounded-lg p-1.5 text-slate-400 hover:bg-slate-800"
              aria-label="Close menu"
            >
              <X className="h-5 w-5" />
            </button>
            {navContent}
          </div>
        </div>
      )}
    </>
  );
}
