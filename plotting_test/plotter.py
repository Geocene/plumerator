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

 
class MyFrame(wx.Frame):
    def __init__(self, queue):
        self.queue = queue
        wx.Frame.__init__(self, None, wx.ID_ANY, title='Plotter', size=(500, 700))
        self.timer = wx.Timer(self)
        self.Bind(wx.EVT_TIMER, self.OnRefresh)
        self.timer.Start(1000)

        self.panel1 = wx.Panel(self, wx.ID_ANY)
        self.panel1.SetBackgroundColour("white")
        self.panel2 = wx.Panel(self, wx.ID_ANY)
        self.panel2.SetBackgroundColour("white")
        self.panel3 = wx.Panel(self, wx.ID_ANY)
        self.panel3.SetBackgroundColour("white")
        panel1_sizer = wx.BoxSizer(wx.VERTICAL)
        panel2_sizer = wx.BoxSizer(wx.VERTICAL)
        panel3_sizer = wx.BoxSizer(wx.VERTICAL)
 
        plotter = plot.PlotCanvas(self.panel1)
        plotter.SetInitialSize(size=(500, 200))
        plotter2 = plot.PlotCanvas(self.panel2)
        plotter2.SetInitialSize(size=(500, 200))
        plotter3 = plot.PlotCanvas(self.panel3)
        plotter3.SetInitialSize(size=(500, 200))
 
        self.co2_data = []
        self.nox_data = []
        self.bc_data = []
        line = plot.PolyLine([], colour='red', width=1)
        line2 = plot.PolyLine([], colour='red', width=1)
        line3 = plot.PolyLine([], colour='red', width=1)
 
        gc = plot.PlotGraphics([line], 'CO2', 'seconds ago', 'y')
        gc2 = plot.PlotGraphics([line2], 'NOX', 'seconds ago', 'y')
        gc3 = plot.PlotGraphics([line3], 'BC', 'seconds ago', 'y')
        plotter.Draw(gc, xAxis=(0, 120))
        plotter2.Draw(gc2, xAxis=(0, 120))
        plotter3.Draw(gc3, xAxis=(0, 120))

        panel1_sizer.Add(plotter,0,wx.EXPAND) 
        self.panel1.SetSizer(panel1_sizer)
        panel2_sizer.Add(plotter2,0,wx.EXPAND) 
        self.panel2.SetSizer(panel2_sizer)
        panel3_sizer.Add(plotter3,0,wx.EXPAND)
        self.panel3.SetSizer(panel3_sizer)

        main_sizer = wx.BoxSizer(wx.VERTICAL)
        main_sizer.Add(self.panel1, 1, wx.EXPAND)
        main_sizer.Add(self.panel2, 1, wx.EXPAND)
        main_sizer.Add(self.panel3, 1, wx.EXPAND)
        self.SetSizer(main_sizer)
        self.Layout()
 
        self.Show(True)
 
    def redraw(self, event):
        self.panel1 = wx.Panel(self, wx.ID_ANY)
        self.panel1.SetBackgroundColour("white")
        self.panel2 = wx.Panel(self, wx.ID_ANY)
        self.panel2.SetBackgroundColour("white")
        self.panel3 = wx.Panel(self, wx.ID_ANY)
        self.panel3.SetBackgroundColour("white")
        panel1_sizer = wx.BoxSizer(wx.VERTICAL)
        panel2_sizer = wx.BoxSizer(wx.VERTICAL)
        panel3_sizer = wx.BoxSizer(wx.VERTICAL)
        
 
        plotter = plot.PlotCanvas(self.panel1)
        plotter.SetInitialSize(size=(500, 200))
        plotter2 = plot.PlotCanvas(self.panel2)
        plotter2.SetInitialSize(size=(500, 200))
        plotter3 = plot.PlotCanvas(self.panel3)
        plotter3.SetInitialSize(size=(500, 200))

        self.update_data()

        current_time = datetime.datetime.now()
        
        self.co2_data.sort(key=operator.itemgetter(0))
        self.nox_data.sort(key=operator.itemgetter(0))
        self.bc_data.sort(key=operator.itemgetter(0))
        co2_update = [[(current_time - x[0]).total_seconds(), x[1]] for x in self.co2_data if (current_time - x[0]).total_seconds() <= 120]
        nox_update = [[(current_time - x[0]).total_seconds(), x[1]] for x in self.nox_data if (current_time - x[0]).total_seconds() <= 120]
        bc_update = [[(current_time - x[0]).total_seconds(), x[1]] for x in self.bc_data if (current_time - x[0]).total_seconds() <= 120]

        line = plot.PolyLine(co2_update, colour='red', width=1)
        line2 = plot.PolyLine(nox_update, colour='red', width=1)
        line3 = plot.PolyLine(bc_update, colour='red', width=1)
 
        gc = plot.PlotGraphics([line], 'CO2', 'seconds ago', 'y')
        gc2 = plot.PlotGraphics([line2], 'NOX', 'seconds ago', 'y')
        gc3 = plot.PlotGraphics([line3], 'BC', 'seconds ago', 'y')
        plotter.Draw(gc, xAxis=(0, 120))
        plotter2.Draw(gc2, xAxis=(0, 120))
        plotter3.Draw(gc3, xAxis=(0, 120))

        panel1_sizer.Add(plotter,0,wx.EXPAND)
        self.panel1.SetSizer(panel1_sizer)
        panel2_sizer.Add(plotter2,0,wx.EXPAND)
        self.panel2.SetSizer(panel2_sizer)
        panel3_sizer.Add(plotter3,0,wx.EXPAND)
        self.panel3.SetSizer(panel3_sizer)

        main_sizer = wx.BoxSizer(wx.VERTICAL)
        main_sizer.Add(self.panel1, 1, wx.EXPAND)
        main_sizer.Add(self.panel2, 1, wx.EXPAND)
        main_sizer.Add(self.panel3, 1, wx.EXPAND)
        self.SetSizer(main_sizer)
        self.Layout()
 
        self.Show(True)

    def update_data(self):
        while not self.queue.empty():
            item = self.queue.get()
            print(item)
            if item[0] == 'co2':
                self.co2_data.append([item[1], item[2]])
            elif item[0] == 'nox':
                self.nox_data.append([item[1], item[2]])
            elif item[0] == 'bc':
                self.bc_data.append([item[1], item[2]])
            else:
                print('error bad send')

    def OnRefresh(self, event):
        self.redraw(event)

q = Queue()
co2 = Process(target=co2.send, args=(q,))
co2.start()
nox = Process(target=nox.send, args=(q,))
nox.start()
bc = Process(target=bc.send, args=(q,))
bc.start()

def main():
    app = wx.App()
    f = MyFrame(q)
    app.MainLoop()

if __name__ == '__main__':
    main()