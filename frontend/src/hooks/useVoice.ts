import { useCallback, useEffect, useRef, useState } from 'react';
import { toast } from 'sonner';
import { apiUrl } from '../lib/api';

function detectAudioMimeType(): string | undefined {
  if (typeof MediaRecorder === 'undefined') return undefined;
  const candidates = [
    'audio/webm;codecs=opus',
    'audio/webm',
    'audio/ogg;codecs=opus',
    'audio/mp4',
  ];
  return candidates.find((m) => MediaRecorder.isTypeSupported(m));
}

function cleanTextForSpeech(text: string): string {
  return text
    .replace(/```[\s\S]*?```/g, ' ')
    .replace(/[#*_`~>-]+/g, ' ')
    .replace(/\[([^\]]+)\]\([^\)]+\)/g, '$1')
    .replace(/\s+/g, ' ')
    .trim();
}

export function useVoice(onTranscript: (text: string) => void) {
  const [isRecording, setIsRecording] = useState(false);
  const [isTranscribing, setIsTranscribing] = useState(false);
  const [isSpeaking, setIsSpeaking] = useState(false);

  const recorderRef = useRef<MediaRecorder | null>(null);
  const streamRef = useRef<MediaStream | null>(null);
  const chunksRef = useRef<Blob[]>([]);
  const onTranscriptRef = useRef(onTranscript);
  onTranscriptRef.current = onTranscript;

  const stopSpeaking = useCallback(() => {
    if (typeof window !== 'undefined' && 'speechSynthesis' in window) {
      window.speechSynthesis.cancel();
    }
    setIsSpeaking(false);
  }, []);

  const speak = useCallback((rawText: string) => {
    if (typeof window === 'undefined' || !('speechSynthesis' in window)) return;
    const cleaned = cleanTextForSpeech(rawText);
    if (!cleaned) return;

    // Kill any previous utterance immediately so 2 voices NEVER overlap
    window.speechSynthesis.cancel();

    const utterance = new SpeechSynthesisUtterance(cleaned);
    utterance.rate = 1.03;
    utterance.pitch = 1.0;

    const voices = window.speechSynthesis.getVoices();
    const preferred =
      voices.find((v) => /en-(GB|US)/i.test(v.lang) && /natural|neural|google|david|mark/i.test(v.name)) ||
      voices.find((v) => v.lang.startsWith('en'));
    if (preferred) {
      utterance.voice = preferred;
    }

    utterance.onstart = () => setIsSpeaking(true);
    utterance.onend = () => setIsSpeaking(false);
    utterance.onerror = () => setIsSpeaking(false);

    window.speechSynthesis.speak(utterance);
  }, []);

  const startRecording = useCallback(async () => {
    // 1. Always interrupt Jarvis immediately when user presses mic
    stopSpeaking();

    if (recorderRef.current && recorderRef.current.state === 'recording') {
      return;
    }

    if (!navigator.mediaDevices?.getUserMedia) {
      toast.error('Microphone is not supported in this browser.');
      return;
    }

    try {
      const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
      streamRef.current = stream;
      chunksRef.current = [];

      const mimeType = detectAudioMimeType();
      const recorder = mimeType ? new MediaRecorder(stream, { mimeType }) : new MediaRecorder(stream);
      recorderRef.current = recorder;

      recorder.ondataavailable = (e) => {
        if (e.data && e.data.size > 0) {
          chunksRef.current.push(e.data);
        }
      };

      recorder.onstop = async () => {
        const tracks = streamRef.current?.getTracks() || [];
        tracks.forEach((t) => t.stop());
        streamRef.current = null;

        const recordedType = recorder.mimeType || mimeType || 'audio/webm';
        const blob = new Blob(chunksRef.current, { type: recordedType });
        chunksRef.current = [];

        if (blob.size < 400) {
          toast.info('Hold the mic button while speaking.');
          return;
        }

        setIsTranscribing(true);
        try {
          const ext = recordedType.includes('ogg')
            ? 'ogg'
            : recordedType.includes('mp4')
              ? 'mp4'
              : 'webm';
          const form = new FormData();
          form.append('file', blob, `ptt.${ext}`);

          const res = await fetch(apiUrl('/api/voice/transcribe'), {
            method: 'POST',
            body: form,
          });
          if (!res.ok) {
            throw new Error(`Transcription failed (${res.status})`);
          }
          const data = (await res.json()) as { text?: string };
          const text = (data.text || '').trim();
          if (text) {
            onTranscriptRef.current(text);
          } else {
            toast.info('Could not catch speech — please try again.');
          }
        } catch (err) {
          toast.error(err instanceof Error ? err.message : 'Voice transcription failed');
        } finally {
          setIsTranscribing(false);
        }
      };

      // Record as a single clean utterance (no timeslice fragmentation)
      recorder.start();
      setIsRecording(true);
    } catch {
      toast.error('Microphone permission denied or unavailable.');
      setIsRecording(false);
    }
  }, [stopSpeaking]);

  const stopRecording = useCallback(() => {
    setIsRecording(false);
    const recorder = recorderRef.current;
    if (recorder && recorder.state === 'recording') {
      try {
        recorder.stop();
      } catch {
        // ignore if already stopped
      }
    }
  }, []);

  useEffect(() => {
    return () => {
      stopSpeaking();
      const tracks = streamRef.current?.getTracks() || [];
      tracks.forEach((t) => t.stop());
    };
  }, [stopSpeaking]);

  return {
    isRecording,
    isTranscribing,
    isSpeaking,
    startRecording,
    stopRecording,
    speak,
    stopSpeaking,
  };
}
