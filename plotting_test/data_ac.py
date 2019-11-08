import serial.tools.list_ports
import signal
from datetime import datetime
import time
import threading
import collections
import fcntl
from multiprocessing import Process, Queue
import os, sys, csv, re, math
import numpy as np

stop_requested = False
bc_correction = 0.88
instruments = []

def serialGeneric(device,baudrate):
	ser = serial.Serial(port=device,
		baudrate=baudrate,
		parity=serial.PARITY_NONE,
		stopbits=serial.STOPBITS_ONE,
		bytesize=serial.EIGHTBITS
	)
	return ser

def sig_handler(signum, frame):
	sys.stdout.write("handling signal: %s\n" % signum)
	sys.stdout.flush()

	global stop_requested
	stop_requested = True

class Instrument(object):
	def __init__(self, comport, baudrate):
		if comport:
			self.serial = serialGeneric(comport, baudrate)
		global instruments
		instruments.append(self)

	def __str__(self):
		return "%s %s Instrument S#-%s" % (self.name, self.v_type, self.serial_num)

	def __repr__(self):
		return self.__str__()

	def dumpserial(self, ser, dt):
		with open(filepath + 'rawraw_data.csv', mode='ab') as rawFile:
			fcntl.flock(rawFile, fcntl.LOCK_EX)
			rawData = csv.writer(rawFile, delimiter=',', quotechar='"', quoting=csv.QUOTE_MINIMAL)
			rawData.writerow([dt, self.name, self.serial_num, ser])
			fcntl.flock(rawFile, fcntl.LOCK_UN)
		return

	def run(self, queue):
		while not stop_requested:
			values = self.get_values()
			if values is None:
				continue
			else:
				data_pack = ([self.name, self.v_type], values)
				# print(data_pack)
				queue.put(data_pack)
		if stop_requested:
			self.serial.close()

# BC Instr

class AE33_Instrument(Instrument):
	def __init__(self, sn):
		self.name = 'AE33'
		self.v_type = 'BC'
		self.serial_num = sn
		super(AE33_Instrument, self).__init__('/dev/cu.usbserial-' + self.serial_num, 9600)

	def get_values(self):
		bc_values = []
		ser = self.serial.readline()
		dt_object = datetime.now()
		self.dumpserial(ser, dt_object)
		time_str3 = dt_object.strftime('%H:%M:%S')
		values_ae33 = ser.split('\n')[0].split(',')
		time_now=int(time.time()*1000000000)
		try:
			bc2 = float(values_ae33[9])
			bc_ae33 = bc2/1000
			flow = float(values_ae33[10])
			bc_values.insert(0,bc_ae33)
			bc_values.insert(1,dt_object)
			bc_values.insert(2,flow)
		except(ValueError,IndexError) as e:
			print("ae33 index failure")
			return None
		return bc_values

class AE16_Instrument(Instrument):
	def __init__(self, sn):
		self.name = 'AE16'
		self.v_type = 'BC'
		self.serial_num = sn
		super(AE16_Instrument, self).__init__('/dev/cu.usbserial-' + self.serial_num, 9600)

	def get_values(self):
		bc_values = []
		ser = self.serial.readline()
		dt_object = datetime.now()
		self.dumpserial(ser, dt_object)
		time_str2 = dt_object.strftime('%H:%M:%S')
		values_ae16 = ser.split('\n')[0].split(',')
		time_now=int(time.time()*1000000000)
		try:
			#print(values_ae16)
			bc1 = float(values_ae16[2])
			bc = bc1/1000
			atn = float(values_ae16[9])
			bc = bc / (math.exp((-1*atn)/100)*bc_correction + (1-bc_correction))
			flow = float(values_ae16[3])
			bc_values.insert(0,bc)
			bc_values.insert(1,dt_object)
			bc_values.insert(2,flow)
			bc_values.insert(3,atn)

		except(ValueError,IndexError) as e:
			print("ae16 index error")
			return None
		return bc_values

