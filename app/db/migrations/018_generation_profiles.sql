CREATE TABLE generation_profiles (
    purpose TEXT PRIMARY KEY CHECK (purpose IN ('answer', 'extraction')),
    provider TEXT NOT NULL CHECK (provider IN ('ollama','openai','anthropic','gemini','openai-compatible')),
    model TEXT NOT NULL CHECK (char_length(model) BETWEEN 1 AND 160),
    endpoint TEXT NOT NULL DEFAULT '',
    credential BYTEA,
    revision INTEGER NOT NULL DEFAULT 1 CHECK (revision > 0)
);
