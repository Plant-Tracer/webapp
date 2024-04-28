ALTER TABLE `objects` DROP INDEX sha256;
ALTER TABLE `objects` ADD KEY (sha256);
ALTER TABLE `objects` DROP INDEX urn;
ALTER TABLE `objects` ADD UNIQUE KEY (urn(768));
UPDATE metadata set v=9 where k='schema_version';
