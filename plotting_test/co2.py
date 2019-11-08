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

co2_files = ['LI7000-1-CO2-nan.csv', 'LI820-1-CO2-nan.csv', 'SBA5-1-CO2-nan.csv', 'Vaisala-1-CO2-nan.csv']
nox_files = ['CLD64-1-NOx-nan.csv', 'CAPS-1-NO2-nan.csv']
bc_files = ['AE33-1-BC-nan.csv', 'MA300-1-BC-nan.csv']

class Instrument(object):
	def __init__(self, name, v_type):
		self.name = name
		self.v_type = v_type

	def __str__(self):
		return "%s %s Instrument" % (self.name, self.v_type)

	def __repr__(self):
		return self.__str__()

def send(queue):
	names = [x.replace('.csv', '') for x in co2_files]
	threads = []
	for index in range(4):
		t = threading.Thread(target=send_file, args=(queue, names[index], index))
		t.daemon = True
		threads.append(t)
	instruments = []
	for f in co2_files:
		name = f.split('-')[0]
		instr = Instrument(name, 'CO2')
		instruments.append(instr)
	for f in nox_files:
		name = f.split('-')[0]
		instr = Instrument(name, 'NOX')
		instruments.append(instr)
	for f in bc_files:
		name = f.split('-')[0]
		instr = Instrument(name, 'BC')
		instruments.append(instr)
	queue.put(('instruments', instruments))
	try:
		for t in threads:
			t.start()
		while True:
			time.sleep(100)
	except (KeyboardInterrupt, SystemExit):
		sys.exit()

def send_file(queue, name, thread):
	if getattr(sys, 'frozen', False):
		__location__ = sys._MEIPASS
	else:
		__location__ = os.path.realpath(os.path.join(os.getcwd(), os.path.dirname(__file__)))
	new_path = os.path.join(__location__, '..', 'plume_results', 'Trapac_2019_Day5', name + '.csv')
	send_name = name.split('-')[0]
	with open(new_path) as csv_file:
		csv_reader = csv.reader(csv_file, delimiter=',')
		next(csv_reader)
		for i in range(1550):
			next(csv_reader)
		first_item = next(csv_reader)
		try:
			actual_time = datetime.strptime(first_item[0], '%Y-%m-%d %H:%M:%S.%f')
		except ValueError:
			actual_time = datetime.strptime(first_item[0], '%M:%S.%f')
		try:
			currpost_value = float(first_item[2])
		except ValueError:
			currpost_value = 0
		first_post = ([send_name, 'CO2'], [currpost_value, datetime.now()])
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
			post = ([send_name, 'CO2'], [local_value, datetime.now()])
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