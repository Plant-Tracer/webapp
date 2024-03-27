ALTER TABLE `objects` ADD UNIQUE KEY (sha256);
ALTER TABLE `objects` ADD KEY (mtime);
ALTER TABLE `objects` ADD KEY (urn (768));
ALTER TABLE `objects` DROP COLUMN data;
UPDATE metadata set v=4 where k='schema_version';
