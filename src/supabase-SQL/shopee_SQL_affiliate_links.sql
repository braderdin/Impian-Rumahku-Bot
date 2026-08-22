-- =============================================================================
-- 🛍️ JADUAL KHAS AFFILIATE SHOPEE (SEMBANG PC & TECH ECOSYSTEM)
-- =============================================================================

-- 1. Pastikan Extension pg_trgm aktif untuk carian pantas Telegram / REST API
CREATE EXTENSION IF NOT EXISTS pg_trgm;

-- 2. Cipta Jadual Khusus Shopee
CREATE TABLE IF NOT EXISTS public.shopee_affiliate_links (
    id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    shopee_product_id TEXT NOT NULL UNIQUE,
    shopee_product_name TEXT NOT NULL,
    shopee_brand TEXT DEFAULT 'Shopee Preferred',
    shopee_price NUMERIC(12, 2) DEFAULT 0.00,
    shopee_sales_count TEXT DEFAULT '0',
    shopee_commission_rate TEXT DEFAULT '0%',
    shopee_commission_amount TEXT DEFAULT 'RM 0.00',
    shopee_picture_url TEXT NOT NULL,
    shopee_product_url TEXT,
    shopee_affiliate_link TEXT NOT NULL,
    shopee_category TEXT NOT NULL DEFAULT '📦 Tawaran Gajet & Gaya Hidup',
    shopee_status_used BOOLEAN NOT NULL DEFAULT FALSE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- 3. Cipta Indeks Prestasi Tinggi (Carian Pantas & Tapisan Automasi)
CREATE INDEX IF NOT EXISTS idx_shopee_product_name_trgm 
ON public.shopee_affiliate_links USING gin (shopee_product_name gin_trgm_ops);

CREATE INDEX IF NOT EXISTS idx_shopee_status_used 
ON public.shopee_affiliate_links (shopee_status_used);

CREATE INDEX IF NOT EXISTS idx_shopee_category 
ON public.shopee_affiliate_links (shopee_category);

CREATE INDEX IF NOT EXISTS idx_shopee_brand 
ON public.shopee_affiliate_links (shopee_brand);

-- 4. Aktifkan Row Level Security (RLS) & Polisi Akses
ALTER TABLE public.shopee_affiliate_links ENABLE ROW LEVEL SECURITY;

CREATE POLICY "Allow public read access for Shopee" 
ON public.shopee_affiliate_links 
FOR SELECT 
USING (true);

CREATE POLICY "Allow service role full access for Shopee" 
ON public.shopee_affiliate_links 
FOR ALL 
USING (true);