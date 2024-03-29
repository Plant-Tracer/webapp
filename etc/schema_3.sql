ALTER TABLE `movie_data` CHANGE COLUMN movie_data movie_data mediumblob DEFAULT NULL;
ALTER TABLE `objects` RENAME COLUMN url TO urn;
UPDATE metadata set v=3 where k='schema_version';
