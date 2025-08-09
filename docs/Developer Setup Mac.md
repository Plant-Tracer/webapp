# Developer Setup Mac
This tutorial takes a new macOS install and gets you to running PlantTracer locally and on Amazon.

# Initial mac Configuration
1. Install developer tools.
 
From a clean install, open the Terminal window and type `make`. You should get an error message:
<img width="949" height="455" alt="image" src="https://github.com/user-attachments/assets/a51cd276-7eae-4de8-8ba7-cea15ebe3bb6" />

* After a few moments, you'll see this window. Click **Install**:
<img width="573" height="307" alt="image" src="https://github.com/user-attachments/assets/21294734-0324-4b83-9a4a-1c4185dfa7aa" />

Agree to the license agreement.

2. Install `brew` from https://brew.sh/

```
/bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)"
```
   
<img width="1110" height="553" alt="image" src="https://github.com/user-attachments/assets/53738f7e-3168-4041-a211-f6d1058ae0bd" />

(You will need to enter your password and type **RETURN/ENTER**.)

2. Download the git repo.

```
% git clone --recursive https://github.com/Plant-Tracer/webapp.git
Cloning into 'webapp'...
remote: Enumerating objects: 10477, done.
remote: Counting objects: 100% (1404/1404), done.
remote: Compressing objects: 100% (577/577), done.
remote: Total 10477 (delta 866), reused 827 (delta 827), pack-reused 9073 (from 3)
Receiving objects: 100% (10477/10477), 106.38 MiB | 48.78 MiB/s, done.
Resolving deltas: 100% (7355/7355), done.
% 
```

3. Use the macOS installer built into the Makefile:
```
% cd Makefile
% make install-macos
```

4. 

