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

class Instrument(object):
	def __init__(self, name, v_type):
		self.name = name
		self.v_type = v_type

	def __str__(self):
		return "%s %s Instrument" % (self.name, self.v_type)

	def __repr__(self):
		return self.__str__()

def send(queue, filepath):
	instruments = []
	# open ../instruments.csv and construct instr dict
	instr_file = os.path.join(filepath, 'instruments.csv')
	with open(instr_file) as instr_file:
		instr_reader = csv.reader(instr_file, delimiter=',')
		next(instr_reader)
		for instr in instr_reader:
			i = Instrument(instr[0], instr[1])
			instruments.append(i)

	queue.put(('instruments', instruments))

	raw_data_path = os.path.join(filepath, 'raw_data.csv')
	with open(raw_data_path) as csv_file:
		csv_reader = csv.reader(csv_file, delimiter=',')
		next(csv_reader)
		first_item = next(csv_reader)
		actual_time = datetime.strptime(first_item[0], '%Y-%m-%d %H:%M:%S.%f')
		currpost_value = float(first_item[3])
		first_post = ([first_item[1], first_item[2]], [currpost_value, datetime.now()])
		queue.put(first_post)
		for item in csv_reader:
			local_time = datetime.strptime(item[0], '%Y-%m-%d %H:%M:%S.%f')
			sleep_time = (local_time - actual_time).total_seconds()
			time.sleep((local_time - actual_time).total_seconds())
			actual_time = local_time
			try:
				local_value = float(item[3])
			except ValueError:
				local_value = 0
			post = ([item[1], item[2]], [currpost_value, datetime.now()])
			queue.put(post)