-- Rulează acest cod în Supabase > SQL Editor > New Query

CREATE TABLE IF NOT EXISTS contracte (
    id              BIGSERIAL PRIMARY KEY,
    id_anunt        TEXT UNIQUE,          -- evită duplicate
    firma           TEXT,
    cui             TEXT,
    valoare         NUMERIC,
    obiect          TEXT,
    autoritate      TEXT,
    data_atribuirii DATE,
    cpv             TEXT,
    created_at      TIMESTAMPTZ DEFAULT NOW()
);

-- Index pentru căutare rapidă după dată
CREATE INDEX IF NOT EXISTS idx_data ON contracte(data_atribuirii);

-- Permite citire publică (necesară pentru Streamlit)
ALTER TABLE contracte ENABLE ROW LEVEL SECURITY;

CREATE POLICY "Citire publica" ON contracte
    FOR SELECT USING (true);

CREATE POLICY "Scriere din service" ON contracte
    FOR INSERT WITH CHECK (true);
