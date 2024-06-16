--
-- Table structure for table `movie_frame_trackpoints`
--

DROP TABLE IF EXISTS `movie_frame_trackpoints`;
CREATE TABLE `movie_frame_trackpoints` (
  `id` int NOT NULL AUTO_INCREMENT,
  `movie_id` int NOT NULL,
  `frame_number` int NOT NULL,
  `label` varchar(255) NOT NULL,
  `x` int NOT NULL,
  `y` int NOT NULL,
  PRIMARY KEY (`id`),
  UNIQUE KEY `uk3` (`movie_id`,`frame_number`,`label`),
  CONSTRAINT `m1` FOREIGN KEY (`movie_id`) REFERENCES `movies` (`id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_general_ci;

drop table movie_data;
drop table movie_analysis;
drop table movie_frame_analysis;
