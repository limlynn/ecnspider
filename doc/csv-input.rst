CSV Input File Format
*********************
ECN-Spider's CSV input file contains domain names and IP addresses to which connection attempts are made.

Each record in the file has the following format::

    name,ipv4,ipv6

The fields have the following meanings:
    ``name``:
        A domain name. This will be used as is as the value of the ``HOST`` header field in HTTP requests. This field must not be empty.
    
    ``ipv4``:
        The IPv4 address that is a DNS A record of ``name``. This field may be empty.
    
    ``ipv6``:
        The IPv6 address that is a DNS AAAA record of ``name``. This field may be empty.

This is a sample input file snippet::

www.mail.ru,94.100.180.70,
www.ask.com,184.29.106.11,
www.google.it,173.194.43.31,2607:f8b0:4006:802::1018
www.tmall.com,220.181.113.241,
www.sina.com.cn,58.63.236.31,
www.google.fr,173.194.43.23,2607:f8b0:4006:802::1017
    www.example.com,,
