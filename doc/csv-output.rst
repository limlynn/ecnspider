CSV Output File Format
**********************
ECN-Spider's CSV output file contains information on all the TCP connections and the HTTP traffic it generates. The file format is designed with ease of parsing in mind, and not optimized for minimal file size.

Each record in the file has the following format::

    time,ip,domain,ecn_mode,record_type,data

The fields have the following meanings:
    ``time``:
        A timestamp of when the log record was created. In seconds since Unix epoch.
    
    ``ip``:
        The IP address of the web server connected to.
    
    ``domain``:
        The URL of the web server connected to.
    
    ``ecn_mode``:
        ``on`` if this TCP connection uses ECN, ``off`` otherwise.
    
    ``record_type``:
        What event this log message represents. This also defines the meaning of the ``data`` field.
        
        This field has one of the following values:
            ``PRE_CONN``:
                Immediately before the opening of a TCP connection.
            
            ``POST_CONN``:
                Immediately after opening a TCP connection.
            
            ``PRE_REQ``:
                Immediately before making an HTTP request.
            
            ``POST_REQ``:
                Immediately after having parsed the response to an HTTP request.
            
            ``REQ_HDR``:
                The headers of an HTTP response.
    
    ``data``:
        Additional data. The meaning of this field depends on the ``record_type`` and is defined as follows:
            ``PRE_CONN`` (Nothing):
                Always ``None``.
            
            ``POST_CONN`` (Port):
                The local port of the open TCP connection. 0 if the connection could not be established.
            
            ``PRE_REQ`` (is_dummy):
                ``True``, if no actual request will be made (because the connection could not be established), ``False`` otherwise.
            
            ``POST_REQ`` (Status Code):
                The status code of the HTTP response. 0 if no response was made, 418 if the request failed, or the response could not be parsed.
            
            ``REQ_HDR`` (Headers):
                The headers of an HTTP response.

Each test of a single domain by ECN-Spider generates exactly the following pattern of records in the given order (only record types listed, for display purposes)::

    PRE_CONN
    POST_CONN
    PRE_CONN
    POST_CONN
    PRE_REQ
    POST_REQ
    REQ_HDR
    PRE_REQ
    POST_REQ
    REQ_HDR

Whereby the occurrence of ``REQ_HDR`` type records are optional since it depends on configuration of ECN-Spider.

This is a sample output file snippet::

    1401961474.3344474,66.211.160.88,ebay.com,off,PRE_CONN,
    1401961474.3347988,206.190.36.45,yahoo.com,off,PRE_CONN,
    1401961474.335094,173.194.40.87,google.co.jp,off,PRE_CONN,
    1401961474.335769,[2a00:1450:4001:c02::bf],blogspot.com,off,POST_CONN,0
    1401961474.3749285,162.243.54.31,fc2.com,on,POST_REQ,200
    1401961474.375057,162.243.54.31,fc2.com,on,REQ_HDR,"[('Accept-Ranges', 'bytes'), ('Content-Type', 'text/html'), ('Date', 'Thu, 05 Jun 2014 09:44:01 GMT'), ('ETag', '""683d3b-8818-4fb13875fde40""'), ('Last-Modified', 'Thu, 05 Jun 2014 09:40:01 GMT'), ('Server', 'nginx/1.1.19'), ('Vary', 'Accept-Encoding'), ('Content-Length', '34840'), ('Connection', 'Close')]"
    1401961474.375366,54.200.228.182,fc2.com,off,PRE_REQ,False
    1401961474.4061024,206.190.36.45,yahoo.com,off,POST_CONN,47885
    1401961474.4142444,66.211.160.88,ebay.com,off,POST_CONN,55109
    1401961474.4262393,173.194.70.191,blogspot.com,off,POST_CONN,49240
    1401961474.4331276,173.194.40.87,google.co.jp,off,POST_CONN,45960
    1401961474.4698431,162.243.54.31,fc2.com,off,POST_REQ,200