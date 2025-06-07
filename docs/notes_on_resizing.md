```
LD50-P [ec2-user@mv1 ~]$ df -h
Filesystem      Size  Used Avail Use% Mounted on
devtmpfs        4.0M     0  4.0M   0% /dev
tmpfs           2.0G     0  2.0G   0% /dev/shm
tmpfs           781M  496K  781M   1% /run
/dev/xvda1       30G  8.5G   22G  29% /
tmpfs           2.0G     0  2.0G   0% /tmp
/dev/xvda128     10M  1.3M  8.7M  13% /boot/efi
tmpfs           391M     0  391M   0% /run/user/1000
```
AWS allows creating a volume snapshot and an instance snapshot.
Current public IP address: 52.91.3.27
Current instance iD: i-0a667096741d5dd53
Current AMI: al2023-ami-2023.6.20250107.0-kernel-6.1-x86_64
Owner: 343218180669

Instructions to create an AMI from a running instance:
https://docs.aws.amazon.com/AWSEC2/latest/UserGuide/creating-an-ami-ebs.html
https://serverfault.com/questions/578360/creating-an-ec2-ami-image-from-a-running-instance-vs-from-a-volume-snapshot

created snap1 from the volume. Volume size: 30gb  (this was more than we needed; we have 22G free.)
snap: snap-01d38e33f57f1b0d2
vol: vol-08d3a6bb9872b3d1d