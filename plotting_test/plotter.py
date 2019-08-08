#!/usr/bin/env python
# -*- coding: UTF-8 -*-
 
import wx
import wx.lib.plot as plot
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

class ComplexPlot(wx.Frame):
    def __init__(self, queue):
        wx.Frame.__init__(self, None, wx.ID_ANY, title='Plotter', size=(500, 750))
        self.panel = CanvasPanel(self, queue)

        sizer = wx.BoxSizer(wx.VERTICAL)
        sizer.Add(self.panel,1,wx.EXPAND)
        self.SetSizer(sizer)
        self.Layout()
        self.Show(True)

        menuBar = wx.MenuBar()
        menu = wx.Menu()
        item = menu.Append(wx.ID_ANY, "Edit", "Edit time of flight / response time")
        self.Bind(wx.EVT_MENU, self.Edit, item)
        menuBar.Append(menu, "File")
        
        self.SetMenuBar(menuBar)

    def Edit(self, event):
        print('event')
        return

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

        # plotting data structures
        self.queue = queue
        self.co2_data = []
        self.nox_data = []
        self.bc_data = []
        self.co2am_vals = {}
        self.noxam_vals = {}
        self.bcam_vals = {}
        self.figure = Figure()

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

        # time correction
        self.time_correction = {'co2':{},'nox':{},'bc':{}}
        for i in range(self.co2_chans):
            self.time_correction['co2'][i] = {'tof':None, 'rt':None}
        for i in range(self.nox_chans):
            self.time_correction['nox'][i] = {'tof':None, 'rt':None}
        for i in range(self.bc_chans):
            self.time_correction['bc'][i] = {'tof':None, 'rt':None}

        self.co2_axes = self.figure.add_subplot(311)
        self.reset_data(self.co2_axes, 'co2')

        self.nox_axes = self.figure.add_subplot(312)
        self.reset_data(self.nox_axes, 'nox')

        self.bc_axes = self.figure.add_subplot(313)
        self.reset_data(self.bc_axes, 'bc')

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
        self.co2_ambient = self.get_ambient('co2', self.primary_co2instr)
        self.nox_ambient = self.get_ambient('nox', 0)
        self.bc_ambient = self.get_ambient('bc', 0)
        with open(self.plotfile, 'a') as plotFile:
            writer = csv.writer(plotFile, delimiter=',', quotechar='"', quoting=csv.QUOTE_MINIMAL)
            writer.writerow([current_time, '', 'CO2_ambient', self.co2_ambient])
            writer.writerow([current_time, '', 'NOX_ambient', self.nox_ambient])
            writer.writerow([current_time, '', 'BC_ambient', self.bc_ambient])
        for i in range(self.co2_chans):
            if self.co2_updates[i]:
                self.co2_axes.plot(self.co2_updates[i][0], self.co2_updates[i][1], c=self.line_colors[i], linewidth=1.0)
        for i in range(self.bc_chans):
            if self.bc_updates[i]:
                self.bc_axes.plot(self.bc_updates[i][0], self.bc_updates[i][1], c=self.line_colors[i], linewidth=1.0)
        for i in range(self.nox_chans):
            if self.nox_updates[i]:
                self.nox_axes.plot(self.nox_updates[i][0], self.nox_updates[i][1], c=self.line_colors[i], linewidth=1.0)
        
        self.co2_axes.plot(np.arange(0, 180, 1), np.array([self.co2_ambient for i in range(180)]), c='b', linewidth=1.5, linestyle='--')
        self.nox_axes.plot(np.arange(0, 180, 1), np.array([self.nox_ambient for i in range(180)]), c='b', linewidth=1.5, linestyle='--')
        self.bc_axes.plot(np.arange(0, 180, 1), np.array([self.bc_ambient for i in range(180)]), c='b', linewidth=1.5, linestyle='--')
        self.co2_axes.text(37, 1650, "Ambient CO2 (ppm): {:.2f}".format(self.co2_ambient), fontsize=11, bbox={'facecolor': 'red', 'alpha': 0.5, 'pad': 6})
        self.nox_axes.text(37, 220, "Ambient NOX (ppb): {:.2f}".format(self.nox_ambient), fontsize=11, bbox={'facecolor': 'red', 'alpha': 0.5, 'pad': 6})
        self.bc_axes.text(37, 28, r"Ambient BC ($\mu g/m^3$): {:.2f}".format(self.bc_ambient), fontsize=11, bbox={'facecolor': 'red', 'alpha': 0.5, 'pad': 4})
        self.Show(True)
        self.canvas.draw()
        self.canvas.flush_events()

    def analyze(self, ts_dict):
        for k, v in ts_dict.items():
            if k not in self.analyzed_ts_dict:
                co2_vals = v['co2'][self.primary_co2instr]
                co2_value = self.average_list(co2_vals)
                if co2_value:
                    if co2_value >= 500:
                        self.analyzed_ts_dict[k] = [True, v]
                        if self.plume_markers[0] == None:
                            self.plume_markers[0] = k
                    else:
                        self.analyzed_ts_dict[k] = [False, v]
                        if self.plume_markers[0] != None:
                            self.plume_markers[1] = k
                            self.write_plume(self.plume_markers)
                            self.plume_markers = [None, None]

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

    def update_ambient_co2(self, event):
        dlg = wx.TextEntryDialog(self, 'Enter new ambient value (ppm):',"Edit CO2 Ambient","", 
                style=wx.OK)
        dlg.ShowModal()
        self.co2_ambient = float(dlg.GetValue())
        self.co2am_vals = []
        self.co2am_vals.append([datetime.datetime.now(), self.co2_ambient])
        dlg.Destroy()

    def update_ambient_nox(self, event):
        dlg = wx.TextEntryDialog(self, 'Enter new ambient value (ppb):',"Edit NOX Ambient","", 
                style=wx.OK)
        dlg.ShowModal()
        self.nox_ambient = float(dlg.GetValue())
        self.noxam_vals = []
        self.noxam_vals.append([datetime.datetime.now(), self.nox_ambient])
        dlg.Destroy()

    def update_ambient_bc(self, event):
        dlg = wx.TextEntryDialog(self, 'Enter new ambient value (μg/m³):',"Edit BC Ambient","", 
                style=wx.OK)
        dlg.ShowModal()
        self.bc_ambient = float(dlg.GetValue())
        self.bcam_vals = []
        self.bcam_vals.append([datetime.datetime.now(), self.bc_ambient])
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
            plot.set_ylim([-5, 200])
            plot.set_title('NOX')
            plot.set_ylabel('ppb')
        elif name == 'bc':
            plot.set_ylim([-5, 25])
            plot.set_title('BC')
            plot.set_ylabel(r'$\mu g/m^3$')
            plot.set_xlabel('seconds ago')
        plot.tick_params(axis='y', left=True, right=True, labelright=True)

    def get_ambient(self, name, instr_id):
        if name == 'co2':
            vals = [x[1] for x in self.co2am_vals[instr_id]]
        elif name == 'nox':
            vals = [x[1] for x in self.noxam_vals[instr_id]]
        elif name == 'bc':
            vals = [x[1] for x in self.bcam_vals[instr_id]]
        size = len(vals)
        total = 0.0
        for item in vals:
            total += item
        if size == 0:
            return 0
        return total / size


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