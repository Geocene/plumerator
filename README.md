# python_plotting
To run:
> python plotter.py

Spins up GUI and 3 scripts (co2.py, nox.py, bc.py) which send to
multiprocessing queue. 
To package: 
> pyinstaller plotter.py

To bundle in single application:
> python -m PyInstaller -F --windowed ./cli.spec