class ABCD_Instrument(Instrument):
	def __init__(self, serial_num):
		self.name = 'ABCD'
		self.v_type = 'BC'
		self.serial_num = serial_num
		if 'wchusbserial' in self.serial_num:
			path = '/dev/cu.' + self.serial_num
		else:
			path = '/dev/cu.usbserial-' + self.serial_num
		super(ABCD_Instrument, self).__init__(path, 57600)

	def get_values(self):
		bc_values = []
		ser = self.serial.readline()
		values_abcd1 = ser.split('\n')[0].split(',')
		dt_object = datetime.now()
		self.dumpserial(ser, dt_object)
		#print(values_abcd1)
		time_now=int(time.time()*1000000000)
		#time_str1 = dt_object.strftime('%H:%M:%S')
		try:
			#print(values_abcd1)
			atn = float(values_abcd1[3])
			bc = float(values_abcd1[4])
			bc = bc / (math.exp((-1*atn)/100)*bc_correction + (1-bc_correction))
			flow = float(values_abcd1[7])
			bc_values.insert(0,bc)
			bc_values.insert(1,dt_object)
			bc_values.insert(2,flow)
			bc_values.insert(3,atn)
			#print(bc_abcd1)

		except (ValueError,IndexError) as e:
			print("abcd index failure")
			return None
		return bc_values

class MA300_Instrument(Instrument):
	def __init__(self, sn):
		self.name = 'MA300'
		self.v_type = 'BC'
		self.serial_num = sn
		super(MA300_Instrument, self).__init__('/dev/cu.usbserial-' + self.serial_num, 1000000)

	def get_values(self):
		bc_values = []
		ser = self.serial.readline()
		dt_object = datetime.now()
		self.dumpserial(ser, dt_object)
		time_str2 = dt_object.strftime('%H:%M:%S')
		values_ae16 = ser.split('\n')[0].split(',')
		time_now=int(time.time()*1000000000)

		try:
			#print(values_ae16)
			bc1 = float(values_ae16[44])
			bc = bc1/1000
			atn = float(values_ae16[9])
			bc = bc / (math.exp((-1*atn)/100)*bc_correction + (1-bc_correction))
			flow = float(values_ae16[4])
			bc_values.insert(0,bc)
			bc_values.insert(1,dt_object)
			bc_values.insert(2,flow)
			bc_values.insert(3,atn)

		except(ValueError,IndexError) as e:
			print("ma300 index error")
			return None
		return bc_values

# CO2 Instr
class LI7000_Instrument(Instrument):
	def __init__(self, sn):
		self.name = 'LI7000'
		self.v_type = 'CO2'
		self.serial_num = sn
		super(LI7000_Instrument, self).__init__('/dev/cu.usbserial-' + self.serial_num, 9600)

	def get_values(self):
		co2_values = []
		ser = self.serial.readline()
		dt_object = datetime.now()
		self.dumpserial(ser, dt_object)
		time_str5 = dt_object.strftime('%H:%M:%S')
		time_now=int(time.time()*1000000000)
		try:
			values_li7000 = ser.split('\n')[0].split('\t')

			#print("The values for li700 are:")
			#print(values_li7000)
			co2_values.insert(0,float(values_li7000[8])) # CO2 value
			co2_values.insert(1,dt_object)
			co2_values.insert(2,float(values_li7000[24])) # Temp
			co2_values.insert(3,float(values_li7000[21])) # Pressure
			#print(co2_values)
		except (ValueError,IndexError) as e:
			print("li7000 index failure")
			return None
		return co2_values

class LI820_Instrument(Instrument):
	def __init__(self, sn):
		self.name = 'LI820'
		self.v_type = 'CO2'
		self.serial_num = sn
		super(LI820_Instrument, self).__init__('/dev/cu.usbserial-' + self.serial_num, 9600)

	def get_values(self):
		co2_values = []
		ser = self.serial.readline()
		dt_object = datetime.now()
		self.dumpserial(ser, dt_object)
		time_str4 = dt_object.strftime('%H:%M:%S')
		time_now=int(time.time()*1000000000)
		try:
			values_li820 = re.split(r'[<>]', ser)
			#print(values_1820)
			co2_values.insert(0,float(values_li820[14])) # CO2 value
			co2_values.insert(1,dt_object)
			co2_values.insert(2,float(values_li820[6])) # Temp
			co2_values.insert(3,float(values_li820[10])) # Pressure

		except(ValueError,IndexError) as e:
			print("li820 index failure")
			return None
		return co2_values

class SBA5_Instrument(Instrument):
	def __init__(self, sn):
		self.name = 'SBA5'
		self.v_type = 'CO2'
		self.serial_num = sn
		super(SBA5_Instrument, self).__init__('/dev/cu.usbserial-' + self.serial_num, 19200)

	def get_values(self):
		co2_values = []
		ser = self.serial.readline()
		dt_object = datetime.now()
		self.dumpserial(ser, dt_object)
		time_str6 = dt_object.strftime('%H:%M:%S')
		values_sba5 = ser.split('\n')[0].split(' ')
		time_now=int(time.time()*1000000000)

		try:
			#print(values_sba5)
			#print(float(values_sba5[7]))
			co2_values.insert(0,float(values_sba5[3])) # CO2 value
			co2_values.insert(1,dt_object)# Time
			co2_values.insert(2,float(values_sba5[4])) # CO2 temp
			co2_values.insert(3,(float(values_sba5[7])/1000)) # CO2 pressure



		except (ValueError, IndexError) as e:
			print("sba5 index failure")
			return None
		return co2_values

