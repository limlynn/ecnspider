#!/usr/bin/env python3
# -*- coding: utf-8 -*-

'''
ECN-Spider: Crawl web pages to test the Internet's support of ECN.

Setting up ECN-Spider:

This application requires root privileges to change some settings using sysctl. The following steps grant ECN-Spider the minimal rights to make it work:
1) Install the application 'sudo'.
2) Add the following rule to the sudoers file, adjusting 'username' as necessary:
username ALL=NOPASSWD: /sbin/sysctl -w net.ipv4.tcp_ecn=[0-2]

Of course, if your setup allow caching the password for use of sudo, then that works too. Apart from during startup, subsequent calls to sudo should never be more than a user-defined timeout value (+ a small constant) apart, so typically in the order of 10 seconds. Your cached password should not expire.

.. moduleauthor:: Damiano Boppart <hat.guy.repo@gmail.com>

Copyright 2014 Damiano Boppart

This file is part of ECN-Spider.
'''

import subprocess
import platform
import sys
import http.client
from collections import namedtuple
import csv
#import errno
import logging
import threading
import queue
from time import sleep
import io
import time
import argparse
import datetime
import socket
import bisect
from math import floor

E = {
	'timeout': 'socket.timeout',
	'refused': 'Connection refused',
	'noroute': 'No route to host',
	'invalid': 'Invalid argument',
	'perm': 'Permission denied',
	'unreach': 'Network is unreachable',
	'success': 'success'}  #: Error strings used by ecn_spider

NO_RETRY = frozenset([None, E['invalid'], E['perm']])
DLOGGER = None  #: DataLogger instance shared between all threads
RETRY_LOGGER = None  #: DataLogger instance shared for writing the retry data file
USER_AGENT = 'Mozilla/5.0 (X11; Linux x86_64; rv:28.0) Gecko/20100101 Firefox/28.0'  #: User agent string used for HTTP requests
RUN = False  #: Signal end to master and worker threads
VERBOSITY = 100  #: Print message about processing speed every VERBOSITY jobs.
Q_SIZE = 100  #: Maximum job queue size
PER = None
count = None  #: Shared counter instance to keep track of completed jobs.
retry_count = None  #: Shared counter instance for keeping track of number of jobs to be retried.
ARGS = None  #: argparse configuration
START_TIME = None  #: Start time. Used to calculate runtime.

ECN_STATE = {
	'never': 0,
	'always': 1,
	'on_demand': 2
}  #: Mapping of human-readable strings to values used for /proc/net/ipv4/tcp_ecn .

Record = namedtuple('Record', ['rank', 'domain', 'ipv4', 'ipv6'])  #: Type used to parse the input CSV file into
Job = namedtuple('Job', ['rank', 'domain', 'ip'])  #: Type of elements in job queue


class SharedCounter:
	'''
	A counter object that can be shared by multiple threads.
	Based on : http://chimera.labs.oreilly.com/books/1230000000393/ch12.html#_problem_200
	'''
	def __init__(self, initial_value=0):
		self._value = initial_value
		self._value_lock = threading.Lock()
	
	def __str__(self):
		return str(self.value)

	def incr(self, delta=1):
		'''
		Increment the counter with locking
		'''
		with self._value_lock:
			self._value += delta

	def decr(self, delta=1):
		'''
		Decrement the counter with locking
		'''
		with self._value_lock:
			self._value -= delta
	
	@property
	def value(self):
		'''
		Get the value of the counter.
		'''
		with self._value_lock:
			return self._value


class DataLogger(logging.Logger):
	'''
	A logger that outputs CSV.
	
	This logger generates its messages using Python's CSV module, and has no fancy log string formatting. Only the content of the iterable passed to :meth:`writerow` will be written to the logfile.
	'''
	def __init__(self, file_name):
		'''
		:param str file_name: The log filename.
		'''
		logging.Logger.__init__(self, 'DataLogger', level=logging.DEBUG)
		fileHandler = logging.FileHandler(file_name, encoding='utf-8')
		fileFormatter = logging.Formatter('%(message)s')
		fileHandler.setFormatter(fileFormatter)
		fileHandler.setLevel(logging.DEBUG)
		self.addHandler(fileHandler)
		
		self._strio = io.StringIO()
		self._writer = csv.writer(self._strio, quoting=csv.QUOTE_MINIMAL)
	
	def writerow(self, data, lvl=logging.DEBUG):
		'''
		Produce one logfile record.
		
		:param data: An iterable of fields. This will be converted to a CSV row, and then written to file.
		:param lvl: Logging level. See documentation of the logging module for information on levels.
		'''
		if hasattr(data, '__getitem__'):
			strio = io.StringIO()
			writer = csv.writer(strio, quoting=csv.QUOTE_MINIMAL)
			writer.writerow(data)
			self.log(lvl, strio.getvalue().rstrip('\r\n'))
		else:
			raise ValueError('"data" has no "__getitem__"')


