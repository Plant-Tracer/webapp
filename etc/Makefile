# webapp/etc/Makefile
# Used for managing services on the VM server (for VM deployments)

install: setup_services.py
	@echo read configuration out of setup_services.py and install gunicorn proxies
	sudo python3 setup_services.py


fix-certs:
	sudo /opt/certbot/bin/certbot --nginx
	sudo nginx -t
	sudo systemctl restart nginx

.PHONY: install fix-certs
