create table if not exists public.user_steam_accounts (
  user_id text primary key,
  steam_id text not null unique,
  profile_url text not null,
  ownership_sync_status text not null default 'pending',
  ownership_sync_error text,
  owned_game_count integer not null default 0,
  linked_at timestamptz not null default timezone('utc', now()),
  last_sync_at timestamptz,
  created_at timestamptz not null default timezone('utc', now()),
  updated_at timestamptz not null default timezone('utc', now()),
  constraint user_steam_accounts_sync_status_check
    check (ownership_sync_status in ('pending', 'synced', 'private_or_unavailable', 'error'))
);

create table if not exists public.user_owned_games (
  user_id text not null references public.user_steam_accounts(user_id) on delete cascade,
  steam_id text not null,
  appid text not null,
  name text,
  playtime_forever integer,
  last_played_at timestamptz,
  created_at timestamptz not null default timezone('utc', now()),
  updated_at timestamptz not null default timezone('utc', now()),
  primary key (user_id, appid)
);

create index if not exists user_owned_games_user_id_idx on public.user_owned_games (user_id);
create index if not exists user_owned_games_steam_id_idx on public.user_owned_games (steam_id);

drop trigger if exists user_steam_accounts_set_updated_at on public.user_steam_accounts;
create trigger user_steam_accounts_set_updated_at
before update on public.user_steam_accounts
for each row
execute function public.set_updated_at();

drop trigger if exists user_owned_games_set_updated_at on public.user_owned_games;
create trigger user_owned_games_set_updated_at
before update on public.user_owned_games
for each row
execute function public.set_updated_at();
