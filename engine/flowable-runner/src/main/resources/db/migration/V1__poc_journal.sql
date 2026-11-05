CREATE TABLE poc_command (
    command_id uuid PRIMARY KEY,
    request_hash varchar(64) NOT NULL,
    receipt jsonb,
    created_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE poc_event (
    journal_id bigserial PRIMARY KEY,
    event_id uuid NOT NULL UNIQUE,
    payload jsonb NOT NULL
);
