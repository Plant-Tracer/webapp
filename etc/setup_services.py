#!/usr/bin/env python3

import os

# Define the instances we are creating.
# name,port,demovar,demoval,base
DEFS = """
app,8010,DEMO,OFF,/home/ubuntu/webapp
demo,8020,DEMO_COURSE_ID,demo,/home/ubuntu/webapp
dev,8030,DEMO,OFF,/home/ubuntu/dev
dev-slg,8040,DEMO,OFF,/home/ubuntu/dev-slg
dev-seb,8050,DEMO,OFF,/home/ubuntu/dev-seb"""

def readfile(fname):
    with open(fname,'r') as f:
        return f.read()

def writefile(fname,name,content):
    path = fname.format(name=name)
    print("Creating",path)
    with open(path, 'w') as f:
        f.write(content)


if __name__=="__main__":
    NGINX_TEMPLATE=readfile('planttracer-nginx-template.conf')
    SERVICE_TEMPLATE=readfile('planttracer-template.service')

    for d in DEFS.strip().split('\n'):
        try:
            (name,port,demovar,demoval,base) = d.split(',')
        except ValueError:
            print(f"Error in d='{d}'\n")
            continue

        # "{" is significant in ngnix templates.
        # Right now we are doing this the ugly way
        temp = NGINX_TEMPLATE
        temp=temp.replace("{name}",name)
        temp=temp.replace("{port}",port)
        temp=temp.replace("{demovar}",demovar)
        temp=temp.replace("{demoval}",demoval)
        temp=temp.replace("{base}",base)

        writefile('/etc/nginx/sites-available/{name}.planttracer.com', name, temp)

        writefile('/etc/systemd/system/planttracer-{name}.service', name,
                  SERVICE_TEMPLATE.format(name=name, port=port, demovar=demovar, demoval=demoval,base=base))
        symlink_path   = f"/etc/nginx/sites-enabled/{name}.planttracer.com"
        symlink_target = f"../sites-available/{name}.planttracer.com"
        if not os.path.exists(symlink_path):
            os.symlink(symlink_target, symlink_path)

    # Always reload the daemons when the service files are modified
    os.system("sudo systemctl daemon-reload")

    for d in DEFS.strip().split('\n'):
        (name,port,demovar,demoval,base) = d.split(',')
        service = f'planttracer-{name}'
        os.system(f"sudo systemctl enable {service}")
        os.system(f"sudo systemctl start {service}")
        os.system(f"sudo systemctl restart {service}")
