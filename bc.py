#!/usr/bin/env python
# -*- coding: UTF-8 -*-

import numpy as np
import time
import datetime
import threading
from multiprocessing import Process,Queue

def send(queue):
	while True:
		times = [abs(x) for x in np.random.normal(1, 0.5, 1000)]
		while times:
			t = times.pop()
			val = get_value()
			time.sleep(t)
			queue.put(['bc', datetime.datetime.now(), val])

def get_value():
	return abs(np.random.normal(100, 50))