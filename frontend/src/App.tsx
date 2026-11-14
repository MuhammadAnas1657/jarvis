import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { Toaster } from 'sonner';
import { Sidebar } from './components/layout/Sidebar';
import { ChatPanel } from './components/chat/ChatPanel';
import { DashboardSections } from './components/dashboard/DashboardSections';
import { ConfirmationModal } from './components/modals/ConfirmationModal';
import { useWebSocket } from './hooks/useWebSocket';

const queryClient = new QueryClient();

function JarvisShell() {
  useWebSocket();

  return (
    <div className="min-h-screen bg-slate-950 text-slate-100 md:flex light:bg-slate-50 light:text-slate-900">
      <Sidebar />
      <main className="flex-1 space-y-6 p-4 md:p-6 lg:p-8">
        <ChatPanel />
        <DashboardSections />
      </main>
      <ConfirmationModal />
      <Toaster richColors position="top-right" />
    </div>
  );
}

export function App() {
  return (
    <QueryClientProvider client={queryClient}>
      <JarvisShell />
    </QueryClientProvider>
  );
}

export default App;
