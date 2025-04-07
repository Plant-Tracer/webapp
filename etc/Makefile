install:
	python3 setup_services.py


fix-certs:
	sudo /opt/certbot/bin/certbot --apache
	sudo apachectl configtest
	sudo apachectl graceful

