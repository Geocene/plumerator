#!/usr/bin/env python
# -*- coding: UTF-8 -*-

import numpy as np
import time
import datetime
import threading
from multiprocessing import Process,Queue

def send(queue):
	np.random.seed()
	while True:
		val = get_value()
		time.sleep(0.2)
		post = ['bc', datetime.datetime.now(), val]
		queue.put(post)

def get_value():
	return abs(np.random.normal(loc=20, scale=5))