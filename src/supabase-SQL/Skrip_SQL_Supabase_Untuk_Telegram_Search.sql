-- 1. Aktifkan Extension pg_trgm untuk carian teks pantas & tepat (Fuzzy / Short Keyword Matching)
CREATE EXTENSION IF NOT EXISTS pg_trgm;

-- 2. Bina Jadual Produk Affiliate Universal
CREATE TABLE IF NOT EXISTS public.affiliate_links (
    id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    product_id TEXT NOT NULL UNIQUE,
    sku_id TEXT,
    title TEXT NOT NULL,
    brand TEXT DEFAULT 'No Brand',
    sale_price NUMERIC(12, 2) DEFAULT 0.00,
    discounted_price NUMERIC(12, 2) DEFAULT 0.00,
    discount_percentage TEXT DEFAULT '-0%',
    image_url TEXT NOT NULL,
    affiliate_link TEXT NOT NULL,
    category TEXT NOT NULL DEFAULT '📦 Tawaran Gajet & Gaya Hidup',
    status_used BOOLEAN NOT NULL DEFAULT FALSE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- 3. Bina Indeks Prestasi Tinggi untuk Carian Pantas di Telegram
CREATE INDEX IF NOT EXISTS idx_affiliate_links_title_trgm ON public.affiliate_links USING gin (title gin_trgm_ops);
CREATE INDEX IF NOT EXISTS idx_affiliate_links_category ON public.affiliate_links(category);
CREATE INDEX IF NOT EXISTS idx_affiliate_links_status ON public.affiliate_links(status_used);

-- 4. Buka Akses Bacaan Awam (RLS Policy)
ALTER TABLE public.affiliate_links ENABLE ROW LEVEL SECURITY;

CREATE POLICY "Allow public read access" 
ON public.affiliate_links 
FOR SELECT 
USING (true);

CREATE POLICY "Allow service role full access" 
ON public.affiliate_links 
FOR ALL 
USING (true);