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

# name,port,demovar,demoval,base
DEFS = """app,8010,DEMO,OFF,/home/ubuntu/webapp
demo,8020,DEMO_COURSE_ID,demo,/home/ubuntu/webapp
dev,8030,DEMO,OFF,/home/ubuntu/dev
dev-slg,8040,DEMO,OFF,/home/ubuntu/dev-slg
dev-seb,8050,DEMO,OFF,/home/ubuntu/dev-seb
"""


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
