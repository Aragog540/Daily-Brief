-- Migration: create profiles table and optional RLS policies for Supabase

-- Create table (idempotent)
create table if not exists public.profiles (
  user_id text primary key,
  email text,
  city text,
  created_at timestamptz default now()
);

-- OPTIONAL: Enable Row Level Security and add policies so authenticated users
-- can read and manage only their own profile. Uncomment if you want frontend
-- clients (anon key) to directly read/upsert profiles without a service key.

-- enable RLS
-- alter table public.profiles enable row level security;

-- allow authenticated users to select their own profile
-- create policy "Select own profile" on public.profiles
--   for select using (auth.uid() = user_id);

-- allow authenticated users to insert their own profile
-- create policy "Insert own profile" on public.profiles
--   for insert with check (auth.uid() = user_id);

-- allow authenticated users to update their own profile
-- create policy "Update own profile" on public.profiles
--   for update using (auth.uid() = user_id) with check (auth.uid() = user_id);

-- If you enable RLS, make sure to test and adjust policies to fit your workflow.
