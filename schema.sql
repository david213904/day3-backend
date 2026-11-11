-- Supabase 대시보드 > SQL Editor 에서 한 번 실행하세요
create table if not exists public.items (
  id bigint generated always as identity primary key,
  name text not null,
  created_at timestamptz not null default now()
)

-- ───── 미세먼지 (에어코리아) ─────
create table if not exists public.air_quality (
  id bigint generated always as identity primary key,
  station_name text not null,
  sido_name text,
  data_time text not null,
  pm10 numeric, pm10_grade int,
  pm25 numeric, pm25_grade int,
  o3 numeric, no2 numeric, co numeric, so2 numeric,
  khai numeric, khai_grade int,
  created_at timestamptz not null default now(),
  unique (station_name, data_time)
);
alter table public.air_quality enable row level security;
-- Supabase → SQL Editor 에 붙여 넣고 Run
create table if not exists air_readings (
id bigint generated always as identity primary key,
source text not null, -- 'airkorea'(진짜) / 'demo'(연습)
sido text not null,
station text not null, -- 측정소 이름
data_time timestamptz not null, -- 측정 시각
pm10 int, -- 미세먼지 ㎍/㎥
pm25 int, -- 초미세먼지 ㎍/㎥
o3 real,
no2 real,
pm10_grade text, -- 좋음/보통/나쁨/매우나쁨 (FastAPI가 계산)
pm25_grade text,
collected_at timestamptz not null default now(),
unique (source, station, data_time) -- 같은 시각 중복 저장 방지
);
create table if not exists collect_logs (
id bigint generated always as identity primary key,
ran_at timestamptz not null default now(),
source text,
fetched int, -- 받은 개수
fixed_values int, -- 고친(지운) 이상값 개수
dropped int, -- 버린 행 개수
cleaned int, -- 정리된 행 개수
saved int -- 저장된 행 개수
);
-- 브라우저에서 직접 못 건드리게 잠금. FastAPI는 secret 키라서 통과.
alter table air_readings enable row level security;
alter table collect_logs enable row level security;