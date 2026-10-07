-- Raw-SQL migration applied after the Prisma-generated init migration.
-- Requires: database created with LC_CTYPE = C.UTF-8 (or ICU), pg_trgm, vector.

-- Guard: pg_trgm must see Arabic letters (fails silently with LC_CTYPE=C).
DO $$ BEGIN
  IF show_trgm('عربي') = '{}' THEN
    RAISE EXCEPTION 'pg_trgm returns no trigrams for Arabic: recreate the database with LC_CTYPE=C.UTF-8 or ICU';
  END IF;
END $$;

-- Exactly one live correct option per question.
CREATE UNIQUE INDEX IF NOT EXISTS answer_one_correct
  ON "AnswerOption"("questionId") WHERE "isCorrect" AND "retiredAt" IS NULL;

-- One open placement attempt per user.
CREATE UNIQUE INDEX IF NOT EXISTS one_open_placement
  ON "ExamAttempt"("userId") WHERE kind = 'PLACEMENT' AND status IN ('IN_PROGRESS','PAUSED');

-- One live job per (file, stage).
CREATE UNIQUE INDEX IF NOT EXISTS one_live_job
  ON "IngestionJob"("fileId", stage) WHERE status IN ('QUEUED','RUNNING');

-- Publish gate: a published question needs a reference unless its key comes
-- from a usable source file or was keyed by its (team) author.
ALTER TABLE "Question" DROP CONSTRAINT IF EXISTS published_needs_reference;
ALTER TABLE "Question" ADD CONSTRAINT published_needs_reference CHECK (
  status <> 'PUBLISHED'
  OR "answerBasis" IN ('IN_SOURCE_FILE','EDITOR_KEYED')
  OR "answerRefSourceId" IS NOT NULL);

-- Scorable items must have a strong key.
ALTER TABLE "Question" DROP CONSTRAINT IF EXISTS scorable_needs_strong_key;
ALTER TABLE "Question" ADD CONSTRAINT scorable_needs_strong_key CHECK (
  NOT scorable OR "answerConfidence" IN ('VERIFIED','CONSENSUS'));

-- AI-generated questions must carry provenance.
ALTER TABLE "Question" DROP CONSTRAINT IF EXISTS ai_needs_provenance;
ALTER TABLE "Question" ADD CONSTRAINT ai_needs_provenance CHECK (
  origin <> 'AI_GENERATED'
  OR ("generatorModel" IS NOT NULL AND "promptVersion" IS NOT NULL AND "generatedAt" IS NOT NULL));

-- ---------------------------------------------------------------------
-- Search indexes live in schema `search`, which Prisma does not manage.
-- (Tested: raw HNSW/tsvector indexes on Prisma-managed tables are reported as
-- drift and would be dropped by the next `prisma migrate dev`.)
-- Rows are written by the app/worker whenever the source row's *Norm text or
-- embedding changes; FKs cascade so deleting content cleans its index rows.
-- Vector dimension follows the embedding model (1024 = BGE-M3).
-- ---------------------------------------------------------------------
CREATE SCHEMA IF NOT EXISTS search;

CREATE TABLE IF NOT EXISTS search.question_index (
  question_id text PRIMARY KEY REFERENCES public."Question"(id) ON DELETE CASCADE,
  key_text    text NOT NULL,                       -- normalized key (+ synonyms, light prefix stripping)
  tsv         tsvector GENERATED ALWAYS AS (to_tsvector('simple', key_text)) STORED,
  embedding   vector(1024),
  model       text,                                -- embedding model id
  updated_at  timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS question_index_tsv  ON search.question_index USING gin (tsv);
CREATE INDEX IF NOT EXISTS question_index_trgm ON search.question_index USING gin (key_text gin_trgm_ops);
CREATE INDEX IF NOT EXISTS question_index_vec  ON search.question_index USING hnsw (embedding vector_cosine_ops);

CREATE TABLE IF NOT EXISTS search.chunk_index (
  chunk_id    text PRIMARY KEY REFERENCES public."ContentChunk"(id) ON DELETE CASCADE,
  key_text    text NOT NULL,
  tsv         tsvector GENERATED ALWAYS AS (to_tsvector('simple', key_text)) STORED,
  embedding   vector(1024),
  model       text,
  updated_at  timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS chunk_index_tsv ON search.chunk_index USING gin (tsv);
CREATE INDEX IF NOT EXISTS chunk_index_vec ON search.chunk_index USING hnsw (embedding vector_cosine_ops);

CREATE TABLE IF NOT EXISTS search.extracted_index (
  extracted_id text PRIMARY KEY REFERENCES public."ExtractedQuestion"(id) ON DELETE CASCADE,
  embedding    vector(1024),
  model        text,
  updated_at   timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS extracted_index_vec ON search.extracted_index USING hnsw (embedding vector_cosine_ops);
