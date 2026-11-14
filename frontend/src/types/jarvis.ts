export interface FreeSlot {
  start: string;
  end: string;
  start_12h?: string;
  end_12h?: string;
  duration_minutes?: number;
  duration_hours?: number;
  duration?: string;
  label: string;
}

export interface JarvisAction {
  type:
    | 'schedule_free_slot'
    | 'create_reminder'
    | 'mark_routine'
    | 'unmark_routine'
    | 'complete_reminder'
    | 'delete_reminder'
    | 'add_routine_block'
    | 'delete_routine_block'
    | 'run_audit'
    | 'switch_theme'
    | string;
  title: string;
  details: string;
  day?: string;
  slots?: FreeSlot[];
  params: Record<string, unknown>;
}

export interface ChatMessage {
  id: string;
  role: 'user' | 'assistant';
  content: string;
  timestamp: string;
  viaVoice?: boolean;
}

export interface RoutineBlock {
  id: number;
  day_of_week: string;
  title: string;
  start_time: string;
  end_time: string;
  category: string;
  is_locked: boolean;
}

export interface RoutineCompletion {
  id: number;
  routine_id: number;
  date_str: string;
  status: string;
  completed_at?: string;
}

export interface JarvisTask {
  id: number;
  title: string;
  description?: string;
  raw_due_text?: string;
  due_datetime?: string | null;
  priority: string;
  status: string;
  created_at?: string;
}

export interface ProjectItem {
  id: number;
  title: string;
  category: 'project' | 'learning' | string;
  goal: string;
  total_hours: number;
  session_minutes: number;
  priority: string;
  deadline?: string | null;
  status: string;
  created_at?: string;
}

export interface ProposedSlot {
  day: string;
  start: string;
  end: string;
  duration_minutes: number;
  label: string;
}

export interface SkillItem {
  command: string;
  name: string;
  description: string;
  example: string;
  enabled: boolean;
}

export interface SyncPayload {
  reminders: JarvisTask[];
  tasks: JarvisTask[];
  weekly_routine: RoutineBlock[];
  routine_completions: RoutineCompletion[];
  projects?: ProjectItem[];
  alarms: Array<Record<string, unknown>>;
  courses: Array<Record<string, unknown>>;
  course_logs: Array<Record<string, unknown>>;
  business_deliverables: Array<Record<string, unknown>>;
  small_tasks: Array<Record<string, unknown>>;
  backend?: string;
  synced_at?: string;
}

export interface WsEvent {
  event:
    | 'action_confirmed'
    | 'routine_updated'
    | 'reminder_added'
    | 'reminder_updated'
    | 'reminder_deleted'
    | 'ping'
    | string;
  type?: string;
  data?: Record<string, unknown>;
}
