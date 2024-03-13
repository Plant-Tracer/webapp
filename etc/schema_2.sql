ALTER TABLE `movies` ADD COLUMN status VARCHAR(250);
UPDATE metadata set v=2 where k='schema_version';
