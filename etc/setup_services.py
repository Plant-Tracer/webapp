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
DEFS = """mv1,8000,no,/home/ec2-user/webapp
app,8010,no,/home/ec2-user/webapp
demo1,8020,no,/home/ec2-user/webapp
dev-slg,8030,no,/home/ec2-user/dev-slg"""


for d in DEFS.split('\n'):
    print("d=",d)
    (name,port,demo,base) = d.split(',')
    writefile('/etc/httpd/conf.d/planttracer-{name}.conf', name,
              HTTPD_TEMPLATE.format(name=name, port=port, demo=demo,base=base))
    writefile('/etc/systemd/system/planttracer-{name}.service', name,
              SYSTEMD_TEMPLATE.format(name=name, port=port, demo=demo,base=base))

os.system("sudo systemctl daemon-reload")
