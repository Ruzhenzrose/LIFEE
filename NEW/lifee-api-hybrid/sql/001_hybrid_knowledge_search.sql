-- Hybrid retrieval schema for LIFEE (vector 70% + keyword 30%)
-- Run in Supabase SQL editor (safe to rerun)

create extension if not exists vector;

create table if not exists public.persona_knowledge_chunks (
  id bigserial primary key,
  persona_id text not null,
  chunk_text text not null,
  source text not null default 'manual',
  metadata jsonb not null default '{}'::jsonb,
  embedding vector(768),
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  tsv tsvector generated always as (to_tsvector('simple', coalesce(chunk_text, ''))) stored
);

create index if not exists idx_persona_knowledge_chunks_persona_id
  on public.persona_knowledge_chunks (persona_id);

create index if not exists idx_persona_knowledge_chunks_tsv
  on public.persona_knowledge_chunks using gin (tsv);

create index if not exists idx_persona_knowledge_chunks_embedding
  on public.persona_knowledge_chunks using ivfflat (embedding vector_cosine_ops)
  with (lists = 100);

create or replace function public.set_persona_knowledge_chunks_updated_at()
returns trigger
language plpgsql
as $$
begin
  new.updated_at = now();
  return new;
end;
$$;

drop trigger if exists trg_persona_knowledge_chunks_updated_at on public.persona_knowledge_chunks;
create trigger trg_persona_knowledge_chunks_updated_at
before update on public.persona_knowledge_chunks
for each row
execute function public.set_persona_knowledge_chunks_updated_at();

create or replace function public.hybrid_knowledge_search(
  p_query_text text,
  p_query_embedding vector(768) default null,
  p_persona_id text default null,
  p_match_count int default 4,
  p_vector_weight float8 default 0.7,
  p_keyword_weight float8 default 0.3
)
returns table (
  chunk_text text,
  source text,
  score float8,
  vector_score float8,
  keyword_score float8
)
language sql
stable
as $$
with base as (
  select
    c.chunk_text,
    c.source,
    case
      when p_query_embedding is null or c.embedding is null then 0::float8
      else greatest(0::float8, 1 - (c.embedding <=> p_query_embedding))
    end as vector_score,
    case
      when coalesce(trim(p_query_text), '') = '' then 0::float8
      else greatest(0::float8, ts_rank_cd(c.tsv, websearch_to_tsquery('simple', p_query_text)))
    end as keyword_score
  from public.persona_knowledge_chunks c
  where (p_persona_id is null or c.persona_id = p_persona_id)
), scored as (
  select
    chunk_text,
    source,
    vector_score,
    keyword_score,
    (coalesce(p_vector_weight, 0.7) * vector_score + coalesce(p_keyword_weight, 0.3) * keyword_score) as score
  from base
)
select
  s.chunk_text,
  s.source,
  s.score,
  s.vector_score,
  s.keyword_score
from scored s
order by s.score desc nulls last
limit greatest(1, least(coalesce(p_match_count, 4), 20));
$$;

comment on function public.hybrid_knowledge_search(text, vector, text, int, float8, float8)
is 'Hybrid retrieval: weighted vector + keyword ranking for persona knowledge chunks.';
