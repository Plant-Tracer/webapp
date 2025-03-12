Windows Developer Setup Notes
=============================

This note contains additional steps and departures from :doc: `DeveloperSetup` (which was written with Linux and MacOS in mind). Read that document first, then look here for guidance on a Windows machine.

These notes were written using Windows 11 24H2 (OS Build 26100.2984) for ARM actually running on the UMT Virtualization platform running on MacOS Sequoia 15.3, in case it is helpful to know that. These steps assume an otherwise fresh Windows 11 installation. The VM has 8GB RAM, 2 CPUs, and 64GB disk. 

There are probably many other paths to getting a working development environment -- these are just one way that is known to have worked.

It just might be that getting Plant-Tracer/webapp to run on Windows is more trouble than it is worth. Windows is not a targeted runtime environment, and there are a few platform dependencies. Other possibilities for a dev and local test environment include finding a Linux machine to use, real or virtual (Ubuntu is what we build and test with) or Amazon Linux on AWS EC2.

* Download and install Google Chrome

* Run Terminal (This is a PowerShell by default, make sure it has Administrator privileges.)

* Install the Chocolatey package manager. Follow the directions at, for example, `<https://chocolatey.org/install#individual>`

* choco install python311

   * On the ARM Mac host, this required the Visual C++ 2022 Arm64 Runtime via `<https://learn.microsoft.com/en-us/cpp/windows/latest-supported-vc-redist?view=msvc-170>`. This involved seeing some scary error messages, ignoring them, and rebooting the Windows VM a couple times.

* choco install make

* choco install git

* choco install gh

* choco install mysql --version=8.0.41
    * Lots of red XML appeared but choco said it succeeded? Some notes I've read said that's OK

    * That said, mysql does not appear to be supported on Windows ARM. So, at this point, I am not proceeding down this path any further. With no MySQL client on Windows ARM, there's no reasonable way to proceed further down this path.

    * I've also choco uninstall mysql which claims to have succeeded, yet the mysql executable still exists. Buggy for sure.