class VCO2_Instrument(Instrument):
	def __init__(self, sn=''):
		self.name = 'Vaisala'
		self.v_type = 'CO2'
		self.serial_num = sn
		self.setup = True
		if self.serial_num:
			path = '/dev/cu.usbserial-' + self.serial_num
		else:
			path = '/dev/cu.usbserial'
		super(VCO2_Instrument, self).__init__(path, 19200)

	def get_values(self):
		if self.setup:
			self.serial.write("R\r\n")
			response=self.serial.readline()
			self.setup = False
		co2_values = []
		ser = self.serial.readline()
		dt_object = datetime.now()
		self.dumpserial(ser, dt_object)
		time_str8 = dt_object.strftime('%H:%M:%S')
		values_vco2 = ser.split('\n')[0].split('\t')
		time_now=int(time.time()*1000000000)

		try:
			#print(values_vco2)
			co2_values.insert(0,float(values_vco2[0])) # CO2
			co2_values.insert(1,dt_object) # time
			co2_values.insert(2,float(values_vco2[1])) # temp
			#co2_values.insert(3,float(999)) #pressure


		except (ValueError, IndexError) as e:
			print("vco2 index failure")
			return None
		return co2_values

class K30_Instrument(Instrument):
	def __init__(self, sn):
		self.name = 'K30'
		self.v_type = 'CO2'
		self.serial_num = sn
		self.serial = serial.Serial(port='/dev/cu.usbserial-' + self.serial_num, baudrate=9600, timeout=0.5)
		self.serial.flushInput()
		time.sleep(1)
		super(K30_Instrument, self).__init__(None, 9600)

	def get_values(self):
		co2_values = []
		self.serial.flushInput()
		self.serial.write("\xFE\x44\x00\x08\x02\x9F\x25")
		time.sleep(0.5)
		resp = self.serial.read(7)
		dt_object = datetime.now()
		self.dumpserial(resp, dt_object)
		time_str10 = dt_object.strftime('%H:%M:%S')
		time_now=int(time.time()*1000000000)
		high = ord(resp[3])
		low = ord(resp[4])
		co2 = (high*256) + low
		time.sleep(0.1)

		try:
			co2_values.insert(0, co2)
			co2_values.insert(1, dt_object)

		except Exception as e:
			print("k30 index failure")
			return None
		return co2_values


# NOX Instr
class UCB_Instrument(Instrument):
	def __init__(self, sn):
		self.name = 'UCB'
		self.v_type = 'NOX'
		self.serial_num = sn
		self.serial = serial.Serial(port='/dev/cu.usbserial-' + self.serial_num, baudrate=9600, timeout=1, bytesize=serial.SEVENBITS)
		super(UCB_Instrument, self).__init__(None, 9600)

	def get_values(self):
		nox_values = []
		self.serial.write(b'\x0201RD0\x03\x26')
		ser = self.serial.readline()
		dt_object = datetime.now()
		self.dumpserial(ser, dt_object)
		time_str10 = dt_object.strftime('%H:%M:%S')
		time_now=int(time.time()*1000000000)

		try:
			output_ucb = ser.decode('ascii')
			values_ucb = output_ucb.split('\n')[0].split(',')
			#print(values_ucb)
			nox_values.insert(0,float(values_ucb[1]))
			nox_values.insert(1,dt_object)

		except Exception as e:
			print("ucb index failure")
			return None
		return nox_values

class CAPS_Instrument(Instrument):
	def __init__(self, sn):
		self.name = 'CAPS'
		self.v_type = 'NOX'
		self.serial_num = sn
		super(CAPS_Instrument, self).__init__('/dev/cu.usbserial-' + self.serial_num, 9600)

	def get_values(self):
		nox_values = []
		ser =  self.serial.readline()
		dt_object = datetime.now()
		self.dumpserial(ser, dt_object)
		time_str9 = dt_object.strftime('%H:%M:%S')
		values_caps = ser.split('\n')[0].split(',')
		time_now=int(time.time()*1000000000)

		try:
			#print(values_caps)
			nox1 = float(values_caps[1])
			nox_values.insert(0,(nox1/1000))
			nox_values.insert(1,dt_object)

		except (ValueError, IndexError) as e:
			print("caps index failure")
			return None
		return nox_values

