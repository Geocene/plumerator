#!/usr/bin/env python
# -*- coding: UTF-8 -*-
 
import wx
import wx.lib.plot as plot
import wx.lib.newevent
from multiprocessing import Process,Queue,Pipe
import os
import errno
import sys
import co2 as c
import nox as n
import bc as b
import data_ac as d_ac
import reup_raw as re_r
from datetime import datetime, timedelta
import operator
import signal
import numpy as np
import csv
import collections
import time
import math
import hashlib

import matplotlib
matplotlib.use('WXAgg')
from matplotlib.backends.backend_wxagg import FigureCanvasWxAgg as FigureCanvas
from matplotlib.backends.backend_wx import NavigationToolbar2Wx
from matplotlib.figure import Figure
from matplotlib.widgets import Button
import matplotlib.pyplot as plt
import matplotlib.gridspec as gridspec
from scipy.interpolate import InterpolatedUnivariateSpline

stop_requested = False
output_dir = '/csv_outputs/'
hash = hashlib.sha1()
hash.update(str(time.time()))
time_hash = hash.hexdigest()[:10] + '/'
filepath = os.getcwd() + output_dir + time_hash

class ComplexPlot(wx.Frame):
    def __init__(self, queue, instruments=None, mode=None):
        wx.Frame.__init__(self, None, wx.ID_ANY, title='Plotter', size=(500, 750))
        self.panel = CanvasPanel(self, queue, instruments, mode)

        sizer = wx.BoxSizer(wx.VERTICAL)
        sizer.Add(self.panel,1,wx.EXPAND)
        self.SetSizer(sizer)
        self.Layout()
        self.Show(True)

