export interface User {
  id: string;
  name: string;
  email: string;
  is_demo: boolean;
  clinic_id: string;
  clinic_name: string;
  clinic_slug: string;
}

export interface Session {
  token: string;
  user: User;
}

export interface Doctor {
  id: number;
  name: string;
  name_hi: string;
  specialty: string;
  specialty_hi: string;
  slot_minutes: number;
  schedule: Record<string, [string, string][]>;
}

export interface Appointment {
  id: number;
  doctor_id: number;
  doctor_name: string;
  patient_name: string;
  patient_phone: string;
  starts_at: string;
  ends_at: string;
  status: 'booked' | 'cancelled';
  source: 'voice' | 'staff' | 'seed';
  call_id: string | null;
}

export type Outcome = 'in_progress' | 'booked' | 'rescheduled' | 'cancelled' | 'handoff' | 'ended';

export interface CallSummary {
  id: string;
  created_at: string;
  outcome: Outcome;
  handoff_reason: string | null;
  language: string | null;
  provider: string;
  turns: number;
  patient_name: string | null;
  avg_agent_ms: number | null;
}

export interface CallTurn {
  role: 'patient' | 'agent';
  text: string;
  stage: string | null;
  stt_ms: number | null;
  agent_ms: number | null;
  tts_ms: number | null;
}

export interface CallDetail extends Omit<CallSummary, 'turns' | 'patient_name' | 'avg_agent_ms'> {
  appointment: { doctor: string | null; starts_at: string; status: string } | null;
  turns: CallTurn[];
}

export interface Meta {
  provider: string;
  model: string;
  demo_mode: boolean;
  voice_enabled: boolean;
  timezone: string;
}

export interface ClinicInfo {
  name: string;
  is_demo: boolean;
  voice_enabled: boolean;
  demo_mode: boolean;
  doctors: { name: string; name_hi: string; specialty: string; specialty_hi: string }[];
}

export interface TurnResponse {
  transcript: string;
  reply: string;
  stage: string;
  outcome: Outcome;
  done: boolean;
  latency: { stt_ms: number | null; agent_ms: number | null; tts_ms: number | null };
  audio_b64: string | null;
}
