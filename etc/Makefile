force:
	touch Makefile
	make schema.sql

known_hosts:
	ssh-keyscan downloads.digitalcorpora.org > known_hosts

DATABASE := $(shell grep database= credentials-localhost.ini | head -1 | sed s/database=//)
schema.sql:
	grep -v 'database=' credentials-localhost.ini > credentials-db.ini
	mysqldump --defaults-file=credentials-db.ini         \
            -d --single-transaction --no-tablespaces $(DATABASE) \
	    | sed 's/ AUTO_INCREMENT=[0-9]*//g' \
	    | sed 's/CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci //g' \
	    | sed 's/COLLATE utf8mb4_general_ci //g' \
	    | grep -v 'character_set_client' \
	    | grep -v 'Dump completed on' > schema.sql
	/bin/rm -f credentials-db.ini
	touch Makefile		# so we can repeat!
	git diff schema.sql

database-dump.sql: Makefile ../Makefile
	(source $$HOME/plant_dev.bash;mysqldump -h$$MYSQL_HOST -u$$MYSQL_USER -p$$MYSQL_PASSWORD --single-transaction --no-tablespaces $$MYSQL_DATABASE) > database-dump.sql
	touch Makefile		# so we can repeat!

output-ssh_priv_key:
	@echo here is the base64 encoded private key, for pasting into the GitHub secrets section
	cat $$HOME/.ssh/id_ed25519 | openssl base64 -e

check:


reset-db: check
	@echo -n "Are you sure? [y/N] " && read ans && [ $${ans:-N} = y ]
	@echo REALLY WIPING DATABASE with credentials.ini
	cat credentials.ini
	@echo -n "Are you sure? [y/N] " && read ans && [ $${ans:-N} = y ]
	make clean
	mysql --defaults-extra-file=credentials.ini < schema.sql

.PHONY: schema.sql schema-local.sql database-dump.sql
