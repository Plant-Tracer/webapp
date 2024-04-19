ALTER TABLE `movies` ADD COLUMN `movie_data_urn` VARCHAR(1024);
ALTER TABLE `movies` ADD KEY (movie_data_urn (768));
UPDATE metadata set v=8 where k='schema_version';