class SemaphoreN(threading.BoundedSemaphore):
	'''
	An extension to the standard library's BoundedSemaphore that provides functions to handle n tokens at once.
	'''
	def __init__(self, value):
		self._VALUE = value
		super().__init__(self._VALUE)
		self.empty()
	
	def __str__(self):
		return 'SemaphoreN with a maximum value of {}.'.format(self._VALUE)
	
	def acquire_n(self, value=1, blocking=True, timeout=None):
		'''
		Acquire ``value`` number of tokens at once.
		
		The parameters ``blocking`` and ``timeout`` have the same semantics as :class:`BoundedSemaphore`.
		
		:returns: The same value as the last call to `BoundedSemaphore`'s :meth:`acquire` if :meth:`acquire` were called ``value`` times instead of the call to this method.
		'''
		ret = None
		for _ in range(value):
			ret = self.acquire(blocking=blocking, timeout=timeout)
		return ret
	
	def release_n(self, value=1):
		'''
		Release ``value`` number of tokens at once.
		
		:returns: The same value as the last call to `BoundedSemaphore`'s :meth:`release` if :meth:`release` were called ``value`` times instead of the call to this method.
		'''
		ret = None
		for _ in range(value):
			ret = self.release()
		return ret
	
	def empty(self):
		'''
		Acquire all tokens of the semaphore.
		'''
		while self.acquire(blocking=False):
			pass


class BigPer():
	'''
	A thread-safe class that allows the calculation of percentiles of an internal list of values that can be continually added to.
	'''
	def __init__(self):
		self._d = []
		self._s = threading.BoundedSemaphore()
	
	def append(self, value):
		'''
		Add a new value to the internal list of values.
		'''
		with self._s:
			bisect.insort_left(self._d, value)
	
	def percentile_left(self, p=50):
		'''
		Calculate the (possibly rounded down) pth percentile of the internal list of values.
		
		:returns: Always returns a value from the list.
		'''
		if p < 0 or p > 100:
			raise ValueError('p is not a valid percentage value.')
		
		with self._s:
			i = floor((len(self._d) - 1) * (p / 100))
			#print('len: {}, i: {}.'.format(len(self._d) - 1, i))
			return self._d[i]
	
	@property
	def length(self):
		'''
		Calculate the length of the list of values.
		'''
		return len(self._d)


def get_ecn():
	'''
	Use sysctl to get the kernel's ECN behavior.
	
	:raises: subprocess.CalledProcessError when the command fails.
	'''
	ecn = subprocess.check_output(['/sbin/sysctl', '-n', 'net.ipv4.tcp_ecn'], universal_newlines=True).rstrip('\n')
	ecn = [k for k, v in ECN_STATE.items() if v == int(ecn)][0]
	return ecn


def set_ecn(value):
	'''
	Use sysctl to set the kernel's ECN behavior.
	
	This is the equivalent of calling "sudo /sbin/sysctl -w "net.ipv4.tcp_ecn=$MODE" in a shell.
	
	:raises: subprocess.CalledProcessError when the command fails.
	'''
	if value in ECN_STATE.keys():
		subprocess.check_output(['sudo', '-n', '/sbin/sysctl', '-w', 'net.ipv4.tcp_ecn={}'.format(ECN_STATE[value])], universal_newlines=True).rstrip('\n')
	elif value in ECN_STATE.values():
		subprocess.check_output(['sudo', '-n', '/sbin/sysctl', '-w', 'net.ipv4.tcp_ecn={}'.format(value)], universal_newlines=True).rstrip('\n')
	else:
		raise ValueError('Only keys or values from ECN_STATE may be used to call set_ecn.')


def disable_ecn():
	''' Wrapper for :meth:`set_ecn` to disable ECN. '''
	set_ecn('never')


