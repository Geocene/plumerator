# python_plotting
To run:
> python plotter.py

Spins up GUI and 3 scripts (co2.py, nox.py, bc.py) which send dummy data to a
multiprocessing queue. Data is displayed in real time across the GUI plots.
To package: 
> pyinstaller plotter.py

To bundle in single application:
> python -m PyInstaller -F --windowed ./cli.spec
