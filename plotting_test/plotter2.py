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

import matplotlib
matplotlib.use('WXAgg')
from matplotlib.backends.backend_wxagg import FigureCanvasWxAgg as FigureCanvas
from matplotlib.backends.backend_wx import NavigationToolbar2Wx
from matplotlib.figure import Figure
import matplotlib.pyplot as plt

class ComplexPlot(wx.Frame):
    def __init__(self, queue):
        wx.Frame.__init__(self, None, wx.ID_ANY, title='Plotter', size=(500, 750))
        self.panel = CanvasPanel(self, queue)

        sizer = wx.BoxSizer(wx.VERTICAL)
        sizer.Add(self.panel,1,wx.EXPAND)
        self.SetSizer(sizer)
        self.Show(True)

class CanvasPanel(wx.Panel):
    def __init__(self, parent, queue):
        wx.Panel.__init__(self, parent)
        self.queue = queue
        self.co2_data = []
        self.nox_data = []
        self.bc_data = []
        self.figure = Figure()
        self.co2_axes = self.figure.add_subplot(311)
        self.reset_data(self.co2_axes, 'co2')
        self.nox_axes = self.figure.add_subplot(312)
        self.reset_data(self.nox_axes, 'nox')
        self.bc_axes = self.figure.add_subplot(313)
        self.reset_data(self.bc_axes, 'bc')
        self.canvas = FigureCanvas(self, -1, self.figure)
        self.sizer = wx.BoxSizer(wx.VERTICAL)
        self.sizer.Add(self.canvas, 1, wx.LEFT | wx.TOP | wx.GROW)
        self.SetSizer(self.sizer)
        self.Fit()
        parent.Maximize(True)
        self.timer = wx.Timer(self)
        self.Bind(wx.EVT_TIMER, self.drawEvent)
        self.timer.Start(1000)

    def draw(self):
        self.update_data()
        current_time = datetime.datetime.now()
        
        self.co2_data.sort(key=operator.itemgetter(0))
        self.nox_data.sort(key=operator.itemgetter(0))
        self.bc_data.sort(key=operator.itemgetter(0))
        co2_update = zip(*[[(current_time - x[0]).total_seconds(), x[1]] for x in self.co2_data if (current_time - x[0]).total_seconds() <= 120])
        nox_update = zip(*[[(current_time - x[0]).total_seconds(), x[1]] for x in self.nox_data if (current_time - x[0]).total_seconds() <= 120])
        bc_update = zip(*[[(current_time - x[0]).total_seconds(), x[1]] for x in self.bc_data if (current_time - x[0]).total_seconds() <= 120])
        self.reset_data(self.co2_axes, 'co2')
        self.reset_data(self.nox_axes, 'nox')
        self.reset_data(self.bc_axes, 'bc')
        self.co2_axes.plot(co2_update[0], co2_update[1], c='r', linewidth=1.0)
        self.nox_axes.plot(nox_update[0], nox_update[1], c='r', linewidth=1.0)
        self.bc_axes.plot(bc_update[0], bc_update[1], c='r', linewidth=1.0)
        self.Show(True)
        self.canvas.draw()
        self.canvas.flush_events()

    def drawEvent(self, event):
        self.draw()

    def update_data(self):
        while not self.queue.empty():
            item = self.queue.get()
            if item[0] == 'co2':
                self.co2_data.append([item[1], item[2]])
            elif item[0] == 'nox':
                self.nox_data.append([item[1], item[2]])
            elif item[0] == 'bc':
                self.bc_data.append([item[1], item[2]])
            else:
                print('error bad send')

    def reset_data(self, plot, name):
        plot.clear()
        plot.set_xlim([120, 0])
        plot.xaxis.set_ticks(np.arange(0, 150, 20))
        if name == 'co2':
            plot.set_ylim([0, 1000])
            plot.set_title('CO2')
            plot.set_ylabel('ppm')
        elif name == 'nox':
            plot.set_ylim([0, 200])
            plot.set_title('NOX')
            plot.set_ylabel('ppb')
        elif name == 'bc':
            plot.set_ylim([0, 100])
            plot.set_title('BC')
            plot.set_ylabel(r'$\mu g/m^3$')
            plot.set_xlabel('seconds ago')
        plot.tick_params(axis='y', left=True, right=True, labelright=True)

q = Queue()
co2 = Process(target=co2.send, args=(q,))
co2.start()
nox = Process(target=nox.send, args=(q,))
nox.start()
bc = Process(target=bc.send, args=(q,))
bc.start()

def main():
    app = wx.App()
    f = ComplexPlot(q)
    app.MainLoop()

if __name__ == '__main__':
    main()