def enable_ecn():
	''' Wrapper for :meth:`set_ecn` to enable ECN. '''
	set_ecn('always')


def check_ecn():
	'''
	Test that all the things that are done with ``sysctl`` work properly.
	
	:returns: If this function returns without raising an exception, then everything is in working order.
	'''
	state = get_ecn()
	set_ecn(state)
	
	set_ecn('never')
	set_ecn('always')
	set_ecn('on_demand')
	
	set_ecn(state)


def print_platform():
	''' Print information about the platform. '''
	logger = logging.getLogger('default')
	p_info = platform.platform()
	logger.info('Platform Information: {}.'.format(p_info))
	logger.info(sys.version_info)


def master(num_workers, ecn_on, ecn_on_rdy, ecn_off, ecn_off_rdy):
	'''
	Master thread for controlling the kernel's ECN behavior.
	
	This thread synchronizes with the worker threads using the following semaphores:
	
	``ecn_on``
		Master signals the workers that ECN has just been turned on.
	
	``ecn_on_rdy``
		Worker signals the master that ECN may be turned on now.
	
	``ecn_off``
		Master signals the workers that ECN has just been turned off.
	
	``ecn_off_rdy``
		Worker signals the master that ECN may be turned off now.
	
	The five semaphores must have been created before this thread is started, and their values must have been set to zero, i.e. acquiring a token is not possible.
	
	:param int num_workers: Number of worker threads (that perform HTTP requests)
	:param SemaphoreN ecn_on, ecn_on_rdy, ecn_off, ecn_off_rdy, end: The semaphores described above.
	'''
	logger = logging.getLogger('default')
	while RUN:
		disable_ecn()
		logger.debug('ECN off connects from here onwards.')
		ecn_off.release_n(num_workers)
		ecn_on_rdy.acquire_n(num_workers)
		enable_ecn()
		logger.debug('ECN on connects from here onwards.')
		ecn_on.release_n(num_workers)
		ecn_off_rdy.acquire_n(num_workers)
	
	# In case the master exits the run loop before all workers have, these tokens will allow all workers to run through again, until the next check at the start of the RUN loop
	ecn_off.release_n(num_workers)
	ecn_on.release_n(num_workers)
	
	logger.debug('Master thread ending.')


def setup_socket(ip, timeout):
	'''
	Open a socket using an instance of http.client.HTTPConnection.
	
	:param ip: IP address
	:param timeout: Timeout for socket operations
	:returns: A tuple of: Error message or None, an instance of http.client.HTTPConnection.
	'''
	logger = logging.getLogger('default')
	client = http.client.HTTPConnection(ip, timeout=timeout)
	client.auto_open = 0
	try:
		client.connect()
	except socket.timeout:
		logger.error('Connecting to {} timed out.'.format(ip))
		return ('socket.timeout', None)
	except OSError as e:
		if e.errno is None:
			logger.error('Connecting to {} failed: {}'.format(ip, e))
			return (str(e), None)
		else:
			logger.error('Connecting to {} failed: {}'.format(ip, e.strerror))
			return (e.strerror, None)
	else:
		return (None, client)


def make_get(client, domain, note):
	'''
	Make an HTTP GET request and return the important bits of information as a dictionary.
	
	:param client: The instance of http.client.HTTPConnection for making the request with.
	:param domain: The value of the ``Host`` field of the GET request.
	:param note: The string 'eoff' or 'eon'. Used as part of the keys in the returned dictionary.
	'''
	if note not in ['eoff', 'eon']:
		raise ValueError('Unsupported value for note: {}.'.format(note))
	
	logger = logging.getLogger('default')
	
	h = {'User-Agent': USER_AGENT, 'Connection': 'close'}
	if domain is not None:
		h['Host'] = domain
	
	d = {}  # Dictionary of values to be logged to the CSV output file.
	err_name = 'http_err_' + note
	stat_name = 'status_' + note
	hdr_name = 'headers_' + note
	
	try:
		client.request('GET', '/', headers=h)
		r = client.getresponse()
		client.close()
		
		logger.debug('Request for {} ({}) returned status code {}.'.format(client.host, note, r.status))
		
		d[stat_name] = r.status
		if ARGS.save_headers:
			d[hdr_name] = r.getheaders()
		else:
			d[hdr_name] = None
		d[err_name] = None
	except OSError as e:
		if e.errno is None:
			logger.error('Request for {} failed (errno None): {}'.format(client.host, e))
			d[err_name] = str(e)
			d[stat_name] = None
			d[hdr_name] = None
		else:
			logger.error('Request for {} failed (with errno): {}'.format(client.host, e.strerror))
			d[err_name] = e.strerror
			d[stat_name] = None
			d[hdr_name] = None
	except Exception as e:
		logger.error('Request for {} failed ({}): {}.'.format(client.host, type(e), e))
		d[err_name] = str(e)
		d[stat_name] = None
		d[hdr_name] = None
	return d


