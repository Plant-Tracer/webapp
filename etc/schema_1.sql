CREATE TABLE IF NOT EXISTS `metadata` (
  `id` int(11) NOT NULL auto_increment,
  `k` varchar(250) NOT NULL default '',
  `v` varchar(250) NOT NULL default '',
  PRIMARY KEY (`id`),
  UNIQUE KEY `uc1` (`k`)
);

INSERT INTO metadata (k,v) values ('version',1) ON DUPLICATE KEY UPDATE id=id;
