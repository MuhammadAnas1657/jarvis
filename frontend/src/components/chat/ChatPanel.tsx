import { FormEvent, useEffect, useRef, useState } from 'react';
import {
  ChevronDown,
  ChevronUp,
  Loader2,
  MessageSquare,
  Mic,
  Send,
  Sparkles,
  Trash2,
  Volume2,
  VolumeX,
} from 'lucide-react';
import { useAppStore } from '../../stores/appStore';
import { useVoice } from '../../hooks/useVoice';
import { useJarvis } from '../../hooks/useJarvis';
import { useSkills } from '../../queries/sync';

export function ChatPanel() {
  const [input, setInput] = useState('');
  const [showSkills, setShowSkills] = useState(false);
  const isChatOpen = useAppStore((s) => s.isChatOpen);
  const toggleChatOpen = useAppStore((s) => s.toggleChatOpen);
  const setChatOpen = useAppStore((s) => s.setChatOpen);
  const messages = useAppStore((s) => s.messages);
  const clearMessages = useAppStore((s) => s.clearMessages);
  const bottomRef = useRef<HTMLDivElement | null>(null);
  const { data: skillsData } = useSkills();

  const matchingSkills = (skillsData?.skills ?? []).filter(
    (sk) =>
      showSkills ||
      (input.startsWith('/') &&
        sk.command.toLowerCase().includes(input.split(' ')[0].toLowerCase()))
  );

  const voice = useVoice((transcript) => {
    setChatOpen(true);
    void sendMessage(transcript, { viaVoice: true });
  });

  const { sendMessage, isSending } = useJarvis(voice.speak);

  useEffect(() => {
    if (isChatOpen) {
      bottomRef.current?.scrollIntoView({ behavior: 'smooth' });
    }
  }, [messages.length, isChatOpen]);

  const handleSubmit = async (e: FormEvent) => {
    e.preventDefault();
    if (!input.trim() || isSending) return;
    const text = input;
    setInput('');
    await sendMessage(text, { viaVoice: false });
  };

  return (
    <section
      id="chat"
      className="rounded-2xl border border-slate-800/80 bg-slate-900/60 p-4 shadow-lg transition-all md:p-5 light:border-slate-200 light:bg-white"
    >
      <div
        role="button"
        tabIndex={0}
        onClick={toggleChatOpen}
        onKeyDown={(e) => (e.key === 'Enter' || e.key === ' ') && toggleChatOpen()}
        className={`flex cursor-pointer select-none items-center justify-between gap-2 ${
          isChatOpen ? 'mb-3 border-b border-slate-800/70 pb-3 light:border-slate-200' : ''
        }`}
      >
        <div className="flex items-center gap-3">
          <div className="flex h-9 w-9 items-center justify-center rounded-xl bg-sky-500/15 text-sky-400">
            <MessageSquare className="h-4 w-4" />
          </div>
          <div>
            <div className="flex items-center gap-2">
              <h2 className="text-base font-semibold tracking-tight">
                JARVIS Chat &amp; Push-to-Talk Voice
              </h2>
              <span className="rounded-full bg-slate-800 px-2 py-0.5 text-[10px] font-medium text-slate-300 light:bg-slate-100 light:text-slate-600">
                {messages.length}
              </span>
            </div>
            <p className="text-xs text-slate-400">
              {isChatOpen
                ? 'Hold Mic to speak (auto-speaks reply) • Type for silent text mode'
                : 'Click here to expand chat & voice assistant'}
            </p>
          </div>
        </div>
        <div
          className="flex items-center gap-2"
          onClick={(e) => e.stopPropagation()}
        >
          {voice.isSpeaking && (
            <button
              type="button"
              onClick={voice.stopSpeaking}
              className="inline-flex items-center gap-1.5 rounded-lg bg-amber-500/20 px-2.5 py-1.5 text-xs font-medium text-amber-300 hover:bg-amber-500/30"
            >
              <VolumeX className="h-3.5 w-3.5" />
              Stop Voice
            </button>
          )}
          {isChatOpen && (
            <button
              type="button"
              onClick={clearMessages}
              className="inline-flex items-center gap-1 rounded-lg border border-slate-700 px-2.5 py-1.5 text-xs text-slate-400 hover:bg-slate-800 hover:text-slate-200 light:border-slate-300 light:hover:bg-slate-100"
            >
              <Trash2 className="h-3.5 w-3.5" />
              Clear
            </button>
          )}
          <button
            type="button"
            onClick={toggleChatOpen}
            className="rounded-lg border border-slate-700 p-1.5 text-slate-300 hover:bg-slate-800 light:border-slate-300 light:text-slate-700 light:hover:bg-slate-100"
            aria-label={isChatOpen ? 'Collapse chat' : 'Expand chat'}
          >
            {isChatOpen ? <ChevronUp className="h-4 w-4" /> : <ChevronDown className="h-4 w-4" />}
          </button>
        </div>
      </div>

      {isChatOpen && (
        <>

      {/* Messages area */}
      <div className="h-80 space-y-3 overflow-y-auto pr-1">
        {messages.map((msg) => (
          <div
            key={msg.id}
            className={`flex ${msg.role === 'user' ? 'justify-end' : 'justify-start'}`}
          >
            <div
              className={`max-w-[85%] rounded-2xl px-4 py-2.5 text-sm leading-relaxed ${
                msg.role === 'user'
                  ? 'bg-sky-600 text-white'
                  : 'border border-slate-800 bg-slate-950/70 text-slate-200 light:border-slate-200 light:bg-slate-100 light:text-slate-800'
              }`}
            >
              <p className="whitespace-pre-wrap">{msg.content}</p>
              <div className="mt-1.5 flex items-center justify-between gap-3 text-[10px] opacity-65">
                <span>
                  {new Date(msg.timestamp).toLocaleTimeString([], {
                    hour: '2-digit',
                    minute: '2-digit',
                  })}
                  {msg.viaVoice ? ' • Voice' : ''}
                </span>
                {msg.role === 'assistant' && (
                  <button
                    type="button"
                    onClick={() => voice.speak(msg.content)}
                    className="inline-flex items-center gap-1 hover:opacity-100"
                    title="Listen"
                  >
                    <Volume2 className="h-3 w-3" />
                    Listen
                  </button>
                )}
              </div>
            </div>
          </div>
        ))}
        {isSending && (
          <div className="flex justify-start">
            <div className="inline-flex items-center gap-2 rounded-2xl border border-slate-800 bg-slate-950/70 px-4 py-2 text-xs text-slate-400 light:border-slate-200 light:bg-slate-100">
              <Loader2 className="h-3.5 w-3.5 animate-spin text-sky-400" />
              JARVIS is thinking...
            </div>
          </div>
        )}
        <div ref={bottomRef} />
      </div>

      {/* Slash-Skills Popover */}
      {(showSkills || input.startsWith('/')) && matchingSkills.length > 0 && (
        <div className="mt-3 grid grid-cols-1 gap-1.5 rounded-xl border border-slate-800 bg-slate-950/90 p-2.5 sm:grid-cols-2 light:border-slate-200 light:bg-slate-50">
          {matchingSkills.map((sk) => (
            <button
              key={sk.command}
              type="button"
              onClick={() => {
                setInput(`${sk.command} `);
                setShowSkills(false);
              }}
              className="flex flex-col items-start rounded-lg px-2.5 py-1.5 text-left text-xs transition hover:bg-slate-800/80 light:hover:bg-slate-200/70"
            >
              <span className="font-mono font-semibold text-sky-400 light:text-sky-700">
                {sk.command}{' '}
                <span className="font-sans font-normal text-slate-300 light:text-slate-700">
                  — {sk.name}
                </span>
              </span>
              <span className="line-clamp-1 text-[11px] text-slate-500">{sk.description}</span>
            </button>
          ))}
        </div>
      )}

      {/* Voice PTT + Text Input Bar */}
      <form onSubmit={handleSubmit} className="mt-3 flex items-center gap-2">
        <button
          type="button"
          onClick={() => setShowSkills((v) => !v)}
          className={`flex h-11 shrink-0 items-center gap-1.5 rounded-xl border px-3 text-xs font-semibold transition ${
            showSkills
              ? 'border-sky-500 bg-sky-500/20 text-sky-300 light:text-sky-700'
              : 'border-slate-700 bg-slate-800 text-slate-300 hover:bg-slate-700 light:border-slate-300 light:bg-slate-100 light:text-slate-700'
          }`}
          title="JARVIS Slash Skills"
        >
          <Sparkles className="h-4 w-4 text-sky-400" />
          <span className="hidden sm:inline">Skills</span>
        </button>
        <button
          type="button"
          onPointerDown={() => void voice.startRecording()}
          onPointerUp={voice.stopRecording}
          onPointerCancel={voice.stopRecording}
          onPointerLeave={() => voice.isRecording && voice.stopRecording()}
          disabled={voice.isTranscribing}
          className={`flex h-11 shrink-0 select-none items-center gap-2 rounded-xl px-4 text-xs font-semibold transition ${
            voice.isRecording
              ? 'animate-pulse bg-red-600 text-white shadow-lg shadow-red-600/30'
              : voice.isTranscribing
                ? 'bg-amber-600/80 text-white'
                : 'border border-slate-700 bg-slate-800 text-slate-200 hover:bg-slate-700 light:border-slate-300 light:bg-slate-100 light:text-slate-800'
          }`}
          title="Hold to speak, release to send"
        >
          {voice.isTranscribing ? (
            <>
              <Loader2 className="h-4 w-4 animate-spin" />
              <span>Transcribing...</span>
            </>
          ) : (
            <>
              <Mic className="h-4 w-4" />
              <span>{voice.isRecording ? 'Listening...' : 'Hold to Talk'}</span>
            </>
          )}
        </button>

        <input
          type="text"
          value={input}
          onChange={(e) => setInput(e.target.value)}
          placeholder="Message JARVIS in Roman-Urdu or English..."
          className="h-11 flex-1 rounded-xl border border-slate-800 bg-slate-950/80 px-4 text-sm text-slate-100 placeholder:text-slate-500 focus:border-sky-500 focus:outline-none light:border-slate-300 light:bg-white light:text-slate-900"
        />

        <button
          type="submit"
          disabled={!input.trim() || isSending}
          className="flex h-11 items-center gap-1.5 rounded-xl bg-sky-600 px-4 text-sm font-semibold text-white transition hover:bg-sky-500 disabled:opacity-50"
        >
          <Send className="h-4 w-4" />
          <span className="hidden sm:inline">Send</span>
        </button>
      </form>
        </>
      )}
    </section>
  );
}
