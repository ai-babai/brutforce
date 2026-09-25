-- +goose Up
CREATE TABLE demo_catalog (
    id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    winery TEXT NOT NULL,
    year INTEGER NOT NULL CHECK (year > 0),
    image TEXT NOT NULL,
    description TEXT NOT NULL,
    display_order SMALLINT NOT NULL UNIQUE
);

-- +goose Down
DROP TABLE demo_catalog;
