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
        self.plotfile = 'raw_data.csv'
        self.plumefile = 'plumes.csv'
        self.plumeArea = 'plume_areas.csv'
        self.summaryfile = 'secondly_data.csv'
        with open(self.plotfile, mode='w') as plotFile:
            self.plotData = csv.writer(plotFile, delimiter=',', quotechar='"', quoting=csv.QUOTE_MINIMAL)
            self.plotData.writerow(['Timestamp', 'Instr ID', 'Channel', 'Value'])
        with open(self.plumefile, mode='w') as plumeFile:
            self.plumeData = csv.writer(plumeFile, delimiter=',', quotechar='"', quoting=csv.QUOTE_MINIMAL)
            self.plumeData.writerow(['Instr ID', 'Plume ID', 'Start Time', 'Stop Time'])
        with open(self.plumeArea, mode='w') as plumeArea:
            self.plumeAreas = csv.writer(plumeArea, delimiter=',', quotechar='"', quoting=csv.QUOTE_MINIMAL)
            self.plumeAreas.writerow(['Plume ID', 'Instr ID', 'Area', 'Units'])
        self.setSummary = True

        # timing test
        with open('timing.csv', mode='w') as timingFile:
            timeData = csv.writer(timingFile, delimiter=',', quotechar='"', quoting=csv.QUOTE_MINIMAL)
            timeData.writerow(['Drawcycle', 'Update Data', 'Cleanup', 'Update Ambient', 'Get Updates', 'Analyze', 'Write Summary', 'Plotting', 'Histograms', 'Plumes'])

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
        self.ts_aligned_dps = {}
        self.plumes = []
        self.plume_markers = [None, None]

        # histograms
        self.nox_histogram = {}
        for i in range(self.nox_chans):
            self.nox_histogram[i] = []
        self.bc_histogram = {}
        for i in range(self.bc_chans):
            self.bc_histogram[i] = []
        self.replot_hists = False

        # time correction
        self.time_correction = {'co2':{},'nox':{},'bc':{}}
        for i in range(self.co2_chans):
            self.time_correction['co2'][i] = {'tof':None, 'rt':None}
        for i in range(self.nox_chans):
            self.time_correction['nox'][i] = {'tof':None, 'rt':None}
        for i in range(self.bc_chans):
            self.time_correction['bc'][i] = {'tof':None, 'rt':None}

        self.co2_axes = self.figure.add_subplot(self.gridspec[0, 0])
        self.reset_data(self.co2_axes, 'co2')

        self.nox_axes = self.figure.add_subplot(self.gridspec[1, 0])
        self.reset_data(self.nox_axes, 'nox')

        self.bc_axes = self.figure.add_subplot(self.gridspec[2, 0])
        self.reset_data(self.bc_axes, 'bc')

        self.nox_histogram_axes = self.figure.add_subplot(self.gridspec[1, 1])
        self.nox_histogram_axes.set_ylabel('Observations')
        self.nox_histogram_axes.set_xlabel('ppb (NOX) / ppm (CO2)')
        self.bc_histogram_axes = self.figure.add_subplot(self.gridspec[2, 1])
        self.bc_histogram_axes.set_ylabel('Observations')
        self.bc_histogram_axes.set_xlabel(r'$\mu g/m^3$ (BC) / ppm (CO2)')

        self.figure.subplots_adjust(hspace=0.5)
        self.canvas = FigureCanvas(self, -1, self.figure)

        self.co2button_ax = self.figure.add_axes([0.61, 0.90, 0.025, 0.025])
        self.co2_button = Button(self.co2button_ax, 'Edit')
        self.co2_button.on_clicked(self.update_ambient_co2)

        self.noxbutton_ax = self.figure.add_axes([0.61, 0.61, 0.025, 0.025])
        self.nox_button = Button(self.noxbutton_ax, 'Edit')
        self.nox_button.on_clicked(self.update_ambient_nox)

        self.bcbutton_ax = self.figure.add_axes([0.61, 0.32, 0.025, 0.025])
        self.bc_button = Button(self.bcbutton_ax, 'Edit')
        self.bc_button.on_clicked(self.update_ambient_bc)

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
        drawCycle = time.time()
        row = [drawCycle]

        self.update_data()

        updateData = time.time()
        row.append(updateData - drawCycle)

        if self.setSummary:
            self.setupSummary()
            self.setSummary = False

        current_time = datetime.datetime.now()
        
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
        self.co2_updates = []
        self.nox_updates = []
        self.bc_updates = []
        for i in range(self.co2_chans):
            self.co2_updates.append(zip(*[[(current_time - x[0]).total_seconds(), x[1], x[0]] for x in self.co2_data if x[2] == i]))
        for i in range(self.bc_chans):
            self.bc_updates.append(zip(*[[(current_time - x[0]).total_seconds(), x[1], x[0]] for x in self.bc_data if x[2] == i]))
        for i in range(self.nox_chans):
            self.nox_updates.append(zip(*[[(current_time - x[0]).total_seconds(), x[1], x[0]] for x in self.nox_data if x[2] == i]))

        getUpdate = time.time()
        row.append(getUpdate - cleanupData)

        self.reset_data(self.co2_axes, 'co2')
        self.reset_data(self.nox_axes, 'nox')
        self.reset_data(self.bc_axes, 'bc')

        self.ambient_cs -= 1
        if self.ambient_cs == 0:
            self.update_ambient()
            self.ambient_cs = 5

        update_am = time.time()
        row.append(update_am - getUpdate)

        # plume analysis and summary write
        self.analyze()
        analyze = time.time()
        row.append(analyze - update_am)
        self.write_ts()
        write_summ = time.time()
        row.append(write_summ - analyze)

        

        current_time = datetime.datetime.now()
        selected_co2_id = self.getIdByName(self.selected_co2_plot, 'co2')
        selected_nox_id = self.getIdByName(self.selected_nox_plot, 'nox')
        selected_bc_id = self.getIdByName(self.selected_bc_plot, 'bc')
        co2_update = self.co2_updates[selected_co2_id]
        nox_update = self.nox_updates[selected_nox_id]
        bc_update = self.bc_updates[selected_bc_id]
        if co2_update:
            self.co2_axes.plot(co2_update[0], co2_update[1], c='r', linewidth=1.0)
            if self.co2_ambient[selected_co2_id]:
                co2_ambient_line = zip(*[[(current_time - x[0]).total_seconds(), x[1]] for x in self.co2_ambient[selected_co2_id] if (current_time - x[0]).total_seconds() <= 180])
                self.co2_axes.plot(co2_ambient_line[0], co2_ambient_line[1], c='b', linewidth=1.5, linestyle='--')
        if bc_update:
            self.bc_axes.plot(bc_update[0], bc_update[1], c='r', linewidth=1.0)
            if self.bc_ambient[selected_bc_id]:
                bc_ambient_line = zip(*[[(current_time - x[0]).total_seconds(), x[1]] for x in self.bc_ambient[selected_bc_id] if (current_time - x[0]).total_seconds() <= 180])
                self.bc_axes.plot(bc_ambient_line[0], bc_ambient_line[1], c='b', linewidth=1.5, linestyle='--')
        if nox_update:
            self.nox_axes.plot(nox_update[0], nox_update[1], c='r', linewidth=1.0)
            if self.nox_ambient[selected_nox_id]:
                nox_ambient_line = zip(*[[(current_time - x[0]).total_seconds(), x[1]] for x in self.nox_ambient[selected_nox_id] if (current_time - x[0]).total_seconds() <= 180])
                self.nox_axes.plot(nox_ambient_line[0], nox_ambient_line[1], c='b', linewidth=1.5, linestyle='--')

        plotting = time.time()
        row.append(plotting - write_summ)

        current_time = datetime.datetime.now()

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

        with open('timing.csv', mode='a') as timingFile:
            timeData = csv.writer(timingFile, delimiter=',', quotechar='"', quoting=csv.QUOTE_MINIMAL)
            timeData.writerow(row)
            
        if self.co2_ambient[selected_co2_id]:
            self.co2_axes.text(60, 1650, "Ambient CO2 (ppm): {:.2f}".format(self.co2_ambient[selected_co2_id][0][1]), fontsize=11, bbox={'facecolor': 'red', 'alpha': 0.5, 'pad': 6})
        if self.nox_ambient[selected_nox_id]:
            self.nox_axes.text(60, 28, "Ambient NOX (ppb): {:.2f}".format(self.nox_ambient[selected_nox_id][0][1]), fontsize=11, bbox={'facecolor': 'red', 'alpha': 0.5, 'pad': 6})
        if self.bc_ambient[selected_bc_id]:
            self.bc_axes.text(60, 28, r"Ambient BC ($\mu g/m^3$): {:.2f}".format(self.bc_ambient[selected_bc_id][0][1]), fontsize=11, bbox={'facecolor': 'red', 'alpha': 0.5, 'pad': 4})
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

    def analyze(self):
        to_analyze = []
        current_time = datetime.datetime.now()
        for k, v in self.ts_aligned_dps.items():
            if (current_time - k).total_seconds() >= 185:
                del self.ts_aligned_dps[k]
            if (current_time - k).total_seconds() >= 90 and v['plume'] == None:
                to_analyze.append((k, v))
        to_analyze.sort(key=operator.itemgetter(0))
        for k, v in to_analyze:
            co2_vals = v['co2'][self.primary_co2instr]
            co2_value = self.average_list(co2_vals)
            if co2_value:
                if co2_value >= 750:
                    v['plume'] = True
                    self.ts_aligned_dps[k] = v
                    if self.plume_markers[0] == None:
                        self.plume_markers[0] = k
                else:
                    v['plume'] = False
                    self.ts_aligned_dps[k] = v
                    if self.plume_markers[0] != None:
                        self.plume_markers[1] = k
                        self.update_histogram(self.plume_markers)
                        self.write_plume(self.plume_markers)
                        self.plume_markers = [None, None]

    def update_histogram(self, plume_markers):
        current_time = datetime.datetime.now()
        areas_post = []

        plume_markers = [plume_markers[0], plume_markers[1] + datetime.timedelta(seconds=1)]

        co2_plot = zip(*[x for x in zip(*self.co2_updates[self.primary_co2instr]) if plume_markers[0] <= x[2] <= plume_markers[1]])
        co2_plot = [x[::-1] for x in co2_plot]
        co2am_plot = zip(*[[(current_time - x[0]).total_seconds(), x[1]] for x in self.co2_ambient[self.primary_co2instr] if plume_markers[0] <= x[0] <= plume_markers[1]])
        co2am_plot = [x[::-1] for x in co2am_plot]
        if not co2am_plot:
            print(self.co2_ambient[self.primary_co2instr])
            print(plume_markers)
        co2_area = np.trapz(co2_plot[1], x=co2_plot[0])
        co2am_area = np.trapz(co2am_plot[1], x=co2am_plot[0])
        co2_calc_area = co2_area - co2am_area
        areas_post.append([self.plume_counter, self.co2_chan_names[self.primary_co2instr], co2_calc_area, 'ppm-co2-s'])

        for i in range(self.nox_chans):
            nox_plot = zip(*[x for x in zip(*self.nox_updates[i]) if plume_markers[0] <= x[2] <= plume_markers[1]])
            nox_plot = [x[::-1] for x in nox_plot]
            noxam_plot = zip(*[[(current_time - x[0]).total_seconds(), x[1]] for x in self.nox_ambient[i] if plume_markers[0] <= x[0] <= plume_markers[1]])
            noxam_plot = [x[::-1] for x in noxam_plot]
            if nox_plot:
                nox_area = np.trapz(nox_plot[1], x=nox_plot[0])
            else:
                nox_area = 0
            if noxam_plot:
                noxam_area = np.trapz(noxam_plot[1], x=noxam_plot[0])
            else:
                noxam_area = 0
            nox_calc_area = nox_area - noxam_area
            areas_post.append([self.plume_counter, self.nox_chan_names[i], nox_calc_area, 'ppb-nox-s'])
            nox_histogram_val = nox_calc_area / co2_calc_area
            self.nox_histogram[i].append(nox_histogram_val)

        for i in range(self.bc_chans):
            bc_plot = zip(*[x for x in zip(*self.bc_updates[i]) if plume_markers[0] <= x[2] <= plume_markers[1]])
            bc_plot = [x[::-1] for x in bc_plot]
            bcam_plot = zip(*[[(current_time - x[0]).total_seconds(), x[1]] for x in self.bc_ambient[i] if plume_markers[0] <= x[0] <= plume_markers[1]])
            bcam_plot = [x[::-1] for x in bcam_plot]
            if bc_plot:
                bc_area = np.trapz(bc_plot[1], x=bc_plot[0])
            else:
                bc_area = 0
            if bcam_plot:
                bcam_area = np.trapz(bcam_plot[1], x=bcam_plot[0])
            else:
                bcam_area = 0
            bc_calc_area = bc_area - bcam_area
            areas_post.append([self.plume_counter, self.bc_chan_names[i], bc_calc_area, 'μg/m³-bc-s'])
            bc_histogram_val = bc_calc_area / co2_calc_area
            self.bc_histogram[i].append(bc_histogram_val)

        with open(self.plumeArea, 'a') as plumeAreas:
            writer = csv.writer(plumeAreas, delimiter=',', quotechar='"', quoting=csv.QUOTE_MINIMAL)
            writer.writerows(areas_post)

        self.replot_hists = True

    def write_plume(self, timestamps):
        self.plumes.append(timestamps)
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

    def write_ts(self):
        csv_post = []
        for k, v in self.ts_aligned_dps.items():
            if (datetime.datetime.now() - k).total_seconds() >= 5 and not v['written']:
                v['written'] = True
                self.ts_aligned_dps[k] = v
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
            if item[2]:
                if item[0] == 'co2':
                    self.co2_data.append([item[1], item[2], item[3]])
                    csv_post.append([item[1], self.co2_chan_names[item[3]], 'CO2', item[2]])
                    self.align_ts(item, 'co2')
                elif item[0] == 'nox':
                    self.nox_data.append([item[1], item[2], item[3]])
                    csv_post.append([item[1], self.nox_chan_names[item[3]], 'NOX', item[2]])
                    self.align_ts(item, 'nox')
                elif item[0] == 'bc':
                    self.bc_data.append([item[1], item[2], item[3]])
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
    #                                     'nox': {0: [], 1: []}, 'plume':None, 'written':False}}
    def align_ts(self, dp, dp_type):
        old_dt = dp[1]
        floored_dt = self.floor_dt(old_dt)
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
            self.ts_aligned_dps[floored_dt] = {'co2':co2_dict, 'bc':bc_dict, 'nox':nox_dict, 'plume':None, 'written':False}
            self.ts_aligned_dps[floored_dt][dp_type][dp[3]].append(dp[2])


    # need to update how this is handled, self.co2am_vals is depricated, ambient is calculated using self.ts_aligned_dps
    def update_ambient_co2(self, event):
        dlg = wx.TextEntryDialog(self, 'Enter new ambient value (ppm):',"Edit CO2 Ambient","", 
                style=wx.OK)
        dlg.ShowModal()
        selected_co2_id = self.getIdByName(self.selected_co2_plot, 'co2')
        value = float(dlg.GetValue())
        if self.co2_ambient[selected_co2_id]:
            self.co2_ambient[selected_co2_id].append([datetime.datetime.now() - datetime.timedelta(seconds=90), value])
        dlg.Destroy()

    def update_ambient_nox(self, event):
        dlg = wx.TextEntryDialog(self, 'Enter new ambient value (ppb):',"Edit NOX Ambient","", 
                style=wx.OK)
        dlg.ShowModal()
        selected_nox_id = self.getIdByName(self.selected_nox_plot, 'nox')
        value = float(dlg.GetValue())
        if self.nox_ambient[selected_nox_id]:
            self.nox_ambient[selected_nox_id].append([datetime.datetime.now() - datetime.timedelta(seconds=90), value])
        dlg.Destroy()

    def update_ambient_bc(self, event):
        dlg = wx.TextEntryDialog(self, 'Enter new ambient value (μg/m³):',"Edit BC Ambient","", 
                style=wx.OK)
        dlg.ShowModal()
        selected_bc_id = self.getIdByName(self.selected_bc_plot, 'bc')
        value = float(dlg.GetValue())
        if self.bc_ambient[selected_bc_id]:
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

    def nearest_vals(self, timestamp):
        seconds = 1
        sign = True
        ret = {'co2':{}, 'nox':{}, 'bc':{}}
        for i in range(self.co2_chans):
            ret['co2'][i] = False
        for i in range(self.nox_chans):
            ret['nox'][i] = False
        for i in range(self.bc_chans):
            ret['bc'][i] = False
        while self.notFull(ret):
            if timestamp in self.ts_aligned_dps:
                for i in range(self.co2_chans):
                    if self.ts_aligned_dps[timestamp]['co2'][i]:
                        ret['co2'][i] = self.average_list(self.ts_aligned_dps[timestamp]['co2'][i])
                for i in range(self.bc_chans):
                    if self.ts_aligned_dps[timestamp]['bc'][i]:
                        ret['bc'][i] = self.average_list(self.ts_aligned_dps[timestamp]['bc'][i])
                for i in range(self.nox_chans):
                    if self.ts_aligned_dps[timestamp]['nox'][i]:
                        ret['nox'][i] = self.average_list(self.ts_aligned_dps[timestamp]['nox'][i])
            if sign:
                timestamp = timestamp + datetime.timedelta(seconds=seconds)
            else: 
                timestamp = timestamp - datetime.timedelta(seconds=seconds)
            seconds += 1
            sign = not sign
        return ret
        
    def notFull(self, d):
        for i in range(self.co2_chans):
            if d['co2'][i] == False:
                return True
        for i in range(self.nox_chans):
            if d['nox'][i] == False:
                return True
        for i in range(self.bc_chans):
            if d['bc'][i] == False:
                return True
        return False

    def update_ambient(self):
        current_time = datetime.datetime.now()
        ambient_time = current_time - datetime.timedelta(seconds=90)
        co2_amvals, bc_amvals, nox_amvals = {}, {}, {}
        for i in range(self.co2_chans):
            co2_amvals[i] = []
        for i in range(self.bc_chans):
            bc_amvals[i] = []
        for i in range(self.nox_chans):
            nox_amvals[i] = []
        for k, v in self.ts_aligned_dps.items():
            if (current_time - k).total_seconds() >= 90 and (current_time - k).total_seconds() <= 180:
                if v['plume'] == False:
                    for i in range(self.co2_chans):
                        co2_amvals[i].extend(v['co2'][i])
                    for i in range(self.bc_chans):
                        bc_amvals[i].extend(v['bc'][i])
                    for i in range(self.nox_chans):
                        nox_amvals[i].extend(v['nox'][i])
        rows = []
        for i in range(self.co2_chans):
            if co2_amvals[i]:
                am_value = self.average_list(co2_amvals[i])
                rows.append([ambient_time, i, 'CO2_ambient', am_value])
                self.co2_ambient[i].append([ambient_time, am_value])
        for i in range(self.bc_chans):
            if bc_amvals[i]:
                am_value = self.average_list(bc_amvals[i])
                rows.append([ambient_time, i, 'BC_ambient', am_value])
                self.bc_ambient[i].append([ambient_time, am_value])
        for i in range(self.nox_chans):
            if nox_amvals[i]:
                am_value = self.average_list(nox_amvals[i])
                rows.append([ambient_time, i, 'NOX_ambient', am_value])
                self.nox_ambient[i].append([ambient_time, am_value])
        with open(self.plotfile, 'a') as plotFile:
            writer = csv.writer(plotFile, delimiter=',', quotechar='"', quoting=csv.QUOTE_MINIMAL)
            writer.writerows(rows)

    # def update_ambient(self):
    #     current_time = datetime.datetime.now()
    #     ambient_time = current_time - datetime.timedelta(seconds=90)
    #     nearest = self.nearest_vals(self.floor_dt(ambient_time))
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
    #                     co2_amvals[i].extend(v['co2'][i])
    #                 for i in range(self.bc_chans):
    #                     bc_amvals[i].extend(v['bc'][i])
    #                 for i in range(self.nox_chans):
    #                     nox_amvals[i].extend(v['nox'][i])
    #     rows = []
    #     for i in range(self.co2_chans):
    #         if co2_amvals[i]:
    #             am_value = self.average_list(co2_amvals[i])
    #             rows.append([ambient_time, i, 'CO2_ambient', am_value])
    #             self.co2_ambient[i].append([ambient_time, am_value, nearest['co2'][i]])
    #     for i in range(self.bc_chans):
    #         if bc_amvals[i]:
    #             am_value = self.average_list(bc_amvals[i])
    #             rows.append([ambient_time, i, 'BC_ambient', am_value])
    #             self.bc_ambient[i].append([ambient_time, am_value, nearest['bc'][i]])
    #     for i in range(self.nox_chans):
    #         if nox_amvals[i]:
    #             am_value = self.average_list(nox_amvals[i])
    #             rows.append([ambient_time, i, 'NOX_ambient', am_value])
    #             self.nox_ambient[i].append([ambient_time, am_value, nearest['nox'][i]])
    #     with open(self.plotfile, 'a') as plotFile:
    #         writer = csv.writer(plotFile, delimiter=',', quotechar='"', quoting=csv.QUOTE_MINIMAL)
    #         writer.writerows(rows)

    def floor_dt(self, dt):
        return datetime.datetime(dt.year, dt.month, dt.day, dt.hour, dt.minute, dt.second)

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