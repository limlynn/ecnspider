Setting up ECN-Spider on a Machine
**********************************
This section will give an overview over compiling the current Python version from source, and setting up an unpriviledged account with exactly the right permissions to modify the Kernel's ECN-related behavior (which normally only ``root`` can do).

The following instructions have been tested on Ubuntu 14.04 LTS. Ubuntu 14.04 ships with Python 3.4 by default, but for demonstration purposes Python 3.4 is compiled from source here.

Setting up a User Account
-------------------------
To run ECN-Spider, I create a separate user account. ::

    root$ adduser ecn --disabled-password

Since I am only accessing this account by ``su``, I will not allow password logins.

To give the user ``ecn`` the privileges to change the ECN behavior, the configuration file for ``sudo`` has to be adjusted. The configuration file is edited with the ``visudo`` program::

    root$ visudo

The following listing shows the complete configuration file (with some comments removed) after editing::

    Defaults        env_reset
    Defaults        mail_badpass
    Defaults        secure_path="/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin"

    # User privilege specification
    root    ALL=(ALL:ALL) ALL
    ecn ALL=NOPASSWD: /sbin/sysctl -w net.ipv4.tcp_ecn=[0-2]

    # Members of the admin group may gain root privileges
    %admin ALL=(ALL) ALL

    # Allow members of group sudo to execute any command
    %sudo   ALL=(ALL:ALL) ALL

The line starting with ``ecn``... was added to the existing configuration. Now, the user ``ecn`` can change the necessary settings::

    root$ su - ecn
    ecn$ /sbin/sysctl net.ipv4.tcp_ecn
    net.ipv4.tcp_ecn = 2
    ecn$ sudo /sbin/sysctl -w net.ipv4.tcp_ecn=0
    net.ipv4.tcp_ecn = 0

Note that changing this setting using sysctl affects all TCP connections created with the Kernel's network stack.

Setting up Python
-----------------
ECN-Spider requires Python 3.4. Since this version is not yet packaged for many Linux distributions, I compile it from source. Compiling Python from source also provides the appropriate versions of the ``virtualenv`` and ``pip`` utilities. The latter is required to install ECN-Spider's dependencies.

First, I download Python's source code and unpack it::

    ecn$ wget https://www.python.org/ftp/python/3.4.1/Python-3.4.1.tar.xz
    ecn$ tar xf Python-3.4.1.tar.xz

Some of Python's optional dependencies should be installed::

    root$ apt-get install build-essential libbz2-dev libsqlite3-dev libreadline-dev zlib1g-dev libncurses5-dev libssl-dev libgdbm-dev liblzma-dev tk-dev

Now, Python can be compiled::

    ecn$ ./configure --prefix=/home/ecn/bin/Python-3.4.1
    ecn$ make
    ecn$ make test
    ecn$ make install

Setting up the Environment for ECN-Spider
-----------------------------------------
I use a virtual environment for running ECN-Spider in. It is set up as follows::

    ecn$ bin/Python-3.4.1/bin/pyvenv ~/ecnsenv
    ecn$ source ecnsenv/bin/activate
    (ecnsenv) ecn$ python --version
    Python 3.4.1

ECN-Spider has a few dependencies that need to be installed as well. This can be done using the Python package manager ``pip``::

    (ecnsenv) ecn$ pip install psutil dnspython3

Note that ``dnspython`` is not the same thing as ``dnspython3``.