def retry(eoff_err, eon_err):
	return not ((eoff_err in NO_RETRY) and (eon_err in NO_RETRY))


def worker(queue_, timeout, ecn_on, ecn_on_rdy, ecn_off, ecn_off_rdy):
	'''
	Worker thread for crawling websites with and without ECN.
	
	This thread synchronizes with the master thread using the semaphores described in the documentation of :meth:`master`.
	
	The five semaphores must have been created before this thread is started, and their values must have been set to zero, i.e. acquiring a token is not possible.
	
	:param Queue queue: A job queue with elements of type ``Job``.
	:param int timeout: Timeout for socket operations.
	:param SemaphoreN ecn_on, ecn_on_rdy, ecn_off, ecn_off_rdy: The semaphores referenced above.
	'''
	logger = logging.getLogger('default')
	tl = datetime.datetime.now()  # Timestamp for measuring frequency of job processing for this worker
	
	while RUN:
		queue_job = False  #: If the current job was taken from the queue this is True
		try:
			job = queue_.get_nowait()
			tt = datetime.datetime.now()
			PER.append((tt - tl).total_seconds())
			tl = tt
			queue_job = True
			d = {}  # Aggregator for values to go into the CSV output file. The values that this dict will contain at log entry writing time are:
				#record_time
				#rank
				#domain
				#ip
				#eoff_err
				#port_eoff
				#eon_err
				#port_eon
				#pre_conn_eoff_time
				#post_conn_eoff_time
				#pre_conn_eon_time
				#post_conn_eon_time
				#pre_req_time
				#inter_req_time
				#post_req_time
				#http_err_eoff
				#status_eoff
				#headers_eoff
				#http_err_eon
				#status_eon
				#headers_eon
		except queue.Empty:
			sleep(0.5)
			logger.debug('Not a queue job, skipping processing.')
		
		ecn_off.acquire()
		
		if queue_job:
			logger.debug('Connecting with ECN off...')
			
			d['ip'] = job.ip
			d['rank'] = job.rank
			d['domain'] = job.domain
			d['pre_conn_eoff_time'] = time.time()
			
			eoff_err, eoff = setup_socket(job.ip, timeout=timeout)
			
			d['post_conn_eoff_time'] = time.time()
			d['eoff_err'] = eoff_err
			if isinstance(eoff, http.client.HTTPConnection):
				d['port_eoff'] = eoff.sock.getsockname()[1]
			else:
				d['port_eoff'] = 0
		
		ecn_on_rdy.release()
		ecn_on.acquire()
		
		if queue_job:
			logger.debug('Connecting with ECN on...')
			
			d['pre_conn_eon_time'] = time.time()
			
			if ARGS.fast_fail and eoff_err == 'socket.timeout':
				eon_err = 'no_attempt'
				eon = None
			else:
				eon_err, eon = setup_socket(job.ip, timeout=timeout)
			
			d['post_conn_eon_time'] = time.time()
			d['eon_err'] = eon_err
			if isinstance(eon, http.client.HTTPConnection):
				d['port_eon'] = eon.sock.getsockname()[1]
			else:
				d['port_eon'] = 0
		
		ecn_off_rdy.release()
		
		if queue_job:
			logger.debug('Making GET requests...')
			
			d['pre_req_time'] = time.time()
			
			if isinstance(eon, http.client.HTTPConnection):
				d_ = make_get(eon, job.domain, 'eon')
				d.update(d_)
			else:
				d['http_err_eon'] = 'no_attempt'
				d['status_eon'] = None
				d['headers_eon'] = None
			
			d['inter_req_time'] = time.time()
			
			if isinstance(eoff, http.client.HTTPConnection):
				d_ = make_get(eoff, job.domain, 'eoff')
				d.update(d_)
			else:
				d['http_err_eoff'] = 'no_attempt'
				d['status_eoff'] = None
				d['headers_eoff'] = None
			
			d['post_req_time'] = time.time()
			d['record_time'] = time.time()
			
			DLOGGER.writerow([d['record_time'], d['rank'], d['domain'], d['ip'], d['eoff_err'], d['port_eoff'], d['eon_err'], d['port_eon'], d['pre_conn_eoff_time'], d['post_conn_eoff_time'], d['pre_conn_eon_time'], d['post_conn_eon_time'], d['pre_req_time'], d['inter_req_time'], d['post_req_time'], d['http_err_eoff'], d['status_eoff'], d['headers_eoff'], d['http_err_eon'], d['status_eon'], d['headers_eon']])
			
			if retry(d['eoff_err'], d['eon_err']):
				# This test needs to be retried.
				logger.debug('eoff_err == {}, eon_err == {}.'.format(d['eoff_err'], d['eon_err']))
				stripped_ip = d['ip'].lstrip('[').rstrip(']')
				if stripped_ip == d['ip']:
					# This is a v4 address, since it did not have square brackets
					RETRY_LOGGER.writerow([d['rank'], d['domain'], stripped_ip, ''])
				else:
					RETRY_LOGGER.writerow([d['rank'], d['domain'], '', stripped_ip])
				retry_count.incr()
			
			queue_.task_done()
			count.incr()
	
	logger.debug('Worker thread ending.')


