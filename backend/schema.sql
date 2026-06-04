-- StarSling Dashboard — Supabase schema
-- Run this in the Supabase SQL Editor to create all tables.

-- Enable UUID generation
create extension if not exists "pgcrypto";

-- ── Battles: one row per battle simulation session ──────────────────────────
create table if not exists battles (
  id            bigint generated always as identity primary key,
  battle_id     uuid default gen_random_uuid() unique not null,
  created_at    timestamptz default now(),
  status        text default 'running',
  completed_at  timestamptz
);

-- ── Runs: one row per attempt ────────────────────────────────────────────────
create table if not exists runs (
  id            bigint generated always as identity primary key,
  battle_id     uuid references battles(battle_id) on delete set null,
  created_at    timestamptz default now(),
  attempt_num   int not null,
  total_score   int,
  wins          int not null,
  losses        int not null,
  total_games   int not null,
  avg_moves     real,
  avg_ms        real,
  ships_surviving real,
  hits_taken    real,
  move_savings  int default 0,
  timeout_warnings int default 0,
  errors        int default 0,
  status        text default 'complete'
);

-- ── Games: one row per game within a run ─────────────────────────────────────
create table if not exists games (
  id            bigint generated always as identity primary key,
  battle_id     uuid references battles(battle_id) on delete set null,
  run_id        bigint references runs(id) on delete cascade,
  opponent_id   text not null,
  won           boolean not null,
  moves         int not null,
  ships_lost    int default 0,
  hits_received int default 0,
  strategy      text,
  trust         real default 0,
  created_at    timestamptz default now()
);

-- ── Opponents: latest state per opponent (upserted after each run) ───────────
create table if not exists opponents (
  id              bigint generated always as identity primary key,
  battle_id       uuid references battles(battle_id) on delete set null,
  opponent_id     text unique not null,
  classification  text,
  stability       real default 0,
  trust           real default 0,
  games_played    int default 0,
  wins            int default 0,
  win_rate        real default 0,
  avg_moves       real,
  best_moves      int,
  avg_survival    real,
  exploitable     boolean default false,
  updated_at      timestamptz default now()
);

-- ── Indexes for dashboard queries ────────────────────────────────────────────
create index if not exists idx_battles_uuid on battles(battle_id);
create index if not exists idx_runs_battle on runs(battle_id);
create index if not exists idx_games_battle on games(battle_id);
create index if not exists idx_games_run_id on games(run_id);
create index if not exists idx_games_opponent on games(opponent_id);
create index if not exists idx_runs_created on runs(created_at desc);
create index if not exists idx_opponents_id on opponents(opponent_id);
