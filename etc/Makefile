force:
	touch Makefile
	make schema.sql

known_hosts:
	ssh-keyscan downloads.digitalcorpora.org > known_hosts

schema.sql: Makefile ../Makefile
	mysqldump --defaults-extra-file=$$HOME/plant_dev.ini -d --single-transaction --no-tablespaces planttracer_dev | sed 's/ AUTO_INCREMENT=[0-9]*//g' | grep -v 'Dump completed on' > schema.sql
	touch Makefile		# so we can repeat!
	git diff schema.sql

schema-local.sql: Makefile ../Makefile
	mysqldump --defaults-extra-file=credentials-local.ini -d --single-transaction --no-tablespaces planttracer_local | sed 's/ AUTO_INCREMENT=[0-9]*//g' | grep -v 'Dump completed on' > schema-local.sql

database-dump.sql: Makefile ../Makefile
	(source $$HOME/plant_dev.bash;mysqldump -h$$MYSQL_HOST -u$$MYSQL_USER -p$$MYSQL_PASSWORD --single-transaction --no-tablespaces $$MYSQL_DATABASE) > database-dump.sql
	touch Makefile		# so we can repeat!

output-ssh_priv_key:
	@echo here is the base64 encoded private key, for pasting into the GitHub secrets section
	cat $$HOME/.ssh/id_ed25519 | openssl base64 -e

switch-dreamhost:
	/bin/rm -f credentials.ini
	ln -s credentials-dreamhost.ini credentials.ini
	ls -l *.ini

switch-local:
	/bin/rm -f credentials.ini
	ln -s credentials-local.ini credentials.ini
	ls -l *.ini