def domain_reader(max_lines, *args, **kwargs):
	'''
	A wrapper around csv reader, that makes it a generator. Reads records from the input file, and returns them as the ``namedtuple`` ``Record``.
	
	:param \*args: Arguments passed to :meth:`csv.reader`.
	:param \*\*kwargs: Keyword arguments passed to :meth:`csv.reader`.
	:returns: One record in the form of ``namedtuple`` ``Record`` on each call to next()
	'''
	reader = limited_reader(max_lines, *args, **kwargs)
	
	for row in map(Record._make, reader):
		yield row


def limited_reader(max_lines=0, *args, **kwargs):
	'''
	A wrapper around :meth:`csv.reader`, that returns only the first ``max_lines`` lines.
	
	:param int max_lines: The maximum number of lines to return. All, if set to 0.
	:param \*args: Arguments passed to :meth:`csv.reader`.
	:param \*\*kwargs: Keyword arguments passed to :meth:`csv.reader`.
	'''
	reader = csv.reader(*args, **kwargs)
	
	c = 0
	for row in reader:
		yield row
		c += 1
		if max_lines != 0 and c >= max_lines:
			break


def arguments(argv):
	'''
	Parse the command-line arguments.
	
	:param argv: The command line.
	:returns: The return value of ``argparse.ArgumentParser.parse_args``.
	'''
	parser = argparse.ArgumentParser(description='%(prog)s: Crawl web pages using TCP connections with and without ECN simultaneously.', epilog='This program is part of ECN-Spider.')
	
	parser.add_argument('input', type=str, help='CSV format input data file with domain names and associated IP addresses. Each record has the format: "domain,IPv4,IPv6".')
	parser.add_argument('retry_data_file', type=str, help='CSV format output data file for running retries of failed tests with %(prog)s. This file will consist of a subset of the information of the input data. Each domain will have at most one IP, but a domain may appear twice if it had both an IPv4 and IPv6 address originally.')
	parser.add_argument('output', type=str, help='CSV format output data file with meta-data and data of HTTP GET requests that were answered.')
	parser.add_argument('logfile', type=str, help='Log file with all further messages about the run.')
	
	parser.add_argument('--verbosity', '-v', default='DEBUG', choices=['CRITICAL', 'ERROR', 'WARNING', 'INFO', 'DEBUG'], help='Verbosity of logging to stdout. Writing to output files will not be affected by this setting.')
	parser.add_argument('--workers', '-w', type=int, default='5', help='The number of worker threads used for making HTTP requests.')
	parser.add_argument('--timeout', '-t', type=int, default='10', help='Timeout for connection setup.')
	parser.add_argument('--no-tcpdump-check', action='store_true', dest='no_tcpdump_check', help='If set, ECN-Spider will not fail when it can\'t find tcpdump running already at startup.')
	parser.add_argument('--save-headers', '-s', action='store_true', dest='save_headers', help='If set, write the HTTP response headers to the CSV file, otherwise leave the header field empty in the CSV output.')
	parser.add_argument('--no-IPv6', '-6', action='store_true', dest='no_ipv6', help='If set, do not attempt to test any IPv6 addresses. Use this switch on machines with no IPv6 address.')
	parser.add_argument('--debug-count', '-d', type=int, default='0', dest='debug_count', help='Perform test for at most N domains. All of them if this value is set to 0.')
	parser.add_argument('--fast-fail', '-f', action='store_true', dest='fast_fail', help='For debugging only. If set, do not attempt to make connections with ECN when the non-ECN connections times out. Using this switch makes the assumption that there will be no server that allows ECN connections, while allowing non-ECN connections. Also, the information for retries may be inaccurate when this option is used.')
	
	args = parser.parse_args(argv)
	
	# Input validation
	if args.workers <= 0:
		raise ValueError('Workers must be a positive integer, it was set to {}.'.format(args.workers))
	if args.timeout <= 0:
		raise ValueError('Timeout must be a positive integer, it was set to {}.'.format(args.timeout))
	if not args.no_tcpdump_check:
		import psutil
		ps = [p for p in psutil.process_iter() if 'tcpdump' in str(p.name)]
		if len(ps) == 0:
			raise Exception('No tcpdump process is running. To skip this check, use "--no-tcpdump-check".')
	if args.debug_count < 0:
		raise ValueError('Debug_count must be a positive integer, it was set to {}.'.format(args.debug_count))
	
	return args


