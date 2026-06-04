import { createClient } from "@supabase/supabase-js";

const supabaseUrl = process.env.NEXT_PUBLIC_SUPABASE_URL!;
const supabaseKey = process.env.NEXT_PUBLIC_SUPABASE_ANON_KEY!;

export const supabase = createClient(supabaseUrl, supabaseKey);

// -- Types matching the DB schema --

export interface Battle {
  id: number;
  battle_id: string; // UUID
  created_at: string;
  status: string;
  completed_at: string | null;
}

export interface Run {
  id: number;
  battle_id: string | null; // UUID
  created_at: string;
  attempt_num: number;
  total_score: number;
  wins: number;
  losses: number;
  total_games: number;
  avg_moves: number;
  avg_ms: number;
  ships_surviving: number;
  hits_taken: number;
  move_savings: number;
  timeout_warnings: number;
  errors: number;
  status: string;
}

export interface Game {
  id: number;
  battle_id: string | null; // UUID
  run_id: number;
  opponent_id: string;
  won: boolean;
  moves: number;
  ships_lost: number;
  hits_received: number;
  strategy: string | null;
  trust: number;
  created_at: string;
}

export interface Opponent {
  id: number;
  battle_id: string | null; // UUID
  opponent_id: string;
  classification: string | null;
  stability: number;
  trust: number;
  games_played: number;
  wins: number;
  win_rate: number;
  avg_moves: number;
  best_moves: number;
  avg_survival: number;
  exploitable: boolean;
  updated_at: string;
}

// -- Data fetching helpers --

export async function createBattle(): Promise<Battle | null> {
  const { data, error } = await supabase
    .from("battles")
    .insert({ status: "running" })
    .select()
    .single();

  if (error) {
    console.error("Failed to create battle:", error);
    return null;
  }
  return data;
}

export async function fetchBattle(battleId: string): Promise<Battle | null> {
  const { data, error } = await supabase
    .from("battles")
    .select("*")
    .eq("battle_id", battleId)
    .single();

  if (error) {
    console.error("Failed to fetch battle:", error);
    return null;
  }
  return data;
}

export async function fetchRuns(limit = 50): Promise<Run[]> {
  const { data, error } = await supabase
    .from("runs")
    .select("*")
    .order("created_at", { ascending: false })
    .limit(limit);

  if (error) {
    console.error("Failed to fetch runs:", error);
    return [];
  }
  return data ?? [];
}

export async function fetchGames(runId: number): Promise<Game[]> {
  const { data, error } = await supabase
    .from("games")
    .select("*")
    .eq("run_id", runId);

  if (error) {
    console.error("Failed to fetch games:", error);
    return [];
  }
  return data ?? [];
}

export async function fetchOpponents(): Promise<Opponent[]> {
  const { data, error } = await supabase
    .from("opponents")
    .select("*")
    .order("opponent_id");

  if (error) {
    console.error("Failed to fetch opponents:", error);
    return [];
  }
  return data ?? [];
}
