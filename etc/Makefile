known_hosts:
	ssh-keyscan downloads.digitalcorpora.org > known_hosts

schema.sql: Makefile
	(source $$HOME/plant_dev.bash;mysqldump -h$$MYSQL_HOST -u$$MYSQL_USER -p$$MYSQL_PASSWORD -d --no-tablespaces $$MYSQL_DATABASE) > schema.sql

ssh_priv_key:
	@echo here is the base64 encoded private key, for pasting into the GitHub secrets section
	cat $$HOME/.ssh/id_ed25519 | openssl base64 -e