class CanvasPanel(wx.Panel):
    def __init__(self, parent, queue, instruments, mode):
        # set mode - 'i' = Instrument, 'r' = Reupload, 't' = Test
        self.mode = mode

        self.instruments = instruments[1]
        self.co2_instr = [x for x in self.instruments if x.v_type == 'CO2']
        self.bc_instr = [x for x in self.instruments if x.v_type == 'BC']
        self.nox_instr = [x for x in self.instruments if x.v_type == 'NOX']
        self.co2_chans = len(self.co2_instr)
        self.bc_chans = len(self.bc_instr)
        self.nox_chans = len(self.nox_instr)

        self.co2_chan_names = {}
        self.bc_chan_names = {}
        self.nox_chan_names = {}
        self.co2_temp = 0
        self.nox_temp = 0
        self.bc_temp = 0

        # set channel_units
        self.chan_units = {'CO2':'ppm', 'NOX':'ppm', 'BC':'µg/m3'}

        # set neighbor threshold and slope threshold
        self.neighbor_threshold = 50
        self.slope_threshold = 50

        # set plume counter
        self.plume_counter = 1

        # create and write headers of output files
        self.filepath = filepath

        if not os.path.exists(os.path.dirname(self.filepath)):
            try:
                os.makedirs(os.path.dirname(self.filepath))
            except OSError as exc: # Guard against race condition
                if exc.errno != errno.EEXIST:
                    raise

        self.plotfile = self.filepath + 'raw_data.csv'
        self.plumefile = self.filepath + 'plume_events.csv'
        self.plumeArea = self.filepath + 'plumes.csv'
        self.summaryfile = self.filepath + 'secondly_data.csv'
        self.instrumentfile = self.filepath + 'instruments.csv'
        with open(self.plotfile, mode='wb') as plotFile:
            self.plotData = csv.writer(plotFile, delimiter=',', quotechar='"', quoting=csv.QUOTE_MINIMAL)
            self.plotData.writerow(['Timestamp', 'Instr ID', 'Channel', 'Value'])
        with open(self.plumefile, mode='wb') as plumeFile:
            self.plumeData = csv.writer(plumeFile, delimiter=',', quotechar='"', quoting=csv.QUOTE_MINIMAL)
            self.plumeData.writerow(['plume_raw_start_time', 'plume_raw_stop_time', 'plume_event_id', 'detector_instrument_id', 'detector_instrument_model'])
        with open(self.plumeArea, mode='wb') as plumeArea:
            self.plumeAreas = csv.writer(plumeArea, delimiter=',', quotechar='"', quoting=csv.QUOTE_MINIMAL)
            self.plumeAreas.writerow(['plume_event_id', 'instrument_id', 'instrument_model', 'channel_species', 'channel_units', 'pip_pre', 'pip_post', 'plume_start_time', 'plume_stop_time', 'baseline_pre', 'baseline_post', 'baseline_area', 'plume_total_area', 'plume_area', 'emission_factor'])
        self.setSummary = True

        # timing test
        with open('timing.csv', mode='wb') as timingFile:
            timeData = csv.writer(timingFile, delimiter=',', quotechar='"', quoting=csv.QUOTE_MINIMAL)
            timeData.writerow(['Drawcycle', 'Update Data', 'Cleanup', 'Update Ambient', 'Get Updates', 'Analyze', 'Write Summary', 'Plotting', 'Histograms', 'Plumes'])

        wx.Panel.__init__(self, parent)

        # setup plot selection
        co2_plots = [x.name for x in self.co2_instr]
        nox_plots = [x.name for x in self.nox_instr]
        bc_plots = [x.name for x in self.bc_instr]

        for i in co2_plots:
            self.co2_chan_names[i] = self.co2_temp
            self.co2_temp += 1
        for i in nox_plots:
            self.nox_chan_names[i] = self.nox_temp
            self.nox_temp += 1
        for i in bc_plots:
            self.bc_chan_names[i] = self.bc_temp
            self.bc_temp += 1

        # set primary co2 instrument
        self.primary_co2instr = self.getIdByName('LI7000', 'CO2')

        with open(self.instrumentfile, mode='wb') as instrFile:
            self.instrumentWriter = csv.writer(instrFile, delimiter=',', quotechar='"', quoting=csv.QUOTE_MINIMAL)
            self.instrumentWriter.writerow(['Instr ID', 'Channel'])
            for i in co2_plots:
                self.instrumentWriter.writerow([i, 'CO2'])
            for i in nox_plots:
                self.instrumentWriter.writerow([i, 'NOX'])
            for i in bc_plots:
                self.instrumentWriter.writerow([i, 'BC'])

        if co2_plots:
            self.selected_co2_plot = co2_plots[0]
        else:
            self.selected_co2_plot = None
        if nox_plots:
            self.selected_nox_plot = nox_plots[0]
        else:
            self.selected_nox_plot = None
        if bc_plots:
            self.selected_bc_plot = bc_plots[0]
        else:
            self.selected_bc_plot = None

        self.menuBar = wx.MenuBar()
        self.co2_menu = wx.Menu()
        self.co2_menu_items = []
        for i in co2_plots:
            item = self.co2_menu.Append(wx.ID_ANY, i.replace('.csv', ''), "", wx.ITEM_RADIO)
            parent.Bind(wx.EVT_MENU, self.co2_select, item)
            self.co2_menu_items.append(item)
        self.nox_menu = wx.Menu()
        self.nox_menu_items = []
        for i in nox_plots:
            item = self.nox_menu.Append(wx.ID_ANY, i.replace('.csv', ''), "", wx.ITEM_RADIO)
            parent.Bind(wx.EVT_MENU, self.nox_select, item)
            self.nox_menu_items.append(item)
        self.bc_menu = wx.Menu()
        self.bc_menu_items = []
        for i in bc_plots:
            item = self.bc_menu.Append(wx.ID_ANY, i.replace('.csv', ''), "", wx.ITEM_RADIO)
            parent.Bind(wx.EVT_MENU, self.bc_select, item)
            self.bc_menu_items.append(item)
        self.menuBar.Append(self.co2_menu, "CO2 Plot")
        self.menuBar.Append(self.nox_menu, "NOX Plot")
        self.menuBar.Append(self.bc_menu, "BC Plot")

        # Settings bar - change PIP and set output dir name
        self.settings_menu = wx.Menu()
        set_pip = self.settings_menu.Append(wx.ID_ANY, 'Set PIP', "")
        parent.Bind(wx.EVT_MENU, self.set_pip, set_pip)
        self.settings_menu_items = [set_pip]

        self.menuBar.Append(self.settings_menu, "Settings")

        
        parent.SetMenuBar(self.menuBar)

        # plotting data structures
        self.queue = queue
        self.co2_data = []
        self.nox_data = []
        self.bc_data = []
        self.co2_ambient = {}
        self.nox_ambient = {}
        self.bc_ambient = {}
        for i in range(self.co2_chans):
            self.co2_ambient[i] = []
        for i in range(self.nox_chans):
            self.nox_ambient[i] = []
        for i in range(self.bc_chans):
            self.bc_ambient[i] = []
        self.figure = Figure(constrained_layout=False)
        self.gridspec = gridspec.GridSpec(ncols=2, nrows=3, width_ratios=[2, 1], figure=self.figure)

        # analysis data structures
        self.ts_aligned_dps = collections.OrderedDict()
        # self.plumes = []
        # self.plume_markers = [None, None]

        # histograms
        self.nox_histogram = {}
        for i in range(self.nox_chans):
            self.nox_histogram[i] = []
        self.bc_histogram = {}
        for i in range(self.bc_chans):
            self.bc_histogram[i] = []
        self.replot_hists = False

        # time correction
        self.pip = {'CO2':{},'NOX':{},'BC':{}}
        for i in range(self.co2_chans):
            self.pip['CO2'][i] = {'start_lag':None, 'stop_lag':None}
        for i in range(self.nox_chans):
            self.pip['NOX'][i] = {'start_lag':None, 'stop_lag':None}
        for i in range(self.bc_chans):
            self.pip['BC'][i] = {'start_lag':None, 'stop_lag':None}

        # setup with default pip values
        self.set_pip_by_chan('BC', 'ABCD', 4, 9)
        self.set_pip_by_chan('BC', 'AE16', 1, 0)
        self.set_pip_by_chan('BC', 'AE33', 1, 8)
        self.set_pip_by_chan('BC', 'MA300', 4, 25)
        self.set_pip_by_chan('CO2', 'K30', 0, 6)
        self.set_pip_by_chan('CO2', 'LI7000', 0, 0)
        self.set_pip_by_chan('CO2', 'LI820', 1, -1)
        self.set_pip_by_chan('CO2', 'Vaisala', 6, 25)
        self.set_pip_by_chan('NOX', 'CAPS', 2, 2)
        self.set_pip_by_chan('NOX', 'UCB', 2, 0)
        # factor out - just for testing
        self.set_pip_by_chan('NOX', 'CLD64', 2, 0)
        self.set_pip_by_chan('CO2', 'SBA5', 0, 0)

        self.co2_axes = self.figure.add_subplot(self.gridspec[0, 0])
        self.reset_data(self.co2_axes, 'CO2')

        self.nox_axes = self.figure.add_subplot(self.gridspec[1, 0])
        self.reset_data(self.nox_axes, 'NOX')

        self.bc_axes = self.figure.add_subplot(self.gridspec[2, 0])
        self.reset_data(self.bc_axes, 'BC')

        self.nox_histogram_axes = self.figure.add_subplot(self.gridspec[1, 1])
        self.nox_histogram_axes.set_ylabel('Observations')
        self.nox_histogram_axes.set_xlabel('ppm (NOX) / ppm (CO2)')
        self.bc_histogram_axes = self.figure.add_subplot(self.gridspec[2, 1])
        self.bc_histogram_axes.set_ylabel('Observations')
        self.bc_histogram_axes.set_xlabel(r'$\mu g/m^3$ (BC) / ppm (CO2)')

        self.figure.subplots_adjust(hspace=0.5)
        self.canvas = FigureCanvas(self, -1, self.figure)

        # self.co2button_ax = self.figure.add_axes([0.61, 0.90, 0.025, 0.025])
        # self.co2_button = Button(self.co2button_ax, 'Edit')
        # self.co2_button.on_clicked(self.update_ambient_co2)

        # self.noxbutton_ax = self.figure.add_axes([0.61, 0.61, 0.025, 0.025])
        # self.nox_button = Button(self.noxbutton_ax, 'Edit')
        # self.nox_button.on_clicked(self.update_ambient_nox)

        # self.bcbutton_ax = self.figure.add_axes([0.61, 0.32, 0.025, 0.025])
        # self.bc_button = Button(self.bcbutton_ax, 'Edit')
        # self.bc_button.on_clicked(self.update_ambient_bc)

        self.sizer = wx.BoxSizer(wx.VERTICAL)
        self.sizer.Add(self.canvas, 1, wx.LEFT | wx.TOP | wx.GROW | wx.EXPAND )
        self.SetSizer(self.sizer)
        self.Fit()
        self.Layout()
        parent.Maximize(True)

        # setup redraw timer
        self.ambient_cs = 5
        self.timer = wx.Timer(self)
        self.Bind(wx.EVT_TIMER, self.drawEvent, self.timer)
        time.sleep(5)
        self.timer.Start(200)
        self.Show(True)

    def draw(self):

        drawCycle = time.time()
        row = [drawCycle]

        self.update_data()

        updateData = time.time()
        row.append(updateData - drawCycle)

        if self.setSummary:
            self.setupSummary()
            self.setSummary = False

        current_time = datetime.now()
        
        self.co2_data.sort(key=operator.itemgetter(0))
        self.nox_data.sort(key=operator.itemgetter(0))
        self.bc_data.sort(key=operator.itemgetter(0))

        # cleanup old data
        self.co2_data = [x for x in self.co2_data if (current_time - x[0]).total_seconds() <= 180]
        self.nox_data = [x for x in self.nox_data if (current_time - x[0]).total_seconds() <= 180]
        self.bc_data = [x for x in self.bc_data if (current_time - x[0]).total_seconds() <= 180]
            
        for i in range(self.co2_chans):
            self.co2_ambient[i] = [x for x in self.co2_ambient[i] if (current_time - x[0]).total_seconds() <= 180]
        for i in range(self.nox_chans):
            self.nox_ambient[i] = [x for x in self.nox_ambient[i] if (current_time - x[0]).total_seconds() <= 180]
        for i in range(self.bc_chans):
            self.bc_ambient[i] = [x for x in self.bc_ambient[i] if (current_time - x[0]).total_seconds() <= 180]

        cleanupData = time.time()
        row.append(cleanupData - updateData)


        # current plotted data
        self.co2_updates = {}
        self.nox_updates = {}
        self.bc_updates = {}
        for x in self.co2_data:
            dp = [(current_time - x[0]).total_seconds(), x[1], x[0]]
            if x[2] in self.co2_updates:
                self.co2_updates[x[2]].append(dp)
            else:
                self.co2_updates[x[2]] = []
                self.co2_updates[x[2]].append(dp)
        for x in self.bc_data:
            dp = [(current_time - x[0]).total_seconds(), x[1], x[0]]
            if x[2] in self.bc_updates:
                self.bc_updates[x[2]].append(dp)
            else:
                self.bc_updates[x[2]] = []
                self.bc_updates[x[2]].append(dp)
        for x in self.nox_data:
            dp = [(current_time - x[0]).total_seconds(), x[1], x[0]]
            if x[2] in self.nox_updates:
                self.nox_updates[x[2]].append(dp)
            else:
                self.nox_updates[x[2]] = []
                self.nox_updates[x[2]].append(dp)

        getUpdate = time.time()
        row.append(getUpdate - cleanupData)

        self.reset_data(self.co2_axes, 'CO2')
        self.reset_data(self.nox_axes, 'NOX')
        self.reset_data(self.bc_axes, 'BC')

        # self.ambient_cs -= 1
        # if self.ambient_cs == 0:
        #     self.update_ambient()
        #     self.ambient_cs = 5

        update_am = time.time()
        row.append(update_am - getUpdate)

        # plume analysis and summary write
        self.analyze(current_time)
        analyze = time.time()
        row.append(analyze - update_am)
        self.write_ts(current_time)
        write_summ = time.time()
        row.append(write_summ - analyze)

        
        # get updates
        if self.selected_co2_plot:
            selected_co2_id = self.getIdByName(self.selected_co2_plot, 'CO2')
            try:
                co2_update = zip(*self.co2_updates[selected_co2_id])
            except KeyError:
                co2_update = None
        else:
            co2_update = None
        if self.selected_nox_plot:
            selected_nox_id = self.getIdByName(self.selected_nox_plot, 'NOX')
            try:
                nox_update = zip(*self.nox_updates[selected_nox_id])
            except KeyError:
                nox_update = None
        else:
            nox_update = None
        if self.selected_bc_plot:
            selected_bc_id = self.getIdByName(self.selected_bc_plot, 'BC')
            try:
                bc_update = zip(*self.bc_updates[selected_bc_id])
            except KeyError:
                bc_update = None
        else:
            bc_update = None
        
        # plot updates
        if co2_update:
            self.co2_axes.plot(co2_update[0], co2_update[1], c='r', linewidth=1.0)
            # if self.co2_ambient[selected_co2_id]:
            #     co2_ambient_line = zip(*[[(current_time - x[0]).total_seconds(), x[1]] for x in self.co2_ambient[selected_co2_id] if (current_time - x[0]).total_seconds() <= 180])
            #     self.co2_axes.plot(co2_ambient_line[0], co2_ambient_line[1], c='b', linewidth=1.5, linestyle='--')
        if bc_update:
            self.bc_axes.plot(bc_update[0], bc_update[1], c='r', linewidth=1.0)
            # if self.bc_ambient[selected_bc_id]:
            #     bc_ambient_line = zip(*[[(current_time - x[0]).total_seconds(), x[1]] for x in self.bc_ambient[selected_bc_id] if (current_time - x[0]).total_seconds() <= 180])
            #     self.bc_axes.plot(bc_ambient_line[0], bc_ambient_line[1], c='b', linewidth=1.5, linestyle='--')
        if nox_update:
            self.nox_axes.plot(nox_update[0], nox_update[1], c='r', linewidth=1.0)
            # if self.nox_ambient[selected_nox_id]:
            #     nox_ambient_line = zip(*[[(current_time - x[0]).total_seconds(), x[1]] for x in self.nox_ambient[selected_nox_id] if (current_time - x[0]).total_seconds() <= 180])
            #     self.nox_axes.plot(nox_ambient_line[0], nox_ambient_line[1], c='b', linewidth=1.5, linestyle='--')

        plotting = time.time()
        row.append(plotting - write_summ)

        if self.replot_hists:
            self.nox_histogram_axes.hist(self.nox_histogram[selected_nox_id], bins=8, color="skyblue")
            self.bc_histogram_axes.hist(self.bc_histogram[selected_bc_id], bins=8, color="skyblue")
            self.replot_hists = False

        histogram = time.time()
        row.append(histogram - plotting)


        # fill plumes
        # for plume in self.plumes:
        #     plume = [(current_time - x).total_seconds() for x in plume]
        #     # self.co2_axes.fill_between(co2_ambient_line[0], co2_ambient_line[1], co2_ambient_line[2], 
        #     #     where=co2_ambient_line[0] <= plume[0] and co2_ambient_line[0] >= plume[1], facecolor='green', interpolate=True)

        plumeage = time.time()
        row.append(plumeage - histogram)

        with open('timing.csv', mode='ab') as timingFile:
            timeData = csv.writer(timingFile, delimiter=',', quotechar='"', quoting=csv.QUOTE_MINIMAL)
            timeData.writerow(row)
            
        # if self.selected_co2_plot and self.co2_ambient[selected_co2_id]:
        #     self.co2_axes.text(60, 1650, "Ambient CO2 (ppm): {:.2f}".format(self.co2_ambient[selected_co2_id][0][1]), fontsize=11, bbox={'facecolor': 'red', 'alpha': 0.5, 'pad': 6})
        # if self.selected_nox_plot and self.nox_ambient[selected_nox_id]:
        #     self.nox_axes.text(60, 28, "Ambient NOX (ppb): {:.2f}".format(self.nox_ambient[selected_nox_id][0][1]), fontsize=11, bbox={'facecolor': 'red', 'alpha': 0.5, 'pad': 6})
        # if self.selected_bc_plot and self.bc_ambient[selected_bc_id]:
        #     self.bc_axes.text(60, 28, r"Ambient BC ($\mu g/m^3$): {:.2f}".format(self.bc_ambient[selected_bc_id][0][1]), fontsize=11, bbox={'facecolor': 'red', 'alpha': 0.5, 'pad': 4})
        self.Show(True)
        self.canvas.draw()
        self.canvas.flush_events()

    def analyze(self, current_time):
        to_analyze = []
        for k, v in self.ts_aligned_dps.items():
            if (k - timedelta(seconds=30)) > self.first_dt_second:
                diff = (current_time - k).total_seconds()
                if diff >= 185:
                    del self.ts_aligned_dps[k]
                # plume analyze
                if int(diff) == 45:
                    if v['plume'] == True and v['analyzed'] == False and self.ts_aligned_dps[k + timedelta(seconds=1)]['plume'] == False:
                        v['analyzed'] = True
                        print('found plume ending at {}'.format(k))
                        self.plume_calc(k, current_time)
                # deblipping
                if diff >= 35 and v['blip'] == False:
                    self.ts_aligned_dps[k]['blip'] = True
                    if v['plume'] == True:
                        if self.ts_aligned_dps[k + timedelta(seconds=1)]['plume'] == False and self.ts_aligned_dps[k - timedelta(seconds=1)]['plume'] == False:
                            self.ts_aligned_dps[k]['plume'] = False
                        elif self.ts_aligned_dps[k + timedelta(seconds=1)]['plume'] == False and self.ts_aligned_dps[k - timedelta(seconds=2)]['plume'] == False:
                            assert self.ts_aligned_dps[k - timedelta(seconds=1)]['plume'] == True
                            self.ts_aligned_dps[k]['plume'] = False
                            self.ts_aligned_dps[k - timedelta(seconds=1)]['blip'] = True
                            self.ts_aligned_dps[k - timedelta(seconds=1)]['plume'] = False
                        elif self.ts_aligned_dps[k - timedelta(seconds=1)]['plume'] == False and self.ts_aligned_dps[k + timedelta(seconds=2)]['plume'] == False:
                            assert self.ts_aligned_dps[k + timedelta(seconds=1)]['plume'] == True
                            self.ts_aligned_dps[k]['plume'] = False
                            self.ts_aligned_dps[k + timedelta(seconds=1)]['blip'] = True
                            self.ts_aligned_dps[k + timedelta(seconds=1)]['plume'] = False
                # initial guessing and calc
                if diff >= 30:
                    if v['plume'] == None:
                        co2_val = self.lvcf(k, 'CO2', self.primary_co2instr)
                        deriv = self.lvcf(k + timedelta(seconds=1), 'CO2', self.primary_co2instr) - co2_val
                        mean, sd, quan = self.calc_window(k)
                        # decision tree
                        if abs(deriv) > self.slope_threshold:
                            self.ts_aligned_dps[k]['plume'] = True
                            ret = True
                            method = 'deriv > slope_thres'
                        elif co2_val > (mean + (sd * 3)):
                            self.ts_aligned_dps[k]['plume'] = True
                            ret = True
                            method = 'co2_val > (mean + 3 * sd)'
                        elif (co2_val - quan) > self.neighbor_threshold:
                            self.ts_aligned_dps[k]['plume'] = True
                            ret = True
                            method = 'co2_val - quan > neighbor_thres'
                        else:
                            self.ts_aligned_dps[k]['plume'] = False
                            ret = False
                        # factor out - testing
                        print('guessing: {}'.format(ret))
                        if ret == True:
                            print('found by {}'.format(method))
                else:
                    break
            else:
                v['plume'] = False
            
            

        # to_analyze.sort(key=operator.itemgetter(0))
        # for k, v in to_analyze:
        #     co2_vals = v['CO2'][self.primary_co2instr]
        #     co2_value = self.average_list(co2_vals)
        #     if co2_value:
        #         if co2_value >= 750:
        #             v['plume'] = True
        #             self.ts_aligned_dps[k] = v
        #             if self.plume_markers[0] == None:
        #                 self.plume_markers[0] = k
        #         else:
        #             v['plume'] = False
        #             self.ts_aligned_dps[k] = v
        #             if self.plume_markers[0] != None:
        #                 self.plume_markers[1] = k
        #                 self.update_histogram(self.plume_markers)
        #                 self.write_plume(self.plume_markers)
        #                 self.plume_markers = [None, None]

    def plume_calc(self, stop_time, current_time):
        start_time, event_id = self.write_plume_event(stop_time)
        ts_dict = self.get_ts_dict(start_time, stop_time)
        master_co2_area = self.calc_plume(start_time, stop_time, self.primary_co2instr, 'CO2', event_id, current_time, ts_dict)

        for i in range(self.co2_chans):
            if i != self.primary_co2instr:
                self.calc_plume(start_time, stop_time, i, 'CO2', event_id, current_time, ts_dict, master_co2_area)
        for i in range(self.nox_chans):
            self.calc_plume(start_time, stop_time, i, 'NOX', event_id, current_time, ts_dict, master_co2_area)
        for i in range(self.bc_chans):
            self.calc_plume(start_time, stop_time, i, 'BC', event_id, current_time, ts_dict, master_co2_area)

    def calc_window(self, datetime):
        start_dt = datetime - timedelta(seconds=30)
        stop_dt = datetime + timedelta(seconds=30)
        mean_vals = []
        while start_dt != stop_dt:
            b = self.ts_aligned_dps[start_dt]['CO2'][self.primary_co2instr]
            if b:
                mean_vals.append(self.average_list(b))
            start_dt = start_dt + timedelta(seconds=1)
        mean_vals = sorted(mean_vals, key=float)
        quantile = mean_vals[2]
        mean = self.average_list(mean_vals)
        sq_diffs = [math.pow((x - mean), 2) for x in mean_vals]
        sd = self.average_list(sq_diffs)
        return mean, sd, quantile

    def lvcf(self, timestamp, chan, name):
        seconds = 1
        ret = None
        while ret is None:
            if timestamp in self.ts_aligned_dps:
                if self.ts_aligned_dps[timestamp][chan][name]:
                    ret = self.ts_aligned_dps[timestamp][chan][name]
            timestamp = timestamp - timedelta(seconds=seconds)
            seconds += 1
        return self.average_list(ret)

    def calc_plume(self, start_time, stop_time, chan_id, chan_spec, event_id, current_time, ts_dict, master_co2_area=None):
        plume_event_id = event_id
        instrument_model = self.getNameById(chan_id, chan_spec)
        instrument_id = self.getSerialbyName(instrument_model, chan_spec)
        channel_species = chan_spec
        channel_units = self.chan_units[channel_species]
        pip_pre = self.pip[channel_species][chan_id]['start_lag']
        pip_post = self.pip[channel_species][chan_id]['stop_lag']
        plume_start_time = start_time - timedelta(seconds=pip_pre)
        plume_stop_time = stop_time + timedelta(seconds=pip_post)
        baseline_pre = self.get_baseline_pre(plume_start_time, channel_species, chan_id)
        baseline_post = self.get_baseline_post(plume_stop_time, channel_species, chan_id)
        # use np.trapz to get baseline area and actual area
        area_x = [(current_time - x).total_seconds() for x in [plume_start_time, plume_stop_time]]
        area_y = [baseline_pre, baseline_post]
        area_x = area_x[::-1]
        area_y = area_y[::-1]
        baseline_area = np.trapz(area_y, x=area_x)
        plume_area_x, plume_area_y = self.get_plume_area(ts_dict, chan_spec, chan_id)
        plume_area_x = [(current_time - x).total_seconds() for x in plume_area_x]
        plume_area_x = plume_area_x[::-1]
        plume_area_y = plume_area_y[::-1]
        plume_total_area = np.trapz(plume_area_y, x=plume_area_x)
        plume_area = plume_total_area - baseline_area
        if master_co2_area is not None:
            if chan_spec == 'CO2':
                emission_factor = 3190.0 * (plume_area / master_co2_area)
            elif chan_spec == 'NOX':
                emission_factor = 3335.0 * (plume_area / master_co2_area)
            elif chan_spec == 'BC':
                emission_factor = 1.778 * (plume_area / master_co2_area)
        else:
            assert chan_spec == 'CO2' and chan_id == self.primary_co2instr
            emission_factor = 3190.0
        with open(self.plumeArea, mode='ab') as plumeArea:
            self.plumeAreas = csv.writer(plumeArea, delimiter=',', quotechar='"', quoting=csv.QUOTE_MINIMAL)
            self.plumeAreas.writerow([plume_event_id, instrument_id, instrument_model, channel_species, channel_units, pip_pre, pip_post, plume_start_time, plume_stop_time, baseline_pre, baseline_post, baseline_area, plume_total_area, plume_area, emission_factor])
        return plume_area

    def getIdByName(self, name, chan):
        if chan == 'CO2':
            for k, v in self.co2_chan_names.items():
                if k == name:
                    return v
        elif chan == 'NOX':
            for k, v in self.nox_chan_names.items():
                if k == name:
                    return v
        elif chan == 'BC':
            for k, v in self.bc_chan_names.items():
                if k == name:
                    return v
        return None

    def getNameById(self, ID, chan):
        if chan == 'CO2':
            for k, v in self.co2_chan_names.items():
                if v == ID:
                    return k
        elif chan == 'NOX':
            for k, v in self.nox_chan_names.items():
                if v == ID:
                    return k
        elif chan == 'BC':
            for k, v in self.bc_chan_names.items():
                if v == ID:
                    return k
        return None

    def getSerialbyName(self, name, chan):
        if chan == 'CO2':
            for instr in self.co2_instr:
                if instr.name == name and hasattr(instr, 'serial_num'):
                    return instr.serial_num
        elif chan == 'NOX':
            for instr in self.nox_instr:
                if instr.name == name and hasattr(instr, 'serial_num'):
                    return instr.serial_num
        elif chan == 'BC':
            for instr in self.nox_instr:
                if instr.name == name and hasattr(instr, 'serial_num'):
                    return instr.serial_num
        return None

    def get_plume_area(self, ts_dict, chan_spec, chan_id):
        plume_area_x = []
        plume_area_y = []
        for k, v in ts_dict.items():
            plume_area_x.append(k)
            plume_area_y.append(self.lvcf(k, chan_spec, chan_id))
        return plume_area_x, plume_area_y

    def get_ts_dict(self, start_time, stop_time):
        ret = collections.OrderedDict()
        print(start_time, stop_time)
        t = start_time
        while t != stop_time:
            ret[t] = self.ts_aligned_dps[t]
            t += timedelta(seconds=1)
        ret[t] = self.ts_aligned_dps[t]
        return ret

    def get_baseline_pre(self, start_time, chan, name_id):
        vals = []
        t1 = start_time - timedelta(seconds=1)
        t2 = start_time - timedelta(seconds=2)
        t3 = start_time - timedelta(seconds=3)
        vals.append(self.lvcf(t1, chan, name_id))
        vals.append(self.lvcf(t2, chan, name_id))
        vals.append(self.lvcf(t3, chan, name_id))
        return self.average_list(vals)

    def get_baseline_post(self, stop_time, chan, name_id):
        vals = []
        t1 = stop_time + timedelta(seconds=1)
        t2 = stop_time + timedelta(seconds=2)
        t3 = stop_time + timedelta(seconds=3)
        vals.append(self.lvcf(t1, chan, name_id))
        vals.append(self.lvcf(t2, chan, name_id))
        vals.append(self.lvcf(t3, chan, name_id))
        return self.average_list(vals)

    def write_plume_event(self, stop_time):
        s = 1
        start_time = None
        while start_time is None:
            t = stop_time - timedelta(seconds=s)
            if self.ts_aligned_dps[t]['plume'] == False:
                assert s >= 2
                start_time = t + timedelta(seconds=1)
            s += 1
        event_id = time.mktime(start_time.timetuple())
        detector_instr_model = self.getNameById(self.primary_co2instr, 'CO2')
        detector_instr_id = self.getSerialbyName(detector_instr_model, 'CO2')

        to_write = [start_time, stop_time, event_id, detector_instr_id, detector_instr_model]
        with open(self.plumefile, mode='ab') as plumeFile:
            writer = csv.writer(plumeFile, delimiter=',', quotechar='"', quoting=csv.QUOTE_MINIMAL)
            writer.writerow(to_write)

        return start_time, event_id

    def write_ts(self, current_time):
        csv_post = []
        for k, v in self.ts_aligned_dps.items():
            if (current_time - k).total_seconds() >= 5 and not v['written']:
                v['written'] = True
                self.ts_aligned_dps[k] = v
                post = [k]
                for i in range(self.co2_chans):
                    post.append(self.average_list(v['CO2'][i]))
                for i in range(self.nox_chans):
                    post.append(self.average_list(v['NOX'][i]))
                for i in range(self.bc_chans):
                    post.append(self.average_list(v['BC'][i]))
                csv_post.append(post)
        with open(self.summaryfile, mode='ab') as summaryFile:
                writer = csv.writer(summaryFile, delimiter=',', quotechar='"', quoting=csv.QUOTE_MINIMAL)
                writer.writerows(csv_post)

    def update_data(self):
        csv_post = []
        while not self.queue.empty():
            item = self.queue.get()
            csv_post.append([item[1][1], item[0][0], item[0][1], item[1][0]])
            if item[0][1] == 'CO2':
                self.co2_data.append([item[1][1], item[1][0], self.getIdByName(item[0][0], item[0][1])])
            elif item[0][1] == 'NOX':
                self.nox_data.append([item[1][1], item[1][0], self.getIdByName(item[0][0], item[0][1])])
            elif item[0][1] == 'BC':
                self.bc_data.append([item[1][1], item[1][0], self.getIdByName(item[0][0], item[0][1])])
            else:
                print('error bad send')
            self.align_ts(item, item[0][1])
        with open(self.plotfile, mode='ab') as plotFile:
            csv_post.sort(key=operator.itemgetter(0))
            writer = csv.writer(plotFile, delimiter=',', quotechar='"', quoting=csv.QUOTE_MINIMAL)
            writer.writerows(csv_post)

    # Input Structure:
    # (['AE33-1-BC-nan', 'BC'], [0.1895, datetime.datetime(2019, 10, 8, 11, 42, 26, 206925)])
    # Output structure:
    # {datetime.datetime(2019, 8, 5, 14, 37, 4): {'BC': {0: [0.98], 1: []},
    #                                     'CO2': {0: [668.39],
    #                                             1: [813.28573],
    #                                             2: [628.0],
    #                                             3: [873.1]},
    #                                     'NOX': {0: [], 1: []}, 'plume':None, 'written':False, 'blip':False}}
    def align_ts(self, dp, dp_type):
        old_dt = dp[1][1]
        floored_dt = self.floor_dt(old_dt)
        if floored_dt in self.ts_aligned_dps:
            self.ts_aligned_dps[floored_dt][dp_type][self.getIdByName(dp[0][0], dp[0][1])].append(dp[1][0])
        else:
            if len(self.ts_aligned_dps) == 0:
                self.first_dt_second = floored_dt
            co2_dict = {}
            nox_dict = {}
            bc_dict = {}
            for i in range(self.co2_chans):
                co2_dict[i] = []
            for i in range(self.nox_chans):
                nox_dict[i] = []
            for i in range(self.bc_chans):
                bc_dict[i] = []
            self.ts_aligned_dps[floored_dt] = {'CO2':co2_dict, 'BC':bc_dict, 'NOX':nox_dict, 'plume':None, 'written':False, 'blip':False, 'analyzed':False}
            self.ts_aligned_dps[floored_dt][dp_type][self.getIdByName(dp[0][0], dp[0][1])].append(dp[1][0])

    def reset_data(self, plot, name):
        plot.clear()
        plot.set_xlim([120, 0])
        plot.xaxis.set_ticks(np.arange(0, 210, 30))
        if name == 'CO2':
            plot.set_ylim([-100, 2000])
            plot.set_title('CO2')
            plot.set_ylabel('ppm')
        elif name == 'NOX':
            plot.set_ylim([-5, 5])
            plot.set_title('NOX')
            plot.set_ylabel('ppm')
        elif name == 'BC':
            plot.set_ylim([-5, 100])
            plot.set_title('BC')
            plot.set_ylabel(r'$\mu g/m^3$')
            plot.set_xlabel('seconds ago')
        plot.tick_params(axis='y', left=True, right=True, labelright=True)

    def correct_ts(self, timestamps, chan, instr_id):
        start_lag = self.pip[chan][instr_id]['start_lag']
        stop_lag = self.pip[chan][instr_id]['stop_lag']
        return [timestamps[0] - start_lag, timestamps[1] + stop_lag]

    def average_list(self, lst):
        if lst:
            return sum(lst) / len(lst)
        else:
            return None

    def drawEvent(self, event):
        self.draw()

    def set_pip(self, event):
        dlg = wx.TextEntryDialog(self, 'Enter new pip values:',"Edit PIP","", 
                style=wx.OK)
        dlg.ShowModal()
        value = float(dlg.GetValue())
        dlg.Destroy()

    def setupSummary(self):
        with open(self.summaryfile, mode='wb') as summaryFile:
            self.summary = csv.writer(summaryFile, delimiter=',', quotechar='"', quoting=csv.QUOTE_MINIMAL)
            header = ['Timestamp']
            co2_names = dict((v,k) for k,v in self.co2_chan_names.iteritems())
            nox_names = dict((v,k) for k,v in self.nox_chan_names.iteritems())
            bc_names = dict((v,k) for k,v in self.bc_chan_names.iteritems())
            for i in range(self.co2_chans):
                header.append(co2_names[i])
            for i in range(self.nox_chans):
                header.append(nox_names[i])
            for i in range(self.bc_chans):
                header.append(bc_names[i])
            self.summary.writerow(header)

    def set_pip_by_chan(self, chan, name, start_lag, stop_lag):
        if chan == 'CO2':
            try:
                name_id = self.co2_chan_names[name]
            except KeyError:
                return
        elif chan == 'NOX':
            try:
                name_id = self.nox_chan_names[name]
            except KeyError:
                return
        elif chan == 'BC':
            try:
                name_id = self.bc_chan_names[name]
            except KeyError:
                return
        self.pip[chan][name_id]['start_lag'] = start_lag
        self.pip[chan][name_id]['stop_lag'] = stop_lag

    def co2_select(self, event):
        for i in self.co2_menu_items:
            if i.IsChecked():
                self.selected_co2_plot = i.GetName()

    def nox_select(self, event):
        for i in self.nox_menu_items:
            if i.IsChecked():
                self.selected_nox_plot = i.GetName()

    def bc_select(self, event):
        for i in self.bc_menu_items:
            if i.IsChecked():
                self.selected_bc_plot = i.GetName()

    def floor_dt(self, dt):
        return datetime(dt.year, dt.month, dt.day, dt.hour, dt.minute, dt.second)

    # def update_histogram(self, plume_markers):
    #     current_time = datetime.now()
    #     areas_post = []

    #     plume_markers = [plume_markers[0], plume_markers[1] + timedelta(seconds=1)]

    #     co2_plot = zip(*[x for x in self.co2_updates[self.primary_co2instr] if plume_markers[0] <= x[2] <= plume_markers[1]])
    #     co2_plot = [x[::-1] for x in co2_plot]
    #     co2am_plot = zip(*[[(current_time - x[0]).total_seconds(), x[1]] for x in self.co2_ambient[self.primary_co2instr] if plume_markers[0] <= x[0] <= plume_markers[1]])
    #     co2am_plot = [x[::-1] for x in co2am_plot]
    #     if not co2am_plot:
    #         print(self.co2_ambient[self.primary_co2instr])
    #         print(plume_markers)
    #     co2_area = np.trapz(co2_plot[1], x=co2_plot[0])
    #     co2am_area = np.trapz(co2am_plot[1], x=co2am_plot[0])
    #     co2_calc_area = co2_area - co2am_area
    #     areas_post.append([self.plume_counter, self.co2_chan_names[self.primary_co2instr], co2_calc_area, 'ppm-co2-s'])

    #     for i in range(self.nox_chans):
    #         nox_plot = zip(*[x for x in self.nox_updates[i] if plume_markers[0] <= x[2] <= plume_markers[1]])
    #         nox_plot = [x[::-1] for x in nox_plot]
    #         noxam_plot = zip(*[[(current_time - x[0]).total_seconds(), x[1]] for x in self.nox_ambient[i] if plume_markers[0] <= x[0] <= plume_markers[1]])
    #         noxam_plot = [x[::-1] for x in noxam_plot]
    #         if nox_plot:
    #             nox_area = np.trapz(nox_plot[1], x=nox_plot[0])
    #         else:
    #             nox_area = 0
    #         if noxam_plot:
    #             noxam_area = np.trapz(noxam_plot[1], x=noxam_plot[0])
    #         else:
    #             noxam_area = 0
    #         nox_calc_area = nox_area - noxam_area
    #         areas_post.append([self.plume_counter, self.nox_chan_names[i], nox_calc_area, 'ppm-nox-s'])
    #         nox_histogram_val = nox_calc_area / co2_calc_area
    #         self.nox_histogram[i].append(nox_histogram_val)

    #     for i in range(self.bc_chans):
    #         bc_plot = zip(*[x for x in self.bc_updates[i] if plume_markers[0] <= x[2] <= plume_markers[1]])
    #         bc_plot = [x[::-1] for x in bc_plot]
    #         bcam_plot = zip(*[[(current_time - x[0]).total_seconds(), x[1]] for x in self.bc_ambient[i] if plume_markers[0] <= x[0] <= plume_markers[1]])
    #         bcam_plot = [x[::-1] for x in bcam_plot]
    #         if bc_plot:
    #             bc_area = np.trapz(bc_plot[1], x=bc_plot[0])
    #         else:
    #             bc_area = 0
    #         if bcam_plot:
    #             bcam_area = np.trapz(bcam_plot[1], x=bcam_plot[0])
    #         else:
    #             bcam_area = 0
    #         bc_calc_area = bc_area - bcam_area
    #         areas_post.append([self.plume_counter, self.bc_chan_names[i], bc_calc_area, 'μg/m³-bc-s'])
    #         bc_histogram_val = bc_calc_area / co2_calc_area
    #         self.bc_histogram[i].append(bc_histogram_val)

    #     with open(self.plumeArea, mode='ab') as plumeAreas:
    #         writer = csv.writer(plumeAreas, delimiter=',', quotechar='"', quoting=csv.QUOTE_MINIMAL)
    #         writer.writerows(areas_post)

    #     self.replot_hists = True

    # def update_ambient(self):
    #     current_time = datetime.datetime.now()
    #     ambient_time = current_time - datetime.timedelta(seconds=90)
    #     co2_amvals, bc_amvals, nox_amvals = {}, {}, {}
    #     for i in range(self.co2_chans):
    #         co2_amvals[i] = []
    #     for i in range(self.bc_chans):
    #         bc_amvals[i] = []
    #     for i in range(self.nox_chans):
    #         nox_amvals[i] = []
    #     for k, v in self.ts_aligned_dps.items():
    #         if (current_time - k).total_seconds() >= 90 and (current_time - k).total_seconds() <= 180:
    #             if v['plume'] == False:
    #                 for i in range(self.co2_chans):
    #                     co2_amvals[i].extend(v['CO2'][i])
    #                 for i in range(self.bc_chans):
    #                     bc_amvals[i].extend(v['BC'][i])
    #                 for i in range(self.nox_chans):
    #                     nox_amvals[i].extend(v['NOX'][i])
    #     rows = []
    #     for i in range(self.co2_chans):
    #         if co2_amvals[i]:
    #             am_value = self.average_list(co2_amvals[i])
    #             rows.append([ambient_time, i, 'CO2_ambient', am_value])
    #             self.co2_ambient[i].append([ambient_time, am_value])
    #     for i in range(self.bc_chans):
    #         if bc_amvals[i]:
    #             am_value = self.average_list(bc_amvals[i])
    #             rows.append([ambient_time, i, 'BC_ambient', am_value])
    #             self.bc_ambient[i].append([ambient_time, am_value])
    #     for i in range(self.nox_chans):
    #         if nox_amvals[i]:
    #             am_value = self.average_list(nox_amvals[i])
    #             rows.append([ambient_time, i, 'NOX_ambient', am_value])
    #             self.nox_ambient[i].append([ambient_time, am_value])
    #     with open(self.plotfile, mode='ab') as plotFile:
    #         writer = csv.writer(plotFile, delimiter=',', quotechar='"', quoting=csv.QUOTE_MINIMAL)
    #         writer.writerows(rows)

    # def write_plume(self, timestamps):
    #     self.plumes.append(timestamps)
    #     with open(self.plumefile, mode='ab') as plumeFile:
    #         writer = csv.writer(plumeFile, delimiter=',', quotechar='"', quoting=csv.QUOTE_MINIMAL)
    #         for i in range(self.co2_chans):
    #             if i != self.primary_co2instr:
    #                 timestamps = self.correct_ts(timestamps, 'CO2', i)
    #             writer.writerow([self.co2_chan_names[i], self.plume_counter, timestamps[0], timestamps[1]])
    #         for i in range(self.nox_chans):
    #             timestamps = self.correct_ts(timestamps, 'NOX', i)
    #             writer.writerow([self.nox_chan_names[i], self.plume_counter, timestamps[0], timestamps[1]])
    #         for i in range(self.bc_chans):
    #             timestamps = self.correct_ts(timestamps, 'BC', i)
    #             writer.writerow([self.bc_chan_names[i], self.plume_counter, timestamps[0], timestamps[1]])
    #     self.plume_counter += 1

    # need to update how this is handled, self.co2am_vals is depricated, ambient is calculated using self.ts_aligned_dps
    # def update_ambient_co2(self, event):
    #     dlg = wx.TextEntryDialog(self, 'Enter new ambient value (ppm):',"Edit CO2 Ambient","", 
    #             style=wx.OK)
    #     dlg.ShowModal()
    #     selected_co2_id = self.getIdByName(self.selected_co2_plot, 'CO2')
    #     value = float(dlg.GetValue())
    #     if self.co2_ambient[selected_co2_id]:
    #         self.co2_ambient[selected_co2_id].append([datetime.datetime.now() - datetime.timedelta(seconds=90), value])
    #     dlg.Destroy()

    # def update_ambient_nox(self, event):
    #     dlg = wx.TextEntryDialog(self, 'Enter new ambient value (ppb):',"Edit NOX Ambient","", 
    #             style=wx.OK)
    #     dlg.ShowModal()
    #     selected_nox_id = self.getIdByName(self.selected_nox_plot, 'NOX')
    #     value = float(dlg.GetValue())
    #     if self.nox_ambient[selected_nox_id]:
    #         self.nox_ambient[selected_nox_id].append([datetime.datetime.now() - datetime.timedelta(seconds=90), value])
    #     dlg.Destroy()

    # def update_ambient_bc(self, event):
    #     dlg = wx.TextEntryDialog(self, 'Enter new ambient value (μg/m³):',"Edit BC Ambient","", 
    #             style=wx.OK)
    #     dlg.ShowModal()
    #     selected_bc_id = self.getIdByName(self.selected_bc_plot, 'BC')
    #     value = float(dlg.GetValue())
    #     if self.bc_ambient[selected_bc_id]:
    #         self.bc_ambient[selected_bc_id].append([datetime.datetime.now() - datetime.timedelta(seconds=90), value])
    #     dlg.Destroy()

