DROP TABLE IF EXISTS `object_store`;
CREATE TABLE `object_store` (
  `id` int NOT NULL AUTO_INCREMENT,
  `sha256` varchar(64) NOT NULL,
  `data` longblob NOT NULL,
  PRIMARY KEY (`id`),
  UNIQUE KEY `sha256` (`sha256`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_general_ci;
UPDATE metadata set v=5 where k='schema_version';
