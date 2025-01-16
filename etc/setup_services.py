#!/usr/bin/env python3

# Define the instances we are creating.

def readfile(fname):
    with open(fname,'r') as f:
        return f.read()

def writefile(fname,name,content):
    with open(fname.format(name=name), 'w') as f:
        f.write(content)

HTTPD_TEMPLATE=readfile('planttracer-template.conf')
SYSTEMD_TEMPLATE=readfile('planttracer-template.service')

HTTPD_DIR =
SYSTEMD_DIR = '/etc/systemd/system'


DEFS = """mv1,8000,no
app,8010,no
demo1,8020,no
dev-slg,8030,no"""


for def in DEFS.split('\n'):
    for (name,port,demo) in def.split(','):
        writefile('/etc/httpd/conf.d/planttracer-{name}.conf', name, content.format(name=name, port=port, demo=demo))
        writefile('/etc/systemd/system/planttracer-{name}.service', name, content.format(name=name, port=port, demo=demo))