def filler(file_name, queue_):
	'''
	Fill a queue with jobs from the input file.
	
	:param file_name: Input file with jobs.
	:param queue_: Job queue to fill.
	'''
	logger = logging.getLogger('default')
	
	with open(file_name) as inf:
		reader = domain_reader(ARGS.debug_count, inf)
		
		q = queue_
		#t0 = datetime.datetime.now()  # Start time of job queue population
		#tl = t0  # Time since last printed message
		#c = 0  # Counter of added jobs
		
		for job in reader:
			logger.debug('Parsing job {}.'.format(job))
			if job.ipv4 == '' and job.ipv6 == '':
				logger.debug('No IP for "{}"'.format(job.domain))
				continue
			if job.ipv4 != '':
				j = Job(rank=job.rank, domain=job.domain, ip=job.ipv4)
				q.put(j)
			if job.ipv6 != '' and not ARGS.no_ipv6:
				j = Job(rank=job.rank, domain=job.domain, ip='[' + job.ipv6 + ']')
				q.put(j)
	
	logger.debug('Filler thread ending.')


def set_up_logging(logfile, verbosity):
	'''
	Configure logging.
	
	:param file logfile: Filename of logfile.
	:param verbosity verbosity: Stdout logging verbosity.
	'''
	#logging.basicConfig(filemode='w')
	logger = logging.getLogger('default')
	logger.setLevel(logging.DEBUG)
	
	fileHandler = logging.FileHandler(logfile)
	fileFormatter = logging.Formatter('%(created)f,%(threadName)s,%(levelname)s,%(message)s')
	fileHandler.setFormatter(fileFormatter)
	fileHandler.setLevel(logging.DEBUG)
	logger.addHandler(fileHandler)
	
	consoleHandler = logging.StreamHandler(sys.stdout)
	consoleFormatter = logging.Formatter('%(asctime)s [%(threadName)-10.10s] [%(levelname)-5.5s]  %(message)s')
	consoleHandler.setFormatter(consoleFormatter)
	consoleHandler.setLevel(verbosity)
	logger.addHandler(consoleHandler)
	
	logger.debug('All logging handlers: {}.'.format(logger.handlers))
	
	logger.info('The logging level is set to %s.', logging.getLevelName(logger.getEffectiveLevel()))
	logger.info('Running Python %s.', platform.python_version())
	logger.info('ECN: {}.'.format(get_ecn()))
	
	return logger


