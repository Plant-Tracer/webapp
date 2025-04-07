#!/usr/bin/env python3

import os

# Define the instances we are creating.

def readfile(fname):
    with open(fname,'r') as f:
        return f.read()

def writefile(fname,name,content):
    with open(fname.format(name=name), 'w') as f:
        f.write(content)

HTTPD_TEMPLATE=readfile('planttracer-template.conf')
SYSTEMD_TEMPLATE=readfile('planttracer-template.service')

# name,port,demo,base
DEFS = """app,8010,NO,/home/ec2-user/webapp
demo,8020,yes,/home/ec2-user/webapp
dev2,8030,NO,/home/ec2-user/dev2
dev-slg,8040,NO,/home/ec2-user/dev-slg"""


for d in DEFS.split('\n'):
    print("d=",d)
    (name,port,demo,base) = d.split(',')
    writefile('/etc/httpd/conf.d/planttracer-{name}.conf', name,
              HTTPD_TEMPLATE.format(name=name, port=port, demo=demo,base=base))
    writefile('/etc/systemd/system/planttracer-{name}.service', name,
              SYSTEMD_TEMPLATE.format(name=name, port=port, demo=demo,base=base))

os.system("sudo systemctl daemon-reload")

for d in DEFS.split('\n'):
    (name,port,demo,base) = d.split(',')
    service = f'planttracer-{name}'
    os.system(f"sudo systemctl enable {service}")
    os.system(f"sudo systemctl start {service}")
    os.system(f"sudo systemctl restart {service}")
