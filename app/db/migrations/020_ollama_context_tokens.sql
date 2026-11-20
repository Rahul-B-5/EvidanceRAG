ALTER TABLE generation_profiles
    ADD COLUMN ollama_context_tokens INTEGER
        CHECK (ollama_context_tokens IS NULL OR (
            provider = 'ollama' AND ollama_context_tokens BETWEEN 2048 AND 65536
        ));
