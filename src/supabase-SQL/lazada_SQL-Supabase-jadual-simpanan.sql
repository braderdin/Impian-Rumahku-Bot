-- 1. Bina jadual affiliate_links (sepadan 100% dengan src/supabase_db.py)
create table affiliate_links (
    id uuid default gen_random_uuid() primary key,
    product_id text unique not null,
    title text,
    category text,
    keyword text,
    original_url text,
    affiliate_link text not null,
    image_url text,
    b2_image_url text,
    price numeric(10, 2),
    commission_rate text default '>=2.5%',
    status_used boolean default false,
    created_at timestamp with time zone default now(),
    updated_at timestamp with time zone default now()
);

-- 2. Aktifkan Row Level Security (RLS) untuk piawaian keselamatan Supabase
alter table affiliate_links enable row level security;

-- 3. Cipta polisi akses penuh untuk Service Role / Anon Key
create policy "Allow full access for backend script" 
on affiliate_links 
for all 
using (true) 
with check (true);