How To Use ECN-Spider
*********************
In this section I illustrates a typical use case for ECN-Spider. I will highlight how the various scripts that make up ECN-Spider work together.

Getting The Input Ready
-----------------------
First, I obtain a CSV data file with a list of domain names and traffic rank information that I would like to test. To use Alexa's list of the top 1 million domains, I did this::

    ecn$ wget http://s3.amazonaws.com/alexa-static/top-1m.csv.zip
    ecn$ unzip ./top-1m.csv.zip

The list has the following format::

    1,google.com
    2,facebook.com
    3,youtube.com
    4,yahoo.com
    5,baidu.com
    6,wikipedia.org
    7,qq.com
    8,twitter.com
    9,linkedin.com
    10,taobao.com

A records consists of a rank and a domain name. The rank is only used for the analysis at the very end, and is stored together with the domain name through the processing in all scripts.

For most tests, I choose not to use the entire domain name list. Using the script ``new_subset.py``, I can extract a shorter list of two parts: the first ``n`` unique domains, and ``m`` randomly selected unique domains from the remainder.::

    ecn$ python ./new_subset.py 50000 50000 ./top-1m.csv ./subset.csv

Note that this script should always be used (even when using the complete input list and not a subset), since this script not only does subset selection: it also does some clean-up and other minor manipulation of the list. If this script is not used, the analysis at the end may produce incorrect results.

The main testing script ``ecn_spider.py`` expects an input file with domain names *and* IP addresses they resolve to. The script ``resolution.py`` takes an input file and runs address resolution on the domain names therein::

    ecn$ python ./resolution.py --workers 10 --www preferred ./subset.csv ./resolved.csv

With input files like Alexa's top 1M list, ``resolved.csv`` will now contain many duplicate IP addresses, due to many popular websites being hosted on CDNs that share an IP address between multiple sites. The script ``unique.py`` ensures that both the IPv4 and IPv6 addresses of the resolved domain names are unique. Non-unique IP addresses may lead to erroneous results in the analysis. ::

    ecn$ python ./unique.py ./resolved.csv ./input.csv

The list now has the following format::

    1,www.google.com,173.194.40.52,2a00:1450:400a:804::1013
    2,www.facebook.com,31.13.91.2,2a03:2880:f01b:1:face:b00c:0:1
    3,www.youtube.com,173.194.40.32,2a00:1450:400a:804::1002
    4,www.yahoo.com,46.228.47.115,2a00:1288:f006:1fe::3001
    5,www.baidu.com,180.76.3.151,
    6,www.wikipedia.org,91.198.174.192,2620:0:862:ed1a::1
    7,www.qq.com,80.239.148.10,
    8,www.twitter.com,199.16.156.38,
    9,www.linkedin.com,108.174.2.129,
    10,www.taobao.com,195.27.31.241,

Note that in this particular example, the option ``--www preferred`` for the resolution script has led to most domains in ``input.csv`` to now have a prepended ``www.``.

Running The Test
----------------
Now that the input file has been prepared, I can run ``ecn_spider``. Before I start ECN-Spider, I run ``tcpdump`` as root in a separate shell, to capture all TCP packet headers for later analysis::

    root$ tcpdump -ni eth0 -w ./ecn_spider.pcap -s 128

And now::

    ecn$ python ./ecn_spider.py --verbosity INFO --workers 64 --timeout 4 ./input.csv ./retry.csv ./ecn-spider.csv ./ecn-spider.log

This run creates three output files:
    ``retry.csv``:
        This file is used as the input file for later runs of ``ecn_spider`` and contains only the IP addresses that had problems during this test run.
    
    ``ecn-spider.csv``:
        This file contains the collected test data used for further analysis.
    
    ``ecn-spider.log``:
        This file contains human-readable log data useful for debugging. It is not needed for normal use of the tools of ECN-Spider.

Benchmarking the ``--workers`` parameter
------------------------------------------
The rate at which ECN-Spider tests domains varies greatly with the number of worker threads used for testing. This number can be adjusted with the command line option ``--workers``. Of course, the rate also depends on the the round-trip time to the tested domains and the value of the ``--timeout`` option.

To find the optimal number of workers, the script ``simple_bench.sh`` can be used.
