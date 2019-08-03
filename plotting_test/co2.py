#!/usr/bin/env python
# -*- coding: UTF-8 -*-

import numpy as np
import time
import _strptime
from datetime import datetime
import threading
import os
import csv
import sys
from multiprocessing import Process,Queue

def send(queue):
	files = ['LI7000-1-CO2-nan.csv', 'LI820-1-CO2-nan.csv', 'SBA5-1-CO2-nan.csv', 'Vaisala-1-CO2-nan.csv']
	threads = []
	for index in range(4):
		t = threading.Thread(target=send_file, args=(queue, files[index], index))
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
	script_dir = os.path.dirname(__file__)
	new_path = os.path.join(script_dir, '..', 'plume_results', 'Trapac_2019_Day5', name)
	with open(new_path) as csv_file:
		csv_reader = csv.reader(csv_file, delimiter=',')
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
		first_post = ['co2', send_time, currpost_value, thread]
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
			post = ['co2', datetime.now(), local_value, thread]
			queue.put(post)

# def send(queue):
# 	np.random.seed()
# 	while True:
# 		val = get_value()
# 		time.sleep(0.2)
# 		post = ['co2', datetime.datetime.now(), val]
# 		print(post)
# 		queue.put(post)

# def get_value():
# 	return abs(np.random.normal(loc=400, scale=50))