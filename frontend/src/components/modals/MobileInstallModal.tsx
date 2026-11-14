import { useEffect, useState } from 'react';
import * as Dialog from '@radix-ui/react-dialog';
import { QRCodeSVG } from 'qrcode.react';
import { Check, Copy, Download, QrCode, Smartphone, X } from 'lucide-react';
import { toast } from 'sonner';
import { apiUrl, getServerUrl } from '../../lib/api';

interface BeforeInstallPromptEvent extends Event {
  prompt: () => Promise<void>;
  userChoice: Promise<{ outcome: 'accepted' | 'dismissed' }>;
}

interface MobileInstallInfo {
  install_url: string;
  public_url?: string;
  lan_ip: string;
  port: number;
  apk_available: boolean;
  apk_download_url: string;
}

export function MobileInstallButtonAndModal() {
  const [open, setOpen] = useState(false);
  const [deferredPrompt, setDeferredPrompt] =
    useState<BeforeInstallPromptEvent | null>(null);
  const [info, setInfo] = useState<MobileInstallInfo | null>(null);
  const [copied, setCopied] = useState(false);

  useEffect(() => {
    const handler = (e: Event) => {
      e.preventDefault();
      setDeferredPrompt(e as BeforeInstallPromptEvent);
    };
    window.addEventListener('beforeinstallprompt', handler);
    return () => window.removeEventListener('beforeinstallprompt', handler);
  }, []);

  const handleOpen = async () => {
    setOpen(true);
    try {
      const res = await fetch(apiUrl('/api/mobile/install-info'));
      if (res.ok) {
        const data = (await res.json()) as MobileInstallInfo;
        setInfo(data);
      }
    } catch {
      // Fallback to current origin if offline
    }
  };

  const handleNativeInstall = async () => {
    if (!deferredPrompt) {
      toast.info(
        'In your mobile browser menu, tap "Add to Home Screen" or "Install app".'
      );
      return;
    }
    await deferredPrompt.prompt();
    const choice = await deferredPrompt.userChoice;
    if (choice.outcome === 'accepted') {
      toast.success('JARVIS app installed on your device!');
      setDeferredPrompt(null);
      setOpen(false);
    }
  };

  const isLocalHost =
    window.location.hostname === 'localhost' || window.location.hostname === '127.0.0.1';
  const serverOrigin = getServerUrl() || window.location.origin;
  const mobileUrl =
    isLocalHost && info?.lan_ip
      ? `http://${info.lan_ip}:${window.location.port || info.port || 3000}`
      : serverOrigin;

  const qrTargetUrl = info?.apk_available
    ? `${mobileUrl}${info.apk_download_url}`
    : mobileUrl;

  const copyUrl = async () => {
    await navigator.clipboard.writeText(qrTargetUrl);
    setCopied(true);
    toast.success('Mobile URL copied!');
    setTimeout(() => setCopied(false), 2000);
  };

  return (
    <>
      <button
        type="button"
        onClick={() => void handleOpen()}
        className="inline-flex items-center gap-2 rounded-xl bg-emerald-600 px-3.5 py-2 text-xs font-semibold text-white transition hover:bg-emerald-500"
      >
        <Download className="h-4 w-4" />
        Download App
      </button>

      <Dialog.Root open={open} onOpenChange={setOpen}>
        <Dialog.Portal>
          <Dialog.Overlay className="fixed inset-0 z-50 bg-black/70 backdrop-blur-sm" />
          <Dialog.Content className="fixed left-1/2 top-1/2 z-50 w-[92vw] max-w-md -translate-x-1/2 -translate-y-1/2 rounded-2xl border border-slate-700 bg-slate-900 p-6 text-slate-100 shadow-2xl light:border-slate-200 light:bg-white light:text-slate-900">
            <div className="flex items-start justify-between gap-3">
              <div className="flex items-center gap-3">
                <div className="flex h-10 w-10 items-center justify-center rounded-xl bg-emerald-500/15 text-emerald-400">
                  <Smartphone className="h-5 w-5" />
                </div>
                <div>
                  <Dialog.Title className="text-base font-semibold">
                    Download JARVIS Mobile App
                  </Dialog.Title>
                  <Dialog.Description className="text-xs text-slate-400">
                    Android APK + Offline-First PWA for Android &amp; iOS
                  </Dialog.Description>
                </div>
              </div>
              <button
                type="button"
                onClick={() => setOpen(false)}
                className="rounded-lg p-1.5 text-slate-400 hover:bg-slate-800 light:hover:bg-slate-100"
              >
                <X className="h-4 w-4" />
              </button>
            </div>

            <div className="mt-5 space-y-4">
              {info?.apk_available ? (
                <a
                  href={apiUrl(info.apk_download_url)}
                  download="jarvis.apk"
                  className="flex w-full items-center justify-center gap-2 rounded-xl bg-emerald-600 px-4 py-2.5 text-sm font-semibold text-white hover:bg-emerald-500"
                >
                  <Download className="h-4 w-4" />
                  Download Android APK (jarvis.apk)
                </a>
              ) : (
                <div className="rounded-xl border border-amber-500/30 bg-amber-500/10 px-3.5 py-2.5 text-xs text-amber-300 light:text-amber-800">
                  <strong>APK not compiled yet on server.</strong> Run the{' '}
                  <code className="rounded bg-black/20 px-1">.github/workflows/build-apk.yml</code>{' '}
                  action or drop <code className="rounded bg-black/20 px-1">mobile/dist/jarvis.apk</code>{' '}
                  to enable direct APK download.
                </div>
              )}

              <button
                type="button"
                onClick={() => void handleNativeInstall()}
                className="flex w-full items-center justify-center gap-2 rounded-xl bg-sky-600 px-4 py-2.5 text-sm font-semibold text-white hover:bg-sky-500"
              >
                <Download className="h-4 w-4" />
                {deferredPrompt ? 'Install Web App (1-Click)' : 'Install via Browser Menu'}
              </button>

              <div className="flex flex-col items-center rounded-xl border border-slate-800 bg-white p-4 text-slate-900 light:border-slate-200">
                <QRCodeSVG
                  value={qrTargetUrl}
                  size={168}
                  level="M"
                  includeMargin
                />
                <span className="mt-2 inline-flex items-center gap-1 text-[11px] font-medium text-slate-600">
                  <QrCode className="h-3.5 w-3.5" />
                  {info?.apk_available
                    ? 'Scan with phone camera to download jarvis.apk'
                    : 'Scan with phone camera to open & install'}
                </span>
              </div>

              <div className="flex items-center gap-2 rounded-xl border border-slate-800 bg-slate-950/60 px-3 py-2 text-xs light:border-slate-200 light:bg-slate-100">
                <span className="flex-1 truncate font-mono text-sky-400 light:text-sky-700">
                  {qrTargetUrl}
                </span>
                <button
                  type="button"
                  onClick={() => void copyUrl()}
                  className="inline-flex items-center gap-1 rounded-lg border border-slate-700 px-2.5 py-1 text-[11px] font-medium hover:bg-slate-800 light:border-slate-300 light:hover:bg-slate-200"
                >
                  {copied ? (
                    <>
                      <Check className="h-3.5 w-3.5 text-emerald-400" />
                      Copied
                    </>
                  ) : (
                    <>
                      <Copy className="h-3.5 w-3.5" />
                      Copy
                    </>
                  )}
                </button>
              </div>
            </div>
          </Dialog.Content>
        </Dialog.Portal>
      </Dialog.Root>
    </>
  );
}
