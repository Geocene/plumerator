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

class ComplexPlot(wx.Frame):
    def __init__(self, queue):
        wx.Frame.__init__(self, None, wx.ID_ANY, title='Plotter', size=(500, 750))
        self.panel = CanvasPanel(self, queue)

        sizer = wx.BoxSizer(wx.VERTICAL)
        sizer.Add(self.panel,1,wx.EXPAND)
        self.SetSizer(sizer)
        self.Layout()
        self.Show(True)

class ButtonEvent(object):

    def event(self, event):
        print('callback event')

class CanvasPanel(wx.Panel):
    def __init__(self, parent, queue):
        self.filename = 'plotFile.csv'
        with open(self.filename, mode='w') as plotFile:
            self.plotData = csv.writer(plotFile, delimiter=',', quotechar='"', quoting=csv.QUOTE_MINIMAL)
            self.plotData.writerow(['Timestamp', 'Instr ID', 'Channel', 'Value'])

        wx.Panel.__init__(self, parent)
        self.queue = queue
        self.co2_data = []
        self.nox_data = []
        self.bc_data = []
        self.co2am_vals = []
        self.noxam_vals = []
        self.bcam_vals = []
        self.figure = Figure()

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
        self.Bind(wx.EVT_TIMER, self.drawEvent)
        self.timer.Start(200)
        self.Show(True)

    def draw(self):
        self.update_data()
        current_time = datetime.datetime.now()
        
        self.co2_data.sort(key=operator.itemgetter(0))
        self.nox_data.sort(key=operator.itemgetter(0))
        self.bc_data.sort(key=operator.itemgetter(0))
        self.co2_updates = []
        self.co2_updates.append(zip(*[[(current_time - x[0]).total_seconds(), x[1]] for x in self.co2_data if (current_time - x[0]).total_seconds() <= 180 and x[2] == 0]))
        self.co2_updates.append(zip(*[[(current_time - x[0]).total_seconds(), x[1]] for x in self.co2_data if (current_time - x[0]).total_seconds() <= 180 and x[2] == 1]))
        self.co2_updates.append(zip(*[[(current_time - x[0]).total_seconds(), x[1]] for x in self.co2_data if (current_time - x[0]).total_seconds() <= 180 and x[2] == 2]))
        self.co2_updates.append(zip(*[[(current_time - x[0]).total_seconds(), x[1]] for x in self.co2_data if (current_time - x[0]).total_seconds() <= 180 and x[2] == 3]))
        self.nox_update = zip(*[[(current_time - x[0]).total_seconds(), x[1]] for x in self.nox_data if (current_time - x[0]).total_seconds() <= 180])
        self.bc_updates = []
        self.bc_updates.append(zip(*[[(current_time - x[0]).total_seconds(), x[1]] for x in self.bc_data if (current_time - x[0]).total_seconds() <= 180 and x[2] == 0]))
        self.bc_updates.append(zip(*[[(current_time - x[0]).total_seconds(), x[1]] for x in self.bc_data if (current_time - x[0]).total_seconds() <= 180 and x[2] == 1]))
        self.co2am_vals = [x for x in self.co2am_vals if (current_time - x[0]).total_seconds() <= 180]
        self.noxam_vals = [x for x in self.noxam_vals if (current_time - x[0]).total_seconds() <= 180]
        self.bcam_vals = [x for x in self.bcam_vals if (current_time - x[0]).total_seconds() <= 180]
        self.reset_data(self.co2_axes, 'co2')
        self.reset_data(self.nox_axes, 'nox')
        self.reset_data(self.bc_axes, 'bc')
        self.co2_ambient = self.get_ambient('co2')
        self.nox_ambient = self.get_ambient('nox')
        self.bc_ambient = self.get_ambient('bc')
        with open(self.filename, 'a') as plotFile:
            writer = csv.writer(plotFile, delimiter=',', quotechar='"', quoting=csv.QUOTE_MINIMAL)
            writer.writerow([current_time, 1, 'CO2_ambient', self.co2_ambient])
            writer.writerow([current_time, 2, 'NOX_ambient', self.nox_ambient])
            writer.writerow([current_time, 3, 'BC_ambient', self.bc_ambient])
        if self.co2_updates[0]:
            self.co2_axes.plot(self.co2_updates[0][0], self.co2_updates[0][1], c='r', linewidth=1.0)
        if self.co2_updates[1]:
            self.co2_axes.plot(self.co2_updates[1][0], self.co2_updates[1][1], c='g', linewidth=1.0)
        if self.co2_updates[2]:
            self.co2_axes.plot(self.co2_updates[2][0], self.co2_updates[2][1], c='b', linewidth=1.0)
        if self.co2_updates[3]:
            self.co2_axes.plot(self.co2_updates[3][0], self.co2_updates[3][1], c='y', linewidth=1.0)
        if self.bc_updates[0]:
            self.bc_axes.plot(self.bc_updates[0][0], self.bc_updates[0][1], c='r', linewidth=1.0)
        if self.bc_updates[1]:
            self.bc_axes.plot(self.bc_updates[1][0], self.bc_updates[1][1], c='g', linewidth=1.0)
        self.nox_axes.plot(self.nox_update[0], self.nox_update[1], c='r', linewidth=1.0)
        
        self.co2_axes.plot(np.arange(0, 180, 1), np.array([self.co2_ambient for i in range(180)]), c='b', linewidth=1.5, linestyle='--')
        self.nox_axes.plot(np.arange(0, 180, 1), np.array([self.nox_ambient for i in range(180)]), c='b', linewidth=1.5, linestyle='--')
        self.bc_axes.plot(np.arange(0, 180, 1), np.array([self.bc_ambient for i in range(180)]), c='b', linewidth=1.5, linestyle='--')
        self.co2_axes.text(37, 1650, "Ambient CO2 (ppm): {:.2f}".format(self.co2_ambient), fontsize=11, bbox={'facecolor': 'red', 'alpha': 0.5, 'pad': 6})
        self.nox_axes.text(37, 220, "Ambient NOX (ppb): {:.2f}".format(self.nox_ambient), fontsize=11, bbox={'facecolor': 'red', 'alpha': 0.5, 'pad': 6})
        self.bc_axes.text(37, 28, r"Ambient BC ($\mu g/m^3$): {:.2f}".format(self.bc_ambient), fontsize=11, bbox={'facecolor': 'red', 'alpha': 0.5, 'pad': 4})
        self.Show(True)
        self.canvas.draw()
        self.canvas.flush_events()

    def drawEvent(self, event):
        self.draw()

    def update_data(self):
        csv_post = []
        while not self.queue.empty():
            item = self.queue.get()
            print(item)
            if item[2]:
                if item[0] == 'co2':
                    self.co2_data.append([item[1], item[2], item[3]])
                    self.co2am_vals.append([item[1], item[2], item[3]])
                    csv_post.append([item[1], item[3], 'CO2', item[2]])
                elif item[0] == 'nox':
                    self.nox_data.append([item[1], item[2], item[3]])
                    self.noxam_vals.append([item[1], item[2], item[3]])
                    csv_post.append([item[1], item[3], 'NOX', item[2]])
                elif item[0] == 'bc':
                    self.bc_data.append([item[1], item[2], item[3]])
                    self.bcam_vals.append([item[1], item[2], item[3]])
                    csv_post.append([item[1], item[3], 'BC', item[2]])
                else:
                    print('error bad send')
            with open(self.filename, 'a') as plotFile:
                writer = csv.writer(plotFile, delimiter=',', quotechar='"', quoting=csv.QUOTE_MINIMAL)
                writer.writerows(csv_post)

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

    def get_ambient(self, name):
        if name == 'co2':
            vals = [x[1] for x in self.co2am_vals]
        elif name == 'nox':
            vals = [x[1] for x in self.noxam_vals]
        elif name == 'bc':
            vals = [x[1] for x in self.bcam_vals]
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