def reporter(queue_):
	'''
	Periodically report on the length of the job queue.
	'''
	period = 1  #: Interval between log messages in seconds. Increases exponentially up to MAX_PERIOD.
	MAX_PERIOD = 120  #: Maximum interval between log messages.
	t0 = datetime.datetime.now()  # Start time of rate calculation
	tl = t0  # Time since last printed message
	completed_jobs = 0
	logger = logging.getLogger('default')
	
	while RUN:
		# FIXME Switch to semaphore with timeout here to avoid wait at the end.
		sleep(period)
		if period >= MAX_PERIOD:
			period = MAX_PERIOD
		else:
			period *= 2
		
		queue_length = queue_.qsize()
		queue_utilization = queue_length / Q_SIZE * 100
		prev_completed_jobs = completed_jobs
		completed_jobs = count.value
		retries = retry_count.value
		try:
			med_job_interval = PER.percentile_left()
		except IndexError:
			med_job_interval = -1
		tt = datetime.datetime.now()
		current_rate = float(completed_jobs - prev_completed_jobs) / (tt - tl).total_seconds()
		average_rate = float(completed_jobs) / (tt - t0).total_seconds()
		runtime = tt - START_TIME
		tl = tt
		
		# NOTE The last stats might be printed before all jobs were processed, it's a race condition.
		logger.info('Queue: {q_len:4}, {q_util:5.1f}%. Done: {jobs:6}. Med. job ival: {med:5.2f}s. Rate: now: {cur:6.2f} Hz; avg: {avg:6.2f} Hz. Runtime {rtime}. Sched. retries: {rtry}'.format(q_len=queue_length, q_util=queue_utilization, jobs=completed_jobs, med=med_job_interval, cur=current_rate, avg=average_rate, rtime=runtime, rtry=retries))
	
	logger.debug('Reporter thread ending.')


def main(argv):
	'''
	Method to be called when run from the command line.
	'''
	args = arguments(argv)
	
	global ARGS
	ARGS = args
	
	global count
	count = SharedCounter()
	
	global retry_count
	retry_count = SharedCounter()
	
	# Test that the kernel's ECN-related behavior can be changed
	# This will raise subprocess.CalledProcessError if there is a problem
	try:
		check_ecn()
	except subprocess.CalledProcessError:
		print('Error running the necessary commands as root. Make sure that you can execute "sudo /sbin/sysctl -w net.ipv4.tcp_ecn=$MODE" for $MODE = 0, 1 or 2 as the user ECN-Spider runs as.')
		return 1
	
	# Set up logging
	logger = set_up_logging(args.logfile, args.verbosity)
	
	# FIXME See that everyone can use getLogger instead of having a global instance instead.
	global DLOGGER
	DLOGGER = DataLogger(args.output)
	
	global RETRY_LOGGER
	RETRY_LOGGER = DataLogger(args.retry_data_file)
	
	global PER
	PER = BigPer()
	
	ecn_on = SemaphoreN(args.workers)
	ecn_on.empty()
	ecn_on_rdy = SemaphoreN(args.workers)
	ecn_on_rdy.empty()
	ecn_off = SemaphoreN(args.workers)
	ecn_off.empty()
	ecn_off_rdy = SemaphoreN(args.workers)
	ecn_off_rdy.empty()
	#end = SemaphoreN(args.workers + 2)
	#end.empty()
	#all_filled = SemaphoreN(1)
	#all_filled.empty()
	
	global RUN
	RUN = True
	
	ts = {}  #: Dictionary of thread instances.
	
	q = queue.Queue(Q_SIZE)
	
	global START_TIME
	START_TIME = datetime.datetime.now()
	
	t = threading.Thread(target=reporter, name='reporter', args=(q, ), daemon=True)
	t.start()
	ts[t.name] = t
	
	t = threading.Thread(target=filler, name='filler', args=(args.input, q), daemon=True)
	t.start()
	ts[t.name] = t
	
	t = threading.Thread(target=master, name='master', args=(args.workers, ecn_on, ecn_on_rdy, ecn_off, ecn_off_rdy), daemon=True)
	t.start()
	ts[t.name] = t
	
	for i in range(args.workers):
		t = threading.Thread(target=worker, name='worker_{}'.format(i), args=(q, args.timeout, ecn_on, ecn_on_rdy, ecn_off, ecn_off_rdy), daemon=True)
		t.start()
		ts[t.name] = t
	
	# When the filler thread ends, and the queue is empty (both conditions necessary), continue to shutdown.
	ts['filler'].join()
	q.join()
	
	RUN = False
	
	for i in ts.values():
		i.join()
	
	logger.info('All done.')
	
	set_ecn('on_demand')
	
	return 0


if __name__ == '__main__':
	sys.exit(main(sys.argv[1:]))
