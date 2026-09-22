-- +goose Up
-- Keep the original text identifiers: deployed demo identifiers are stable
-- catalog identities.  Slugs are a separate, mutable lookup key from now on.
ALTER TABLE demo_catalog RENAME TO catalog_items;
ALTER TABLE catalog_items ADD COLUMN slug TEXT;
UPDATE catalog_items SET slug = id WHERE slug IS NULL;
ALTER TABLE catalog_items ALTER COLUMN slug SET NOT NULL;
ALTER TABLE catalog_items ADD CONSTRAINT catalog_items_slug_key UNIQUE (slug);

ALTER TABLE catalog_aliases DROP CONSTRAINT catalog_aliases_canonical_slug_fkey;
ALTER TABLE catalog_aliases
  ADD CONSTRAINT catalog_aliases_canonical_slug_fkey
  FOREIGN KEY (canonical_slug) REFERENCES catalog_items(slug);

-- A short-lived compatibility surface keeps older diagnostic queries and the
-- seed script usable.  Application queries use catalog_items exclusively.
CREATE VIEW demo_catalog AS SELECT * FROM catalog_items;

-- +goose Down
SELECT 1;
