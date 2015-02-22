# Overview
The master controls the testing procedure, and coordinates all entities. The master starts worker processes on client machines. Each client machine represents one vantage point for a test session, and so each client's workers handle the same jobs simultaneously.

Parallelization is implemented using the features of Python's ``multiprocessing`` module (https://docs.python.org/3.4/library/multiprocessing.html).

In particular, this module already offers ways for processes running on different machines to communicate with each other (using ``SyncManager``) as well as synchronization primitives that work over these channels.

Configuration parameters constant for one whole test:
MAX_WORKERS: maximum number of workers per client
NUM_CLIENTS: number of clients

# Problems
* A variety of the synchronization primitives to be used synchronize a fixed number of processes. If one process hangs, or can not sensibly continue due to an error, it is difficult to make the rest recover.
* TCP connections open to the web servers under test may time out if one worker has to wait a long time for another worker to connect.

# Tasks of the master
* disable ECN

* start all workers

* Populate one job list for each client identical to all other job lists

* emit 'start'
* wait for every worker on all machines to be done

* Repeat, if there are jobs left

# Tasks of a worker

* Wait for 'start'

* get a job; if there are no jobs left, emit 'done'
* disable ECN (needs handling of timeout?)
* resolve URL from job to IP address (needs handling of timeout)

* emit 'I have IP'
* wait for every worker on all machines to get an IP

* connect socket (needs handling of timeout)

* emit 'I have connection'
* wait for every worker on this machine to get a connect

* enable ECN (needs handling of timeout)
* connect socket (needs handling of timeout)

* emit 'I have connection2'
* wait for every worker on all machines to get a connect

* Make GET request, save result (needs handling of timeout)

* emit 'done'
