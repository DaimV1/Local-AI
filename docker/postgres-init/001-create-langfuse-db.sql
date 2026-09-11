-- Langfuse gets its own database on the same Postgres instance so Phase 1
-- doesn't need a second database container.
CREATE DATABASE langfuse;
