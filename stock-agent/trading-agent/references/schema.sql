create table if not exists market_bars_1d (
  symbol text not null,
  name text not null,
  trade_date text not null,
  open real not null,
  close real not null,
  high real not null,
  low real not null,
  volume real not null,
  adjust_type text not null default 'qfq',
  source text not null default 'akshare',
  updated_at text not null,
  primary key (symbol, trade_date, adjust_type)
);

create table if not exists market_universes (
  universe_id text primary key,
  name text not null,
  status text not null default 'active',
  created_at text not null
);

create table if not exists market_universe_members (
  universe_id text not null,
  symbol text not null,
  name text not null,
  asset_type text not null,
  sector_name text not null,
  is_sector_etf integer not null default 1,
  enabled integer not null default 1,
  effective_from text,
  effective_to text,
  primary key (universe_id, symbol)
);

create table if not exists strategy_definitions (
  strategy_id text primary key,
  name text not null,
  type text not null,
  market_scope text not null,
  description text,
  created_at text not null
);

create table if not exists strategy_versions (
  strategy_id text not null,
  version text not null,
  parameters_json text not null,
  rules_json text not null,
  enabled integer not null default 1,
  created_at text not null,
  primary key (strategy_id, version)
);

create table if not exists strategy_execution_policies (
  strategy_id text not null,
  version text not null,
  allowed_universe_id text not null,
  allowed_asset_type text not null,
  allowed_market_scope text not null,
  require_latest_sync integer not null default 1,
  require_recent_backtest_for_live integer not null default 1,
  max_backtest_staleness_days integer not null default 30,
  created_at text not null,
  primary key (strategy_id, version)
);

create table if not exists strategy_backtest_runs (
  run_id text primary key,
  strategy_id text not null,
  version text not null,
  symbol text not null,
  start_date text not null,
  end_date text not null,
  total_return real,
  annual_return real,
  max_drawdown real,
  win_rate real,
  trade_count integer,
  report_path text,
  status text not null,
  created_at text not null
);

create table if not exists trading_trade_plans (
  plan_id text primary key,
  strategy_id text not null,
  version text not null,
  symbol text not null,
  trade_mode text not null,
  signal_date text not null,
  action text not null,
  target_position real not null,
  rationale text not null,
  status text not null,
  created_at text not null
);

create table if not exists ops_sync_runs (
  sync_id text primary key,
  sync_type text not null,
  trade_date text,
  status text not null,
  total_symbols integer not null default 0,
  success_symbols integer not null default 0,
  failed_symbols integer not null default 0,
  started_at text not null,
  finished_at text
);
