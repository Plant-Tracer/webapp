known_hosts:
	ssh-keyscan downloads.digitalcorpora.org > known_hosts

schema.sql: Makefile
	(source $$HOME/plant_dev.bash;mysqldump -h$$MYSQL_HOST -u$$MYSQL_USER -p$$MYSQL_PASSWORD -d --no-tablespaces $$MYSQL_DATABASE) > schema.sql
