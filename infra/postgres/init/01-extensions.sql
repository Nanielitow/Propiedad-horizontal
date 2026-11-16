-- Se ejecuta solo la primera vez que se crea el volumen pg_data.
-- La migración inicial de Alembic repite estos CREATE EXTENSION IF NOT EXISTS
-- para que producción (Supabase/RDS/Neon) no dependa de este script.
CREATE EXTENSION IF NOT EXISTS vector;
CREATE EXTENSION IF NOT EXISTS unaccent;
CREATE EXTENSION IF NOT EXISTS citext;