def main_wrapper(q):
	global filepath
	filepath = q.get()

	if not os.path.exists(os.path.dirname(filepath)):
            try:
                os.makedirs(os.path.dirname(filepath))
            except OSError as exc: # Guard against race condition
                if exc.errno != errno.EEXIST:
                    raise

	with open(filepath + 'rawraw_data.csv', mode='wb') as rawFile:
		rawData = csv.writer(rawFile, delimiter=',', quotechar='"', quoting=csv.QUOTE_MINIMAL)
		rawData.writerow(['Timestamp', 'Instr', 'S#', 'Message'])

	comport_dict = {
		'FTXP6UA4': AE33_Instrument,
		'FTXP9NHN': AE16_Instrument,
		'wchusbserial': ABCD_Instrument,
		# '142140': ABCD_Instrument,
		'FT0HCK2R': MA300_Instrument,
		'FTE4W8JS': LI7000_Instrument, 
		'FTXP9HEV': LI820_Instrument,
		'DN03Y92G': SBA5_Instrument,
		'Vaisala':VCO2_Instrument,
		'142340':VCO2_Instrument,
		'141110':VCO2_Instrument,
		'FTXP9VNO': UCB_Instrument, # CLD64 
		'FTXPC1N7': CAPS_Instrument,
		'AH06VSA4': K30_Instrument
		}

	# Setup signal handler to allow for exiting on Keyboard Interrupt (Ctrl +C)
	signal.signal(signal.SIGTERM, sig_handler)
	signal.signal(signal.SIGINT, sig_handler)

	comlist = serial.tools.list_ports.comports()
	comport_pattern = re.compile('\/dev\/cu\.usbserial(\-(.)*)?$')
	serial_comlist = []

	for element in comlist:
		if comport_pattern.match(element.device):
			try:
				sn = element.device.split('/dev/cu.usbserial-')[1]
				comport_dict[sn](sn)
			except KeyError, IndexError:
				if element.device == '/dev/cu.usbserial':
					comport_dict['Vaisala']()
		elif '/dev/cu.wchusbserial' in element.device:
			sn = element.device.split('/dev/cu.')[1]
			comport_dict['wchusbserial'](sn)

	print(('instruments', instruments))

	q.put(('instruments', instruments))

	processes = []
	for instr in instruments:
		p = Process(target=instr.run, args=(q,))
		p.start()
		processes.append(p)

	while not stop_requested:
		time.sleep(1)

	return

def main():
	comport_dict = {
		'FTXP6UA4': AE33_Instrument,
		'FTXP9NHN': AE16_Instrument,
		'wchusbserial': ABCD_Instrument,
		# '142140': ABCD_Instrument,
		'FT0HCK2R': MA300_Instrument,
		'FTE4W8JS': LI7000_Instrument, 
		'FTXP9HEV': LI820_Instrument,
		'DN03Y92G': SBA5_Instrument,
		'Vaisala':VCO2_Instrument,
		# '142340':VCO2_Instrument,
		'141110':VCO2_Instrument,
		'FTXP9VNO': UCB_Instrument, # CLD64 
		'FTXPC1N7': CAPS_Instrument,
		'AH06VSA4': K30_Instrument
		}

	# Setup signal handler to allow for exiting on Keyboard Interrupt (Ctrl +C)
	signal.signal(signal.SIGTERM, sig_handler)
	signal.signal(signal.SIGINT, sig_handler)

	comlist = serial.tools.list_ports.comports()
	comport_pattern = re.compile('\/dev\/cu\.usbserial(\-(.)*)?$')
	serial_comlist = []

	for element in comlist:
		if comport_pattern.match(element.device):
			try:
				sn = element.device.split('/dev/cu.usbserial-')[1]
				comport_dict[sn](sn)
			except KeyError, IndexError:
				if element.device == '/dev/cu.usbserial':
					comport_dict['Vaisala']()
		elif '/dev/cu.wchusbserial' in element.device:
			sn = element.device.split('/dev/cu.')[1]
			comport_dict['wchusbserial'](sn)

	print(('instruments', instruments))

	q = Queue()
	processes = []
	for instr in instruments:
		p = Process(target=instr.run, args=(q,))
		p.start()
		processes.append(p)

	while not stop_requested:
		time.sleep(1)

	return



if __name__ == "__main__":
	main()