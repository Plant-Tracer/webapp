ALTER TABLE `movies`ADD COLUMN IF NOT EXISTS status VARCHAR(250);
UPDATE metadata set v=2 where k='version';