q = Queue()


def sig_handler(signum, frame):
    sys.stdout.write("handling signal: %s\n" % signum)
    sys.stdout.flush()

    global stop_requested
    stop_requested = True

def main(instr, reupload):
    # Setup signal handler to allow for exiting on Keyboard Interrupt (Ctrl +C)
    signal.signal(signal.SIGTERM, sig_handler)
    signal.signal(signal.SIGINT, sig_handler)

    app = wx.App()

    if instr:
        mode = 'i'
        q.put(filepath)
        data_ac = Process(target=d_ac.main_wrapper, args=(q,))
        data_ac.start()

        # Get instr dict from data_ac.py by queue before starting
        time.sleep(0.5)
        instruments = q.get()

        f = ComplexPlot(q, instruments, mode)
    elif reupload:
        mode = 'r'
        reup = Process(target=re_r.send, args=(q, reupload))
        reup.daemon = True
        reup.start()

        # Get instr dict from reup_raw.py by queue before starting
        time.sleep(0.5)
        instruments = q.get()

        f = ComplexPlot(q, instruments, mode)
    else:
        mode = 't'
        co2 = Process(target=c.send, args=(q,))
        co2.daemon = True
        co2.start()
        nox = Process(target=n.send, args=(q,))
        nox.daemon = True
        nox.start()
        bc = Process(target=b.send, args=(q,))
        bc.daemon = True
        bc.start()

        # Get instr dict from co2.py by queue before starting
        time.sleep(0.5)
        instruments = q.get()

        f = ComplexPlot(q, instruments, mode)
    
    app.MainLoop()
    co2.join()
    nox.join()
    bc.join()




if __name__ == '__main__':
    main()