#!/usr/bin/env python
# -*- coding: UTF-8 -*-

import numpy as np
import time
import _strptime
from datetime import datetime
import threading
import os
import sys
import csv
from multiprocessing import Process,Queue

def send(queue):
	files = ['AE33-1-BC-nan.csv', 'MA300-1-BC-nan.csv']
	names = [x.replace('.csv', '') for x in files]
	threads = []
	for index in range(2):
		t = threading.Thread(target=send_file, args=(queue, names[index], index))
		t.daemon = True
		threads.append(t)
	try:
		for t in threads:
			t.start()
		while True:
			time.sleep(100)
	except (KeyboardInterrupt, SystemExit):
		sys.exit()

def send_file(queue, name, thread):
	if getattr(sys, 'frozen', False):
		new_path = os.path.realpath(os.path.join(os.getcwd(), '..', 'plume_results', 'Trapac_2019_Day5', name + '.csv'))
	elif __file__:
		__location__ = os.path.realpath(os.path.join(os.getcwd(), os.path.dirname(__file__)))
		new_path = os.path.join(__location__, '..', 'plume_results', 'Trapac_2019_Day5', name + '.csv')
	new_path = os.path.join(__location__, '..', 'plume_results', 'Trapac_2019_Day5', name + '.csv')
	with open(new_path) as csv_file:
		csv_reader = csv.reader(csv_file, delimiter=',')
		next(csv_reader)
		for i in range(360):
			next(csv_reader)
		first_item = next(csv_reader)
		try:
			actual_time = datetime.strptime(first_item[0], '%Y-%m-%d %H:%M:%S.%f')
		except ValueError:
			actual_time = datetime.strptime(first_item[0], '%M:%S.%f')
		send_time = datetime.now()
		try:
			currpost_value = float(first_item[2])
		except ValueError:
			currpost_value = 0
		first_post = ([name, 'BC'], [currpost_value, datetime.now()])
		queue.put(first_post)
		for item in csv_reader:
			try:
				local_time = datetime.strptime(item[0], '%Y-%m-%d %H:%M:%S.%f')
			except ValueError:
				local_time = datetime.strptime(item[0], '%M:%S.%f')
			time.sleep((local_time - actual_time).total_seconds())
			actual_time = local_time
			try:
				local_value = float(item[2])
			except ValueError:
				local_value = 0
			post = ([name, 'BC'], [local_value, datetime.now()])
			queue.put(post)

# def send(queue):
# 	np.random.seed()
# 	while True:
# 		val = get_value()
# 		time.sleep(0.2)
# 		post = ['bc', datetime.datetime.now(), val]
# 		queue.put(post)

# def get_value():
# 	return abs(np.random.normal(loc=20, scale=5))