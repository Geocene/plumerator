#!/usr/bin/env python
# -*- coding: UTF-8 -*-
 
import wx
import wx.lib.plot as plot
import wx.lib.newevent
from multiprocessing import Process,Queue,Pipe
import co2
import nox
import bc
import datetime
import operator
import signal
import os
import numpy as np
import csv
import time
from pprint import pprint

import matplotlib
matplotlib.use('WXAgg')
from matplotlib.backends.backend_wxagg import FigureCanvasWxAgg as FigureCanvas
from matplotlib.backends.backend_wx import NavigationToolbar2Wx
from matplotlib.figure import Figure
from matplotlib.widgets import Button
import matplotlib.pyplot as plt
import matplotlib.gridspec as gridspec
from scipy.interpolate import InterpolatedUnivariateSpline

class ComplexPlot(wx.Frame):
    def __init__(self, queue):
        wx.Frame.__init__(self, None, wx.ID_ANY, title='Plotter', size=(500, 750))
        self.panel = CanvasPanel(self, queue)

        sizer = wx.BoxSizer(wx.VERTICAL)
        sizer.Add(self.panel,1,wx.EXPAND)
        self.SetSizer(sizer)
        self.Layout()
        self.Show(True)

class CanvasPanel(wx.Panel):
    def __init__(self, parent, queue):
        # set # of channels and line colors
        self.co2_chans = 4
        self.co2_chan_names = {}
        self.bc_chans = 2
        self.bc_chan_names = {}
        self.nox_chans = 2
        self.nox_chan_names = {}
        self.line_colors = 'rgbycm'

        # set primary co2 instrument and plume counter
        self.primary_co2instr = 0 
        self.plume_counter = 1

        # create and write headers of output files
        self.plotfile = 'plotFile.csv'
        self.plumefile = 'plumeFile.csv'
        self.summaryfile = 'summary.csv'
        with open(self.plotfile, mode='w') as plotFile:
            self.plotData = csv.writer(plotFile, delimiter=',', quotechar='"', quoting=csv.QUOTE_MINIMAL)
            self.plotData.writerow(['Timestamp', 'Instr ID', 'Channel', 'Value'])
        with open(self.plumefile, mode='w') as plumeFile:
            self.plumeData = csv.writer(plumeFile, delimiter=',', quotechar='"', quoting=csv.QUOTE_MINIMAL)
            self.plumeData.writerow(['Instr ID', 'Plume ID', 'Start Time', 'Stop Time'])
        self.setSummary = True

        wx.Panel.__init__(self, parent)

        # setup plot selection

        self.selected_co2_plot = 'LI7000-1-CO2-nan'
        self.selected_nox_plot = 'CLD64-1-NOx-nan'
        self.selected_bc_plot = 'AE33-1-BC-nan'

        self.menuBar = wx.MenuBar()
        self.co2_menu = wx.Menu()
        self.co2_menu_items = []
        for i in ['LI7000-1-CO2-nan.csv', 'LI820-1-CO2-nan.csv', 'SBA5-1-CO2-nan.csv', 'Vaisala-1-CO2-nan.csv']:
            item = self.co2_menu.Append(wx.ID_ANY, i.replace('.csv', ''), "", wx.ITEM_RADIO)
            parent.Bind(wx.EVT_MENU, self.co2_select, item)
            self.co2_menu_items.append(item)
        self.nox_menu = wx.Menu()
        self.nox_menu_items = []
        for i in ['CLD64-1-NOx-nan.csv', 'CAPS-1-NO2-nan.csv']:
            item = self.nox_menu.Append(wx.ID_ANY, i.replace('.csv', ''), "", wx.ITEM_RADIO)
            parent.Bind(wx.EVT_MENU, self.nox_select, item)
            self.nox_menu_items.append(item)
        self.bc_menu = wx.Menu()
        self.bc_menu_items = []
        for i in ['AE33-1-BC-nan.csv', 'MA300-1-BC-nan.csv']:
            item = self.bc_menu.Append(wx.ID_ANY, i.replace('.csv', ''), "", wx.ITEM_RADIO)
            parent.Bind(wx.EVT_MENU, self.bc_select, item)
            self.bc_menu_items.append(item)
        self.menuBar.Append(self.co2_menu, "CO2 Plot")
        self.menuBar.Append(self.nox_menu, "NOX Plot")
        self.menuBar.Append(self.bc_menu, "BC Plot")

        
        parent.SetMenuBar(self.menuBar)

        # plotting data structures
        self.queue = queue
        self.co2_data = []
        self.nox_data = []
        self.bc_data = []
        self.co2am_vals = {}
        self.noxam_vals = {}
        self.bcam_vals = {}
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


        for i in range(self.co2_chans):
            self.co2am_vals[i] = []
        for i in range(self.nox_chans):
            self.noxam_vals[i] = []
        for i in range(self.bc_chans):
            self.bcam_vals[i] = []

        # analysis data structures
        self.ts_aligned_dps = {}
        self.analyzed_ts_dict = {}
        self.written_ts = []
        self.plume_markers = [None, None]

        # histograms
        self.nox_histogram = {}
        self.bc_histogram = {}

        # time correction
        self.time_correction = {'co2':{},'nox':{},'bc':{}}
        for i in range(self.co2_chans):
            self.time_correction['co2'][i] = {'tof':None, 'rt':None}
        for i in range(self.nox_chans):
            self.time_correction['nox'][i] = {'tof':None, 'rt':None}
        for i in range(self.bc_chans):
            self.time_correction['bc'][i] = {'tof':None, 'rt':None}

        self.co2_axes = self.figure.add_subplot(321)
        self.reset_data(self.co2_axes, 'co2')

        self.nox_axes = self.figure.add_subplot(323)
        self.reset_data(self.nox_axes, 'nox')

        self.bc_axes = self.figure.add_subplot(325)
        self.reset_data(self.bc_axes, 'bc')

        # self.nox_histogram_axes = self.figure.add_subplot(222)
        # self.bc_histogram_axes = self.figure.add_subplot(224)

        self.figure.subplots_adjust(hspace=0.5)
        self.canvas = FigureCanvas(self, -1, self.figure)

        self.co2button_ax = self.figure.add_axes([0.91, 0.90, 0.025, 0.025])
        self.co2_button = Button(self.co2button_ax, 'Edit')
        self.co2_button.on_clicked(self.update_ambient_co2)

        self.noxbutton_ax = self.figure.add_axes([0.91, 0.61, 0.025, 0.025])
        self.nox_button = Button(self.noxbutton_ax, 'Edit')
        self.nox_button.on_clicked(self.update_ambient_nox)

        self.bcbutton_ax = self.figure.add_axes([0.91, 0.32, 0.025, 0.025])
        self.bc_button = Button(self.bcbutton_ax, 'Edit')
        self.bc_button.on_clicked(self.update_ambient_bc)

        self.sizer = wx.BoxSizer(wx.VERTICAL)
        self.sizer.Add(self.canvas, 1, wx.LEFT | wx.TOP | wx.GROW | wx.EXPAND )
        self.SetSizer(self.sizer)
        self.Fit()
        self.Layout()
        parent.Maximize(True)
        self.timer = wx.Timer(self)
        self.Bind(wx.EVT_TIMER, self.drawEvent, self.timer)
        self.timer.Start(200)
        self.Show(True)

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

    def setupSummary(self):
        with open(self.summaryfile, mode='w') as summaryFile:
            self.summary = csv.writer(summaryFile, delimiter=',', quotechar='"', quoting=csv.QUOTE_MINIMAL)
            header = ['Timestamp']
            for i in range(self.co2_chans):
                header.append(self.co2_chan_names[i])
            for i in range(self.nox_chans):
                header.append(self.nox_chan_names[i])
            for i in range(self.bc_chans):
                header.append(self.bc_chan_names[i])
            self.summary.writerow(header)

    def draw(self):
        self.update_data()
        if self.setSummary:
            self.setupSummary()
            self.setSummary = False

        current_time = datetime.datetime.now()
        
        self.co2_data.sort(key=operator.itemgetter(0))
        self.nox_data.sort(key=operator.itemgetter(0))
        self.bc_data.sort(key=operator.itemgetter(0))

        # remove data older than 180 seconds
        self.co2_data = [x for x in self.co2_data if (current_time - x[0]).total_seconds() <= 180]
        self.nox_data = [x for x in self.nox_data if (current_time - x[0]).total_seconds() <= 180]
        self.bc_data = [x for x in self.bc_data if (current_time - x[0]).total_seconds() <= 180]

        # current plotted data
        self.co2_updates = []
        self.nox_updates = []
        self.bc_updates = []
        for i in range(self.co2_chans):
            self.co2_updates.append(zip(*[[(current_time - x[0]).total_seconds(), x[1], x[0]] for x in self.co2_data if (current_time - x[0]).total_seconds() <= 180 and x[2] == i]))
        for i in range(self.bc_chans):
            self.bc_updates.append(zip(*[[(current_time - x[0]).total_seconds(), x[1], x[0]] for x in self.bc_data if (current_time - x[0]).total_seconds() <= 180 and x[2] == i]))
        for i in range(self.nox_chans):
            self.nox_updates.append(zip(*[[(current_time - x[0]).total_seconds(), x[1], x[0]] for x in self.nox_data if (current_time - x[0]).total_seconds() <= 180 and x[2] == i]))

        # plume analysis
        analysis_ts = {}
        write_ts = {}
        for k, v in self.ts_aligned_dps.items():
            if (current_time - k).total_seconds() >= 90:
                analysis_ts[k] = v
            if (current_time - k).total_seconds() >= 5:
                write_ts[k] = v
            # cleanup old data
            if (current_time - k).total_seconds() >= 185:
                del self.ts_aligned_dps[k]
        self.analyze(analysis_ts)
        self.write_ts(write_ts)

        for k, v in self.co2am_vals.items():
            self.co2am_vals[k] = [x for x in v if (current_time - x[0]).total_seconds() <= 180]
        for k, v in self.noxam_vals.items():
            self.noxam_vals[k] = [x for x in v if (current_time - x[0]).total_seconds() <= 180]
        for k, v in self.bcam_vals.items():
            self.bcam_vals[k] = [x for x in v if (current_time - x[0]).total_seconds() <= 180]
        self.reset_data(self.co2_axes, 'co2')
        self.reset_data(self.nox_axes, 'nox')
        self.reset_data(self.bc_axes, 'bc')
        self.update_ambient()

        selected_co2_id = self.getIdByName(self.selected_co2_plot, 'co2')
        selected_nox_id = self.getIdByName(self.selected_nox_plot, 'nox')
        selected_bc_id = self.getIdByName(self.selected_bc_plot, 'bc')
        co2_update = self.co2_updates[selected_co2_id]
        nox_update = self.nox_updates[selected_nox_id]
        bc_update = self.bc_updates[selected_bc_id]
        if co2_update:
            self.co2_axes.plot(co2_update[0], co2_update[1], c='r', linewidth=1.0)
            if self.co2_ambient[selected_co2_id]:
                ambient_line = zip(*[[(current_time - x[0]).total_seconds(), x[1]] for x in self.co2_ambient[selected_co2_id] if (current_time - x[0]).total_seconds() <= 180])
                self.co2_axes.plot(ambient_line[0], ambient_line[1], c='b', linewidth=1.5, linestyle='--')
        if bc_update:
            self.bc_axes.plot(bc_update[0], bc_update[1], c='r', linewidth=1.0)
            if self.bc_ambient[selected_bc_id]:
                ambient_line = zip(*[[(current_time - x[0]).total_seconds(), x[1]] for x in self.bc_ambient[selected_bc_id] if (current_time - x[0]).total_seconds() <= 180])
                self.bc_axes.plot(ambient_line[0], ambient_line[1], c='b', linewidth=1.5, linestyle='--')
        if nox_update:
            self.nox_axes.plot(nox_update[0], nox_update[1], c='r', linewidth=1.0)
            if self.nox_ambient[selected_nox_id]:
                ambient_line = zip(*[[(current_time - x[0]).total_seconds(), x[1]] for x in self.nox_ambient[selected_nox_id] if (current_time - x[0]).total_seconds() <= 180])
                self.nox_axes.plot(ambient_line[0], ambient_line[1], c='b', linewidth=1.5, linestyle='--')
            
        if self.co2_ambient[selected_co2_id]:
            self.co2_axes.text(37, 1650, "Ambient CO2 (ppm): {:.2f}".format(self.co2_ambient[selected_co2_id][0][1]), fontsize=11, bbox={'facecolor': 'red', 'alpha': 0.5, 'pad': 6})
        if self.nox_ambient[selected_nox_id]:
            self.nox_axes.text(37, 28, "Ambient NOX (ppb): {:.2f}".format(self.nox_ambient[selected_nox_id][0][1]), fontsize=11, bbox={'facecolor': 'red', 'alpha': 0.5, 'pad': 6})
        if self.bc_ambient[selected_bc_id]:
            self.bc_axes.text(37, 28, r"Ambient BC ($\mu g/m^3$): {:.2f}".format(self.bc_ambient[selected_bc_id][0][1]), fontsize=11, bbox={'facecolor': 'red', 'alpha': 0.5, 'pad': 4})
        self.Show(True)
        self.canvas.draw()
        self.canvas.flush_events()

    def getIdByName(self, name, chan):
        if chan == 'co2':
            for k, v in self.co2_chan_names.items():
                if v == name:
                    return k
        elif chan == 'nox':
            for k, v in self.nox_chan_names.items():
                if v == name:
                    return k
        elif chan == 'bc':
            for k, v in self.bc_chan_names.items():
                if v == name:
                    return k

    def analyze(self, ts_dict):
        for k, v in ts_dict.items():
            if k not in self.analyzed_ts_dict:
                co2_vals = v['co2'][self.primary_co2instr]
                co2_value = self.average_list(co2_vals)
                if co2_value:
                    if co2_value >= 750:
                        self.analyzed_ts_dict[k] = [True, v]
                        if self.plume_markers[0] == None:
                            self.plume_markers[0] = k
                    else:
                        self.analyzed_ts_dict[k] = [False, v]
                        if self.plume_markers[0] != None:
                            self.plume_markers[1] = k
                            self.write_plume(self.plume_markers)
                            self.update_histogram(self.plume_markers)
                            self.plume_markers = [None, None]

    def update_histogram(self, plume_markers):
        plume_markers = [(datetime.datetime.now() - x).total_seconds() for x in plume_markers]
        plume_markers = plume_markers[::-1]
        co2_plot = self.co2_updates[self.primary_co2instr]
        co2_plot = [x[::-1] for x in co2_plot]
        
        co2_int = InterpolatedUnivariateSpline(co2_plot[0], co2_plot[1], k=1)
        co2_area = co2_int.integral(plume_markers[0], plume_markers[1])

        nox_plot = self.nox_updates[self.getIdByName(self.selected_nox_plot, 'nox')]
        nox_plot = [x[::-1] for x in nox_plot]
        nox_int = InterpolatedUnivariateSpline(nox_plot[0], nox_plot[1], k=1)
        nox_area = nox_int.integral(plume_markers[0], plume_markers[1])

        bc_plot = self.bc_updates[self.getIdByName(self.selected_bc_plot, 'bc')]
        bc_plot = [x[::-1] for x in bc_plot]
        bc_int = InterpolatedUnivariateSpline(bc_plot[0], bc_plot[1], k=1)
        bc_area = bc_int.integral(plume_markers[0], plume_markers[1])

        print('Areas:')
        print(co2_area)
        print(nox_area)
        print(bc_area)


    def write_plume(self, timestamps):
        with open(self.plumefile, 'a') as plumeFile:
            writer = csv.writer(plumeFile, delimiter=',', quotechar='"', quoting=csv.QUOTE_MINIMAL)
            for i in range(self.co2_chans):
                if i != self.primary_co2instr:
                    timestamps = self.correct_ts(timestamps, 'co2', i)
                writer.writerow([self.co2_chan_names[i], self.plume_counter, timestamps[0], timestamps[1]])
            for i in range(self.nox_chans):
                timestamps = self.correct_ts(timestamps, 'nox', i)
                writer.writerow([self.nox_chan_names[i], self.plume_counter, timestamps[0], timestamps[1]])
            for i in range(self.bc_chans):
                timestamps = self.correct_ts(timestamps, 'bc', i)
                writer.writerow([self.bc_chan_names[i], self.plume_counter, timestamps[0], timestamps[1]])
        self.plume_counter += 1

    def write_ts(self, ts_dict):
        csv_post = []
        for k, v in ts_dict.items():
            if k not in self.written_ts:
                self.written_ts.append(k)
                post = [k]
                for i in range(self.co2_chans):
                    post.append(self.average_list(v['co2'][i]))
                for i in range(self.nox_chans):
                    post.append(self.average_list(v['nox'][i]))
                for i in range(self.bc_chans):
                    post.append(self.average_list(v['bc'][i]))
                csv_post.append(post)
        with open(self.summaryfile, 'a') as summaryFile:
                writer = csv.writer(summaryFile, delimiter=',', quotechar='"', quoting=csv.QUOTE_MINIMAL)
                writer.writerows(csv_post)

    def correct_ts(self, timestamps, chan, instr_id):
        tof = self.time_correction[chan][instr_id]['tof']
        rt = self.time_correction[chan][instr_id]['rt']
        if tof != None:
            timestamps = [timestamps[0] + tof, timestamps[1] + tof]
        if rt != None:
            timestamps = [timestamps[0], timestamps[1] + rt]
        return timestamps

    def average_list(self, lst):
        if lst:
            return sum(lst) / len(lst)
        else:
            return None

    def drawEvent(self, event):
        self.draw()

    def update_data(self):
        csv_post = []
        while not self.queue.empty():
            item = self.queue.get()
            if item[0] == 'co2' and item[3] not in self.co2_chan_names:
                self.co2_chan_names[item[3]] = item[4]
            elif item[0] == 'nox' and item[3] not in self.nox_chan_names:
                self.nox_chan_names[item[3]] = item[4]
            elif item[0] == 'bc' and item[3] not in self.bc_chan_names:
                self.bc_chan_names[item[3]] = item[4]
            # print(item)
            if item[2]:
                if item[0] == 'co2':
                    self.co2_data.append([item[1], item[2], item[3]])
                    self.co2am_vals[item[3]].append([item[1], item[2]])
                    csv_post.append([item[1], self.co2_chan_names[item[3]], 'CO2', item[2]])
                    self.align_ts(item, 'co2')
                    
                elif item[0] == 'nox':
                    self.nox_data.append([item[1], item[2], item[3]])
                    self.noxam_vals[item[3]].append([item[1], item[2]])
                    csv_post.append([item[1], self.nox_chan_names[item[3]], 'NOX', item[2]])
                    self.align_ts(item, 'nox')
                elif item[0] == 'bc':
                    self.bc_data.append([item[1], item[2], item[3]])
                    self.bcam_vals[item[3]].append([item[1], item[2]])
                    csv_post.append([item[1], self.bc_chan_names[item[3]], 'BC', item[2]])
                    self.align_ts(item, 'bc')
                else:
                    print('error bad send')
            with open(self.plotfile, 'a') as plotFile:
                writer = csv.writer(plotFile, delimiter=',', quotechar='"', quoting=csv.QUOTE_MINIMAL)
                writer.writerows(csv_post)

    # Output structure:
    # {datetime.datetime(2019, 8, 5, 14, 37, 4): {'bc': {0: [0.98], 1: []},
    #                                     'co2': {0: [668.39],
    #                                             1: [813.28573],
    #                                             2: [628.0],
    #                                             3: [873.1]},
    #                                     'nox': {0: [], 1: []}}}
    def align_ts(self, dp, dp_type):
        old_dt = dp[1]
        floored_dt = datetime.datetime(old_dt.year, old_dt.month, old_dt.day, old_dt.hour, old_dt.minute, old_dt.second)
        if floored_dt in self.ts_aligned_dps:
            self.ts_aligned_dps[floored_dt][dp_type][dp[3]].append(dp[2])        
        else:
            co2_dict = {}
            nox_dict = {}
            bc_dict = {}
            for i in range(self.co2_chans):
                co2_dict[i] = []
            for i in range(self.nox_chans):
                nox_dict[i] = []
            for i in range(self.bc_chans):
                bc_dict[i] = []
            self.ts_aligned_dps[floored_dt] = {'co2':co2_dict, 'bc':bc_dict, 'nox':nox_dict}
            self.ts_aligned_dps[floored_dt][dp_type][dp[3]].append(dp[2])    


    # need to update how this is handled, self.co2am_vals is depricated, ambient is calculated using self.analyzed_ts_dict
    def update_ambient_co2(self, event):
        dlg = wx.TextEntryDialog(self, 'Enter new ambient value (ppm):',"Edit CO2 Ambient","", 
                style=wx.OK)
        dlg.ShowModal()
        selected_co2_id = self.getIdByName(self.selected_co2_plot, 'co2')
        value = float(dlg.GetValue())
        if self.co2_ambient[selected_co2_id]:
            self.co2am_vals[selected_co2_id] = []
            self.co2am_vals[selected_co2_id].append([datetime.datetime.now() - datetime.timedelta(seconds=90), value])
            self.co2_ambient[selected_co2_id].append([datetime.datetime.now() - datetime.timedelta(seconds=90), value])
        dlg.Destroy()

    def update_ambient_nox(self, event):
        dlg = wx.TextEntryDialog(self, 'Enter new ambient value (ppb):',"Edit NOX Ambient","", 
                style=wx.OK)
        dlg.ShowModal()
        selected_nox_id = self.getIdByName(self.selected_nox_plot, 'nox')
        value = float(dlg.GetValue())
        if self.nox_ambient[selected_nox_id]:
            self.noxam_vals[selected_nox_id] = []
            self.noxam_vals[selected_nox_id].append([datetime.datetime.now() - datetime.timedelta(seconds=90), value])
            self.nox_ambient[selected_nox_id].append([datetime.datetime.now() - datetime.timedelta(seconds=90), value])
        dlg.Destroy()

    def update_ambient_bc(self, event):
        dlg = wx.TextEntryDialog(self, 'Enter new ambient value (μg/m³):',"Edit BC Ambient","", 
                style=wx.OK)
        dlg.ShowModal()
        selected_bc_id = self.getIdByName(self.selected_bc_plot, 'bc')
        value = float(dlg.GetValue())
        if self.bc_ambient[selected_bc_id]:
            self.bcam_vals[selected_bc_id] = []
            self.bcam_vals[selected_bc_id].append([datetime.datetime.now() - datetime.timedelta(seconds=90), value])
            self.bc_ambient[selected_bc_id].append([datetime.datetime.now() - datetime.timedelta(seconds=90), value])
        dlg.Destroy()

    def reset_data(self, plot, name):
        plot.clear()
        plot.set_xlim([120, 0])
        plot.xaxis.set_ticks(np.arange(0, 210, 30))
        if name == 'co2':
            plot.set_ylim([-100, 1500])
            plot.set_title('CO2')
            plot.set_ylabel('ppm')
        elif name == 'nox':
            plot.set_ylim([-5, 25])
            plot.set_title('NOX')
            plot.set_ylabel('ppb')
        elif name == 'bc':
            plot.set_ylim([-5, 25])
            plot.set_title('BC')
            plot.set_ylabel(r'$\mu g/m^3$')
            plot.set_xlabel('seconds ago')
        plot.tick_params(axis='y', left=True, right=True, labelright=True)

    def update_ambient(self):
        for i in range(self.co2_chans):
            am_value = self.get_ambient('co2', i)
            if am_value:
                self.co2_ambient[i].append([datetime.datetime.now() - datetime.timedelta(seconds=90), am_value])
        for i in range(self.nox_chans):
            am_value = self.get_ambient('nox', i)
            if am_value:
                self.nox_ambient[i].append([datetime.datetime.now() - datetime.timedelta(seconds=90), am_value])
        for i in range(self.bc_chans):
            am_value = self.get_ambient('bc', i)
            if am_value:
                self.bc_ambient[i].append([datetime.datetime.now() - datetime.timedelta(seconds=90), am_value])

    def get_ambient(self, name, instr_id):
        current_time = datetime.datetime.now()
        am_vals = []
        for k, v in self.analyzed_ts_dict.items():
            if (current_time - k).total_seconds() >= 90 and (current_time - k).total_seconds() <= 180:
                if v[0] == False:
                    am_vals.extend(v[1][name][instr_id])
        am_value = self.average_list(am_vals)
        if am_value:
            with open(self.plotfile, 'a') as plotFile:
                writer = csv.writer(plotFile, delimiter=',', quotechar='"', quoting=csv.QUOTE_MINIMAL)
                writer.writerow([current_time, instr_id, name.upper() + '_ambient', am_value])
        return self.average_list(am_vals)


    # def get_ambient(self, name, instr_id):
    #     current_time = datetime.datetime.now()
    #     if name == 'co2':
    #         vals = [x[1] for x in self.co2am_vals[instr_id] if (current_time - x[0]).total_seconds() >= 90 and (current_time - x[0]).total_seconds() <= 180]
    #     elif name == 'nox':
    #         vals = [x[1] for x in self.noxam_vals[instr_id] if (current_time - x[0]).total_seconds() >= 90 and (current_time - x[0]).total_seconds() <= 180]
    #     elif name == 'bc':
    #         vals = [x[1] for x in self.bcam_vals[instr_id] if (current_time - x[0]).total_seconds() >= 90 and (current_time - x[0]).total_seconds() <= 180]
    #     size = len(vals)
    #     total = 0.0
    #     for item in vals:
    #         total += item
    #     if size == 0:
    #         return None
    #     return total / size

q = Queue()
co2 = Process(target=co2.send, args=(q,))
co2.daemon = True
co2.start()
nox = Process(target=nox.send, args=(q,))
nox.daemon = True
nox.start()
bc = Process(target=bc.send, args=(q,))
bc.daemon = True
bc.start()

def main():
    app = wx.App()
    f = ComplexPlot(q)
    app.MainLoop()
    co2.join()
    nox.join()
    bc.join()

if __name__ == '__main__':
    main()